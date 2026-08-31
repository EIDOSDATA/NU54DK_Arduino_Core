#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M21 보안·bond·표준 profile HIL을 자동 검증합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m21_ble_hil"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from m6_serial_echo import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    DaplinkVolume,
    detail_value,
    find_daplink_volume,
    find_serial_port,
    import_pyserial,
    normalize_board_id,
    validate_hex_image,
    wait_for_flash_result,
)
from m14_pin_hil import (  # noqa: E402
    CORE_SOURCE_SCOPES,
    build_record_value,
    file_sha256,
    files_digest,
    git_revision,
    validate_board_revision,
)


PROTOCOL_PREFIX = b"NUCODE_M21_"
FAIL_PREFIX = b"NUCODE_M21_FAIL:"
NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_TRANSCRIPT_BYTES = 524288
DEFAULT_RESULT_TIMEOUT_SECONDS = 360.0
EVIDENCE_SCHEMA = 3
RF_NONCE_BINDING_BITS = 128


class M21HilFailure(RuntimeError):
    """! @brief M21 두 보드 HIL의 장치·protocol·증적 실패입니다. """


class M21ExecutionFailure(M21HilFailure):
    """! @brief 실패 시점의 양쪽 raw transcript를 보존하는 오류입니다. """

    def __init__(self, message: str, peripheral: bytes, central: bytes) -> None:
        """! @brief 오류 설명과 두 transcript를 저장합니다. """

        super().__init__(message)
        self.peripheral_transcript = peripheral
        self.central_transcript = central


@dataclass(frozen=True)
class RoleEndpoint:
    """! @brief 한 BLE role의 DAPLink UID·MSD·UART endpoint입니다. """

    board_id: str
    volume: DaplinkVolume
    port_name: str


@dataclass(frozen=True)
class RoleResult:
    """! @brief 한 role에서 검증한 phase와 최종 protocol 결과입니다. """

    role: str
    nonce: str
    phases: tuple[str, ...]
    pairing_events: tuple[int, ...]
    bond_counts: tuple[int, ...]
    bond_states: tuple[str, ...]
    rf_nonce_binding_bits: int
    erase_reboot_verified: bool
    old_key_reconnect_rejected: bool
    final_pass: bool


@dataclass(frozen=True)
class RoleExecution:
    """! @brief 한 role의 flash 결과와 raw UART transcript입니다. """

    flash_sequence: str
    flash_bytes: str
    transcript: bytes


@dataclass(frozen=True)
class PairExecution:
    """! @brief 두 role의 동시 실행 결과입니다. """

    peripheral: RoleExecution
    central: RoleExecution


## @brief 실제 두 보드 HIL CLI 인자를 정의합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "두 NU54DK에 M21 role image를 기록하고 pairing, bond 재부팅 복원, "
            "삭제·재페어, BAS, DIS와 HID report protocol을 자동 검증합니다."
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
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--evidence", help="신규 PASS JSON 증적 경로")
    parser.add_argument("--expected-core-revision", required=False)
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


## @brief 동일 실행의 소문자 32자리 hex nonce를 검증하거나 생성합니다.
def build_nonce(explicit_nonce: str | None = None) -> str:
    nonce = explicit_nonce if explicit_nonce is not None else secrets.token_hex(16)
    if NONCE_PATTERN.fullmatch(nonce) is None:
        raise M21HilFailure("M21 nonce는 32자리 소문자 hex여야 합니다.")
    return nonce


## @brief UID·MSD·UART가 두 개의 서로 다른 실제 보드인지 검사합니다.
def validate_pair_identity(peripheral: RoleEndpoint, central: RoleEndpoint) -> None:
    if peripheral.board_id == central.board_id:
        raise M21HilFailure("peripheral과 central DAPLink UID가 같습니다.")
    if peripheral.volume.root.resolve() == central.volume.root.resolve():
        raise M21HilFailure("peripheral과 central DAPLink MSD가 같습니다.")
    if peripheral.port_name.casefold() == central.port_name.casefold():
        raise M21HilFailure("peripheral과 central UART가 같습니다.")


## @brief UID로 DAPLink MSD와 target UART를 찾습니다.
def discover_endpoint(
    board_id: str,
    explicit_volume: str | None,
    explicit_port: str,
    list_ports: Any,
) -> RoleEndpoint:
    normalized = normalize_board_id(board_id)
    return RoleEndpoint(
        normalized,
        find_daplink_volume(normalized, explicit_volume),
        find_serial_port(normalized, explicit_port, list_ports),
    )


