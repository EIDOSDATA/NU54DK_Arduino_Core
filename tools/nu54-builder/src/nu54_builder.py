#!/usr/bin/env python3
"""! @brief Arduino build graph와 NU54DK flash 경로를 NCS/Zephyr에 연결합니다. """

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator, Sequence
import uuid


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


## @brief process가 현재 host에서 생존 중인지 보수적으로 판정합니다.
def process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information, False, process_id
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return ctypes.get_last_error() == 5
        except (AttributeError, OSError):
            return True
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


## @brief lock JSON을 읽고 손상된 경우 빈 object를 반환합니다.
def read_lock_document(lock_path: Path) -> dict[str, Any]:
    try:
        document = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


## @brief lock root에 대응하는 운영체제 lock 식별자를 생성합니다.
def operating_system_lock_identity(
    lock_root: Path, logical_identity: str | None = None
) -> str:
    seed = logical_identity if logical_identity is not None else path_key(lock_root)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"NUCODE_NU54_{digest}"


## @brief 운영체제가 crash 시 자동 회수하는 process 간 lock을 획득합니다.
@contextlib.contextmanager
def operating_system_lock(
    lock_root: Path,
    timeout_seconds: float,
    logical_identity: str | None = None,
) -> Iterator[None]:
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    identity = operating_system_lock_identity(lock_root, logical_identity)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateMutexW(None, False, f"Global\\{identity}")
        if not handle:
            raise AdapterError(
                f"Windows mutex를 만들지 못했습니다: error={ctypes.get_last_error()}"
            )
        wait_object_0 = 0x00000000
        wait_abandoned = 0x00000080
        wait_timeout = 0x00000102
        wait_failed = 0xFFFFFFFF
        acquired = False
        try:
            while not acquired:
                remaining = max(0.0, deadline - time.monotonic())
                wait_milliseconds = min(50, max(0, int(remaining * 1000)))
                result = kernel32.WaitForSingleObject(handle, wait_milliseconds)
                if result in {wait_object_0, wait_abandoned}:
                    acquired = True
                    break
                if result == wait_failed:
                    raise AdapterError(
                        f"Windows mutex 대기에 실패했습니다: error={ctypes.get_last_error()}"
                    )
                if result != wait_timeout:
                    raise AdapterError(f"Windows mutex가 알 수 없는 상태를 반환했습니다: {result}")
                if time.monotonic() >= deadline:
                    raise TimeoutError
            yield
        finally:
            if acquired:
                kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        return

    import fcntl

    lock_directory = canonical_path(Path(tempfile.gettempdir()) / "n54" / "adapter-locks")
    lock_directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_directory / f"{identity}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        while not acquired:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


## @brief 다른 adapter process와 cache 또는 session 갱신을 직렬화합니다.
@contextlib.contextmanager
def build_lock(
    lock_root: Path,
    *,
    operation: str = "build",
    timeout_seconds: float = DEFAULT_BUILD_LOCK_TIMEOUT_SECONDS,
    logical_identity: str | None = None,
) -> Iterator[None]:
    lock_root = canonical_path(lock_root)
    lock_path = lock_root / ".adapter.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    host_name = socket.gethostname()
    token = uuid.uuid4().hex
    lock_document = {
        "schema_version": 1,
        "pid": os.getpid(),
        "host": host_name,
        "operation": operation,
        "token": token,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    try:
        with operating_system_lock(lock_root, timeout_seconds, logical_identity):
            atomic_write_json(lock_path, lock_document)
            try:
                yield
            finally:
                owner = read_lock_document(lock_path)
                if owner.get("token") == token:
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        pass
    except TimeoutError as error:
        owner = read_lock_document(lock_path)
        detail = json.dumps(owner, ensure_ascii=False, sort_keys=True) if owner else "unknown"
        raise AdapterError(
            f"build lock 대기 시간이 초과되었습니다: {lock_path}; owner={detail}"
        ) from error


## @brief cache root가 단일 host의 local filesystem인지 검증합니다.
def local_cache_root(value: str | Path) -> Path:
    root = canonical_path(value)
    if os.name == "nt" and str(root).startswith(("\\\\", "//")):
        raise AdapterError("M9 build cache는 UNC/network 경로를 지원하지 않습니다.")
    return root


## @brief M9 영구 build cache root를 환경 또는 짧은 사용자 local data 경로에서 계산합니다.
def build_cache_root() -> Path:
    configured = os.environ.get("NUCODE_BUILD_CACHE_ROOT")
    if configured:
        return local_cache_root(configured)
    local_data = os.environ.get("LOCALAPPDATA")
    if local_data:
        base = canonical_path(local_data)
    else:
        base = canonical_path(Path.home() / ".cache")
    ## @note nRF Security의 긴 object 이름이 Windows MAX_PATH를 넘지 않도록 build 전용
    ##       기본 경로는 짧게 유지하고 설치 상태와 log는 기존 NUCODE 경로를 사용합니다.
    return local_cache_root(base / "NU54" / "c")


## @brief 정수형 환경 설정을 유효한 양수로 읽습니다.
def positive_environment_integer(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise AdapterError(f"{name}은 양의 정수여야 합니다: {value}") from error
    if parsed <= 0:
        raise AdapterError(f"{name}은 양의 정수여야 합니다: {value}")
    return parsed


## @brief common argument에서 adapter의 고정 directory를 계산합니다.
def adapter_paths(args: argparse.Namespace) -> dict[str, Path]:
    platform_root = canonical_path(args.platform_root)
    build_path = canonical_path(args.build_path)
    state_root = build_path / CONTEXT_DIRECTORY
    return {
        "platform_root": platform_root,
        "build_path": build_path,
        "sketch_root": canonical_path(args.sketch_root),
        "state_root": state_root,
        "context": state_root / "context.json",
        "records": state_root / "records",
    }


## @brief 중복 key를 거부하는 JSON object hook입니다.
def strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise DuplicateJsonKeyError(f"중복 JSON key입니다: {key}")
        document[key] = value
    return document


## @brief root를 벗어나지 않는 선언형 상대 경로만 허용합니다.
def declared_path(root: Path, value: str, error_code: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or PureWindowsPath(value).is_absolute() or value.startswith(("\\\\", "//")):
        raise AdapterError(f"[NU54:{error_code}] 상대 경로가 아닙니다: {value}")
    candidate = canonical_path(root / value)
    if not is_within(candidate, root):
        raise AdapterError(f"[NU54:{error_code}] 경로가 root를 벗어납니다: {value}")
    return candidate


## @brief 선택한 NU54DK 구성 profile과 실제 build target을 엄격히 검증하여 읽습니다.
def load_configuration_profile(
    platform_root: Path,
    profile_id: str,
    *,
    fqbn: str = "nucode:zephyr:nu54dk",
    zephyr_board: str = DEFAULT_BOARD,
) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", profile_id):
        raise AdapterError(f"[NU54:E_PROFILE_ID] 잘못된 profile ID입니다: {profile_id}")
    root = platform_root / "variants" / "nu54dk" / "profiles" / profile_id
    path = root / "profile.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_json_object)
    except DuplicateJsonKeyError as error:
        raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] {error}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] profile을 읽지 못했습니다: {path}: {error}") from error
    allowed = {"schema_version", "id", "display_name", "board", "zephyr_board", "ncs_version", "conf", "overlay", "features", "conflicts", "requires_hil"}
    if not isinstance(document, dict) or set(document) != allowed or document.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_PROFILE_SCHEMA] profile field/schema가 올바르지 않습니다.")
    for field in ("id", "display_name", "board", "zephyr_board", "ncs_version", "conf", "overlay"):
        if not isinstance(document.get(field), str):
            raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] {field}는 문자열이어야 합니다.")
    fqbn_parts = fqbn.split(":") if isinstance(fqbn, str) else []
    fqbn_board = ":".join(fqbn_parts[:3]) if len(fqbn_parts) >= 3 else ""
    if (
        document.get("id") != profile_id
        or document.get("board") != fqbn_board
        or document.get("zephyr_board") != zephyr_board
        or document.get("ncs_version") != NCS_VERSION
    ):
        raise AdapterError("[NU54:E_PROFILE_TARGET] profile target 계약이 현재 build와 다릅니다.")
    for field in ("features", "conflicts", "requires_hil"):
        if not isinstance(document[field], list) or not all(isinstance(item, str) for item in document[field]):
            raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] {field}는 문자열 배열이어야 합니다.")
    conf = declared_path(root, document["conf"], "E_PROFILE_PATH")
    overlay = declared_path(root, document["overlay"], "E_PROFILE_PATH")
    if not conf.is_file() or not overlay.is_file():
        raise AdapterError("[NU54:E_PROFILE_PATH] profile fragment가 없습니다.")
    return {**document, "root": root, "path": path, "conf_path": conf, "overlay_path": overlay}


## @brief bundled library의 선언형 feature manifest만 allowlist로 읽습니다.
def load_library_feature(platform_root: Path, library_name: str) -> dict[str, Any] | None:
    expected_id = FEATURE_ALLOWLIST.get(library_name)
    if expected_id is None:
        return None
    root = platform_root / "libraries" / library_name / "zephyr"
    path = root / "feature.yml"
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_json_object)
    except DuplicateJsonKeyError as error:
        raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] {error}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] feature manifest를 읽지 못했습니다: {path}: {error}") from error
    allowed = {"schema_version", "id", "requires", "conf", "overlays", "conflicts", "compatible_profiles"}
    if not isinstance(document, dict) or set(document) != allowed or document.get("schema_version") != FEATURE_SCHEMA_VERSION or document.get("id") != expected_id:
        raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] allowlist feature 계약이 잘못되었습니다: {library_name}")
    for field in ("requires", "conf", "overlays", "conflicts", "compatible_profiles"):
        if not isinstance(document[field], list) or not all(isinstance(item, str) for item in document[field]):
            raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] {field}는 문자열 배열이어야 합니다.")
    for field in ("conf", "overlays"):
        for value in document[field]:
            if not declared_path(root, value, "E_FEATURE_PATH").is_file():
                raise AdapterError(f"[NU54:E_FEATURE_PATH] feature fragment가 없습니다: {value}")
    return {**document, "root": root, "path": path}


