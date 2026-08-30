#!/usr/bin/env python3
"""! @brief NU54DK v0.1 release candidate를 준비하고 검증 증거를 결합합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


SCHEMA_VERSION = 1
MILESTONE = "M11"
REQUIRED_GATES = (
    "package_integrity",
    "host_regression",
    "arduino_cli_fixed_package",
    "zephyr_regression",
    "hil_rc_pyocd",
    "hil_pyocd",
    "clean_windows",
    "documentation",
)
OPTIONAL_GATES = ("hil_jlink",)
REQUIRED_DOCUMENT_ROLES = (
    "readme",
    "license",
    "installation",
    "api_matrix",
    "migration",
    "troubleshooting",
    "release_notes",
    "known_issues",
    "third_party_notices",
)
COMMAND_GATES = (
    "host_regression",
    "arduino_cli_fixed_package",
    "zephyr_regression",
    "hil_rc_pyocd",
)
MAX_COMMAND_LOG_BYTES = 32 * 1024 * 1024
LOG_EXCERPT_CHARS = 8192
LOG_TRUNCATION_MARKER = b"[NU54] log truncated to final 32 MiB\n"
PROCESS_TERMINATION_GRACE_SECONDS = 5
ARDUINO_CLI_VERSION = "1.5.2-rc.1"
ARDUINO_CLI_COMMIT = "fef6e48df"
ARDUINO_CLI_SHA256 = "ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538"
M10_SAFE_INITIAL_VERSION = "0.0.96"
M10_SAFE_LATEST_VERSION = "0.0.97"
M10_PREVIEW_INDEX_URL = (
    "https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/"
    "main/package_nucode_nu54dk_preview_index.json"
)
M10_FQBN = "nucode:zephyr:nu54dk"
M10_TARGET_RUNNER_PATH = "tools/remote-windows/m10/run-m10-target.ps1"
FIXED_GATE_RUNNER_PATH = "tools/release/run_fixed_gate.py"
RC_HIL_RUNNER_PATH = "tests/hil/nu54dk/m8_upload.py"
M11_PYOCD_UPLOAD_ATTEMPTS = 10
M11_RC_PYOCD_UPLOAD_ATTEMPTS = 1
M11_READY_TOKEN = "NUCODE_M8_UPLOAD_READY"
M10_FOLLOWUP_ALLOWED_PREFIXES = (".github/", "00_Docs/", "tests/", "tools/release/")
M10_FOLLOWUP_ALLOWED_FILES = (
    "README.md",
    "package_nucode_nu54dk_preview_index.json",
    "packaging/boards-manager/README.md",
)
## @brief M11 재현용으로 허용하는 역사적 v0.1 release candidate입니다.
M11_RELEASE_CANDIDATE_VERSIONS = ("0.1.0-rc.2",)


class ReleaseError(RuntimeError):
    """! @brief 안전하게 계속할 수 없는 M11 release 준비 오류입니다. """


## @brief 이 도구와 같은 저장소의 Boards Manager 패키징 모듈을 읽습니다.
def load_package_module() -> Any:
    module_path = Path(__file__).resolve().parents[2] / "packaging" / "boards-manager" / "nu54_package.py"
    specification = importlib.util.spec_from_file_location("nu54_m11_package", module_path)
    if specification is None or specification.loader is None:
        raise ReleaseError(f"패키징 모듈을 읽을 수 없습니다: {module_path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


PACKAGE = load_package_module()


## @brief JSON을 중복 key 없이 읽습니다.
def strict_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseError(f"UTF-8 JSON을 읽지 못했습니다: {path}: {error}") from error

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseError(f"중복 JSON key가 있습니다: {path}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as error:
        raise ReleaseError(f"유효한 JSON이 아닙니다: {path}: {error}") from error


## @brief JSON을 byte 단위로 재현 가능한 형식으로 직렬화합니다.
def canonical_json(document: Any) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


## @brief 파일 byte의 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ReleaseError(f"파일 checksum을 계산하지 못했습니다: {path}: {error}") from error
    return digest.hexdigest()


## @brief 같은 directory의 임시 파일을 이용해 byte를 원자적으로 기록합니다.
def atomic_write(path: Path, data: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


## @brief 외부 명령을 실행하고 stdout을 반환합니다.
def git_output(repo_root: Path, arguments: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
    except (OSError, subprocess.CalledProcessError, UnicodeError) as error:
        detail = getattr(error, "stderr", "") or ""
        raise ReleaseError(f"Git 상태 확인에 실패했습니다: {' '.join(arguments)}\n{detail.strip()}") from error
    return result.stdout


## @brief 지정 commit의 한 파일을 line-ending 변환 없이 읽습니다.
def git_file_at_revision(repo_root: Path, commit: str, relative: str) -> bytes:
    try:
        PACKAGE.ensure_safe_relative_path(relative)
        result = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError, PACKAGE.PackageError) as error:
        detail = getattr(error, "stderr", b"") or b""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise ReleaseError(f"고정 Git 파일을 읽지 못했습니다: {relative}: {str(detail).strip()}") from error
    return result.stdout


## @brief 현재 checkout이 지정 commit과 일치하고 submodule까지 깨끗한지 확인합니다.
def assert_source_state(repo_root: Path, commit: str) -> None:
    repo_root = repo_root.resolve()
    head = git_output(repo_root, ["rev-parse", "HEAD"]).strip()
    if head != commit:
        raise ReleaseError(f"검증 checkout HEAD가 RC commit과 다릅니다: {head} != {commit}")
    status = git_output(
        repo_root,
        ["status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"],
    )
    if status.strip():
        raise ReleaseError("RC 준비와 검증은 깨끗한 checkout에서만 허용합니다.\n" + status.rstrip())
    submodules = git_output(repo_root, ["submodule", "status", "--recursive"])
    board_lines = [
        line
        for line in submodules.splitlines()
        if len(line.strip().split()) >= 2
        and line.strip().split()[1] == "board_package/NU54DK_Zephyr_DTS"
    ]
    if len(board_lines) != 1 or not board_lines[0].startswith(" "):
        raise ReleaseError("고정된 NU54DK 보드 submodule 상태를 확인하지 못했습니다.")


## @brief 과거 M10 commit이 RC commit의 직계 history 조상인지 확인합니다.
def git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise ReleaseError("M10/RC Git ancestry를 확인하지 못했습니다.") from error
    if result.returncode not in {0, 1}:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ReleaseError(f"M10/RC Git ancestry 검사가 실패했습니다: {detail}")
    return result.returncode == 0


## @brief M10 이후 RC commit까지 허용된 문서·시험·release 경로만 바뀌었는지 확인합니다.
def validate_m10_followup_changes(repo_root: Path, m10_revision: str, rc_revision: str) -> list[str]:
    if not git_is_ancestor(repo_root, m10_revision, rc_revision):
        raise ReleaseError("M10 preview commit이 RC commit의 ancestor가 아닙니다.")
    changed = [
        path
        for path in git_output(
            repo_root,
            [
                "diff",
                "--name-only",
                "-z",
                "--no-renames",
                "--diff-filter=ACDMRTUXB",
                m10_revision,
                rc_revision,
            ],
        ).split("\0")
        if path
    ]
    disallowed = [
        path
        for path in changed
        if path not in M10_FOLLOWUP_ALLOWED_FILES
        and not any(path.startswith(prefix) for prefix in M10_FOLLOWUP_ALLOWED_PREFIXES)
    ]
    if disallowed:
        raise ReleaseError(
            "M10 이후 RC commit에 허용되지 않은 source 변경이 있습니다: "
            + ", ".join(disallowed)
        )
    return changed


## @brief plan 또는 evidence에 저장할 release artifact identity를 만듭니다.
def artifact_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReleaseError(f"release artifact가 없습니다: {path}")
    return {
        "file_name": path.name,
        "sha256": file_sha256(path),
        "size": path.stat().st_size,
    }


## @brief M11 RC package, RC index와 불변 검증 plan을 생성합니다.
def prepare_rc(repo_root: Path, output_dir: Path, version: str, revision: str) -> dict[str, Path]:
    if version not in M11_RELEASE_CANDIDATE_VERSIONS:
        raise ReleaseError("M11 도구는 명시적으로 허용된 release candidate만 준비합니다. stable은 금지됩니다.")
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    commit = PACKAGE.resolve_commit(repo_root, revision)
    assert_source_state(repo_root, commit)

    try:
        artifacts = PACKAGE.build_package(repo_root, output_dir, version, commit)
        index_path = PACKAGE.generate_index(output_dir, [version])
        release_manifest = PACKAGE.validate_archive(
            artifacts["archive"], expected_version=version, expected_commit=commit
        )
        PACKAGE.validate_index(index_path, artifact_dir=output_dir)
    except PACKAGE.PackageError as error:
        raise ReleaseError(str(error)) from error

    artifact_paths = {**artifacts, "index": index_path}
    plan = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "kind": "release-candidate-plan",
        "version": version,
        "release_tag": PACKAGE.release_tag(version),
        "source_repository": PACKAGE.REPOSITORY_URL,
        "core_revision": commit,
        "board_revision": release_manifest["board_revision"],
        "ncs_version": release_manifest["ncs_version"],
        "ncs_revision": release_manifest["ncs_revision"],
        "zephyr_version": release_manifest["zephyr_version"],
        "zephyr_revision": release_manifest["zephyr_revision"],
        "toolchain_bundle_id": release_manifest["toolchain_bundle_id"],
        "runtime_payload_sha256": release_manifest["runtime_payload_sha256"],
        "source_policy": "exact-clean-checkout-and-exact-commit-package",
        "created_at_utc": PACKAGE.commit_timestamp(repo_root, commit),
        "artifacts": {
            name: artifact_record(path)
            for name, path in sorted(artifact_paths.items())
        },
        "required_gates": list(REQUIRED_GATES),
        "optional_gates": list(OPTIONAL_GATES),
        "validation_scope": {
            "boards_manager_backend": {
                "tool": "arduino-cli",
                "version": ARDUINO_CLI_VERSION,
                "commit": ARDUINO_CLI_COMMIT,
                "executable_sha256": ARDUINO_CLI_SHA256,
                "m10_safe_preview_lifecycle": [
                    M10_SAFE_INITIAL_VERSION,
                    M10_SAFE_LATEST_VERSION,
                ],
            },
            "arduino_ide_gui": {
                "validated": False,
                "status": "not-independently-automated",
                "pass_inference_allowed": False,
            },
            "release_candidate_hil": {
                "archive": "exact-plan-archive",
                "runner": "pyocd",
                "upload_attempts": M11_RC_PYOCD_UPLOAD_ATTEMPTS,
                "uart_ready_token": M11_READY_TOKEN,
                "mass_erase_allowed": False,
                "recover_allowed": False,
            },
        },
        "publication_boundary": {
            "candidate_prerelease_publication_automatable": True,
            "stable_version": "0.1.0",
            "stable_publication_allowed": False,
            "legal_review": "required-human-approval",
            "final_release_approval": "required-human-approval",
        },
    }
    plan_path = output_dir / "m11-rc-plan.json"
    atomic_write(plan_path, canonical_json(plan))
    plan_hash = file_sha256(plan_path)
    integrity_evidence = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "evidence_type": "internal-gate",
        "gate_id": "package_integrity",
        "status": "passed",
        "plan_sha256": plan_hash,
        "release": release_binding(plan),
        "checks": {
            "archive_validator": "passed",
            "index_validator": "passed",
            "artifact_checksums": "passed",
            "exact_core_revision": "passed",
        },
    }
    integrity_path = output_dir / "package_integrity.evidence.json"
    atomic_write(integrity_path, canonical_json(integrity_evidence))
    return {"plan": plan_path, "package_integrity_evidence": integrity_path, **artifact_paths}


## @brief plan에서 모든 evidence가 공유할 release identity를 가져옵니다.
def release_binding(plan: dict[str, Any]) -> dict[str, Any]:
    archive = plan["artifacts"]["archive"]
    index = plan["artifacts"]["index"]
    return {
        "version": plan["version"],
        "release_tag": plan["release_tag"],
        "core_revision": plan["core_revision"],
        "board_revision": plan["board_revision"],
        "runtime_payload_sha256": plan["runtime_payload_sha256"],
        "archive_sha256": archive["sha256"],
        "archive_size": archive["size"],
        "index_sha256": index["sha256"],
    }


## @brief plan 상대 artifact 경로를 traversal 없이 해석합니다.
def plan_artifact_path(plan_path: Path, record: dict[str, Any]) -> Path:
    file_name = record.get("file_name")
    if not isinstance(file_name, str) or Path(file_name).name != file_name or file_name in {"", ".", ".."}:
        raise ReleaseError(f"plan artifact 이름이 안전하지 않습니다: {file_name!r}")
    return plan_path.resolve().parent / file_name


## @brief M11 plan schema와 모든 artifact byte를 다시 검증합니다.
def validate_plan(plan_path: Path) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    document = strict_json(plan_path)
    if not isinstance(document, dict):
        raise ReleaseError("M11 plan 최상위 값이 object가 아닙니다.")
    fixed = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "kind": "release-candidate-plan",
        "required_gates": list(REQUIRED_GATES),
        "optional_gates": list(OPTIONAL_GATES),
    }
    for field, expected in fixed.items():
        if document.get(field) != expected:
            raise ReleaseError(f"M11 plan {field}가 고정 계약과 다릅니다.")
    version = document.get("version")
    if version not in M11_RELEASE_CANDIDATE_VERSIONS:
        raise ReleaseError("M11 plan version은 허용된 RC여야 하며 stable은 허용하지 않습니다.")
    if document.get("release_tag") != PACKAGE.release_tag(version):
        raise ReleaseError("M11 plan release tag가 RC 계약과 다릅니다.")
    exact_identity = {
        "source_repository": PACKAGE.REPOSITORY_URL,
        "ncs_version": PACKAGE.NCS_VERSION,
        "ncs_revision": PACKAGE.NCS_REVISION,
        "zephyr_version": PACKAGE.ZEPHYR_VERSION,
        "zephyr_revision": PACKAGE.ZEPHYR_REVISION,
        "toolchain_bundle_id": PACKAGE.TOOLCHAIN_BUNDLE_ID,
        "source_policy": "exact-clean-checkout-and-exact-commit-package",
    }
    for field, expected in exact_identity.items():
        if document.get(field) != expected:
            raise ReleaseError(f"M11 plan {field} identity가 고정 계약과 다릅니다.")
    for field in ("core_revision", "board_revision"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(document.get(field, ""))):
            raise ReleaseError(f"M11 plan {field}가 full Git commit이 아닙니다.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(document.get("runtime_payload_sha256", ""))):
        raise ReleaseError("M11 plan runtime payload fingerprint가 SHA-256이 아닙니다.")
    created_at = document.get("created_at_utc")
    if not isinstance(created_at, str):
        raise ReleaseError("M11 plan created_at_utc가 없습니다.")
    try:
        dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReleaseError("M11 plan created_at_utc가 ISO-8601이 아닙니다.") from error
    boundary = document.get("publication_boundary")
    expected_boundary = {
        "candidate_prerelease_publication_automatable": True,
        "stable_version": "0.1.0",
        "stable_publication_allowed": False,
        "legal_review": "required-human-approval",
        "final_release_approval": "required-human-approval",
    }
    if boundary != expected_boundary:
        raise ReleaseError("M11 plan이 stable 공개 차단 경계를 보존하지 않습니다.")
    expected_scope = {
        "boards_manager_backend": {
            "tool": "arduino-cli",
            "version": ARDUINO_CLI_VERSION,
            "commit": ARDUINO_CLI_COMMIT,
            "executable_sha256": ARDUINO_CLI_SHA256,
            "m10_safe_preview_lifecycle": [
                M10_SAFE_INITIAL_VERSION,
                M10_SAFE_LATEST_VERSION,
            ],
        },
        "arduino_ide_gui": {
            "validated": False,
            "status": "not-independently-automated",
            "pass_inference_allowed": False,
        },
        "release_candidate_hil": {
            "archive": "exact-plan-archive",
            "runner": "pyocd",
            "upload_attempts": M11_RC_PYOCD_UPLOAD_ATTEMPTS,
            "uart_ready_token": M11_READY_TOKEN,
            "mass_erase_allowed": False,
            "recover_allowed": False,
        },
    }
    if document.get("validation_scope") != expected_scope:
        raise ReleaseError("M11 plan의 Arduino CLI backend/IDE GUI 검증 범위가 고정 계약과 다릅니다.")
    artifacts = document.get("artifacts")
    required_artifacts = {"archive", "checksums", "index", "licenses", "manifest", "notices", "sbom"}
    if not isinstance(artifacts, dict) or set(artifacts) != required_artifacts:
        raise ReleaseError("M11 plan artifact 집합이 고정 계약과 다릅니다.")
    for name, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != {"file_name", "sha256", "size"}:
            raise ReleaseError(f"M11 plan artifact record가 유효하지 않습니다: {name}")
        path = plan_artifact_path(plan_path, record)
        if not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
            raise ReleaseError(f"M11 plan artifact가 없거나 checksum 형식이 잘못되었습니다: {name}")
        if record.get("size") != path.stat().st_size or record["sha256"] != file_sha256(path):
            raise ReleaseError(f"M11 plan artifact byte identity가 다릅니다: {name}")
    archive_path = plan_artifact_path(plan_path, artifacts["archive"])
    index_path = plan_artifact_path(plan_path, artifacts["index"])
    try:
        manifest = PACKAGE.validate_archive(
            archive_path,
            expected_version=version,
            expected_commit=document.get("core_revision"),
        )
        PACKAGE.validate_index(index_path, artifact_dir=plan_path.parent)
    except PACKAGE.PackageError as error:
        raise ReleaseError(str(error)) from error
    if manifest.get("board_revision") != document.get("board_revision"):
        raise ReleaseError("plan과 archive의 보드 revision이 다릅니다.")
    if manifest.get("runtime_payload_sha256") != document.get("runtime_payload_sha256"):
        raise ReleaseError("plan과 archive의 runtime payload fingerprint가 다릅니다.")
    return document


## @brief 자격 증명과 장치 식별자 후보를 command evidence에서 제거합니다.
def redact_text(text: str) -> str:
    result = re.sub(
        r"(?i)(\bauthorization\b\s*:\s*(?:bearer|basic)\s+)\S+",
        r"\1<redacted>",
        text,
    )
    result = re.sub(
        r"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b",
        "<redacted>",
        result,
    )
    result = re.sub(
        r'''(?ix)
        (?P<prefix>
            [\"']?(?:gh_token|github_token|token|password|passwd|secret|client_secret|api_key)[\"']?
            \s*[:=]\s*
        )
        (?P<quote>[\"']?)
        (?P<value>[^\s,;}\"']+)
        (?P=quote)
        ''',
        lambda match: f"{match.group('prefix')}{match.group('quote')}<redacted>{match.group('quote')}",
        result,
    )
    result = re.sub(
        r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        "<redacted-private-key>",
        result,
    )
    return re.sub(r"(?i)\b[0-9a-f]{16,}\b", "<redacted-device-id-or-hash>", result)


## @brief UTF-8 경계를 보존하며 byte 문자열의 마지막 부분을 제한 크기로 줄입니다.
def utf8_tail(data: bytes, limit: int) -> bytes:
    if limit < 0:
        raise ReleaseError("공개 command log byte 제한이 올바르지 않습니다.")
    if len(data) <= limit:
        return data
    return data[-limit:].decode("utf-8", "ignore").encode("utf-8")


## @brief 공개 command log byte를 UTF-8과 truncation marker를 보존하며 제한합니다.
def limit_public_log(data: bytes, *, truncated: bool = False) -> bytes:
    if MAX_COMMAND_LOG_BYTES <= len(LOG_TRUNCATION_MARKER):
        raise ReleaseError("공개 command log byte 제한이 truncation marker보다 작습니다.")
    if not truncated and len(data) <= MAX_COMMAND_LOG_BYTES:
        return data
    budget = MAX_COMMAND_LOG_BYTES - len(LOG_TRUNCATION_MARKER)
    return LOG_TRUNCATION_MARKER + utf8_tail(data, budget)


## @brief 임시 capture에서 제한된 마지막 출력만 읽고 자격 증명을 제거합니다.
def bounded_redacted_log(capture: Any) -> bytes:
    capture.flush()
    captured_size = capture.seek(0, os.SEEK_END)
    capture.seek(max(0, captured_size - MAX_COMMAND_LOG_BYTES), os.SEEK_SET)
    raw_tail = capture.read(MAX_COMMAND_LOG_BYTES)
    sanitized = redact_text(raw_tail.decode("utf-8", "replace")).encode("utf-8")
    truncated = captured_size > len(raw_tail) or len(sanitized) > MAX_COMMAND_LOG_BYTES
    return limit_public_log(sanitized, truncated=truncated)


## @brief timeout된 command의 Windows process tree 또는 POSIX process group을 종료합니다.
def terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        taskkill = Path(system_root) / "System32" / "taskkill.exe"
        taskkill_command = str(taskkill) if taskkill.is_file() else "taskkill.exe"
        try:
            subprocess.run(
                [taskkill_command, "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            process.terminate()
    try:
        process.wait(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            process.kill()
    try:
        process.wait(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise ReleaseError("timeout된 command process tree를 종료하지 못했습니다.") from error


## @brief gate runner가 RC commit에 포함된 exact blob인지 기록합니다.
def committed_runner_record(repo_root: Path, plan: dict[str, Any], relative: str) -> dict[str, str]:
    runner_bytes = git_file_at_revision(repo_root, plan["core_revision"], relative)
    git_object = git_output(
        repo_root, ["rev-parse", f"{plan['core_revision']}:{relative}"]
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", git_object):
        raise ReleaseError(f"고정 gate runner Git object가 유효하지 않습니다: {relative}")
    return {
        "path": relative,
        "git_object": git_object,
        "sha256": hashlib.sha256(runner_bytes).hexdigest(),
    }


## @brief gate별 repo-owned 실행기와 검증 범위를 불변 계약으로 만듭니다.
def fixed_gate_contract(
    repo_root: Path, plan: dict[str, Any], gate_id: str
) -> dict[str, Any]:
    if gate_id not in COMMAND_GATES:
        raise ReleaseError(f"고정 command 계약이 없는 M11 gate입니다: {gate_id}")
    package_identity = {
        "version": plan["version"],
        "core_revision": plan["core_revision"],
        "board_revision": plan["board_revision"],
        "runtime_payload_sha256": plan["runtime_payload_sha256"],
        "archive_sha256": plan["artifacts"]["archive"]["sha256"],
    }
    common: dict[str, Any] = {
        "schema_version": 1,
        "gate_id": gate_id,
        "runner": committed_runner_record(
            repo_root,
            plan,
            RC_HIL_RUNNER_PATH if gate_id == "hil_rc_pyocd" else FIXED_GATE_RUNNER_PATH,
        ),
        "package": package_identity if gate_id != "host_regression" else None,
        "arduino_cli": None,
    }
    if gate_id == "host_regression":
        common.update(
            {
                "command_template": [
                    "{python}",
                    FIXED_GATE_RUNNER_PATH,
                    "host",
                    "--repo-root",
                    "{repo_root}",
                ],
                "scope": {
                    "kind": "python-unittest-discovery",
                    "start_directory": "tests/host",
                    "pattern": "test_*.py",
                },
            }
        )
    elif gate_id == "arduino_cli_fixed_package":
        common.update(
            {
                "arduino_cli": {
                    "version": ARDUINO_CLI_VERSION,
                    "commit": ARDUINO_CLI_COMMIT,
                    "executable_sha256": ARDUINO_CLI_SHA256,
                },
                "command_template": [
                    "{python}",
                    FIXED_GATE_RUNNER_PATH,
                    "arduino",
                    "--repo-root",
                    "{repo_root}",
                    "--platform-root",
                    "{platform_root}",
                    "--arduino-cli",
                    "{arduino_cli}",
                    "--expected-version",
                    plan["version"],
                    "--expected-core-revision",
                    plan["core_revision"],
                    "--expected-board-revision",
                    plan["board_revision"],
                    "--expected-runtime-payload-sha256",
                    plan["runtime_payload_sha256"],
                    "--expected-release-manifest-sha256",
                    plan["artifacts"]["manifest"]["sha256"],
                ],
                "scope": {
                    "kind": "arduino-cli-package-smoke",
                    "fqbn": M10_FQBN,
                    "scenarios": [
                        "blink",
                        "library",
                        "config",
                        "error",
                        "parallel",
                        "m6",
                        "m7",
                        "m8",
                        "m9",
                        "m11",
                    ],
                },
            }
        )
    elif gate_id == "zephyr_regression":
        common.update(
            {
                "command_template": [
                    "{python}",
                    FIXED_GATE_RUNNER_PATH,
                    "zephyr",
                    "--repo-root",
                    "{repo_root}",
                    "--platform-root",
                    "{platform_root}",
                    "--outdir",
                    "{gate_workspace}",
                    "--expected-version",
                    plan["version"],
                    "--expected-core-revision",
                    plan["core_revision"],
                    "--expected-board-revision",
                    plan["board_revision"],
                    "--expected-runtime-payload-sha256",
                    plan["runtime_payload_sha256"],
                    "--expected-release-manifest-sha256",
                    plan["artifacts"]["manifest"]["sha256"],
                ],
                "scope": {
                    "kind": "zephyr-twister-target-build",
                    "board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
                    "test_root": "tests/zephyr",
                    "scenarios": [
                        "nucode.m3.runtime",
                        "nucode.m4.api_contract",
                        "nucode.m6.core_api",
                        "nucode.m7.core_api",
                    ],
                    "build_only": True,
                    "result_contract": "built-not-run",
                    "detailed_test_id": True,
                    "short_build_path": False,
                    "device_testing": False,
                },
            }
        )
    else:
        common.update(
            {
                "arduino_cli": {
                    "version": ARDUINO_CLI_VERSION,
                    "commit": ARDUINO_CLI_COMMIT,
                    "executable_sha256": ARDUINO_CLI_SHA256,
                },
                "command_template": [
                    "{python}",
                    RC_HIL_RUNNER_PATH,
                    "--repository",
                    "{repo_root}",
                    "--workspace",
                    "{gate_workspace}",
                    "--cli",
                    "{arduino_cli}",
                    "--runner",
                    "pyocd",
                    "--rc-platform-root",
                    "{platform_root}",
                    "--expected-version",
                    plan["version"],
                    "--expected-core-revision",
                    plan["core_revision"],
                    "--expected-runtime-payload-sha256",
                    plan["runtime_payload_sha256"],
                    "--serial-port",
                    "{serial_port}",
                    "--repetitions",
                    str(M11_RC_PYOCD_UPLOAD_ATTEMPTS),
                    "--uart-each",
                ],
                "scope": {
                    "kind": "exact-rc-pyocd-uart-hil",
                    "fqbn": f"{M10_FQBN}:upload_probe=pyocd",
                    "upload_attempts": M11_RC_PYOCD_UPLOAD_ATTEMPTS,
                    "ready_token": M11_READY_TOKEN,
                    "mass_erase_allowed": False,
                    "recover_allowed": False,
                },
            }
        )
    return common


## @brief 고정 계약의 placeholder를 검증된 실제 경로로만 치환합니다.
def fixed_gate_invocation(
    repo_root: Path,
    plan: dict[str, Any],
    gate_id: str,
    platform_root: Path | None,
    gate_workspace: Path,
    arduino_cli: Path | None,
    serial_port: str,
) -> tuple[list[str], dict[str, Any]]:
    contract = fixed_gate_contract(repo_root, plan, gate_id)
    requires_package = gate_id != "host_regression"
    requires_cli = gate_id in {"arduino_cli_fixed_package", "hil_rc_pyocd"}
    if requires_package != (platform_root is not None):
        raise ReleaseError(f"고정 gate package 추출 계약이 다릅니다: {gate_id}")
    cli_path: Path | None = None
    if requires_cli:
        if arduino_cli is None:
            raise ReleaseError(f"{gate_id}에는 --arduino-cli가 필요합니다.")
        cli_path = arduino_cli.resolve()
        if (
            not cli_path.is_file()
            or cli_path.is_symlink()
            or file_sha256(cli_path) != ARDUINO_CLI_SHA256
        ):
            raise ReleaseError("Arduino CLI executable이 고정 1.5.2-rc.1 SHA-256과 다릅니다.")
    elif arduino_cli is not None:
        raise ReleaseError(f"{gate_id}에는 --arduino-cli를 지정할 수 없습니다.")
    if gate_id != "hil_rc_pyocd" and serial_port != "auto":
        raise ReleaseError(f"{gate_id}에는 --serial-port를 지정할 수 없습니다.")
    if not isinstance(serial_port, str) or not serial_port or "\0" in serial_port:
        raise ReleaseError("HIL serial port 값이 유효하지 않습니다.")
    replacements = {
        "{python}": sys.executable,
        "{repo_root}": str(repo_root),
        "{platform_root}": str(platform_root) if platform_root is not None else "",
        "{gate_workspace}": str(gate_workspace),
        "{arduino_cli}": str(cli_path) if cli_path is not None else "",
        "{serial_port}": serial_port,
    }
    command = [replacements.get(value, value) for value in contract["command_template"]]
    if any(not value or "\0" in value for value in command):
        raise ReleaseError("고정 gate command 치환 결과가 유효하지 않습니다.")
    return command, contract


## @brief RC HIL runner JSON이 exact package·HEX·pyOCD·UART 계약을 증명하는지 확인합니다.
def validate_rc_hil_result(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    result = strict_json(path)
    if (
        not isinstance(result, dict)
        or result.get("schema_version") != 1
        or result.get("milestone") != MILESTONE
        or result.get("evidence_type") != "rc-pyocd-hil"
        or result.get("status") != "passed"
    ):
        raise ReleaseError("RC pyOCD HIL result schema 또는 PASS 상태가 유효하지 않습니다.")
    release = result.get("release")
    if not isinstance(release, dict):
        raise ReleaseError("RC pyOCD HIL release identity가 없습니다.")
    expected_release = {
        "version": plan["version"],
        "core_revision": plan["core_revision"],
        "board_revision": plan["board_revision"],
        "runtime_payload_sha256": plan["runtime_payload_sha256"],
    }
    if any(release.get(field) != value for field, value in expected_release.items()):
        raise ReleaseError("RC pyOCD HIL result가 현재 RC package identity와 다릅니다.")
    if release.get("release_manifest_sha256") != plan["artifacts"]["manifest"]["sha256"]:
        raise ReleaseError("RC pyOCD HIL release manifest byte identity가 RC plan과 다릅니다.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(release.get("platform_tree_sha256", ""))):
        raise ReleaseError("RC pyOCD HIL platform tree checksum이 SHA-256이 아닙니다.")
    if not isinstance(release.get("file_count"), int) or release.get("file_count") < 1:
        raise ReleaseError("RC pyOCD HIL platform file count가 유효하지 않습니다.")
    if result.get("platform") != {
        "mode": "validated-extracted-rc",
        "staged_byte_exact": True,
    }:
        raise ReleaseError("RC pyOCD HIL이 검증된 archive 추출본을 byte-exact로 사용하지 않았습니다.")
    sketch = result.get("sketch")
    expected_sketch_path = "tests/arduino-cli/m8_upload/m8_upload.ino"
    expected_sketch_sha256 = hashlib.sha256(
        git_file_at_revision(
            Path(__file__).resolve().parents[2],
            plan["core_revision"],
            expected_sketch_path,
        )
    ).hexdigest()
    if sketch != {
        "repository_relative_path": expected_sketch_path,
        "sha256": expected_sketch_sha256,
    }:
        raise ReleaseError("RC pyOCD HIL sketch가 RC commit의 고정 M8 fixture와 다릅니다.")
    cli = result.get("arduino_cli")
    if cli != {"sha256": ARDUINO_CLI_SHA256}:
        raise ReleaseError("RC pyOCD HIL Arduino CLI executable identity가 다릅니다.")
    build = result.get("build")
    if (
        not isinstance(build, dict)
        or build.get("fqbn") != f"{M10_FQBN}:upload_probe=pyocd"
        or not re.fullmatch(r"[0-9a-f]{64}", str(build.get("manifest_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(build.get("hex_sha256", "")))
        or not isinstance(build.get("hex_size"), int)
        or build.get("hex_size") < 1
    ):
        raise ReleaseError("RC pyOCD HIL build/HEX identity가 유효하지 않습니다.")
    upload = result.get("upload")
    expected_upload_fields = {
        "runner": "pyocd",
        "attempts": M11_RC_PYOCD_UPLOAD_ATTEMPTS,
        "smart_flash": False,
        "mass_erase_requested": False,
        "recover_requested": False,
        "hex_unchanged_after_upload": True,
    }
    if not isinstance(upload, dict) or any(
        upload.get(field) != value for field, value in expected_upload_fields.items()
    ):
        raise ReleaseError("RC pyOCD HIL upload가 1회 비파괴 exact HEX 계약과 다릅니다.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(upload.get("flash_log_sha256", ""))):
        raise ReleaseError("RC pyOCD HIL flash log checksum이 유효하지 않습니다.")
    uart = result.get("uart")
    if (
        not isinstance(uart, dict)
        or uart.get("token") != M11_READY_TOKEN
        or uart.get("ready") is not True
        or not isinstance(uart.get("candidate_count"), int)
        or uart.get("candidate_count") < 1
        or uart.get("ready_match_count") != 1
        or not re.fullmatch(r"[0-9a-f]{64}", str(uart.get("transcript_sha256", "")))
    ):
        raise ReleaseError("RC pyOCD HIL UART READY evidence가 유일한 물리 port를 증명하지 않습니다.")
    return {
        "result_file_name": path.name,
        "result_sha256": file_sha256(path),
        "runtime_payload_sha256": release["runtime_payload_sha256"],
        "platform_tree_sha256": release["platform_tree_sha256"],
        "sketch_sha256": expected_sketch_sha256,
        "hex_sha256": build["hex_sha256"],
        "hex_size": build["hex_size"],
        "flash_log_sha256": upload["flash_log_sha256"],
        "ready_token": uart["token"],
        "upload_attempts": upload["attempts"],
    }


## @brief RC ZIP을 검증한 뒤 임시 platform root에 안전하게 해제합니다.
def extract_platform(plan_path: Path, plan: dict[str, Any], destination: Path) -> Path:
    archive_path = plan_artifact_path(plan_path, plan["artifacts"]["archive"])
    try:
        PACKAGE.validate_archive(
            archive_path,
            expected_version=plan["version"],
            expected_commit=plan["core_revision"],
        )
    except PACKAGE.PackageError as error:
        raise ReleaseError(str(error)) from error
    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1 or roots[0].name != f"nucode-nu54dk-zephyr-{plan['version']}":
        raise ReleaseError("해제된 RC platform root가 archive 계약과 다릅니다.")
    return roots[0]


## @brief 하나의 검증 명령을 실행하고 RC identity에 묶인 evidence와 정제 log를 기록합니다.
def run_command_gate(
    repo_root: Path,
    plan_path: Path,
    gate_id: str,
    output_path: Path,
    timeout_seconds: int,
    arduino_cli: Path | None = None,
    serial_port: str = "auto",
) -> tuple[dict[str, Any], int]:
    if gate_id not in COMMAND_GATES:
        raise ReleaseError(f"command로 실행할 수 없는 M11 gate입니다: {gate_id}")
    if timeout_seconds < 1 or timeout_seconds > 86400:
        raise ReleaseError("gate timeout은 1..86400초여야 합니다.")
    plan_path = plan_path.resolve()
    repo_root = repo_root.resolve()
    plan = validate_plan(plan_path)
    assert_source_state(repo_root, plan["core_revision"])
    plan_hash = file_sha256(plan_path)
    output_path = output_path.resolve()
    log_path = output_path.with_suffix(".log")
    started = dt.datetime.now(dt.timezone.utc)
    started_monotonic = time.monotonic()
    exit_code: int | None = None
    timed_out = False
    temporary: tempfile.TemporaryDirectory[str] | None = None
    platform_root: Path | None = None
    command_contract: dict[str, Any] | None = None
    hil_result: dict[str, Any] | None = None
    try:
        if gate_id != "host_regression":
            temporary = tempfile.TemporaryDirectory(prefix="nu54-m11-rc-")
            temporary_root = Path(temporary.name)
            platform_root = extract_platform(plan_path, plan, temporary_root / "platform")
            gate_workspace = temporary_root / "gate-workspace"
        else:
            gate_workspace = output_path.parent / ".unused-host-workspace"
        expanded, command_contract = fixed_gate_invocation(
            repo_root,
            plan,
            gate_id,
            platform_root,
            gate_workspace,
            arduino_cli,
            serial_port,
        )
        environment = os.environ.copy()
        environment.update(
            {
                "NU54_RELEASE_VERSION": plan["version"],
                "NU54_RELEASE_CORE_REVISION": plan["core_revision"],
                "NU54_RELEASE_RUNTIME_PAYLOAD_SHA256": plan["runtime_payload_sha256"],
                "NU54_RELEASE_ARCHIVE": str(plan_artifact_path(plan_path, plan["artifacts"]["archive"])),
                "NU54_RELEASE_INDEX": str(plan_artifact_path(plan_path, plan["artifacts"]["index"])),
            }
        )
        if platform_root is not None:
            environment["NU54_RELEASE_PLATFORM_ROOT"] = str(platform_root)
        with tempfile.TemporaryFile(prefix="nu54-m11-command-", mode="w+b") as capture:
            try:
                process_options: dict[str, Any] = {}
                if os.name == "nt":
                    process_options["creationflags"] = getattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                    )
                else:
                    process_options["start_new_session"] = True
                process = subprocess.Popen(
                    expanded,
                    cwd=repo_root,
                    env=environment,
                    stdout=capture,
                    stderr=subprocess.STDOUT,
                    **process_options,
                )
                try:
                    exit_code = process.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    exit_code = 124
                    terminate_process_tree(process)
            except OSError as error:
                exit_code = 127
                capture.write(str(error).encode("utf-8", "replace"))
            public_log = bounded_redacted_log(capture)
        sanitized = public_log.decode("utf-8")
        atomic_write(log_path, public_log)
        if exit_code == 0 and not timed_out and gate_id == "hil_rc_pyocd":
            candidates = sorted(gate_workspace.glob("*/m8-upload-result.json"))
            if len(candidates) != 1:
                raise ReleaseError("RC pyOCD HIL result JSON이 정확히 하나 생성되지 않았습니다.")
            frozen_result = output_path.with_suffix(".result.json")
            atomic_write(frozen_result, candidates[0].read_bytes())
            hil_result = validate_rc_hil_result(frozen_result, plan)
    finally:
        if temporary is not None:
            temporary.cleanup()
    try:
        assert_source_state(repo_root, plan["core_revision"])
    except ReleaseError as error:
        source_failure = redact_text(f"\n[NU54] gate 실행 후 source identity 검증 실패: {error}\n")
        public_log = limit_public_log(public_log + source_failure.encode("utf-8"))
        sanitized = public_log.decode("utf-8")
        atomic_write(log_path, public_log)
        exit_code = 125
    completed = dt.datetime.now(dt.timezone.utc)
    status = "passed" if exit_code == 0 and not timed_out else "failed"
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "evidence_type": "command-gate",
        "gate_id": gate_id,
        "status": status,
        "plan_sha256": plan_hash,
        "release": release_binding(plan),
        "command_contract": command_contract,
        "started_at_utc": started.isoformat(),
        "completed_at_utc": completed.isoformat(),
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        "command": command_contract["command_template"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "log": {
            "file_name": log_path.name,
            "sha256": file_sha256(log_path),
            "size": log_path.stat().st_size,
            "redacted": True,
            "excerpt": sanitized[-LOG_EXCERPT_CHARS:],
        },
        "environment": {
            "os": platform.system(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
    }
    if hil_result is not None:
        evidence["hil_result"] = hil_result
    atomic_write(output_path, canonical_json(evidence))
    return evidence, int(exit_code or 0)


## @brief 문서 파일이 고정 RC commit의 blob과 같은지 확인해 documentation evidence를 만듭니다.
def record_documentation_gate(
    repo_root: Path, plan_path: Path, output_path: Path, documents: dict[str, Path]
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    plan_path = plan_path.resolve()
    plan = validate_plan(plan_path)
    assert_source_state(repo_root, plan["core_revision"])
    if set(documents) != set(REQUIRED_DOCUMENT_ROLES):
        missing = sorted(set(REQUIRED_DOCUMENT_ROLES).difference(documents))
        extra = sorted(set(documents).difference(REQUIRED_DOCUMENT_ROLES))
        raise ReleaseError(
            "documentation 역할 집합이 불완전합니다. "
            f"누락={','.join(missing) or '-'} 초과={','.join(extra) or '-'}"
        )
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role in REQUIRED_DOCUMENT_ROLES:
        requested = documents[role]
        path = requested if requested.is_absolute() else repo_root / requested
        path = path.resolve()
        try:
            relative = path.relative_to(repo_root).as_posix()
        except ValueError as error:
            raise ReleaseError(f"문서가 repository 밖에 있습니다: {path}") from error
        if relative in seen or not path.is_file():
            raise ReleaseError(f"문서가 없거나 중복되었습니다: {relative}")
        seen.add(relative)
        try:
            committed = subprocess.run(
                ["git", "show", f"{plan['core_revision']}:{relative}"],
                cwd=repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            raise ReleaseError(f"RC commit에 문서가 없습니다: {relative}") from error
        committed_object = git_output(
            repo_root, ["rev-parse", f"{plan['core_revision']}:{relative}"]
        ).strip()
        checkout_object = git_output(repo_root, ["hash-object", "--path", relative, relative]).strip()
        if checkout_object != committed_object:
            raise ReleaseError(f"checkout 문서가 RC commit의 정규화된 blob과 다릅니다: {relative}")
        records.append(
            {
                "role": role,
                "path": relative,
                "git_object": committed_object,
                "sha256": hashlib.sha256(committed).hexdigest(),
                "size": len(committed),
            }
        )
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "evidence_type": "file-gate",
        "gate_id": "documentation",
        "status": "passed",
        "plan_sha256": file_sha256(plan_path),
        "release": release_binding(plan),
        "files": records,
    }
    atomic_write(output_path, canonical_json(evidence))
    return evidence


## @brief M10 target와 orchestrator 원본이 exact runner·공개 index·10회 HIL을 증명하는지 검증합니다.
def validate_m10_source_evidence(
    plan: dict[str, Any], target_evidence_path: Path, orchestrator_path: Path
) -> dict[str, Any]:
    target_evidence_path = target_evidence_path.resolve()
    orchestrator_path = orchestrator_path.resolve()
    target = strict_json(target_evidence_path)
    if not isinstance(target, dict) or target.get("schema_version") != 2 or target.get("milestone") != "M10":
        raise ReleaseError("가져올 대상 evidence가 M10 schema 2가 아닙니다.")
    run_id = target.get("run_id")
    if (
        target.get("status") != "passed"
        or not isinstance(target.get("completed_at_utc"), str)
        or not isinstance(run_id, str)
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", run_id)
        or target.get("failure") is not None
    ):
        raise ReleaseError("M10 clean Windows evidence가 완료 PASS가 아닙니다.")
    if target.get("redaction") != {"device_identifiers": True, "credentials": True}:
        raise ReleaseError("M10 target evidence의 redaction 계약이 유효하지 않습니다.")

    configuration = target.get("configuration")
    if (
        not isinstance(configuration, dict)
        or configuration.get("index_url") != M10_PREVIEW_INDEX_URL
        or configuration.get("fqbn") != M10_FQBN
        or configuration.get("initial_version") != M10_SAFE_INITIAL_VERSION
        or configuration.get("latest_version") != M10_SAFE_LATEST_VERSION
        or configuration.get("ncs_version") != plan["ncs_version"]
        or configuration.get("toolchain_bundle_id") != plan["toolchain_bundle_id"]
        or configuration.get("require_probe") is not True
    ):
        raise ReleaseError("M10 공개 index/FQBN/NCS/toolchain/probe 계약이 M11 plan과 다릅니다.")
    m10_index_sha256 = configuration.get("index_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", str(m10_index_sha256 or "")):
        raise ReleaseError("M10 안전 preview public index checksum이 유효하지 않습니다.")

    repository = Path(__file__).resolve().parents[2]
    expected_runner_sha256 = hashlib.sha256(
        git_file_at_revision(repository, plan["core_revision"], M10_TARGET_RUNNER_PATH)
    ).hexdigest()
    if configuration.get("target_runner_sha256") != expected_runner_sha256:
        raise ReleaseError("M10 target runner가 RC exact commit의 runner byte와 다릅니다.")
    expected_cli = {
        "expected_version": ARDUINO_CLI_VERSION,
        "expected_commit": ARDUINO_CLI_COMMIT,
        "executable_sha256": ARDUINO_CLI_SHA256,
    }
    if configuration.get("arduino_cli") != expected_cli:
        raise ReleaseError("M10 evidence의 Arduino CLI backend exact identity가 M11 계약과 다릅니다.")

    archives = configuration.get("archives")
    if not isinstance(archives, dict) or set(archives) != {
        M10_SAFE_INITIAL_VERSION,
        M10_SAFE_LATEST_VERSION,
    }:
        raise ReleaseError("M10 evidence의 안전 preview archive 집합이 정확하지 않습니다.")
    safe_archive_identities: dict[str, dict[str, Any]] = {}
    for version in (M10_SAFE_INITIAL_VERSION, M10_SAFE_LATEST_VERSION):
        identity = archives[version]
        if not isinstance(identity, dict):
            raise ReleaseError(f"M10 안전 preview archive identity가 없습니다: {version}")
        normalized = {
            "file_name": identity.get("file_name"),
            "sha256": identity.get("sha256"),
            "size": str(identity.get("size", "")),
            "core_revision": identity.get("core_revision"),
            "board_revision": identity.get("board_revision"),
            "runtime_payload_sha256": identity.get("runtime_payload_sha256"),
            "release_manifest_sha256": identity.get("release_manifest_sha256"),
        }
        if (
            normalized["file_name"] != PACKAGE.archive_filename(version)
            or not re.fullmatch(r"[0-9a-f]{64}", str(normalized["sha256"] or ""))
            or not re.fullmatch(r"[1-9][0-9]*", normalized["size"])
            or not re.fullmatch(r"[0-9a-f]{40}", str(normalized["core_revision"] or ""))
            or not re.fullmatch(r"[0-9a-f]{40}", str(normalized["board_revision"] or ""))
            or not re.fullmatch(r"[0-9a-f]{64}", str(normalized["runtime_payload_sha256"] or ""))
            or not re.fullmatch(r"[0-9a-f]{64}", str(normalized["release_manifest_sha256"] or ""))
        ):
            raise ReleaseError(f"M10 안전 preview {version} identity가 M11 source와 다릅니다.")
        safe_archive_identities[version] = normalized

    preview_revisions = {item["core_revision"] for item in safe_archive_identities.values()}
    preview_boards = {item["board_revision"] for item in safe_archive_identities.values()}
    preview_payloads = {
        item["runtime_payload_sha256"] for item in safe_archive_identities.values()
    }
    if len(preview_revisions) != 1 or len(preview_boards) != 1 or len(preview_payloads) != 1:
        raise ReleaseError("M10 두 safe preview가 같은 source/board/runtime payload를 사용하지 않았습니다.")
    m10_revision = next(iter(preview_revisions))
    runtime_payload = next(iter(preview_payloads))
    if next(iter(preview_boards)) != plan["board_revision"]:
        raise ReleaseError("M10 safe preview와 RC plan의 보드 revision이 다릅니다.")
    if runtime_payload != plan["runtime_payload_sha256"]:
        raise ReleaseError("M10 safe preview와 RC plan의 runtime payload fingerprint가 다릅니다.")
    allowed_followup_changes = validate_m10_followup_changes(
        repository, m10_revision, plan["core_revision"]
    )
    m10_runner_sha256 = hashlib.sha256(
        git_file_at_revision(repository, m10_revision, M10_TARGET_RUNNER_PATH)
    ).hexdigest()
    if m10_runner_sha256 != expected_runner_sha256:
        raise ReleaseError("M10 preview와 RC commit의 target runner byte가 다릅니다.")

    baseline = target.get("initial_environment")
    if (
        not isinstance(baseline, dict)
        or baseline.get("ncs_exists") is not False
        or baseline.get("prerequisite_state_exists") is not False
        or baseline.get("ready_marker_exists") is not False
    ):
        raise ReleaseError("M10 evidence가 NCS 없는 clean Windows 시작 상태를 증명하지 않습니다.")
    required_step_order = (
        "preflight",
        "update_index",
        "install_initial",
        "board_details_initial",
        "blink_cold_compile",
        "blink_warm_compile",
        "probe_and_upload",
        "upgrade_latest",
        "downgrade_initial",
        "uninstall_preserves_ncs",
        "reinstall_latest",
    )
    steps = target.get("steps")
    if not isinstance(steps, list):
        raise ReleaseError("M10 steps가 배열이 아닙니다.")
    by_name = {step.get("name"): step for step in steps if isinstance(step, dict)}
    if (
        [step.get("name") for step in steps if isinstance(step, dict)] != list(required_step_order)
        or len(by_name) != len(steps)
        or any(by_name[name].get("status") != "passed" for name in required_step_order)
    ):
        raise ReleaseError("M10 필수 clean Windows lifecycle step이 정확히 모두 PASS가 아닙니다.")
    upload = by_name["probe_and_upload"].get("result")
    if (
        not isinstance(upload, dict)
        or upload.get("attached") is not True
        or upload.get("upload") != "passed"
        or upload.get("probe_count") != 1
        or upload.get("upload_attempts") != M11_PYOCD_UPLOAD_ATTEMPTS
    ):
        raise ReleaseError("M10 evidence가 단일 CMSIS-DAP pyOCD 10회 upload PASS를 증명하지 않습니다.")

    target_hash = file_sha256(target_evidence_path)
    orchestrator = strict_json(orchestrator_path)
    if not isinstance(orchestrator, dict) or orchestrator.get("schema_version") != 1 or orchestrator.get("milestone") != "M10":
        raise ReleaseError("M10 orchestrator evidence schema가 유효하지 않습니다.")
    if (
        orchestrator.get("run_id") != run_id
        or orchestrator.get("status") != "passed"
        or orchestrator.get("remote_exit_code") != 0
        or orchestrator.get("target_evidence_sha256") != target_hash
        or orchestrator.get("public_index_url") != M10_PREVIEW_INDEX_URL
        or orchestrator.get("public_index_sha256") != m10_index_sha256
        or orchestrator.get("target_runner_sha256") != expected_runner_sha256
    ):
        raise ReleaseError("M10 orchestrator가 target runner·공개 index·PASS evidence에 정확히 묶이지 않았습니다.")
    if orchestrator.get("expected_arduino_cli") != {
        "version": ARDUINO_CLI_VERSION,
        "commit": ARDUINO_CLI_COMMIT,
        "sha256": ARDUINO_CLI_SHA256,
    }:
        raise ReleaseError("M10 orchestrator Arduino CLI backend identity가 M11 계약과 다릅니다.")
    orchestrator_archives = orchestrator.get("archives")
    if not isinstance(orchestrator_archives, dict):
        raise ReleaseError("M10 orchestrator 안전 preview archive 목록이 없습니다.")
    for version in (M10_SAFE_INITIAL_VERSION, M10_SAFE_LATEST_VERSION):
        identity = orchestrator_archives.get(version)
        normalized = {
            "file_name": identity.get("file_name") if isinstance(identity, dict) else None,
            "sha256": identity.get("sha256") if isinstance(identity, dict) else None,
            "size": str(identity.get("size", "")) if isinstance(identity, dict) else "",
            "core_revision": identity.get("core_revision") if isinstance(identity, dict) else None,
            "board_revision": identity.get("board_revision") if isinstance(identity, dict) else None,
            "runtime_payload_sha256": identity.get("runtime_payload_sha256") if isinstance(identity, dict) else None,
            "release_manifest_sha256": identity.get("release_manifest_sha256") if isinstance(identity, dict) else None,
        }
        if normalized != safe_archive_identities[version]:
            raise ReleaseError("M10 orchestrator 안전 preview archive identity가 target과 다릅니다.")
    return {
        "run_id": run_id,
        "target_evidence_sha256": target_hash,
        "orchestrator_evidence_sha256": file_sha256(orchestrator_path),
        "safe_preview_index_sha256": m10_index_sha256,
        "target_runner_sha256": expected_runner_sha256,
        "safe_preview_archives": safe_archive_identities,
        "m10_source_revision": m10_revision,
        "rc_source_revision": plan["core_revision"],
        "runtime_payload_sha256": runtime_payload,
        "allowed_followup_changes": allowed_followup_changes,
        "pyocd_upload_attempts": M11_PYOCD_UPLOAD_ATTEMPTS,
    }


## @brief 검증된 M10 원본을 RC evidence directory에 동결하고 두 필수 gate를 생성합니다.
def import_m10_evidence(
    plan_path: Path,
    target_evidence_path: Path,
    output_dir: Path,
    orchestrator_path: Path,
) -> dict[str, Path]:
    plan_path = plan_path.resolve()
    plan = validate_plan(plan_path)
    source = validate_m10_source_evidence(plan, target_evidence_path, orchestrator_path)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    frozen_target = output_dir / "m10-target.source.json"
    frozen_orchestrator = output_dir / "m10-orchestrator.source.json"
    atomic_write(frozen_target, target_evidence_path.resolve().read_bytes())
    atomic_write(frozen_orchestrator, orchestrator_path.resolve().read_bytes())
    frozen_source = validate_m10_source_evidence(plan, frozen_target, frozen_orchestrator)
    if source != frozen_source:
        raise ReleaseError("동결한 M10 source evidence identity가 원본과 다릅니다.")

    source_record = {
        "milestone": "M10",
        "run_id": source["run_id"],
        "target_evidence_file": frozen_target.name,
        "target_evidence_sha256": source["target_evidence_sha256"],
        "orchestrator_evidence_file": frozen_orchestrator.name,
        "orchestrator_evidence_sha256": source["orchestrator_evidence_sha256"],
        "safe_preview_versions": [M10_SAFE_INITIAL_VERSION, M10_SAFE_LATEST_VERSION],
        "safe_preview_index_url": M10_PREVIEW_INDEX_URL,
        "safe_preview_index_sha256": source["safe_preview_index_sha256"],
        "target_runner_sha256": source["target_runner_sha256"],
        "safe_preview_archives": source["safe_preview_archives"],
        "m10_source_revision": source["m10_source_revision"],
        "rc_source_revision": source["rc_source_revision"],
        "runtime_payload_sha256": source["runtime_payload_sha256"],
        "allowed_followup_changes": source["allowed_followup_changes"],
        "pyocd_upload_attempts": source["pyocd_upload_attempts"],
    }
    common = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "evidence_type": "imported-m10-gate",
        "status": "passed",
        "plan_sha256": file_sha256(plan_path),
        "release": release_binding(plan),
        "source": source_record,
        "validation_scope": {
            "boards_manager_backend": "arduino-cli-1.5.2-rc.1",
            "clean_windows_packages": [M10_SAFE_INITIAL_VERSION, M10_SAFE_LATEST_VERSION],
            "pyocd_upload_attempts": M11_PYOCD_UPLOAD_ATTEMPTS,
            "release_candidate_package_directly_installed": False,
            "arduino_ide_gui_validated": False,
            "arduino_ide_gui_pass_inferred": False,
        },
    }
    results: dict[str, Path] = {}
    for gate_id in ("clean_windows", "hil_pyocd"):
        evidence = {**common, "gate_id": gate_id}
        path = output_dir / f"{gate_id}.evidence.json"
        atomic_write(path, canonical_json(evidence))
        results[gate_id] = path
    return results


## @brief 개별 gate evidence가 plan identity와 log checksum을 정확히 참조하는지 검증합니다.
def validate_gate_evidence(plan_path: Path, plan: dict[str, Any], evidence_path: Path) -> dict[str, Any]:
    evidence_path = evidence_path.resolve()
    evidence = strict_json(evidence_path)
    if not isinstance(evidence, dict) or evidence.get("schema_version") != SCHEMA_VERSION or evidence.get("milestone") != MILESTONE:
        raise ReleaseError(f"M11 gate evidence schema가 유효하지 않습니다: {evidence_path}")
    gate_id = evidence.get("gate_id")
    if gate_id not in {*REQUIRED_GATES, *OPTIONAL_GATES}:
        raise ReleaseError(f"알 수 없는 M11 gate입니다: {gate_id}")
    if evidence.get("plan_sha256") != file_sha256(plan_path) or evidence.get("release") != release_binding(plan):
        raise ReleaseError(f"gate evidence가 현재 RC plan에 묶이지 않았습니다: {gate_id}")
    if evidence.get("status") not in {"passed", "failed"}:
        raise ReleaseError(f"gate evidence status가 유효하지 않습니다: {gate_id}")
    evidence_type = evidence.get("evidence_type")
    allowed_types = {
        "package_integrity": {"internal-gate"},
        "host_regression": {"command-gate"},
        "arduino_cli_fixed_package": {"command-gate"},
        "zephyr_regression": {"command-gate"},
        "hil_rc_pyocd": {"command-gate"},
        "hil_pyocd": {"imported-m10-gate"},
        "clean_windows": {"imported-m10-gate"},
        "documentation": {"file-gate"},
        "hil_jlink": {"command-gate"},
    }
    if evidence_type not in allowed_types[gate_id]:
        raise ReleaseError(f"gate evidence 종류가 gate 계약과 다릅니다: {gate_id}: {evidence_type}")
    if evidence_type == "internal-gate":
        expected_checks = {
            "archive_validator": "passed",
            "index_validator": "passed",
            "artifact_checksums": "passed",
            "exact_core_revision": "passed",
        }
        if evidence.get("checks") != expected_checks:
            raise ReleaseError("package integrity evidence의 검증 항목이 불완전합니다.")
    if evidence_type == "command-gate":
        required_fields = {
            "started_at_utc",
            "completed_at_utc",
            "duration_seconds",
            "command",
            "command_contract",
            "exit_code",
            "timed_out",
            "log",
            "environment",
        }
        if not required_fields.issubset(evidence):
            raise ReleaseError(f"command evidence 필수 field가 누락되었습니다: {gate_id}")
        command = evidence.get("command")
        repository = Path(__file__).resolve().parents[2]
        expected_contract = fixed_gate_contract(repository, plan, gate_id)
        if evidence.get("command_contract") != expected_contract:
            raise ReleaseError(f"command evidence의 repo-owned gate 계약이 다릅니다: {gate_id}")
        exit_code = evidence.get("exit_code")
        timed_out = evidence.get("timed_out")
        duration = evidence.get("duration_seconds")
        if (
            not isinstance(command, list)
            or not command
            or command != expected_contract["command_template"]
            ## @note command template은 repo-owned exact 계약과 동일해야 하며,
            ##       core revision과 runtime payload SHA-256은 공개 릴리스 식별자입니다.
            or any(not isinstance(value, str) or not value for value in command)
            or not isinstance(exit_code, int)
            or isinstance(exit_code, bool)
            or not isinstance(timed_out, bool)
            or not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise ReleaseError(f"command evidence 실행 field가 유효하지 않습니다: {gate_id}")
        for field in ("started_at_utc", "completed_at_utc"):
            value = evidence.get(field)
            if not isinstance(value, str):
                raise ReleaseError(f"command evidence 시각이 없습니다: {gate_id}:{field}")
            try:
                dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise ReleaseError(f"command evidence 시각이 ISO-8601이 아닙니다: {gate_id}:{field}") from error
        environment = evidence.get("environment")
        if (
            not isinstance(environment, dict)
            or set(environment) != {"os", "os_release", "machine", "python"}
            or any(not isinstance(value, str) or not value for value in environment.values())
        ):
            raise ReleaseError(f"command evidence 환경 field가 유효하지 않습니다: {gate_id}")
        if evidence.get("status") == "passed" and (exit_code != 0 or timed_out):
            raise ReleaseError(f"PASS command evidence의 종료 상태가 유효하지 않습니다: {gate_id}")
        if evidence.get("status") == "failed" and exit_code == 0 and not timed_out:
            raise ReleaseError(f"FAIL command evidence의 종료 상태가 유효하지 않습니다: {gate_id}")
        if gate_id == "hil_rc_pyocd":
            result_record = evidence.get("hil_result")
            required_result_fields = {
                "result_file_name",
                "result_sha256",
                "runtime_payload_sha256",
                "platform_tree_sha256",
                "sketch_sha256",
                "hex_sha256",
                "hex_size",
                "flash_log_sha256",
                "ready_token",
                "upload_attempts",
            }
            if not isinstance(result_record, dict) or set(result_record) != required_result_fields:
                raise ReleaseError("RC pyOCD command evidence에 HIL result identity가 없습니다.")
            result_path = plan_artifact_path(
                evidence_path, {"file_name": result_record["result_file_name"]}
            )
            if (
                not result_path.is_file()
                or result_record["result_sha256"] != file_sha256(result_path)
                or result_record != validate_rc_hil_result(result_path, plan)
            ):
                raise ReleaseError("RC pyOCD command evidence와 동결 HIL result가 다릅니다.")
        elif "hil_result" in evidence:
            raise ReleaseError(f"HIL이 아닌 command gate에 HIL result가 있습니다: {gate_id}")
    if evidence_type == "file-gate":
        files = evidence.get("files")
        roles = [item.get("role") for item in files if isinstance(item, dict)] if isinstance(files, list) else []
        if roles != list(REQUIRED_DOCUMENT_ROLES):
            raise ReleaseError("documentation file evidence의 필수 역할 목록이 불완전합니다.")
        repository = Path(__file__).resolve().parents[2]
        seen_paths: set[str] = set()
        for record in files:
            if not isinstance(record, dict) or set(record) != {"role", "path", "git_object", "sha256", "size"}:
                raise ReleaseError("documentation file evidence record가 유효하지 않습니다.")
            relative = record.get("path")
            if not isinstance(relative, str) or relative in seen_paths:
                raise ReleaseError("documentation file path가 없거나 중복되었습니다.")
            try:
                PACKAGE.ensure_safe_relative_path(relative)
            except PACKAGE.PackageError as error:
                raise ReleaseError(f"documentation file path가 안전하지 않습니다: {relative}") from error
            seen_paths.add(relative)
            committed = git_file_at_revision(repository, plan["core_revision"], relative)
            committed_object = git_output(
                repository, ["rev-parse", f"{plan['core_revision']}:{relative}"]
            ).strip()
            if (
                record.get("git_object") != committed_object
                or record.get("sha256") != hashlib.sha256(committed).hexdigest()
                or record.get("size") != len(committed)
            ):
                raise ReleaseError(f"documentation file evidence가 exact Git blob과 다릅니다: {relative}")
    if evidence_type == "imported-m10-gate":
        source = evidence.get("source")
        required_source_fields = {
            "milestone",
            "run_id",
            "target_evidence_file",
            "target_evidence_sha256",
            "orchestrator_evidence_file",
            "orchestrator_evidence_sha256",
            "safe_preview_versions",
            "safe_preview_index_url",
            "safe_preview_index_sha256",
            "target_runner_sha256",
            "safe_preview_archives",
            "m10_source_revision",
            "rc_source_revision",
            "runtime_payload_sha256",
            "allowed_followup_changes",
            "pyocd_upload_attempts",
        }
        if not isinstance(source, dict) or set(source) != required_source_fields:
            raise ReleaseError(f"가져온 M10 evidence 출처 구조가 유효하지 않습니다: {gate_id}")
        target_source = plan_artifact_path(
            evidence_path, {"file_name": source["target_evidence_file"]}
        )
        orchestrator_source = plan_artifact_path(
            evidence_path, {"file_name": source["orchestrator_evidence_file"]}
        )
        if not target_source.is_file() or not orchestrator_source.is_file():
            raise ReleaseError(f"가져온 M10 원본 evidence 파일이 없습니다: {gate_id}")
        validated_source = validate_m10_source_evidence(plan, target_source, orchestrator_source)
        expected_source = {
            "milestone": "M10",
            "run_id": validated_source["run_id"],
            "target_evidence_file": target_source.name,
            "target_evidence_sha256": validated_source["target_evidence_sha256"],
            "orchestrator_evidence_file": orchestrator_source.name,
            "orchestrator_evidence_sha256": validated_source["orchestrator_evidence_sha256"],
            "safe_preview_versions": [M10_SAFE_INITIAL_VERSION, M10_SAFE_LATEST_VERSION],
            "safe_preview_index_url": M10_PREVIEW_INDEX_URL,
            "safe_preview_index_sha256": validated_source["safe_preview_index_sha256"],
            "target_runner_sha256": validated_source["target_runner_sha256"],
            "safe_preview_archives": validated_source["safe_preview_archives"],
            "m10_source_revision": validated_source["m10_source_revision"],
            "rc_source_revision": validated_source["rc_source_revision"],
            "runtime_payload_sha256": validated_source["runtime_payload_sha256"],
            "allowed_followup_changes": validated_source["allowed_followup_changes"],
            "pyocd_upload_attempts": M11_PYOCD_UPLOAD_ATTEMPTS,
        }
        if source != expected_source:
            raise ReleaseError(f"가져온 M10 evidence가 동결 원본과 다릅니다: {gate_id}")
        expected_scope = {
            "boards_manager_backend": "arduino-cli-1.5.2-rc.1",
            "clean_windows_packages": [M10_SAFE_INITIAL_VERSION, M10_SAFE_LATEST_VERSION],
            "pyocd_upload_attempts": M11_PYOCD_UPLOAD_ATTEMPTS,
            "release_candidate_package_directly_installed": False,
            "arduino_ide_gui_validated": False,
            "arduino_ide_gui_pass_inferred": False,
        }
        if evidence.get("status") != "passed" or evidence.get("validation_scope") != expected_scope:
            raise ReleaseError(f"가져온 M10 gate 범위가 유효하지 않습니다: {gate_id}")
    log = evidence.get("log")
    if log is not None:
        if (
            not isinstance(log, dict)
            or set(log) != {"file_name", "sha256", "size", "redacted", "excerpt"}
            or log.get("redacted") is not True
            or not isinstance(log.get("size"), int)
            or isinstance(log.get("size"), bool)
            or log.get("size") < 0
            or log.get("size") > MAX_COMMAND_LOG_BYTES
            or not isinstance(log.get("excerpt"), str)
            or len(log.get("excerpt")) > LOG_EXCERPT_CHARS
            or log.get("excerpt") != redact_text(log["excerpt"])
        ):
            raise ReleaseError(f"gate log의 redaction 계약이 유효하지 않습니다: {gate_id}")
        log_path = plan_artifact_path(evidence_path, log)
        if not log_path.is_file() or log.get("size") != log_path.stat().st_size or log.get("sha256") != file_sha256(log_path):
            raise ReleaseError(f"gate log byte identity가 다릅니다: {gate_id}")
        try:
            log_text = log_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ReleaseError(f"gate log가 UTF-8이 아닙니다: {gate_id}") from error
        if log_text != redact_text(log_text):
            raise ReleaseError(f"gate log에 제거되지 않은 자격 증명 후보가 있습니다: {gate_id}")
    elif evidence_type == "command-gate":
        raise ReleaseError(f"command gate log가 누락되었습니다: {gate_id}")
    return evidence


## @brief 모든 M11 evidence를 결합하고 기술 준비 상태와 사람 승인 경계를 기록합니다.
def finalize_evidence(
    plan_path: Path, evidence_paths: Sequence[Path], output_path: Path
) -> tuple[dict[str, Any], bool]:
    plan_path = plan_path.resolve()
    plan = validate_plan(plan_path)
    by_gate: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in evidence_paths:
        resolved = path.resolve()
        evidence = validate_gate_evidence(plan_path, plan, resolved)
        gate_id = evidence["gate_id"]
        if gate_id in by_gate:
            raise ReleaseError(f"같은 gate evidence가 중복되었습니다: {gate_id}")
        by_gate[gate_id] = (resolved, evidence)
    missing = [gate for gate in REQUIRED_GATES if gate not in by_gate]
    failed = [gate for gate in REQUIRED_GATES if gate in by_gate and by_gate[gate][1]["status"] != "passed"]
    technical_ready = not missing and not failed
    gate_records = []
    for gate_id in (*REQUIRED_GATES, *OPTIONAL_GATES):
        if gate_id not in by_gate:
            gate_records.append({"gate_id": gate_id, "status": "missing", "required": gate_id in REQUIRED_GATES})
            continue
        path, evidence = by_gate[gate_id]
        gate_records.append(
            {
                "gate_id": gate_id,
                "status": evidence["status"],
                "required": gate_id in REQUIRED_GATES,
                "evidence_file": path.name,
                "evidence_sha256": file_sha256(path),
            }
        )
    final = {
        "schema_version": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "evidence_type": "release-candidate-evidence-manifest",
        "status": "ready-for-human-approval" if technical_ready else "hold",
        "technical_gates_passed": technical_ready,
        "plan_file": plan_path.name,
        "plan_sha256": file_sha256(plan_path),
        "release": release_binding(plan),
        "gates": gate_records,
        "missing_required_gates": missing,
        "failed_required_gates": failed,
        "human_approval_boundary": {
            "stable_version": "0.1.0",
            "stable_publication_allowed": False,
            "legal_review": "pending-human-approval",
            "final_release_approval": "pending-human-approval",
            "next_action": "사람 승인 후 별도 stable release 절차를 실행해야 함",
        },
        "validation_scope": {
            "boards_manager_backend": {
                "tool": "arduino-cli",
                "version": ARDUINO_CLI_VERSION,
                "commit": ARDUINO_CLI_COMMIT,
                "executable_sha256": ARDUINO_CLI_SHA256,
                "gate": "clean_windows",
                "clean_windows_packages": [
                    M10_SAFE_INITIAL_VERSION,
                    M10_SAFE_LATEST_VERSION,
                ],
                "pyocd_upload_attempts": M11_PYOCD_UPLOAD_ATTEMPTS,
                "release_candidate_pyocd_upload_attempts": M11_RC_PYOCD_UPLOAD_ATTEMPTS,
                "release_candidate_uart_ready_token": M11_READY_TOKEN,
                "release_candidate_direct_hil": True,
                "release_candidate_direct_clean_install": False,
            },
            "arduino_ide_gui": {
                "validated": False,
                "status": "not-independently-automated",
                "pass_inferred_from_backend": False,
            },
        },
        "known_issues": [
            {
                "id": "M11-ARDUINO-IDE-GUI-NOT-INDEPENDENTLY-VALIDATED",
                "severity": "documented-limitation",
                "description": "Arduino IDE GUI 조작 자체는 자동 검증하지 않았으며 Arduino CLI backend 결과만 기록함",
            },
            {
                "id": "M11-RC-CLEAN-WINDOWS-INHERITS-SAFE-PREVIEW",
                "severity": "documented-limitation",
                "description": "clean Windows 설치 lifecycle과 pyOCD 10회 내구 반복은 동일 runtime payload의 0.0.96/0.0.97에서 검증함. exact RC ZIP은 별도 1회 pyOCD+UART HIL 및 고정 package compile gate로 검증하지만 clean PC lifecycle 전체를 재실행한 것은 아님",
            }
        ],
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    atomic_write(output_path, canonical_json(final))
    return final, technical_ready


## @brief CLI 인자를 정의합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NU54DK M11 release candidate automation")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    prepare = subparsers.add_parser("prepare", help="깨끗한 exact commit에서 RC artifact와 plan을 만듭니다.")
    prepare.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--version", choices=M11_RELEASE_CANDIDATE_VERSIONS, required=True)
    prepare.add_argument("--commit", default="HEAD")

    validate = subparsers.add_parser("validate-plan", help="RC plan과 모든 artifact byte를 검증합니다.")
    validate.add_argument("--plan", type=Path, required=True)

    run_gate = subparsers.add_parser("run-gate", help="repo-owned 고정 M11 gate를 실행합니다.")
    run_gate.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    run_gate.add_argument("--plan", type=Path, required=True)
    run_gate.add_argument("--gate", choices=COMMAND_GATES, required=True)
    run_gate.add_argument("--output", type=Path, required=True)
    run_gate.add_argument("--timeout-seconds", type=int, default=3600)
    run_gate.add_argument("--arduino-cli", type=Path)
    run_gate.add_argument("--serial-port", default="auto")

    documents = subparsers.add_parser("record-docs", help="고정 commit의 문서 blob evidence를 만듭니다.")
    documents.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    documents.add_argument("--plan", type=Path, required=True)
    documents.add_argument("--output", type=Path, required=True)
    documents.add_argument(
        "--document",
        action="append",
        required=True,
        metavar="ROLE=PATH",
        help="필수 문서 역할과 exact commit 파일 경로를 지정합니다.",
    )

    import_m10 = subparsers.add_parser("import-m10", help="M10 clean Windows PASS를 RC gate로 가져옵니다.")
    import_m10.add_argument("--plan", type=Path, required=True)
    import_m10.add_argument("--target-evidence", type=Path, required=True)
    import_m10.add_argument("--orchestrator", type=Path, required=True)
    import_m10.add_argument("--output-dir", type=Path, required=True)

    finalize = subparsers.add_parser("finalize", help="gate evidence를 fail-closed 방식으로 결합합니다.")
    finalize.add_argument("--plan", type=Path, required=True)
    finalize.add_argument("--evidence", nargs="+", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    finalize.add_argument("--allow-incomplete", action="store_true")
    return parser


## @brief CLI 요청을 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    try:
        if parsed.command_name == "prepare":
            paths = prepare_rc(parsed.repo_root, parsed.output_dir, parsed.version, parsed.commit)
            for name, path in paths.items():
                print(f"NU54_M11_{name.upper()}={path}")
        elif parsed.command_name == "validate-plan":
            plan = validate_plan(parsed.plan)
            print(f"NU54_M11_PLAN_VALID={plan['version']}:{plan['core_revision']}")
        elif parsed.command_name == "run-gate":
            evidence, exit_code = run_command_gate(
                parsed.repo_root,
                parsed.plan,
                parsed.gate,
                parsed.output,
                parsed.timeout_seconds,
                parsed.arduino_cli,
                parsed.serial_port,
            )
            print(f"NU54_M11_GATE={parsed.gate}:{evidence['status']}:{parsed.output}")
            return 0 if evidence["status"] == "passed" else exit_code or 1
        elif parsed.command_name == "record-docs":
            document_map: dict[str, Path] = {}
            for item in parsed.document:
                if "=" not in item:
                    raise ReleaseError(f"--document는 ROLE=PATH 형식이어야 합니다: {item}")
                role, path = item.split("=", 1)
                if role in document_map or not path:
                    raise ReleaseError(f"중복되거나 빈 문서 역할입니다: {role}")
                document_map[role] = Path(path)
            record_documentation_gate(
                parsed.repo_root, parsed.plan, parsed.output, document_map
            )
            print(f"NU54_M11_GATE=documentation:passed:{parsed.output}")
        elif parsed.command_name == "import-m10":
            paths = import_m10_evidence(
                parsed.plan, parsed.target_evidence, parsed.output_dir, parsed.orchestrator
            )
            for gate_id, path in paths.items():
                print(f"NU54_M11_GATE={gate_id}:passed:{path}")
        elif parsed.command_name == "finalize":
            final, ready = finalize_evidence(parsed.plan, parsed.evidence, parsed.output)
            print(f"NU54_M11_STATUS={final['status']}:{parsed.output}")
            if not ready and not parsed.allow_incomplete:
                return 3
        return 0
    except ReleaseError as error:
        print(f"NU54_M11_ERROR={error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
