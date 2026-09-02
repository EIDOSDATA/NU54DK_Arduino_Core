#!/usr/bin/env python3
"""! @brief 두 NU54DK의 BLE NUS 양방향·재연결 M16 HIL을 자동 검증합니다. """

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
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m16_ble_hil"
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


PROTOCOL_PREFIX = b"NUCODE_M16_"
FAIL_PREFIX = b"NUCODE_M16_FAIL:"
NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_RESULT_TIMEOUT_SECONDS = 180.0
MAX_TRANSCRIPT_BYTES = 262144
EVIDENCE_SCHEMA = 1


class BlePairHilFailure(RuntimeError):
    """! @brief M16 BLE pair HIL의 장치·protocol·증적 실패를 나타냅니다. """


class PairExecutionFailure(BlePairHilFailure):
    """! @brief 실행 실패와 양쪽 UART 원문을 함께 보존합니다. """

    def __init__(
        self, message: str, peripheral_transcript: bytes, central_transcript: bytes
    ) -> None:
        """! @brief 오류 설명과 실패 시점까지의 두 transcript를 저장합니다. """

        super().__init__(message)
        self.peripheral_transcript = peripheral_transcript
        self.central_transcript = central_transcript


@dataclass(frozen=True)
class RoleEndpoint:
    """! @brief 한 BLE role에 결합된 DAPLink UID·MSD·UART를 보관합니다. """

    board_id: str
    volume: DaplinkVolume
    port_name: str


@dataclass(frozen=True)
class CentralResult:
    """! @brief central UART에서 검증한 frame·연결 경계 결과입니다. """

    nonce: str
    frame_sizes_round_1: tuple[int, ...]
    frame_sizes_round_2: tuple[int, ...]
    connection_rounds: tuple[int, ...]
    disconnection_count: int
    callback_context: str
    reconnect: str


@dataclass(frozen=True)
class PeripheralResult:
    """! @brief peripheral UART에서 검증한 광고·수신량·재연결 결과입니다. """

    nonce: str
    first_round_bytes: int
    second_round_bytes: int
    connection_rounds: tuple[int, ...]
    disconnection_count: int
    callback_context: str
    reconnect: str


@dataclass(frozen=True)
class RoleExecution:
    """! @brief 한 role의 flash 결과와 원문 UART transcript입니다. """

    flash_sequence: str
    flash_bytes: str
    transcript: bytes


@dataclass(frozen=True)
class PairExecution:
    """! @brief 두 role의 동시 HIL 실행 결과입니다. """

    peripheral: RoleExecution
    central: RoleExecution


## @brief CLI 인자를 만들며 두 DAPLink UID를 실제 실행에서 반드시 요구합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "두 NU54DK에 M16 peripheral/central image를 기록하고 NUS frame 경계와 "
            "disconnect/reconnect를 자동 검증합니다."
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
    parser.add_argument("--evidence", help="PASS JSON evidence 경로")
    parser.add_argument(
        "--expected-core-revision", help="시험할 checkout의 기대 40자리 Core commit"
    )
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


## @brief 동일 실행에서 사용할 32자리 소문자 hex nonce를 검증하거나 생성합니다.
def build_nonce(explicit_nonce: str | None = None) -> str:
    nonce = explicit_nonce if explicit_nonce is not None else secrets.token_hex(16)
    if NONCE_PATTERN.fullmatch(nonce) is None:
        raise BlePairHilFailure("M16 nonce는 32자리 소문자 hex여야 합니다.")
    return nonce


## @brief 두 role의 UID·MSD·UART가 모두 서로 다른 물리 endpoint인지 검사합니다.
def validate_pair_identity(peripheral: RoleEndpoint, central: RoleEndpoint) -> None:
    if peripheral.board_id == central.board_id:
        raise BlePairHilFailure("peripheral과 central DAPLink UID가 같을 수 없습니다.")
    if peripheral.volume.root.resolve() == central.volume.root.resolve():
        raise BlePairHilFailure("peripheral과 central이 같은 DAPLink MSD를 가리킵니다.")
    if peripheral.port_name.casefold() == central.port_name.casefold():
        raise BlePairHilFailure("peripheral과 central이 같은 UART 포트를 가리킵니다.")


