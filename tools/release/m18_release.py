#!/usr/bin/env python3
"""! @brief NU54DK v0.2.0-rc.2 Draft Release를 재현 가능하고 비파괴적으로 준비합니다. """

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable


SCHEMA_VERSION = 1
MILESTONE = "M18"
VERSION = "0.2.0-rc.2"
TAG = "v0.2.0-rc.2"
EXPECTED_RELEASE_NAME = f"NU54DK Arduino Core {TAG}"
FINAL_STATE = "awaiting-clean-windows-manual-validation"
EXPECTED_NEXT_ACTION = (
    "clean Windows Arduino IDE 설치·compile·upload 수동 검증 후 프로젝트 소유자 승인"
)
PLAN_FILENAME = "m18-draft-plan.json"
EVIDENCE_FILENAME = f"NU54DK_{VERSION}_EVIDENCE.json"
EXPECTED_REPOSITORY_URL = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core"
EXPECTED_BOARD_REPOSITORY_URL = "https://github.com/Nucode01/NU54DK_Zephyr_DTS"
EXPECTED_RC_VERSIONS = ("0.1.0-rc.2", "0.2.0-rc.1", VERSION)
EXPECTED_RC_INDEX_FILENAME = "package_nucode_nu54dk_rc_index.json"
EXPECTED_STABLE_INDEX_FILENAME = "package_nucode_nu54dk_index.json"
EXPECTED_STABLE_INDEX_SIZE = 1125
EXPECTED_STABLE_INDEX_SHA256 = (
    "385445512ba6bb842024979e8314f2f953eb15a14e3ce72076b6d475e2e7583d"
)
EXPECTED_STABLE_VERSIONS = ("0.1.0",)
EXPECTED_STABLE_RELEASE_COMMITS = {
    "0.1.0": "5dbc5e37270e477d21f578dd877f4b5226b44a0d",
}
EXPECTED_STABLE_LEGAL_REVIEW_STATUSES = {
    "0.1.0": "project-owner-approved-for-final-public-release",
}
STABLE_SOURCE_PATHS = (
    EXPECTED_STABLE_INDEX_FILENAME,
    "packaging/boards-manager/nu54_package.py",
)
EXPECTED_PINS = {
    "NCS_VERSION": "v3.4.0",
    "NCS_REVISION": "99553055607b2e9885fbc80ccd11fa9da81c2df0",
    "ZEPHYR_VERSION": "4.4.0",
    "ZEPHYR_REVISION": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
    "TOOLCHAIN_BUNDLE_ID": "dcbdc366a1",
}
BOARD_PATH = "board_package/NU54DK_Zephyr_DTS"
DOCUMENT_PATHS = {
    "release_notes": "00_Docs/05_릴리스/v0.2.0/RELEASE_NOTES.md",
    "known_issues": "00_Docs/05_릴리스/v0.2.0/KNOWN_ISSUES.md",
    "migration": "00_Docs/05_릴리스/v0.2.0/MIGRATION.md",
    "troubleshooting": "00_Docs/05_릴리스/v0.2.0/TROUBLESHOOTING.md",
}
DOCUMENT_ASSET_NAMES = {
    "release_notes": f"NU54DK_{VERSION}_RELEASE_NOTES.md",
    "known_issues": f"NU54DK_{VERSION}_KNOWN_ISSUES.md",
    "migration": f"NU54DK_{VERSION}_MIGRATION.md",
    "troubleshooting": f"NU54DK_{VERSION}_TROUBLESHOOTING.md",
}
PACKAGE_ARTIFACT_KEYS = (
    "archive",
    "checksums",
    "licenses",
    "manifest",
    "notices",
    "sbom",
    "index",
)
EXPECTED_PACKAGE_ASSET_NAMES = {
    "archive": f"nucode-nu54dk-zephyr-{VERSION}.zip",
    "checksums": f"nucode-nu54dk-zephyr-{VERSION}.CHECKSUMS.sha256",
    "licenses": f"nucode-nu54dk-zephyr-{VERSION}.license-inventory.json",
    "manifest": f"nucode-nu54dk-zephyr-{VERSION}.release-manifest.json",
    "notices": f"nucode-nu54dk-zephyr-{VERSION}.THIRD_PARTY_NOTICES.md",
    "sbom": f"nucode-nu54dk-zephyr-{VERSION}.spdx.json",
    "index": EXPECTED_RC_INDEX_FILENAME,
}
EXPECTED_PRIMARY_ROLES_BY_NAME = {
    **{name: role for role, name in EXPECTED_PACKAGE_ASSET_NAMES.items()},
    **{name: role for role, name in DOCUMENT_ASSET_NAMES.items()},
}
EXPECTED_ASSET_ROLES_BY_NAME = {
    **EXPECTED_PRIMARY_ROLES_BY_NAME,
    EVIDENCE_FILENAME: "evidence_manifest",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class M18Error(RuntimeError):
    """! @brief 안전하게 계속할 수 없는 M18 Draft Release 오류입니다. """


## @brief 같은 저장소의 Boards Manager package 모듈을 읽습니다.
def load_package_module() -> Any:
    path = Path(__file__).resolve().parents[2] / "packaging" / "boards-manager" / "nu54_package.py"
    specification = importlib.util.spec_from_file_location("nu54_m18_package", path)
    if specification is None or specification.loader is None:
        raise M18Error(f"package 모듈을 읽을 수 없습니다: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


PACKAGE = load_package_module()


@dataclass(frozen=True)
class CommandResult:
    """! @brief shell 없이 실행한 외부 명령의 최소 결과입니다. """

    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[list[str], Path | None], CommandResult]
Sleeper = Callable[[float], None]

## @brief GitHub Draft가 REST 목록에 반영되기를 기다리는 최대 조회 횟수입니다.
DRAFT_DISCOVERY_ATTEMPTS = 10
## @brief GitHub Draft REST 목록 재조회 간격입니다.
DRAFT_DISCOVERY_INTERVAL_SECONDS = 1.0


## @brief 사용자 command 문자열 없이 argv 배열과 shell=False로 외부 명령을 실행합니다.
def run_external(argv: list[str], cwd: Path | None = None) -> CommandResult:
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise M18Error("외부 명령 argv가 유효하지 않습니다.")
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            shell=False,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise M18Error(f"외부 명령을 시작하지 못했습니다: {argv[0]}: {error}") from error
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


## @brief 실패한 외부 명령을 M18 오류로 변환합니다.
def require_command(runner: Runner, argv: list[str], cwd: Path | None = None) -> bytes:
    result = runner(argv, cwd)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise M18Error(f"외부 명령 실패: {argv[0]}: {detail}")
    return result.stdout


## @brief JSON object의 중복 key를 거부합니다.
def strict_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M18Error(f"중복 JSON key를 허용하지 않습니다: {path}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except M18Error:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise M18Error(f"UTF-8 JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(value, dict):
        raise M18Error(f"JSON 최상위 값은 object여야 합니다: {path}")
    return value


## @brief JSON을 byte 단위로 재현 가능한 형식으로 직렬화합니다.
def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


## @brief 파일 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise M18Error(f"파일 SHA-256을 계산하지 못했습니다: {path}: {error}") from error
    return digest.hexdigest()


## @brief release asset record를 만듭니다.
def asset_record(path: Path, role: str) -> dict[str, Any]:
    if not path.is_file():
        raise M18Error(f"release asset이 없습니다: {path}")
    return {
        "file_name": path.name,
        "role": role,
        "sha256": file_sha256(path),
        "size": path.stat().st_size,
    }


## @brief package 모듈을 수정하지 않고 M18 RC, 저장소, pin과 stable 계약을 확인합니다.
def assert_package_contract(package: Any) -> None:
    if tuple(package.RELEASE_CANDIDATE_VERSIONS) != EXPECTED_RC_VERSIONS:
        raise M18Error("release candidate allowlist가 M18 고정 계약과 다릅니다.")
    if tuple(package.STABLE_VERSIONS) != EXPECTED_STABLE_VERSIONS:
        raise M18Error("STABLE_VERSIONS 변경을 M18 RC 도구에서 허용하지 않습니다.")
    if dict(package.STABLE_RELEASE_COMMITS) != EXPECTED_STABLE_RELEASE_COMMITS:
        raise M18Error("stable release commit map 변경을 M18 RC 도구에서 허용하지 않습니다.")
    if (
        dict(package.STABLE_LEGAL_REVIEW_STATUSES)
        != EXPECTED_STABLE_LEGAL_REVIEW_STATUSES
    ):
        raise M18Error("stable legal review map 변경을 M18 RC 도구에서 허용하지 않습니다.")
    if package.REPOSITORY_URL != EXPECTED_REPOSITORY_URL:
        raise M18Error("source repository URL이 M18 고정 계약과 다릅니다.")
    if package.BOARD_REPOSITORY_URL != EXPECTED_BOARD_REPOSITORY_URL:
        raise M18Error("board repository URL이 M18 고정 계약과 다릅니다.")
    if package.RC_INDEX_FILENAME != EXPECTED_RC_INDEX_FILENAME:
        raise M18Error("RC index filename이 M18 고정 계약과 다릅니다.")
    if package.STABLE_INDEX_FILENAME != EXPECTED_STABLE_INDEX_FILENAME:
        raise M18Error("stable index filename이 M18 고정 계약과 다릅니다.")
    if package.RC_INDEX_FILENAME == package.STABLE_INDEX_FILENAME:
        raise M18Error("RC와 stable index filename은 반드시 분리되어야 합니다.")
    for name, expected in EXPECTED_PINS.items():
        if getattr(package, name, None) != expected:
            raise M18Error(f"package pin {name}이 M18 고정 계약과 다릅니다.")
    expected_package_versions = (
        tuple(package.SUPPORTED_VERSIONS)
        + EXPECTED_RC_VERSIONS
        + EXPECTED_STABLE_VERSIONS
    )
    expected_windows_versions = (
        tuple(package.FAILED_M10_PREVIEW_VERSIONS)
        + tuple(package.SAFE_PREVIEW_VERSIONS)
        + EXPECTED_RC_VERSIONS
        + EXPECTED_STABLE_VERSIONS
    )
    if tuple(package.PACKAGE_VERSIONS) != expected_package_versions:
        raise M18Error("package version allowlist가 M18 고정 계약과 다릅니다.")
    if tuple(package.WINDOWS_SAFE_VERSIONS) != expected_windows_versions:
        raise M18Error("Windows-safe version allowlist가 M18 고정 계약과 다릅니다.")
    if package.release_channel(VERSION) != "release-candidate" or package.release_tag(VERSION) != TAG:
        raise M18Error("package 모듈의 v0.2.0-rc.2 channel/tag 계약이 잘못되었습니다.")
    if package.archive_filename(VERSION) != EXPECTED_PACKAGE_ASSET_NAMES["archive"]:
        raise M18Error("M18 archive filename 계약이 잘못되었습니다.")


## @brief repo-relative Git 경로의 traversal을 거부합니다.
def safe_git_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise M18Error(f"안전하지 않은 Git 경로입니다: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise M18Error(f"안전하지 않은 Git 상대 경로입니다: {value}")
    return pure.as_posix()


## @brief exact commit의 Git blob을 worktree 변환 없이 읽습니다.
def git_blob_at_commit(runner: Runner, repo_root: Path, commit: str, relative: str) -> bytes:
    relative = safe_git_path(relative)
    return require_command(runner, ["git", "show", f"{commit}:{relative}"], repo_root)


## @brief exact clean Core commit과 clean exact board gitlink를 강제합니다.
def assert_clean_source(runner: Runner, repo_root: Path, commit: str) -> str:
    if not COMMIT_RE.fullmatch(commit):
        raise M18Error("--commit은 lowercase 40자리 exact Git commit이어야 합니다.")
    actual = require_command(
        runner, ["git", "rev-parse", "--verify", "HEAD^{commit}"], repo_root
    ).decode("ascii", "strict").strip()
    if actual != commit:
        raise M18Error(f"M18 source commit은 현재 HEAD와 같아야 합니다: expected={commit}, HEAD={actual}")
    status = require_command(
        runner, ["git", "status", "--porcelain=v1", "--untracked-files=all"], repo_root
    )
    if status.strip():
        raise M18Error("Core worktree가 깨끗하지 않습니다.")
    tree = require_command(
        runner, ["git", "ls-tree", commit, "--", BOARD_PATH], repo_root
    ).decode("utf-8", "strict").strip()
    match = re.fullmatch(rf"160000 commit ([0-9a-f]{{40}})\t{re.escape(BOARD_PATH)}", tree)
    if not match:
        raise M18Error("exact commit에 유효한 board gitlink가 없습니다.")
    expected_board = match.group(1)
    board_root = repo_root / BOARD_PATH
    actual_board = require_command(
        runner, ["git", "rev-parse", "--verify", "HEAD^{commit}"], board_root
    ).decode("ascii", "strict").strip()
    if actual_board != expected_board:
        raise M18Error(
            f"board submodule revision이 gitlink와 다릅니다: expected={expected_board}, actual={actual_board}"
        )
    board_status = require_command(
        runner, ["git", "status", "--porcelain=v1", "--untracked-files=all"], board_root
    )
    if board_status.strip():
        raise M18Error("board submodule worktree가 깨끗하지 않습니다.")
    return expected_board


## @brief 출력 경로가 source와 섞이지 않도록 build/ 또는 저장소 외부로 제한합니다.
def assert_safe_output(repo_root: Path, output_dir: Path) -> None:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    try:
        relative = output_dir.relative_to(repo_root)
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != "build":
        raise M18Error("저장소 내부 출력은 gitignored build/ 아래만 허용합니다.")


## @brief stable index와 package stable map source의 byte identity를 고정합니다.
def stable_source_snapshot(repo_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in STABLE_SOURCE_PATHS:
        path = repo_root / relative
        if not path.is_file():
            raise M18Error(f"stable 보호 대상 파일이 없습니다: {relative}")
        result[relative] = file_sha256(path)
    return result


## @brief 공개 v0.1 stable root index가 worktree와 exact commit에서 byte 불변인지 확인합니다.
def assert_stable_root_index(
    runner: Runner, repo_root: Path, commit: str
) -> None:
    path = repo_root / EXPECTED_STABLE_INDEX_FILENAME
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != EXPECTED_STABLE_INDEX_SIZE
        or file_sha256(path) != EXPECTED_STABLE_INDEX_SHA256
    ):
        raise M18Error("공개 v0.1 stable root index byte 계약이 변경되었습니다.")
    committed = git_blob_at_commit(
        runner, repo_root, commit, EXPECTED_STABLE_INDEX_FILENAME
    )
    if (
        len(committed) != EXPECTED_STABLE_INDEX_SIZE
        or hashlib.sha256(committed).hexdigest() != EXPECTED_STABLE_INDEX_SHA256
        or committed != path.read_bytes()
    ):
        raise M18Error("exact commit의 v0.1 stable root index byte 계약이 변경되었습니다.")


## @brief release output의 모든 항목이 exact regular-file allowlist인지 확인합니다.
def assert_output_entries(output_dir: Path, expected_names: set[str]) -> None:
    try:
        entries = list(output_dir.iterdir())
    except OSError as error:
        raise M18Error(f"M18 output directory를 읽지 못했습니다: {error}") from error
    actual_names = {path.name for path in entries}
    if len(entries) != len(actual_names) or actual_names != expected_names:
        raise M18Error("M18 output에 plan/allowlist 밖의 파일 또는 directory가 있습니다.")
    for path in entries:
        try:
            mode = path.lstat().st_mode
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
        except OSError as error:
            raise M18Error(f"M18 output 항목 상태를 읽지 못했습니다: {path}: {error}") from error
        reparse = bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        if path.is_symlink() or reparse or not stat.S_ISREG(mode):
            raise M18Error(f"M18 output에는 regular file만 허용합니다: {path.name}")


## @brief package 산출물 2세트가 key, filename과 byte까지 같은지 확인합니다.
def compare_reproducible_builds(
    first: dict[str, Path], second: dict[str, Path]
) -> dict[str, dict[str, Any]]:
    if set(first) != set(PACKAGE_ARTIFACT_KEYS) or set(second) != set(PACKAGE_ARTIFACT_KEYS):
        raise M18Error("package build artifact key 집합이 M18 allowlist와 다릅니다.")
    records: dict[str, dict[str, Any]] = {}
    for key in PACKAGE_ARTIFACT_KEYS:
        left = first[key]
        right = second[key]
        if left.name != right.name:
            raise M18Error(f"독립 package build filename이 다릅니다: {key}")
        left_hash = file_sha256(left)
        right_hash = file_sha256(right)
        if left_hash != right_hash or left.read_bytes() != right.read_bytes():
            raise M18Error(f"독립 package build byte가 재현되지 않습니다: {key}")
        records[key] = {"file_name": left.name, "sha256": left_hash, "size": left.stat().st_size}
    return records


## @brief package 모듈로 RC archive/index 한 세트를 생성하고 엄격 검증합니다.
def build_package_once(package: Any, repo_root: Path, output_dir: Path, commit: str) -> tuple[dict[str, Path], dict[str, Any]]:
    try:
        artifacts = package.build_package(repo_root, output_dir, VERSION, commit)
        index = package.generate_index(
            output_dir,
            [VERSION],
            destination=output_dir / package.RC_INDEX_FILENAME,
        )
        manifest = package.validate_archive(
            artifacts["archive"], expected_version=VERSION, expected_commit=commit
        )
        package.validate_index(index, artifact_dir=output_dir)
    except package.PackageError as error:
        raise M18Error(f"package module 검증 실패: {error}") from error
    combined = {**artifacts, "index": index}
    actual_names = {role: path.name for role, path in combined.items()}
    if actual_names != EXPECTED_PACKAGE_ASSET_NAMES:
        raise M18Error("package artifact role/filename allowlist가 고정 계약과 다릅니다.")
    return combined, manifest


## @brief 외부 checksum sidecar가 archive와 네 metadata sidecar byte를 정확히 묶는지 확인합니다.
def validate_external_checksums(
    package: Any, output_dir: Path, records: dict[str, dict[str, Any]]
) -> None:
    checksums_path = output_dir / EXPECTED_PACKAGE_ASSET_NAMES["checksums"]
    try:
        parsed = package.parse_checksums(
            checksums_path.read_bytes(), source=checksums_path.name
        )
    except (OSError, package.PackageError) as error:
        raise M18Error(f"외부 checksum sidecar를 검증하지 못했습니다: {error}") from error
    expected_roles = ("archive", "licenses", "manifest", "notices", "sbom")
    expected_names = [EXPECTED_PACKAGE_ASSET_NAMES[role] for role in expected_roles]
    if list(parsed) != sorted(expected_names, key=lambda name: name.encode("utf-8")):
        raise M18Error("외부 checksum sidecar filename allowlist가 다릅니다.")
    for role in expected_roles:
        name = EXPECTED_PACKAGE_ASSET_NAMES[role]
        record = records.get(name)
        if record is None or parsed.get(name) != record.get("sha256"):
            raise M18Error(f"외부 checksum sidecar가 asset record와 다릅니다: {name}")


## @brief M18 asset 이름의 exact allowlist를 계산합니다.
def expected_asset_names(package: Any) -> set[str]:
    assert_package_contract(package)
    return set(EXPECTED_ASSET_ROLES_BY_NAME)


## @brief v0.2.0-rc.2 package와 Draft Release plan을 두 독립 build에서 준비합니다.
def prepare_release(
    repo_root: Path,
    output_dir: Path,
    commit: str,
    *,
    document_paths: dict[str, str] | None = None,
    package: Any = PACKAGE,
    runner: Runner = run_external,
) -> Path:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    if repo_root != Path(__file__).resolve().parents[2]:
        raise M18Error("M18 source와 실행 중인 release/package 도구는 같은 저장소 root여야 합니다.")
    assert_safe_output(repo_root, output_dir)
    assert_package_contract(package)
    board_revision = assert_clean_source(runner, repo_root, commit)
    assert_stable_root_index(runner, repo_root, commit)
    before_stable = stable_source_snapshot(repo_root)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise M18Error("M18 output directory는 새로 만들거나 비어 있어야 하며 clobber하지 않습니다.")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = dict(DOCUMENT_PATHS if document_paths is None else document_paths)
    if paths != DOCUMENT_PATHS:
        raise M18Error("네 release document는 M18 canonical Git 경로만 허용합니다.")

    with tempfile.TemporaryDirectory(prefix=".m18-a-", dir=output_dir) as first_temp, tempfile.TemporaryDirectory(
        prefix=".m18-b-", dir=output_dir
    ) as second_temp:
        first, first_manifest = build_package_once(
            package, repo_root, Path(first_temp), commit
        )
        second, second_manifest = build_package_once(
            package, repo_root, Path(second_temp), commit
        )
        if first_manifest != second_manifest:
            raise M18Error("독립 package build의 strict archive manifest가 다릅니다.")
        reproducibility = compare_reproducible_builds(first, second)
        documents = {
            role: git_blob_at_commit(runner, repo_root, commit, relative)
            for role, relative in sorted(paths.items())
        }
        for role, data in documents.items():
            try:
                if not data.decode("utf-8").strip():
                    raise M18Error(f"{role} 문서가 비어 있습니다.")
            except UnicodeDecodeError as error:
                raise M18Error(f"{role} 문서가 UTF-8이 아닙니다.") from error
        for artifact in first.values():
            shutil.copy2(artifact, output_dir / artifact.name)

    document_assets: dict[str, Path] = {}
    for role, data in documents.items():
        destination = output_dir / DOCUMENT_ASSET_NAMES[role]
        destination.write_bytes(data)
        document_assets[role] = destination

    package_assets = {key: output_dir / record["file_name"] for key, record in reproducibility.items()}
    primary_paths = {**package_assets, **document_assets}
    primary_records = {
        role: asset_record(path, role)
        for role, path in sorted(primary_paths.items())
    }
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "kind": "draft-release-evidence",
        "version": VERSION,
        "release_tag": TAG,
        "core_revision": commit,
        "board_revision": board_revision,
        "final_state": FINAL_STATE,
        "reproducibility": {
            "independent_builds": 2,
            "archive_and_index_byte_identical": True,
            "artifact_records": reproducibility,
        },
        "assets": primary_records,
        "stable_boundary": {
            "stable_versions": list(EXPECTED_STABLE_VERSIONS),
            "stable_legal_review_statuses": EXPECTED_STABLE_LEGAL_REVIEW_STATUSES,
            "stable_index_file_name": EXPECTED_STABLE_INDEX_FILENAME,
            "stable_index_size": EXPECTED_STABLE_INDEX_SIZE,
            "stable_index_sha256": EXPECTED_STABLE_INDEX_SHA256,
            "stable_index_uploaded": False,
            "stable_map_modified": False,
            "stable_publication_implemented": False,
        },
    }
    evidence_path = output_dir / EVIDENCE_FILENAME
    evidence_path.write_bytes(canonical_json(evidence))

    upload_paths = {path.name: path for path in [*primary_paths.values(), evidence_path]}
    expected_names = expected_asset_names(package)
    if set(upload_paths) != expected_names:
        raise M18Error(
            f"M18 asset allowlist가 다릅니다: missing={sorted(expected_names - set(upload_paths))}, "
            f"extra={sorted(set(upload_paths) - expected_names)}"
        )
    plan_assets = [
        asset_record(upload_paths[name], EXPECTED_ASSET_ROLES_BY_NAME[name])
        for name in sorted(upload_paths)
    ]
    plan = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "kind": "draft-release-plan",
        "version": VERSION,
        "release_tag": TAG,
        "repository": EXPECTED_REPOSITORY_URL,
        "target_commit": commit,
        "board_revision": board_revision,
        "created_at_utc": package.commit_timestamp(repo_root, commit),
        "final_state": FINAL_STATE,
        "assets": plan_assets,
        "publication": {
            "draft": True,
            "prerelease": True,
            "latest": False,
            "draft_to_public_supported": False,
            "production_boards_manager_url_test_supported": False,
            "stable_publish_supported": False,
            "next_action": EXPECTED_NEXT_ACTION,
        },
        "stable_boundary": {
            "stable_versions": list(EXPECTED_STABLE_VERSIONS),
            "stable_release_commits": EXPECTED_STABLE_RELEASE_COMMITS,
            "stable_legal_review_statuses": EXPECTED_STABLE_LEGAL_REVIEW_STATUSES,
            "stable_index_file_name": EXPECTED_STABLE_INDEX_FILENAME,
            "stable_index_size": EXPECTED_STABLE_INDEX_SIZE,
            "stable_index_sha256": EXPECTED_STABLE_INDEX_SHA256,
            "stable_source_sha256": before_stable,
            "stable_assets_uploaded": [],
        },
    }
    plan_path = output_dir / PLAN_FILENAME
    plan_path.write_bytes(canonical_json(plan))
    if stable_source_snapshot(repo_root) != before_stable:
        raise M18Error("M18 준비 중 stable index/map source가 변경되었습니다.")
    assert_stable_root_index(runner, repo_root, commit)
    assert_clean_source(runner, repo_root, commit)
    validate_plan(plan_path, package=package, runner=runner)
    return plan_path


## @brief plan과 모든 asset byte, package schema 및 stable 경계를 다시 검증합니다.
def validate_plan(
    plan_path: Path,
    *,
    package: Any = PACKAGE,
    runner: Runner = run_external,
) -> dict[str, Any]:
    assert_package_contract(package)
    plan_path = plan_path.resolve()
    output_dir = plan_path.parent
    plan = strict_json(plan_path)
    expected_fields = {
        "schema_version",
        "milestone",
        "kind",
        "version",
        "release_tag",
        "repository",
        "target_commit",
        "board_revision",
        "created_at_utc",
        "final_state",
        "assets",
        "publication",
        "stable_boundary",
    }
    if set(plan) != expected_fields:
        raise M18Error("M18 plan field 계약이 다릅니다.")
    fixed = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "kind": "draft-release-plan",
        "version": VERSION,
        "release_tag": TAG,
        "repository": EXPECTED_REPOSITORY_URL,
        "final_state": FINAL_STATE,
    }
    for key, expected in fixed.items():
        if plan.get(key) != expected:
            raise M18Error(f"M18 plan {key}가 고정 계약과 다릅니다.")
    commit = plan.get("target_commit")
    if not isinstance(commit, str):
        raise M18Error("M18 plan target_commit이 없습니다.")
    repo_root = Path(__file__).resolve().parents[2]
    board_revision = assert_clean_source(runner, repo_root, commit)
    assert_stable_root_index(runner, repo_root, commit)
    if plan.get("board_revision") != board_revision:
        raise M18Error("M18 plan board revision이 source와 다릅니다.")
    try:
        expected_created_at = package.commit_timestamp(repo_root, commit)
    except package.PackageError as error:
        raise M18Error(f"exact commit 시간을 확인하지 못했습니다: {error}") from error
    if plan.get("created_at_utc") != expected_created_at:
        raise M18Error("M18 plan created_at_utc가 exact commit 시간과 다릅니다.")
    publication = plan.get("publication")
    if not isinstance(publication, dict) or set(publication) != {
        "draft",
        "prerelease",
        "latest",
        "draft_to_public_supported",
        "production_boards_manager_url_test_supported",
        "stable_publish_supported",
        "next_action",
    } or (
        publication.get("draft") is not True
        or publication.get("prerelease") is not True
        or publication.get("latest") is not False
        or publication.get("draft_to_public_supported") is not False
        or publication.get("production_boards_manager_url_test_supported") is not False
        or publication.get("stable_publish_supported") is not False
        or publication.get("next_action") != EXPECTED_NEXT_ACTION
    ):
        raise M18Error("M18 publication은 draft+prerelease+latest=false여야 합니다.")
    stable = plan.get("stable_boundary")
    if not isinstance(stable, dict) or set(stable) != {
        "stable_versions",
        "stable_release_commits",
        "stable_legal_review_statuses",
        "stable_index_file_name",
        "stable_index_size",
        "stable_index_sha256",
        "stable_source_sha256",
        "stable_assets_uploaded",
    } or (
        stable.get("stable_versions") != list(EXPECTED_STABLE_VERSIONS)
        or stable.get("stable_release_commits") != EXPECTED_STABLE_RELEASE_COMMITS
        or stable.get("stable_legal_review_statuses")
        != EXPECTED_STABLE_LEGAL_REVIEW_STATUSES
        or stable.get("stable_index_file_name") != EXPECTED_STABLE_INDEX_FILENAME
        or stable.get("stable_index_size") != EXPECTED_STABLE_INDEX_SIZE
        or stable.get("stable_index_sha256") != EXPECTED_STABLE_INDEX_SHA256
        or stable.get("stable_assets_uploaded") != []
        or stable.get("stable_source_sha256") != stable_source_snapshot(repo_root)
    ):
        raise M18Error("M18 plan stable boundary가 변경되었습니다.")
    assets = plan.get("assets")
    if not isinstance(assets, list):
        raise M18Error("M18 plan assets가 배열이 아닙니다.")
    records: dict[str, dict[str, Any]] = {}
    for record in assets:
        if not isinstance(record, dict) or set(record) != {"file_name", "role", "sha256", "size"}:
            raise M18Error("M18 asset record schema가 잘못되었습니다.")
        name = record.get("file_name")
        if not isinstance(name, str) or PurePosixPath(name).name != name or name in records:
            raise M18Error(f"M18 asset filename이 안전하지 않거나 중복되었습니다: {name!r}")
        if not SHA256_RE.fullmatch(str(record.get("sha256", ""))):
            raise M18Error(f"M18 asset SHA-256 형식이 잘못되었습니다: {name}")
        if record.get("role") != EXPECTED_ASSET_ROLES_BY_NAME.get(name):
            raise M18Error(f"M18 asset role이 고정 allowlist와 다릅니다: {name}")
        path = output_dir / name
        if not path.is_file() or path.stat().st_size != record.get("size") or file_sha256(path) != record["sha256"]:
            raise M18Error(f"M18 asset byte가 plan과 다릅니다: {name}")
        records[name] = record
    expected_names = expected_asset_names(package)
    if set(records) != expected_names:
        raise M18Error("M18 plan asset allowlist가 정확하지 않습니다.")
    assert_output_entries(output_dir, expected_names | {PLAN_FILENAME})
    archive = output_dir / EXPECTED_PACKAGE_ASSET_NAMES["archive"]
    index = output_dir / EXPECTED_RC_INDEX_FILENAME
    try:
        package.validate_archive(archive, expected_version=VERSION, expected_commit=commit)
        package.validate_index(index, artifact_dir=output_dir)
    except package.PackageError as error:
        raise M18Error(f"M18 package strict validation 실패: {error}") from error
    validate_external_checksums(package, output_dir, records)
    for role, relative in DOCUMENT_PATHS.items():
        expected_document = git_blob_at_commit(runner, repo_root, commit, relative)
        actual_document = output_dir / DOCUMENT_ASSET_NAMES[role]
        if actual_document.read_bytes() != expected_document:
            raise M18Error(f"M18 release document가 exact commit blob과 다릅니다: {role}")
    evidence = strict_json(output_dir / EVIDENCE_FILENAME)
    if set(evidence) != {
        "schema_version",
        "milestone",
        "kind",
        "version",
        "release_tag",
        "core_revision",
        "board_revision",
        "final_state",
        "reproducibility",
        "assets",
        "stable_boundary",
    } or any(
        evidence.get(key) != expected
        for key, expected in {
            "schema_version": SCHEMA_VERSION,
            "milestone": MILESTONE,
            "kind": "draft-release-evidence",
            "version": VERSION,
            "release_tag": TAG,
            "core_revision": commit,
            "board_revision": board_revision,
            "final_state": FINAL_STATE,
        }.items()
    ):
        raise M18Error("M18 evidence manifest binding이 plan과 다릅니다.")
    evidence_assets = evidence.get("assets")
    if not isinstance(evidence_assets, dict):
        raise M18Error("M18 evidence manifest assets가 object가 아닙니다.")
    evidence_by_name: dict[str, dict[str, Any]] = {}
    for role, record in evidence_assets.items():
        if not isinstance(role, str) or not isinstance(record, dict) or set(record) != {
            "file_name",
            "role",
            "sha256",
            "size",
        } or record.get("role") != role:
            raise M18Error("M18 evidence asset record schema가 잘못되었습니다.")
        name = record.get("file_name")
        if not isinstance(name, str) or name in evidence_by_name:
            raise M18Error("M18 evidence asset 이름이 유효하지 않거나 중복되었습니다.")
        evidence_by_name[name] = record
    expected_primary = {
        name: record for name, record in records.items() if name != EVIDENCE_FILENAME
    }
    if evidence_by_name != expected_primary:
        raise M18Error("M18 evidence manifest의 primary asset allowlist가 다릅니다.")
    reproducibility = evidence.get("reproducibility")
    if not isinstance(reproducibility, dict) or set(reproducibility) != {
        "independent_builds",
        "archive_and_index_byte_identical",
        "artifact_records",
    } or reproducibility.get("independent_builds") != 2 or reproducibility.get(
        "archive_and_index_byte_identical"
    ) is not True:
        raise M18Error("M18 evidence reproducibility 계약이 잘못되었습니다.")
    expected_artifact_records = {
        role: {
            "file_name": name,
            "sha256": records[name]["sha256"],
            "size": records[name]["size"],
        }
        for role, name in EXPECTED_PACKAGE_ASSET_NAMES.items()
    }
    if reproducibility.get("artifact_records") != expected_artifact_records:
        raise M18Error("M18 evidence reproducibility artifact record가 plan과 다릅니다.")
    stable_evidence = evidence.get("stable_boundary")
    if stable_evidence != {
        "stable_versions": list(EXPECTED_STABLE_VERSIONS),
        "stable_legal_review_statuses": EXPECTED_STABLE_LEGAL_REVIEW_STATUSES,
        "stable_index_file_name": EXPECTED_STABLE_INDEX_FILENAME,
        "stable_index_size": EXPECTED_STABLE_INDEX_SIZE,
        "stable_index_sha256": EXPECTED_STABLE_INDEX_SHA256,
        "stable_index_uploaded": False,
        "stable_map_modified": False,
        "stable_publication_implemented": False,
    }:
        raise M18Error("M18 evidence stable boundary가 잘못되었습니다.")
    with tempfile.TemporaryDirectory(prefix="nu54-m18-validate-") as temporary:
        rebuilt, _manifest = build_package_once(
            package, repo_root, Path(temporary), commit
        )
        for role, name in EXPECTED_PACKAGE_ASSET_NAMES.items():
            if rebuilt[role].read_bytes() != (output_dir / name).read_bytes():
                raise M18Error(f"exact commit 재빌드 byte가 plan asset과 다릅니다: {role}")
    return plan