## @brief exact commit HIL이 요구하는 source와 board clean 상태를 검사합니다.
def validate_source_clean() -> None:
    scopes = (
        "cores/arduino",
        "libraries/NUCODE_BLE",
        "libraries/NUCODE_BLE_Security",
        "third_party/ArduinoCore-API",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/m21_ble_hil",
        "tests/hil/nu54dk/m21_ble_security.py",
    )
    result = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *scopes,
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip():
        raise M21HilFailure(
            "M21 HIL source가 exact clean commit이 아닙니다: "
            + (result.stdout.strip() or result.stderr.strip())
        )
    board = subprocess.run(
        ("git", "-C", str(BOARD_ROOT), "status", "--porcelain=v1"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if board.returncode != 0 or board.stdout.strip():
        raise M21HilFailure("board_package submodule이 clean하지 않습니다.")


## @brief HEX build record를 현재 exact commit과 source byte에 결합합니다.
def validate_build_record(
    image: Path, core_revision: str, board_revision: str
) -> dict[str, str]:
    record = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record.stat().st_size > 16384:
            raise M21HilFailure("NUCODE build record가 허용 크기를 넘었습니다.")
        text = record.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise M21HilFailure(f"M21 HEX build record를 읽지 못했습니다: {record}") from error
    keys = (
        "core_revision",
        "core_source_sha256",
        "application_source_sha256",
        "board_revision",
        "board_source_sha256",
        "ncs_revision",
        "zephyr_revision",
        "board",
        "board_qualifiers",
    )
    values = {key: build_record_value(text, key) for key in keys}
    expected = {
        "core_revision": core_revision[:12],
        "board_revision": board_revision[:12],
        "ncs_revision": "99553055607b",
        "zephyr_revision": "bf801e4e3d19",
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
        "core_source_sha256": files_digest(REPOSITORY, CORE_SOURCE_SCOPES),
        "application_source_sha256": files_digest(
            APPLICATION_SOURCE_ROOT, (APPLICATION_SOURCE_ROOT,)
        ),
        "board_source_sha256": files_digest(
            BOARD_ROOT, (BOARD_ROOT / "boards" / "nucode" / "nu54dk",)
        ),
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise M21HilFailure(
                f"M21 build record가 exact source와 다릅니다: {key}="
                f"{values[key]}, expected={expected_value}"
            )
    values["record_sha256"] = file_sha256(record)
    return values


## @brief evidence와 두 raw transcript의 신규 경로를 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path, Path]:
    if not evidence_argument:
        raise M21HilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise M21HilFailure("--evidence는 .json 확장자여야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise M21HilFailure("기존 증적을 자동 덮어쓰지 않습니다.")
    for path in existing:
        if not path.is_file():
            raise M21HilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
        path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return paths


## @brief 한 role image를 DAPLink MSD에 기록합니다.
def flash_image(
    role: str, volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise M21HilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    destination = volume.root / f"NUCODE_M21_{role.upper()}.HEX"
    shutil.copyfile(image, destination)
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief 제한된 UART buffer에서 완전한 한 줄을 읽습니다.
def read_line(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> bytes:
    while time.monotonic() < deadline:
        newline = pending.find(b"\n")
        if newline >= 0:
            raw = bytes(pending[: newline + 1])
            del pending[: newline + 1]
            return raw.rstrip(b"\r\n")
        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            pending.extend(chunk)
            capture.extend(chunk)
            if len(capture) > MAX_TRANSCRIPT_BYTES:
                raise M21HilFailure("M21 UART transcript가 허용 크기를 넘었습니다.")
    raise TimeoutError("M21 UART token 대기 시간이 끝났습니다.")


## @brief 현재 nonce의 원하는 protocol line이 나올 때까지 fail-closed 대기합니다.
def wait_token(
    serial_port: Any,
    role: str,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    predicate: Callable[[bytes], bool],
) -> bytes:
    expected_suffix = f":nonce={nonce}".encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line:
            print(f"[{role}] {line.decode('utf-8', errors='backslashreplace')}")
        if line.startswith(FAIL_PREFIX):
            raise M21HilFailure(f"{role} target 실패: {line!r}")
        if line.startswith(PROTOCOL_PREFIX) and b":nonce=" in line and not line.endswith(
            expected_suffix
        ):
            raise M21HilFailure(f"{role} stale nonce token입니다: {line!r}")
        if predicate(line):
            return line


## @brief UART 명령을 완전하게 기록합니다.
def send_command(serial_port: Any, verb: str, nonce: str) -> None:
    command = f"NUCODE_M21_{verb}:{nonce}\r\n".encode("ascii")
    written = serial_port.write(command)
    serial_port.flush()
    if written != len(command):
        raise M21HilFailure(f"M21 {verb} 명령이 일부만 기록됐습니다.")


## @brief 양쪽 role token을 서로의 UART를 막지 않고 동시에 기다립니다.
def wait_pair_tokens(
    peripheral_serial: Any,
    central_serial: Any,
    nonce: str,
    peripheral_pending: bytearray,
    central_pending: bytearray,
    peripheral_capture: bytearray,
    central_capture: bytearray,
    deadline: float,
    peripheral_predicate: Callable[[bytes], bool],
    central_predicate: Callable[[bytes], bool],
) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(
                wait_token,
                peripheral_serial,
                "peripheral",
                nonce,
                peripheral_pending,
                peripheral_capture,
                deadline,
                peripheral_predicate,
            ),
            executor.submit(
                wait_token,
                central_serial,
                "central",
                nonce,
                central_pending,
                central_capture,
                deadline,
                central_predicate,
            ),
        )
        for future in futures:
            future.result()


## @brief 두 role의 광고→연결 phase를 시작합니다.
def start_phase(
    peripheral_serial: Any,
    central_serial: Any,
    nonce: str,
    phase: str,
    peripheral_pending: bytearray,
    peripheral_capture: bytearray,
    deadline: float,
    command: str = "START",
) -> None:
    send_command(peripheral_serial, command, nonce)
    expected = (
        f"NUCODE_M21_PERIPHERAL:ADVERTISE:PASS:phase={phase}:"
        f"rf_nonce_binding_bits={RF_NONCE_BINDING_BITS}:nonce={nonce}"
    ).encode("ascii")
    wait_token(
        peripheral_serial,
        "peripheral",
        nonce,
        peripheral_pending,
        peripheral_capture,
        deadline,
        lambda line: line == expected,
    )
    send_command(central_serial, command, nonce)


## @brief flash 뒤 persistence·삭제 재부팅·old-key 거부·repair를 수행합니다.
def execute_pair(
    *,
    serial_module: Any,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    peripheral_image: Path,
    central_image: Path,
    nonce: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
) -> PairExecution:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise M21HilFailure(f"M21 기준선은 {DEFAULT_BAUD_RATE} baud입니다.")
    if not 120.0 <= result_timeout <= 900.0:
        raise M21HilFailure("--result-timeout은 120..900초 범위여야 합니다.")

    peripheral_capture = bytearray()
    central_capture = bytearray()
    peripheral_pending = bytearray()
    central_pending = bytearray()
    peripheral_flash = ("not-started", "unknown")
    central_flash = ("not-started", "unknown")
    try:
        with ExitStack() as stack:
            def open_serial(port: str) -> Any:
                return stack.enter_context(
                    serial_module.Serial(
                        port=port,
                        baudrate=baud_rate,
                        bytesize=serial_module.EIGHTBITS,
                        parity=serial_module.PARITY_NONE,
                        stopbits=serial_module.STOPBITS_ONE,
                        timeout=0.1,
                        write_timeout=2.0,
                    )
                )

            peripheral_serial = open_serial(peripheral_endpoint.port_name)
            central_serial = open_serial(central_endpoint.port_name)
            peripheral_serial.reset_input_buffer()
            central_serial.reset_input_buffer()
            peripheral_flash = flash_image(
                "peripheral", peripheral_endpoint.volume, peripheral_image, flash_timeout
            )
            central_flash = flash_image(
                "central", central_endpoint.volume, central_image, flash_timeout
            )
            deadline = time.monotonic() + result_timeout

            ready = lambda role: lambda line: line.startswith(
                f"NUCODE_M21_READY:role={role}:bond_count=".encode("ascii")
            )
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                ready("peripheral"),
                ready("central"),
            )

            for port in (peripheral_serial, central_serial):
                send_command(port, "CLEAR", nonce)
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                lambda line: line.startswith(b"NUCODE_M21_PERIPHERAL:CLEAR:REQUESTED:"),
                lambda line: line.startswith(b"NUCODE_M21_CENTRAL:CLEAR:REQUESTED:"),
            )

            for port in (peripheral_serial, central_serial):
                send_command(port, "REBOOT", nonce)
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                lambda line: line == b"NUCODE_M21_READY:role=peripheral:bond_count=0",
                lambda line: line == b"NUCODE_M21_READY:role=central:bond_count=0",
            )

            phase_predicate = lambda role, phase: lambda line: line.startswith(
                f"NUCODE_M21_{role.upper()}:PHASE:PASS:phase={phase}:".encode("ascii")
            )
            start_phase(
                peripheral_serial,
                central_serial,
                nonce,
                "first",
                peripheral_pending,
                peripheral_capture,
                deadline,
            )
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                phase_predicate("peripheral", "first"),
                phase_predicate("central", "first"),
            )

            for port in (peripheral_serial, central_serial):
                send_command(port, "REBOOT", nonce)
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                ready("peripheral"),
                ready("central"),
            )
            start_phase(
                peripheral_serial,
                central_serial,
                nonce,
                "restore",
                peripheral_pending,
                peripheral_capture,
                deadline,
            )
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                phase_predicate("peripheral", "restore"),
                phase_predicate("central", "restore"),
            )

            for port in (peripheral_serial, central_serial):
                send_command(port, "ERASE", nonce)
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                lambda line: line.startswith(b"NUCODE_M21_PERIPHERAL:ERASE:REQUESTED:"),
                lambda line: line.startswith(b"NUCODE_M21_CENTRAL:ERASE:REQUESTED:"),
            )
            for port in (peripheral_serial, central_serial):
                send_command(port, "REBOOT", nonce)
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                lambda line: line == b"NUCODE_M21_READY:role=peripheral:bond_count=0",
                lambda line: line == b"NUCODE_M21_READY:role=central:bond_count=0",
            )
            start_phase(
                peripheral_serial,
                central_serial,
                nonce,
                "erased_probe",
                peripheral_pending,
                peripheral_capture,
                deadline,
                command="PROBE",
            )
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                lambda line: line.startswith(
                    b"NUCODE_M21_PERIPHERAL:OLD_KEY:RECONNECT:REJECTED:bond_count=0:"
                ),
                lambda line: line.startswith(
                    b"NUCODE_M21_CENTRAL:OLD_KEY:RECONNECT:REJECTED:bond_count=0:"
                ),
            )
            start_phase(
                peripheral_serial,
                central_serial,
                nonce,
                "repair",
                peripheral_pending,
                peripheral_capture,
                deadline,
                command="REPAIR",
            )
            final = lambda role: lambda line: line.startswith(
                f"NUCODE_M21_{role.upper()}:FINAL:PASS:".encode("ascii")
            )
            wait_pair_tokens(
                peripheral_serial,
                central_serial,
                nonce,
                peripheral_pending,
                central_pending,
                peripheral_capture,
                central_capture,
                deadline,
                final("peripheral"),
                final("central"),
            )
    except Exception as error:
        raise M21ExecutionFailure(
            str(error), bytes(peripheral_capture), bytes(central_capture)
        ) from error

    return PairExecution(
        RoleExecution(*peripheral_flash, bytes(peripheral_capture)),
        RoleExecution(*central_flash, bytes(central_capture)),
    )


