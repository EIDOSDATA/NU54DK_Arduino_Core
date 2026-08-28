#!/usr/bin/env python3
"""! @brief Arduino CLI M8 pyOCD/J-Link upload를 실제 NU54DK 전용 경로에서 반복 검증합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


FQBN = "nucode:zephyr:nu54dk"
M8_SKETCH_RELATIVE_PATH = "tests/arduino-cli/m8_upload/m8_upload.ino"
## @brief Build Adapter가 기록하는 artifact manifest의 현재 schema입니다.
ARTIFACT_MANIFEST_SCHEMA_VERSION = 2
## @brief Build Adapter가 artifact manifest에 포함하는 session context schema입니다.
SESSION_CONTEXT_SCHEMA_VERSION = 2
READY_TOKEN = b"NUCODE_M8_UPLOAD_READY"
DAPLINK_VID = 0x0D28
DAPLINK_PID = 0x0204
MAX_UART_TRANSCRIPT_BYTES = 64 * 1024
UART_AMBIGUITY_WINDOW_SECONDS = 1.0
RC_METADATA_FILES = (
    "release-manifest.json",
    "sbom.spdx.json",
    "license-inventory.json",
    "THIRD_PARTY_NOTICES.md",
    "CHECKSUMS.sha256",
)
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_FLASH_LOG_BYTES = 16 * 1024 * 1024
MAX_COMMAND_OUTPUT_BYTES = 32 * 1024 * 1024
COMMAND_TRUNCATION_MARKER = b"[NU54] command output truncated to final 32 MiB\n"
PROCESS_TERMINATION_GRACE_SECONDS = 5


class UploadHilFailure(RuntimeError):
    """! @brief M8 실제 upload 계약 위반을 나타냅니다. """


## @brief exact checkout의 Git blob byte를 line-ending 변환 없이 SHA-256으로 고정합니다.
def committed_file_sha256(repository: Path, relative_path: str) -> str:
    relative = ensure_safe_relative_path(relative_path)
    try:
        result = subprocess.run(
            ("git", "-C", str(repository.resolve()), "show", f"HEAD:{relative}"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise UploadHilFailure(f"M8 fixture Git blob을 읽지 못했습니다: {error}") from error
    if result.returncode != 0 or not result.stdout:
        raise UploadHilFailure("M8 fixture Git blob이 exact checkout에 없습니다.")
    return hashlib.sha256(result.stdout).hexdigest()


## @brief Arduino IDE에 포함된 CLI 기본 경로를 반환합니다.
def default_cli() -> Path:
    return Path("C:/Program Files/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe")


## @brief UTF-8 경계를 보존하며 command capture의 제한된 마지막 출력만 읽습니다.
def bounded_command_output(capture: Any) -> bytes:
    if MAX_COMMAND_OUTPUT_BYTES <= len(COMMAND_TRUNCATION_MARKER):
        raise UploadHilFailure("command output byte 제한이 marker보다 작습니다.")
    capture.flush()
    captured_size = capture.seek(0, os.SEEK_END)
    capture.seek(max(0, captured_size - MAX_COMMAND_OUTPUT_BYTES), os.SEEK_SET)
    tail = capture.read(MAX_COMMAND_OUTPUT_BYTES)
    safe_output = tail.decode("utf-8", "replace").encode("utf-8")
    if captured_size <= len(tail) and len(safe_output) <= MAX_COMMAND_OUTPUT_BYTES:
        return safe_output
    budget = MAX_COMMAND_OUTPUT_BYTES - len(COMMAND_TRUNCATION_MARKER)
    safe_tail = safe_output[-budget:].decode("utf-8", "ignore").encode("utf-8")
    return COMMAND_TRUNCATION_MARKER + safe_tail


## @brief timeout된 command의 Windows tree 또는 POSIX process group을 종료합니다.
def terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        taskkill = Path(system_root) / "System32" / "taskkill.exe"
        executable = str(taskkill) if taskkill.is_file() else "taskkill.exe"
        try:
            subprocess.run(
                [executable, "/PID", str(process.pid), "/T", "/F"],
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
        raise UploadHilFailure("timeout된 HIL command process tree를 종료하지 못했습니다.") from error


## @brief 명령 출력을 disk에 spool하고 제한된 tail 및 종료 code를 반환합니다.
def run(
    command: Sequence[str | Path], *, timeout_seconds: int = 3600
) -> tuple[int, str, float]:
    if timeout_seconds < 1 or timeout_seconds > 86400:
        raise UploadHilFailure("HIL command timeout은 1..86400초여야 합니다.")
    started = time.monotonic()
    normalized = [str(value) for value in command]
    with tempfile.TemporaryFile(prefix="nu54-m11-hil-command-", mode="w+b") as capture:
        try:
            process_options: dict[str, Any] = {}
            if os.name == "nt":
                process_options["creationflags"] = getattr(
                    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                )
            else:
                process_options["start_new_session"] = True
            process = subprocess.Popen(
                normalized,
                stdout=capture,
                stderr=subprocess.STDOUT,
                **process_options,
            )
            try:
                return_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                return_code = 124
                terminate_process_tree(process)
        except OSError as error:
            return_code = 127
            capture.write(str(error).encode("utf-8", "replace"))
        output_bytes = bounded_command_output(capture)
    elapsed = time.monotonic() - started
    output = output_bytes.decode("utf-8")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    return return_code, output, elapsed


## @brief repository를 격리된 Arduino hardware package로 복사합니다.
def stage_platform(repository: Path, user_root: Path) -> Path:
    platform = user_root / "hardware" / "nucode" / "zephyr"
    platform.mkdir(parents=True)
    for name in ("boards.txt", "platform.txt", "LICENSE"):
        shutil.copy2(repository / name, platform / name)
    for name in (
        "board_package",
        "cores",
        "dts",
        "libraries",
        "third_party",
        "tools",
        "variants",
        "zephyr",
    ):
        shutil.copytree(
            repository / name,
            platform / name,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
    return platform


## @brief 파일 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief package version을 sentinel로 치환해 runtime payload byte를 정규화합니다.
def normalize_runtime_payload_bytes(path: str, data: bytes) -> bytes:
    if path != "platform.txt":
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise UploadHilFailure("RC platform.txt가 UTF-8이 아닙니다.") from error
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith("version=")]
    if len(matches) != 1:
        raise UploadHilFailure("RC platform.txt에는 version= 항목이 정확히 하나 있어야 합니다.")
    index = matches[0]
    ending = (
        "\r\n"
        if lines[index].endswith("\r\n")
        else "\n"
        if lines[index].endswith("\n")
        else ""
    )
    lines[index] = f"version=@NU54_PACKAGE_VERSION@{ending}"
    return "".join(lines).encode("utf-8")


## @brief 검증된 payload record로 version 독립 runtime SHA-256을 계산합니다.
def runtime_payload_fingerprint(records: Iterable[tuple[str, bytes, str]]) -> str:
    normalized_records: list[dict[str, Any]] = []
    previous_path: bytes | None = None
    for path, data, mode in records:
        path_key = path.encode("utf-8")
        if previous_path is not None and path_key <= previous_path:
            raise UploadHilFailure("RC runtime payload record 순서가 결정적이지 않습니다.")
        previous_path = path_key
        normalized = normalize_runtime_payload_bytes(path, data)
        normalized_records.append(
            {
                "mode": mode,
                "path": path,
                "sha256": hashlib.sha256(normalized).hexdigest(),
                "size": len(normalized),
            }
        )
    canonical = (
        json.dumps(
            {
                "normalization": "platform-version-sentinel-v1",
                "records": normalized_records,
                "schema_version": 1,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


## @brief JSON evidence를 같은 directory의 임시 파일에서 원자 교체합니다.
def write_json_evidence(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    content = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


## @brief 중복 key와 과도한 크기를 거부하며 UTF-8 JSON object를 읽습니다.
def strict_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise UploadHilFailure(f"JSON 파일이 없거나 허용 크기를 초과합니다: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise UploadHilFailure(f"UTF-8 JSON을 읽지 못했습니다: {path}: {error}") from error

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise UploadHilFailure(f"JSON key가 중복됩니다: {path}: {key}")
            document[key] = value
        return document

    try:
        document = json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as error:
        raise UploadHilFailure(f"JSON 형식이 올바르지 않습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise UploadHilFailure(f"JSON 최상위 값이 object가 아닙니다: {path}")
    return document


## @brief Windows와 POSIX에서 모두 안전한 package 상대 경로인지 확인합니다.
def ensure_safe_relative_path(value: str) -> str:
    if (
        not value
        or "\\" in value
        or ":" in value
        or "\0" in value
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise UploadHilFailure(f"안전하지 않은 package 상대 경로입니다: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise UploadHilFailure(f"안전하지 않은 package 상대 경로입니다: {value!r}")
    normalized = pure.as_posix()
    if normalized != value:
        raise UploadHilFailure(f"정규화되지 않은 package 상대 경로입니다: {value!r}")
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
    for part in pure.parts:
        stem = part.split(".", 1)[0].casefold()
        if part.endswith((" ", ".")) or stem in reserved:
            raise UploadHilFailure(f"Windows에서 안전하지 않은 package 경로입니다: {value!r}")
    return normalized


## @brief symlink·junction·root 이탈 없이 platform의 일반 파일을 열거합니다.
def enumerate_platform_files(platform_root: Path) -> dict[str, Path]:
    root = platform_root.resolve()
    if not root.is_dir() or platform_root.is_symlink():
        raise UploadHilFailure(f"RC platform root가 일반 directory가 아닙니다: {platform_root}")
    is_junction = getattr(platform_root, "is_junction", lambda: False)
    if is_junction():
        raise UploadHilFailure(f"RC platform root junction은 허용하지 않습니다: {platform_root}")
    files: dict[str, Path] = {}
    casefold_paths: set[str] = set()
    for path in root.rglob("*"):
        path_is_junction = getattr(path, "is_junction", lambda: False)
        if path.is_symlink() or path_is_junction():
            raise UploadHilFailure(f"RC platform에 link 또는 junction이 있습니다: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise UploadHilFailure(f"RC platform에 일반 파일이 아닌 항목이 있습니다: {path}")
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise UploadHilFailure(f"RC platform file이 root 밖을 가리킵니다: {path}")
        relative = ensure_safe_relative_path(path.relative_to(root).as_posix())
        if relative in files or relative.casefold() in casefold_paths:
            raise UploadHilFailure(f"RC platform 경로가 중복되거나 대소문자 충돌합니다: {relative}")
        files[relative] = path
        casefold_paths.add(relative.casefold())
    return files


## @brief CHECKSUMS.sha256의 엄격한 path·digest mapping을 읽습니다.
def parse_checksums(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise UploadHilFailure(f"RC checksum 목록을 읽지 못했습니다: {error}") from error
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if match is None:
            raise UploadHilFailure(f"RC checksum record 형식이 올바르지 않습니다: {line!r}")
        digest, relative = match.groups()
        relative = ensure_safe_relative_path(relative)
        if relative in checksums:
            raise UploadHilFailure(f"RC checksum 경로가 중복됩니다: {relative}")
        checksums[relative] = digest
    return checksums


## @brief 해제된 RC platform의 manifest, payload와 checksum을 exact identity로 검증합니다.
def validate_rc_platform(
    platform_root: Path,
    expected_version: str,
    expected_core_revision: str,
    expected_runtime_payload_sha256: str,
    *,
    require_archive_root_name: bool = True,
) -> dict[str, Any]:
    if not re.fullmatch(r"\d+\.\d+\.\d+-rc\.\d+", expected_version):
        raise UploadHilFailure("RC version 형식이 올바르지 않습니다.")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_core_revision):
        raise UploadHilFailure("RC core revision은 full Git commit이어야 합니다.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_runtime_payload_sha256):
        raise UploadHilFailure("RC runtime payload SHA-256이 올바르지 않습니다.")
    root = platform_root.resolve()
    files = enumerate_platform_files(platform_root)
    if ".git" in files or (root / ".git").exists():
        raise UploadHilFailure("해제된 RC platform에 .git 항목이 있습니다.")
    missing_metadata = sorted(set(RC_METADATA_FILES).difference(files))
    if missing_metadata:
        raise UploadHilFailure(f"RC platform metadata가 없습니다: {', '.join(missing_metadata)}")
    manifest_path = files["release-manifest.json"]
    manifest = strict_json_object(manifest_path)
    expected_root_name = f"nucode-nu54dk-zephyr-{expected_version}"
    if (
        manifest.get("schema_version") != 1
        or manifest.get("version") != expected_version
        or manifest.get("core_revision") != expected_core_revision
        or manifest.get("runtime_payload_sha256") != expected_runtime_payload_sha256
        or manifest.get("archive_root") != expected_root_name
        or (require_archive_root_name and root.name != expected_root_name)
        or manifest.get("generated_metadata") != list(RC_METADATA_FILES)
    ):
        raise UploadHilFailure("RC platform release manifest identity가 예상값과 다릅니다.")
    board_revision = manifest.get("board_revision")
    if not isinstance(board_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", board_revision):
        raise UploadHilFailure("RC platform board revision이 유효하지 않습니다.")

    records = manifest.get("files")
    file_hashes = manifest.get("file_hashes")
    if not isinstance(records, list) or not isinstance(file_hashes, dict):
        raise UploadHilFailure("RC platform payload manifest 구조가 유효하지 않습니다.")
    record_paths: list[str] = []
    total_size = 0
    for record in records:
        required = {"git_object", "mode", "origin", "path", "sha256", "size"}
        if (
            not isinstance(record, dict)
            or not required.issubset(record)
            or set(record).difference(required | {"transformation"})
            or not isinstance(record.get("path"), str)
        ):
            raise UploadHilFailure("RC platform payload record 구조가 유효하지 않습니다.")
        relative = ensure_safe_relative_path(str(record.get("path", "")))
        if relative in record_paths:
            raise UploadHilFailure(f"RC platform payload 경로가 중복됩니다: {relative}")
        digest = record.get("sha256")
        size = record.get("size")
        if (
            relative not in files
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or file_hashes.get(relative) != digest
            or record.get("origin") not in {"core", "board"}
            or not isinstance(record.get("mode"), str)
            or not re.fullmatch(r"0(?:644|755)", record["mode"])
            or not isinstance(record.get("git_object"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", record["git_object"])
            or (
                "transformation" in record
                and record.get("transformation") not in {"platform-version", "windows-crlf"}
            )
        ):
            raise UploadHilFailure(f"RC platform payload identity가 유효하지 않습니다: {relative}")
        if files[relative].stat().st_size != size or file_sha256(files[relative]) != digest:
            raise UploadHilFailure(f"RC platform payload byte가 manifest와 다릅니다: {relative}")
        record_paths.append(relative)
        total_size += size
    if record_paths != sorted(record_paths, key=lambda item: item.encode("utf-8")):
        raise UploadHilFailure("RC platform payload record가 결정적 경로 순서가 아닙니다.")
    if list(file_hashes) != record_paths:
        raise UploadHilFailure("RC platform file_hashes 경로 집합 또는 순서가 payload와 다릅니다.")
    if manifest.get("file_count") != len(records) or manifest.get("total_size") != total_size:
        raise UploadHilFailure("RC platform payload 개수 또는 전체 크기가 manifest와 다릅니다.")
    if set(files) != set(record_paths) | set(RC_METADATA_FILES):
        raise UploadHilFailure("RC platform에 manifest 허용목록 밖의 파일이 있습니다.")
    payload_fingerprint = runtime_payload_fingerprint(
        (
            (record["path"], files[record["path"]].read_bytes(), record["mode"])
            for record in records
        )
    )
    if payload_fingerprint != expected_runtime_payload_sha256:
        raise UploadHilFailure("RC runtime payload SHA-256이 실제 payload byte와 다릅니다.")
    expected_directories: set[str] = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    actual_directories = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    }
    if actual_directories != expected_directories:
        raise UploadHilFailure("RC platform directory 집합이 file manifest에서 파생되지 않았습니다.")

    checksums = parse_checksums(files["CHECKSUMS.sha256"])
    checksum_paths = sorted(
        set(files).difference({"CHECKSUMS.sha256"}), key=lambda item: item.encode("utf-8")
    )
    if list(checksums) != checksum_paths:
        raise UploadHilFailure("RC checksum 경로 집합 또는 순서가 platform과 다릅니다.")
    for relative in checksum_paths:
        if checksums[relative] != file_sha256(files[relative]):
            raise UploadHilFailure(f"RC checksum이 실제 file과 다릅니다: {relative}")

    tree_digest = hashlib.sha256()
    for relative in sorted(files, key=lambda item: item.encode("utf-8")):
        tree_digest.update(relative.encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(bytes.fromhex(file_sha256(files[relative])))
    return {
        "version": expected_version,
        "core_revision": expected_core_revision,
        "runtime_payload_sha256": expected_runtime_payload_sha256,
        "board_revision": board_revision,
        "release_manifest_sha256": file_sha256(manifest_path),
        "platform_tree_sha256": tree_digest.hexdigest(),
        "file_count": len(files),
    }


## @brief 검증된 RC platform을 byte 변경 없이 격리된 Arduino hardware 경로에 복사합니다.
def stage_rc_platform(
    package_root: Path,
    user_root: Path,
    expected_version: str,
    expected_core_revision: str,
    expected_runtime_payload_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    source_identity = validate_rc_platform(
        package_root,
        expected_version,
        expected_core_revision,
        expected_runtime_payload_sha256,
    )
    platform = user_root / "hardware" / "nucode" / "zephyr"
    platform.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_root.resolve(), platform)
    staged_identity = validate_rc_platform(
        platform,
        expected_version,
        expected_core_revision,
        expected_runtime_payload_sha256,
        require_archive_root_name=False,
    )
    if staged_identity != source_identity:
        raise UploadHilFailure("격리 경로에 복사된 RC platform byte identity가 원본과 다릅니다.")
    return platform, staged_identity


## @brief build manifest의 platform·sketch·HEX identity를 RC compile 입력에 묶습니다.
def validate_build_manifest(
    manifest_path: Path,
    build_path: Path,
    platform_root: Path,
    sketch_root: Path,
    runner: str,
) -> dict[str, Any]:
    if manifest_path.is_symlink():
        raise UploadHilFailure("M8 build manifest symlink는 허용하지 않습니다.")
    manifest = strict_json_object(manifest_path)
    expected_fqbn = f"{FQBN}:upload_probe={runner}"
    context = manifest.get("context")
    artifacts = manifest.get("artifacts")
    if (
        manifest.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION
        or manifest.get("fqbn") != expected_fqbn
        or manifest.get("sysbuild") is not False
        or not isinstance(context, dict)
        or not isinstance(artifacts, dict)
    ):
        raise UploadHilFailure("M8 build manifest 기본 계약이 유효하지 않습니다.")
    if (
        context.get("schema_version") != SESSION_CONTEXT_SCHEMA_VERSION
        or context.get("state") != "built"
        or context.get("fqbn") != expected_fqbn
    ):
        raise UploadHilFailure("M8 build context의 schema 또는 완료 상태가 유효하지 않습니다.")
    expected_paths = {
        "build_path": build_path.resolve(),
        "platform_root": platform_root.resolve(),
        "sketch_root": sketch_root.resolve(),
    }
    for field, expected in expected_paths.items():
        value = context.get(field)
        if (
            not isinstance(value, str)
            or not Path(value).is_absolute()
            or Path(value).resolve() != expected
        ):
            raise UploadHilFailure(f"M8 build context의 {field}가 exact 입력과 다릅니다.")
    zephyr_build_value = context.get("zephyr_build_dir")
    if not isinstance(zephyr_build_value, str) or not Path(zephyr_build_value).is_absolute():
        raise UploadHilFailure("M8 build context의 Zephyr build 경로가 유효하지 않습니다.")
    zephyr_build = Path(zephyr_build_value).resolve()
    if zephyr_build.is_symlink() or not zephyr_build.is_dir():
        raise UploadHilFailure("M8 build context의 Zephyr build directory가 없습니다.")
    hex_record = artifacts.get("hex")
    if not isinstance(hex_record, dict):
        raise UploadHilFailure("M8 build manifest에 HEX artifact가 없습니다.")
    hex_value = hex_record.get("path")
    hex_digest = hex_record.get("sha256")
    hex_size = hex_record.get("size")
    if (
        not isinstance(hex_value, str)
        or not isinstance(hex_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", hex_digest)
        or not isinstance(hex_size, int)
        or isinstance(hex_size, bool)
        or hex_size < 1
    ):
        raise UploadHilFailure("M8 HEX artifact record가 유효하지 않습니다.")
    hex_path = Path(hex_value)
    if not hex_path.is_absolute() or hex_path.is_symlink() or not hex_path.is_file():
        raise UploadHilFailure("M8 HEX artifact가 일반 파일이 아닙니다.")
    resolved_hex = hex_path.resolve()
    if not resolved_hex.is_relative_to(build_path.resolve()):
        raise UploadHilFailure("M8 HEX artifact path가 build directory 밖을 가리킵니다.")
    if resolved_hex.stat().st_size != hex_size or file_sha256(resolved_hex) != hex_digest:
        raise UploadHilFailure("M8 HEX artifact byte가 build manifest와 다릅니다.")
    return {
        "manifest": manifest,
        "manifest_sha256": file_sha256(manifest_path),
        "hex": resolved_hex,
        "hex_sha256": hex_digest,
        "hex_size": hex_size,
        "zephyr_build": zephyr_build,
    }


## @brief 한 번의 pyOCD upload log가 비파괴 runner와 exact HEX를 사용했는지 검증합니다.
def validate_pyocd_flash_log(
    log_path: Path,
    expected_hex_sha256: str,
    expected_hex_path: Path,
    expected_zephyr_build: Path,
) -> dict[str, Any]:
    if (
        log_path.is_symlink()
        or not log_path.is_file()
        or log_path.stat().st_size < 1
        or log_path.stat().st_size > MAX_FLASH_LOG_BYTES
    ):
        raise UploadHilFailure("pyOCD flash log가 없거나 허용 크기를 초과합니다.")
    try:
        text = log_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise UploadHilFailure(f"pyOCD flash log를 읽지 못했습니다: {error}") from error
    command_lines = [line for line in text.splitlines() if line.startswith("command=")]
    log_lines = text.splitlines()
    probe_lines = [line for line in log_lines if line.startswith("probe_id=")]
    required_lines = {
        "runner=pyocd",
        f"hex={expected_hex_path.resolve().as_posix()}",
        f"hex_sha256={expected_hex_sha256}",
        "smart_flash=false",
        "mass_erase_requested=false",
        "recover_requested=false",
        "exit_code=0",
    }
    if (
        text.count("started_at_utc=") != 1
        or len(command_lines) != 1
        or len(probe_lines) != 1
        or not probe_lines[0].removeprefix("probe_id=").strip()
    ):
        raise UploadHilFailure("RC HIL에는 정확히 한 번의 pyOCD flash 기록이 필요합니다.")
    if any(log_lines.count(line) != 1 for line in required_lines):
        raise UploadHilFailure("pyOCD flash log의 runner·HEX·비파괴 계약이 유효하지 않습니다.")
    command = command_lines[0].removeprefix("command=")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as error:
        raise UploadHilFailure("pyOCD flash command quoting이 올바르지 않습니다.") from error
    runner_pairs = sum(
        1
        for index in range(len(tokens) - 1)
        if tokens[index : index + 2] == ["-r", "pyocd"]
    )
    probe_options = [index for index, token in enumerate(tokens) if token == "--dev-id"]
    build_options = [index for index, token in enumerate(tokens) if token == "-d"]
    expected_build = expected_zephyr_build.resolve()
    probe_id = probe_lines[0].removeprefix("probe_id=")
    if (
        tokens.count("flash") != 1
        or runner_pairs != 1
        or tokens.count("--no-rebuild") != 1
        or tokens.count("--tool-opt=-Osmart_flash=false") != 1
        or len(probe_options) != 1
        or probe_options[0] + 1 >= len(tokens)
        or tokens[probe_options[0] + 1] != probe_id
        or len(build_options) != 1
        or build_options[0] + 1 >= len(tokens)
        or Path(tokens[build_options[0] + 1]).resolve() != expected_build
        or any(re.fullmatch(r"(?i)--(?:erase|recover)(?:=.*)?", token) for token in tokens)
    ):
        raise UploadHilFailure("pyOCD flash command에 필수 안전 option이 없거나 파괴 option이 있습니다.")
    return {
        "runner": "pyocd",
        "attempts": 1,
        "smart_flash": False,
        "mass_erase_requested": False,
        "recover_requested": False,
        "flash_log_sha256": file_sha256(log_path),
    }


## @brief NCS Toolchain의 pySerial 본체와 포트 탐색 모듈을 불러옵니다.
def import_pyserial() -> tuple[Any, Any]:
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise UploadHilFailure("pyserial이 없어 UART reset 표식을 확인할 수 없습니다.") from error
    return serial, list_ports


## @brief UART transcript를 제한 크기의 최근 byte로 유지합니다.
def append_transcript(transcript: bytearray, block: bytes) -> None:
    transcript.extend(block)
    excess = len(transcript) - MAX_UART_TRANSCRIPT_BYTES
    if excess > 0:
        del transcript[:excess]


## @brief reset 후 명시된 NU54DK UART에서 고정 생존 표식을 기다립니다.
def wait_for_ready(port: str, timeout_seconds: float) -> bytes:
    serial, _ = import_pyserial()
    deadline = time.monotonic() + timeout_seconds
    transcript = bytearray()
    with serial.Serial(port=port, baudrate=115200, timeout=0.25) as stream:
        stream.reset_input_buffer()
        while time.monotonic() < deadline:
            block = stream.read(512)
            if block:
                append_transcript(transcript, block)
                if READY_TOKEN in transcript:
                    return bytes(transcript)
    raise UploadHilFailure(
        f"{port}에서 upload 후 reset 표식을 받지 못했습니다: {bytes(transcript)!r}"
    )


## @brief DAPLink VID/PID의 모든 UART를 동시에 열어 READY token의 유일한 port를 찾습니다.
def wait_for_ready_auto(timeout_seconds: float) -> tuple[bytes, int]:
    serial, list_ports = import_pyserial()
    candidates = sorted(
        [
            port
            for port in list_ports.comports()
            if port.vid == DAPLINK_VID and port.pid == DAPLINK_PID
        ],
        key=lambda port: str(port.device).casefold(),
    )
    if not candidates:
        raise UploadHilFailure("DAPLink VID:PID 0D28:0204 UART 후보가 없습니다.")
    devices = [str(candidate.device) for candidate in candidates]
    if len({device.casefold() for device in devices}) != len(devices):
        raise UploadHilFailure("DAPLink UART 후보 이름이 중복되거나 대소문자 충돌합니다.")
    streams: list[tuple[str, Any]] = []
    try:
        for candidate in candidates:
            try:
                stream = serial.Serial(
                    port=str(candidate.device), baudrate=115200, timeout=0
                )
            except Exception as error:
                raise UploadHilFailure(
                    "DAPLink UART 후보를 모두 동시에 점유하지 못했습니다. "
                    f"다른 프로그램의 port 사용을 해제하세요: {candidate.device}"
                ) from error
            streams.append((str(candidate.device), stream))
        for _, stream in streams:
            try:
                stream.reset_input_buffer()
            except Exception as error:
                raise UploadHilFailure("DAPLink UART 입력 buffer 초기화에 실패했습니다.") from error

        transcripts = {device: bytearray() for device, _ in streams}
        matches: set[str] = set()
        deadline = time.monotonic() + timeout_seconds
        ambiguity_deadline: float | None = None
        while time.monotonic() < deadline:
            for device, stream in streams:
                try:
                    waiting = int(getattr(stream, "in_waiting", 0))
                    block = stream.read(waiting if waiting > 0 else 1)
                except Exception as error:
                    raise UploadHilFailure("DAPLink UART READY 수신 중 I/O 오류가 발생했습니다.") from error
                if block:
                    append_transcript(transcripts[device], block)
                    if READY_TOKEN in transcripts[device]:
                        matches.add(device)
            if len(matches) > 1:
                raise UploadHilFailure("둘 이상의 DAPLink UART에서 READY token이 검출되었습니다.")
            if matches and ambiguity_deadline is None:
                ambiguity_deadline = min(
                    deadline, time.monotonic() + UART_AMBIGUITY_WINDOW_SECONDS
                )
            if ambiguity_deadline is not None and time.monotonic() >= ambiguity_deadline:
                break
            time.sleep(0.01)
        if len(matches) != 1:
            raise UploadHilFailure(
                "DAPLink UART 후보 중 READY token을 보낸 port를 하나로 결정하지 못했습니다."
            )
        selected = next(iter(matches))
        return bytes(transcripts[selected]), len(candidates)
    finally:
        for _, stream in streams:
            try:
                stream.close()
            except Exception:
                pass


## @brief 명시 port 또는 자동 다중 port 판별로 UART READY evidence를 수집합니다.
def collect_ready_evidence(port: str, timeout_seconds: float) -> tuple[bytes, dict[str, Any]]:
    if port.casefold() == "auto":
        transcript, candidate_count = wait_for_ready_auto(timeout_seconds)
        return transcript, {
            "selection": "auto-daplink-token",
            "candidate_count": candidate_count,
            "ready_match_count": 1,
        }
    transcript = wait_for_ready(port, timeout_seconds)
    return transcript, {
        "selection": "explicit",
        "candidate_count": 1,
        "ready_match_count": 1,
    }


## @brief 실행 인자를 구성합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=default_cli())
    parser.add_argument("--repository", type=Path, default=repository)
    parser.add_argument("--workspace", type=Path, default=repository / "build" / "m8-upload-hil")
    parser.add_argument("--runner", choices=("pyocd", "jlink"), default="pyocd")
    parser.add_argument("--probe-id")
    parser.add_argument("--serial-port", default="auto")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--rc-platform-root", type=Path)
    parser.add_argument(
        "--expected-version", default=os.environ.get("NU54_RELEASE_VERSION", "")
    )
    parser.add_argument(
        "--expected-core-revision",
        default=os.environ.get("NU54_RELEASE_CORE_REVISION", ""),
    )
    parser.add_argument(
        "--expected-runtime-payload-sha256",
        default=os.environ.get("NU54_RELEASE_RUNTIME_PAYLOAD_SHA256", ""),
    )
    parser.add_argument("--uart-timeout", type=float, default=6.0)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--compile-timeout", type=int, default=3600)
    parser.add_argument("--upload-timeout", type=int, default=600)
    parser.add_argument("--uart-each", action="store_true")
    parsed = parser.parse_args(arguments)
    if parsed.repetitions is None:
        parsed.repetitions = 1 if parsed.rc_platform_root is not None else 10
    return parsed


## @brief Arduino CLI build와 실제 반복 upload HIL을 수행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.repetitions < 1:
        raise UploadHilFailure("반복 횟수는 1 이상이어야 합니다.")
    if (
        args.uart_timeout <= 0.0
        or args.settle_seconds < 0.0
        or not 1 <= args.compile_timeout <= 86400
        or not 1 <= args.upload_timeout <= 86400
    ):
        raise UploadHilFailure("UART timeout과 upload 정착 시간 범위가 올바르지 않습니다.")
    rc_mode = args.rc_platform_root is not None
    if rc_mode and (
        args.runner != "pyocd"
        or args.repetitions != 1
        or bool((args.probe_id or "").strip())
    ):
        raise UploadHilFailure(
            "RC exact HIL은 probe 자동 단일 선택의 pyOCD upload 정확히 1회만 허용합니다."
        )
    if args.runner == "jlink" and not (args.probe_id or "").strip():
        raise UploadHilFailure("J-Link HIL에는 --probe-id serial이 필요합니다.")
    repository = args.repository.resolve()
    cli = args.cli.resolve()
    sketch_file = repository / Path(PurePosixPath(M8_SKETCH_RELATIVE_PATH))
    sketch = sketch_file.parent
    if (
        not cli.is_file()
        or not sketch_file.is_file()
        or sketch_file.is_symlink()
        or not sketch.resolve().is_relative_to(repository)
    ):
        raise UploadHilFailure("Arduino CLI 또는 M8 upload sketch를 찾지 못했습니다.")

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
    run_root = args.workspace.resolve() / timestamp
    user_root = run_root / "user"
    build_path = run_root / "build"
    run_root.mkdir(parents=True)
    release_identity: dict[str, Any] | None = None
    if rc_mode:
        _, release_identity = stage_rc_platform(
            args.rc_platform_root,
            user_root,
            str(args.expected_version),
            str(args.expected_core_revision),
            str(args.expected_runtime_payload_sha256),
        )
    else:
        stage_platform(repository, user_root)
    platform_root = user_root / "hardware" / "nucode" / "zephyr"
    config = run_root / "arduino-cli.yaml"
    config.write_text(f"directories:\n  user: {user_root.as_posix()}\n", encoding="utf-8")

    compile_command: list[str | Path] = [
        cli,
        "compile",
        "--fqbn",
        FQBN,
        "--config-file",
        config,
        "--build-path",
        build_path,
        "--board-options",
        f"upload_probe={args.runner}",
        sketch,
    ]
    return_code, _, compile_seconds = run(
        compile_command, timeout_seconds=args.compile_timeout
    )
    if return_code != 0:
        raise UploadHilFailure(f"Arduino CLI compile이 종료 코드 {return_code}로 실패했습니다.")

    manifest_path = build_path / "m8_upload.ino.nu54-build.json"
    build_identity = validate_build_manifest(
        manifest_path, build_path, platform_root, sketch, args.runner
    )
    hex_path = build_identity["hex"]
    hex_sha256 = build_identity["hex_sha256"]
    upload_results: list[dict[str, object]] = []
    final_uart_evidence: dict[str, Any] | None = None
    for sequence in range(1, args.repetitions + 1):
        if file_sha256(hex_path) != hex_sha256:
            raise UploadHilFailure("upload 직전 HEX byte가 compile manifest에서 변경되었습니다.")
        upload_command: list[str | Path] = [
            cli,
            "upload",
            "--fqbn",
            FQBN,
            "--config-file",
            config,
            "--build-path",
            build_path,
            "--board-options",
            f"upload_probe={args.runner}",
        ]
        if args.runner == "jlink":
            upload_command.extend(("--upload-field", f"probe_id={args.probe_id}"))
        upload_command.append(sketch)
        print(f"NUCODE_M8_UPLOAD_ATTEMPT:{sequence}/{args.repetitions}")
        return_code, output, upload_seconds = run(
            upload_command, timeout_seconds=args.upload_timeout
        )
        pass_marker = f"NU54_UPLOAD_PASS runner={args.runner}"
        if return_code != 0 or pass_marker not in output:
            raise UploadHilFailure(
                f"Arduino CLI upload {sequence}회차가 종료 코드 {return_code}로 실패했습니다."
            )
        verify_uart = args.uart_each or sequence == args.repetitions
        transcript = b""
        uart_selection: dict[str, Any] | None = None
        if verify_uart:
            transcript, uart_selection = collect_ready_evidence(
                args.serial_port, args.uart_timeout
            )
            final_uart_evidence = {
                **uart_selection,
                "token": READY_TOKEN.decode("ascii"),
                "ready": READY_TOKEN in transcript,
                "transcript_bytes": len(transcript),
                "transcript_sha256": hashlib.sha256(transcript).hexdigest(),
                "timeout_seconds": args.uart_timeout,
            }
        upload_results.append(
            {
                "sequence": sequence,
                "upload_seconds": round(upload_seconds, 3),
                "uart_checked": verify_uart,
                "uart_ready": READY_TOKEN in transcript if verify_uart else None,
            }
        )
        print(f"NUCODE_M8_UPLOAD_ATTEMPT_PASS:{sequence}/{args.repetitions}")
        if sequence != args.repetitions and args.settle_seconds > 0.0:
            time.sleep(args.settle_seconds)

    if file_sha256(hex_path) != hex_sha256:
        raise UploadHilFailure("upload 후 HEX byte가 compile manifest에서 변경되었습니다.")
    completed_at_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    if rc_mode:
        if release_identity is None or final_uart_evidence is None:
            raise UploadHilFailure("RC HIL release 또는 UART evidence가 완성되지 않았습니다.")
        flash_identity = validate_pyocd_flash_log(
            build_path / "nu54-zephyr" / "logs" / "flash.log",
            hex_sha256,
            hex_path,
            build_identity["zephyr_build"],
        )
        summary = {
            "schema_version": 1,
            "milestone": "M11",
            "evidence_type": "rc-pyocd-hil",
            "status": "passed",
            "release": release_identity,
            "platform": {
                "mode": "validated-extracted-rc",
                "staged_byte_exact": True,
            },
            "sketch": {
                "repository_relative_path": M8_SKETCH_RELATIVE_PATH,
                "sha256": committed_file_sha256(
                    repository, M8_SKETCH_RELATIVE_PATH
                ),
            },
            "arduino_cli": {"sha256": file_sha256(cli)},
            "build": {
                "fqbn": f"{FQBN}:upload_probe=pyocd",
                "compile_seconds": round(compile_seconds, 3),
                "manifest_sha256": build_identity["manifest_sha256"],
                "hex_file_name": hex_path.name,
                "hex_sha256": hex_sha256,
                "hex_size": build_identity["hex_size"],
            },
            "upload": {
                **flash_identity,
                "upload_seconds": upload_results[0]["upload_seconds"],
                "hex_unchanged_after_upload": True,
            },
            "uart": final_uart_evidence,
            "completed_at_utc": completed_at_utc,
        }
    else:
        summary = {
            "schema_version": 1,
            "runner": args.runner,
            "probe_id": args.probe_id if args.runner == "jlink" else "auto-single",
            "serial_port": args.serial_port,
            "repetitions": args.repetitions,
            "compile_seconds": round(compile_seconds, 3),
            "hex_path": hex_path.as_posix(),
            "hex_sha256": hex_sha256,
            "mass_erase_requested": False,
            "recover_requested": False,
            "uploads": upload_results,
            "completed_at_utc": completed_at_utc,
        }
    summary_path = run_root / "m8-upload-result.json"
    write_json_evidence(summary_path, summary)
    print(
        f"M8_UPLOAD_HIL_PASS runner={args.runner} repetitions={args.repetitions} "
        f"hex_sha256={hex_sha256} result={summary_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UploadHilFailure as error:
        print(f"M8_UPLOAD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
