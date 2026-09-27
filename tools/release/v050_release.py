#!/usr/bin/env python3
"""! @brief v0.5.0 정식 package와 승인 기반 공개 경로를 준비합니다. """

from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE_MODULE = REPOSITORY / "packaging" / "boards-manager" / "nu54_package.py"
M31_READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "m31-ble-readiness.json"
RELEASE_READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "v0.5.0-release-readiness.json"
ROOT_INDEX_PATH = REPOSITORY / "package_nucode_nu54dk_index.json"
VERSION = "0.5.0"
RC_VERSION = "0.5.0-rc.2"
TAG = f"v{VERSION}"
PUBLISHED_SOURCE_COMMIT = "0999b6a721b4579faa6a7a4d91d04da5e4960c07"
PUBLISHED_ARCHIVE_SIZE = 8712498
PUBLISHED_ARCHIVE_SHA256 = (
    "0a7b72de5772c9d710e521552a6197a8164d5da924f78b64efa6c595fb93c972"
)
PUBLISHED_LEGAL_STATUS = "project-owner-approved-for-final-public-release"
REPOSITORY_URL = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core"
GITHUB_REPOSITORY = "EIDOSDATA/NU54DK_Arduino_Core"
PLAN_FILENAME = "v0.5.0-stable-plan.json"
TECHNICAL_GATE_IDS = (
    "m31_functionality",
    "api_examples_support_matrix",
    "windows_package_reproducibility",
    "windows_clean_install_examples_upload",
    "windows_lifecycle",
    "rc_review_and_owner_approval",
    "public_assets_and_download_smoke",
)
DOCUMENT_PATHS = {
    "release_notes": "00_Docs/05_릴리스/v0.5.0/RELEASE_NOTES.md",
    "known_issues": "00_Docs/05_릴리스/v0.5.0/KNOWN_ISSUES.md",
    "migration": "00_Docs/05_릴리스/v0.5.0/MIGRATION.md",
    "testing": "00_Docs/05_릴리스/v0.5.0/TESTING.md",
    "troubleshooting": "00_Docs/05_릴리스/v0.5.0/TROUBLESHOOTING.md",
}
DOCUMENT_ASSET_NAMES = {
    role: f"NU54DK_{VERSION}_{Path(path).stem}.md"
    for role, path in DOCUMENT_PATHS.items()
}
PACKAGE_ROLES = ("archive", "checksums", "licenses", "manifest", "notices", "sbom")
ASSET_ROLES = PACKAGE_ROLES + tuple(DOCUMENT_PATHS) + ("index",)
APPROVAL_FIELDS = {
    "schema_version",
    "milestone",
    "decision",
    "version",
    "target_commit",
    "stable_plan_sha256",
    "approver_role",
    "approval_source",
    "approved_at_utc",
}


class StableReleaseFailure(RuntimeError):
    """! @brief stable 준비 또는 공개 안전 계약 위반입니다. """


@dataclass(frozen=True)
class CommandResult:
    """! @brief 외부 명령의 byte 단위 결과입니다. """

    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[Sequence[str], Path | None], CommandResult]


