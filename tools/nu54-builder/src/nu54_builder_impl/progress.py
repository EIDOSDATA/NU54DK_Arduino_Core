"""! @brief 장시간 build 명령의 진행률, UTF-8 log와 병렬 작업자 정책을 제공합니다. """

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Sequence
import ctypes
import os
import re
import shlex
import subprocess
import sys
import time

from .common import AdapterError, ChildCommandError


NINJA_PROGRESS_PATTERN = re.compile(r"^\[(\d+)/(\d+)\]")
MAX_BUILD_JOBS = 64


@dataclass(frozen=True)
class ProgressResult:
    """! @brief 진행 명령의 측정 결과입니다. """

    duration_seconds: float
    completed_targets: int
    total_targets: int
    worker_count: int
    log_path: str


## @brief Arduino CLI가 성공 명령 stdout을 숨겨도 보존하는 진단 stream에 출력합니다.
def progress_message(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


## @brief 현재 host의 물리 메모리 byte를 OS API로 읽습니다.
def physical_memory_bytes() -> int | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            """! @brief GlobalMemoryStatusEx 입력 구조체입니다. """

            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
        return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages) * int(page_size)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


## @brief CPU와 RAM을 함께 제한하며 명시 override를 우선하는 작업자 수를 계산합니다.
def build_worker_count(
    *, cpu_count: int | None = None, memory_bytes: int | None = None,
    override: str | None = None,
) -> int:
    requested = override if override is not None else os.environ.get("NUCODE_BUILD_JOBS")
    if requested is not None:
        try:
            parsed = int(requested)
        except ValueError as error:
            raise AdapterError(
                f"[NU54:E_BUILD_JOBS] NUCODE_BUILD_JOBS는 1~{MAX_BUILD_JOBS} 정수여야 합니다."
            ) from error
        if parsed < 1 or parsed > MAX_BUILD_JOBS:
            raise AdapterError(
                f"[NU54:E_BUILD_JOBS] NUCODE_BUILD_JOBS는 1~{MAX_BUILD_JOBS} 정수여야 합니다."
            )
        return parsed
    processors = max(1, cpu_count if cpu_count is not None else (os.cpu_count() or 1))
    physical = physical_memory_bytes() if memory_bytes is None else memory_bytes
    memory_limit = MAX_BUILD_JOBS
    if physical is not None and physical > 0:
        memory_limit = max(1, int(physical // (2 * 1024 ** 3)))
    return min(processors, memory_limit, MAX_BUILD_JOBS)


## @brief build child process용 병렬화와 UTF-8 환경을 복제해 반환합니다.
def build_environment(environment: dict[str, str], worker_count: int) -> dict[str, str]:
    result = environment.copy()
    result["CMAKE_BUILD_PARALLEL_LEVEL"] = str(worker_count)
    result["NINJA_STATUS"] = "[%f/%t] "
    result["PYTHONUTF8"] = "1"
    result["PYTHONIOENCODING"] = "utf-8"
    return result


## @brief stdout을 별도 thread에서 읽어 heartbeat가 막히지 않게 합니다.
def _read_output(stream, queue: Queue[bytes | None]) -> None:
    try:
        for line in iter(stream.readline, b""):
            queue.put(line)
    finally:
        queue.put(None)


## @brief 하위 명령을 실행하며 전체 log와 최대 10초 간격의 진행 상황을 제공합니다.
def run_progress_command(
    command: Sequence[str | Path], *, cwd: Path, environment: dict[str, str],
    log_path: Path, stage: str, worker_count: int, heartbeat_seconds: float = 10.0,
) -> ProgressResult:
    normalized = [str(value) for value in command]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    queue: Queue[bytes | None] = Queue()
    started = time.perf_counter()
    completed = 0
    total = 0
    last_reported = 0
    tail: deque[str] = deque(maxlen=24)
    try:
        process = subprocess.Popen(
            normalized,
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as error:
        raise AdapterError(
            f"[NU54:E_BUILD_EXEC] build process를 시작하지 못했습니다: {error}"
        ) from error
    assert process.stdout is not None
    reader = Thread(target=_read_output, args=(process.stdout, queue), daemon=True)
    reader.start()
    with log_path.open("a", encoding="utf-8", newline="\n") as log:
        log.write("\n=== " + stage + " ===\n")
        log.write("command=" + shlex.join(normalized) + "\n")
        log.write(f"workers={worker_count}\n")
        stream_finished = False
        while not stream_finished:
            try:
                raw = queue.get(timeout=heartbeat_seconds)
            except Empty:
                elapsed = time.perf_counter() - started
                detail = f"{completed}/{total}" if total else "대상 계산 중"
                progress_message(f"[NU54] {stage}: {detail}, {elapsed:.1f}초 경과")
                continue
            if raw is None:
                stream_finished = True
                continue
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            log.write(text + "\n")
            log.flush()
            tail.append(text)
            match = NINJA_PROGRESS_PATTERN.match(text)
            if match is not None:
                completed = int(match[1])
                total = int(match[2])
                interval = max(1, total // 20)
                if completed == total or completed - last_reported >= interval:
                    progress_message(f"[NU54] {stage}: {completed}/{total}")
                    last_reported = completed
        reader.join(timeout=1.0)
        process.stdout.close()
        return_code = process.wait()
        duration = time.perf_counter() - started
        log.write(f"exit_code={return_code}\n")
        log.write(f"duration_seconds={duration:.6f}\n")
        log.flush()
        os.fsync(log.fileno())
    if return_code != 0:
        for line in tail:
            print(line, file=sys.stderr)
        raise ChildCommandError(
            f"[NU54:E_BUILD_EXEC] {stage} 명령이 종료 코드 {return_code}로 실패했습니다. "
            f"전체 log: {log_path}",
            return_code,
        )
    return ProgressResult(
        duration_seconds=duration,
        completed_targets=completed,
        total_targets=total,
        worker_count=worker_count,
        log_path=log_path.as_posix(),
    )