## @brief gh API가 명시적으로 404/Not Found를 반환했을 때만 resource 부재로 인정합니다.
def require_github_absent(runner: Runner, argv: list[str]) -> None:
    result = runner(argv, None)
    if result.returncode == 0:
        raise M18Error("동일 tag 또는 GitHub Release가 이미 존재하므로 충돌 없이 생성할 수 없습니다.")
    detail = (result.stdout + b"\n" + result.stderr).decode("utf-8", "replace").casefold()
    if "404" not in detail and "not found" not in detail:
        raise M18Error("GitHub resource 부재를 확정하지 못했습니다.")


## @brief 인증된 REST pagination으로 pending tag가 같은 Draft까지 모두 조회합니다.
def list_github_releases_by_tag(
    runner: Runner,
    repository: str,
) -> list[dict[str, Any]]:
    raw = require_command(
        runner,
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
            f"repos/{repository}/releases?per_page=100",
        ],
    )
    try:
        pages = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise M18Error("GitHub Release pagination JSON이 유효하지 않습니다.") from error
    if not isinstance(pages, list):
        raise M18Error("GitHub Release pagination 결과가 배열이 아닙니다.")
    matches: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, list):
            raise M18Error("GitHub Release pagination page가 배열이 아닙니다.")
        for release in page:
            if not isinstance(release, dict):
                raise M18Error("GitHub Release pagination record가 object가 아닙니다.")
            if release.get("tag_name") == TAG:
                matches.append(release)
    return matches