## @brief 선택된 bundled library feature의 profile 적합성과 충돌을 판정합니다.
def resolve_library_features(
    platform_root: Path, profile: dict[str, Any], library_names: Sequence[str]
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    profile_features = set(profile["features"])
    conflict_owners = {
        resource: f"profile:{profile['id']}" for resource in profile["conflicts"]
    }
    for library_name in sorted(set(library_names), key=str.casefold):
        feature = load_library_feature(platform_root, library_name)
        if feature is None:
            continue
        if profile["id"] not in feature["compatible_profiles"]:
            raise AdapterError(f"[NU54:E_FEATURE_PROFILE] {feature['id']}는 {profile['id']} profile과 호환되지 않습니다.")
        missing = sorted(set(feature["requires"]) - profile_features)
        conflicts = sorted(set(feature["conflicts"]) & conflict_owners.keys())
        if missing:
            raise AdapterError(f"[NU54:E_FEATURE_REQUIREMENT] {feature['id']} 요구 기능이 없습니다: {missing}")
        if conflicts:
            detail = ", ".join(
                f"{resource} ({conflict_owners[resource]} <-> {feature['id']})"
                for resource in conflicts
            )
            raise AdapterError(f"[NU54:E_FEATURE_CONFLICT] 충돌 자원: {detail}")
        for resource in feature["conflicts"]:
            conflict_owners[resource] = feature["id"]
        resolved.append(feature)
    return resolved


## @brief cache workspace 경로를 adapter path 집합에 결합합니다.
def add_workspace_paths(paths: dict[str, Path], workspace: Path) -> dict[str, Path]:
    combined = dict(paths)
    combined.update(
        {
            "workspace": canonical_path(workspace),
            "app": canonical_path(workspace) / "app",
            "zephyr_build": canonical_path(workspace) / "build",
        }
    )
    return combined


## @brief 저장된 context의 cache workspace를 검증하고 path 집합에 결합합니다.
def paths_from_context(paths: dict[str, Path], context: dict[str, Any]) -> dict[str, Path]:
    workspace_value = context.get("cache_dir") or context.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value:
        raise AdapterError("build context에 M9 cache directory가 없습니다. 다시 compile하십시오.")
    cache_key = context.get("cache_key")
    cache_root_value = context.get("cache_root")
    if not isinstance(cache_key, str) or not re.fullmatch(r"[0-9a-f]{64}", cache_key):
        raise AdapterError("build context의 M9 cache key가 잘못되었습니다. 다시 compile하십시오.")
    if not isinstance(cache_root_value, str) or not cache_root_value:
        raise AdapterError("build context에 M9 cache root가 없습니다. 다시 compile하십시오.")
    workspace = canonical_path(workspace_value)
    cache_root = local_cache_root(cache_root_value)
    expected = cache_workspace(cache_key, root=cache_root)
    if path_key(workspace) != path_key(expected):
        raise AdapterError(
            f"build context의 cache directory가 key/root 계약과 다릅니다: {workspace}"
        )
    return add_workspace_paths(paths, workspace)


## @brief 요청 platform root가 exact Git checkout인지 확인합니다.
def is_development_checkout(platform_root: Path) -> bool:
    if not (platform_root / ".git").exists():
        return False
    try:
        top = subprocess.run(
            ["git", "-C", str(platform_root), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except OSError:
        return True
    return top.returncode == 0 and path_key(top.stdout.strip()) == path_key(platform_root)


## @brief 고정 버전의 NCS root를 환경 또는 기본 설치 위치에서 찾습니다.
def discover_ncs_root(*, prefer_user_profile: bool = False) -> Path:
    configured = os.environ.get("NUCODE_NCS_ROOT")
    if configured is not None:
        if not configured.strip():
            raise AdapterError("명시한 NUCODE_NCS_ROOT 값이 비어 있습니다.")
        candidate = canonical_path(configured)
        if (candidate / "zephyr" / "CMakeLists.txt").is_file() and (
            candidate / "nrf" / "west.yml"
        ).is_file():
            return candidate.resolve()
        raise AdapterError(
            "명시한 NUCODE_NCS_ROOT에 nRF Connect SDK v3.4.0이 없습니다: "
            f"{candidate}"
        )
    default_candidates = (Path("C:/ncs/v3.4.0"), Path.home() / "ncs" / "v3.4.0")
    if prefer_user_profile:
        default_candidates = tuple(reversed(default_candidates))
    for candidate in default_candidates:
        if (candidate / "zephyr" / "CMakeLists.txt").is_file() and (candidate / "nrf" / "west.yml").is_file():
            return candidate.resolve()
    raise AdapterError(
        "nRF Connect SDK v3.4.0을 찾을 수 없습니다. NUCODE_NCS_ROOT를 설정하십시오."
    )


## @brief NCS version과 연결된 Toolchain Manager bundle identifier를 읽습니다.
def configured_bundle_id(ncs_root: Path) -> str | None:
    registry = ncs_root.parent / "toolchains" / "toolchains.json"
    if not registry.is_file():
        return None
    try:
        documents = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for document in documents if isinstance(documents, list) else []:
        for entry in document.get("toolchains", []):
            if NCS_VERSION in entry.get("ncs_versions", []):
                identifier = entry.get("identifier", {})
                bundle = identifier.get("bundle_id")
                if isinstance(bundle, str):
                    return bundle
    return None


## @brief 개발 환경 discovery 또는 배포 package의 exact Toolchain bundle을 찾습니다.
def discover_toolchain_root(ncs_root: Path, *, exact_required: bool = False) -> Path:
    toolchains_root = ncs_root.parent / "toolchains"
    if exact_required:
        pinned = toolchains_root / TOOLCHAIN_BUNDLE_ID
        if (
            (pinned / "environment.json").is_file()
            and (pinned / "opt" / "bin" / "python.exe").is_file()
        ):
            return pinned.resolve()
        raise AdapterError(
            "Boards Manager package에 필요한 고정 NCS Toolchain bundle을 찾을 수 없습니다: "
            f"{pinned}"
        )

    configured = os.environ.get("NUCODE_TOOLCHAIN_ROOT")
    candidates: list[Path] = []
    if configured:
        candidates.append(canonical_path(configured))
    bundle = configured_bundle_id(ncs_root)
    if bundle:
        candidates.append(ncs_root.parent / "toolchains" / bundle)
    candidates.append(toolchains_root / TOOLCHAIN_BUNDLE_ID)
    if toolchains_root.is_dir():
        candidates.extend(sorted(path for path in toolchains_root.iterdir() if path.is_dir()))
    visited: set[str] = set()
    for candidate in candidates:
        key = path_key(candidate)
        if key in visited:
            continue
        visited.add(key)
        if (candidate / "environment.json").is_file() and (candidate / "opt" / "bin" / "python.exe").is_file():
            return candidate.resolve()
    raise AdapterError(
        "NCS toolchain environment.json을 찾을 수 없습니다. NUCODE_TOOLCHAIN_ROOT를 설정하십시오."
    )


## @brief Toolchain Manager environment.json을 현재 child process 환경에 적용합니다.
def apply_toolchain_environment(toolchain_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    # 사용자의 shell flag가 canonical cache key 밖에서 build를 바꾸지 못하게 합니다.
    for key in BUILD_ENVIRONMENT_OVERRIDE_KEYS:
        environment.pop(key, None)
    document_path = toolchain_root / "environment.json"
    try:
        document = json.loads(document_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"toolchain environment.json을 읽지 못했습니다: {error}") from error

    for entry in document.get("env_vars", []):
        key = entry.get("key")
        if not isinstance(key, str):
            continue
        entry_type = entry.get("type")
        if entry_type == "relative_paths":
            values = [str((toolchain_root / value).resolve()) for value in entry.get("values", [])]
            treatment = entry.get("existing_value_treatment", "overwrite")
            if treatment == "prepend_to" and environment.get(key):
                values.append(environment[key])
            environment[key] = os.pathsep.join(values)
        elif entry_type == "string":
            environment[key] = str(entry.get("value", ""))
    return environment


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


## @brief M10 사용자별 prerequisite state directory를 계산합니다.
def prerequisite_state_root() -> Path:
    configured = os.environ.get("NUCODE_PREREQUISITE_STATE_ROOT")
    if configured:
        return canonical_path(configured)
    local_data = os.environ.get("LOCALAPPDATA")
    if not local_data:
        raise AdapterError("[NU54:E_PREREQUISITE_STATE] LOCALAPPDATA 환경 변수가 없습니다.")
    return canonical_path(
        Path(local_data) / "NUCODE" / "NU54DK_Arduino_Core" / "prerequisites"
    )


## @brief 배포 package의 pin과 완료 marker를 현재 Nordic 설치와 대조합니다.
def validate_packaged_prerequisites(
    platform_root: Path, ncs_root: Path, toolchain_root: Path
) -> None:
    package_manifest = release_manifest(platform_root)
    pins_path = platform_root / "tools" / "nu54-prerequisites" / "pins.json"
    pins = load_json_object(pins_path, "E_PREREQUISITE_PINS")
    ready_path = prerequisite_state_root() / "ready.json"
    ready = load_json_object(ready_path, "E_PREREQUISITE_READY")
    pins_hash = file_sha256(pins_path)

    if pins.get("schema_version") != 1:
        raise AdapterError("[NU54:E_PREREQUISITE_PINS] 지원하지 않는 pin schema입니다.")
    ## @brief 중첩 pin 값이 object/string 계약을 만족할 때만 반환합니다.
    def pin_value(section: str, field: str) -> Any:
        section_value = pins.get(section)
        return section_value.get(field) if isinstance(section_value, dict) else None

    expected_values = {
        "ncs_version": pin_value("ncs", "version"),
        "ncs_revision": pin_value("ncs", "revision"),
        "zephyr_revision": pin_value("zephyr", "revision"),
        "toolchain_bundle_id": pin_value("toolchain", "bundle_id"),
        "nrfutil_version": pin_value("nrfutil", "version"),
        "nrfutil_sha256": pin_value("nrfutil", "sha256"),
        "sdk_manager_version": pin_value("sdk_manager", "version"),
    }
    if expected_values != {
        "ncs_version": NCS_VERSION,
        "ncs_revision": NCS_REVISION,
        "zephyr_revision": ZEPHYR_REVISION,
        "toolchain_bundle_id": TOOLCHAIN_BUNDLE_ID,
        "nrfutil_version": NRFUTIL_VERSION,
        "nrfutil_sha256": NRFUTIL_SHA256,
        "sdk_manager_version": SDK_MANAGER_VERSION,
    }:
        raise AdapterError("[NU54:E_PREREQUISITE_PINS] Build Adapter와 pin 계약이 다릅니다.")
    for field in ("ncs_revision", "zephyr_revision", "toolchain_bundle_id"):
        if package_manifest.get(field) != expected_values[field]:
            raise AdapterError(
                f"[NU54:E_PACKAGE_MANIFEST] release manifest의 {field} 값이 pin과 다릅니다."
            )
    if package_manifest.get("prerequisites_pins_sha256") != pins_hash:
        raise AdapterError(
            "[NU54:E_PACKAGE_MANIFEST] release manifest의 prerequisite pin hash가 다릅니다."
        )

    if ready.get("schema_version") != 1 or ready.get("status") != "ready":
        raise AdapterError(
            "[NU54:E_PREREQUISITE_READY] 설치 완료 marker가 없거나 상태가 잘못되었습니다. "
            "post_install.bat을 다시 실행하십시오."
        )
    ready_expected = {
        "pins_sha256": pins_hash,
        "ncs_version": NCS_VERSION,
        "ncs_revision": NCS_REVISION,
        "zephyr_revision": ZEPHYR_REVISION,
        "toolchain_bundle_id": TOOLCHAIN_BUNDLE_ID,
        "nrfutil_version": NRFUTIL_VERSION,
        "nrfutil_sha256": NRFUTIL_SHA256,
        "sdk_manager_version": SDK_MANAGER_VERSION,
    }
    for field, expected in ready_expected.items():
        if ready.get(field) != expected:
            raise AdapterError(
                f"[NU54:E_PREREQUISITE_READY] 완료 marker의 {field} 값이 다릅니다."
            )
    marker_ncs_root = ready.get("ncs_root")
    marker_toolchain_root = ready.get("toolchain_root")
    marker_nrfutil = ready.get("nrfutil_path")
    local_data = os.environ.get("LOCALAPPDATA")
    if not local_data:
        raise AdapterError("[NU54:E_PREREQUISITE_STATE] LOCALAPPDATA 환경 변수가 없습니다.")
    expected_nrfutil = canonical_path(
        Path(local_data) / "NUCODE" / "NU54DK_Arduino_Core" / "tools" / "nrfutil.exe"
    )
    if (
        not isinstance(marker_ncs_root, str)
        or path_key(marker_ncs_root) != path_key(ncs_root.parent)
        or not isinstance(marker_toolchain_root, str)
        or path_key(marker_toolchain_root) != path_key(toolchain_root)
        or not isinstance(marker_nrfutil, str)
        or path_key(marker_nrfutil) != path_key(expected_nrfutil)
    ):
        raise AdapterError(
            "[NU54:E_PREREQUISITE_READY] 완료 marker와 발견한 Nordic 설치 경로가 다릅니다."
        )
    if toolchain_root.name != TOOLCHAIN_BUNDLE_ID:
        raise AdapterError("[NU54:E_PREREQUISITE_TOOLCHAIN] 고정 Toolchain bundle이 아닙니다.")
    bundled_git = toolchain_root / "bin" / "git.exe"
    if not bundled_git.is_file():
        raise AdapterError(
            "[NU54:E_PREREQUISITE_TOOLCHAIN] Toolchain bundle의 Git 실행 파일이 없습니다."
        )
    toolchain_manifest = load_json_object(
        toolchain_root / "manifest.json", "E_PREREQUISITE_TOOLCHAIN"
    )
    if toolchain_manifest.get("bundle_id") != TOOLCHAIN_BUNDLE_ID:
        raise AdapterError(
            "[NU54:E_PREREQUISITE_TOOLCHAIN] Toolchain manifest bundle_id가 pin과 다릅니다."
        )
    if not expected_nrfutil.is_file() or file_sha256(expected_nrfutil) != NRFUTIL_SHA256:
        raise AdapterError("[NU54:E_PREREQUISITE_NRFUTIL] nRF Util byte hash가 pin과 다릅니다.")
    if exact_git_revision(ncs_root / "nrf", git_executable=bundled_git) != NCS_REVISION:
        raise AdapterError("[NU54:E_PREREQUISITE_NCS] NCS revision이 고정 pin과 다릅니다.")
    if exact_git_revision(
        ncs_root / "zephyr", git_executable=bundled_git
    ) != ZEPHYR_REVISION:
        raise AdapterError("[NU54:E_PREREQUISITE_ZEPHYR] Zephyr revision이 고정 pin과 다릅니다.")


## @brief west와 compiler에 필요한 실행 환경 및 절대 경로를 구성합니다.
def tool_environment(platform_root: Path | None = None) -> dict[str, Any]:
    packaged = platform_root is not None and not is_development_checkout(platform_root)
    if packaged:
        release_manifest(platform_root)
    ncs_root = discover_ncs_root(prefer_user_profile=packaged)
    toolchain_root = discover_toolchain_root(ncs_root, exact_required=packaged)
    if packaged and platform_root is not None:
        validate_packaged_prerequisites(platform_root, ncs_root, toolchain_root)
    environment = apply_toolchain_environment(toolchain_root)
    zephyr_base = ncs_root / "zephyr"
    environment["ZEPHYR_BASE"] = str(zephyr_base)
    west = toolchain_root / "opt" / "bin" / "Scripts" / "west.exe"
    git = toolchain_root / "bin" / "git.exe"
    compiler = (
        toolchain_root
        / "opt"
        / "zephyr-sdk"
        / "gnu"
        / "arm-zephyr-eabi"
        / "bin"
        / "arm-zephyr-eabi-g++.exe"
    )
    size_tool = compiler.with_name("arm-zephyr-eabi-size.exe")
    ccache = toolchain_root / "opt" / "bin" / ("ccache.exe" if os.name == "nt" else "ccache")
    for executable in (west, git, compiler, size_tool):
        if not executable.is_file():
            raise AdapterError(f"NCS toolchain 실행 파일이 없습니다: {executable}")
    ccache_root = build_cache_root() / "compiler-cache"
    if ccache.is_file():
        ccache_root.mkdir(parents=True, exist_ok=True)
        environment["CCACHE_DIR"] = str(ccache_root)
        environment["CCACHE_MAXSIZE"] = os.environ.get(
            "NUCODE_CCACHE_MAX_SIZE", DEFAULT_CCACHE_MAX_SIZE
        )
        environment["CCACHE_COMPILERCHECK"] = "content"
    return {
        "ncs_root": ncs_root,
        "toolchain_root": toolchain_root,
        "zephyr_base": zephyr_base,
        "environment": environment,
        "west": west,
        "git": git,
        "compiler": compiler,
        "size": size_tool,
        "ccache": ccache if ccache.is_file() else None,
        "ccache_root": ccache_root,
    }


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


## @brief compiler의 version 첫 줄을 build identity로 읽습니다.
def compiler_version(compiler: Path, environment: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            [str(compiler), "--version"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
    except OSError:
        return "unknown"
    if result.returncode != 0 or not result.stdout:
        return "unknown"
    return result.stdout.splitlines()[0].strip()


## @brief M9 cache key에 사용할 canonical input manifest를 생성합니다.
def cache_input_manifest(
    paths: dict[str, Path], args: argparse.Namespace, tools: dict[str, Any],
    selected_library_names: Sequence[str] = (),
) -> dict[str, Any]:
    platform_root = paths["platform_root"]
    board_root = platform_root / "board_package" / "NU54DK_Zephyr_DTS"
    ncs_root = tools["ncs_root"]
    toolchain_root = tools["toolchain_root"]
    platform_inputs = (
        "release-manifest.json",
        "post_install.bat",
        "platform.txt",
        "boards.txt",
        "programmers.txt",
        "cores",
        "variants",
        "dts",
        "zephyr",
        "third_party/ArduinoCore-API",
        "tools/nu54-builder/src",
        "tools/nu54-builder/templates",
        "tools/nu54-prerequisites",
    )
    board_inputs = ("boards/nucode/nu54dk",)
    nrf_root = ncs_root / "nrf"
    zephyr_root = ncs_root / "zephyr"
    toolchain_manifest = toolchain_root / "manifest.json"
    bundled_git = tools.get("git")
    revision_arguments: dict[str, str | Path] = {}
    if isinstance(bundled_git, Path) and bundled_git.is_file():
        revision_arguments["git_executable"] = bundled_git
    profile_id = getattr(args, "profile", DEFAULT_PROFILE)
    profile_path = platform_root / "variants" / "nu54dk" / "profiles" / profile_id / "profile.json"
    profile = (
        load_configuration_profile(
            platform_root,
            profile_id,
            fqbn=args.fqbn,
            zephyr_board=args.board,
        )
        if profile_path.is_file()
        else None
    )
    features = resolve_library_features(platform_root, profile, selected_library_names) if profile is not None else []
    manifest = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "adapter": {
            "version": ADAPTER_VERSION,
            "platform_root": platform_root.as_posix(),
            "platform_content": tree_content_sha256(platform_root, platform_inputs),
        },
        "target": {
            "fqbn": args.fqbn,
            "board": args.board,
            "sysbuild": False,
            "profile": profile_id,
        },
        "sketch": {
            "root": paths["sketch_root"].as_posix(),
            "prj_conf": optional_file_sha256(paths["sketch_root"] / "prj.conf"),
            "app_overlay": optional_file_sha256(paths["sketch_root"] / "app.overlay"),
        },
        "board_package": {
            "root": board_root.resolve().as_posix(),
            "revision": git_or_release_revision(
                board_root, platform_root, "board_revision"
            ),
            "content": tree_content_sha256(board_root, board_inputs),
        },
        "ncs": {
            "declared_version": NCS_VERSION,
            "root": ncs_root.as_posix(),
            "nrf_revision": exact_git_revision(
                nrf_root, **revision_arguments
            ),
            "nrf_west_yml": optional_file_sha256(nrf_root / "west.yml"),
            "zephyr_revision": exact_git_revision(
                zephyr_root, **revision_arguments
            ),
            "zephyr_version_file": optional_file_sha256(zephyr_root / "VERSION"),
        },
        "toolchain": {
            "root": toolchain_root.as_posix(),
            "bundle_id": toolchain_root.name,
            "environment": optional_file_sha256(toolchain_root / "environment.json"),
            "manifest": optional_file_sha256(toolchain_manifest),
            "compiler": compiler_version(tools["compiler"], tools["environment"]),
        },
    }
    if profile is not None:
        manifest["configuration"] = {
            "profile": {"id": profile["id"], "manifest": optional_file_sha256(profile["path"]), "conf": optional_file_sha256(profile["conf_path"]), "overlay": optional_file_sha256(profile["overlay_path"])},
            "selected_features": [{"id": item["id"], "manifest": optional_file_sha256(item["path"]), "conf": [optional_file_sha256(declared_path(item["root"], value, "E_FEATURE_PATH")) for value in item["conf"]], "overlays": [optional_file_sha256(declared_path(item["root"], value, "E_FEATURE_PATH")) for value in item["overlays"]]} for item in features],
        }
    elif hasattr(args, "profile"):
        raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] profile을 찾을 수 없습니다: {profile_path}")
    return manifest


## @brief canonical input manifest에서 전체 SHA-256 cache key를 계산합니다.
def cache_key_for_manifest(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


## @brief cache key의 persistent workspace path를 계산합니다.
def cache_workspace(cache_key: str, *, root: Path | None = None) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", cache_key):
        raise AdapterError(f"잘못된 cache key입니다: {cache_key}")
    directory_key = cache_key[:32]
    cache_root = local_cache_root(root or build_cache_root())
    return cache_root / f"v{CACHE_SCHEMA_VERSION}" / directory_key[:2] / directory_key


## @brief cache access 시각과 크기 계산용 metadata를 갱신합니다.
def touch_cache_access(workspace: Path, cache_key: str) -> None:
    atomic_write_json(
        workspace / "access.json",
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "last_accessed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )


## @brief cache state를 원자적으로 전이하고 기존 누적값을 보존합니다.
def transition_cache_state(workspace: Path, cache_key: str, state: str, **updates: Any) -> dict[str, Any]:
    state_path = workspace / "state.json"
    previous: dict[str, Any] = {}
    if state_path.is_file():
        try:
            previous = load_json_object(state_path, "E_CACHE_STATE")
        except AdapterError:
            previous = {}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    document = dict(previous)
    if state == "ready":
        document.pop("failure", None)
        document.pop("failed_at_utc", None)
    elif state == "failed":
        updates.setdefault("failed_at_utc", now)
    document.update(updates)
    document.update(
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "state": state,
            "updated_at_utc": now,
        }
    )
    document.setdefault("created_at_utc", now)
    atomic_write_json(state_path, document)
    touch_cache_access(workspace, cache_key)
    return document


## @brief ccache의 machine-readable 통계를 dictionary로 읽습니다.
def read_ccache_stats(tools: dict[str, Any]) -> dict[str, int]:
    ccache = tools.get("ccache")
    if not isinstance(ccache, Path) or not ccache.is_file():
        return {}
    try:
        result = subprocess.run(
            [str(ccache), "--print-stats"],
            env=tools["environment"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except OSError:
        return {}
    if result.returncode != 0:
        return {}
    statistics: dict[str, int] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t", 1)
        if len(fields) == 2 and fields[1].strip().isdigit():
            statistics[fields[0].strip()] = int(fields[1].strip())
    return statistics


## @brief 두 ccache snapshot의 증가량만 반환합니다.
def ccache_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {key: after.get(key, 0) - before.get(key, 0) for key in sorted(keys)}


## @brief JSON object를 읽고 손상 또는 잘못된 root type을 거부합니다.
def load_json_object(path: Path, error_code: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"[NU54:{error_code}] JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise AdapterError(f"[NU54:{error_code}] JSON root가 object가 아닙니다: {path}")
    return document


## @brief west configure command를 cache 정책에 맞게 생성합니다.
def configure_command(
    paths: dict[str, Path],
    args: argparse.Namespace,
    tools: dict[str, Any],
    board_root: Path,
    *,
    pristine: bool,
) -> list[str | Path]:
    command: list[str | Path] = [
        tools["west"],
        "-z",
        tools["zephyr_base"],
        "build",
        "--cmake-only",
        "--no-sysbuild",
    ]
    if pristine:
        command.append("--pristine=always")
    command.extend(
        [
            "-b",
            args.board,
            "-d",
            paths["zephyr_build"],
            paths["app"],
            "--",
            "-UCONFIG_*",
            f"-DBOARD_ROOT={board_root.as_posix()}",
            f"-DEXTRA_ZEPHYR_MODULES={paths['platform_root'].as_posix()}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ]
    )
    ccache = tools.get("ccache")
    if isinstance(ccache, Path) and ccache.is_file():
        command.extend(
            (
                f"-DCMAKE_C_COMPILER_LAUNCHER={ccache.as_posix()}",
                f"-DCMAKE_CXX_COMPILER_LAUNCHER={ccache.as_posix()}",
            )
        )
    overlay = paths["app"] / "app.overlay"
    if overlay.is_file():
        command.append(f"-DDTC_OVERLAY_FILE={overlay.as_posix()}")
    return command


## @brief west build가 application과 build directory의 volume에서 실행될 작업 directory를 반환합니다.
def west_build_working_directory(paths: dict[str, Path]) -> Path:
    app_root = paths["app"]
    build_root = paths["zephyr_build"]
    if app_root.drive.casefold() != build_root.drive.casefold():
        raise AdapterError(
            "[NU54:E_BUILD_VOLUME] application과 Zephyr build directory가 서로 다른 volume에 있습니다: "
            f"{app_root} != {build_root}"
        )
    return app_root


## @brief Zephyr application template과 사용자 config/overlay를 materialize합니다.
def materialize_application(
    paths: dict[str, Path], args: argparse.Namespace,
    selected_library_names: Sequence[str] = (),
) -> None:
    platform_root = paths["platform_root"]
    sketch_root = paths["sketch_root"]
    app_root = paths["app"]
    template = platform_root / "tools" / "nu54-builder" / "templates" / "zephyr-app"
    for required in ("CMakeLists.txt", "prj.conf", "app.overlay", "sources.cmake", "src/bootstrap.cpp"):
        if not (template / required).is_file():
            raise AdapterError(f"Zephyr application template이 불완전합니다: {template / required}")
    app_root.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes_if_changed(app_root / "CMakeLists.txt", (template / "CMakeLists.txt").read_bytes())
    atomic_write_bytes_if_changed(app_root / "src" / "bootstrap.cpp", (template / "src" / "bootstrap.cpp").read_bytes())
    sources = app_root / "sources.cmake"
    if not sources.exists():
        atomic_write_bytes(sources, (template / "sources.cmake").read_bytes())

    profile = load_configuration_profile(
        platform_root,
        getattr(args, "profile", DEFAULT_PROFILE),
        fqbn=args.fqbn,
        zephyr_board=args.board,
    )
    features = resolve_library_features(platform_root, profile, selected_library_names)
    base_config = (template / "prj.conf").read_text(encoding="utf-8").rstrip() + "\n"
    base_config += "\n# Selected profile: " + profile["id"] + "\n" + profile["conf_path"].read_text(encoding="utf-8").rstrip() + "\n"
    for feature in features:
        for relative in feature["conf"]:
            base_config += "\n# Library feature: " + feature["id"] + "\n" + declared_path(feature["root"], relative, "E_FEATURE_PATH").read_text(encoding="utf-8").rstrip() + "\n"
    sketch_config = sketch_root / "prj.conf"
    if sketch_config.is_file():
        base_config += "\n# Sketch prj.conf\n" + sketch_config.read_text(encoding="utf-8").rstrip() + "\n"
    atomic_write_text(app_root / "prj.conf", base_config)

    generated_overlay = app_root / "app.overlay"
    base_overlay = (template / "app.overlay").read_text(encoding="utf-8").rstrip() + "\n"
    base_overlay += "\n/** @brief 선택한 구성 profile의 overlay입니다. */\n" + profile["overlay_path"].read_text(encoding="utf-8").rstrip() + "\n"
    for feature in features:
        for relative in feature["overlays"]:
            base_overlay += "\n/** @brief 허용된 bundled library feature overlay입니다. */\n" + declared_path(feature["root"], relative, "E_FEATURE_PATH").read_text(encoding="utf-8").rstrip() + "\n"
    sketch_overlay = sketch_root / "app.overlay"
    if sketch_overlay.is_file():
        combined_overlay = (
            base_overlay
            + "\n/** Sketch가 제공한 app.overlay override입니다. */\n"
            + sketch_overlay.read_text(encoding="utf-8").rstrip()
            + "\n"
        )
        atomic_write_text(generated_overlay, combined_overlay)
    else:
        atomic_write_text(generated_overlay, base_overlay)


## @brief 생성된 devicetree에서 이름을 가진 mapped partition의 주소와 크기를 반환합니다.
def generated_mapped_partition(
    devicetree: str, label: str, *, required: bool = True
) -> tuple[int, int] | None:
    node = re.search(
        rf"^\s*{re.escape(label)}:\s+partition@[0-9a-fA-F]+\s*\{{(?P<body>.*?)^\s*\}};",
        devicetree,
        re.MULTILINE | re.DOTALL,
    )
    if node is None:
        if required:
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] generated devicetree에 {label} partition이 없습니다."
            )
        return None
    body = node.group("body")
    if not re.search(r'compatible\s*=\s*"zephyr,mapped-partition"\s*;', body):
        raise AdapterError(
            f"[NU54:E_MEMORY_LAYOUT] {label}이 zephyr,mapped-partition이 아닙니다."
        )
    region = re.search(
        r"reg\s*=\s*<\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*>\s*;",
        body,
    )
    if region is None:
        raise AdapterError(
            f"[NU54:E_MEMORY_LAYOUT] {label} partition의 reg 영역을 해석할 수 없습니다."
        )
    address, size = (int(value, 16) for value in region.groups())
    if size <= 0:
        raise AdapterError(f"[NU54:E_MEMORY_LAYOUT] {label} partition 크기가 0입니다.")
    return address, size


## @brief 선택한 code partition과 실제 linker FLASH 영역이 같은지 fail-closed로 검증합니다.
def validate_linked_code_partition(zephyr_output: Path) -> dict[str, int | str]:
    configuration_path = zephyr_output / ".config"
    devicetree_path = zephyr_output / "zephyr.dts"
    map_path = zephyr_output / "zephyr.map"
    for required in (configuration_path, devicetree_path, map_path):
        if not required.is_file():
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] linker memory 검증 입력이 없습니다: {required}"
            )

    configuration = configuration_path.read_text(encoding="utf-8")
    for symbol in ("CONFIG_USE_DT_CODE_PARTITION", "CONFIG_FLASH_USES_MAPPED_PARTITION"):
        if not re.search(rf"^{re.escape(symbol)}=y\s*$", configuration, re.MULTILINE):
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] {symbol}=y가 아니므로 linker 경계를 보장할 수 없습니다."
            )

    devicetree = devicetree_path.read_text(encoding="utf-8")
    chosen = re.search(
        r"zephyr,code-partition\s*=\s*&([A-Za-z_][A-Za-z0-9_]*)\s*;",
        devicetree,
    )
    if chosen is None:
        raise AdapterError(
            "[NU54:E_MEMORY_LAYOUT] /chosen/zephyr,code-partition을 해석할 수 없습니다."
        )
    code_label = chosen.group(1)
    code_region = generated_mapped_partition(devicetree, code_label)
    assert code_region is not None
    code_start, code_size = code_region
    code_end = code_start + code_size

    reserved_regions: list[tuple[str, int, int]] = []
    for label in ("arduino_fs_partition", "storage_partition"):
        region = generated_mapped_partition(devicetree, label, required=False)
        if region is not None:
            start, size = region
            reserved_regions.append((label, start, start + size))
    for label, start, end in reserved_regions:
        if max(code_start, start) < min(code_end, end):
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] code partition이 {label}과 겹칩됩니다: "
                f"0x{code_start:x}..0x{code_end:x} / 0x{start:x}..0x{end:x}"
            )
    ordered_reserved = sorted(reserved_regions, key=lambda item: item[1])
    for previous, current in zip(ordered_reserved, ordered_reserved[1:]):
        if previous[2] > current[1]:
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] {previous[0]}와 {current[0]} 저장소가 겹칩됩니다."
            )

    memory_map = map_path.read_text(encoding="utf-8")
    flash = re.search(
        r"^FLASH\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+\S+\s*$",
        memory_map,
        re.MULTILINE,
    )
    if flash is None:
        raise AdapterError("[NU54:E_MEMORY_LAYOUT] linker map의 FLASH 영역을 해석할 수 없습니다.")
    linker_start, linker_size = (int(value, 16) for value in flash.groups())
    if (linker_start, linker_size) != code_region:
        raise AdapterError(
            "[NU54:E_MEMORY_LAYOUT] linker FLASH 영역과 devicetree code partition이 다릅니다: "
            f"linker=0x{linker_start:x}+0x{linker_size:x}, "
            f"devicetree=0x{code_start:x}+0x{code_size:x}"
        )
    return {
        "code_partition": code_label,
        "flash_origin": code_start,
        "flash_size": code_size,
        "flash_end": code_end,
    }


