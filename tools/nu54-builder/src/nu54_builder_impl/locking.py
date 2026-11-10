"""! @brief OS 및 build·probe 배타 lock을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Iterator
import contextlib
import datetime as dt
import hashlib
import json
import os
import socket
import stat
import tempfile
import time
import uuid
from .common import (
    AdapterError,
    DEFAULT_BUILD_LOCK_TIMEOUT_SECONDS,
    atomic_write_json,
    canonical_path,
    path_key,
)

POSIX_LOCK_ROOT = Path('/tmp')


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
    if logical_identity is not None:
        seed = logical_identity
    else:
        seed = canonical_path(lock_root).as_posix()
        ## @note 기존 Windows worker와 같은 kernel mutex를 사용해 업그레이드 중 배타성을 유지합니다.
        if os.name == 'nt':
            seed = seed.casefold()
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"NUCODE_NU54_{digest}"


def posix_lock_directory(logical_identity: str | None = None) -> Path:
    """! @brief 사용자별 cache lock과 공통 probe lock을 TMP 환경과 무관한 위치에 둡니다. """
    legacy_probe = bool(logical_identity and logical_identity.startswith('probe:'))
    base = POSIX_LOCK_ROOT / ('n54' if legacy_probe else f'n54-{os.geteuid()}')
    directory = base / 'adapter-locks'
    try:
        for path in (base, directory):
            if path.is_symlink():
                raise AdapterError('[NU54:E_LOCK_PERMISSION] lock directory의 symlink는 허용하지 않습니다.')
            path.mkdir(exist_ok=True, mode=0o700)
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise AdapterError('[NU54:E_LOCK_PERMISSION] lock directory의 소유권·쓰기 권한을 확인하십시오.')
    except OSError as error:
        raise AdapterError('[NU54:E_LOCK_PERMISSION] native lock directory에 접근하지 못했습니다.') from error
    return directory


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

    lock_directory = posix_lock_directory(logical_identity)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
    try:
        descriptor = os.open(lock_directory / f"{identity}.lock", flags, 0o600)
    except OSError as error:
        raise AdapterError('[NU54:E_LOCK_PERMISSION] native lock 파일을 열지 못했습니다.') from error
    acquired = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            raise AdapterError('[NU54:E_LOCK_PERMISSION] native lock 파일의 종류·소유권·권한이 다릅니다.')
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
                    # OS mutex가 실제 배타성을 소유하므로 scanner가 diagnostic
                    # JSON 삭제를 잠시 막아도 build 결과를 실패시키지 않습니다.
                    except OSError:
                        pass
    except TimeoutError as error:
        owner = read_lock_document(lock_path)
        detail = json.dumps(owner, ensure_ascii=False, sort_keys=True) if owner else "unknown"
        raise AdapterError(
            f"build lock 대기 시간이 초과되었습니다: {lock_path}; owner={detail}"
        ) from error


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
