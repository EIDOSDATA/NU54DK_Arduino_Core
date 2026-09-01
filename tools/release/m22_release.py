#!/usr/bin/env python3
"""! @brief NU54DK v0.3.0-rc.2 산출물과 검증 수명주기를 fail-closed로 관리합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


SCHEMA_VERSION = 1
MILESTONE = "M22"
VERSION = "0.3.0-rc.2"
TAG = f"v{VERSION}"
REPOSITORY_URL = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core"
BOARD_PATH = "board_package/NU54DK_Zephyr_DTS"
STABLE_INDEX_PATH = "package_nucode_nu54dk_index.json"
PLAN_FILENAME = "m22-rc2-plan.json"
FINAL_FILENAME = "m22-rc2-final-evidence.json"
EXPECTED_RC_VERSIONS = (
    "0.1.0-rc.2", "0.2.0-rc.1", "0.2.0-rc.2", "0.3.0-rc.1", VERSION,
)
EXPECTED_STABLE_VERSIONS = ("0.1.0", "0.2.0")
EXPECTED_STABLE_INDEX_SIZE = 1877
EXPECTED_STABLE_INDEX_SHA256 = (
    "5ae7fbe13f71c52950879064685694cf4b062557572f187e81476639724e5344"
)
EXPECTED_PINS = {
    "NCS_VERSION": "v3.4.0",
    "NCS_REVISION": "99553055607b2e9885fbc80ccd11fa9da81c2df0",
    "ZEPHYR_VERSION": "4.4.0",
    "ZEPHYR_REVISION": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
    "TOOLCHAIN_BUNDLE_ID": "dcbdc366a1",
}
RUNNER_PATHS = (
    "tools/release/m22_release.py",
    "tools/release/run_m22_fixed_gate.py",
    "tools/release/run_m22_package_examples.py",
    "tools/release/m22_cleanroom.py",
    "tools/release/m22-package-examples.lock.json",
    "tests/hil/nu54dk/m8_upload.py",
)
CLEANROOM_RUNNER_PATH = "tools/release/m22_cleanroom.py"
PACKAGE_ROLES = ("archive", "checksums", "licenses", "manifest", "notices", "sbom", "index")
EXPECTED_ARTIFACT_NAMES = {
    "archive": f"nucode-nu54dk-zephyr-{VERSION}.zip",
    "checksums": f"nucode-nu54dk-zephyr-{VERSION}.CHECKSUMS.sha256",
    "licenses": f"nucode-nu54dk-zephyr-{VERSION}.license-inventory.json",
    "manifest": f"nucode-nu54dk-zephyr-{VERSION}.release-manifest.json",
    "notices": f"nucode-nu54dk-zephyr-{VERSION}.THIRD_PARTY_NOTICES.md",
    "sbom": f"nucode-nu54dk-zephyr-{VERSION}.spdx.json",
    "index": "package_nucode_nu54dk_rc_index.json",
}
REQUIRED_GATES = ("host", "package-examples", "rc-upload", "cleanroom")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_JSON_BYTES = 32 * 1024 * 1024


class M22ReleaseFailure(RuntimeError):
    """! @brief M22 RC2 identity 또는 gate를 보장할 수 없는 오류입니다. """


## @brief 같은 저장소의 Boards Manager package 모듈을 읽습니다.
def load_package_module() -> Any:
    path = Path(__file__).resolve().parents[2] / "packaging" / "boards-manager" / "nu54_package.py"
    specification = importlib.util.spec_from_file_location("nu54_m22_package", path)
    if specification is None or specification.loader is None:
        raise M22ReleaseFailure(f"package 모듈을 읽을 수 없습니다: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


PACKAGE = load_package_module()


## @brief 파일의 SHA-256을 bounded streaming 방식으로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


## @brief 중복 key와 과대 JSON을 거부해 object를 읽습니다.
def strict_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_JSON_BYTES:
        raise M22ReleaseFailure(f"JSON이 없거나 안전한 크기가 아닙니다: {path}")

    ## @brief object 내부의 중복 key를 거부합니다.
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise M22ReleaseFailure(f"JSON key가 중복되었습니다: {key}")
            value[key] = item
        return value

    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M22ReleaseFailure(f"JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise M22ReleaseFailure(f"JSON 최상위 값이 object가 아닙니다: {path}")
    return document


## @brief JSON을 결정적인 UTF-8 LF 형식으로 원자 기록합니다.
def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


## @brief package 모듈의 0.3.0 RC allowlist와 SDK pin을 강제합니다.
def assert_package_contract(package: Any = PACKAGE) -> None:
    if tuple(package.RELEASE_CANDIDATE_VERSIONS) != EXPECTED_RC_VERSIONS:
        raise M22ReleaseFailure("release candidate allowlist가 M22 고정 계약과 다릅니다.")
    if tuple(package.STABLE_VERSIONS) != EXPECTED_STABLE_VERSIONS:
        raise M22ReleaseFailure("공개 stable allowlist 변경을 M22 RC 도구에서 허용하지 않습니다.")
    for name, expected in EXPECTED_PINS.items():
        if getattr(package, name, None) != expected:
            raise M22ReleaseFailure(f"package pin {name}이 M22 고정 계약과 다릅니다.")
    if (
        package.release_channel(VERSION) != "release-candidate"
        or package.release_tag(VERSION) != TAG
        or package.RC_INDEX_FILENAME != "package_nucode_nu54dk_rc_index.json"
    ):
        raise M22ReleaseFailure("0.3.0-rc.2 channel/tag/index 계약이 잘못되었습니다.")


## @brief 외부 명령을 shell 없이 실행하고 stdout byte를 반환합니다.
def run_external(argv: Sequence[str], cwd: Path) -> bytes:
    try:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise M22ReleaseFailure(f"명령 실행이 실패했습니다: {argv[0]}") from error
    return result.stdout


Runner = Callable[[Sequence[str], Path], bytes]


## @brief exact clean Core commit과 board gitlink/checkout을 검증합니다.
def assert_clean_source(repo_root: Path, commit: str, runner: Runner = run_external) -> str:
    if not COMMIT_RE.fullmatch(commit):
        raise M22ReleaseFailure("commit은 lowercase 40자리 exact SHA여야 합니다.")
    resolved = runner(
        ("git", "rev-parse", "--verify", f"{commit}^{{commit}}"), repo_root
    ).decode().strip()
    if resolved != commit:
        raise M22ReleaseFailure("M22 exact commit object를 확인하지 못했습니다.")
    actual = runner(("git", "rev-parse", "--verify", "HEAD^{commit}"), repo_root).decode().strip()
    if actual != commit:
        raise M22ReleaseFailure("현재 HEAD가 M22 exact commit과 다릅니다.")
    if runner(("git", "status", "--porcelain=v1", "--untracked-files=all"), repo_root).strip():
        raise M22ReleaseFailure("Core worktree가 깨끗하지 않습니다.")
    tree = runner(("git", "ls-tree", commit, "--", BOARD_PATH), repo_root).decode().strip()
    match = re.fullmatch(rf"160000 commit ([0-9a-f]{{40}})\t{re.escape(BOARD_PATH)}", tree)
    if not match:
        raise M22ReleaseFailure("exact commit에 board gitlink가 없습니다.")
    board_revision = match.group(1)
    board_root = repo_root / BOARD_PATH
    actual_board = runner(("git", "rev-parse", "--verify", "HEAD^{commit}"), board_root).decode().strip()
    if actual_board != board_revision:
        raise M22ReleaseFailure("board checkout이 exact gitlink와 다릅니다.")
    if runner(("git", "status", "--porcelain=v1", "--untracked-files=all"), board_root).strip():
        raise M22ReleaseFailure("board submodule worktree가 깨끗하지 않습니다.")
    return board_revision


## @brief 기존 stable Boards Manager index가 exact commit과 worktree에서 불변인지 확인합니다.
def assert_stable_index_unchanged(
    repo_root: Path, commit: str, runner: Runner = run_external
) -> None:
    path = repo_root / STABLE_INDEX_PATH
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != EXPECTED_STABLE_INDEX_SIZE
        or file_sha256(path) != EXPECTED_STABLE_INDEX_SHA256
    ):
        raise M22ReleaseFailure("stable index worktree byte 계약이 변경되었습니다.")
    committed = runner(("git", "show", f"{commit}:{STABLE_INDEX_PATH}"), repo_root)
    if (
        len(committed) != EXPECTED_STABLE_INDEX_SIZE
        or hashlib.sha256(committed).hexdigest() != EXPECTED_STABLE_INDEX_SHA256
        or committed != path.read_bytes()
    ):
        raise M22ReleaseFailure("stable index exact commit byte 계약이 변경되었습니다.")


## @brief 출력이 저장소 밖 또는 gitignored build 아래의 비어 있는 경로인지 확인합니다.
def assert_safe_output(repo_root: Path, output_dir: Path) -> None:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    try:
        relative = output_dir.relative_to(repo_root)
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != "build":
        raise M22ReleaseFailure("저장소 내부 RC 출력은 build/ 아래만 허용합니다.")


## @brief package와 exact RC index 한 세트를 생성·검증합니다.
def build_once(package: Any, repo_root: Path, output: Path, commit: str) -> dict[str, Path]:
    try:
        artifacts = package.build_package(repo_root, output, VERSION, commit)
        index = package.generate_index(
            output, [VERSION], destination=output / package.RC_INDEX_FILENAME
        )
        package.validate_archive(artifacts["archive"], expected_version=VERSION, expected_commit=commit)
        package.validate_index(index, artifact_dir=output)
    except package.PackageError as error:
        raise M22ReleaseFailure(f"package 생성·검증이 실패했습니다: {error}") from error
    combined = {**artifacts, "index": index}
    if tuple(sorted(combined)) != tuple(sorted(PACKAGE_ROLES)):
        raise M22ReleaseFailure("package artifact role allowlist가 다릅니다.")
    if {role: path.name for role, path in combined.items()} != EXPECTED_ARTIFACT_NAMES:
        raise M22ReleaseFailure("package artifact filename allowlist가 다릅니다.")
    return combined


## @brief 두 독립 build의 filename, size, hash, byte를 모두 대조합니다.
def compare_builds(first: dict[str, Path], second: dict[str, Path]) -> dict[str, dict[str, Any]]:
    if set(first) != set(PACKAGE_ROLES) or set(second) != set(PACKAGE_ROLES):
        raise M22ReleaseFailure("독립 build artifact role이 다릅니다.")
    records: dict[str, dict[str, Any]] = {}
    for role in PACKAGE_ROLES:
        left, right = first[role], second[role]
        if left.name != right.name or left.stat().st_size != right.stat().st_size:
            raise M22ReleaseFailure(f"독립 build filename/size가 다릅니다: {role}")
        digest = file_sha256(left)
        if digest != file_sha256(right) or left.read_bytes() != right.read_bytes():
            raise M22ReleaseFailure(f"독립 build byte가 재현되지 않습니다: {role}")
        records[role] = {"file_name": left.name, "size": left.stat().st_size, "sha256": digest}
    return records


## @brief exact clean commit에서 RC2 package를 두 번 만들어 plan을 기록합니다.
def prepare_release(
    repo_root: Path,
    output_dir: Path,
    commit: str,
    *,
    package: Any = PACKAGE,
    runner: Runner = run_external,
) -> Path:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    if repo_root != Path(__file__).resolve().parents[2]:
        raise M22ReleaseFailure("M22 release 도구와 source는 같은 저장소여야 합니다.")
    assert_safe_output(repo_root, output_dir)
    assert_package_contract(package)
    board_revision = assert_clean_source(repo_root, commit, runner)
    assert_stable_index_unchanged(repo_root, commit, runner)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise M22ReleaseFailure("M22 output은 새 경로 또는 빈 directory여야 합니다.")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".m22-a-", dir=output_dir) as left_temp, tempfile.TemporaryDirectory(
        prefix=".m22-b-", dir=output_dir
    ) as right_temp:
        first = build_once(package, repo_root, Path(left_temp), commit)
        second = build_once(package, repo_root, Path(right_temp), commit)
        records = compare_builds(first, second)
        for path in first.values():
            shutil.copy2(path, output_dir / path.name)
    runner_records: dict[str, dict[str, Any]] = {}
    for relative in RUNNER_PATHS:
        path = repo_root / relative
        if not path.is_file() or path.is_symlink():
            raise M22ReleaseFailure(f"M22 고정 runner가 없습니다: {relative}")
        runner_records[relative] = {"sha256": file_sha256(path), "size": path.stat().st_size}
    plan = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "kind": "rc2-local-validation-plan",
        "version": VERSION,
        "release_tag": TAG,
        "repository": REPOSITORY_URL,
        "target_commit": commit,
        "board_revision": board_revision,
        "created_at_utc": package.commit_timestamp(repo_root, commit),
        "reproducibility": {"independent_builds": 2, "byte_identical": True},
        "artifacts": records,
        "runners": runner_records,
        "required_gates": list(REQUIRED_GATES),
        "publication": {
            "github_release_created_by_this_tool": False,
            "github_release_supported_by_this_tool": False,
            "push_performed_by_this_tool": False,
            "public_prerelease_required_before_cleanroom": True,
            "ordered_flow": [
                "prepare",
                "fixed-gates",
                "external-public-prerelease",
                "public-url-cleanroom",
                "finalize",
            ],
            "next_action": "고정 gate 완료 뒤 외부 절차로 공개 prerelease를 만든 다음 public URL clean-room과 finalize 실행",
        },
        "state": "artifacts-prepared-awaiting-gates",
    }
    plan_path = output_dir / PLAN_FILENAME
    write_json(plan_path, plan)
    assert_clean_source(repo_root, commit, runner)
    validate_plan(plan_path, package=package, runner=runner)
    return plan_path


## @brief plan, artifact bytes, runner bytes와 source identity를 다시 검증합니다.
def validate_plan(
    plan_path: Path,
    *,
    package: Any = PACKAGE,
    runner: Runner = run_external,
) -> dict[str, Any]:
    assert_package_contract(package)
    plan_path = plan_path.resolve()
    plan = strict_json(plan_path)
    expected_output_names = {PLAN_FILENAME, *EXPECTED_ARTIFACT_NAMES.values()}
    try:
        output_entries = list(plan_path.parent.iterdir())
    except OSError as error:
        raise M22ReleaseFailure("plan output directory를 열거하지 못했습니다.") from error
    if {path.name for path in output_entries} != expected_output_names or any(
        not path.is_file() or path.is_symlink() for path in output_entries
    ):
        raise M22ReleaseFailure("plan output에 artifact/plan allowlist 밖 항목이 있습니다.")
    if set(plan) != {
        "schema_version", "milestone", "kind", "version", "release_tag",
        "repository", "target_commit", "board_revision", "created_at_utc",
        "reproducibility", "artifacts", "runners", "required_gates",
        "publication", "state",
    }:
        raise M22ReleaseFailure("plan 최상위 field 계약이 다릅니다.")
    fixed = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "kind": "rc2-local-validation-plan",
        "version": VERSION,
        "release_tag": TAG,
        "repository": REPOSITORY_URL,
        "required_gates": list(REQUIRED_GATES),
        "state": "artifacts-prepared-awaiting-gates",
    }
    for key, expected in fixed.items():
        if plan.get(key) != expected:
            raise M22ReleaseFailure(f"plan {key}가 고정 계약과 다릅니다.")
    commit = plan.get("target_commit")
    if not isinstance(commit, str):
        raise M22ReleaseFailure("plan target commit이 없습니다.")
    board = assert_clean_source(Path(__file__).resolve().parents[2], commit, runner)
    assert_stable_index_unchanged(Path(__file__).resolve().parents[2], commit, runner)
    if plan.get("board_revision") != board:
        raise M22ReleaseFailure("plan board revision이 source와 다릅니다.")
    if plan.get("created_at_utc") != package.commit_timestamp(
        Path(__file__).resolve().parents[2], commit
    ):
        raise M22ReleaseFailure("plan 생성 시간이 exact commit과 다릅니다.")
    if plan.get("reproducibility") != {"independent_builds": 2, "byte_identical": True}:
        raise M22ReleaseFailure("plan 재현 build 계약이 다릅니다.")
    artifacts = plan.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(PACKAGE_ROLES):
        raise M22ReleaseFailure("plan artifact role이 다릅니다.")
    for role, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != {"file_name", "size", "sha256"}:
            raise M22ReleaseFailure(f"artifact record schema가 다릅니다: {role}")
        path = plan_path.parent / str(record["file_name"])
        if Path(str(record["file_name"])).name != str(record["file_name"]):
            raise M22ReleaseFailure(f"artifact filename이 안전한 basename이 아닙니다: {role}")
        if record["file_name"] != EXPECTED_ARTIFACT_NAMES[role]:
            raise M22ReleaseFailure(f"artifact filename allowlist가 다릅니다: {role}")
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != record["size"]
            or not isinstance(record["sha256"], str)
            or not SHA256_RE.fullmatch(record["sha256"])
            or file_sha256(path) != record["sha256"]
        ):
            raise M22ReleaseFailure(f"artifact byte identity가 다릅니다: {role}")
    package.validate_archive(
        plan_path.parent / artifacts["archive"]["file_name"],
        expected_version=VERSION,
        expected_commit=commit,
    )
    package.validate_index(
        plan_path.parent / artifacts["index"]["file_name"], artifact_dir=plan_path.parent
    )
    runners = plan.get("runners")
    if not isinstance(runners, dict) or set(runners) != set(RUNNER_PATHS):
        raise M22ReleaseFailure("plan runner allowlist가 다릅니다.")
    for relative, record in runners.items():
        path = Path(__file__).resolve().parents[2] / relative
        if record != {"sha256": file_sha256(path), "size": path.stat().st_size}:
            raise M22ReleaseFailure(f"고정 runner byte가 plan 이후 변경되었습니다: {relative}")
    publication = plan.get("publication")
    if (
        not isinstance(publication, dict)
        or set(publication) != {
            "github_release_created_by_this_tool", "github_release_supported_by_this_tool",
            "push_performed_by_this_tool", "public_prerelease_required_before_cleanroom",
            "ordered_flow", "next_action",
        }
        or publication.get("github_release_created_by_this_tool") is not False
        or publication.get("github_release_supported_by_this_tool") is not False
        or publication.get("push_performed_by_this_tool") is not False
        or publication.get("public_prerelease_required_before_cleanroom") is not True
        or publication.get("ordered_flow") != [
            "prepare", "fixed-gates", "external-public-prerelease",
            "public-url-cleanroom", "finalize",
        ]
        or not isinstance(publication.get("next_action"), str)
        or not publication["next_action"].strip()
    ):
        raise M22ReleaseFailure("M22 도구는 GitHub publication을 지원하면 안 됩니다.")
    return plan


## @brief plan에 묶인 fixed-gate 명령을 shell 없이 실행합니다.
def invoke_fixed_gate(plan_path: Path, gate_args: Sequence[str]) -> None:
    plan = validate_plan(plan_path)
    if any(
        value in {"--release-plan-sha256", "--release-core-revision"}
        for value in gate_args
    ):
        raise M22ReleaseFailure("release binding 인자는 plan에서만 주입합니다.")
    command = [
        str(Path(sys.executable).resolve()),
        str(Path(__file__).with_name("run_m22_fixed_gate.py")),
        *gate_args,
        "--release-plan-sha256",
        file_sha256(plan_path.resolve()),
        "--release-core-revision",
        plan["target_commit"],
    ]
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[2], check=False)
    if result.returncode != 0:
        raise M22ReleaseFailure("M22 fixed gate가 실패했습니다.")


## @brief 공개 URL clean-room에 plan의 exact index/archive identity를 전달합니다.
def invoke_cleanroom(args: argparse.Namespace, plan_path: Path, plan: dict[str, Any]) -> None:
    artifacts = plan["artifacts"]
    release_manifest = strict_json(
        plan_path.resolve().parent / artifacts["manifest"]["file_name"]
    )
    runtime_payload = release_manifest.get("runtime_payload_sha256")
    if not isinstance(runtime_payload, str) or not SHA256_RE.fullmatch(runtime_payload):
        raise M22ReleaseFailure("release manifest runtime payload identity가 없습니다.")
    command = [
        str(Path(sys.executable).resolve()),
        str(Path(__file__).with_name("m22_cleanroom.py")),
        "--arduino-cli",
        str(args.arduino_cli),
        "--index-sha256",
        artifacts["index"]["sha256"],
        "--archive-sha256",
        artifacts["archive"]["sha256"],
        "--archive-size",
        str(artifacts["archive"]["size"]),
        "--core-revision",
        plan["target_commit"],
        "--board-revision",
        plan["board_revision"],
        "--runtime-payload-sha256",
        runtime_payload,
        "--release-manifest-sha256",
        artifacts["manifest"]["sha256"],
        "--runner-revision",
        plan["target_commit"],
        "--runner-sha256",
        plan["runners"][CLEANROOM_RUNNER_PATH]["sha256"],
        "--plan-sha256",
        file_sha256(plan_path.resolve()),
        "--probe-id",
        args.probe_id,
        "--parent",
        str(args.parent),
        "--evidence",
        str(args.evidence),
        "--log",
        str(args.log),
    ]
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[2], check=False)
    if result.returncode != 0:
        raise M22ReleaseFailure("M22 same-PC clean-room이 실패했습니다.")


## @brief 네 필수 evidence를 exact plan에 결합하고 RC2 준비 상태를 결정합니다.
def finalize_evidence(
    plan_path: Path, evidence_paths: Sequence[Path], output: Path
) -> dict[str, Any]:
    plan = validate_plan(plan_path)
    gates: dict[str, dict[str, Any]] = {}
    for path in evidence_paths:
        evidence = strict_json(path.resolve())
        if (
            evidence.get("schema_version") != 1
            or evidence.get("milestone") != MILESTONE
            or evidence.get("release_version") != VERSION
            or evidence.get("status") != "passed"
        ):
            raise M22ReleaseFailure(f"M22 evidence가 PASS identity가 아닙니다: {path}")
        if evidence.get("evidence_type") == "fixed-gate":
            gate = evidence.get("gate_id")
            if gate not in {"host", "package-examples", "rc-upload"}:
                raise M22ReleaseFailure("fixed gate ID가 allowlist 밖입니다.")
            if evidence.get("command_contract", {}).get("probe_id_recorded") is not False:
                raise M22ReleaseFailure("fixed gate probe UID redaction evidence가 없습니다.")
            if evidence.get("release_binding") != {
                "plan_sha256": file_sha256(plan_path.resolve()),
                "core_revision": plan["target_commit"],
            }:
                raise M22ReleaseFailure("fixed gate evidence가 exact release plan에 묶이지 않았습니다.")
            runner_record = evidence.get("runner")
            expected_runner = plan["runners"]["tools/release/run_m22_fixed_gate.py"]
            if (
                not isinstance(runner_record, dict)
                or runner_record.get("repository_relative_path")
                != "tools/release/run_m22_fixed_gate.py"
                or runner_record.get("sha256") != expected_runner["sha256"]
            ):
                raise M22ReleaseFailure("fixed gate runner byte가 release plan과 다릅니다.")
        elif evidence.get("evidence_type") == "same-pc-isolated-cleanroom":
            gate = "cleanroom"
            cleanup = evidence.get("cleanup", {})
            isolation = evidence.get("isolation", {})
            public_index = evidence.get("public_index", {})
            archive = evidence.get("archive", {})
            cleanroom_runner = evidence.get("runner", {})
            if (
                cleanup.get("status") != "passed"
                or cleanup.get("exact_run_leaf_removed") is not True
                or cleanup.get("external_evidence_preserved") is not True
                or cleanup.get("reparse_scan_passed") is not True
                or cleanup.get("marker_verified") is not True
                or isolation.get("existing_path_leakage") is not False
                or isolation.get("probe_id_recorded") is not False
                or public_index != {
                    "url": (
                        f"{REPOSITORY_URL}/releases/download/{TAG}/"
                        f"{EXPECTED_ARTIFACT_NAMES['index']}"
                    ),
                    "sha256": plan["artifacts"]["index"]["sha256"],
                }
                or archive != {
                    "sha256": plan["artifacts"]["archive"]["sha256"],
                    "size": plan["artifacts"]["archive"]["size"],
                }
                or cleanroom_runner != {
                    "repository_relative_path": CLEANROOM_RUNNER_PATH,
                    "revision": plan["target_commit"],
                    "sha256": plan["runners"][CLEANROOM_RUNNER_PATH]["sha256"],
                    "plan_sha256": file_sha256(plan_path.resolve()),
                }
                or evidence.get("installed_release", {}).get("core_revision") != plan["target_commit"]
                or evidence.get("installed_release", {}).get("board_revision") != plan["board_revision"]
            ):
                raise M22ReleaseFailure(
                    "clean-room public URL/cleanup/isolation evidence가 완성되지 않았습니다."
                )
        else:
            raise M22ReleaseFailure("M22 evidence type이 allowlist 밖입니다.")
        if gate in gates:
            raise M22ReleaseFailure(f"M22 gate evidence가 중복되었습니다: {gate}")
        gates[str(gate)] = {
            "file_name": path.name,
            "sha256": file_sha256(path),
            "size": path.stat().st_size,
        }
    if set(gates) != set(REQUIRED_GATES):
        raise M22ReleaseFailure(
            f"필수 M22 gate가 완성되지 않았습니다: {sorted(set(REQUIRED_GATES) - set(gates))}"
        )
    final = {
        "schema_version": 1,
        "milestone": MILESTONE,
        "evidence_type": "rc2-final",
        "status": "passed",
        "release_version": VERSION,
        "release_tag": TAG,
        "target_commit": plan["target_commit"],
        "board_revision": plan["board_revision"],
        "plan_sha256": file_sha256(plan_path),
        "gates": gates,
        "publication": {
            "performed_by_this_tool": False,
            "public_prerelease_required_before_cleanroom": True,
            "public_index_observed_by_cleanroom": True,
        },
        "state": "public-rc2-validated",
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(output.resolve(), final)
    return final


## @brief prepare/validate/gate/clean-room/finalize만 노출하는 parser입니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M22 v0.3.0-rc.2 local release lifecycle")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--commit", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--plan", type=Path, required=True)
    gate = commands.add_parser("run-gate")
    gate.add_argument("--plan", type=Path, required=True)
    gate.add_argument("gate_args", nargs=argparse.REMAINDER)
    cleanroom = commands.add_parser("run-cleanroom")
    cleanroom.add_argument("--plan", type=Path, required=True)
    cleanroom.add_argument("--arduino-cli", type=Path, required=True)
    cleanroom.add_argument("--probe-id", required=True)
    cleanroom.add_argument("--parent", type=Path, default=Path(r"C:\NU54CI\M22"))
    cleanroom.add_argument("--evidence", type=Path, required=True)
    cleanroom.add_argument("--log", type=Path, required=True)
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--plan", type=Path, required=True)
    finalize.add_argument("--evidence", type=Path, nargs="+", required=True)
    finalize.add_argument("--output", type=Path, required=True)
    return parser


## @brief M22 lifecycle 진입점입니다.
def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "prepare":
            path = prepare_release(args.repo_root, args.output_dir, args.commit)
            print(path)
        elif args.command == "validate":
            validate_plan(args.plan)
            print("M22_RC2_PLAN_VALID")
        elif args.command == "run-gate":
            if not args.gate_args or args.gate_args[0] not in {"host", "package-examples", "rc-upload"}:
                raise M22ReleaseFailure("run-gate는 고정 gate ID로 시작해야 합니다.")
            invoke_fixed_gate(args.plan, args.gate_args)
        elif args.command == "run-cleanroom":
            invoke_cleanroom(args, args.plan, validate_plan(args.plan))
        elif args.command == "finalize":
            finalize_evidence(args.plan, args.evidence, args.output)
            print("M22_RC2_VALIDATED_READY")
        return 0
    except (M22ReleaseFailure, PACKAGE.PackageError) as error:
        print(f"M22_RELEASE_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