## @brief cache key 변경 시 이전 placeholder와 source record만 안전하게 무효화합니다.
def invalidate_source_records(paths: dict[str, Path]) -> None:
    records_root = paths["records"]
    if not records_root.is_dir():
        return
    for record_file in records_root.glob("*.json"):
        try:
            record = load_json_object(record_file, "E_SOURCE_RECORD")
        except AdapterError:
            record = {}
        object_value = record.get("object")
        if isinstance(object_value, str):
            object_path = canonical_path(object_value)
            if is_within(object_path, paths["build_path"]):
                for candidate in (object_path, object_path.with_suffix(".d")):
                    try:
                        candidate.unlink()
                    except FileNotFoundError:
                        pass
        try:
            record_file.unlink()
        except FileNotFoundError:
            pass


## @brief 현재 고정 입력으로 Zephyr configure-only를 수행하고 context를 기록합니다.
def prepare(args: argparse.Namespace) -> dict[str, Any]:
    session_paths = adapter_paths(args)
    platform_root = session_paths["platform_root"]
    board_root = platform_root / "board_package" / "NU54DK_Zephyr_DTS"
    if not (board_root / "boards" / "nucode" / "nu54dk" / "board.yml").is_file():
        raise AdapterError(f"NU54DK board package를 찾을 수 없습니다: {board_root}")
    cache_root = build_cache_root()
    if cache_root == platform_root or is_within(cache_root, platform_root):
        raise AdapterError(
            "M9 build cache를 platform/board fingerprint 내부에 둘 수 없습니다: "
            f"{cache_root}"
        )
    tools = tool_environment(platform_root)
    input_manifest = cache_input_manifest(session_paths, args, tools)
    cache_key = cache_key_for_manifest(input_manifest)
    workspace = cache_workspace(cache_key, root=cache_root)
    paths = add_workspace_paths(session_paths, workspace)
    paths["build_path"].mkdir(parents=True, exist_ok=True)
    paths["state_root"].mkdir(parents=True, exist_ok=True)

    with build_lock(paths["state_root"], operation="prepare-session"):
        # Arduino의 library 선택과 include graph는 cache key와 독립적으로 바뀔 수 있습니다.
        # Placeholder만 매번 지워 graph를 다시 수집하고 실제 compile은 Ninja가 증분 판정합니다.
        invalidate_source_records(paths)
        workspace.mkdir(parents=True, exist_ok=True)
        with build_lock(workspace, operation="prepare-cache"):
            input_path = workspace / "input-manifest.json"
            stored_input: dict[str, Any] | None = None
            if input_path.is_file():
                try:
                    stored_input = load_json_object(input_path, "E_CACHE_INPUT")
                except AdapterError:
                    stored_input = None
            if (
                stored_input is not None
                and cache_key_for_manifest(stored_input) != cache_key
            ):
                raise AdapterError(
                    "[NU54:E_CACHE_KEY_COLLISION] 축약 cache directory의 전체 SHA-256이 다릅니다."
                )
            state_path = workspace / "state.json"
            state_document: dict[str, Any] | None = None
            if state_path.is_file():
                try:
                    state_document = load_json_object(state_path, "E_CACHE_STATE")
                except AdapterError:
                    state_document = None
            stored_state_key = (state_document or {}).get("cache_key")
            if (
                isinstance(stored_state_key, str)
                and re.fullmatch(r"[0-9a-f]{64}", stored_state_key)
                and stored_state_key != cache_key
            ):
                raise AdapterError(
                    "[NU54:E_CACHE_KEY_COLLISION] 축약 cache directory의 state SHA-256이 다릅니다."
                )

            # 전체 key 충돌 여부를 확인한 뒤에만 persistent tree를 변경합니다.
            materialize_application(paths, args)

            cache_exists = (paths["zephyr_build"] / "CMakeCache.txt").is_file()
            build_graph_exists = (paths["zephyr_build"] / "build.ninja").is_file()
            input_matches = stored_input == input_manifest
            state_matches = bool(
                state_document
                and state_document.get("schema_version") == CACHE_SCHEMA_VERSION
                and state_document.get("cache_key") == cache_key
                and state_document.get("state") == "ready"
                and state_document.get("first_configure_complete") is True
                and state_document.get("last_build_result") in {"not-built", "success"}
            )
            configure_required = not (
                cache_exists and build_graph_exists and input_matches and state_matches
            )
            if not cache_exists and not build_graph_exists and stored_input is None:
                configure_reason = "new-cache"
            elif not input_matches:
                configure_reason = "input-manifest-recovery"
            elif not state_matches:
                configure_reason = "state-recovery"
            else:
                configure_reason = "build-graph-recovery"

            atomic_write_json(input_path, input_manifest)
            configure_seconds = 0.0
            pristine_count = int((state_document or {}).get("pristine_configure_count", 0))
            recovery_count = int((state_document or {}).get("recovery_count", 0))
            if configure_required:
                transition_cache_state(
                    workspace,
                    cache_key,
                    "configuring",
                    configure_reason=configure_reason,
                    first_configure_complete=False,
                )
                started = time.perf_counter()
                try:
                    run_checked(
                        configure_command(
                            paths, args, tools, board_root.resolve(), pristine=True
                        ),
                        cwd=west_build_working_directory(paths),
                        environment=tools["environment"],
                    )
                except Exception as error:
                    transition_cache_state(
                        workspace,
                        cache_key,
                        "failed",
                        last_build_result="configure-failed",
                        failure=str(error),
                    )
                    raise
                configure_seconds = time.perf_counter() - started
                pristine_count += 1
                if configure_reason != "new-cache":
                    recovery_count += 1

            transition_cache_state(
                workspace,
                cache_key,
                "ready",
                first_configure_complete=True,
                last_build_result=(
                    "not-built"
                    if configure_required
                    else (state_document or {}).get("last_build_result", "not-built")
                ),
                configure_reason=configure_reason if configure_required else "cache-hit",
                configure_duration_seconds=round(configure_seconds, 6),
                pristine_configure_count=pristine_count,
                recovery_count=recovery_count,
            )
            context = {
                "schema_version": SESSION_CONTEXT_SCHEMA_VERSION,
                "adapter_version": ADAPTER_VERSION,
                "state": "configured",
                "fqbn": args.fqbn,
                "board": args.board,
                "profile": getattr(args, "profile", DEFAULT_PROFILE),
                "sysbuild": False,
                "ncs_version": NCS_VERSION,
                "zephyr_version": "4.4.0",
                "platform_root": platform_root.as_posix(),
                "board_root": board_root.resolve().as_posix(),
                "sketch_root": paths["sketch_root"].as_posix(),
                "build_path": paths["build_path"].as_posix(),
                "cache_schema_version": CACHE_SCHEMA_VERSION,
                "cache_key": cache_key,
                "cache_root": cache_root.as_posix(),
                "cache_dir": workspace.as_posix(),
                "input_manifest": input_path.as_posix(),
                "app_dir": paths["app"].as_posix(),
                "zephyr_build_dir": paths["zephyr_build"].as_posix(),
                "ncs_root": tools["ncs_root"].as_posix(),
                "toolchain_root": tools["toolchain_root"].as_posix(),
                "toolchain_bundle_id": tools["toolchain_root"].name,
                "cxx_compiler": tools["compiler"].as_posix(),
                "size_tool": tools["size"].as_posix(),
                "ccache": tools["ccache"].as_posix() if tools.get("ccache") else None,
                "ccache_dir": tools["ccache_root"].as_posix(),
                "configuration_fingerprint": f"sha256:{cache_key}",
                "configure_mode": "cmake-only",
                "configure_reason": configure_reason if configure_required else "cache-hit",
                "configure_duration_seconds": round(configure_seconds, 6),
                "configure_skipped": not configure_required,
                "cache_reused": not configure_required,
                "pristine_configure_count": pristine_count,
                "recovery_count": recovery_count,
                "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            atomic_write_json(paths["context"], context)
            return context


## @brief context가 없으면 preprocessor 단계에서도 안전하게 최초 configure를 수행합니다.
def load_context(args: argparse.Namespace, create: bool = True) -> dict[str, Any]:
    path = adapter_paths(args)["context"]
    if not path.is_file():
        if not create:
            raise AdapterError(f"configure context가 없습니다: {path}")
        return prepare(args)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"configure context를 읽지 못했습니다: {error}") from error


