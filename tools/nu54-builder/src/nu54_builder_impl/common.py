"""! @brief schema·오류와 원자 파일·JSON·hash·revision 기본 계약을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Sequence
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile


ADAPTER_VERSION = "0.1.0-dev.m10"


NCS_VERSION = "v3.4.0"


NCS_REVISION = "99553055607b2e9885fbc80ccd11fa9da81c2df0"


ZEPHYR_REVISION = "bf801e4e3d19e1ffa76164346480cb7734dd2800"


TOOLCHAIN_BUNDLE_ID = "dcbdc366a1"


NRFUTIL_VERSION = "8.2.1"


NRFUTIL_SHA256 = "1d291d8a9d6bb5bec18454f8d95064aed7f62e8997ec1c4511f13bdf1124c037"


SDK_MANAGER_VERSION = "1.16.1"


DEFAULT_BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"


DEFAULT_PROFILE = "standard"


PROFILE_SCHEMA_VERSION = 1


FEATURE_SCHEMA_VERSION = 1


FEATURE_ALLOWLIST = {
    "NUCODE_BLE": "nucode.ble.nus",
    "NUCODE_BLE_Security": "nucode.ble.security",
    "NUCODE_NU54DK": "nucode.board",
    "Wire": "nucode.wire",
    "SPI": "nucode.spi",
    "Servo": "nucode.servo",
    "EEPROM": "nucode.eeprom",
    "LittleFS": "nucode.littlefs",
}


CONTEXT_DIRECTORY = "nu54-zephyr"


CACHE_SCHEMA_VERSION = 1


SESSION_CONTEXT_SCHEMA_VERSION = 2


ARTIFACT_MANIFEST_SCHEMA_VERSION = 2


SOURCE_RECORD_SCHEMA_VERSION = 2


DEFAULT_BUILD_CACHE_MAX_BYTES = 12 * 1024 * 1024 * 1024


DEFAULT_BUILD_CACHE_MAX_ENTRIES = 8


DEFAULT_CCACHE_MAX_SIZE = "2G"


DEFAULT_BUILD_LOCK_TIMEOUT_SECONDS = 900.0


BUILD_ENVIRONMENT_OVERRIDE_KEYS = (
    "CFLAGS",
    "CXXFLAGS",
    "CPPFLAGS",
    "LDFLAGS",
    "CONF_FILE",
    "EXTRA_CONF_FILE",
    "OVERLAY_CONFIG",
    "DTC_OVERLAY_FILE",
    "BOARD_ROOT",
    "EXTRA_ZEPHYR_MODULES",
    "CMAKE_PREFIX_PATH",
    "CMAKE_GENERATOR",
    "CMAKE_TOOLCHAIN_FILE",
    "ZEPHYR_BASE",
    "WEST_CONFIG",
    "WEST_TOPDIR",
)


class AdapterError(RuntimeError):
    """! @brief 사용자가 수정할 수 있는 Build Adapter 오류입니다. """


class DuplicateJsonKeyError(ValueError):
    """! @brief strict JSON 문서에서 발견한 중복 key를 보존하는 오류입니다. """


class ChildCommandError(AdapterError):
    """! @brief 하위 process의 실패 종료 code를 보존하는 오류입니다. """

    def __init__(self, message: str, return_code: int) -> None:
        super().__init__(message)
        self.return_code = return_code


class CacheBusyError(AdapterError):
    """! @brief 사용 중인 cache entry의 삭제를 안전하게 건너뛰기 위한 오류입니다. """


## @brief 경로를 존재 여부와 무관하게 절대 경로로 정규화합니다.
def canonical_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


## @brief Windows에서도 결정적인 비교가 가능한 경로 key를 반환합니다.
def path_key(value: str | Path) -> str:
    normalized = canonical_path(value).as_posix()
    return normalized.casefold() if os.name == "nt" else normalized


## @brief 같은 directory 안에서 임시 파일을 교체하여 bytes를 원자적으로 기록합니다.
def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


## @brief bytes 내용이 같으면 기존 파일과 timestamp를 보존합니다.
def atomic_write_bytes_if_changed(path: Path, content: bytes) -> bool:
    if path.exists() and path.read_bytes() == content:
        return False
    atomic_write_bytes(path, content)
    return True


## @brief UTF-8 text를 원자적으로 기록하며 내용이 같으면 timestamp를 보존합니다.
def atomic_write_text(path: Path, content: str) -> bool:
    encoded = content.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return False
    atomic_write_bytes(path, encoded)
    return True


## @brief JSON을 정렬된 UTF-8 형식으로 원자적으로 기록합니다.
def atomic_write_json(path: Path, value: Any) -> bool:
    return atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


## @brief 중복 key를 거부하는 JSON object hook입니다.
def strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise DuplicateJsonKeyError(f"중복 JSON key입니다: {key}")
        document[key] = value
    return document


## @brief release manifest를 엄격한 JSON object로 읽습니다.
def release_manifest(platform_root: Path) -> dict[str, Any]:
    manifest_path = platform_root / "release-manifest.json"
    if not manifest_path.is_file():
        raise AdapterError(
            "[NU54:E_PACKAGE_MANIFEST] Git-less package에 release-manifest.json이 없습니다."
        )
    document = load_json_object(manifest_path, "E_PACKAGE_MANIFEST")
    if document.get("schema_version") != 1:
        raise AdapterError("[NU54:E_PACKAGE_MANIFEST] 지원하지 않는 release manifest입니다.")
    return document


## @brief command를 shell 없이 실행하고 실패 code를 그대로 오류로 변환합니다.
def run_checked(command: Sequence[str | Path], *, cwd: Path, environment: dict[str, str], capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    normalized = [str(item) for item in command]
    result = subprocess.run(
        normalized,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode != 0:
        if capture:
            if result.stdout:
                sys.stdout.buffer.write(result.stdout)
            if result.stderr:
                sys.stderr.buffer.write(result.stderr)
        raise ChildCommandError(
            f"명령이 종료 코드 {result.returncode}로 실패했습니다: {shlex.join(normalized)}",
            result.returncode,
        )
    return result


## @brief 파일의 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief 파일이 없을 때도 결정적인 SHA-256 표기를 반환합니다.
def optional_file_sha256(path: Path) -> str:
    return f"sha256:{file_sha256(path)}" if path.is_file() else "missing"


## @brief directory tree의 상대 경로와 내용을 결정적으로 hashing합니다.
def tree_content_sha256(root: Path, relative_inputs: Sequence[str | Path]) -> str:
    digest = hashlib.sha256()
    for relative_input in relative_inputs:
        candidate = root / relative_input
        if candidate.is_file():
            files = [candidate]
        elif candidate.is_dir():
            files = sorted(
                (
                    path
                    for path in candidate.rglob("*")
                    if path.is_file()
                    and ".git" not in path.relative_to(root).parts
                    and "__pycache__" not in path.relative_to(root).parts
                ),
                key=lambda path: path.relative_to(root).as_posix().casefold(),
            )
        else:
            digest.update(f"missing:{Path(relative_input).as_posix()}\0".encode("utf-8"))
            continue
        for path in files:
            relative = path.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


## @brief 요청 root 자체의 Git revision 또는 검증된 archive revision을 읽습니다.
def exact_git_revision(
    root: Path,
    fallback_platform_root: Path | None = None,
    fallback_field: str | None = None,
    *,
    git_executable: str | Path = "git",
) -> str:
    try:
        top = subprocess.run(
            [str(git_executable), "-C", str(root), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
        if top.returncode == 0 and path_key(top.stdout.strip()) == path_key(root):
            revision = subprocess.run(
                [str(git_executable), "-C", str(root), "rev-parse", "HEAD"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                text=True,
            )
            if revision.returncode == 0 and re.fullmatch(
                r"[0-9a-fA-F]{40}", revision.stdout.strip()
            ):
                return revision.stdout.strip().lower()
    except OSError:
        pass
    if fallback_platform_root is not None and fallback_field is not None:
        document = release_manifest(fallback_platform_root)
        fallback = document.get(fallback_field)
        if isinstance(fallback, str) and re.fullmatch(r"[0-9a-fA-F]{40}", fallback):
            return fallback.lower()
        raise AdapterError(
            f"[NU54:E_PACKAGE_MANIFEST] {fallback_field} revision이 없거나 잘못되었습니다."
        )
    return "unknown"


## @brief 개발 checkout은 Git을, 배포 archive는 release manifest revision을 사용합니다.
def git_or_release_revision(root: Path, platform_root: Path, field: str) -> str:
    revision = exact_git_revision(root)
    if revision != "unknown":
        return revision
    document = release_manifest(platform_root)
    fallback = document.get(field)
    if isinstance(fallback, str) and re.fullmatch(r"[0-9a-fA-F]{40}", fallback):
        return fallback.lower()
    raise AdapterError(f"[NU54:E_PACKAGE_MANIFEST] {field} revision이 없거나 잘못되었습니다.")


## @brief JSON object를 읽고 손상 또는 잘못된 root type을 거부합니다.
def load_json_object(path: Path, error_code: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"[NU54:{error_code}] JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise AdapterError(f"[NU54:{error_code}] JSON root가 object가 아닙니다: {path}")
    return document


## @brief path가 지정 directory 내부인지 판정합니다.
def is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False