## @brief 한 role의 UID로 DAPLink MSD와 target UART를 함께 찾습니다.
def discover_endpoint(
    board_id: str,
    explicit_volume: str | None,
    explicit_port: str,
    list_ports: Any,
) -> RoleEndpoint:
    normalized = normalize_board_id(board_id)
    volume = find_daplink_volume(normalized, explicit_volume)
    port_name = find_serial_port(normalized, explicit_port, list_ports)
    return RoleEndpoint(normalized, volume, port_name)


## @brief M16 HIL 입력 source와 board checkout이 exact commit으로 clean한지 검사합니다.
def validate_source_clean() -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/m16_ble_hil",
        "tests/hil/nu54dk/m16_ble_pair.py",
        "tests/hil/nu54dk/m14_pin_hil.py",
        "tests/hil/nu54dk/m6_serial_echo.py",
    )
    core = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *core_paths,
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    board = subprocess.run(
        (
            "git",
            "-C",
            str(BOARD_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if core.returncode != 0 or core.stdout.strip():
        raise BlePairHilFailure(
            "M16 BLE pair HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise BlePairHilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief CMake build record와 같은 checkout byte 기준 source digest를 계산합니다.
def current_source_digests() -> dict[str, str]:
    board_scope = BOARD_ROOT / "boards" / "nucode" / "nu54dk"
    return {
        "core_source_sha256": files_digest(REPOSITORY, CORE_SOURCE_SCOPES),
        "application_source_sha256": files_digest(
            APPLICATION_SOURCE_ROOT, (APPLICATION_SOURCE_ROOT,)
        ),
        "board_source_sha256": files_digest(BOARD_ROOT, (board_scope,)),
    }


## @brief HEX build record를 exact revision·target·source byte와 결합합니다.
def validate_build_record(
    image: Path, core_revision: str, board_revision: str
) -> dict[str, str]:
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record_path.stat().st_size > 16384:
            raise BlePairHilFailure("NUCODE build record가 허용 크기를 초과했습니다.")
        text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BlePairHilFailure(
            f"HEX의 NUCODE build record를 읽지 못했습니다: {record_path}: {error}"
        ) from error

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
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise BlePairHilFailure(
                "NUCODE build record가 exact M16 HIL 계약과 다릅니다: "
                f"{key}={values[key]}, expected={expected_value}"
            )
    for key, expected_digest in current_source_digests().items():
        if re.fullmatch(r"[0-9a-f]{64}", values[key]) is None:
            raise BlePairHilFailure(f"NUCODE build record digest가 잘못되었습니다: {key}")
        if values[key] != expected_digest:
            raise BlePairHilFailure(
                "NUCODE build record source digest가 현재 exact source와 다릅니다: "
                f"{key}={values[key]}, expected={expected_digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief 시험 도중 HEX byte가 변경되지 않았는지 검사합니다.
def validate_image_unchanged(image: Path, size: int, sha256: str) -> None:
    if image.stat().st_size != size or file_sha256(image) != sha256:
        raise BlePairHilFailure("시험 중 M16 HEX byte가 변경되어 PASS 생성을 거부했습니다.")


## @brief evidence와 두 raw transcript 경로를 안전하게 신규 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path, Path]:
    if not evidence_argument:
        raise BlePairHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise BlePairHilFailure("--evidence는 .json 확장자여야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise BlePairHilFailure(
            "기존 증적을 자동 덮어쓰지 않습니다: "
            + ", ".join(str(path) for path in existing)
        )
    for path in existing:
        if not path.is_file():
            raise BlePairHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing:
            path.unlink()
    return paths


## @brief 한 role의 HEX를 해당 DAPLink MSD에 기록하고 결과를 반환합니다.
def flash_image(
    role: str, volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise BlePairHilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    destination = volume.root / f"NUCODE_M16_{role.upper()}.HEX"
    shutil.copyfile(image, destination)
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief 제한된 UART buffer에서 완전한 line 하나를 읽고 원문에 누적합니다.
def read_line(
    serial_port: Any,
    pending: bytearray,
    raw_capture: bytearray,
    deadline: float,
    stop_event: threading.Event | None = None,
) -> bytes:
    while time.monotonic() < deadline:
        newline = pending.find(b"\n")
        if newline >= 0:
            raw = bytes(pending[: newline + 1])
            del pending[: newline + 1]
            return raw.rstrip(b"\r\n")
        if stop_event is not None and stop_event.is_set():
            raise BlePairHilFailure("다른 BLE role 실패로 UART 수집을 중단했습니다.")
        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            pending.extend(chunk)
            raw_capture.extend(chunk)
            if len(raw_capture) > MAX_TRANSCRIPT_BYTES:
                raise BlePairHilFailure("M16 UART transcript가 허용 크기를 초과했습니다.")
    raise TimeoutError("M16 UART line을 제한 시간 안에 읽지 못했습니다.")


## @brief role UART가 정확한 READY token을 낼 때까지 수집합니다.
def wait_ready(
    serial_port: Any,
    role: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    expected = f"NUCODE_M16_READY:role={role}".encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(FAIL_PREFIX):
            raise BlePairHilFailure(f"{role} target 실패: {line!r}")
        if line.startswith(PROTOCOL_PREFIX) and line != expected:
            raise BlePairHilFailure(
                f"{role} READY 앞 stale/예상 밖 protocol token입니다: {line!r}"
            )
        if line == expected:
            return


## @brief UART에 동일 nonce의 M16 시작 명령을 완전하게 기록합니다.
def write_start_command(serial_port: Any, nonce: str) -> None:
    request = f"NUCODE_M16_START:{nonce}\r\n".encode("ascii")
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise BlePairHilFailure(
            f"M16 시작 명령 일부만 전송했습니다: 기대={len(request)}, 실제={written}"
        )


## @brief peripheral 광고 시작 token을 확인한 뒤 central scan을 허용합니다.
def wait_peripheral_advertising(
    serial_port: Any,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    expected = f"NUCODE_M16_PERIPHERAL:ADVERTISE:PASS:nonce={nonce}".encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(FAIL_PREFIX):
            raise BlePairHilFailure(f"peripheral target 실패: {line!r}")
        if line.startswith(PROTOCOL_PREFIX) and line != expected:
            raise BlePairHilFailure(
                f"광고 시작 전 stale/예상 밖 protocol token입니다: {line!r}"
            )
        if line == expected:
            return


## @brief 한 role의 현재 nonce FINAL token까지 UART를 독립 수집합니다.
def collect_until_final(
    serial_port: Any,
    role: str,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    final_prefix = f"NUCODE_M16_{role.upper()}:FINAL:PASS:".encode("ascii")
    expected_suffix = f":nonce={nonce}".encode("ascii")
    try:
        while True:
            line = read_line(
                serial_port, pending, capture, deadline, stop_event=stop_event
            )
            if line:
                print(f"[{role}] {line.decode('utf-8', errors='backslashreplace')}")
            if line.startswith(FAIL_PREFIX):
                raise BlePairHilFailure(f"{role} target 실패: {line!r}")
            if line.startswith(final_prefix):
                if not line.endswith(expected_suffix):
                    raise BlePairHilFailure(
                        f"{role} FINAL nonce가 현재 실행과 다릅니다: {line!r}"
                    )
                return
    except Exception:
        stop_event.set()
        raise


## @brief serial port를 flash 전에 열어 양쪽 boot READY를 손실 없이 보존합니다.
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
        raise BlePairHilFailure(
            f"M16 기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다: 요청={baud_rate}"
        )
    if not 30.0 <= result_timeout <= 600.0:
        raise BlePairHilFailure("--result-timeout은 30..600초 범위여야 합니다.")

    peripheral_capture = bytearray()
    central_capture = bytearray()
    peripheral_pending = bytearray()
    central_pending = bytearray()
    peripheral_flash = ("not-started", "unknown")
    central_flash = ("not-started", "unknown")

    try:
        with ExitStack() as stack:
            peripheral_serial = stack.enter_context(
                serial_module.Serial(
                    port=peripheral_endpoint.port_name,
                    baudrate=baud_rate,
                    bytesize=serial_module.EIGHTBITS,
                    parity=serial_module.PARITY_NONE,
                    stopbits=serial_module.STOPBITS_ONE,
                    timeout=0.1,
                    write_timeout=2.0,
                )
            )
            central_serial = stack.enter_context(
                serial_module.Serial(
                    port=central_endpoint.port_name,
                    baudrate=baud_rate,
                    bytesize=serial_module.EIGHTBITS,
                    parity=serial_module.PARITY_NONE,
                    stopbits=serial_module.STOPBITS_ONE,
                    timeout=0.1,
                    write_timeout=2.0,
                )
            )
            peripheral_serial.reset_input_buffer()
            central_serial.reset_input_buffer()

            peripheral_flash = flash_image(
                "peripheral", peripheral_endpoint.volume, peripheral_image, flash_timeout
            )
            central_flash = flash_image(
                "central", central_endpoint.volume, central_image, flash_timeout
            )
            deadline = time.monotonic() + result_timeout
            wait_ready(
                peripheral_serial,
                "peripheral",
                peripheral_pending,
                peripheral_capture,
                deadline,
            )
            wait_ready(
                central_serial,
                "central",
                central_pending,
                central_capture,
                deadline,
            )

            write_start_command(peripheral_serial, nonce)
            wait_peripheral_advertising(
                peripheral_serial,
                nonce,
                peripheral_pending,
                peripheral_capture,
                deadline,
            )
            write_start_command(central_serial, nonce)

            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as executor:
                peripheral_future = executor.submit(
                    collect_until_final,
                    peripheral_serial,
                    "peripheral",
                    nonce,
                    peripheral_pending,
                    peripheral_capture,
                    deadline,
                    stop_event,
                )
                central_future = executor.submit(
                    collect_until_final,
                    central_serial,
                    "central",
                    nonce,
                    central_pending,
                    central_capture,
                    deadline,
                    stop_event,
                )
                try:
                    peripheral_future.result()
                    central_future.result()
                except Exception:
                    stop_event.set()
                    raise
    except Exception as error:
        raise PairExecutionFailure(
            str(error), bytes(peripheral_capture), bytes(central_capture)
        ) from error

    return PairExecution(
        peripheral=RoleExecution(
            flash_sequence=peripheral_flash[0],
            flash_bytes=peripheral_flash[1],
            transcript=bytes(peripheral_capture),
        ),
        central=RoleExecution(
            flash_sequence=central_flash[0],
            flash_bytes=central_flash[1],
            transcript=bytes(central_capture),
        ),
    )


## @brief M16 protocol line만 추출하고 stale nonce·target FAIL을 fail-closed 거부합니다.
def protocol_lines(transcript: bytes, nonce: str) -> list[bytes]:
    expected_suffix = f":nonce={nonce}".encode("ascii")
    lines = [
        line.strip()
        for line in transcript.replace(b"\r", b"").split(b"\n")
        if line.strip().startswith(PROTOCOL_PREFIX)
    ]
    for line in lines:
        if line.startswith(FAIL_PREFIX):
            raise BlePairHilFailure(f"target이 M16 실패를 보고했습니다: {line!r}")
        if line.startswith(b"NUCODE_M16_READY:"):
            continue
        if not line.endswith(expected_suffix):
            raise BlePairHilFailure(
                f"stale 또는 다른 실행의 M16 nonce token을 거부했습니다: {line!r}"
            )
    return lines


## @brief strict protocol parser에서 다음 exact line을 소비합니다.
def take_exact(lines: list[bytes], cursor: int, expected: bytes) -> int:
    if cursor >= len(lines):
        raise BlePairHilFailure(f"M16 protocol line이 누락되었습니다: {expected!r}")
    if lines[cursor] != expected:
        raise BlePairHilFailure(
            f"M16 protocol 순서/값이 다릅니다: 기대={expected!r}, 실제={lines[cursor]!r}"
        )
    return cursor + 1


## @brief central transcript에서 1/20/21/64 frame과 재연결 round를 검증합니다.
def parse_central_transcript(transcript: bytes, nonce: str) -> CentralResult:
    nonce = build_nonce(nonce)
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, nonce)
    cursor = 0
    expected = [
        b"NUCODE_M16_READY:role=central",
        b"NUCODE_M16_CENTRAL:SCAN:PASS" + suffix,
        b"NUCODE_M16_EVENT:CONNECTED:round=1" + suffix,
        b"NUCODE_M16_EVENT:READY:round=1" + suffix,
    ]
    expected.extend(
        f"NUCODE_M16_CENTRAL:FRAME:PASS:round=1:size={size}:nonce={nonce}".encode(
            "ascii"
        )
        for size in (1, 20, 21, 64)
    )
    expected.extend(
        (
            b"NUCODE_M16_EVENT:DISCONNECTED:count=1" + suffix,
            b"NUCODE_M16_EVENT:CONNECTED:round=2" + suffix,
            b"NUCODE_M16_EVENT:READY:round=2" + suffix,
            b"NUCODE_M16_CENTRAL:FRAME:PASS:round=2:size=21" + suffix,
            b"NUCODE_M16_CENTRAL:FINAL:PASS:callback_context=PASS:"
            b"reconnect=PASS" + suffix,
        )
    )
    for line in expected:
        cursor = take_exact(lines, cursor, line)
    if cursor != len(lines):
        raise BlePairHilFailure(
            f"central FINAL 뒤 예상하지 않은 protocol token이 있습니다: {lines[cursor:]!r}"
        )
    return CentralResult(
        nonce=nonce,
        frame_sizes_round_1=(1, 20, 21, 64),
        frame_sizes_round_2=(21,),
        connection_rounds=(1, 2),
        disconnection_count=1,
        callback_context="PASS",
        reconnect="PASS",
    )


## @brief peripheral transcript에서 광고·106/21 byte와 재연결 round를 검증합니다.
def parse_peripheral_transcript(transcript: bytes, nonce: str) -> PeripheralResult:
    nonce = build_nonce(nonce)
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, nonce)
    expected = (
        b"NUCODE_M16_READY:role=peripheral",
        b"NUCODE_M16_PERIPHERAL:ADVERTISE:PASS" + suffix,
        b"NUCODE_M16_EVENT:CONNECTED:round=1" + suffix,
        b"NUCODE_M16_EVENT:READY:round=1" + suffix,
        b"NUCODE_M16_PERIPHERAL:ROUND:PASS:round=1:bytes=106" + suffix,
        b"NUCODE_M16_EVENT:DISCONNECTED:count=1" + suffix,
        b"NUCODE_M16_EVENT:CONNECTED:round=2" + suffix,
        b"NUCODE_M16_EVENT:READY:round=2" + suffix,
        b"NUCODE_M16_PERIPHERAL:FINAL:PASS:callback_context=PASS:"
        b"reconnect=PASS:bytes=21" + suffix,
    )
    cursor = 0
    for line in expected:
        cursor = take_exact(lines, cursor, line)
    if cursor != len(lines):
        raise BlePairHilFailure(
            "peripheral FINAL 뒤 예상하지 않은 protocol token이 있습니다: "
            f"{lines[cursor:]!r}"
        )
    return PeripheralResult(
        nonce=nonce,
        first_round_bytes=106,
        second_round_bytes=21,
        connection_rounds=(1, 2),
        disconnection_count=1,
        callback_context="PASS",
        reconnect="PASS",
    )


## @brief 두 이미지·보드·raw transcript identity를 하나의 PASS evidence로 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    nonce: str,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    peripheral_image: Path,
    central_image: Path,
    peripheral_image_size: int,
    central_image_size: int,
    peripheral_image_sha256: str,
    central_image_sha256: str,
    peripheral_build_record: dict[str, str],
    central_build_record: dict[str, str],
    peripheral_transcript_path: Path,
    central_transcript_path: Path,
    execution: PairExecution,
    peripheral_result: PeripheralResult,
    central_result: CentralResult,
) -> dict[str, Any]:
    def board_entry(endpoint: RoleEndpoint) -> dict[str, Any]:
        return {
            "daplink_uid": endpoint.board_id,
            "target_detect": detail_value(endpoint.volume.details, "Target Detect"),
            "msd_root": str(endpoint.volume.root),
            "uart_port": endpoint.port_name,
        }

    def image_entry(
        image: Path,
        size: int,
        sha256: str,
        role_execution: RoleExecution,
        build_record: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "name": image.name,
            "size": size,
            "sha256": sha256,
            "flash_sequence": role_execution.flash_sequence,
            "flash_bytes": role_execution.flash_bytes,
            "build_record": build_record,
        }

    def transcript_entry(path: Path, raw: bytes) -> dict[str, Any]:
        return {
            "name": path.name,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    return {
        "schema_version": EVIDENCE_SCHEMA,
        "gate": "m16-ble-nus-pair-hil",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "nonce": nonce,
        "boards": {
            "peripheral": board_entry(peripheral_endpoint),
            "central": board_entry(central_endpoint),
        },
        "images": {
            "peripheral": image_entry(
                peripheral_image,
                peripheral_image_size,
                peripheral_image_sha256,
                execution.peripheral,
                peripheral_build_record,
            ),
            "central": image_entry(
                central_image,
                central_image_size,
                central_image_sha256,
                execution.central,
                central_build_record,
            ),
        },
        "transcripts": {
            "peripheral": transcript_entry(
                peripheral_transcript_path, execution.peripheral.transcript
            ),
            "central": transcript_entry(
                central_transcript_path, execution.central.transcript
            ),
        },
        "results": {
            "peripheral": asdict(peripheral_result),
            "central": asdict(central_result),
        },
        "coverage": {
            "nus_peripheral": True,
            "nus_central": True,
            "bidirectional_echo": True,
            "frame_sizes": [1, 20, 21, 64],
            "disconnect_reconnect": True,
            "post_reconnect_frame_size": 21,
            "callback_context": "arduino-main-thread",
        },
        "safety": {
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    }


## @brief 실패 시점까지 확보한 두 raw transcript를 각각 보존합니다.
def save_failure_transcripts(
    peripheral_path: Path,
    central_path: Path,
    error: Exception,
) -> bool:
    if not isinstance(error, PairExecutionFailure):
        return False
    peripheral_path.write_bytes(error.peripheral_transcript)
    central_path.write_bytes(error.central_transcript)
    return True


## @brief 장치 탐색 또는 전체 M16 두 보드 BLE NUS HIL을 수행합니다.
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
        "NU54DK M16 pair discovery SUCCESS: "
        f"peripheral={peripheral_endpoint.board_id}/{peripheral_endpoint.volume.root}/"
        f"{peripheral_endpoint.port_name}, central={central_endpoint.board_id}/"
        f"{central_endpoint.volume.root}/{central_endpoint.port_name}"
    )
    if args.discover_only:
        return 0

    evidence_path, peripheral_transcript_path, central_transcript_path = (
        prepare_output_paths(args.evidence, args.overwrite_evidence)
    )
    peripheral_image = validate_hex_image(args.peripheral_hex)
    central_image = validate_hex_image(args.central_hex)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean()
    peripheral_build_record = validate_build_record(
        peripheral_image, core_revision, board_revision
    )
    central_build_record = validate_build_record(
        central_image, core_revision, board_revision
    )
    peripheral_image_size = peripheral_image.stat().st_size
    central_image_size = central_image.stat().st_size
    peripheral_image_sha256 = file_sha256(peripheral_image)
    central_image_sha256 = file_sha256(central_image)
    if peripheral_image_sha256 == central_image_sha256:
        raise BlePairHilFailure("peripheral과 central HEX가 동일하여 role 오배치를 거부했습니다.")

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
        validate_image_unchanged(
            peripheral_image, peripheral_image_size, peripheral_image_sha256
        )
        validate_image_unchanged(central_image, central_image_size, central_image_sha256)
        peripheral_transcript_path.write_bytes(execution.peripheral.transcript)
        central_transcript_path.write_bytes(execution.central.transcript)
        peripheral_result = parse_peripheral_transcript(
            execution.peripheral.transcript, nonce
        )
        central_result = parse_central_transcript(execution.central.transcript, nonce)
        evidence = build_evidence(
            core_revision=core_revision,
            board_revision=board_revision,
            nonce=nonce,
            peripheral_endpoint=peripheral_endpoint,
            central_endpoint=central_endpoint,
            peripheral_image=peripheral_image,
            central_image=central_image,
            peripheral_image_size=peripheral_image_size,
            central_image_size=central_image_size,
            peripheral_image_sha256=peripheral_image_sha256,
            central_image_sha256=central_image_sha256,
            peripheral_build_record=peripheral_build_record,
            central_build_record=central_build_record,
            peripheral_transcript_path=peripheral_transcript_path,
            central_transcript_path=central_transcript_path,
            execution=execution,
            peripheral_result=peripheral_result,
            central_result=central_result,
        )
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(
            "M16 BLE NUS PAIR HIL PASS: "
            f"nonce={nonce}, frames=1/20/21/64, reconnect=PASS, "
            f"evidence={evidence_path}"
        )
        return 0
    except Exception as error:
        save_failure_transcripts(
            peripheral_transcript_path, central_transcript_path, error
        )
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"M16 BLE NUS PAIR HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