## @brief Arduino recipe가 전달한 -I include argument를 directory 목록으로 바꿉니다.
def parse_include_arguments(arguments: Sequence[str]) -> list[Path]:
    includes: list[Path] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        value: str | None = None
        if argument == "-I" and index + 1 < len(arguments):
            index += 1
            value = arguments[index]
        elif argument.startswith("-I") and len(argument) > 2:
            value = argument[2:]
        if value:
            includes.append(canonical_path(value.strip('"')))
        index += 1
    unique: dict[str, Path] = {}
    for include in includes:
        unique[path_key(include)] = include
    return list(unique.values())


## @brief Arduino CLI가 뒤에 붙인 dependency 생성 option만 안전하게 전달합니다.
def dependency_arguments(arguments: Sequence[str]) -> list[str]:
    forwarded: list[str] = []
    index = 0
    flags_with_value = {"-MF", "-MT", "-MQ"}
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"-MMD", "-MD", "-MP"}:
            forwarded.append(argument)
        elif argument in flags_with_value and index + 1 < len(arguments):
            forwarded.extend((argument, arguments[index + 1]))
            index += 1
        elif argument.startswith(("-D", "-U")):
            forwarded.append(argument)
        index += 1
    return forwarded


## @brief Arduino prototype 전처리에서 직접 Zephyr/NCS header를 보류할지 확인합니다.
def has_direct_zephyr_include(source: Path) -> bool:
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AdapterError(f"Zephyr/NCS include 탐색용 source를 읽지 못했습니다: {error}") from error
    return re.search(
        r'^\s*#\s*include\s*[<\"](?:zephyr|bluetooth)/', content, re.MULTILINE
    ) is not None


## @brief 직접 Zephyr/NCS include만 같은 줄 수의 Doxygen 주석으로 치환합니다.
def stage_prototype_source(source: Path, temporary_root: Path) -> Path:
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AdapterError(f"Zephyr/NCS include 보류용 source를 읽지 못했습니다: {error}") from error
    pattern = re.compile(
        r'^(?P<indent>\s*)#\s*include\s*[<\"](?:zephyr|bluetooth)/[^>\"]*[>\"].*$',
        re.MULTILINE,
    )
    staged_content, replacements = pattern.subn(
        r'\g<indent>/** @brief Arduino prototype 단계에서는 Zephyr/NCS header 해석을 최종 컴파일까지 보류합니다. */',
        content,
    )
    if replacements == 0:
        return source
    staged = temporary_root / source.name
    atomic_write_text(staged, staged_content)
    return staged


## @brief NCS compiler를 전처리기로 호출하여 Arduino discovery 출력을 만듭니다.
def preprocess(args: argparse.Namespace, passthrough: Sequence[str]) -> None:
    context = load_context(args)
    tools = tool_environment(canonical_path(context["platform_root"]))
    source = canonical_path(args.source)
    if not source.is_file():
        raise AdapterError(f"전처리할 source가 없습니다: {source}")
    platform_root = canonical_path(context["platform_root"])
    include_dirs = [
        platform_root / "cores" / "arduino",
        platform_root / "variants" / "nu54dk",
        platform_root / "third_party" / "ArduinoCore-API",
    ]
    include_dirs.extend(parse_include_arguments(passthrough))
    command: list[str | Path] = [
        context["cxx_compiler"],
        "-w",
        "-x",
        "c++",
        "-std=gnu++17",
        f"-DARDUINO={args.arduino_version}",
        "-DARDUINO_ARCH_ZEPHYR",
        "-DARDUINO_NUCODE_NU54DK",
        f"-DARDUINO_LIBRARY_DISCOVERY_PHASE={args.discovery_phase}",
    ]
    for include in include_dirs:
        command.extend(("-I", include))
    dependencies = dependency_arguments(passthrough)
    if args.mode == "includes":
        command.extend(("-M", "-MG", "-MP", source))
        result = run_checked(command, cwd=canonical_path(context["sketch_root"]), environment=tools["environment"], capture=True)
        sys.stdout.buffer.write(result.stdout)
        return
    if not args.output:
        raise AdapterError("macros 전처리에는 --output이 필요합니다.")
    with tempfile.TemporaryDirectory(prefix="n54-pp-") as temporary:
        prototype_source = source
        if has_direct_zephyr_include(source):
            prototype_source = stage_prototype_source(source, Path(temporary))
            command.extend(("-iquote", source.parent))
        command.extend(dependencies)
        command.extend(("-E", "-CC", prototype_source))
        result = run_checked(
            command,
            cwd=canonical_path(context["sketch_root"]),
            environment=tools["environment"],
            capture=True,
        )
    if args.output.casefold() not in {"nul", "/dev/null"}:
        atomic_write_bytes(canonical_path(args.output), result.stdout)


## @brief object path와 일대일로 대응하는 record file 경로를 계산합니다.
def record_path(records_root: Path, object_path: Path) -> Path:
    digest = hashlib.sha256(path_key(object_path).encode("utf-8")).hexdigest()
    return records_root / f"{digest}.json"


## @brief source graph record와 placeholder object/dependency를 원자적으로 생성합니다.
def record_source(args: argparse.Namespace, passthrough: Sequence[str]) -> None:
    paths = adapter_paths(args)
    context = load_context(args)
    source = canonical_path(args.source)
    object_path = canonical_path(args.object)
    if not source.is_file():
        raise AdapterError(f"기록할 source가 없습니다: {source}")
    if not is_within(object_path, paths["build_path"]):
        raise AdapterError(f"object가 Arduino build directory 밖에 있습니다: {object_path}")
    include_dirs = parse_include_arguments(passthrough)
    include_dirs.append(source.parent)
    unique = {path_key(path): path for path in include_dirs}
    record = {
        "schema_version": SOURCE_RECORD_SCHEMA_VERSION,
        "source": source.as_posix(),
        "object": object_path.as_posix(),
        "language": args.language,
        "include_dirs": [path.as_posix() for path in unique.values()],
        "platform_root": context["platform_root"],
        "cache_key": context["cache_key"],
    }
    atomic_write_json(record_path(paths["records"], object_path), record)
    atomic_write_bytes(object_path, b"")
    dependency = object_path.with_suffix(".d")
    escaped_object = object_path.as_posix().replace(" ", "\\ ")
    escaped_source = source.as_posix().replace(" ", "\\ ")
    atomic_write_text(dependency, f"{escaped_object}: {escaped_source}\n")


## @brief Arduino core archive lifecycle을 만족하는 placeholder archive를 생성합니다.
def create_archive(args: argparse.Namespace) -> None:
    load_context(args)
    archive = canonical_path(args.archive)
    if not archive.exists():
        atomic_write_bytes(archive, b"")


## @brief path가 지정 directory 내부인지 판정합니다.
def is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


## @brief directory가 사용하는 전체 byte 수를 계산합니다.
def directory_size(path: Path) -> int:
    total = 0
    if not path.is_dir():
        return total
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


## @brief cache entry의 운영체제 lock이 현재 다른 worker에 점유됐는지 확인합니다.
def cache_entry_is_locked(entry: Path) -> bool:
    try:
        with operating_system_lock(entry, 0.0):
            return False
    except TimeoutError:
        return True