## @brief M21 protocol line을 추출하고 stale nonce와 target FAIL을 거부합니다.
def protocol_lines(transcript: bytes, nonce: str) -> list[bytes]:
    suffix = f":nonce={nonce}".encode("ascii")
    lines = [
        line.strip()
        for line in transcript.replace(b"\r", b"").split(b"\n")
        if line.strip().startswith(PROTOCOL_PREFIX)
    ]
    for line in lines:
        if line.startswith(FAIL_PREFIX):
            raise M21HilFailure(f"target이 M21 실패를 보고했습니다: {line!r}")
        if b":nonce=" in line and not line.endswith(suffix):
            raise M21HilFailure(f"stale nonce token입니다: {line!r}")
    return lines


## @brief 필요한 token을 transcript 순서대로 정확히 소비합니다.
def require_ordered(lines: list[bytes], required: Sequence[bytes]) -> None:
    cursor = 0
    for expected in required:
        while cursor < len(lines) and lines[cursor] != expected:
            cursor += 1
        if cursor >= len(lines):
            raise M21HilFailure(f"필수 M21 token이 누락됐습니다: {expected!r}")
        cursor += 1


## @brief role transcript의 persistence·삭제 재부팅·old-key 거부를 검증합니다.
def parse_role_transcript(transcript: bytes, role: str, nonce: str) -> RoleResult:
    if role not in ("peripheral", "central"):
        raise M21HilFailure("role은 peripheral 또는 central이어야 합니다.")
    lines = protocol_lines(transcript, nonce)
    upper = role.upper()
    suffix = f":nonce={nonce}".encode("ascii")
    old_key_prefix = (
        f"NUCODE_M21_{upper}:OLD_KEY:RECONNECT:REJECTED:bond_count=0:"
        "pairing_requested="
    ).encode("ascii")
    old_key_lines = [
        line
        for line in lines
        if line.startswith(old_key_prefix) and line.endswith(suffix)
    ]
    if len(old_key_lines) != 1 or not re.fullmatch(
        old_key_prefix
        + rb"[01]:security_failed=[01]"
        + re.escape(suffix),
        old_key_lines[0] if old_key_lines else b"",
    ):
        raise M21HilFailure(f"old-key 재연결 거부 token이 잘못됐습니다: {old_key_lines!r}")
    if b"pairing_requested=0:security_failed=0" in old_key_lines[0]:
        raise M21HilFailure("old-key 재연결 실패 근거가 비어 있습니다.")
    old_key_line = old_key_lines[0]
    common = [
        (
            f"NUCODE_M21_{upper}:PHASE:PASS:phase=first:pairing_events=1:"
            "bond_count=1:bond_state=persistence_pending"
        ).encode()
        + suffix,
        f"NUCODE_M21_READY:role={role}:bond_count=1".encode(),
        (
            f"NUCODE_M21_{upper}:PHASE:PASS:phase=restore:pairing_events=0:"
            "bond_count=1:bond_state=verified"
        ).encode()
        + suffix,
        f"NUCODE_M21_{upper}:ERASE:REQUESTED".encode() + suffix,
        f"NUCODE_M21_READY:role={role}:bond_count=0".encode(),
        old_key_line,
        (
            f"NUCODE_M21_{upper}:PHASE:PASS:phase=repair:pairing_events=1:"
            "bond_count=1:bond_state=persistence_pending"
        ).encode()
        + suffix,
        (
            f"NUCODE_M21_{upper}:FINAL:PASS:pairing=PASS:bond_restore=PASS:"
            "erase_reboot=PASS:old_key_reconnect=REJECTED:repair=PASS:"
            "bas=PASS:dis=PASS:hid_protocol=PASS"
        ).encode()
        + suffix,
    ]
    binding_tokens = [
        (
            f"NUCODE_M21_{upper}:"
            f"{'SCAN' if role == 'central' else 'ADVERTISE'}:PASS:phase={phase}:"
            f"rf_nonce_binding_bits={RF_NONCE_BINDING_BITS}"
        ).encode()
        + suffix
        for phase in ("first", "restore", "erased_probe", "repair")
    ]
    require_ordered(lines, binding_tokens)
    if role == "central":
        profile = [
            f"NUCODE_M21_CENTRAL:SECURE_GATT:DENIED".encode() + suffix,
            f"NUCODE_M21_CENTRAL:BAS:READ:PASS:value=73".encode() + suffix,
            f"NUCODE_M21_CENTRAL:BAS:NOTIFY:PASS:value=72".encode() + suffix,
            (
                "NUCODE_M21_CENTRAL:DIS:PASS:manufacturer=NUCODE:"
                "model=NU54DK-M21:serial=M21-HIL"
            ).encode()
            + suffix,
            (
                "NUCODE_M21_CENTRAL:HID:REPORT:PASS:bytes=8:"
                "down=04:release=00"
            ).encode()
            + suffix,
        ]
        require_ordered(lines, profile + common)
    else:
        profile = (
            "NUCODE_M21_PERIPHERAL:PROFILE:PASS:bas_notify=72:hid_bytes=8"
        ).encode() + suffix
        require_ordered(lines, [profile, *common])
    return RoleResult(
        role,
        nonce,
        ("first", "restore", "erased_probe", "repair"),
        (1, 0, 1),
        (1, 1, 0, 1),
        ("persistence_pending", "verified", "none", "persistence_pending"),
        RF_NONCE_BINDING_BITS,
        True,
        True,
        True,
    )