## @brief pending tag가 같은 기존 Draft 또는 공개 Release가 없음을 강제합니다.
def require_github_release_absent(runner: Runner, repository: str) -> None:
    matches = list_github_releases_by_tag(runner, repository)
    if matches:
        raise M18Error(
            f"pending tag가 같은 GitHub Release가 이미 존재합니다: count={len(matches)}"
        )


## @brief Draft 생성 뒤 REST 목록에 exact 한 개가 나타날 때까지 짧게 재조회합니다.
def wait_for_single_github_draft(
    runner: Runner,
    repository: str,
    *,
    sleeper: Sleeper = time.sleep,
    attempts: int = DRAFT_DISCOVERY_ATTEMPTS,
    interval_seconds: float = DRAFT_DISCOVERY_INTERVAL_SECONDS,
) -> dict[str, Any]:
    if attempts < 1 or interval_seconds < 0:
        raise M18Error("Draft discovery retry 계약이 유효하지 않습니다.")
    for attempt in range(attempts):
        matches = list_github_releases_by_tag(runner, repository)
        if len(matches) > 1:
            raise M18Error(
                f"pending tag가 같은 GitHub Draft가 중복되었습니다: count={len(matches)}"
            )
        if len(matches) == 1:
            return matches[0]
        if attempt + 1 < attempts:
            sleeper(interval_seconds)
    raise M18Error("생성된 GitHub Draft가 제한 시간 안에 REST 목록에 나타나지 않았습니다.")