## @brief 현재 schema namespace의 canonical build cache entry를 나열합니다.
def cache_entries(root: Path | None = None) -> list[dict[str, Any]]:
    cache_root = local_cache_root(root or build_cache_root())
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    entries: list[dict[str, Any]] = []
    if not namespace.is_dir():
        return entries
    for shard in sorted(namespace.iterdir(), key=lambda path: path.name):
        if not shard.is_dir() or not re.fullmatch(r"[0-9a-f]{2}", shard.name):
            continue
        for entry in sorted(shard.iterdir(), key=lambda path: path.name):
            if (
                not entry.is_dir()
                or not re.fullmatch(r"[0-9a-f]{32}", entry.name)
                or entry.name[:2] != shard.name
                or not is_within(entry, namespace)
            ):
                continue
            access_document: dict[str, Any] = {}
            access_path = entry / "access.json"
            if access_path.is_file():
                try:
                    access_document = load_json_object(access_path, "E_CACHE_ACCESS")
                except AdapterError:
                    access_document = {}
            state_document: dict[str, Any] = {}
            state_path = entry / "state.json"
            if state_path.is_file():
                try:
                    state_document = load_json_object(state_path, "E_CACHE_STATE")
                except AdapterError:
                    state_document = {}
            try:
                fallback_access = entry.stat().st_mtime
            except OSError:
                fallback_access = 0.0
            access_text = access_document.get("last_accessed_at_utc")
            try:
                access_timestamp = (
                    dt.datetime.fromisoformat(str(access_text)).timestamp()
                    if access_text
                    else fallback_access
                )
            except ValueError:
                access_timestamp = fallback_access
            full_key = state_document.get("cache_key")
            valid_key = isinstance(full_key, str) and bool(
                re.fullmatch(r"[0-9a-f]{64}", full_key)
            )
            valid_key = bool(valid_key and str(full_key).startswith(entry.name))
            entries.append(
                {
                    "key": full_key if valid_key else None,
                    "directory_key": entry.name,
                    "valid": valid_key,
                    "path": entry,
                    "size": directory_size(entry),
                    "last_access_timestamp": access_timestamp,
                    "last_accessed_at_utc": access_text,
                    "state": state_document.get("state", "unknown"),
                    "locked": cache_entry_is_locked(entry),
                    "pinned": (entry / ".pin").exists(),
                }
            )
    return entries


## @brief 검증된 canonical entry를 운영체제 lock 안에서 재귀 삭제합니다.
def remove_cache_entry_path(
    entry: Path,
    *,
    namespace: Path,
    expected_key: str | None,
    lock_timeout: float,
    operation: str,
) -> int:
    namespace = canonical_path(namespace)
    resolved_entry = canonical_path(entry)
    try:
        relative = resolved_entry.relative_to(namespace)
    except ValueError as error:
        raise AdapterError(f"cache root 밖의 경로는 삭제할 수 없습니다: {resolved_entry}") from error
    if (
        len(relative.parts) != 2
        or not re.fullmatch(r"[0-9a-f]{2}", relative.parts[0])
        or not re.fullmatch(r"[0-9a-f]{32}", relative.parts[1])
        or relative.parts[1][:2] != relative.parts[0]
    ):
        raise AdapterError(f"canonical cache entry가 아닌 경로는 삭제할 수 없습니다: {resolved_entry}")
    try:
        with operating_system_lock(resolved_entry, lock_timeout):
            if not resolved_entry.exists():
                return 0
            if (resolved_entry / ".pin").exists():
                raise AdapterError(f"고정된 cache entry는 삭제할 수 없습니다: {resolved_entry.name}")
            if expected_key is not None:
                state_path = resolved_entry / "state.json"
                if not state_path.is_file():
                    raise AdapterError(
                        f"state가 없는 cache entry는 key로 삭제할 수 없습니다: {expected_key}"
                    )
                state_document = load_json_object(state_path, "E_CACHE_STATE")
                if state_document.get("cache_key") != expected_key:
                    raise AdapterError(
                        "[NU54:E_CACHE_KEY_COLLISION] 삭제 요청과 cache state의 전체 SHA-256이 다릅니다."
                    )
            size = directory_size(resolved_entry)
            shutil.rmtree(resolved_entry)
    except TimeoutError as error:
        raise CacheBusyError(
            f"[NU54:E_CACHE_BUSY] 활성 worker가 사용 중인 cache entry입니다: {resolved_entry.name}"
        ) from error
    try:
        resolved_entry.parent.rmdir()
    except OSError:
        pass
    return size


## @brief 검증된 cache entry 하나를 maintenance 및 entry lock 안에서 삭제합니다.
def remove_cache_entry(
    cache_key: str,
    *,
    root: Path | None = None,
    lock_timeout: float = 0.05,
) -> int:
    if not re.fullmatch(r"[0-9a-f]{64}", cache_key):
        raise AdapterError(f"cache key 형식이 잘못되었습니다: {cache_key}")
    cache_root = local_cache_root(root or build_cache_root())
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    entry = cache_workspace(cache_key, root=cache_root)
    with build_lock(cache_root / ".maintenance", operation="cache-remove"):
        return remove_cache_entry_path(
            entry,
            namespace=namespace,
            expected_key=cache_key,
            lock_timeout=lock_timeout,
            operation="cache-remove",
        )


## @brief quota와 LRU 정책에 따라 비활성 build cache를 안전하게 정리합니다.
def prune_build_cache(
    *,
    current_key: str | None = None,
    root: Path | None = None,
    max_bytes: int | None = None,
    max_entries: int | None = None,
) -> dict[str, Any]:
    configured_max_bytes = max_bytes or positive_environment_integer(
        "NUCODE_BUILD_CACHE_MAX_BYTES", DEFAULT_BUILD_CACHE_MAX_BYTES
    )
    configured_max_entries = max_entries or positive_environment_integer(
        "NUCODE_BUILD_CACHE_MAX_ENTRIES", DEFAULT_BUILD_CACHE_MAX_ENTRIES
    )
    cache_root = local_cache_root(root or build_cache_root())
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with build_lock(cache_root / ".maintenance", operation="cache-prune"):
        entries = cache_entries(cache_root)
        total_size = sum(int(entry["size"]) for entry in entries)
        candidates = sorted(entries, key=lambda entry: float(entry["last_access_timestamp"]))
        remaining_count = len(entries)
        for entry in candidates:
            if total_size <= configured_max_bytes and remaining_count <= configured_max_entries:
                break
            if entry["key"] == current_key or entry["pinned"]:
                continue
            try:
                removed_size = remove_cache_entry_path(
                    entry["path"],
                    namespace=namespace,
                    expected_key=str(entry["key"]) if entry["valid"] else None,
                    lock_timeout=0.0,
                    operation="cache-prune",
                )
            except AdapterError as error:
                skipped.append({"directory_key": entry["directory_key"], "reason": str(error)})
                continue
            removed.append(
                {
                    "key": entry["key"],
                    "directory_key": entry["directory_key"],
                    "bytes": removed_size,
                }
            )
            total_size -= removed_size
            remaining_count -= 1
    return {
        "schema_version": 1,
        "max_bytes": configured_max_bytes,
        "max_entries": configured_max_entries,
        "remaining_bytes": total_size,
        "remaining_entries": remaining_count,
        "removed": removed,
        "skipped": skipped,
        "quota_satisfied": (
            total_size <= configured_max_bytes and remaining_count <= configured_max_entries
        ),
    }


## @brief ccache 자체 동시성 제어를 사용해 compiler cache 내용만 비웁니다.
def clear_compiler_cache(cache_root: Path) -> int:
    compiler_cache = cache_root / "compiler-cache"
    if not compiler_cache.exists():
        return 0
    if not is_within(compiler_cache, cache_root) or compiler_cache == cache_root:
        raise AdapterError(f"compiler cache 경로가 잘못되었습니다: {compiler_cache}")
    removed_bytes = directory_size(compiler_cache)
    tools = tool_environment()
    ccache = tools.get("ccache")
    if not isinstance(ccache, Path) or not ccache.is_file():
        raise AdapterError("compiler cache를 안전하게 비울 ccache 실행 파일이 없습니다.")
    environment = tools["environment"].copy()
    environment["CCACHE_DIR"] = str(compiler_cache)
    run_checked([ccache, "--clear"], cwd=cache_root, environment=environment)
    return removed_bytes


## @brief 비활성 build cache 전체와 선택한 compiler cache를 안전하게 비웁니다.
def clear_build_cache(cache_root: Path, *, include_compiler: bool) -> dict[str, Any]:
    cache_root = local_cache_root(cache_root)
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with build_lock(cache_root / ".maintenance", operation="cache-clear"):
        for entry in cache_entries(cache_root):
            if entry["pinned"]:
                skipped.append({"directory_key": entry["directory_key"], "reason": "pinned"})
                continue
            try:
                removed_size = remove_cache_entry_path(
                    entry["path"],
                    namespace=namespace,
                    expected_key=str(entry["key"]) if entry["valid"] else None,
                    lock_timeout=0.0,
                    operation="cache-clear",
                )
            except AdapterError as error:
                skipped.append({"directory_key": entry["directory_key"], "reason": str(error)})
                continue
            removed.append(
                {
                    "key": entry["key"],
                    "directory_key": entry["directory_key"],
                    "bytes": removed_size,
                }
            )
        compiler_removed = clear_compiler_cache(cache_root) if include_compiler else 0
    return {
        "removed": removed,
        "skipped": skipped,
        "compiler_cache_removed_bytes": compiler_removed,
    }


## @brief cache 관리 CLI 작업을 수행합니다.
def manage_cache(args: argparse.Namespace) -> None:
    root = local_cache_root(args.cache_root) if args.cache_root else build_cache_root()
    action = args.cache_action
    try:
        if action == "list":
            result: Any = [
                {key: value.as_posix() if isinstance(value, Path) else value for key, value in entry.items()}
                for entry in cache_entries(root)
            ]
        elif action == "inspect":
            matching = [entry for entry in cache_entries(root) if entry["key"] == args.key]
            if not matching:
                raise AdapterError(f"cache entry를 찾을 수 없습니다: {args.key}")
            entry = matching[0]
            result = {
                key: value.as_posix() if isinstance(value, Path) else value
                for key, value in entry.items()
            }
            for filename in ("input-manifest.json", "state.json", "access.json"):
                document_path = entry["path"] / filename
                if document_path.is_file():
                    result[filename] = load_json_object(document_path, "E_CACHE_METADATA")
        elif action == "prune":
            result = prune_build_cache(root=root)
        elif action == "remove":
            result = {"key": args.key, "removed_bytes": remove_cache_entry(args.key, root=root)}
        elif action == "clear":
            result = clear_build_cache(root, include_compiler=args.include_compiler)
        else:
            raise AdapterError(f"알 수 없는 cache action입니다: {action}")
    except OSError as error:
        raise AdapterError(f"cache {action} 작업 중 filesystem 오류가 발생했습니다: {error}") from error
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