## @brief JSON evidence를 exact images, boards와 raw transcript hash에 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    nonce: str,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    peripheral_image: Path,
    central_image: Path,
    execution: PairExecution,
    peripheral_result: RoleResult,
    central_result: RoleResult,
) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "gate": "m21-ble-security-profile-pair-hil",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "nonce": nonce,
        "rf_nonce_binding_bits": RF_NONCE_BINDING_BITS,
        "boards": {
            "peripheral": {
                "daplink_uid": peripheral_endpoint.board_id,
                "uart_port": peripheral_endpoint.port_name,
            },
            "central": {
                "daplink_uid": central_endpoint.board_id,
                "uart_port": central_endpoint.port_name,
            },
        },
        "images": {
            "peripheral": {
                "name": peripheral_image.name,
                "sha256": file_sha256(peripheral_image),
                "flash_sequence": execution.peripheral.flash_sequence,
            },
            "central": {
                "name": central_image.name,
                "sha256": file_sha256(central_image),
                "flash_sequence": execution.central.flash_sequence,
            },
        },
        "transcripts": {
            "peripheral_sha256": hashlib.sha256(
                execution.peripheral.transcript
            ).hexdigest(),
            "central_sha256": hashlib.sha256(execution.central.transcript).hexdigest(),
        },
        "results": {
            "peripheral": asdict(peripheral_result),
            "central": asdict(central_result),
        },
        "coverage": {
            "pairing": True,
            "bond_warm_reboot_restore": True,
            "bond_persistence_pending_not_verified_same_boot": True,
            "bond_delete_request_accepted": True,
            "bond_delete_warm_reboot_zero": True,
            "old_key_reconnect_rejected": True,
            "bond_repair": True,
            "encrypted_gatt_negative": True,
            "bas_read_and_notify": True,
            "dis_read": True,
            "hid_report_protocol": True,
            "windows_or_smartphone_hid_input": False,
            "manual_os_hid_confirmation_pending": True,
        },
        "safety": {"mass_erase_requested": False, "factory_reset_executed": False},
    }


