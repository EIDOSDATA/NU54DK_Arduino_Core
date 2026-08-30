from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "release" / "m18_release.py"
SPEC = importlib.util.spec_from_file_location("m18_release", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("M18 release 도구를 불러올 수 없습니다.")
M18 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M18
SPEC.loader.exec_module(M18)

CORE_COMMIT = "1" * 40
BOARD_COMMIT = "2" * 40


class FakePackageError(RuntimeError):
    """! @brief fake package 계약 위반입니다. """


class FakePackage:
    """! @brief 실제 ZIP 생성 없이 package API와 재현성을 모사합니다. """

    PackageError = FakePackageError
    SUPPORTED_VERSIONS = ("0.0.97",)
    RELEASE_CANDIDATE_VERSIONS = ("0.1.0-rc.2", "0.2.0-rc.1")
    STABLE_VERSIONS = ("0.1.0",)
    STABLE_RELEASE_COMMITS = {
        "0.1.0": "5dbc5e37270e477d21f578dd877f4b5226b44a0d",
    }
    STABLE_LEGAL_REVIEW_STATUSES = {
        "0.1.0": "project-owner-approved-for-final-public-release",
    }
    PACKAGE_VERSIONS = SUPPORTED_VERSIONS + RELEASE_CANDIDATE_VERSIONS + STABLE_VERSIONS
    FAILED_M10_PREVIEW_VERSIONS = ()
    SAFE_PREVIEW_VERSIONS = SUPPORTED_VERSIONS
    WINDOWS_SAFE_VERSIONS = (
        FAILED_M10_PREVIEW_VERSIONS
        + SAFE_PREVIEW_VERSIONS
        + RELEASE_CANDIDATE_VERSIONS
        + STABLE_VERSIONS
    )
    RC_INDEX_FILENAME = "package_nucode_nu54dk_rc_index.json"
    STABLE_INDEX_FILENAME = "package_nucode_nu54dk_index.json"
    REPOSITORY_URL = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core"
    BOARD_REPOSITORY_URL = "https://github.com/Nucode01/NU54DK_Zephyr_DTS"
    NCS_VERSION = "v3.4.0"
    NCS_REVISION = "99553055607b2e9885fbc80ccd11fa9da81c2df0"
    ZEPHYR_VERSION = "4.4.0"
    ZEPHYR_REVISION = "bf801e4e3d19e1ffa76164346480cb7734dd2800"
    TOOLCHAIN_BUNDLE_ID = "dcbdc366a1"

    def __init__(self, *, nondeterministic: bool = False) -> None:
        self.nondeterministic = nondeterministic
        self.build_calls = 0
        self.archive_validations = 0
        self.index_validations = 0

    def release_channel(self, version: str) -> str:
        if version in self.RELEASE_CANDIDATE_VERSIONS:
            return "release-candidate"
        if version in self.STABLE_VERSIONS:
            return "stable"
        if version in self.SUPPORTED_VERSIONS:
            return "preview"
        raise FakePackageError("unknown version")

    def release_tag(self, version: str) -> str:
        return f"v{version}" if self.release_channel(version) != "preview" else f"preview-{version}"

    def archive_filename(self, version: str) -> str:
        return f"nucode-nu54dk-zephyr-{version}.zip"

    def commit_timestamp(self, _repo_root: Path, commit: str) -> str:
        if commit != CORE_COMMIT:
            raise FakePackageError("unexpected commit")
        return "2026-08-30T00:00:00Z"

    def build_package(self, _repo_root: Path, output_dir: Path, version: str, commit: str) -> dict[str, Path]:
        self.build_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        base = f"nucode-nu54dk-zephyr-{version}"
        paths = {
            "archive": output_dir / f"{base}.zip",
            "checksums": output_dir / f"{base}.CHECKSUMS.sha256",
            "licenses": output_dir / f"{base}.license-inventory.json",
            "manifest": output_dir / f"{base}.release-manifest.json",
            "notices": output_dir / f"{base}.THIRD_PARTY_NOTICES.md",
            "sbom": output_dir / f"{base}.spdx.json",
        }
        for role, path in paths.items():
            if role == "checksums":
                continue
            suffix = b":different" if self.nondeterministic and self.build_calls == 2 and role == "archive" else b""
            path.write_bytes(f"{role}:{version}:{commit}".encode("ascii") + suffix)
        checksum_roles = ("archive", "licenses", "manifest", "notices", "sbom")
        checksums = "".join(
            f"{hashlib.sha256(paths[role].read_bytes()).hexdigest()}  {paths[role].name}\n"
            for role in sorted(checksum_roles, key=lambda item: paths[item].name.encode("utf-8"))
        )
        paths["checksums"].write_text(checksums, encoding="ascii", newline="\n")
        return paths

    def parse_checksums(self, data: bytes, *, source: str) -> dict[str, str]:
        del source
        result: dict[str, str] = {}
        for line in data.decode("ascii").splitlines():
            digest, name = line.split("  ", 1)
            result[name] = digest
        return result

    def generate_index(self, output_dir: Path, versions: list[str], destination: Path | None = None) -> Path:
        if versions != [M18.VERSION]:
            raise FakePackageError("unexpected version list")
        path = destination or output_dir / self.RC_INDEX_FILENAME
        path.write_bytes(f"index:{versions[0]}".encode("ascii"))
        return path

    def validate_archive(self, archive: Path, *, expected_version: str, expected_commit: str) -> dict:
        self.archive_validations += 1
        if not archive.is_file() or expected_version != M18.VERSION or expected_commit != CORE_COMMIT:
            raise FakePackageError("archive validation failed")
        return {
            "version": expected_version,
            "core_revision": expected_commit,
            "board_revision": BOARD_COMMIT,
        }

    def validate_index(self, index: Path, *, artifact_dir: Path | None = None) -> dict:
        self.index_validations += 1
        if not index.is_file() or artifact_dir is None:
            raise FakePackageError("index validation failed")
        return {"packages": [{"platforms": [{"version": M18.VERSION}]}]}


class FakeRunner:
    """! @brief Git과 gh를 side effect 없이 argv 단위로 모사합니다. """

    def __init__(
        self,
        *,
        core_dirty: bool = False,
        board_dirty: bool = False,
        local_tag: bool = False,
        github_tag: bool = False,
        github_release: bool = False,
        duplicate_drafts: bool = False,
        draft_visibility_delay: int = 0,
        release_id_drift: bool = False,
        tag_after_create: bool = False,
        remote_mismatch: bool = False,
        asset_state: str = "uploaded",
        asset_digest_mismatch: bool = False,
        asset_digest_missing: bool = False,
        asset_name_mismatch: bool = False,
        asset_size_mismatch: bool = False,
        duplicate_asset_ids: bool = False,
        release_url_override: str | None = None,
        current_branch: str = "main",
        head_commit: str = CORE_COMMIT,
        origin_main_commit: str = CORE_COMMIT,
        remote_main_commit: str = CORE_COMMIT,
        github_visibility: str = "PUBLIC",
        github_default_branch: str = "main",
        github_viewer_permission: str = "ADMIN",
        github_commit: str | None = CORE_COMMIT,
        release_name_mismatch: bool = False,
        release_body_mismatch: bool = False,
    ) -> None:
        self.core_dirty = core_dirty
        self.board_dirty = board_dirty
        self.local_tag = local_tag
        self.github_tag = github_tag
        self.github_release = github_release
        self.duplicate_drafts = duplicate_drafts
        self.draft_visibility_delay = draft_visibility_delay
        self.release_id_drift = release_id_drift
        self.tag_after_create = tag_after_create
        self.remote_mismatch = remote_mismatch
        self.asset_state = asset_state
        self.asset_digest_mismatch = asset_digest_mismatch
        self.asset_digest_missing = asset_digest_missing
        self.asset_name_mismatch = asset_name_mismatch
        self.asset_size_mismatch = asset_size_mismatch
        self.duplicate_asset_ids = duplicate_asset_ids
        self.release_url_override = release_url_override
        self.current_branch = current_branch
        self.head_commit = head_commit
        self.origin_main_commit = origin_main_commit
        self.remote_main_commit = remote_main_commit
        self.github_visibility = github_visibility
        self.github_default_branch = github_default_branch
        self.github_viewer_permission = github_viewer_permission
        self.github_commit = github_commit
        self.release_name_mismatch = release_name_mismatch
        self.release_body_mismatch = release_body_mismatch
        self.created = False
        self.create_argv: list[str] | None = None
        self.remote_assets: dict[str, bytes] = {}
        self.remote_asset_ids: dict[str, int] = {}
        self.remote_name = M18.EXPECTED_RELEASE_NAME
        self.remote_body = ""
        self.release_id = 9001
        self.release_list_calls_after_create = 0
        self.asset_download_ids: list[int] = []
        self.commands: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: Path | None = None) -> M18.CommandResult:
        self.commands.append(list(argv))
        if argv[0] == "git":
            return self.git(argv, cwd)
        if argv[0] == "gh":
            return self.gh(argv)
        return M18.CommandResult(127, b"", b"unknown executable")

    def git(self, argv: list[str], cwd: Path | None) -> M18.CommandResult:
        is_board = cwd is not None and Path(cwd).resolve() == (REPO_ROOT / M18.BOARD_PATH).resolve()
        if argv[1:3] == ["branch", "--show-current"]:
            return M18.CommandResult(0, f"{self.current_branch}\n".encode("utf-8"), b"")
        if argv[1:3] == ["rev-parse", "--verify"]:
            if argv[3] == "refs/remotes/origin/main^{commit}":
                return M18.CommandResult(0, self.origin_main_commit.encode("ascii") + b"\n", b"")
            return M18.CommandResult(
                0,
                (BOARD_COMMIT if is_board else self.head_commit).encode("ascii") + b"\n",
                b"",
            )
        if argv[1:3] == ["status", "--porcelain=v1"]:
            dirty = self.board_dirty if is_board else self.core_dirty
            return M18.CommandResult(0, b" M changed\n" if dirty else b"", b"")
        if argv[1:3] == ["ls-tree", CORE_COMMIT]:
            line = f"160000 commit {BOARD_COMMIT}\t{M18.BOARD_PATH}\n".encode("ascii")
            return M18.CommandResult(0, line, b"")
        if argv[1] == "show" and len(argv) == 3 and ":" in argv[2]:
            relative = argv[2].split(":", 1)[1]
            if relative == M18.EXPECTED_STABLE_INDEX_FILENAME:
                return M18.CommandResult(
                    0,
                    (REPO_ROOT / relative).read_bytes(),
                    b"",
                )
            return M18.CommandResult(
                0,
                f"# {Path(relative).name}\n\nNU54DK {M18.TAG}\n".encode("utf-8"),
                b"",
            )
        if argv[1:4] == ["show-ref", "--verify", "--quiet"]:
            return M18.CommandResult(0 if self.local_tag else 1, b"", b"")
        if argv[1:3] == ["ls-remote", "--exit-code"]:
            line = f"{self.remote_main_commit}\trefs/heads/main\n".encode("ascii")
            return M18.CommandResult(0, line, b"")
        return M18.CommandResult(2, b"", f"unexpected git argv: {argv}".encode("utf-8"))

    def release_record(self, release_id: int | None = None) -> dict:
        """! @brief 실제 Draft처럼 tag ref 없이 pending tag release를 반환합니다. """

        release_id = self.release_id if release_id is None else release_id
        assets: list[dict] = []
        for index, (name, data) in enumerate(sorted(self.remote_assets.items())):
            asset_id = self.remote_asset_ids.get(name, 10000 + index)
            if self.duplicate_asset_ids and index > 0:
                asset_id = min(self.remote_asset_ids.values())
            record = {
                "id": asset_id,
                "name": f"{name}.tampered" if self.asset_name_mismatch and index == 0 else name,
                "state": self.asset_state,
                "size": len(data) + 1 if self.asset_size_mismatch and index == 0 else len(data),
            }
            if not self.asset_digest_missing:
                digest = hashlib.sha256(data).hexdigest()
                if self.asset_digest_mismatch and index == 0:
                    digest = "0" * 64
                record["digest"] = f"sha256:{digest}"
            assets.append(record)
        return {
            "id": release_id,
            "tag_name": M18.TAG,
            "target_commitish": CORE_COMMIT,
            "draft": True,
            "prerelease": True,
            "published_at": None,
            "immutable": False,
            "name": (
                f"{self.remote_name}-tampered"
                if self.release_name_mismatch
                else self.remote_name
            ),
            "body": (
                f"{self.remote_body}\ntampered"
                if self.release_body_mismatch
                else self.remote_body
            ),
            "assets": assets,
            "html_url": self.release_url_override
            or (
                "https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/"
                f"tag/untagged-{release_id:020x}"
            ),
        }

    def release_pages(self) -> list[list[dict]]:
        """! @brief REST --paginate --slurp의 page 배열을 실제 Draft 의미로 모사합니다. """

        if self.github_release and not self.created:
            return [[self.release_record(8001)]]
        if self.created:
            self.release_list_calls_after_create += 1
            if self.release_list_calls_after_create <= self.draft_visibility_delay:
                return [[]]
            if self.duplicate_drafts:
                return [[self.release_record(8001)], [self.release_record(8002)]]
            if self.release_id_drift and self.release_list_calls_after_create > 1:
                return [[self.release_record(self.release_id + 1)]]
            return [[self.release_record()]]
        return [[]]

    def gh(self, argv: list[str]) -> M18.CommandResult:
        if argv[1:3] == ["auth", "status"]:
            return M18.CommandResult(0, b"authenticated\n", b"")
        if argv[1:3] == ["repo", "view"]:
            value = {
                "visibility": self.github_visibility,
                "defaultBranchRef": {"name": self.github_default_branch},
                "url": M18.EXPECTED_REPOSITORY_URL,
                "viewerPermission": self.github_viewer_permission,
            }
            return M18.CommandResult(0, json.dumps(value).encode("utf-8"), b"")
        endpoint = next(
            (value for value in reversed(argv[2:]) if value.startswith("repos/")),
            "",
        )
        if argv[1] == "api" and "/commits/" in endpoint:
            if self.github_commit is None:
                return M18.CommandResult(1, b"", b"HTTP 404: Not Found")
            return M18.CommandResult(
                0,
                json.dumps({"sha": self.github_commit}).encode("utf-8"),
                b"",
            )
        if argv[1] == "api" and "/git/ref/tags/" in endpoint:
            if self.github_tag or (self.created and self.tag_after_create):
                value = {"object": {"type": "commit", "sha": CORE_COMMIT}}
                return M18.CommandResult(0, json.dumps(value).encode("utf-8"), b"")
            return M18.CommandResult(1, b"", b"HTTP 404: Not Found")
        if argv[1] == "api" and endpoint.endswith("/releases/latest"):
            return M18.CommandResult(0, b'{"tag_name":"v0.1.0"}', b"")
        if argv[1] == "api" and endpoint.endswith("/releases?per_page=100"):
            return M18.CommandResult(
                0,
                json.dumps(self.release_pages()).encode("utf-8"),
                b"",
            )
        if argv[1] == "api" and "/releases/assets/" in endpoint:
            try:
                asset_id = int(endpoint.rsplit("/", 1)[1])
                name = next(
                    name
                    for name, candidate_id in self.remote_asset_ids.items()
                    if candidate_id == asset_id
                )
            except (ValueError, StopIteration):
                return M18.CommandResult(1, b"", b"HTTP 404: Not Found")
            self.asset_download_ids.append(asset_id)
            data = self.remote_assets[name]
            if self.remote_mismatch and asset_id == min(self.remote_asset_ids.values()):
                data = bytes([data[0] ^ 1]) + data[1:] if data else b"x"
            return M18.CommandResult(0, data, b"")
        if argv[1] == "api" and "/releases/" in endpoint:
            try:
                release_id = int(endpoint.rsplit("/", 1)[1])
            except ValueError:
                return M18.CommandResult(1, b"", b"HTTP 404: Not Found")
            if release_id != self.release_id:
                return M18.CommandResult(1, b"", b"HTTP 404: Not Found")
            return M18.CommandResult(
                0,
                json.dumps(self.release_record()).encode("utf-8"),
                b"",
            )
        if argv[1:3] == ["release", "create"]:
            self.created = True
            self.create_argv = list(argv)
            self.remote_name = argv[argv.index("--title") + 1]
            self.remote_body = Path(argv[argv.index("--notes-file") + 1]).read_bytes().decode("utf-8")
            self.remote_assets = {
                Path(value).name: Path(value).read_bytes()
                for value in argv
                if Path(value).is_file()
            }
            self.remote_asset_ids = {
                name: 10000 + index
                for index, name in enumerate(sorted(self.remote_assets))
            }
            return M18.CommandResult(
                0,
                (
                    "https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/"
                    "tag/untagged-00000000000000002329\n"
                ).encode("ascii"),
                b"",
            )
        return M18.CommandResult(2, b"", f"unexpected gh argv: {argv}".encode("utf-8"))