## @brief 현재 Arduino session이 가리키는 build tree만 제거합니다.
def clean_build(args: argparse.Namespace) -> None:
    paths = adapter_paths(args)
    with build_lock(paths["state_root"], operation="clean-session"):
        context = load_context(args, create=False)
        cache_key = context.get("cache_key")
        if not isinstance(cache_key, str):
            raise AdapterError("현재 session에 cache key가 없습니다.")
        contextual_paths = paths_from_context(paths, context)
        cache_root = local_cache_root(str(context["cache_root"]))
        removed_bytes = remove_cache_entry(cache_key, root=cache_root)
        if contextual_paths["workspace"].exists():
            raise AdapterError("현재 session의 cache tree 삭제가 완료되지 않았습니다.")
        for path in (
            paths["context"],
            paths["build_path"] / f"{args.project_name}.nu54-build.json",
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    print(json.dumps({"cache_key": cache_key, "removed_bytes": removed_bytes}, sort_keys=True))


## @brief link recipe object 목록에 대응하는 검증된 sketch/library record를 읽습니다.
def records_for_objects(
    paths: dict[str, Path], objects: Sequence[str], context: dict[str, Any]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for object_name in objects:
        if not object_name:
            continue
        object_path = canonical_path(object_name)
        if not is_within(object_path, paths["build_path"]):
            raise AdapterError(f"object가 Arduino build directory 밖에 있습니다: {object_path}")
        record_file = record_path(paths["records"], object_path)
        if not record_file.is_file():
            if object_path.suffix.lower() in {".a", ".ar"}:
                raise AdapterError(f"M5는 precompiled Arduino library를 지원하지 않습니다: {object_path}")
            missing.append(object_path.as_posix())
            continue
        record = load_json_object(record_file, "E_SOURCE_RECORD")
        include_dirs = record.get("include_dirs")
        if (
            record.get("schema_version") != SOURCE_RECORD_SCHEMA_VERSION
            or record.get("language") not in {"c", "cxx", "asm"}
            or not isinstance(record.get("source"), str)
            or not isinstance(record.get("object"), str)
            or path_key(record["object"]) != path_key(object_path)
            or not isinstance(include_dirs, list)
            or not all(isinstance(value, str) for value in include_dirs)
            or path_key(str(record.get("platform_root", "")))
            != path_key(paths["platform_root"])
            or record.get("cache_key") != context.get("cache_key")
        ):
            raise AdapterError(
                f"[NU54:E_SOURCE_RECORD_STALE] source record가 현재 build context와 다릅니다: {record_file}"
            )
        records.append(record)
    if missing:
        raise AdapterError("object에 대응하는 source record가 없습니다: " + ", ".join(missing))
    return records


## @brief source record에서 실제 선택된 bundled Arduino library 이름만 수집합니다.
def selected_bundled_libraries(
    paths: dict[str, Path], records: Sequence[dict[str, Any]]
) -> list[str]:
    libraries_root = paths["platform_root"] / "libraries"
    selected: set[str] = set()
    for record in records:
        candidates = [canonical_path(record["source"])]
        candidates.extend(canonical_path(value) for value in record.get("include_dirs", []) if isinstance(value, str))
        for candidate in candidates:
            if not is_within(candidate, libraries_root):
                continue
            try:
                relative = candidate.relative_to(libraries_root)
            except ValueError:
                continue
            if relative.parts and relative.parts[0] in FEATURE_ALLOWLIST:
                selected.add(relative.parts[0])
    return sorted(selected, key=str.casefold)


## @brief 최종 feature cache key로 source record와 context를 원자적으로 이관합니다.
def migrate_feature_workspace(
    session_paths: dict[str, Path], args: argparse.Namespace, tools: dict[str, Any],
    context: dict[str, Any], records: Sequence[dict[str, Any]],
    selected_libraries: Sequence[str], input_manifest: dict[str, Any],
) -> tuple[dict[str, Path], dict[str, Any], str]:
    cache_key = cache_key_for_manifest(input_manifest)
    if context.get("cache_key") == cache_key:
        context.update({
            "selected_libraries": list(selected_libraries),
            "selected_features": input_manifest.get("configuration", {}).get("selected_features", []),
        })
        atomic_write_json(session_paths["context"], context)
        return paths_from_context(session_paths, context), context, cache_key
    cache_root = local_cache_root(str(context["cache_root"]))
    workspace = cache_workspace(cache_key, root=cache_root)
    paths = add_workspace_paths(session_paths, workspace)
    board_root = canonical_path(context["board_root"])
    workspace.mkdir(parents=True, exist_ok=True)
    with build_lock(workspace, operation="feature-cache-migration"):
        input_path = workspace / "input-manifest.json"
        stored = load_json_object(input_path, "E_CACHE_INPUT") if input_path.is_file() else None
        state = load_json_object(workspace / "state.json", "E_CACHE_STATE") if (workspace / "state.json").is_file() else None
        if stored is not None and cache_key_for_manifest(stored) != cache_key:
            raise AdapterError("[NU54:E_CACHE_KEY_COLLISION] feature cache directory의 전체 SHA-256이 다릅니다.")
        stored_state_key = (state or {}).get("cache_key")
        if isinstance(stored_state_key, str) and re.fullmatch(r"[0-9a-f]{64}", stored_state_key) and stored_state_key != cache_key:
            raise AdapterError("[NU54:E_CACHE_KEY_COLLISION] feature cache state의 전체 SHA-256이 다릅니다.")
        reusable = bool(stored == input_manifest and state and state.get("cache_key") == cache_key and state.get("state") == "ready" and state.get("first_configure_complete") is True and (paths["zephyr_build"] / "CMakeCache.txt").is_file() and (paths["zephyr_build"] / "build.ninja").is_file())
        materialize_application(paths, args, selected_libraries)
        atomic_write_json(input_path, input_manifest)
        configure_seconds = 0.0
        if not reusable:
            transition_cache_state(workspace, cache_key, "configuring", first_configure_complete=False, configure_reason="selected-features")
            started = time.perf_counter()
            try:
                run_checked(
                    configure_command(paths, args, tools, board_root, pristine=True),
                    cwd=west_build_working_directory(paths),
                    environment=tools["environment"],
                )
            except Exception as error:
                transition_cache_state(workspace, cache_key, "failed", first_configure_complete=False, last_build_result="configure-failed", failure=str(error))
                raise
            configure_seconds = time.perf_counter() - started
            transition_cache_state(workspace, cache_key, "ready", first_configure_complete=True, last_build_result="not-built", configure_reason="selected-features", configure_duration_seconds=round(configure_seconds, 6), pristine_configure_count=int((state or {}).get("pristine_configure_count", 0)) + 1)
    old_key = str(context["cache_key"])
    context.update({
        "cache_key": cache_key,
        "cache_dir": workspace.as_posix(),
        "input_manifest": (workspace / "input-manifest.json").as_posix(),
        "app_dir": paths["app"].as_posix(),
        "zephyr_build_dir": paths["zephyr_build"].as_posix(),
        "configuration_fingerprint": f"sha256:{cache_key}",
        "selected_libraries": list(selected_libraries),
        "selected_features": input_manifest.get("configuration", {}).get("selected_features", []),
        "provisional_cache_key": old_key,
        "configure_reason": "feature-cache-hit" if reusable else "selected-features",
        "configure_duration_seconds": round(configure_seconds, 6),
        "configure_skipped": reusable,
        "cache_reused": reusable,
        "pristine_configure_count": int((state or {}).get("pristine_configure_count", 0)) + (0 if reusable else 1),
    })
    atomic_write_json(session_paths["context"], context)
    for record in records:
        record["cache_key"] = cache_key
        atomic_write_json(record_path(session_paths["records"], canonical_path(record["object"])), record)
    return paths, context, cache_key


## @brief CMake string literal에 사용할 path를 escape합니다.
def cmake_quote(path: Path) -> str:
    return path.as_posix().replace("\\", "/").replace("\"", "\\\"").replace(";", "\\;")


## @brief Arduino 임시 build path와 무관한 source logical identity를 생성합니다.
def source_logical_identity(source: Path, paths: dict[str, Path]) -> str:
    if is_within(source, paths["build_path"]):
        try:
            relative = source.resolve().relative_to(paths["build_path"].resolve()).as_posix()
        except ValueError:
            relative = source.name
        return f"arduino-generated:{relative}"
    if is_within(source, paths["sketch_root"]):
        relative = source.resolve().relative_to(paths["sketch_root"].resolve()).as_posix()
        return f"sketch:{relative}"
    if is_within(source, paths["platform_root"]):
        relative = source.resolve().relative_to(paths["platform_root"].resolve()).as_posix()
        return f"platform:{relative}"
    return f"external:{path_key(source)}"


## @brief source record를 결정적인 sources.cmake와 provenance로 변환합니다.
def write_source_manifest(
    paths: dict[str, Path], records: Sequence[dict[str, Any]]
) -> tuple[list[Path], dict[str, Any], bool]:
    core_root = paths["platform_root"] / "cores"
    variant_root = paths["platform_root"] / "variants"
    sources: list[Path] = []
    source_keys: set[str] = set()
    includes: list[Path] = []
    include_keys: set[str] = set()

    def add_include(include: Path) -> None:
        key = path_key(include)
        if key not in include_keys and include.is_dir() and not is_within(include, paths["build_path"]):
            include_keys.add(key)
            includes.append(include)

    # Arduino의 sketch-local header 우선권을 보존합니다.
    add_include(paths["sketch_root"])
    for record in records:
        source = canonical_path(record["source"])
        if is_within(source, core_root) or is_within(source, variant_root):
            continue
        if not source.is_file():
            raise AdapterError(f"Arduino source가 사라졌습니다: {source}")
        source_key = path_key(source)
        if source_key not in source_keys:
            source_keys.add(source_key)
            sources.append(source)
        for value in record.get("include_dirs", []):
            add_include(canonical_path(value))
        if not is_within(source.parent, paths["build_path"]):
            add_include(source.parent)

    compiled_sources: list[Path] = []
    source_inputs: list[dict[str, str]] = []
    mirror_root = paths["app"] / "generated-sources"
    mirror_owners: dict[str, str] = {}
    for source in sources:
        logical_identity = source_logical_identity(source, paths)
        compiled_source = source
        if is_within(source, paths["build_path"]):
            relative = source.resolve().relative_to(paths["build_path"].resolve())
            mirror = canonical_path(mirror_root / relative)
            if not is_within(mirror, mirror_root):
                raise AdapterError(f"[NU54:E_SOURCE_MIRROR_PATH] mirror 경로가 잘못되었습니다: {mirror}")
            mirror_key = path_key(mirror)
            previous_owner = mirror_owners.get(mirror_key)
            if previous_owner is not None and previous_owner != logical_identity:
                raise AdapterError(
                    "[NU54:E_SOURCE_MIRROR_COLLISION] 서로 다른 source가 같은 mirror를 사용합니다: "
                    f"{previous_owner}, {logical_identity}"
                )
            mirror_owners[mirror_key] = logical_identity
            atomic_write_bytes_if_changed(mirror, source.read_bytes())
            compiled_source = mirror
            add_include(mirror.parent)
        compiled_sources.append(compiled_source)
        source_inputs.append(
            {
                "logical_identity": logical_identity,
                "source_path": source.as_posix(),
                "compiled_path": compiled_source.as_posix(),
                "sha256": file_sha256(source),
            }
        )

    lines = ["# nu54-builder가 원자적으로 생성한 source manifest입니다.", "set(NUCODE_ARDUINO_SKETCH_SOURCES"]
    lines.extend(f'  "{cmake_quote(path)}"' for path in compiled_sources)
    lines.append(")")
    lines.append("set(NUCODE_ARDUINO_INCLUDE_DIRS")
    lines.extend(f'  "{cmake_quote(path)}"' for path in includes)
    lines.extend((")", ""))
    changed = atomic_write_text(paths["app"] / "sources.cmake", "\n".join(lines))
    provenance = {
        "sources": source_inputs,
        "include_roots": [
            {
                "path": include.as_posix(),
                "content_sha256": tree_content_sha256(include, (".",)),
            }
            for include in includes
        ],
    }
    return sources, provenance, changed


## @brief Zephyr artifact를 Arduino build path로 원자적으로 복사합니다.
def copy_artifact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise AdapterError(f"Zephyr artifact가 없습니다: {source}")
    atomic_write_bytes(destination, source.read_bytes())


## @brief 모든 artifact를 staging한 뒤 한 generation으로 export하고 실패 시 복원합니다.
def export_artifacts_transactionally(
    artifacts: dict[str, Path], build_path: Path, project_name: str
) -> dict[str, Any]:
    staging_parent = build_path / CONTEXT_DIRECTORY / "artifact-staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="generation-", dir=staging_parent))
    backup = staging / "backup"
    backup.mkdir()
    staged: dict[str, Path] = {}
    destinations: dict[str, Path] = {}
    exported: dict[str, Any] = {}
    committed: list[str] = []
    preserve_staging = False
    try:
        for extension, source in artifacts.items():
            staged_path = staging / f"new.{extension}"
            copy_artifact(source, staged_path)
            staged[extension] = staged_path
            destination = build_path / f"{project_name}.{extension}"
            destinations[extension] = destination
            exported[extension] = {
                "path": destination.as_posix(),
                "sha256": file_sha256(staged_path),
                "size": staged_path.stat().st_size,
            }
        for extension, destination in destinations.items():
            if destination.is_file():
                shutil.copy2(destination, backup / extension)
        try:
            for extension in artifacts:
                destination = destinations[extension]
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged[extension], destination)
                committed.append(extension)
            for extension, destination in destinations.items():
                record = exported[extension]
                if (
                    not destination.is_file()
                    or destination.stat().st_size != record["size"]
                    or file_sha256(destination) != record["sha256"]
                ):
                    raise AdapterError(
                        f"[NU54:E_EXPORT_INTEGRITY] export artifact 검증에 실패했습니다: {destination}"
                    )
        except BaseException as original_error:
            try:
                for extension, destination in destinations.items():
                    old_artifact = backup / extension
                    if old_artifact.is_file():
                        os.replace(old_artifact, destination)
                    elif extension in committed:
                        try:
                            destination.unlink()
                        except FileNotFoundError:
                            pass
            except BaseException as rollback_error:
                preserve_staging = True
                raise AdapterError(
                    "[NU54:E_EXPORT_ROLLBACK] artifact 복구에 실패했습니다. "
                    f"수동 복구 directory: {staging}; 원인: {rollback_error}"
                ) from original_error
            raise
        return exported
    finally:
        if not preserve_staging:
            shutil.rmtree(staging, ignore_errors=True)


## @brief artifact와 공개 manifest를 metadata commit 끝까지 하나의 rollback 범위로 묶습니다.
@contextlib.contextmanager
def publish_artifact_generation(
    artifacts: dict[str, Path],
    build_path: Path,
    project_name: str,
    manifest_path: Path,
    context_path: Path,
    rollback_context: dict[str, Any] | None,
) -> Iterator[dict[str, Any]]:
    transaction_root = build_path / CONTEXT_DIRECTORY / "publish-transactions"
    transaction_root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="generation-", dir=transaction_root))
    preserve_backup = False
    destinations = {
        extension: build_path / f"{project_name}.{extension}"
        for extension in artifacts
    }
    existed: dict[str, bool] = {}
    try:
        for extension, destination in destinations.items():
            existed[extension] = destination.is_file()
            if existed[extension]:
                shutil.copy2(destination, backup / extension)
        manifest_existed = manifest_path.is_file()
        if manifest_existed:
            shutil.copy2(manifest_path, backup / "manifest.json")
        context_bytes = context_path.read_bytes() if context_path.is_file() else None
        exported = export_artifacts_transactionally(artifacts, build_path, project_name)
        try:
            yield exported
        except BaseException as original_error:
            try:
                for extension, destination in destinations.items():
                    previous = backup / extension
                    if existed[extension]:
                        os.replace(previous, destination)
                    else:
                        try:
                            destination.unlink()
                        except FileNotFoundError:
                            pass
                if rollback_context is not None:
                    atomic_write_json(context_path, rollback_context)
                elif context_bytes is not None:
                    atomic_write_bytes(context_path, context_bytes)
                else:
                    try:
                        context_path.unlink()
                    except FileNotFoundError:
                        pass
                if manifest_existed:
                    os.replace(backup / "manifest.json", manifest_path)
                else:
                    try:
                        manifest_path.unlink()
                    except FileNotFoundError:
                        pass
            except BaseException as rollback_error:
                preserve_backup = True
                raise AdapterError(
                    "[NU54:E_EXPORT_ROLLBACK] 공개 generation 복구에 실패했습니다. "
                    f"수동 복구 directory: {backup}; 원인: {rollback_error}"
                ) from original_error
            raise
    finally:
        if not preserve_backup:
            shutil.rmtree(backup, ignore_errors=True)


