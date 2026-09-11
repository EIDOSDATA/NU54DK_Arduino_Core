#!/usr/bin/env python3
"""! @brief v0.4.1 유지보수 package를 재현 생성하고 공개 자산을 검증합니다. """

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE_MODULE = REPOSITORY / "packaging" / "boards-manager" / "nu54_package.py"
VERSION = "0.4.1"
TAG = f"v{VERSION}"
GITHUB_REPOSITORY = "EIDOSDATA/NU54DK_Arduino_Core"
PLAN_FILENAME = "v0.4.1-release-plan.json"
PACKAGE_ROLES = ("archive", "checksums", "licenses", "manifest", "notices", "sbom")
DOCUMENT_PATHS = {
    "release_notes": "00_Docs/05_릴리스/v0.4.1/RELEASE_NOTES.md",
    "known_issues": "00_Docs/05_릴리스/v0.4.1/KNOWN_ISSUES.md",
    "migration": "00_Docs/05_릴리스/v0.4.1/MIGRATION.md",
    "testing": "00_Docs/05_릴리스/v0.4.1/TESTING.md",
    "troubleshooting": "00_Docs/05_릴리스/v0.4.1/TROUBLESHOOTING.md",
}
DOCUMENT_ASSET_NAMES = {
    role: f"NU54DK_{VERSION}_{Path(path).stem}.md"
    for role, path in DOCUMENT_PATHS.items()
}
PLAN_ROLES = PACKAGE_ROLES + tuple(DOCUMENT_PATHS) + ("index",)


class ReleaseFailure(RuntimeError):
    """! @brief 릴리스 입력·상태·자산 계약 위반입니다. """


