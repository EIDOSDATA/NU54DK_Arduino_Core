#!/usr/bin/env python3
"""! @brief 두 NU54DK의 Signed Write 재부팅·replay와 EATT HIL을 자동화합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    BlePairHilFailure,
    PairExecutionFailure,
    RoleEndpoint,
    RoleExecution,
    build_nonce,
    discover_endpoint,
    file_sha256,
    flash_image,
    flash_image_pyocd,
    git_revision,
    image_record,
    prepare_output_paths,
    read_line,
    save_failure_transcripts,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_pair_identity,
    validate_source_clean,
)
from m6_serial_echo import import_pyserial  # noqa: E402


PROTOCOL = "M29W07|1"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m29_ble_signed_eatt_hil"
DEFAULT_RESULT_TIMEOUT_SECONDS = 900.0
SIGN_REBOOTS = 20
REPLAY_ITERATION = 21
EATT_ITERATION = 22
MAX_CONNECTION_RETRIES = 2
REBOOT_SERIAL_SETTLE_SECONDS = 1.0


@dataclass(frozen=True)
class AdvancedRoleResult:
    """! @brief 한 role의 W07 signing·EATT 정량 결과입니다. """

    role: str
    connection_retries: int
    signing_reboots: int
    signed_writes: int
    final_local_counter: int
    final_remote_counter: int
    replay_attempts: int
    replay_accepts: int
    eatt_bearers: int
    operations_per_bearer: int
    deadlocks: int
    starvation: int
    callback_context: str


@dataclass(frozen=True)
class AdvancedPairExecution:
    """! @brief 두 role의 flash 결과와 전체 strict transcript입니다. """

    peripheral: RoleExecution
    central: RoleExecution


def _strict_lines(transcript: bytes) -> tuple[bytes, ...]:
    """! @brief trailing newline 하나 외의 빈 줄·비 ASCII noise를 거부합니다. """

    normalized = transcript.replace(b"\r", b"")
    pieces = normalized.split(b"\n")
    if pieces and pieces[-1] == b"":
        pieces.pop()
    if not pieces or any(not line for line in pieces):
        raise BlePairHilFailure("W07 transcript에 빈 줄 또는 record 누락이 있습니다.")
    try:
        for line in pieces:
            line.decode("ascii")
    except UnicodeDecodeError as error:
        raise BlePairHilFailure("W07 transcript에 비 ASCII noise가 있습니다.") from error
    return tuple(pieces)


def _suffix(iteration: int, nonce: str, core_revision: str) -> bytes:
    """! @brief mode record의 고정 identity suffix를 생성합니다. """

    return (
        f"|iteration={iteration}|nonce={nonce}|core={core_revision}".encode("ascii")
    )


def _take_exact(lines: tuple[bytes, ...], cursor: int, expected: bytes) -> int:
    """! @brief 현재 cursor의 exact record를 소비하거나 fail-closed로 거부합니다. """

    if cursor >= len(lines) or lines[cursor] != expected:
        actual = b"<missing>" if cursor >= len(lines) else lines[cursor]
        raise BlePairHilFailure(
            f"W07 protocol 순서/값 불일치: 기대={expected!r}, 실제={actual!r}"
        )
    return cursor + 1


def _take_pattern(
    lines: tuple[bytes, ...], cursor: int, pattern: re.Pattern[bytes]
) -> tuple[int, re.Match[bytes]]:
    """! @brief 현재 cursor의 동적 counter record를 full-match로 소비합니다. """

    if cursor >= len(lines):
        raise BlePairHilFailure("W07 동적 counter record가 누락됐습니다.")
    match = pattern.fullmatch(lines[cursor])
    if match is None:
        raise BlePairHilFailure(f"W07 동적 counter record가 잘못됐습니다: {lines[cursor]!r}")
    return cursor + 1, match


def _validate_identity(nonce: str, core_revision: str, role: str) -> None:
    """! @brief parser 입력 identity를 target protocol과 같은 제약으로 검증합니다. """

    build_nonce(nonce)
    if role not in ("peripheral", "central"):
        raise BlePairHilFailure(f"알 수 없는 W07 role입니다: {role}")
    if re.fullmatch(r"[0-9a-f]{40}", core_revision) is None:
        raise BlePairHilFailure("Core revision은 소문자 40자리 SHA-1이어야 합니다.")


def parse_role_transcript(
    transcript: bytes, nonce: str, core_revision: str, role: str
) -> AdvancedRoleResult:
    """! @brief 전체 W07 transcript의 noise·누락·중복·재배치를 거부합니다. """

    _validate_identity(nonce, core_revision, role)
    lines = _strict_lines(transcript)
    cursor = 0
    escaped_protocol = re.escape(PROTOCOL)
    ready_pattern = re.compile(
        rf"{escaped_protocol}\|READY\|role={role}\|bond_count=([01])\|core={core_revision}".encode(
            "ascii"
        )
    )
    cursor, _ = _take_pattern(lines, cursor, ready_pattern)
    cursor = _take_exact(
        lines,
        cursor,
        f"{PROTOCOL}|CLEAR|role={role}|bond_count=0|nonce={nonce}|core={core_revision}".encode(
            "ascii"
        ),
    )

    local_counter = 0
    remote_counter = 0
    connection_retries = 0

    def take_reboot_and_ready(expected_bonds: int) -> None:
        nonlocal cursor
        cursor = _take_exact(
            lines,
            cursor,
            f"{PROTOCOL}|REBOOTING|role={role}|nonce={nonce}|core={core_revision}".encode(
                "ascii"
            ),
        )
        cursor = _take_exact(
            lines,
            cursor,
            f"{PROTOCOL}|READY|role={role}|bond_count={expected_bonds}|core={core_revision}".encode(
                "ascii"
            ),
        )

    def take_session_header(mode: str, iteration: int) -> None:
        nonlocal cursor
        suffix = _suffix(iteration, nonce, core_revision)
        cursor = _take_exact(
            lines,
            cursor,
            f"{PROTOCOL}|BEGIN|role={role}|mode={mode}".encode("ascii") + suffix,
        )
        if role == "peripheral":
            event = f"{PROTOCOL}|ADVERTISE|role=peripheral|mode={mode}|status=pass"
        else:
            event = f"{PROTOCOL}|SCAN|role=central|mode={mode}|status=pass"
        cursor = _take_exact(lines, cursor, event.encode("ascii") + suffix)

    def take_connection_retries(iteration: int) -> None:
        """! @brief 해당 session의 HCI 0x3e 재시도를 순번·상한까지 검증합니다. """

        nonlocal connection_retries, cursor
        attempt = 1
        prefix = f"{PROTOCOL}|RETRY|role={role}|".encode("ascii")
        while cursor < len(lines) and lines[cursor].startswith(prefix):
            if attempt > MAX_CONNECTION_RETRIES:
                raise BlePairHilFailure("W07 connection retry가 고정 상한을 넘었습니다.")
            cursor = _take_exact(
                lines,
                cursor,
                (
                    f"{PROTOCOL}|RETRY|role={role}|reason=62|attempt={attempt}"
                ).encode("ascii")
                + _suffix(iteration, nonce, core_revision),
            )
            attempt += 1
            connection_retries += 1

    def take_end(mode: str, iteration: int) -> None:
        nonlocal cursor
        cursor = _take_exact(
            lines,
            cursor,
            (
                f"{PROTOCOL}|END|role={role}|mode={mode}|status=pass|"
                "callback_context=pass"
            ).encode("ascii")
            + _suffix(iteration, nonce, core_revision),
        )

    take_reboot_and_ready(0)
    take_session_header("pair", 0)
    take_connection_retries(0)
    pair_pattern = re.compile(
        (
            rf"{escaped_protocol}\|PAIR\|role={role}\|bond_count=1\|local_counter=(\d+)"
            rf"\|remote_counter=(\d+)"
        ).encode("ascii")
        + re.escape(_suffix(0, nonce, core_revision))
    )
    cursor, match = _take_pattern(lines, cursor, pair_pattern)
    local_counter = int(match.group(1))
    remote_counter = int(match.group(2))
    if local_counter != 0 or remote_counter != 0:
        raise BlePairHilFailure("W07 새 CSRK counter가 0에서 시작하지 않았습니다.")
    take_end("pair", 0)

    for iteration in range(1, SIGN_REBOOTS + 1):
        take_reboot_and_ready(1)
        take_session_header("sign", iteration)
        take_connection_retries(iteration)
        sign_pattern = re.compile(
            (
                rf"{escaped_protocol}\|SIGN\|role={role}\|writes=1\|local_counter=(\d+)"
                rf"\|remote_counter=(\d+)"
            ).encode("ascii")
            + re.escape(_suffix(iteration, nonce, core_revision))
        )
        cursor, match = _take_pattern(lines, cursor, sign_pattern)
        current_local = int(match.group(1))
        current_remote = int(match.group(2))
        if role == "central":
            if current_local != local_counter + 1 or current_remote != remote_counter:
                raise BlePairHilFailure("central CSRK counter가 재부팅 뒤 단조 증가하지 않았습니다.")
        else:
            if current_remote != remote_counter + 1 or current_local != local_counter:
                raise BlePairHilFailure(
                    "peripheral CSRK counter가 재부팅 뒤 단조 증가하지 않았습니다."
                )
        local_counter = current_local
        remote_counter = current_remote
        take_end("sign", iteration)

    take_reboot_and_ready(1)
    take_session_header("replay", REPLAY_ITERATION)
    take_connection_retries(REPLAY_ITERATION)
    if role == "central":
        replay_prefix = (
            f"{PROTOCOL}|REPLAY|role=central|sent=2|signed_originals=1|replays=1"
        )
    else:
        replay_prefix = (
            f"{PROTOCOL}|REPLAY|role=peripheral|writes=1|replay_accepts=0"
        )
    replay_pattern = re.compile(
        (
            re.escape(replay_prefix.encode("ascii"))
            + rb"\|local_counter=(\d+)\|remote_counter=(\d+)"
            + re.escape(_suffix(REPLAY_ITERATION, nonce, core_revision))
        )
    )
    cursor, match = _take_pattern(lines, cursor, replay_pattern)
    replay_local = int(match.group(1))
    replay_remote = int(match.group(2))
    if role == "central":
        if replay_local != local_counter + 1 or replay_remote != remote_counter:
            raise BlePairHilFailure("replay 원본 전송의 central counter가 정확히 1 증가하지 않았습니다.")
    else:
        if replay_remote != remote_counter + 1 or replay_local != local_counter:
            raise BlePairHilFailure(
                "replay 원본 수신의 peripheral counter가 정확히 1 증가하지 않았습니다."
            )
    local_counter = replay_local
    remote_counter = replay_remote
    take_end("replay", REPLAY_ITERATION)

    take_reboot_and_ready(1)
    take_session_header("eatt", EATT_ITERATION)
    take_connection_retries(EATT_ITERATION)
    if role == "central":
        eatt = (
            f"{PROTOCOL}|EATT|role=central|bearers=2|ops_bearer0=1000|"
            "ops_bearer1=1000|unencrypted_rejected=1|over_limit_rejected=1|"
            "production_read=1|production_write=1|deadlocks=0|starvation=0"
        )
    else:
        eatt = (
            f"{PROTOCOL}|EATT|role=peripheral|bearers=2|ops_bearer0=1000|"
            "ops_bearer1=1000|production_writes=1|payload_errors=0|"
            "deadlocks=0|starvation=0"
        )
    cursor = _take_exact(
        lines,
        cursor,
        eatt.encode("ascii") + _suffix(EATT_ITERATION, nonce, core_revision),
    )
    take_end("eatt", EATT_ITERATION)
    if cursor != len(lines):
        raise BlePairHilFailure(f"W07 END 뒤 예상 밖 record가 있습니다: {lines[cursor:]!r}")

    return AdvancedRoleResult(
        role=role,
        connection_retries=connection_retries,
        signing_reboots=SIGN_REBOOTS,
        signed_writes=SIGN_REBOOTS + 1,
        final_local_counter=local_counter,
        final_remote_counter=remote_counter,
        replay_attempts=1,
        replay_accepts=0,
        eatt_bearers=2,
        operations_per_bearer=1000,
        deadlocks=0,
        starvation=0,
        callback_context="pass",
    )


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact image·board·evidence 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description=(
            "두 NU54DK로 20회 재부팅 Signed Write·replay 거부와 "
            "EATT bearer별 1,000회 부하를 검증합니다."
        )
    )
    parser.add_argument("--peripheral-hex")
    parser.add_argument("--central-hex")
    parser.add_argument("--peripheral-board-id", required=True)
    parser.add_argument("--central-board-id", required=True)
    parser.add_argument("--peripheral-volume")
    parser.add_argument("--central-volume")
    parser.add_argument("--peripheral-port", default="auto")
    parser.add_argument("--central-port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument(
        "--flash-backend", choices=("pyocd-sector", "daplink-msd"), default="pyocd-sector"
    )
    parser.add_argument(
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--evidence")
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def _write_line(serial_port: Any, text: str) -> None:
    """! @brief ASCII command 한 줄이 전부 기록됐는지 확인합니다. """

    request = (text + "\r\n").encode("ascii")
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise BlePairHilFailure("W07 command가 일부만 기록됐습니다.")


def _read_expected(
    serial_port: Any,
    role: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    expected: bytes,
) -> None:
    """! @brief 다음 UART record 하나가 exact 값인지 즉시 검증합니다. """

    line = read_line(serial_port, pending, capture, deadline)
    print(f"[{role}] {line.decode('ascii', errors='backslashreplace')}")
    if line.startswith(f"{PROTOCOL}|FAIL|".encode("ascii")):
        raise BlePairHilFailure(f"{role} target 실패: {line!r}")
    if line != expected:
        raise BlePairHilFailure(
            f"{role} W07 record 불일치: 기대={expected!r}, 실제={line!r}"
        )


def _query_ready(
    ports: dict[str, Any],
    pending: dict[str, bytearray],
    captures: dict[str, bytearray],
    core_revision: str,
    deadline: float,
) -> None:
    """! @brief flash 뒤 입력을 비우고 현재 image READY만 질의합니다. """

    for role in ("peripheral", "central"):
        ports[role].reset_input_buffer()
        pending[role].clear()
        _write_line(ports[role], f"{PROTOCOL}|READY?")
        pattern = re.compile(
            rf"{re.escape(PROTOCOL)}\|READY\|role={role}\|bond_count=[01]\|core={core_revision}".encode(
                "ascii"
            )
        )
        line = read_line(ports[role], pending[role], captures[role], deadline)
        print(f"[{role}] {line.decode('ascii', errors='backslashreplace')}")
        if pattern.fullmatch(line) is None:
            raise BlePairHilFailure(f"{role} W07 READY 불일치: {line!r}")


def _clear_bonds(
    ports: dict[str, Any],
    pending: dict[str, bytearray],
    captures: dict[str, bytearray],
    nonce: str,
    core_revision: str,
    deadline: float,
) -> None:
    """! @brief 두 role bond를 같은 nonce로 지우고 즉시 0을 확인합니다. """

    command = f"{PROTOCOL}|CLEAR|nonce={nonce}|core={core_revision}"
    for role in ("peripheral", "central"):
        _write_line(ports[role], command)
    for role in ("peripheral", "central"):
        _read_expected(
            ports[role],
            role,
            pending[role],
            captures[role],
            deadline,
            f"{PROTOCOL}|CLEAR|role={role}|bond_count=0|nonce={nonce}|core={core_revision}".encode(
                "ascii"
            ),
        )


def _reboot_pair(
    ports: dict[str, Any],
    pending: dict[str, bytearray],
    captures: dict[str, bytearray],
    nonce: str,
    core_revision: str,
    expected_bonds: int,
    timeout_seconds: float,
) -> None:
    """! @brief 두 target을 warm reboot하고 UART 재동기화 뒤 exact READY를 질의합니다. """

    command = f"{PROTOCOL}|REBOOT|nonce={nonce}|core={core_revision}"
    for role in ("peripheral", "central"):
        _write_line(ports[role], command)

    def wait_rebooting(role: str) -> None:
        deadline = time.monotonic() + timeout_seconds
        _read_expected(
            ports[role],
            role,
            pending[role],
            captures[role],
            deadline,
            f"{PROTOCOL}|REBOOTING|role={role}|nonce={nonce}|core={core_revision}".encode(
                "ascii"
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(wait_rebooting, role)
            for role in ("peripheral", "central")
        ]
        for future in futures:
            future.result()

    # Warm reset 동안 DAPLink UART가 만드는 첫 framing byte와 자동 READY는
    # 결과 protocol의 경계 밖에서 버린다. 경계 뒤에는 exact READY 한 줄만 허용한다.
    time.sleep(REBOOT_SERIAL_SETTLE_SECONDS)
    for role in ("peripheral", "central"):
        if pending[role]:
            pending_length = len(pending[role])
            if captures[role][-pending_length:] != pending[role]:
                raise BlePairHilFailure(f"{role} UART pending/capture 경계가 손상됐습니다.")
            del captures[role][-pending_length:]
            pending[role].clear()
        ports[role].reset_input_buffer()
        _write_line(ports[role], f"{PROTOCOL}|READY?")

    def wait_ready(role: str) -> None:
        _read_expected(
            ports[role],
            role,
            pending[role],
            captures[role],
            time.monotonic() + timeout_seconds,
            f"{PROTOCOL}|READY|role={role}|bond_count={expected_bonds}|core={core_revision}".encode(
                "ascii"
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(wait_ready, role) for role in ("peripheral", "central")
        ]
        for future in futures:
            future.result()


def _run_session(
    ports: dict[str, Any],
    pending: dict[str, bytearray],
    captures: dict[str, bytearray],
    nonce: str,
    core_revision: str,
    mode: str,
    iteration: int,
    timeout_seconds: float,
) -> None:
    """! @brief peripheral 광고 확인 뒤 central을 시작하고 양쪽 END까지 수집합니다. """

    suffix = _suffix(iteration, nonce, core_revision)
    start = (
        f"{PROTOCOL}|START|mode={mode}|iteration={iteration}|nonce={nonce}|"
        f"core={core_revision}"
    )
    deadline = time.monotonic() + timeout_seconds
    _write_line(ports["peripheral"], start)
    _read_expected(
        ports["peripheral"],
        "peripheral",
        pending["peripheral"],
        captures["peripheral"],
        deadline,
        f"{PROTOCOL}|BEGIN|role=peripheral|mode={mode}".encode("ascii") + suffix,
    )
    _read_expected(
        ports["peripheral"],
        "peripheral",
        pending["peripheral"],
        captures["peripheral"],
        deadline,
        f"{PROTOCOL}|ADVERTISE|role=peripheral|mode={mode}|status=pass".encode(
            "ascii"
        )
        + suffix,
    )
    _write_line(ports["central"], start)
    expected_end = {
        role: (
            f"{PROTOCOL}|END|role={role}|mode={mode}|status=pass|"
            "callback_context=pass"
        ).encode("ascii")
        + suffix
        for role in ("peripheral", "central")
    }
    stop_event = threading.Event()

    def collect(role: str) -> None:
        try:
            while not stop_event.is_set():
                line = read_line(
                    ports[role],
                    pending[role],
                    captures[role],
                    deadline,
                    stop_event=stop_event,
                )
                print(f"[{role}] {line.decode('ascii', errors='backslashreplace')}")
                if line.startswith(f"{PROTOCOL}|FAIL|".encode("ascii")):
                    raise BlePairHilFailure(f"{role} target 실패: {line!r}")
                if line == expected_end[role]:
                    return
                if line.startswith(f"{PROTOCOL}|END|".encode("ascii")):
                    raise BlePairHilFailure(f"{role} END identity 불일치: {line!r}")
        except Exception:
            stop_event.set()
            raise

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(collect, role) for role in ("peripheral", "central")]
        for future in futures:
            future.result()


def execute_advanced_pair(
    *,
    serial_module: Any,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    peripheral_image: Path,
    central_image: Path,
    nonce: str,
    core_revision: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
    flash_backend: str,
) -> AdvancedPairExecution:
    """! @brief flash부터 20회 signing reboot·replay·EATT까지 연속 실행합니다. """

    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 900.0:
        raise BlePairHilFailure("--result-timeout은 30..900초여야 합니다.")
    captures = {"peripheral": bytearray(), "central": bytearray()}
    pending = {"peripheral": bytearray(), "central": bytearray()}
    flashes = {
        "peripheral": ("not-started", "unknown"),
        "central": ("not-started", "unknown"),
    }
    try:
        with ExitStack() as stack:
            ports = {
                role: stack.enter_context(
                    serial_module.Serial(
                        port=endpoint.port_name,
                        baudrate=baud_rate,
                        bytesize=serial_module.EIGHTBITS,
                        parity=serial_module.PARITY_NONE,
                        stopbits=serial_module.STOPBITS_ONE,
                        timeout=0.1,
                        write_timeout=2.0,
                    )
                )
                for role, endpoint in (
                    ("peripheral", peripheral_endpoint),
                    ("central", central_endpoint),
                )
            }
            for role, endpoint, image in (
                ("peripheral", peripheral_endpoint, peripheral_image),
                ("central", central_endpoint, central_image),
            ):
                ports[role].reset_input_buffer()
                if flash_backend == "pyocd-sector":
                    flashes[role] = flash_image_pyocd(
                        role, endpoint.board_id, image, flash_timeout
                    )
                else:
                    flashes[role] = flash_image(
                        "M29W07", role, endpoint.volume, image, flash_timeout
                    )
            _query_ready(
                ports,
                pending,
                captures,
                core_revision,
                time.monotonic() + result_timeout,
            )
            _clear_bonds(
                ports,
                pending,
                captures,
                nonce,
                core_revision,
                time.monotonic() + result_timeout,
            )
            _reboot_pair(
                ports,
                pending,
                captures,
                nonce,
                core_revision,
                0,
                result_timeout,
            )
            _run_session(
                ports, pending, captures, nonce, core_revision, "pair", 0, result_timeout
            )
            for iteration in range(1, SIGN_REBOOTS + 1):
                _reboot_pair(
                    ports,
                    pending,
                    captures,
                    nonce,
                    core_revision,
                    1,
                    result_timeout,
                )
                _run_session(
                    ports,
                    pending,
                    captures,
                    nonce,
                    core_revision,
                    "sign",
                    iteration,
                    result_timeout,
                )
            _reboot_pair(
                ports,
                pending,
                captures,
                nonce,
                core_revision,
                1,
                result_timeout,
            )
            _run_session(
                ports,
                pending,
                captures,
                nonce,
                core_revision,
                "replay",
                REPLAY_ITERATION,
                result_timeout,
            )
            _reboot_pair(
                ports,
                pending,
                captures,
                nonce,
                core_revision,
                1,
                result_timeout,
            )
            _run_session(
                ports,
                pending,
                captures,
                nonce,
                core_revision,
                "eatt",
                EATT_ITERATION,
                result_timeout,
            )
    except Exception as error:
        raise PairExecutionFailure(
            str(error), bytes(captures["peripheral"]), bytes(captures["central"])
        ) from error
    return AdvancedPairExecution(
        RoleExecution(*flashes["peripheral"], bytes(captures["peripheral"])),
        RoleExecution(*flashes["central"], bytes(captures["central"])),
    )


def _board(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief evidence용 DAP/UART/MSD identity를 복사합니다. """

    return {
        "daplink_uid": endpoint.board_id,
        "msd_root": str(endpoint.volume.root),
        "uart_port": endpoint.port_name,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 장치 탐색 또는 전체 W07 two-board gate를 실행합니다. """

    args = parse_arguments(arguments)
    serial_module, list_ports = import_pyserial()
    peripheral_endpoint = discover_endpoint(
        args.peripheral_board_id, args.peripheral_volume, args.peripheral_port, list_ports
    )
    central_endpoint = discover_endpoint(
        args.central_board_id, args.central_volume, args.central_port, list_ports
    )
    validate_pair_identity(peripheral_endpoint, central_endpoint)
    print(
        "NU54DK M29-W07 pair discovery SUCCESS: "
        f"peripheral={peripheral_endpoint.board_id}/{peripheral_endpoint.port_name}, "
        f"central={central_endpoint.board_id}/{central_endpoint.port_name}"
    )
    if args.discover_only:
        return 0

    evidence_path, peripheral_log, central_log = prepare_output_paths(
        args.evidence, args.overwrite_evidence
    )
    peripheral_image = validate_hex_image(args.peripheral_hex)
    central_image = validate_hex_image(args.central_hex)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean(
        "M29W07",
        APPLICATION_SOURCE_ROOT,
        Path(__file__).resolve(),
        additional_paths=(
            REPOSITORY / "libraries" / "NUCODE_BLE_Security",
            REPOSITORY / "libraries" / "NUCODE_BLE_LegacySigning",
            REPOSITORY / "libraries" / "NUCODE_BLE_EATT",
        ),
    )
    peripheral_record = validate_build_record(
        peripheral_image, core_revision, board_revision, APPLICATION_SOURCE_ROOT
    )
    central_record = validate_build_record(
        central_image, core_revision, board_revision, APPLICATION_SOURCE_ROOT
    )
    peripheral_size = peripheral_image.stat().st_size
    central_size = central_image.stat().st_size
    peripheral_sha256 = file_sha256(peripheral_image)
    central_sha256 = file_sha256(central_image)
    if peripheral_sha256 == central_sha256:
        raise BlePairHilFailure("W07 role HEX가 동일하여 오배치를 거부했습니다.")
    nonce = build_nonce()
    try:
        execution = execute_advanced_pair(
            serial_module=serial_module,
            peripheral_endpoint=peripheral_endpoint,
            central_endpoint=central_endpoint,
            peripheral_image=peripheral_image,
            central_image=central_image,
            nonce=nonce,
            core_revision=core_revision,
            baud_rate=args.baud,
            flash_timeout=args.flash_timeout,
            result_timeout=args.result_timeout,
            flash_backend=args.flash_backend,
        )
        validate_image_unchanged(peripheral_image, peripheral_size, peripheral_sha256)
        validate_image_unchanged(central_image, central_size, central_sha256)
        peripheral_result = parse_role_transcript(
            execution.peripheral.transcript, nonce, core_revision, "peripheral"
        )
        central_result = parse_role_transcript(
            execution.central.transcript, nonce, core_revision, "central"
        )
        if central_result.final_local_counter != peripheral_result.final_remote_counter:
            raise BlePairHilFailure("W07 송수신 CSRK counter가 role 사이에서 다릅니다.")
        peripheral_log.write_bytes(execution.peripheral.transcript)
        central_log.write_bytes(execution.central.transcript)
        evidence = {
            "schema_version": 1,
            "gate": "m29-w07-signed-write-eatt-pair-hil",
            "status": "passed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "core_revision": core_revision,
            "board_revision": board_revision,
            "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
            "nonce": nonce,
            "boards": {
                "peripheral": _board(peripheral_endpoint),
                "central": _board(central_endpoint),
            },
            "images": {
                "peripheral": image_record(
                    peripheral_image,
                    peripheral_size,
                    peripheral_sha256,
                    execution.peripheral,
                    peripheral_record,
                ),
                "central": image_record(
                    central_image,
                    central_size,
                    central_sha256,
                    execution.central,
                    central_record,
                ),
            },
            "transcripts": {
                "peripheral": transcript_record(
                    peripheral_log, execution.peripheral.transcript
                ),
                "central": transcript_record(central_log, execution.central.transcript),
            },
            "results": {
                "peripheral": asdict(peripheral_result),
                "central": asdict(central_result),
            },
            "coverage": {
                "signing_profile": "deprecated-opt-in",
                "signing_reboots": SIGN_REBOOTS,
                "maximum_connection_retries_per_session": MAX_CONNECTION_RETRIES,
                "signed_writes": SIGN_REBOOTS + 1,
                "counter_rollbacks": 0,
                "replay_attempts": 1,
                "replay_accepts": 0,
                "eatt_profile": "experimental-opt-in",
                "eatt_bearers": 2,
                "operations_per_bearer": 1000,
                "deadlocks": 0,
                "starvation": 0,
                "m29_sign_01_status": "passed",
                "m29_eatt_01_status": "passed",
            },
            "safety": {
                "external_wiring_required": False,
                "mass_erase_requested": False,
                "pmic_write_executed": False,
            },
        }
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as error:
        save_failure_transcripts(peripheral_log, central_log, error)
        raise
    print(f"NU54DK M29-W07 Signed Write/EATT pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, PairExecutionFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M29-W07 Signed Write/EATT pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