## @brief source manifest를 갱신하고 Full Zephyr image를 build/export합니다.
def link(args: argparse.Namespace) -> None:
    session_paths = adapter_paths(args)
    tools = tool_environment(canonical_path(args.platform_root))
    output_manifest = session_paths["build_path"] / f"{args.project_name}.nu54-build.json"

    with build_lock(session_paths["state_root"], operation="link-session"):
        context = load_context(args, create=False)
        rollback_context: dict[str, Any] | None = None
        if output_manifest.is_file():
            try:
                previous_manifest = load_json_object(output_manifest, "E_ARTIFACT_MANIFEST")
                previous_context = previous_manifest.get("context")
                if isinstance(previous_context, dict):
                    rollback_context = previous_context
            except AdapterError:
                rollback_context = None
        provisional_paths = paths_from_context(session_paths, context)
        records = records_for_objects(provisional_paths, args.objects, context)
        selected_libraries = selected_bundled_libraries(session_paths, records)
        current_input = cache_input_manifest(session_paths, args, tools, selected_libraries)
        paths, context, cache_key = migrate_feature_workspace(
            session_paths, args, tools, context, records, selected_libraries, current_input
        )
        with build_lock(paths["workspace"], operation="link-cache"):
            state_document = load_json_object(paths["workspace"] / "state.json", "E_CACHE_STATE")
            if (
                state_document.get("schema_version") != CACHE_SCHEMA_VERSION
                or state_document.get("cache_key") != cache_key
                or state_document.get("state") != "ready"
                or state_document.get("first_configure_complete") is not True
            ):
                raise AdapterError("[NU54:E_CACHE_STATE] build cache가 ready 상태가 아닙니다.")
            stored_input = load_json_object(
                paths["workspace"] / "input-manifest.json", "E_CACHE_INPUT"
            )
            if stored_input != current_input:
                raise AdapterError("[NU54:E_CACHE_CONTEXT_STALE] cache input manifest가 변경되었습니다.")
            transition_cache_state(
                paths["workspace"], cache_key, "building", last_build_result="running"
            )
            try:
                sources, source_provenance, manifest_changed = write_source_manifest(
                    paths, records
                )
                if not sources:
                    raise AdapterError(
                        "최종 Zephyr build에 전달할 sketch/library source가 없습니다."
                    )
            except Exception as error:
                transition_cache_state(
                    paths["workspace"],
                    cache_key,
                    "failed",
                    last_build_result="source-graph-failed",
                    failure=str(error),
                )
                raise

            ccache_before = read_ccache_stats(tools)
            configure_seconds = 0.0
            build_started = time.perf_counter()
            try:
                if manifest_changed:
                    configure_started = time.perf_counter()
                    run_checked(
                        configure_command(
                            paths,
                            args,
                            tools,
                            canonical_path(context["board_root"]),
                            pristine=False,
                        ),
                        cwd=west_build_working_directory(paths),
                        environment=tools["environment"],
                    )
                    configure_seconds = time.perf_counter() - configure_started
                run_checked(
                    [
                        tools["west"],
                        "-z",
                        tools["zephyr_base"],
                        "build",
                        "-d",
                        paths["zephyr_build"],
                    ],
                    cwd=west_build_working_directory(paths),
                    environment=tools["environment"],
                )
                memory_layout = validate_linked_code_partition(
                    paths["zephyr_build"] / "zephyr"
                )
            except Exception as error:
                transition_cache_state(
                    paths["workspace"],
                    cache_key,
                    "failed",
                    last_build_result="build-failed",
                    failure=str(error),
                )
                raise
            build_seconds = time.perf_counter() - build_started
            try:
                ccache_after = read_ccache_stats(tools)
                zephyr_output = paths["zephyr_build"] / "zephyr"
                artifacts = {
                    "elf": zephyr_output / "zephyr.elf",
                    "hex": zephyr_output / "zephyr.hex",
                    "bin": zephyr_output / "zephyr.bin",
                    "map": zephyr_output / "zephyr.map",
                }
                with publish_artifact_generation(
                    artifacts,
                    paths["build_path"],
                    args.project_name,
                    output_manifest,
                    paths["context"],
                    rollback_context,
                ) as exported:
                    build_record = paths["zephyr_build"] / "nucode_arduino_core_build.yml"
                    if not build_record.is_file():
                        raise AdapterError(
                            f"[NU54:E_BUILD_RECORD] live build record가 없습니다: {build_record}"
                        )
                    source_provenance["live_build_record"] = {
                        "path": build_record.as_posix(),
                        "sha256": file_sha256(build_record),
                    }
                    context.update(
                        {
                            "state": "built",
                            "source_manifest_changed": manifest_changed,
                            "link_configure_duration_seconds": round(configure_seconds, 6),
                            "build_duration_seconds": round(build_seconds, 6),
                            "ccache_stats_before": ccache_before,
                            "ccache_stats_after": ccache_after,
                            "ccache_stats_delta": ccache_delta(ccache_before, ccache_after),
                            "memory_layout": memory_layout,
                            "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                        }
                    )
                    atomic_write_json(paths["context"], context)
                    manifest = {
                    "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
                    "adapter_version": ADAPTER_VERSION,
                    "fqbn": args.fqbn,
                    "board": args.board,
                    "sysbuild": False,
                    "cache": {
                        "schema_version": CACHE_SCHEMA_VERSION,
                        "key": cache_key,
                        "input_manifest": current_input,
                        "cache_dir": paths["workspace"].as_posix(),
                        "source_manifest_sha256": optional_file_sha256(
                            paths["app"] / "sources.cmake"
                        ),
                    },
                    "metrics": {
                        "configure_seconds": round(configure_seconds, 6),
                        "build_seconds": round(build_seconds, 6),
                        "ccache_delta": ccache_delta(ccache_before, ccache_after),
                    },
                    "context": context,
                    "sources": [path.as_posix() for path in sources],
                    "source_inputs": source_provenance,
                    "artifacts": exported,
                    "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    }
                    # Artifact와 context가 모두 완성된 뒤 manifest를 마지막으로 공개합니다.
                    atomic_write_json(output_manifest, manifest)
                    transition_cache_state(
                        paths["workspace"],
                        cache_key,
                        "ready",
                        first_configure_complete=True,
                        last_build_result="success",
                        last_artifact_manifest=output_manifest.as_posix(),
                        last_build_duration_seconds=round(build_seconds, 6),
                    )
            except Exception as error:
                transition_cache_state(
                    paths["workspace"],
                    cache_key,
                    "failed",
                    last_build_result="export-failed",
                    failure=str(error),
                )
                raise
    try:
        prune_build_cache(current_key=cache_key)
    except (AdapterError, OSError) as error:
        print(f"nu54-builder: warning: cache prune를 건너뜁니다: {error}", file=sys.stderr)


## @brief manifest artifact 한 개의 경로, 크기와 SHA-256을 검증합니다.
def validate_manifest_artifact(
    manifest: dict[str, Any], extension: str, build_path: Path
) -> tuple[Path, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get(extension), dict):
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] manifest에 {extension} artifact가 없습니다.")
    record = artifacts[extension]
    artifact = canonical_path(str(record.get("path", "")))
    if not is_within(artifact, build_path):
        raise AdapterError(
            f"[NU54:E_FLASH_ARTIFACT_PATH] {extension} artifact가 Arduino build directory 밖에 있습니다: {artifact}"
        )
    if not artifact.is_file() or artifact.stat().st_size == 0:
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] {extension} artifact가 없습니다: {artifact}")
    expected_size = record.get("size")
    expected_hash = record.get("sha256")
    if not isinstance(expected_size, int) or expected_size != artifact.stat().st_size:
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_HASH] {extension} artifact 크기가 manifest와 다릅니다.")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_HASH] {extension} SHA-256 기록이 잘못되었습니다.")
    actual_hash = file_sha256(artifact)
    if actual_hash != expected_hash:
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_HASH] {extension} artifact SHA-256이 manifest와 다릅니다.")
    return artifact, actual_hash


## @brief M8 upload가 사용할 manifest와 native Zephyr artifact를 검증합니다.
def validate_flash_manifest(args: argparse.Namespace) -> dict[str, Any]:
    build_path = canonical_path(args.build_path)
    manifest_path = canonical_path(args.manifest)
    expected_manifest = build_path / f"{args.project_name}.nu54-build.json"
    if path_key(manifest_path) != path_key(expected_manifest):
        raise AdapterError(
            f"[NU54:E_FLASH_MANIFEST_PATH] 현재 build의 manifest가 아닙니다: {manifest_path}"
        )
    if not manifest_path.is_file():
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] build manifest가 없습니다: {manifest_path}")
    manifest = load_json_object(manifest_path, "E_FLASH_MANIFEST")
    if (
        manifest.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION
        or manifest.get("adapter_version") != ADAPTER_VERSION
    ):
        raise AdapterError("[NU54:E_FLASH_MANIFEST_VERSION] 지원하지 않는 build manifest version입니다.")
    if manifest.get("fqbn") != args.fqbn or manifest.get("board") != args.board:
        raise AdapterError("[NU54:E_FLASH_BOARD_MISMATCH] manifest의 FQBN 또는 Zephyr board가 다릅니다.")
    if manifest.get("sysbuild") is not False:
        raise AdapterError(
            "[NU54:E_FLASH_SYSBUILD_UNSUPPORTED] M8 upload는 non-sysbuild zephyr.hex만 지원합니다."
        )

    context = manifest.get("context")
    if not isinstance(context, dict):
        raise AdapterError("[NU54:E_FLASH_CONTEXT] manifest에 build context가 없습니다.")
    if context.get("schema_version") != SESSION_CONTEXT_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_FLASH_CONTEXT] 지원하지 않는 session context version입니다.")
    if context.get("state") != "built":
        raise AdapterError("[NU54:E_FLASH_CONTEXT] 마지막으로 완료된 build context가 아닙니다.")
    context_pairs = {
        "fqbn": args.fqbn,
        "board": args.board,
        "build_path": build_path.as_posix(),
        "platform_root": canonical_path(args.platform_root).as_posix(),
    }
    for key, expected in context_pairs.items():
        value = context.get(key)
        if key.endswith("_path") or key.endswith("_root"):
            matches = isinstance(value, str) and path_key(value) == path_key(expected)
        else:
            matches = value == expected
        if not matches:
            raise AdapterError(f"[NU54:E_FLASH_CONTEXT] build context의 {key} 값이 현재 요청과 다릅니다.")

    cache = manifest.get("cache")
    if not isinstance(cache, dict) or cache.get("schema_version") != CACHE_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_FLASH_CACHE] manifest의 M9 cache metadata가 잘못되었습니다.")
    cache_key = cache.get("key")
    input_manifest = cache.get("input_manifest")
    if (
        not isinstance(cache_key, str)
        or not re.fullmatch(r"[0-9a-f]{64}", cache_key)
        or not isinstance(input_manifest, dict)
        or cache_key_for_manifest(input_manifest) != cache_key
        or context.get("cache_key") != cache_key
    ):
        raise AdapterError("[NU54:E_FLASH_CACHE] cache key 또는 input manifest가 일치하지 않습니다.")
    contextual_paths = paths_from_context(adapter_paths(args), context)
    if path_key(str(cache.get("cache_dir", ""))) != path_key(contextual_paths["workspace"]):
        raise AdapterError("[NU54:E_FLASH_CACHE] artifact와 context의 cache directory가 다릅니다.")
    stored_input = load_json_object(
        contextual_paths["workspace"] / "input-manifest.json", "E_FLASH_CACHE"
    )
    state_document = load_json_object(
        contextual_paths["workspace"] / "state.json", "E_FLASH_CACHE"
    )
    if stored_input != input_manifest or (
        state_document.get("schema_version") != CACHE_SCHEMA_VERSION
        or state_document.get("cache_key") != cache_key
        or state_document.get("state") != "ready"
        or state_document.get("last_build_result") != "success"
    ):
        raise AdapterError("[NU54:E_FLASH_CACHE] 현재 cache generation이 build manifest와 다릅니다.")

    exported_hex, hex_hash = validate_manifest_artifact(manifest, "hex", build_path)
    exported_elf, elf_hash = validate_manifest_artifact(manifest, "elf", build_path)
    zephyr_build = canonical_path(str(context.get("zephyr_build_dir", "")))
    if path_key(zephyr_build) != path_key(contextual_paths["zephyr_build"]):
        raise AdapterError("[NU54:E_FLASH_CONTEXT] Zephyr build directory가 cache context와 다릅니다.")
    if not (zephyr_build / "CMakeCache.txt").is_file() or not (zephyr_build / "build.ninja").is_file():
        raise AdapterError(f"[NU54:E_FLASH_CONTEXT] 유효한 Zephyr build directory가 아닙니다: {zephyr_build}")
    native_hex = zephyr_build / "zephyr" / "zephyr.hex"
    native_elf = zephyr_build / "zephyr" / "zephyr.elf"
    for extension, native, exported_hash in (
        ("hex", native_hex, hex_hash),
        ("elf", native_elf, elf_hash),
    ):
        if not native.is_file() or native.stat().st_size == 0:
            raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] native {extension} artifact가 없습니다: {native}")
        if file_sha256(native) != exported_hash:
            raise AdapterError(
                f"[NU54:E_FLASH_ARTIFACT_HASH] native {extension}와 export artifact가 다릅니다."
            )
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "build_path": build_path,
        "zephyr_build": zephyr_build,
        "hex": exported_hex,
        "elf": exported_elf,
        "hex_sha256": hex_hash,
        "elf_sha256": elf_hash,
    }


## @brief Zephyr runners.yaml을 YAML parser로 읽고 선택 runner의 고정 인자를 검증합니다.
def validate_runner_configuration(zephyr_build: Path, runner: str) -> Path:
    runners_path = zephyr_build / "zephyr" / "runners.yaml"
    if not runners_path.is_file():
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] runners.yaml이 없습니다: {runners_path}")
    try:
        import yaml

        document = yaml.safe_load(runners_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] runners.yaml을 읽지 못했습니다: {error}") from error
    if not isinstance(document, dict):
        raise AdapterError("[NU54:E_RUNNER_UNAVAILABLE] runners.yaml root가 object가 아닙니다.")
    available = document.get("runners")
    if not isinstance(available, list) or runner not in available:
        names = ", ".join(str(value) for value in available) if isinstance(available, list) else "없음"
        raise AdapterError(
            f"[NU54:E_RUNNER_UNAVAILABLE] 선택 runner가 build에 없습니다: {runner}; available: {names}"
        )
    runner_arguments = document.get("args", {}).get(runner, [])
    if not isinstance(runner_arguments, list):
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] {runner} runner argument 형식이 잘못되었습니다.")
    normalized_arguments = [str(value).casefold() for value in runner_arguments]
    unsafe_runner_arguments = [
        value
        for value in normalized_arguments
        if value in {"--erase", "--recover", "-e"}
        or value.startswith(("--erase=", "--recover="))
        or "mass-erase" in value
        or "chip-erase" in value
    ]
    if unsafe_runner_arguments:
        raise AdapterError(
            "[NU54:E_FLASH_UNSAFE_OPTION] runners.yaml에 destructive option이 있습니다: "
            + ", ".join(unsafe_runner_arguments)
        )
    if runner == "pyocd" and "--target=nrf54l" not in runner_arguments:
        raise AdapterError("[NU54:E_PYOCD_TARGET] pyOCD target이 nrf54l이 아닙니다.")
    if runner == "jlink" and not {
        "--device=nRF54L15_M33",
        "--speed=4000",
    }.issubset(set(runner_arguments)):
        raise AdapterError("[NU54:E_RUNNER_JLINK_UNAVAILABLE] J-Link device 또는 speed metadata가 다릅니다.")
    return runners_path


## @brief pyOCD API를 사용해 연결된 CMSIS-DAP probe UID를 열거합니다.
def discover_pyocd_probe_ids() -> list[str]:
    try:
        from pyocd.core.helpers import ConnectHelper

        probes = ConnectHelper.get_all_connected_probes(blocking=False, print_wait_message=False)
    except Exception as error:
        raise AdapterError(f"[NU54:E_PROBE_NOT_FOUND] pyOCD probe 열거에 실패했습니다: {error}") from error
    return sorted(
        {str(probe.unique_id) for probe in probes if getattr(probe, "unique_id", None)},
        key=str.casefold,
    )


## @brief 명시값과 발견 목록에서 잘못된 자동 선택 없이 pyOCD probe 하나를 결정합니다.
def select_pyocd_probe(requested: str | None, discovered: Sequence[str] | None = None) -> str:
    probe_ids = list(discovered) if discovered is not None else discover_pyocd_probe_ids()
    requested_id = requested.strip() if requested else ""
    if requested_id:
        matches = [value for value in probe_ids if value.casefold() == requested_id.casefold()]
        if not matches:
            raise AdapterError(
                f"[NU54:E_PROBE_NOT_FOUND] 요청한 CMSIS-DAP UID가 없습니다: {requested_id}; "
                f"detected: {', '.join(probe_ids) or '없음'}"
            )
        return matches[0]
    if not probe_ids:
        raise AdapterError("[NU54:E_PROBE_NOT_FOUND] 연결된 CMSIS-DAP probe가 없습니다.")
    if len(probe_ids) != 1:
        raise AdapterError(
            "[NU54:E_PROBE_AMBIGUOUS] 여러 CMSIS-DAP probe가 연결되어 UID 지정이 필요합니다: "
            + ", ".join(probe_ids)
        )
    return probe_ids[0]


