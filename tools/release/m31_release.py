#!/usr/bin/env python3
"""! @brief M31 v0.5.0 Windows 비공개 RC package를 재현 생성하고 검증합니다. """

from __future__ import annotations

import argparse
import datetime as dt
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
M31_READINESS = Path("variants/nu54dk/m31-ble-readiness.json")
RELEASE_READINESS = Path("variants/nu54dk/v0.5.0-release-readiness.json")
VERSION = "0.5.0-rc.1"
STABLE_VERSION = "0.5.0"
BASE_RC_VERSIONS = (
    "0.1.0-rc.2",
    "0.2.0-rc.1",
    "0.2.0-rc.2",
    "0.3.0-rc.1",
    "0.3.0-rc.2",
    "0.3.0-rc.3",
)
GATE_IDS = (
    "m31_functionality",
    "api_examples_support_matrix",
    "windows_package_reproducibility",
    "windows_clean_install_examples_upload",
    "windows_lifecycle",
    "rc_review_and_owner_approval",
    "public_assets_and_download_smoke",
)


class M31ReleaseFailure(RuntimeError):
    """! @brief W08 RC 준비 계약 위반을 나타냅니다. """


## @brief 중복 key를 거부하며 UTF-8 JSON을 읽습니다.
def strict_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M31ReleaseFailure(f"중복 JSON key입니다: {path}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M31ReleaseFailure(f"유효한 UTF-8 JSON이 아닙니다: {path}: {error}") from error


## @brief 증거와 plan에 사용하는 정규 JSON byte를 만듭니다.
def canonical_json(document: Any) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


## @brief 파일의 SHA-256을 계산합니다.
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief Git 명령 결과를 문자열로 반환합니다.
def git_output(repository: Path, *arguments: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
        encoding=None if binary else "utf-8",
        errors=None if binary else "replace",
        check=False,
    )
    if result.returncode != 0:
        detail = (
            result.stderr.decode("utf-8", "replace")
            if isinstance(result.stderr, bytes)
            else result.stderr
        )
        raise M31ReleaseFailure(f"Git 조회가 실패했습니다: {detail.strip()}")
    if binary:
        assert isinstance(result.stdout, bytes)
        return result.stdout
    assert isinstance(result.stdout, str)
    return result.stdout.strip()


## @brief 요청 revision과 현재 checkout·submodule이 정확하고 깨끗한지 검사합니다.
def assert_exact_clean_commit(repository: Path, revision: str) -> str:
    commit = str(git_output(repository, "rev-parse", f"{revision}^{{commit}}"))
    if git_output(repository, "rev-parse", "HEAD") != commit:
        raise M31ReleaseFailure("RC package는 요청 commit과 같은 HEAD에서만 생성합니다")
    status = git_output(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    if status:
        raise M31ReleaseFailure("RC package는 깨끗한 source에서만 생성합니다")
    submodules = str(git_output(repository, "submodule", "status", "--recursive"))
    if any(
        line.startswith(("+", "-", "U"))
        or re.fullmatch(r" ?[0-9a-f]{40} [^\r\n]+", line) is None
        for line in submodules.splitlines()
        if line
    ):
        raise M31ReleaseFailure("RC package의 submodule 상태가 고정 revision과 다릅니다")
    return commit


## @brief 지정 commit의 tracked JSON byte를 읽습니다.
def git_json_bytes(repository: Path, commit: str, relative: Path) -> bytes:
    return bytes(
        git_output(repository, "show", f"{commit}:{relative.as_posix()}", binary=True)
    )


## @brief package 모듈을 현재 process에서 격리 이름으로 로드합니다.
def load_package_module() -> Any:
    specification = importlib.util.spec_from_file_location(
        "nu54_m31_release_package", PACKAGE_MODULE
    )
    if specification is None or specification.loader is None:
        raise M31ReleaseFailure(f"package 모듈을 읽을 수 없습니다: {PACKAGE_MODULE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


## @brief 공개 allowlist를 바꾸지 않고 이번 process에서만 RC version을 추가합니다.
def configure_candidate(package: Any) -> None:
    if tuple(package.RELEASE_CANDIDATE_VERSIONS) != BASE_RC_VERSIONS:
        raise M31ReleaseFailure("과거 RC allowlist가 변경됐습니다")
    if VERSION in package.PACKAGE_VERSIONS:
        raise M31ReleaseFailure("M31 RC가 영구 package allowlist에 들어갔습니다")
    package.configure_release_candidates(BASE_RC_VERSIONS + (VERSION,))


## @brief M31 7/8 이상과 v0.5.0 Windows release gate schema를 검사합니다.
def validate_contract(repository: Path = REPOSITORY) -> tuple[dict[str, Any], dict[str, Any]]:
    root = repository.resolve()
    m31 = strict_json(root / M31_READINESS)
    release = strict_json(root / RELEASE_READINESS)
    packages = m31.get("work_packages", [])
    if (
        m31.get("milestone") != "M31"
        or m31.get("counts", {}).get("work_total") != 8
        or len(packages) != 8
        or any(item.get("status") != "completed" for item in packages[:7])
        or packages[7].get("id") != "M31-W08"
        or packages[7].get("status") not in {"not_started", "in_progress", "completed"}
    ):
        raise M31ReleaseFailure("M31 W01~W07 완료 또는 W08 상태가 RC 준비 계약과 다릅니다")
    fixed = {
        "schema_version": 1,
        "release": "v0.5.0",
        "candidate_version": VERSION,
        "host_scope": "Windows 10/11 x64",
        "publication_allowed": False,
    }
    if any(release.get(key) != value for key, value in fixed.items()):
        raise M31ReleaseFailure("v0.5.0 release identity 또는 공개 차단 계약이 다릅니다")
    gates = release.get("gates")
    if not isinstance(gates, list) or tuple(item.get("id") for item in gates) != GATE_IDS:
        raise M31ReleaseFailure("v0.5.0 release gate 집합 또는 순서가 다릅니다")
    allowed_status = {"PENDING", "PASS", "HOLD", "NOT_RUN"}
    root_resolved = root.resolve()
    for gate in gates:
        if gate.get("kind") not in {"automated", "automated_and_physical", "human", "external"}:
            raise M31ReleaseFailure(f"release gate kind가 유효하지 않습니다: {gate.get('id')}")
        if gate.get("status") not in allowed_status:
            raise M31ReleaseFailure(f"release gate 상태가 유효하지 않습니다: {gate.get('id')}")
        evidence = gate.get("evidence")
        if not isinstance(evidence, list):
            raise M31ReleaseFailure(f"release gate evidence가 배열이 아닙니다: {gate.get('id')}")
        if gate["status"] == "PASS":
            if not evidence:
                raise M31ReleaseFailure(f"PASS release gate에 증거가 없습니다: {gate['id']}")
            for relative in evidence:
                if not isinstance(relative, str):
                    raise M31ReleaseFailure(f"release gate 증거 경로가 문자열이 아닙니다: {gate['id']}")
                path = (root / relative).resolve()
                if not path.is_relative_to(root_resolved) or not path.is_file():
                    raise M31ReleaseFailure(f"release gate 증거가 없습니다: {gate['id']}: {relative}")
        elif not isinstance(gate.get("reason"), str) or not gate["reason"]:
            raise M31ReleaseFailure(f"미완료 release gate에 사유가 없습니다: {gate['id']}")
    by_id = {item["id"]: item for item in gates}
    if by_id["rc_review_and_owner_approval"]["kind"] != "human":
        raise M31ReleaseFailure("v0.5.0 공개 승인 gate는 human이어야 합니다")
    if by_id["public_assets_and_download_smoke"]["kind"] != "external":
        raise M31ReleaseFailure("공개 자산 smoke gate는 external이어야 합니다")
    if all(item["status"] == "PASS" for item in gates):
        raise M31ReleaseFailure("미공개 v0.5.0 contract가 공개 완료로 승격됐습니다")
    return m31, release


## @brief 아직 PASS가 아닌 release gate ID를 반환합니다.
def blockers(release: dict[str, Any], *, package_passed: bool) -> list[str]:
    result = []
    for gate in release["gates"]:
        status = gate["status"]
        if gate["id"] == "windows_package_reproducibility" and package_passed:
            status = "PASS"
        if status != "PASS":
            result.append(gate["id"])
    return result


## @brief output 내부 artifact의 size와 hash를 기록합니다.
def artifact_record(base: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file():
        raise M31ReleaseFailure(f"artifact가 output 밖으로 벗어났습니다: {path}")
    return {
        "path": resolved.relative_to(base.resolve()).as_posix(),
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


## @brief 독립 package 생성 두 세트가 byte 단위로 같은지 확인합니다.
def compare_builds(first: dict[str, Path], second: dict[str, Path]) -> dict[str, str]:
    if set(first) != set(second):
        raise M31ReleaseFailure("독립 package artifact 역할 집합이 다릅니다")
    result: dict[str, str] = {}
    for role in sorted(first):
        left = first[role]
        right = second[role]
        if left.stat().st_size != right.stat().st_size or sha256_file(left) != sha256_file(right):
            raise M31ReleaseFailure(f"독립 package byte가 다릅니다: {role}")
        result[role] = sha256_file(left)
    return result


## @brief exact clean commit에서 RC package를 두 번 만들고 HOLD plan을 생성합니다.
def prepare(repository: Path, output: Path, revision: str) -> Path:
    repository = repository.resolve()
    output = output.resolve()
    commit = assert_exact_clean_commit(repository, revision)
    _m31, release = validate_contract(repository)
    if output.exists() and any(output.iterdir()):
        raise M31ReleaseFailure(f"output directory가 비어 있지 않습니다: {output}")
    output.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output / "artifacts"
    package = load_package_module()
    configure_candidate(package)
    try:
        with tempfile.TemporaryDirectory(prefix="nu54-m31-rc-repro-") as temporary:
            first = package.build_package(repository, artifacts_dir, VERSION, commit)
            second = package.build_package(
                repository, Path(temporary) / "artifacts", VERSION, commit
            )
            reproducible_hashes = compare_builds(first, second)
        index = package.generate_index(artifacts_dir, [VERSION])
        manifest = package.validate_archive(
            first["archive"], expected_version=VERSION, expected_commit=commit
        )
        package.validate_index(index, artifact_dir=artifacts_dir)
    except package.PackageError as error:
        raise M31ReleaseFailure(str(error)) from error
    artifact_records = {
        role: artifact_record(output, path) for role, path in first.items()
    }
    artifact_records["index"] = artifact_record(output, index)
    plan = {
        "schema_version": 1,
        "milestone": "M31-W08",
        "version": VERSION,
        "stable_version": STABLE_VERSION,
        "host_scope": "Windows 10/11 x64",
        "status": "HOLD",
        "publication_allowed": False,
        "core_revision": commit,
        "board_revision": manifest["board_revision"],
        "runtime_payload_sha256": manifest["runtime_payload_sha256"],
        "m31_readiness_sha256": hashlib.sha256(
            git_json_bytes(repository, commit, M31_READINESS)
        ).hexdigest(),
        "release_readiness_sha256": hashlib.sha256(
            git_json_bytes(repository, commit, RELEASE_READINESS)
        ).hexdigest(),
        "package_reproducibility": {
            "status": "PASS",
            "isolated_builds": 2,
            "artifact_hashes": reproducible_hashes,
        },
        "blockers": blockers(release, package_passed=True),
        "artifacts": artifact_records,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if "rc_review_and_owner_approval" not in plan["blockers"]:
        raise M31ReleaseFailure("RC 준비 plan에서 별도 공개 승인이 사라졌습니다")
    plan_path = output / "m31-windows-rc-plan.json"
    temporary_plan = plan_path.with_suffix(".json.tmp")
    temporary_plan.write_bytes(canonical_json(plan))
    temporary_plan.replace(plan_path)
    validate_plan(plan_path, repository=repository)
    return plan_path


## @brief 생성한 RC plan과 모든 artifact byte를 source commit에 대해 재검증합니다.
def validate_plan(plan_path: Path, *, repository: Path = REPOSITORY) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    repository = repository.resolve()
    plan = strict_json(plan_path)
    if (
        not isinstance(plan, dict)
        or plan.get("schema_version") != 1
        or plan.get("milestone") != "M31-W08"
        or plan.get("version") != VERSION
        or plan.get("stable_version") != STABLE_VERSION
        or plan.get("host_scope") != "Windows 10/11 x64"
        or plan.get("status") != "HOLD"
        or plan.get("publication_allowed") is not False
    ):
        raise M31ReleaseFailure("M31 W08 RC plan identity 또는 공개 차단 상태가 잘못됐습니다")
    commit = str(git_output(repository, "rev-parse", f"{plan.get('core_revision')}^{{commit}}"))
    if commit != plan.get("core_revision"):
        raise M31ReleaseFailure("RC plan core revision이 full commit이 아닙니다")
    expected_m31 = hashlib.sha256(git_json_bytes(repository, commit, M31_READINESS)).hexdigest()
    expected_release = hashlib.sha256(
        git_json_bytes(repository, commit, RELEASE_READINESS)
    ).hexdigest()
    if (
        plan.get("m31_readiness_sha256") != expected_m31
        or plan.get("release_readiness_sha256") != expected_release
    ):
        raise M31ReleaseFailure("RC plan의 tracked readiness identity가 source commit과 다릅니다")
    if (
        not isinstance(plan.get("blockers"), list)
        or "rc_review_and_owner_approval" not in plan["blockers"]
        or not plan["blockers"]
    ):
        raise M31ReleaseFailure("RC plan은 공개 승인 blocker를 유지해야 합니다")
    expected_roles = {
        "archive", "checksums", "licenses", "manifest", "notices", "sbom", "index"
    }
    artifacts = plan.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_roles:
        raise M31ReleaseFailure("RC plan artifact 집합이 잘못됐습니다")
    resolved: dict[str, Path] = {}
    for role, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise M31ReleaseFailure(f"RC artifact record가 잘못됐습니다: {role}")
        path = (plan_path.parent / str(record["path"])).resolve()
        if not path.is_relative_to(plan_path.parent) or not path.is_file():
            raise M31ReleaseFailure(f"RC artifact가 없거나 output 밖입니다: {role}")
        if path.stat().st_size != record["size"] or sha256_file(path) != record["sha256"]:
            raise M31ReleaseFailure(f"RC artifact identity가 바뀌었습니다: {role}")
        resolved[role] = path
    package = load_package_module()
    configure_candidate(package)
    try:
        manifest = package.validate_archive(
            resolved["archive"], expected_version=VERSION, expected_commit=commit
        )
        package.validate_index(resolved["index"], artifact_dir=resolved["index"].parent)
    except package.PackageError as error:
        raise M31ReleaseFailure(str(error)) from error
    if (
        manifest["board_revision"] != plan.get("board_revision")
        or manifest["runtime_payload_sha256"] != plan.get("runtime_payload_sha256")
    ):
        raise M31ReleaseFailure("RC plan과 package provenance가 다릅니다")
    return plan


## @brief 공개 명령 없이 계약·prepare·plan 검증 명령만 제공합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M31 v0.5.0 Windows 비공개 RC 준비")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("contract")
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--repository", type=Path, default=REPOSITORY)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--commit", default="HEAD")
    validate_parser = commands.add_parser("validate-plan")
    validate_parser.add_argument("--plan", type=Path, required=True)
    validate_parser.add_argument("--repository", type=Path, default=REPOSITORY)
    return parser


## @brief 선택한 비공개 RC 준비 명령을 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "contract":
        _m31, release = validate_contract()
        remaining = blockers(release, package_passed=False)
        print(f"M31_RELEASE_CONTRACT_PASS=gates:{len(release['gates'])};blockers:{len(remaining)}")
    elif parsed.command == "prepare":
        plan = prepare(parsed.repository, parsed.output_dir, parsed.commit)
        print(f"M31_RELEASE_PREPARE_HOLD=1;PLAN={plan}")
    elif parsed.command == "validate-plan":
        plan = validate_plan(parsed.plan, repository=parsed.repository)
        print(f"M31_RELEASE_PLAN_HOLD=1;BLOCKERS={len(plan['blockers'])}")
    else:
        raise M31ReleaseFailure(f"지원하지 않는 명령입니다: {parsed.command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M31ReleaseFailure as error:
        print(f"M31_RELEASE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