## @brief JSON 중복 key와 잘못된 UTF-8을 거부합니다.
def strict_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StableReleaseFailure(f"duplicate JSON key: {path}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StableReleaseFailure(f"invalid UTF-8 JSON: {path}: {error}") from error


## @brief 재현 가능한 JSON byte를 만듭니다.
def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


## @brief 파일의 SHA-256을 계산합니다.
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief 지정 경로의 Python 모듈을 격리 이름으로 로드합니다.
def load_module(name: str, path: Path) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise StableReleaseFailure(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


## @brief 실제 외부 명령을 byte 단위로 실행합니다.
def run_external(arguments: Sequence[str], cwd: Path | None) -> CommandResult:
    result = subprocess.run(
        tuple(arguments),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return CommandResult(result.returncode, result.stdout, result.stderr)


## @brief 외부 명령의 성공을 요구합니다.
def require_command(runner: Runner, arguments: Sequence[str], cwd: Path | None) -> bytes:
    result = runner(arguments, cwd)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise StableReleaseFailure(f"external command failed: {arguments[0]}: {detail}")
    return result.stdout


## @brief exact clean main commit과 submodule 상태를 검증합니다.
def assert_exact_source(repository: Path, revision: str) -> str:
    repository = repository.resolve()
    commit = require_command(
        run_external,
        ("git", "rev-parse", f"{revision}^{{commit}}"),
        repository,
    ).decode("ascii", "strict").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise StableReleaseFailure("exact source commit이 유효하지 않습니다")
    head = require_command(run_external, ("git", "rev-parse", "HEAD"), repository)
    if head.decode("ascii", "strict").strip() != commit:
        raise StableReleaseFailure("checkout HEAD와 exact source commit이 다릅니다")
    branch = require_command(
        run_external,
        ("git", "branch", "--show-current"),
        repository,
    ).decode("utf-8", "strict").strip()
    if branch != "main":
        raise StableReleaseFailure("v0.5.0 정식 준비는 main에서만 허용합니다")
    status = require_command(
        run_external,
        (
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ),
        repository,
    )
    if status.strip():
        raise StableReleaseFailure("v0.5.0 정식 준비에는 clean checkout이 필요합니다")
    submodules = require_command(
        run_external,
        ("git", "submodule", "status", "--recursive"),
        repository,
    ).decode("utf-8", "strict")
    board = [
        line
        for line in submodules.splitlines()
        if "board_package/NU54DK_Zephyr_DTS" in line
    ]
    if len(board) != 1 or not board[0].startswith(" "):
        raise StableReleaseFailure("고정 board submodule 상태를 확인하지 못했습니다")
    return commit


## @brief M31 완료와 stable 공개 전후의 모든 기술 gate가 통과했는지 확인합니다.
def validate_technical_readiness(repository: Path) -> dict[str, Any]:
    repository = repository.resolve()
    m31 = strict_json(repository / M31_READINESS_PATH.relative_to(REPOSITORY))
    release = strict_json(repository / RELEASE_READINESS_PATH.relative_to(REPOSITORY))
    work = m31.get("work_packages") if isinstance(m31, dict) else None
    if (
        not isinstance(work, list)
        or len(work) != 8
        or any(item.get("status") != "completed" for item in work)
    ):
        raise StableReleaseFailure("M31 W01~W08 완료 계약이 다릅니다")
    if (
        not isinstance(release, dict)
        or release.get("release") != "v0.5.0"
        or release.get("host_scope") != "Windows 10/11 x64"
    ):
        raise StableReleaseFailure("v0.5.0 release readiness identity가 다릅니다")
    gate_list = release.get("gates")
    if not isinstance(gate_list, list):
        raise StableReleaseFailure("v0.5.0 release gate 목록이 없습니다")
    gates = {gate.get("id"): gate for gate in gate_list}
    blockers = [
        gate_id
        for gate_id in TECHNICAL_GATE_IDS
        if gates.get(gate_id, {}).get("status") != "PASS"
    ]
    if blockers:
        raise StableReleaseFailure(
            f"정식 릴리스 기술 gate가 미완료입니다: {','.join(blockers)}"
        )
    stable = gates.get("stable_v0.5.0_publication", {})
    if stable.get("kind") != "human":
        raise StableReleaseFailure("stable 승인 gate 종류가 다릅니다")
    pre_publication = (
        stable.get("status") == "HOLD"
        and release.get("publication_allowed") is False
    )
    published = (
        stable.get("status") == "PASS"
        and release.get("publication_allowed") is True
        and release.get("status") == "stable_published"
        and isinstance(release.get("stable_release"), dict)
        and release["stable_release"].get("source_revision")
        == PUBLISHED_SOURCE_COMMIT
        and release["stable_release"].get("public_smoke") == "PASS"
    )
    if not pre_publication and not published:
        raise StableReleaseFailure("stable 공개 전후 gate 상태가 다릅니다")
    return release


## @brief 공개 전 후보를 구성하거나 공개된 v0.5.0 고정 identity를 검증합니다.
def configure_stable_package(package: Any, commit: str) -> None:
    in_stable = VERSION in package.STABLE_VERSIONS
    in_package = VERSION in package.PACKAGE_VERSIONS
    if in_stable or in_package:
        archive = package.PUBLISHED_STABLE_ARCHIVE_IDENTITIES.get(VERSION)
        if not in_stable or not in_package:
            raise StableReleaseFailure("v0.5.0 permanent allowlist가 불완전합니다")
        if (
            commit != PUBLISHED_SOURCE_COMMIT
            or package.release_channel(VERSION) != "stable"
            or package.release_tag(VERSION) != TAG
            or package.STABLE_RELEASE_COMMITS.get(VERSION) != PUBLISHED_SOURCE_COMMIT
            or archive
            != {
                "size": PUBLISHED_ARCHIVE_SIZE,
                "sha256": PUBLISHED_ARCHIVE_SHA256,
            }
            or package.STABLE_LEGAL_REVIEW_STATUSES.get(VERSION)
            != PUBLISHED_LEGAL_STATUS
        ):
            raise StableReleaseFailure("published v0.5.0 package identity가 다릅니다")
        return
    try:
        package.configure_unpublished_stable(VERSION, commit)
    except package.PackageError as error:
        raise StableReleaseFailure(str(error)) from error
    if (
        package.release_channel(VERSION) != "stable"
        or package.release_tag(VERSION) != TAG
        or package.STABLE_RELEASE_COMMITS.get(VERSION) != commit
        or package.STABLE_LEGAL_REVIEW_STATUSES.get(VERSION) != package.LEGAL_REVIEW_REQUIRED
    ):
        raise StableReleaseFailure("unpublished stable package contract drifted")


## @brief 출력 경로 안의 regular file identity를 기록합니다.
def artifact_record(base: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file() or resolved.is_symlink():
        raise StableReleaseFailure(f"artifact escaped output directory: {path}")
    return {
        "path": resolved.relative_to(base.resolve()).as_posix(),
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


## @brief 두 stable build의 역할·이름·크기·byte identity를 비교합니다.
def compare_builds(first: dict[str, Path], second: dict[str, Path]) -> dict[str, str]:
    if set(first) != set(PACKAGE_ROLES) or set(second) != set(PACKAGE_ROLES):
        raise StableReleaseFailure("stable package artifact role set is invalid")
    hashes: dict[str, str] = {}
    for role in PACKAGE_ROLES:
        left = first[role]
        right = second[role]
        if left.name != right.name or left.stat().st_size != right.stat().st_size:
            raise StableReleaseFailure(f"stable package reproducibility mismatch: {role}")
        if left.read_bytes() != right.read_bytes():
            raise StableReleaseFailure(f"stable package reproducibility mismatch: {role}")
        hashes[role] = sha256_file(left)
    return hashes


## @brief v0.5.0 하나만 공급하는 stable catalog를 생성합니다.
def build_stable_index(package: Any, output: Path, archive_dir: Path) -> Path:
    try:
        destination = package.generate_index(
            archive_dir,
            [VERSION],
            destination=output / package.STABLE_INDEX_FILENAME,
        )
        package.validate_index(destination)
    except package.PackageError as error:
        raise StableReleaseFailure(str(error)) from error
    document = strict_json(destination)
    versions = [item["version"] for item in document["packages"][0]["platforms"]]
    if versions != [VERSION]:
        raise StableReleaseFailure("stable catalog는 v0.5.0 하나만 제공해야 합니다")
    return destination


## @brief exact commit의 stable 사용자 문서를 공개 asset 이름으로 복사합니다.
def copy_documents(repository: Path, output: Path, commit: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for role, relative in DOCUMENT_PATHS.items():
        completed = subprocess.run(
            ("git", "-C", str(repository), "show", f"{commit}:{relative}"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise StableReleaseFailure(f"stable release document is missing: {relative}")
        try:
            text = completed.stdout.decode("utf-8")
        except UnicodeDecodeError as error:
            raise StableReleaseFailure(f"stable release document is not UTF-8: {relative}") from error
        if not text.strip():
            raise StableReleaseFailure(f"stable release document is empty: {relative}")
        destination = output / DOCUMENT_ASSET_NAMES[role]
        destination.write_bytes(completed.stdout)
        result[role] = destination
    return result


## @brief 비공개 stable package와 승인 결합 전 publication plan을 준비합니다.
def prepare(repository: Path, output: Path, commit: str) -> Path:
    repository = repository.resolve()
    output = output.resolve()
    exact_commit = assert_exact_source(repository, commit)
    validate_technical_readiness(repository)
    if output.exists() and any(output.iterdir()):
        raise StableReleaseFailure(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output / "artifacts"
    package = load_module("nu54_v050_stable_package", PACKAGE_MODULE)
    configure_stable_package(package, exact_commit)
    try:
        with tempfile.TemporaryDirectory(prefix="nu54-v050-stable-") as temporary:
            first = package.build_package(repository, artifacts_dir, VERSION, exact_commit)
            second = package.build_package(repository, Path(temporary), VERSION, exact_commit)
            hashes = compare_builds(first, second)
        manifest = package.validate_archive(
            first["archive"], expected_version=VERSION, expected_commit=exact_commit
        )
    except package.PackageError as error:
        raise StableReleaseFailure(str(error)) from error
    index = build_stable_index(package, output, artifacts_dir)
    documents = copy_documents(repository, output, exact_commit)
    paths = {**first, **documents, "index": index}
    artifacts = {role: artifact_record(output, paths[role]) for role in ASSET_ROLES}
    plan = {
        "schema_version": 1,
        "milestone": "v0.5.0",
        "kind": "v0.5.0-stable-publication-plan",
        "version": VERSION,
        "release_tag": TAG,
        "repository": REPOSITORY_URL,
        "target_commit": exact_commit,
        "board_revision": manifest["board_revision"],
        "runtime_payload_sha256": manifest["runtime_payload_sha256"],
        "rc_version": RC_VERSION,
        "m31_readiness_sha256": sha256_file(
            repository / M31_READINESS_PATH.relative_to(REPOSITORY)
        ),
        "release_readiness_sha256": sha256_file(
            repository / RELEASE_READINESS_PATH.relative_to(REPOSITORY)
        ),
        "technical_gates": list(TECHNICAL_GATE_IDS),
        "owner_approval_required": True,
        "publication_allowed": False,
        "status": "awaiting-project-owner-approval",
        "current_stable_index": artifact_record(repository, repository / ROOT_INDEX_PATH.relative_to(REPOSITORY)),
        "reproducibility": {
            "isolated_builds": 2,
            "artifact_hashes": hashes,
            "runtime_equal_to_rc": False,
            "runtime_difference_reason": "RC2 이후 Standard runtime PM 연속 Upload 교정",
        },
        "artifacts": artifacts,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    plan_path = output / PLAN_FILENAME
    plan_path.write_bytes(canonical_json(plan))
    validate_plan(plan_path, repository=repository)
    return plan_path


## @brief stable plan, source, readiness와 모든 artifact byte를 재검증합니다.
def validate_plan(plan_path: Path, *, repository: Path = REPOSITORY) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    repository = repository.resolve()
    plan = strict_json(plan_path)
    fixed = {
        "schema_version": 1,
        "milestone": "v0.5.0",
        "kind": "v0.5.0-stable-publication-plan",
        "version": VERSION,
        "release_tag": TAG,
        "repository": REPOSITORY_URL,
        "owner_approval_required": True,
        "publication_allowed": False,
        "status": "awaiting-project-owner-approval",
    }
    if not isinstance(plan, dict) or any(plan.get(key) != value for key, value in fixed.items()):
        raise StableReleaseFailure("stable plan identity or HOLD policy is invalid")
    commit = plan.get("target_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise StableReleaseFailure("stable plan target commit is invalid")
    assert_exact_source(repository, commit)
    validate_technical_readiness(repository)
    if plan.get("m31_readiness_sha256") != sha256_file(
        repository / M31_READINESS_PATH.relative_to(REPOSITORY)
    ):
        raise StableReleaseFailure("M31 readiness evidence가 변경됐습니다")
    if plan.get("release_readiness_sha256") != sha256_file(
        repository / RELEASE_READINESS_PATH.relative_to(REPOSITORY)
    ):
        raise StableReleaseFailure("v0.5.0 release readiness evidence가 변경됐습니다")
    if plan.get("technical_gates") != list(TECHNICAL_GATE_IDS):
        raise StableReleaseFailure("stable plan technical gate 집합이 변경됐습니다")
    if plan.get("rc_version") != RC_VERSION:
        raise StableReleaseFailure("검토한 RC version이 변경됐습니다")
    reproducibility = plan.get("reproducibility")
    if (
        not isinstance(reproducibility, dict)
        or reproducibility.get("isolated_builds") != 2
        or reproducibility.get("runtime_equal_to_rc") is not False
        or not reproducibility.get("runtime_difference_reason")
    ):
        raise StableReleaseFailure("stable package 재현성 계약이 잘못됐습니다")
    artifacts = plan.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(ASSET_ROLES):
        raise StableReleaseFailure("stable plan artifact role set is invalid")
    resolved: dict[str, Path] = {}
    for role, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise StableReleaseFailure(f"stable artifact record is invalid: {role}")
        path = (plan_path.parent / str(record["path"])).resolve()
        if not path.is_relative_to(plan_path.parent) or not path.is_file() or path.is_symlink():
            raise StableReleaseFailure(f"stable artifact is missing or escaped: {role}")
        if path.stat().st_size != record["size"] or sha256_file(path) != record["sha256"]:
            raise StableReleaseFailure(f"stable artifact identity changed: {role}")
        resolved[role] = path
    package = load_module("nu54_v050_stable_validate", PACKAGE_MODULE)
    configure_stable_package(package, commit)
    try:
        manifest = package.validate_archive(
            resolved["archive"], expected_version=VERSION, expected_commit=commit
        )
        package.validate_index(resolved["index"])
    except package.PackageError as error:
        raise StableReleaseFailure(str(error)) from error
    if (
        manifest["board_revision"] != plan.get("board_revision")
        or manifest["runtime_payload_sha256"] != plan.get("runtime_payload_sha256")
    ):
        raise StableReleaseFailure("stable package provenance differs from the plan")
    current = plan.get("current_stable_index")
    root = repository / ROOT_INDEX_PATH.relative_to(REPOSITORY)
    if not isinstance(current, dict) or set(current) != {"path", "size", "sha256"}:
        raise StableReleaseFailure("current stable index binding is invalid")
    if root.stat().st_size != current["size"] or sha256_file(root) != current["sha256"]:
        raise StableReleaseFailure("current stable index changed after plan preparation")
    return plan


## @brief 명시적 소유자 승인 문서를 exact stable plan에 결합합니다.
def validate_approval(plan_path: Path, approval_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    approval = strict_json(approval_path.resolve())
    fixed = {
        "schema_version": 1,
        "milestone": "v0.5.0",
        "decision": "approved",
        "version": VERSION,
        "target_commit": plan["target_commit"],
        "stable_plan_sha256": sha256_file(plan_path.resolve()),
        "approver_role": "project-owner",
        "approval_source": "explicit-project-owner-approval",
    }
    if not isinstance(approval, dict) or set(approval) != APPROVAL_FIELDS:
        raise StableReleaseFailure("v0.5.0 승인 evidence schema가 잘못됐습니다")
    if any(approval.get(key) != value for key, value in fixed.items()):
        raise StableReleaseFailure("승인이 이 exact stable plan을 허가하지 않습니다")
    timestamp = approval.get("approved_at_utc")
    if not isinstance(timestamp, str) or not timestamp.endswith(("Z", "+00:00")):
        raise StableReleaseFailure("승인 시각이 유효하지 않습니다")
    return approval


## @brief 원격 main과 tag/Release 부재를 쓰기 없이 검사합니다.
def publication_dry_run(
    plan_path: Path,
    approval_path: Path,
    *,
    repository: Path = REPOSITORY,
    runner: Runner = run_external,
) -> dict[str, Any]:
    plan = validate_plan(plan_path, repository=repository)
    validate_approval(plan_path, approval_path, plan)
    commit = plan["target_commit"]
    branch = require_command(runner, ("git", "branch", "--show-current"), repository).decode(
        "utf-8", "strict"
    ).strip()
    if branch != "main":
        raise StableReleaseFailure("stable publication requires the main branch")
    remote = require_command(
        runner,
        ("git", "ls-remote", "--exit-code", "origin", "refs/heads/main"),
        repository,
    ).decode("ascii", "strict").strip()
    if remote != f"{commit}\trefs/heads/main":
        raise StableReleaseFailure("remote origin/main differs from the approved commit")
    tag = runner(("git", "ls-remote", "--tags", "origin", f"refs/tags/{TAG}"), repository)
    if tag.returncode != 0 or tag.stdout.strip():
        raise StableReleaseFailure("stable tag already exists or its absence is uncertain")
    release = runner(("gh", "release", "view", TAG, "--repo", GITHUB_REPOSITORY), None)
    detail = (release.stdout + b"\n" + release.stderr).decode("utf-8", "replace").casefold()
    if release.returncode == 0:
        raise StableReleaseFailure("stable GitHub Release already exists")
    if "not found" not in detail and "release not found" not in detail:
        raise StableReleaseFailure("stable GitHub Release absence is uncertain")
    return plan


## @brief 승인된 exact asset으로 public GitHub Release를 생성합니다.
def publish_release(
    plan_path: Path,
    approval_path: Path,
    *,
    repository: Path = REPOSITORY,
    runner: Runner = run_external,
) -> None:
    plan = publication_dry_run(
        plan_path, approval_path, repository=repository, runner=runner
    )
    output = plan_path.resolve().parent
    upload_roles = PACKAGE_ROLES + tuple(DOCUMENT_PATHS)
    assets = [str(output / plan["artifacts"][role]["path"]) for role in upload_roles]
    notes = output / plan["artifacts"]["release_notes"]["path"]
    require_command(
        runner,
        (
            "gh",
            "release",
            "create",
            TAG,
            "--repo",
            GITHUB_REPOSITORY,
            "--target",
            plan["target_commit"],
            "--title",
            f"NU54DK Arduino Core {TAG}",
            "--notes-file",
            str(notes),
            "--latest",
            *assets,
        ),
        None,
    )


## @brief 공개 Release asset을 재다운로드해 plan byte와 대조합니다.
def verify_public_assets(plan_path: Path, plan: dict[str, Any], runner: Runner) -> None:
    output = plan_path.resolve().parent
    upload_roles = PACKAGE_ROLES + tuple(DOCUMENT_PATHS)
    with tempfile.TemporaryDirectory(prefix="nu54-v050-public-assets-") as temporary:
        destination = Path(temporary)
        require_command(
            runner,
            (
                "gh",
                "release",
                "download",
                TAG,
                "--repo",
                GITHUB_REPOSITORY,
                "--dir",
                str(destination),
            ),
            None,
        )
        expected_names = {
            Path(plan["artifacts"][role]["path"]).name: plan["artifacts"][role]
            for role in upload_roles
        }
        actual = {path.name: path for path in destination.iterdir() if path.is_file()}
        if set(actual) != set(expected_names):
            raise StableReleaseFailure("public Release asset set differs from the stable plan")
        for name, path in actual.items():
            record = expected_names[name]
            if path.stat().st_size != record["size"] or sha256_file(path) != record["sha256"]:
                raise StableReleaseFailure(f"public Release asset identity differs: {name}")
            if path.read_bytes() != (output / record["path"]).read_bytes():
                raise StableReleaseFailure(f"public Release asset byte differs: {name}")


## @brief 검증된 public Release 뒤 stable root index를 별도 commit으로 게시합니다.
def publish_index(
    plan_path: Path,
    approval_path: Path,
    *,
    repository: Path = REPOSITORY,
    runner: Runner = run_external,
) -> str:
    plan = validate_plan(plan_path, repository=repository)
    validate_approval(plan_path, approval_path, plan)
    remote = require_command(
        runner,
        ("git", "ls-remote", "--exit-code", "origin", "refs/heads/main"),
        repository,
    ).decode("ascii", "strict").strip()
    if remote != f"{plan['target_commit']}\trefs/heads/main":
        raise StableReleaseFailure("stable index publication requires the approved remote main")
    verify_public_assets(plan_path, plan, runner)
    status = require_command(
        runner,
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        repository,
    )
    if status.strip():
        raise StableReleaseFailure("stable index publication requires a clean checkout")
    source = plan_path.resolve().parent / plan["artifacts"]["index"]["path"]
    destination = repository / ROOT_INDEX_PATH.relative_to(REPOSITORY)
    temporary = destination.with_suffix(".json.v050.tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)
    require_command(runner, ("git", "add", "--", str(destination)), repository)
    require_command(
        runner,
        ("git", "commit", "-m", f"release: publish NU54DK Arduino Core {TAG} index"),
        repository,
    )
    commit = require_command(runner, ("git", "rev-parse", "HEAD"), repository).decode(
        "ascii", "strict"
    ).strip()
    require_command(runner, ("git", "push", "origin", "HEAD:main"), repository)
    return commit


## @brief v0.5.0 명령을 prepare·검증·사전점검·실제 게시로 분리합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v0.5.0 stable release 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("contract")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--repository", type=Path, default=REPOSITORY)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--commit", required=True)
    validate_parser = subparsers.add_parser("validate-plan")
    validate_parser.add_argument("--plan", type=Path, required=True)
    dry_run = subparsers.add_parser("publication-dry-run")
    dry_run.add_argument("--plan", type=Path, required=True)
    dry_run.add_argument("--approval-evidence", type=Path, required=True)
    release = subparsers.add_parser("publish-release")
    release.add_argument("--plan", type=Path, required=True)
    release.add_argument("--approval-evidence", type=Path, required=True)
    index = subparsers.add_parser("publish-index")
    index.add_argument("--plan", type=Path, required=True)
    index.add_argument("--approval-evidence", type=Path, required=True)
    return parser


## @brief 명령별 안정적인 성공 표식을 출력합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "contract":
        package = load_module("nu54_v050_stable_contract", PACKAGE_MODULE)
        published = ("0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.4.1", VERSION)
        if tuple(package.STABLE_VERSIONS) != published:
            raise StableReleaseFailure("v0.5.0 stable history가 변경됐습니다")
        configure_stable_package(package, PUBLISHED_SOURCE_COMMIT)
        choices = set(build_parser()._subparsers._group_actions[0].choices)
        if choices != {
            "contract",
            "prepare",
            "validate-plan",
            "publication-dry-run",
            "publish-release",
            "publish-index",
        }:
            raise StableReleaseFailure("stable release command separation changed")
        print("V050_STABLE_CONTRACT_PASS=1;PUBLICATION_STATE=PUBLISHED")
    elif parsed.command == "prepare":
        plan = prepare(parsed.repository, parsed.output_dir, parsed.commit)
        print(f"V050_STABLE_PREPARE_HOLD=1;PLAN={plan}")
    elif parsed.command == "validate-plan":
        plan = validate_plan(parsed.plan)
        print(f"V050_STABLE_PLAN_HOLD=1;COMMIT={plan['target_commit']}")
    elif parsed.command == "publication-dry-run":
        plan = publication_dry_run(parsed.plan, parsed.approval_evidence)
        print(f"V050_STABLE_PUBLICATION_DRY_RUN_PASS={plan['target_commit']}")
    elif parsed.command == "publish-release":
        publish_release(parsed.plan, parsed.approval_evidence)
        print(f"V050_STABLE_RELEASE_PUBLISHED={TAG}")
    elif parsed.command == "publish-index":
        commit = publish_index(parsed.plan, parsed.approval_evidence)
        print(f"V050_STABLE_INDEX_PUBLISHED={commit}")
    else:
        raise StableReleaseFailure(f"unsupported command: {parsed.command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StableReleaseFailure as error:
        print(f"V050_STABLE_RELEASE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