## @brief 설치된 SEGGER J-Link 실행 directory를 찾습니다.
def discover_jlink_directory(environment: dict[str, str]) -> Path:
    candidates: list[Path] = []
    configured = os.environ.get("NUCODE_JLINK_ROOT")
    if configured:
        candidates.append(canonical_path(configured))
    executable = shutil.which("JLink.exe", path=environment.get("PATH"))
    if executable:
        candidates.append(canonical_path(executable).parent)
    for root in (Path("C:/Program Files/SEGGER"), Path("C:/Program Files (x86)/SEGGER")):
        if root.is_dir():
            candidates.extend(sorted(root.glob("JLink_*"), reverse=True))
    visited: set[str] = set()
    for candidate in candidates:
        key = path_key(candidate)
        if key in visited:
            continue
        visited.add(key)
        if (candidate / "JLink.exe").is_file() and (candidate / "JLinkGDBServerCL.exe").is_file():
            return candidate.resolve()
    raise AdapterError(
        "[NU54:E_RUNNER_JLINK_UNAVAILABLE] SEGGER J-Link Software를 찾지 못했습니다. "
        "NUCODE_JLINK_ROOT를 설정하십시오."
    )


## @brief runner에 필요한 실행 파일과 UTF-8 child process 환경을 구성합니다.
def flash_environment(tools: dict[str, Any], runner: str) -> dict[str, str]:
    environment = tools["environment"].copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    if runner == "pyocd":
        pyocd = tools["toolchain_root"] / "opt" / "bin" / "Scripts" / "pyocd.exe"
        if not pyocd.is_file():
            raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] pyOCD 실행 파일이 없습니다: {pyocd}")
    elif runner == "jlink":
        jlink_directory = discover_jlink_directory(environment)
        environment["PATH"] = str(jlink_directory) + os.pathsep + environment.get("PATH", "")
    return environment


## @brief 선택 runner와 probe로 erase 없는 west flash 명령을 만듭니다.
def build_flash_command(
    tools: dict[str, Any], zephyr_build: Path, runner: str, probe_id: str
) -> list[str | Path]:
    command: list[str | Path] = [
        tools["west"],
        "-z",
        tools["zephyr_base"],
        "flash",
        "-d",
        zephyr_build,
        "-r",
        runner,
        "--no-rebuild",
        "--dev-id",
        probe_id,
    ]
    if runner == "pyocd":
        command.append("--tool-opt=-Osmart_flash=false")
    forbidden = {"--erase", "--recover"}
    if forbidden.intersection(str(value) for value in command):
        raise AdapterError("[NU54:E_FLASH_UNSAFE_OPTION] 일반 upload에 destructive option이 포함됐습니다.")
    return command


## @brief 동일 probe에 대한 동시에 실행되는 flash process를 직렬화합니다.
@contextlib.contextmanager
def probe_lock(probe_id: str, timeout_seconds: float = 120.0) -> Iterator[None]:
    digest = hashlib.sha256(probe_id.casefold().encode("utf-8")).hexdigest()[:16]
    lock_root = canonical_path(
        Path(tempfile.gettempdir()) / "n54" / "probe-locks" / digest
    )
    try:
        with build_lock(
            lock_root,
            operation=f"flash-probe:{probe_id}",
            timeout_seconds=timeout_seconds,
            logical_identity=f"probe:{probe_id.casefold()}",
        ):
            yield
    except AdapterError as error:
        if "대기 시간이 초과" in str(error):
            raise AdapterError(
                f"[NU54:E_PROBE_BUSY] probe lock 대기 시간이 초과되었습니다: {probe_id}"
            ) from error
        raise


## @brief flash child process의 출력과 결과를 console 및 build log에 기록합니다.
def run_flash_process(
    command: Sequence[str | Path], *, cwd: Path, environment: dict[str, str], log_path: Path,
    runner: str, probe_id: str, hex_path: Path, hex_sha256: str
) -> None:
    normalized = [str(value) for value in command]
    started = dt.datetime.now(dt.timezone.utc)
    result = subprocess.run(
        normalized,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    finished = dt.datetime.now(dt.timezone.utc)
    lines = [
        f"started_at_utc={started.isoformat()}",
        f"finished_at_utc={finished.isoformat()}",
        f"runner={runner}",
        f"probe_id={probe_id}",
        f"hex={hex_path.as_posix()}",
        f"hex_sha256={hex_sha256}",
        f"smart_flash={'false' if runner == 'pyocd' else 'runner-default'}",
        "mass_erase_requested=false",
        "recover_requested=false",
        f"exit_code={result.returncode}",
        "command=" + shlex.join(normalized),
        "--- child output ---",
        output.rstrip(),
        "--- end ---",
        "",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
        stream.flush()
        os.fsync(stream.fileno())
    if result.returncode != 0:
        raise ChildCommandError(
            f"[NU54:E_FLASH_WRITE] flash가 종료 코드 {result.returncode}로 실패했습니다: "
            + shlex.join(normalized),
            result.returncode,
        )


## @brief build context와 현재 NCS/toolchain identity가 같은지 확인합니다.
def validate_flash_tool_identity(context: dict[str, Any], tools: dict[str, Any]) -> None:
    expected_paths = {
        "ncs_root": tools["ncs_root"],
        "toolchain_root": tools["toolchain_root"],
        "cxx_compiler": tools["compiler"],
    }
    for key, current in expected_paths.items():
        stored = context.get(key)
        if not isinstance(stored, str) or path_key(stored) != path_key(current):
            raise AdapterError(
                f"[NU54:E_FLASH_TOOLCHAIN_MISMATCH] build context의 {key}가 현재 환경과 다릅니다."
            )
    if context.get("toolchain_bundle_id") != tools["toolchain_root"].name:
        raise AdapterError(
            "[NU54:E_FLASH_TOOLCHAIN_MISMATCH] build와 현재 toolchain bundle이 다릅니다."
        )


## @brief 검증된 Full Zephyr image를 선택 runner로 일반 upload합니다.
def flash(args: argparse.Namespace) -> None:
    if args.runner not in {"pyocd", "jlink"}:
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] 지원하지 않는 runner입니다: {args.runner}")
    tools = tool_environment(canonical_path(args.platform_root))
    environment = flash_environment(tools, args.runner)
    session_paths = adapter_paths(args)
    with build_lock(session_paths["state_root"], operation="flash-session"):
        session_context = load_context(args, create=False)
        contextual_paths = paths_from_context(session_paths, session_context)
        with build_lock(contextual_paths["workspace"], operation="flash-cache"):
            validate_flash_tool_identity(session_context, tools)
            inputs = validate_flash_manifest(args)
            if inputs["manifest"].get("context") != session_context:
                raise AdapterError(
                    "[NU54:E_FLASH_CONTEXT] session context가 artifact manifest와 다릅니다."
                )
            validate_runner_configuration(inputs["zephyr_build"], args.runner)
            if args.runner == "pyocd":
                probe_id = select_pyocd_probe(args.probe_id)
            else:
                probe_id = (args.probe_id or "").strip()
                if not probe_id:
                    raise AdapterError(
                        "[NU54:E_PROBE_AMBIGUOUS] J-Link upload에는 명시적인 probe serial이 필요합니다."
                    )
            command = build_flash_command(
                tools, inputs["zephyr_build"], args.runner, probe_id
            )
            print(
                "NU54_UPLOAD_START "
                f"runner={args.runner} probe={probe_id} board={args.board} "
                f"hex_sha256={inputs['hex_sha256']}"
            )
            with probe_lock(probe_id):
                run_flash_process(
                    command,
                    cwd=tools["ncs_root"],
                    environment=environment,
                    log_path=inputs["build_path"] / CONTEXT_DIRECTORY / "logs" / "flash.log",
                    runner=args.runner,
                    probe_id=probe_id,
                    hex_path=inputs["hex"],
                    hex_sha256=inputs["hex_sha256"],
                )
            print(f"NU54_UPLOAD_PASS runner={args.runner} probe={probe_id}")


## @brief cache tree와 독립적으로 export artifact의 manifest 무결성을 검증합니다.
def verify_artifact(args: argparse.Namespace) -> None:
    artifact = canonical_path(args.artifact)
    build_path = canonical_path(args.build_path)
    manifest_path = build_path / f"{args.project_name}.nu54-build.json"
    manifest = load_json_object(manifest_path, "E_ARTIFACT_MANIFEST")
    if (
        manifest.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION
        or manifest.get("adapter_version") != ADAPTER_VERSION
        or manifest.get("fqbn") != args.fqbn
        or manifest.get("board") != args.board
    ):
        raise AdapterError("export artifact manifest의 version 또는 target이 다릅니다.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise AdapterError("export artifact manifest에 artifact 목록이 없습니다.")
    matching = [
        extension
        for extension, record in artifacts.items()
        if isinstance(record, dict)
        and isinstance(record.get("path"), str)
        and path_key(record["path"]) == path_key(artifact)
    ]
    if len(matching) != 1:
        raise AdapterError(f"요청 artifact가 현재 build manifest에 없습니다: {artifact}")
    validate_manifest_artifact(manifest, matching[0], build_path)


## @brief Arduino IDE가 parsing할 수 있는 FLASH/RAM 사용량을 출력합니다.
def print_size(args: argparse.Namespace) -> None:
    context = load_context(args, create=False)
    tools = tool_environment(canonical_path(args.platform_root))
    elf = canonical_path(args.build_path) / f"{args.project_name}.elf"
    result = run_checked(
        [context["size_tool"], elf],
        cwd=canonical_path(args.build_path),
        environment=tools["environment"],
        capture=True,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+[0-9a-fA-F]+", output, re.MULTILINE)
    if not match:
        raise AdapterError("ELF size 출력을 해석할 수 없습니다.")
    text_size, data_size, bss_size = (int(value) for value in match.groups())
    print(f"NU54_FLASH_USED={text_size + data_size}")
    print(f"NU54_RAM_USED={data_size + bss_size}")


## @brief 모든 subcommand에 Arduino recipe 공통 인자를 추가합니다.
def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform-root", required=True)
    parser.add_argument("--build-path", required=True)
    parser.add_argument("--sketch-root", required=True)
    parser.add_argument("--fqbn", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--board", default=DEFAULT_BOARD)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)


## @brief Build Adapter command line parser를 구성합니다.
def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nu54-builder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    add_common_arguments(prepare_parser)

    preprocess_parser = subparsers.add_parser("preprocess")
    add_common_arguments(preprocess_parser)
    preprocess_parser.add_argument("--mode", choices=("includes", "macros"), required=True)
    preprocess_parser.add_argument("--arduino-version", default="10607")
    preprocess_parser.add_argument("--discovery-phase", default="1")
    preprocess_parser.add_argument("--source", required=True)
    preprocess_parser.add_argument("--output")

    record_parser = subparsers.add_parser("record")
    add_common_arguments(record_parser)
    record_parser.add_argument("--language", choices=("c", "cxx", "asm"), required=True)
    record_parser.add_argument("--source", required=True)
    record_parser.add_argument("--object", required=True)

    archive_parser = subparsers.add_parser("archive")
    add_common_arguments(archive_parser)
    archive_parser.add_argument("--archive", required=True)
    archive_parser.add_argument("--object", required=True)

    link_parser = subparsers.add_parser("link")
    add_common_arguments(link_parser)
    link_parser.add_argument("--archive", required=True)
    link_parser.add_argument("--objects", nargs="*", default=[])

    verify_parser = subparsers.add_parser("verify-artifact")
    add_common_arguments(verify_parser)
    verify_parser.add_argument("--artifact", required=True)

    size_parser = subparsers.add_parser("size")
    add_common_arguments(size_parser)

    flash_parser = subparsers.add_parser("flash")
    add_common_arguments(flash_parser)
    flash_parser.add_argument("--manifest", required=True)
    flash_parser.add_argument("--runner", choices=("pyocd", "jlink"), required=True)
    flash_parser.add_argument("--probe-id")
    flash_parser.add_argument("--verbose", action="store_true")

    clean_parser = subparsers.add_parser("clean-build")
    add_common_arguments(clean_parser)

    cache_parser = subparsers.add_parser("cache")
    cache_parser.add_argument(
        "cache_action", choices=("list", "inspect", "prune", "remove", "clear")
    )
    cache_parser.add_argument("key", nargs="?")
    cache_parser.add_argument("--cache-root")
    cache_parser.add_argument("--include-compiler", action="store_true")
    return parser


## @brief Arduino recipe가 의도적으로 전달하는 제한된 추가 인자만 허용합니다.
def validate_passthrough(command: str, values: Sequence[str]) -> None:
    if not values:
        return
    if command in {"preprocess", "record"}:
        index = 0
        while index < len(values):
            value = values[index]
            if value == "-I":
                if index + 1 >= len(values) or values[index + 1].startswith("-"):
                    raise AdapterError("-I 뒤에 include directory가 필요합니다.")
                index += 2
                continue
            if value.startswith("-I") and len(value) > 2:
                index += 1
                continue
            if command == "preprocess" and value in {"-MMD", "-MD", "-MP"}:
                index += 1
                continue
            if command == "preprocess" and value in {"-MF", "-MT", "-MQ"}:
                if index + 1 >= len(values) or values[index + 1].startswith("-"):
                    raise AdapterError(f"{value} 뒤에 dependency 값이 필요합니다.")
                index += 2
                continue
            if command == "preprocess" and value.startswith(("-D", "-U")) and len(value) > 2:
                index += 1
                continue
            raise AdapterError(f"허용되지 않은 {command} 추가 인자입니다: {value}")
        return
    if command == "link":
        for value in values:
            if value.startswith("-") or Path(value).suffix.casefold() not in {".o", ".obj"}:
                raise AdapterError(f"허용되지 않은 link object 인자입니다: {value}")
        return
    raise AdapterError(f"{command} command는 추가 인자를 허용하지 않습니다: {' '.join(values)}")


## @brief subcommand를 실행하고 안정적인 종료 code를 반환합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args, passthrough = parser.parse_known_args(arguments)
    try:
        validate_passthrough(args.command, passthrough)
        if args.command == "prepare":
            prepare(args)
        elif args.command == "preprocess":
            preprocess(args, passthrough)
        elif args.command == "record":
            record_source(args, passthrough)
        elif args.command == "archive":
            create_archive(args)
        elif args.command == "link":
            if passthrough:
                args.objects.extend(passthrough)
            link(args)
        elif args.command == "verify-artifact":
            verify_artifact(args)
        elif args.command == "size":
            print_size(args)
        elif args.command == "flash":
            flash(args)
        elif args.command == "clean-build":
            clean_build(args)
        elif args.command == "cache":
            if args.cache_action in {"inspect", "remove"} and not args.key:
                parser.error(f"cache {args.cache_action}에는 key가 필요합니다")
            manage_cache(args)
        else:
            parser.error(f"알 수 없는 command입니다: {args.command}")
        return 0
    except ChildCommandError as error:
        print(f"nu54-builder: error: {error}", file=sys.stderr)
        return error.return_code
    except AdapterError as error:
        print(f"nu54-builder: error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("nu54-builder: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