## @brief 장치 탐색 또는 전체 M21 두 보드 HIL을 수행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    serial_module, list_ports = import_pyserial()
    peripheral_endpoint = discover_endpoint(
        args.peripheral_board_id,
        args.peripheral_volume,
        args.peripheral_port,
        list_ports,
    )
    central_endpoint = discover_endpoint(
        args.central_board_id,
        args.central_volume,
        args.central_port,
        list_ports,
    )
    validate_pair_identity(peripheral_endpoint, central_endpoint)
    print(
        "NU54DK M21 pair discovery SUCCESS: "
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
    if file_sha256(peripheral_image) == file_sha256(central_image):
        raise M21HilFailure("두 role HEX가 동일합니다.")
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean()
    validate_build_record(peripheral_image, core_revision, board_revision)
    validate_build_record(central_image, core_revision, board_revision)
    nonce = build_nonce()
    try:
        execution = execute_pair(
            serial_module=serial_module,
            peripheral_endpoint=peripheral_endpoint,
            central_endpoint=central_endpoint,
            peripheral_image=peripheral_image,
            central_image=central_image,
            nonce=nonce,
            baud_rate=args.baud,
            flash_timeout=args.flash_timeout,
            result_timeout=args.result_timeout,
        )
        peripheral_log.write_bytes(execution.peripheral.transcript)
        central_log.write_bytes(execution.central.transcript)
        peripheral_result = parse_role_transcript(
            execution.peripheral.transcript, "peripheral", nonce
        )
        central_result = parse_role_transcript(execution.central.transcript, "central", nonce)
        if b"pairing_requested=1" not in (
            execution.peripheral.transcript + execution.central.transcript
        ):
            raise M21HilFailure(
                "old-key 재연결에서 새 pairing이 필요했다는 양쪽 공통 근거가 없습니다."
            )
        evidence = build_evidence(
            core_revision=core_revision,
            board_revision=board_revision,
            nonce=nonce,
            peripheral_endpoint=peripheral_endpoint,
            central_endpoint=central_endpoint,
            peripheral_image=peripheral_image,
            central_image=central_image,
            execution=execution,
            peripheral_result=peripheral_result,
            central_result=central_result,
        )
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"M21 BLE SECURITY PROFILE HIL PASS: nonce={nonce}, evidence={evidence_path}")
        return 0
    except M21ExecutionFailure as error:
        peripheral_log.write_bytes(error.peripheral_transcript)
        central_log.write_bytes(error.central_transcript)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"M21 BLE SECURITY PROFILE HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
