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