## @brief 파일의 SHA-256을 계산합니다.
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief 중복 key와 잘못된 UTF-8을 거부해 JSON을 읽습니다.
def strict_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseFailure(f"중복 JSON key입니다: {path}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseFailure(f"JSON을 읽지 못했습니다: {path}: {error}") from error


## @brief 재현 가능한 JSON byte를 생성합니다.
def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


## @brief 저장소 안의 Python 모듈을 격리 이름으로 로드합니다.
def load_module(name: str, path: Path) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ReleaseFailure(f"모듈을 읽지 못했습니다: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


## @brief Git 명령을 실행하고 ASCII 결과를 반환합니다.
def git_output(repository: Path, arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseFailure(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.decode("ascii", "strict").strip()


## @brief exact clean main source와 submodule 상태를 검증합니다.
def assert_exact_source(repository: Path, revision: str) -> str:
    commit = git_output(repository, ("rev-parse", f"{revision}^{{commit}}"))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseFailure("고정 source commit이 유효하지 않습니다.")
    if git_output(repository, ("rev-parse", "HEAD")) != commit:
        raise ReleaseFailure("checkout HEAD가 지정 source commit과 다릅니다.")
    if git_output(repository, ("branch", "--show-current")) != "main":
        raise ReleaseFailure("v0.4.1 준비는 main branch에서만 허용합니다.")
    status = git_output(
        repository,
        ("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"),
    )
    if status:
        raise ReleaseFailure("v0.4.1 준비는 clean checkout에서만 허용합니다.")
    submodules = git_output(repository, ("submodule", "status", "--recursive"))
    board = [line for line in submodules.splitlines() if "board_package/NU54DK_Zephyr_DTS" in line]
    if len(board) != 1 or not board[0].startswith(" "):
        raise ReleaseFailure("고정 NU54DK 보드 submodule 상태를 확인하지 못했습니다.")
    return commit


## @brief 현재 프로세스에만 v0.4.1 stable 계약을 추가합니다.
def configure_package(package: Any, commit: str) -> None:
    if VERSION in package.STABLE_VERSIONS or VERSION in package.PACKAGE_VERSIONS:
        raise ReleaseFailure("v0.4.1은 공개 전 permanent allowlist에 없어야 합니다.")
    try:
        package.configure_unpublished_stable(VERSION, commit)
    except package.PackageError as error:
        raise ReleaseFailure(str(error)) from error
    if (
        package.release_channel(VERSION) != "stable"
        or package.release_tag(VERSION) != TAG
        or package.STABLE_RELEASE_COMMITS.get(VERSION) != commit
    ):
        raise ReleaseFailure("process-local v0.4.1 package 계약이 변했습니다.")


## @brief exact commit의 사용자 문서를 공개 asset 이름으로 복사합니다.
def copy_documents(repository: Path, output: Path, commit: str) -> dict[str, Path]:
    documents: dict[str, Path] = {}
    for role, relative in DOCUMENT_PATHS.items():
        result = subprocess.run(
            ("git", "show", f"{commit}:{relative}"),
            cwd=repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise ReleaseFailure(f"고정 release 문서가 없습니다: {relative}")
        destination = output / DOCUMENT_ASSET_NAMES[role]
        destination.write_bytes(result.stdout)
        documents[role] = destination
    return documents


## @brief 출력 directory 내부 regular file의 identity를 만듭니다.
def artifact_record(output: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(output.resolve()) or not resolved.is_file() or resolved.is_symlink():
        raise ReleaseFailure(f"자산이 출력 directory를 벗어났습니다: {path}")
    return {
        "path": resolved.relative_to(output.resolve()).as_posix(),
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


## @brief package 두 세트의 이름·크기·byte가 같은지 검증합니다.
def compare_builds(first: dict[str, Path], second: dict[str, Path]) -> None:
    if set(first) != set(PACKAGE_ROLES) or set(second) != set(PACKAGE_ROLES):
        raise ReleaseFailure("package 자산 역할 집합이 잘못됐습니다.")
    for role in PACKAGE_ROLES:
        if (
            first[role].name != second[role].name
            or first[role].stat().st_size != second[role].stat().st_size
            or first[role].read_bytes() != second[role].read_bytes()
        ):
            raise ReleaseFailure(f"package 재현성이 다릅니다: {role}")


## @brief v0.4.1 자산과 단일 버전 stable index를 준비합니다.
def prepare(repository: Path, output: Path, revision: str) -> Path:
    repository = repository.resolve()
    output = output.resolve()
    commit = assert_exact_source(repository, revision)
    if output.exists() and any(output.iterdir()):
        raise ReleaseFailure(f"출력 directory가 비어 있지 않습니다: {output}")
    output.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output / "artifacts"
    package = load_module("nu54_v041_prepare_package", PACKAGE_MODULE)
    configure_package(package, commit)
    try:
        with tempfile.TemporaryDirectory(prefix="nu54-v041-repro-") as temporary:
            first = package.build_package(repository, artifacts_dir, VERSION, commit)
            second = package.build_package(repository, Path(temporary), VERSION, commit)
            compare_builds(first, second)
        manifest = package.validate_archive(
            first["archive"], expected_version=VERSION, expected_commit=commit
        )
        index = package.generate_index(artifacts_dir, [VERSION], destination=output / package.STABLE_INDEX_FILENAME)
        package.validate_index(index)
    except package.PackageError as error:
        raise ReleaseFailure(str(error)) from error
    index_document = strict_json(index)
    versions = [item["version"] for item in index_document["packages"][0]["platforms"]]
    if versions != [VERSION]:
        raise ReleaseFailure("stable index는 v0.4.1 하나만 제공해야 합니다.")
    documents = copy_documents(repository, output, commit)
    paths = {**first, **documents, "index": index}
    plan = {
        "schema_version": 1,
        "kind": "v0.4.1-maintenance-release-plan",
        "version": VERSION,
        "release_tag": TAG,
        "target_commit": commit,
        "board_revision": manifest["board_revision"],
        "runtime_payload_sha256": manifest["runtime_payload_sha256"],
        "supported_catalog_versions": [VERSION],
        "release_upload_roles": list(PACKAGE_ROLES + tuple(DOCUMENT_PATHS)),
        "artifacts": {role: artifact_record(output, paths[role]) for role in PLAN_ROLES},
    }
    plan_path = output / PLAN_FILENAME
    plan_path.write_bytes(canonical_json(plan))
    validate_plan(plan_path)
    return plan_path


## @brief plan과 모든 로컬 자산 identity를 재검증합니다.
def validate_plan(plan_path: Path) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    plan = strict_json(plan_path)
    fixed = {
        "schema_version": 1,
        "kind": "v0.4.1-maintenance-release-plan",
        "version": VERSION,
        "release_tag": TAG,
        "supported_catalog_versions": [VERSION],
        "release_upload_roles": list(PACKAGE_ROLES + tuple(DOCUMENT_PATHS)),
    }
    if not isinstance(plan, dict) or any(plan.get(key) != value for key, value in fixed.items()):
        raise ReleaseFailure("v0.4.1 plan 계약이 잘못됐습니다.")
    commit = plan.get("target_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseFailure("plan source commit이 잘못됐습니다.")
    records = plan.get("artifacts")
    if not isinstance(records, dict) or set(records) != set(PLAN_ROLES):
        raise ReleaseFailure("plan 자산 역할 집합이 잘못됐습니다.")
    for role, record in records.items():
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise ReleaseFailure(f"자산 record가 잘못됐습니다: {role}")
        path = (plan_path.parent / str(record["path"])).resolve()
        if not path.is_relative_to(plan_path.parent) or not path.is_file() or path.is_symlink():
            raise ReleaseFailure(f"자산이 없거나 경로를 벗어났습니다: {role}")
        if path.stat().st_size != record["size"] or sha256_file(path) != record["sha256"]:
            raise ReleaseFailure(f"자산 identity가 달라졌습니다: {role}")
    return plan


## @brief public GitHub Release 자산을 다시 받아 plan byte와 대조합니다.
def verify_public(plan_path: Path) -> None:
    plan = validate_plan(plan_path)
    roles = tuple(plan["release_upload_roles"])
    with tempfile.TemporaryDirectory(prefix="nu54-v041-public-") as temporary:
        destination = Path(temporary)
        result = subprocess.run(
            (
                "gh", "release", "download", TAG, "--repo", GITHUB_REPOSITORY,
                "--dir", str(destination),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise ReleaseFailure(result.stderr.decode("utf-8", "replace").strip())
        expected = {
            Path(plan["artifacts"][role]["path"]).name: plan["artifacts"][role]
            for role in roles
        }
        actual = {path.name: path for path in destination.iterdir() if path.is_file()}
        if set(actual) != set(expected):
            raise ReleaseFailure("public Release 자산 집합이 plan과 다릅니다.")
        for name, path in actual.items():
            record = expected[name]
            source = plan_path.parent / record["path"]
            if path.stat().st_size != record["size"] or sha256_file(path) != record["sha256"]:
                raise ReleaseFailure(f"public 자산 identity가 다릅니다: {name}")
            if path.read_bytes() != source.read_bytes():
                raise ReleaseFailure(f"public 자산 byte가 다릅니다: {name}")


## @brief 준비·검증·공개 검증 명령을 분리합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v0.4.1 유지보수 릴리스 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("contract")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--repository", type=Path, default=REPOSITORY)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--commit", required=True)
    validate_parser = subparsers.add_parser("validate-plan")
    validate_parser.add_argument("--plan", type=Path, required=True)
    public_parser = subparsers.add_parser("verify-public")
    public_parser.add_argument("--plan", type=Path, required=True)
    return parser


## @brief 명령별 성공 표식을 출력합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "contract":
        if set(build_parser()._subparsers._group_actions[0].choices) != {
            "contract", "prepare", "validate-plan", "verify-public"
        }:
            raise ReleaseFailure("명령 분리 계약이 변했습니다.")
        print("V041_RELEASE_CONTRACT_PASS=1;SUPPORTED_CATALOG=0.4.1")
    elif parsed.command == "prepare":
        plan = prepare(parsed.repository, parsed.output_dir, parsed.commit)
        print(f"V041_RELEASE_PREPARE_PASS=1;PLAN={plan}")
    elif parsed.command == "validate-plan":
        plan = validate_plan(parsed.plan)
        print(f"V041_RELEASE_PLAN_PASS=1;COMMIT={plan['target_commit']}")
    elif parsed.command == "verify-public":
        verify_public(parsed.plan)
        print("V041_RELEASE_PUBLIC_ASSETS_PASS=1")
    else:
        raise ReleaseFailure(f"지원하지 않는 명령입니다: {parsed.command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseFailure as error:
        print(f"V041_RELEASE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