## @brief local tag가 이미 있으면 같은 이름의 새 Draft Release 생성을 차단합니다.
def require_local_tag_absent(runner: Runner, repo_root: Path) -> None:
    result = runner(["git", "show-ref", "--verify", "--quiet", f"refs/tags/{TAG}"], repo_root)
    if result.returncode == 0:
        raise M18Error("동일 local Git tag가 이미 존재합니다.")
    if result.returncode != 1:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise M18Error(f"local Git tag 부재를 확인하지 못했습니다: {detail}")


## @brief Draft 생성 직전에 current main, origin/main과 원격 main의 exact commit 일치를 검증합니다.
def assert_publish_source_on_origin_main(
    runner: Runner,
    repo_root: Path,
    commit: str,
) -> None:
    branch = require_command(
        runner, ["git", "branch", "--show-current"], repo_root
    ).decode("utf-8", "strict").strip()
    if branch != "main":
        raise M18Error("M18 Draft는 current branch가 main일 때만 생성할 수 있습니다.")
    head = require_command(
        runner, ["git", "rev-parse", "--verify", "HEAD^{commit}"], repo_root
    ).decode("ascii", "strict").strip()
    if head != commit:
        raise M18Error("M18 Draft target commit과 current HEAD가 다릅니다.")
    origin_main = require_command(
        runner,
        ["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"],
        repo_root,
    ).decode("ascii", "strict").strip()
    if origin_main != commit:
        raise M18Error("M18 Draft target commit과 local origin/main이 다릅니다.")
    remote = runner(
        ["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
        repo_root,
    )
    expected = f"{commit}\trefs/heads/main"
    try:
        remote_line = remote.stdout.decode("ascii", "strict").strip()
    except UnicodeDecodeError as error:
        raise M18Error("원격 origin/main 응답이 ASCII가 아닙니다.") from error
    if remote.returncode != 0 or remote_line != expected:
        raise M18Error("원격 origin/main이 M18 Draft target commit을 가리키지 않습니다.")


## @brief GitHub 저장소가 PUBLIC/default main이며 target commit을 보유하는지 검증합니다.
def assert_github_repository_contract(
    runner: Runner,
    repository: str,
    commit: str,
) -> None:
    repository_bytes = require_command(
        runner,
        [
            "gh",
            "repo",
            "view",
            repository,
            "--json",
            "visibility,defaultBranchRef,url,viewerPermission",
        ],
    )
    try:
        repository_view = json.loads(repository_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise M18Error("GitHub repository 계약 JSON이 유효하지 않습니다.") from error
    default_branch = (
        repository_view.get("defaultBranchRef")
        if isinstance(repository_view, dict)
        else None
    )
    if not isinstance(repository_view, dict) or (
        repository_view.get("visibility") != "PUBLIC"
        or repository_view.get("url") != EXPECTED_REPOSITORY_URL
        or repository_view.get("viewerPermission") not in {"WRITE", "MAINTAIN", "ADMIN"}
        or not isinstance(default_branch, dict)
        or default_branch.get("name") != "main"
    ):
        raise M18Error(
            "GitHub 저장소는 고정 URL의 PUBLIC 저장소, default main과 WRITE 이상 권한이어야 합니다."
        )
    commit_result = runner(
        ["gh", "api", f"repos/{repository}/commits/{commit}"],
        None,
    )
    if commit_result.returncode != 0:
        raise M18Error("GitHub 대상 저장소에서 M18 Draft target commit을 찾지 못했습니다.")
    try:
        commit_view = json.loads(commit_result.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise M18Error("GitHub target commit JSON이 유효하지 않습니다.") from error
    if not isinstance(commit_view, dict) or commit_view.get("sha") != commit:
        raise M18Error("GitHub 대상 저장소의 target commit identity가 다릅니다.")


## @brief explicit subcommand에서만 GitHub Draft prerelease를 생성하고 remote byte를 재검증합니다.
def publish_draft(
    plan_path: Path,
    *,
    package: Any = PACKAGE,
    runner: Runner = run_external,
    sleeper: Sleeper = time.sleep,
) -> str:
    plan = validate_plan(plan_path, package=package, runner=runner)
    output_dir = plan_path.resolve().parent
    repository_url = plan["repository"]
    match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)", repository_url)
    if not match:
        raise M18Error("GitHub repository URL에서 owner/repository를 고정하지 못했습니다.")
    repository = match.group(1)
    require_local_tag_absent(runner, Path(__file__).resolve().parents[2])
    require_command(runner, ["gh", "auth", "status", "--hostname", "github.com"])
    assert_publish_source_on_origin_main(
        runner,
        Path(__file__).resolve().parents[2],
        plan["target_commit"],
    )
    assert_github_repository_contract(runner, repository, plan["target_commit"])
    require_github_absent(
        runner,
        ["gh", "api", f"repos/{repository}/git/ref/tags/{TAG}"],
    )
    require_github_release_absent(runner, repository)
    assets = [output_dir / record["file_name"] for record in plan["assets"]]
    notes = output_dir / DOCUMENT_ASSET_NAMES["release_notes"]
    create_argv = [
        "gh",
        "release",
        "create",
        TAG,
        "--repo",
        repository,
        "--target",
        plan["target_commit"],
        "--title",
        EXPECTED_RELEASE_NAME,
        "--notes-file",
        str(notes),
        "--draft",
        "--prerelease",
        "--latest=false",
        *[str(path) for path in assets],
    ]
    require_command(runner, create_argv)
    discovered = wait_for_single_github_draft(
        runner,
        repository,
        sleeper=sleeper,
    )
    release_id = discovered.get("id")
    if not isinstance(release_id, int) or isinstance(release_id, bool) or release_id <= 0:
        raise M18Error("생성된 GitHub Draft release ID가 유효하지 않습니다.")
    return verify_draft(
        plan_path,
        package=package,
        runner=runner,
        expected_release_id=release_id,
    )


## @brief 기존 GitHub Draft prerelease를 변경하지 않고 tag, 상태와 remote byte를 검증합니다.
def verify_draft(
    plan_path: Path,
    *,
    package: Any = PACKAGE,
    runner: Runner = run_external,
    expected_release_id: int | None = None,
) -> str:
    plan = validate_plan(plan_path, package=package, runner=runner)
    output_dir = plan_path.resolve().parent
    match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)", plan["repository"])
    if not match:
        raise M18Error("GitHub repository URL에서 owner/repository를 고정하지 못했습니다.")
    repository = match.group(1)
    require_command(runner, ["gh", "auth", "status", "--hostname", "github.com"])
    assert_github_repository_contract(runner, repository, plan["target_commit"])
    matches = list_github_releases_by_tag(runner, repository)
    if len(matches) != 1:
        raise M18Error(
            f"pending tag가 같은 GitHub Draft는 정확히 하나여야 합니다: count={len(matches)}"
        )
    listed_id = matches[0].get("id")
    if not isinstance(listed_id, int) or isinstance(listed_id, bool) or listed_id <= 0:
        raise M18Error("GitHub Draft release ID가 유효하지 않습니다.")
    if expected_release_id is not None and listed_id != expected_release_id:
        raise M18Error("GitHub Draft release ID가 생성 직후 확인한 ID와 다릅니다.")
    release_bytes = require_command(
        runner,
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
            f"repos/{repository}/releases/{listed_id}",
        ],
    )
    try:
        release = json.loads(release_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise M18Error("GitHub Release 재조회 JSON이 유효하지 않습니다.") from error
    if not isinstance(release, dict) or (
        release.get("id") != listed_id
        or release.get("tag_name") != TAG
        or release.get("target_commitish") != plan["target_commit"]
        or release.get("draft") is not True
        or release.get("prerelease") is not True
        or release.get("published_at") is not None
        or release.get("immutable") is not False
    ):
        raise M18Error("생성된 GitHub Release가 draft/prerelease/target 계약과 다릅니다.")
    try:
        expected_body = (
            output_dir / DOCUMENT_ASSET_NAMES["release_notes"]
        ).read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise M18Error("local GitHub Release 제목·본문 계약을 읽지 못했습니다.") from error
    if release.get("name") != EXPECTED_RELEASE_NAME or release.get("body") != expected_body:
        raise M18Error("GitHub Release 제목 또는 본문이 exact local 계약과 다릅니다.")
    url = release.get("html_url")
    url_prefix = f"{EXPECTED_REPOSITORY_URL}/releases/tag/"
    if not isinstance(url, str) or not url.startswith(url_prefix):
        raise M18Error("Draft Release URL이 고정 GitHub 저장소 경계 밖입니다.")
    url_suffix = url[len(url_prefix) :]
    if url_suffix != TAG and not re.fullmatch(r"untagged-[A-Za-z0-9][A-Za-z0-9._-]*", url_suffix):
        raise M18Error("Draft Release URL의 tag component가 유효하지 않습니다.")
    require_github_absent(
        runner,
        ["gh", "api", f"repos/{repository}/git/ref/tags/{TAG}"],
    )
    latest_bytes = require_command(
        runner,
        ["gh", "api", f"repos/{repository}/releases/latest"],
    )
    try:
        latest = json.loads(latest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise M18Error("GitHub latest Release 재조회 JSON이 유효하지 않습니다.") from error
    if not isinstance(latest, dict) or latest.get("tag_name") == TAG:
        raise M18Error("M18 Draft Release가 latest release 경계를 침범했습니다.")
    remote_assets = release.get("assets")
    if not isinstance(remote_assets, list):
        raise M18Error("GitHub Release asset 목록이 없습니다.")
    expected_records = {record["file_name"]: record for record in plan["assets"]}
    remote_by_name: dict[str, dict[str, Any]] = {}
    remote_ids: set[int] = set()
    for item in remote_assets:
        if not isinstance(item, dict):
            raise M18Error("GitHub Release asset record schema가 잘못되었습니다.")
        asset_id = item.get("id")
        name = item.get("name")
        size = item.get("size")
        if (
            not isinstance(asset_id, int)
            or isinstance(asset_id, bool)
            or asset_id <= 0
            or not isinstance(name, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or item.get("state") != "uploaded"
        ):
            raise M18Error("GitHub Release asset ID/name/state/size 계약이 잘못되었습니다.")
        if asset_id in remote_ids or name in remote_by_name:
            raise M18Error("GitHub Release asset ID 또는 이름이 중복되었습니다.")
        expected = expected_records.get(name)
        if expected is None or size != expected["size"]:
            raise M18Error("GitHub Release asset 이름 또는 크기가 local allowlist와 다릅니다.")
        digest = item.get("digest")
        if digest is not None and digest != f"sha256:{expected['sha256']}":
            raise M18Error(f"GitHub Release asset digest가 local plan과 다릅니다: {name}")
        remote_ids.add(asset_id)
        remote_by_name[name] = item
    if set(remote_by_name) != set(expected_records):
        raise M18Error("GitHub Release asset 이름 또는 크기가 local allowlist와 다릅니다.")
    with tempfile.TemporaryDirectory(prefix="nu54-m18-download-") as temporary:
        download_root = Path(temporary)
        for name in sorted(expected_records):
            asset_id = remote_by_name[name]["id"]
            data = require_command(
                runner,
                [
                    "gh",
                    "api",
                    "-H",
                    "Accept: application/octet-stream",
                    "-H",
                    "X-GitHub-Api-Version: 2022-11-28",
                    f"repos/{repository}/releases/assets/{asset_id}",
                ],
            )
            if len(data) != expected_records[name]["size"]:
                raise M18Error(f"GitHub remote asset size가 local plan과 다릅니다: {name}")
            (download_root / name).write_bytes(data)
        assert_output_entries(download_root, set(expected_records))
        downloaded = {path.name: path for path in download_root.iterdir()}
        for name, path in downloaded.items():
            if file_sha256(path) != expected_records[name]["sha256"]:
                raise M18Error(f"GitHub remote asset SHA-256이 local plan과 다릅니다: {name}")
    return url


## @brief stable publish 기능 없이 prepare/validate/publish-draft/verify-draft만 노출합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NU54DK M18 v0.2.0-rc.2 Draft Release 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="동일 commit에서 RC package를 2회 만들고 plan 생성")
    prepare.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--commit", required=True)
    validate = subparsers.add_parser("validate", help="local Draft Release plan과 asset 재검증")
    validate.add_argument("--plan", type=Path, required=True)
    publish = subparsers.add_parser("publish-draft", help="GitHub Draft prerelease만 생성")
    publish.add_argument("--plan", type=Path, required=True)
    verify = subparsers.add_parser("verify-draft", help="기존 GitHub Draft를 read-only로 검증")
    verify.add_argument("--plan", type=Path, required=True)
    return parser


## @brief CLI 명령을 실행하고 안정적인 종료 코드를 반환합니다.
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            plan = prepare_release(
                args.repo_root,
                args.output_dir,
                args.commit,
            )
            print(f"NU54_M18_PLAN={plan}")
            print(f"NU54_M18_STATE={FINAL_STATE}")
        elif args.command == "validate":
            plan = validate_plan(args.plan)
            print(f"NU54_M18_VALID={plan['target_commit']}:{plan['final_state']}")
        elif args.command == "publish-draft":
            url = publish_draft(args.plan)
            print(f"NU54_M18_DRAFT_URL={url}")
            print(f"NU54_M18_STATE={FINAL_STATE}")
        else:
            url = verify_draft(args.plan)
            print(f"NU54_M18_DRAFT_VALID={url}")
            print(f"NU54_M18_STATE={FINAL_STATE}")
        return 0
    except M18Error as error:
        print(f"NU54_M18_ERROR={error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