class M18ReleaseTests(unittest.TestCase):
    """! @brief M18 Draft Release의 재현성, 경계와 gh 계약 시험입니다. """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m18-test-")
        self.output = Path(self.temporary.name) / "release"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self, *, package: FakePackage | None = None, runner: FakeRunner | None = None) -> tuple[Path, FakePackage, FakeRunner]:
        package = package or FakePackage()
        runner = runner or FakeRunner()
        plan = M18.prepare_release(
            REPO_ROOT,
            self.output,
            CORE_COMMIT,
            package=package,
            runner=runner,
        )
        return plan, package, runner

    def test_prepare_builds_twice_and_validates_exact_allowlist(self) -> None:
        plan_path, package, runner = self.prepare()
        plan = M18.validate_plan(plan_path, package=package, runner=runner)
        self.assertEqual(package.build_calls, 4)
        self.assertEqual(plan["version"], M18.VERSION)
        self.assertEqual(plan["final_state"], M18.FINAL_STATE)
        self.assertEqual(
            {record["file_name"] for record in plan["assets"]},
            M18.expected_asset_names(package),
        )
        self.assertNotIn("package_nucode_nu54dk_index.json", M18.expected_asset_names(package))

    def test_nondeterministic_second_build_is_rejected(self) -> None:
        with self.assertRaisesRegex(M18.M18Error, "재현되지 않습니다"):
            self.prepare(package=FakePackage(nondeterministic=True))

    def test_dirty_core_and_dirty_board_are_rejected(self) -> None:
        with self.assertRaisesRegex(M18.M18Error, "Core worktree"):
            self.prepare(runner=FakeRunner(core_dirty=True))
        with self.assertRaisesRegex(M18.M18Error, "board submodule worktree"):
            self.prepare(runner=FakeRunner(board_dirty=True))

    def test_stable_contract_change_is_rejected(self) -> None:
        package = FakePackage()
        package.STABLE_VERSIONS = ("0.1.0", "0.2.0")
        with self.assertRaisesRegex(M18.M18Error, "STABLE_VERSIONS"):
            self.prepare(package=package)

    def test_stable_root_index_crlf_worktree_is_rejected(self) -> None:
        """! @brief Windows CRLF로 변형된 stable index를 M18이 거부하는지 검증합니다. """

        source_root = Path(self.temporary.name) / "crlf-source"
        source_root.mkdir()
        canonical = (REPO_ROOT / M18.EXPECTED_STABLE_INDEX_FILENAME).read_bytes()
        self.assertIn(b"\n", canonical)
        self.assertNotIn(b"\r\n", canonical)
        (source_root / M18.EXPECTED_STABLE_INDEX_FILENAME).write_bytes(
            canonical.replace(b"\n", b"\r\n")
        )

        with self.assertRaisesRegex(M18.M18Error, "stable root index byte 계약"):
            M18.assert_stable_root_index(FakeRunner(), source_root, CORE_COMMIT)

    def test_package_contract_is_read_only_and_rejects_rc_or_pin_mutation(self) -> None:
        package = FakePackage()
        original = package.RELEASE_CANDIDATE_VERSIONS
        package.RELEASE_CANDIDATE_VERSIONS = (M18.VERSION,)
        with self.assertRaisesRegex(M18.M18Error, "release candidate allowlist"):
            self.prepare(package=package)
        self.assertEqual(package.RELEASE_CANDIDATE_VERSIONS, (M18.VERSION,))

        package = FakePackage()
        package.NCS_REVISION = "f" * 40
        with self.assertRaisesRegex(M18.M18Error, "NCS_REVISION"):
            self.prepare(package=package)
        self.assertEqual(original, ("0.1.0-rc.2", "0.2.0-rc.1"))

    def test_asset_tamper_and_extra_file_are_rejected(self) -> None:
        plan_path, package, runner = self.prepare()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        target = self.output / plan["assets"][0]["file_name"]
        target.write_bytes(target.read_bytes() + b"tampered")
        with self.assertRaisesRegex(M18.M18Error, "asset byte"):
            M18.validate_plan(plan_path, package=package, runner=runner)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m18-test-")
        self.output = Path(self.temporary.name) / "release"
        plan_path, package, runner = self.prepare()
        (self.output / "unexpected.bin").write_bytes(b"x")
        with self.assertRaisesRegex(M18.M18Error, "allowlist 밖"):
            M18.validate_plan(plan_path, package=package, runner=runner)

    def test_plan_unknown_field_is_rejected(self) -> None:
        plan_path, package, runner = self.prepare()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["publish_stable"] = True
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(M18.M18Error, "field 계약"):
            M18.validate_plan(plan_path, package=package, runner=runner)

    def test_immutable_plan_fields_and_roles_are_rejected_when_tampered(self) -> None:
        plan_path, package, runner = self.prepare()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["created_at_utc"] = "2026-08-31T00:00:00Z"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(M18.M18Error, "created_at_utc"):
            M18.validate_plan(plan_path, package=package, runner=runner)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m18-test-")
        self.output = Path(self.temporary.name) / "release"
        plan_path, package, runner = self.prepare()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["publication"]["next_action"] = "publish stable"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(M18.M18Error, "publication"):
            M18.validate_plan(plan_path, package=package, runner=runner)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m18-test-")
        self.output = Path(self.temporary.name) / "release"
        plan_path, package, runner = self.prepare()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["assets"][0]["role"] = "archive"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(M18.M18Error, "asset role"):
            M18.validate_plan(plan_path, package=package, runner=runner)

    def test_evidence_artifact_and_document_blob_tamper_are_rejected(self) -> None:
        plan_path, package, runner = self.prepare()
        evidence_path = self.output / M18.EVIDENCE_FILENAME
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["reproducibility"]["artifact_records"]["archive"]["size"] += 1
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        for record in plan["assets"]:
            if record["file_name"] == M18.EVIDENCE_FILENAME:
                record["size"] = evidence_path.stat().st_size
                record["sha256"] = M18.file_sha256(evidence_path)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(M18.M18Error, "artifact record"):
            M18.validate_plan(plan_path, package=package, runner=runner)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m18-test-")
        self.output = Path(self.temporary.name) / "release"
        plan_path, package, runner = self.prepare()
        document = self.output / M18.DOCUMENT_ASSET_NAMES["migration"]
        document.write_bytes(document.read_bytes() + b"tampered")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        evidence_path = self.output / M18.EVIDENCE_FILENAME
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["assets"]["migration"] = M18.asset_record(document, "migration")
        evidence_path.write_bytes(M18.canonical_json(evidence))
        for record in plan["assets"]:
            if record["file_name"] == document.name:
                record.update(M18.asset_record(document, "migration"))
            elif record["file_name"] == evidence_path.name:
                record.update(M18.asset_record(evidence_path, "evidence_manifest"))
        plan_path.write_bytes(M18.canonical_json(plan))
        with self.assertRaisesRegex(M18.M18Error, "exact commit blob"):
            M18.validate_plan(plan_path, package=package, runner=runner)

    def test_checksum_sidecar_forgery_is_rejected_even_when_records_are_rehashed(self) -> None:
        plan_path, package, runner = self.prepare()
        checksums = self.output / M18.EXPECTED_PACKAGE_ASSET_NAMES["checksums"]
        lines = checksums.read_text(encoding="ascii").splitlines()
        _digest, name = lines[0].split("  ", 1)
        lines[0] = f"{'0' * 64}  {name}"
        checksums.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        evidence_path = self.output / M18.EVIDENCE_FILENAME
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        forged = M18.asset_record(checksums, "checksums")
        evidence["assets"]["checksums"] = forged
        evidence["reproducibility"]["artifact_records"]["checksums"] = {
            key: forged[key] for key in ("file_name", "sha256", "size")
        }
        evidence_path.write_bytes(M18.canonical_json(evidence))
        for record in plan["assets"]:
            if record["file_name"] == checksums.name:
                record.update(forged)
            elif record["file_name"] == evidence_path.name:
                record.update(M18.asset_record(evidence_path, "evidence_manifest"))
        plan_path.write_bytes(M18.canonical_json(plan))
        with self.assertRaisesRegex(M18.M18Error, "checksum sidecar"):
            M18.validate_plan(plan_path, package=package, runner=runner)

    def test_unexpected_directory_and_symlink_are_rejected(self) -> None:
        plan_path, package, runner = self.prepare()
        (self.output / "unexpected-dir").mkdir()
        with self.assertRaisesRegex(M18.M18Error, "allowlist 밖"):
            M18.validate_plan(plan_path, package=package, runner=runner)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m18-test-")
        self.output = Path(self.temporary.name) / "release"
        plan_path, package, runner = self.prepare()
        target = self.output / M18.DOCUMENT_ASSET_NAMES["migration"]
        original_is_symlink = Path.is_symlink
        with mock.patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=lambda path: path.name == target.name or original_is_symlink(path),
        ):
            with self.assertRaisesRegex(M18.M18Error, "regular file"):
                M18.validate_plan(plan_path, package=package, runner=runner)

    def test_publish_draft_uses_only_safe_flags_and_rechecks_remote_bytes(self) -> None:
        """! @brief untagged Draft를 ID 기반으로 생성·검증하고 tag download를 쓰지 않습니다. """

        plan_path, package, runner = self.prepare()
        url = M18.publish_draft(plan_path, package=package, runner=runner)
        self.assertTrue(
            url.startswith(
                "https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/untagged-"
            )
        )
        self.assertIsNotNone(runner.create_argv)
        argv = runner.create_argv or []
        self.assertIn("--draft", argv)
        self.assertIn("--prerelease", argv)
        self.assertIn("--latest=false", argv)
        self.assertNotIn("--clobber", argv)
        self.assertNotIn("--force", argv)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        uploaded = {Path(value).name for value in argv if Path(value).is_file()}
        self.assertEqual(uploaded, {record["file_name"] for record in plan["assets"]})
        expected_ids = set(runner.remote_asset_ids.values())
        self.assertEqual(set(runner.asset_download_ids), expected_ids)
        self.assertEqual(len(runner.asset_download_ids), len(expected_ids))
        self.assertTrue(
            any(
                command[-1]
                == f"repos/EIDOSDATA/NU54DK_Arduino_Core/releases/{runner.release_id}"
                for command in runner.commands
            )
        )
        self.assertFalse(
            any(command[1:3] == ["release", "download"] for command in runner.commands)
        )
        tag_queries = [
            command
            for command in runner.commands
            if command[0:2] == ["gh", "api"]
            and command[-1].endswith(f"/git/ref/tags/{M18.TAG}")
        ]
        self.assertEqual(len(tag_queries), 2)
        created_argv = list(runner.create_argv or [])
        verified = M18.verify_draft(plan_path, package=package, runner=runner)
        self.assertEqual(verified, url)
        self.assertEqual(runner.create_argv, created_argv)
        self.assertEqual(set(runner.asset_download_ids), expected_ids)
        self.assertEqual(len(runner.asset_download_ids), 2 * len(expected_ids))

    def test_publish_rejects_existing_local_or_github_release(self) -> None:
        """! @brief local tag 및 REST 목록에서 보이는 기존·중복 Draft를 생성 전에 거부합니다. """

        plan_path, package, _ = self.prepare()
        with self.assertRaisesRegex(M18.M18Error, "local Git tag"):
            M18.publish_draft(plan_path, package=package, runner=FakeRunner(local_tag=True))
        with self.assertRaisesRegex(M18.M18Error, "이미 존재"):
            M18.publish_draft(plan_path, package=package, runner=FakeRunner(github_release=True))
        duplicate = FakeRunner(duplicate_drafts=True)
        with self.assertRaisesRegex(M18.M18Error, "중복되었습니다"):
            M18.publish_draft(plan_path, package=package, runner=duplicate)
        self.assertTrue(duplicate.created)

        remote_tag = FakeRunner(github_tag=True)
        with self.assertRaisesRegex(M18.M18Error, "이미 존재"):
            M18.publish_draft(plan_path, package=package, runner=remote_tag)
        self.assertFalse(remote_tag.created)

    def test_publish_waits_for_delayed_draft_and_bounds_discovery(self) -> None:
        """! @brief Draft 목록의 짧은 지연은 재조회하고 무한 대기는 하지 않습니다. """

        plan_path, package, _ = self.prepare()
        delayed = FakeRunner(draft_visibility_delay=2)
        sleeps: list[float] = []
        url = M18.publish_draft(
            plan_path,
            package=package,
            runner=delayed,
            sleeper=sleeps.append,
        )
        self.assertIn("/releases/tag/untagged-", url)
        self.assertEqual(sleeps, [M18.DRAFT_DISCOVERY_INTERVAL_SECONDS] * 2)

        timed_out = FakeRunner(draft_visibility_delay=M18.DRAFT_DISCOVERY_ATTEMPTS)
        sleeps = []
        with self.assertRaisesRegex(M18.M18Error, "제한 시간"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=timed_out,
                sleeper=sleeps.append,
            )
        self.assertTrue(timed_out.created)
        self.assertEqual(
            sleeps,
            [M18.DRAFT_DISCOVERY_INTERVAL_SECONDS]
            * (M18.DRAFT_DISCOVERY_ATTEMPTS - 1),
        )

    def test_publish_rejects_remote_tag_created_during_draft(self) -> None:
        """! @brief Draft 생성 뒤 원격 tag ref가 생기면 Draft 계약 위반으로 거부합니다. """

        plan_path, package, _ = self.prepare()
        runner = FakeRunner(tag_after_create=True)
        with self.assertRaisesRegex(M18.M18Error, "이미 존재"):
            M18.publish_draft(plan_path, package=package, runner=runner)
        self.assertTrue(runner.created)

    def test_publish_binds_verification_to_discovered_release_id(self) -> None:
        """! @brief 생성 직후 발견한 release ID가 재조회 중 바뀌면 검증을 중단합니다. """

        plan_path, package, _ = self.prepare()
        runner = FakeRunner(release_id_drift=True)
        with self.assertRaisesRegex(M18.M18Error, "생성 직후 확인한 ID"):
            M18.publish_draft(plan_path, package=package, runner=runner)
        self.assertTrue(runner.created)

    def test_publish_rejects_non_main_or_unpushed_origin_main(self) -> None:
        """! @brief main/current HEAD/origin-main과 remote main 불일치를 거부합니다. """

        plan_path, package, _ = self.prepare()
        with self.assertRaisesRegex(M18.M18Error, "current branch"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(current_branch="codex/m18"),
            )
        with self.assertRaisesRegex(M18.M18Error, "현재 HEAD"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(head_commit=BOARD_COMMIT),
            )
        with self.assertRaisesRegex(M18.M18Error, "local origin/main"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(origin_main_commit=BOARD_COMMIT),
            )
        with self.assertRaisesRegex(M18.M18Error, "원격 origin/main"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(remote_main_commit=BOARD_COMMIT),
            )

    def test_publish_rejects_non_public_repository_or_missing_remote_commit(self) -> None:
        """! @brief PUBLIC/default main과 GitHub target commit 부재를 거부합니다. """

        plan_path, package, _ = self.prepare()
        with self.assertRaisesRegex(M18.M18Error, "PUBLIC"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(github_visibility="PRIVATE"),
            )
        with self.assertRaisesRegex(M18.M18Error, "default main"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(github_default_branch="develop"),
            )
        with self.assertRaisesRegex(M18.M18Error, "WRITE 이상"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(github_viewer_permission="READ"),
            )
        with self.assertRaisesRegex(M18.M18Error, "target commit을 찾지 못했습니다"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(github_commit=None),
            )
        with self.assertRaisesRegex(M18.M18Error, "commit identity"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(github_commit=BOARD_COMMIT),
            )

    def test_verify_rejects_release_name_or_body_mismatch(self) -> None:
        """! @brief GitHub Release 제목과 본문이 exact local 문서와 다르면 거부합니다. """

        plan_path, package, _ = self.prepare()
        with self.assertRaisesRegex(M18.M18Error, "제목 또는 본문"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(release_name_mismatch=True),
            )
        with self.assertRaisesRegex(M18.M18Error, "제목 또는 본문"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(release_body_mismatch=True),
            )

    def test_publish_rejects_remote_sha_mismatch(self) -> None:
        """! @brief asset ID·이름·상태·크기·digest와 다운로드 byte 불일치를 거부합니다. """

        plan_path, package, _ = self.prepare()
        with self.assertRaisesRegex(M18.M18Error, "remote asset SHA-256"):
            M18.publish_draft(plan_path, package=package, runner=FakeRunner(remote_mismatch=True))
        with self.assertRaisesRegex(M18.M18Error, "asset digest"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(asset_digest_mismatch=True),
            )
        with self.assertRaisesRegex(M18.M18Error, "ID/name/state/size"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(asset_state="new"),
            )
        with self.assertRaisesRegex(M18.M18Error, "이름 또는 크기"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(asset_name_mismatch=True),
            )
        with self.assertRaisesRegex(M18.M18Error, "이름 또는 크기"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(asset_size_mismatch=True),
            )
        with self.assertRaisesRegex(M18.M18Error, "ID 또는 이름이 중복"):
            M18.publish_draft(
                plan_path,
                package=package,
                runner=FakeRunner(duplicate_asset_ids=True),
            )

    def test_verify_accepts_missing_optional_digest_and_rejects_foreign_url(self) -> None:
        """! @brief 미지원 digest 생략은 허용하되 다른 저장소 Draft URL은 거부합니다. """

        plan_path, package, _ = self.prepare()
        runner = FakeRunner(asset_digest_missing=True)
        url = M18.publish_draft(plan_path, package=package, runner=runner)
        self.assertIn("/releases/tag/untagged-", url)

        foreign = FakeRunner(
            release_url_override=(
                "https://github.com/EIDOSDATA/NU54DK_Arduino_Core-evil/"
                "releases/tag/untagged-0001"
            )
        )
        with self.assertRaisesRegex(M18.M18Error, "저장소 경계 밖"):
            M18.publish_draft(plan_path, package=package, runner=foreign)

    def test_cli_exposes_no_stable_publish_or_version_override(self) -> None:
        parser = M18.build_parser()
        help_text = parser.format_help()
        self.assertIn("publish-draft", help_text)
        self.assertIn("verify-draft", help_text)
        self.assertNotIn("publish-stable", help_text)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["prepare", "--output-dir", "x", "--commit", CORE_COMMIT, "--version", "0.2.0"])

    def test_external_process_is_always_shell_false(self) -> None:
        completed = subprocess.CompletedProcess(["gh", "--version"], 0, b"ok", b"")
        with mock.patch.object(M18.subprocess, "run", return_value=completed) as mocked:
            result = M18.run_external(["gh", "--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIs(mocked.call_args.kwargs["shell"], False)


if __name__ == "__main__":
    unittest.main()
