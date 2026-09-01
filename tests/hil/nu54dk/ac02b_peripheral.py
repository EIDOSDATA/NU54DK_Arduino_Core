#!/usr/bin/env python3
"""! @brief 두 NU54DK의 AC-02B 주변장치 물리 HIL을 fail-closed로 실행합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
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
    DEFAULT_RESULT_TIMEOUT_SECONDS,
    REPOSITORY,
    BlePairHilFailure,
    RoleEndpoint,
    RoleExecution,
    build_nonce,
    file_sha256,
    flash_image,
    git_revision,
    image_record,
    protocol_lines,
    read_line,
    take_exact,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_pair_identity,
    write_start_command,
)
from m6_serial_echo import (  # noqa: E402
    DAPLINK_PID,
    DAPLINK_VID,
    find_daplink_volume,
    import_pyserial,
    normalize_board_id,
    port_diagnostic,
)


MILESTONE = "AC02B"
DUT_APPLICATION = REPOSITORY / "tests" / "zephyr" / "ac02b_hil_dut"
PEER_APPLICATION = REPOSITORY / "tests" / "zephyr" / "ac02b_hil_peer"
EVIDENCE_SCHEMA = 2
WIRING_REQUIRED_EXIT_CODE = 3
CONSOLE_INTERFACE = 3
AUXILIARY_INTERFACE = 1
PORT_REDISCOVERY_TIMEOUT_SECONDS = 15.0

RELAY_STEPS = (
    ("PWM:ARM:25", "PWM:ARM:25:OK"),
    ("PWM:CHECK:25", "PWM:25:PASS"),
    ("PWM:ARM:75", "PWM:ARM:75:OK"),
    ("PWM:CHECK:75", "PWM:75:PASS"),
    ("ADC:LOW", "ADC:LOW:OK"),
    ("ADC:HIGH", "ADC:HIGH:OK"),
    ("ADC:LOW", "ADC:LOW:OK"),
    ("DONE", "DONE:PASS"),
)


class Ac02bHilFailure(BlePairHilFailure):
    """! @brief AC-02B 전용 fail-closed 오류입니다. """


class Ac02bExecutionFailure(Ac02bHilFailure):
    """! @brief 실패 시점 console·aux·relay transcript를 보존합니다. """

    def __init__(
        self,
        message: str,
        dut_transcript: bytes,
        peer_transcript: bytes,
        auxiliary_transcript: bytes,
        relay_transcript: bytes,
    ) -> None:
        super().__init__(message)
        self.dut_transcript = dut_transcript
        self.peer_transcript = peer_transcript
        self.auxiliary_transcript = auxiliary_transcript
        self.relay_transcript = relay_transcript


@dataclass(frozen=True)
class RuntimePorts:
    """! @brief flash 뒤 exact UID로 재탐색한 세 UART입니다. """

    dut_console: str
    dut_auxiliary: str
    peer_console: str


@dataclass(frozen=True)
class Ac02bExecution:
    """! @brief 두 role과 DUT aux/host relay의 raw transcript입니다. """

    dut: RoleExecution
    peer: RoleExecution
    dut_auxiliary_transcript: bytes
    relay_transcript: bytes
    runtime_ports: RuntimePorts


@dataclass(frozen=True)
class DutResult:
    """! @brief DUT parser가 승인한 주변장치 결과입니다. """

    nonce: str
    serial_cycles: int
    wire_clocks: tuple[int, int]
    spi_bytes: int
    pwm_duties: tuple[int, int]
    adc_low: int
    adc_high: int


@dataclass(frozen=True)
class PeerResult:
    """! @brief direct Zephyr peer parser가 승인한 결과입니다. """

    nonce: str
    target_address: int
    wire_bytes: int
    pwm_duties: tuple[int, int]
    adc_levels: tuple[int, int]
    uart30_state: str


@dataclass(frozen=True)
class AuxiliaryResult:
    """! @brief DUT auxiliary VCOM exact echo 결과입니다. """

    nonce: str
    cycles: tuple[int, int]


@dataclass(frozen=True)
class RelayResult:
    """! @brief host relay log에서 승인한 exact 명령 수입니다. """

    nonce: str
    commands: int


## @brief 두 role image, UID, UART와 물리 fixture 승인 인자를 선언합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "두 NU54DK로 AC-02B Serial1/Wire/SPI/PWM/ADC 물리 HIL을 실행합니다. "
            "DUT Serial1은 UID x.1 보조 VCOM으로 host exact echo하고 peer 제어는 "
            "console relay합니다. --acknowledge-wiring 없이는 flash하지 않습니다."
        )
    )
    parser.add_argument("--dut-hex")
    parser.add_argument("--peer-hex")
    parser.add_argument("--dut-board-id", required=True)
    parser.add_argument("--peer-board-id", required=True)
    parser.add_argument("--dut-volume")
    parser.add_argument("--peer-volume")
    parser.add_argument("--dut-port", default="auto")
    parser.add_argument("--dut-aux-port", default="auto")
    parser.add_argument("--peer-port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument(
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--nonce")
    parser.add_argument("--evidence")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument(
        "--acknowledge-wiring",
        action="store_true",
        help="GND 포함 6가닥 fixture와 peer uart30 비활성 구조를 확인했음을 승인",
    )
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


## @brief pySerial 포트가 요청한 DAPLink USB interface인지 판정합니다.
def is_daplink_interface(port: Any, interface_index: int) -> bool:
    location = str(getattr(port, "location", "") or "").casefold()
    hardware_id = str(getattr(port, "hwid", "") or "").casefold()
    return location.endswith(f":x.{interface_index}") or (
        f"mi_{interface_index:02d}" in hardware_id
    )


## @brief exact UID와 x.1/x.3 interface를 모두 만족하는 COM 하나만 선택합니다.
def find_uid_interface_port(
    board_id: str,
    interface_index: int,
    explicit_port: str,
    list_ports: Any,
) -> str:
    normalized = normalize_board_id(board_id)
    ports = list(list_ports.comports())
    if explicit_port.casefold() != "auto":
        matches = [
            port
            for port in ports
            if str(getattr(port, "device", "")).casefold()
            == explicit_port.casefold()
        ]
        if len(matches) != 1:
            raise Ac02bHilFailure(
                f"지정한 COM을 하나로 찾을 수 없습니다: {explicit_port}"
            )
        candidates = matches
    else:
        candidates = ports

    matches = [
        port
        for port in candidates
        if str(getattr(port, "serial_number", "") or "").casefold()
        == normalized
        and getattr(port, "vid", None) in (None, DAPLINK_VID)
        and getattr(port, "pid", None) in (None, DAPLINK_PID)
        and is_daplink_interface(port, interface_index)
    ]
    if len(matches) == 1:
        return str(matches[0].device)
    diagnostics = "; ".join(port_diagnostic(port) for port in candidates) or "없음"
    raise Ac02bHilFailure(
        "exact DAPLink UID/interface COM을 하나로 결정할 수 없습니다: "
        f"uid={normalized}, interface=x.{interface_index}, 후보={diagnostics}"
    )


## @brief 한 role의 MSD와 console x.3 endpoint를 fail-closed로 탐색합니다.
def discover_console_endpoint(
    board_id: str,
    explicit_volume: str | None,
    explicit_port: str,
    list_ports: Any,
) -> RoleEndpoint:
    normalized = normalize_board_id(board_id)
    return RoleEndpoint(
        normalized,
        find_daplink_volume(normalized, explicit_volume),
        find_uid_interface_port(
            normalized, CONSOLE_INTERFACE, explicit_port, list_ports
        ),
    )


## @brief 세 runtime COM이 서로 다르고 role/interface가 충돌하지 않게 합니다.
def validate_runtime_ports(ports: RuntimePorts) -> None:
    values = {
        ports.dut_console.casefold(),
        ports.dut_auxiliary.casefold(),
        ports.peer_console.casefold(),
    }
    if len(values) != 3:
        raise Ac02bHilFailure(f"runtime COM role 충돌입니다: {ports}")


## @brief flash 뒤 재열거된 x.3/x.1 COM을 exact UID로 bounded 재탐색합니다.
def rediscover_runtime_ports(
    dut_board_id: str,
    peer_board_id: str,
    list_ports: Any,
    timeout_seconds: float = PORT_REDISCOVERY_TIMEOUT_SECONDS,
) -> RuntimePorts:
    if timeout_seconds <= 0.0:
        raise Ac02bHilFailure("COM 재탐색 제한 시간은 0보다 커야 합니다.")
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            ports = RuntimePorts(
                find_uid_interface_port(
                    dut_board_id, CONSOLE_INTERFACE, "auto", list_ports
                ),
                find_uid_interface_port(
                    dut_board_id, AUXILIARY_INTERFACE, "auto", list_ports
                ),
                find_uid_interface_port(
                    peer_board_id, CONSOLE_INTERFACE, "auto", list_ports
                ),
            )
            validate_runtime_ports(ports)
            return ports
        except (Ac02bHilFailure, RuntimeError) as error:
            last_error = error
            time.sleep(0.1)
    raise Ac02bHilFailure(
        "flash 후 exact UID COM 재탐색에 실패했습니다: "
        f"{last_error or '원인 없음'}"
    )


## @brief AC-02B 관련 exact source와 board checkout의 dirty 상태를 거부합니다.
def validate_source_clean() -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/ac02b_hil_dut",
        "tests/zephyr/ac02b_hil_peer",
        "tests/hil/nu54dk/ac02b_peripheral.py",
        "tests/hil/nu54dk/ble_pair_hil_common.py",
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
        raise Ac02bHilFailure(
            "AC-02B HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise Ac02bHilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief DUT protocol을 exact 순서와 ADC 물리 범위로 검증합니다.
def parse_dut_transcript(transcript: bytes, nonce: str) -> DutResult:
    nonce = build_nonce(nonce)
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, MILESTONE, nonce)
    if lines and lines[0] == b"NUCODE_AC02B_READY:role=dut":
        lines = lines[1:]
    expected_prefix = (
        b"NUCODE_AC02B_DUT:ARMED:PASS:control=console:serial1=aux-vcom-x.1"
        + suffix,
        b"NUCODE_AC02B_DUT:SERIAL1:PASS:baud=115200:cycles=2:echo=host-vcom-x.1"
        + suffix,
        b"NUCODE_AC02B_DUT:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32:restart=2"
        + suffix,
        b"NUCODE_AC02B_DUT:SPI:PASS:frequency=4000000:bytes=40:interrupt-mask=1"
        + suffix,
    )
    cursor = 0
    for expected in expected_prefix:
        cursor = take_exact(lines, cursor, expected)
    for command, _ in RELAY_STEPS[:4]:
        cursor = take_exact(
            lines,
            cursor,
            f"NUCODE_AC02B_RELAY:REQUEST:{command}:nonce={nonce}".encode(
                "ascii"
            ),
        )
    cursor = take_exact(
        lines,
        cursor,
        b"NUCODE_AC02B_DUT:PWM:PASS:frequency=1000:duty=25,75" + suffix,
    )
    for command, _ in RELAY_STEPS[4:7]:
        cursor = take_exact(
            lines,
            cursor,
            f"NUCODE_AC02B_RELAY:REQUEST:{command}:nonce={nonce}".encode(
                "ascii"
            ),
        )
    if cursor >= len(lines):
        raise Ac02bHilFailure("DUT ADC token이 없습니다.")
    adc_pattern = re.compile(
        rb"^NUCODE_AC02B_DUT:ADC:PASS:bits=12:low=([0-9]+):high=([0-9]+):nonce="
        + re.escape(nonce.encode("ascii"))
        + rb"$"
    )
    adc_match = adc_pattern.fullmatch(lines[cursor])
    if adc_match is None:
        raise Ac02bHilFailure(f"DUT ADC token 형식이 다릅니다: {lines[cursor]!r}")
    low = int(adc_match.group(1), 10)
    high = int(adc_match.group(2), 10)
    if not (0 <= low <= 384 and 2500 <= high <= 4095 and (high - low) >= 2200):
        raise Ac02bHilFailure(f"DUT ADC LOW/HIGH 범위가 다릅니다: low={low}, high={high}")
    cursor += 1
    cursor = take_exact(
        lines,
        cursor,
        f"NUCODE_AC02B_RELAY:REQUEST:DONE:nonce={nonce}".encode("ascii"),
    )
    cursor = take_exact(
        lines, cursor, b"NUCODE_AC02B_DUT:FINAL:PASS" + suffix
    )
    if cursor != len(lines):
        raise Ac02bHilFailure(
            f"DUT FINAL 뒤 예상 밖 token이 있습니다: {lines[cursor:]!r}"
        )
    return DutResult(nonce, 2, (100000, 400000), 40, (25, 75), low, high)


## @brief peer protocol을 exact 순서로 검증합니다.
def parse_peer_transcript(transcript: bytes, nonce: str) -> PeerResult:
    nonce = build_nonce(nonce)
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, MILESTONE, nonce)
    if lines and lines[0] == b"NUCODE_AC02B_READY:role=peer":
        lines = lines[1:]
    expected = (
        b"NUCODE_AC02B_PEER:ARMED:PASS:address=0x52:control=host-console"
        + suffix,
        b"NUCODE_AC02B_PEER:UART30:PASS:status=disabled:pins=high-z" + suffix,
        b"NUCODE_AC02B_PEER:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32"
        + suffix,
    )
    cursor = 0
    for line in expected:
        cursor = take_exact(lines, cursor, line)
    for index, (_, response) in enumerate(RELAY_STEPS):
        cursor = take_exact(
            lines,
            cursor,
            f"NUCODE_AC02B_RELAY:RESPONSE:{response}:nonce={nonce}".encode(
                "ascii"
            ),
        )
        if index == 3:
            cursor = take_exact(
                lines,
                cursor,
                b"NUCODE_AC02B_PEER:PWM:PASS:frequency=1000:duty=25,75"
                + suffix,
            )
        if index == 5:
            cursor = take_exact(
                lines,
                cursor,
                b"NUCODE_AC02B_PEER:ADC:PASS:levels=0,1" + suffix,
            )
    cursor = take_exact(
        lines, cursor, b"NUCODE_AC02B_PEER:FINAL:PASS" + suffix
    )
    if cursor != len(lines):
        raise Ac02bHilFailure(
            f"peer FINAL 뒤 예상 밖 token이 있습니다: {lines[cursor:]!r}"
        )
    return PeerResult(nonce, 0x52, 32, (25, 75), (0, 1), "disabled-high-z")


## @brief DUT x.1 보조 VCOM의 두 protocol frame이 nonce·cycle exact인지 검증합니다.
def parse_auxiliary_transcript(transcript: bytes, nonce: str) -> AuxiliaryResult:
    nonce = build_nonce(nonce)
    lines: list[bytes] = []
    for raw_line in transcript.split(b"\n"):
        line = raw_line.rstrip(b"\r")
        marker = line.find(b"S1:")
        if marker >= 0:
            lines.append(line[marker:])
    expected = [f"S1:{nonce}:{cycle}".encode("ascii") for cycle in range(2)]
    if lines != expected:
        raise Ac02bHilFailure(
            f"DUT auxiliary x.1 frame 순서/nonce 불일치: 기대={expected!r}, 실제={lines!r}"
        )
    return AuxiliaryResult(nonce, (0, 1))


## @brief host relay의 RX/TX 네 단계가 모든 명령에서 exact인지 검증합니다.
def parse_relay_transcript(transcript: bytes, nonce: str) -> RelayResult:
    nonce = build_nonce(nonce)
    expected: list[bytes] = []
    for cycle in range(2):
        expected.extend(
            (
                f"AUX:RX:S1:{nonce}:{cycle}".encode("ascii"),
                f"AUX:TX:E1:{nonce}:{cycle}".encode("ascii"),
            )
        )
    for command, response in RELAY_STEPS:
        request = f"NUCODE_AC02B_RELAY:REQUEST:{command}:nonce={nonce}"
        reply = f"NUCODE_AC02B_RELAY:RESPONSE:{response}:nonce={nonce}"
        expected.extend(
            (
                f"DUT:RX:{request}".encode("ascii"),
                f"PEER:TX:{request}".encode("ascii"),
                f"PEER:RX:{reply}".encode("ascii"),
                f"DUT:TX:{reply}".encode("ascii"),
            )
        )
    lines = [line.rstrip(b"\r") for line in transcript.split(b"\n") if line]
    if lines != expected:
        raise Ac02bHilFailure(
            f"host relay 순서/nonce/log 불일치: 기대={expected!r}, 실제={lines!r}"
        )
    return RelayResult(nonce, len(RELAY_STEPS))


## @brief peer의 exact ARMED token까지 기다립니다.
def wait_peer_armed(
    serial_port: Any,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    expected = (
        "NUCODE_AC02B_PEER:ARMED:PASS:address=0x52:control=host-console:"
        f"nonce={nonce}"
    ).encode("ascii")
    prefix = b"NUCODE_AC02B_"
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(b"NUCODE_AC02B_FAIL:"):
            raise Ac02bHilFailure(f"peer target 실패: {line!r}")
        if line == b"NUCODE_AC02B_READY:role=peer":
            continue
        if line.startswith(prefix) and line != expected:
            raise Ac02bHilFailure(f"peer ARMED 앞 stale token입니다: {line!r}")
        if line == expected:
            return


## @brief serial write가 요청 byte 전체를 기록했는지 확인합니다.
def write_exact(serial_port: Any, payload: bytes, stage: str) -> None:
    written = serial_port.write(payload)
    serial_port.flush()
    if written != len(payload):
        raise Ac02bHilFailure(f"{stage} UART write가 일부만 기록됐습니다.")


## @brief DUT auxiliary x.1의 두 protocol frame만 순서대로 exact echo합니다.
def echo_auxiliary_frames(
    serial_port: Any,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    relay_capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    for cycle in range(2):
        expected = f"S1:{nonce}:{cycle}".encode("ascii")
        while True:
            observed = read_line(
                serial_port,
                pending,
                capture,
                deadline,
                stop_event=stop_event,
            )
            ## @details UARTE 활성화 순간의 CMSIS-DAP VCOM 전이 잡음은 raw
            ## transcript에 보존하고 S1 protocol frame만 동기화에 사용합니다.
            marker = observed.find(b"S1:")
            if marker >= 0:
                observed = observed[marker:]
                break
        if observed != expected:
            raise Ac02bHilFailure(
                f"DUT auxiliary x.1 frame 순서/nonce 불일치: {observed!r}"
            )
        response = f"E1:{nonce}:{cycle}".encode("ascii")
        relay_capture.extend(b"AUX:RX:" + observed + b"\n")
        write_exact(serial_port, response + b"\r\n", "auxiliary exact echo")
        relay_capture.extend(b"AUX:TX:" + response + b"\n")


## @brief peer console에서 현재 relay의 exact 응답까지 수집합니다.
def wait_peer_relay_response(
    serial_port: Any,
    expected: bytes,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    while True:
        line = read_line(
            serial_port,
            pending,
            capture,
            deadline,
            stop_event=stop_event,
        )
        if line.startswith(b"NUCODE_AC02B_FAIL:"):
            raise Ac02bHilFailure(f"peer target 실패: {line!r}")
        if line.startswith(b"NUCODE_AC02B_RELAY:RESPONSE:"):
            if line != expected:
                raise Ac02bHilFailure(
                    f"peer relay 순서/nonce/응답 불일치: {line!r}"
                )
            return


## @brief DUT console을 수집하며 relay 요청을 peer console로 exact 전달합니다.
def collect_dut_with_relay(
    dut_port: Any,
    peer_port: Any,
    nonce: str,
    dut_pending: bytearray,
    peer_pending: bytearray,
    dut_capture: bytearray,
    peer_capture: bytearray,
    relay_capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    relay_index = 0
    final = f"NUCODE_AC02B_DUT:FINAL:PASS:nonce={nonce}".encode("ascii")
    while True:
        line = read_line(
            dut_port,
            dut_pending,
            dut_capture,
            deadline,
            stop_event=stop_event,
        )
        if line.startswith(b"NUCODE_AC02B_FAIL:"):
            raise Ac02bHilFailure(f"DUT target 실패: {line!r}")
        if line.startswith(b"NUCODE_AC02B_RELAY:REQUEST:"):
            if relay_index >= len(RELAY_STEPS):
                raise Ac02bHilFailure(f"예상 밖 DUT relay 요청입니다: {line!r}")
            command, response = RELAY_STEPS[relay_index]
            expected_request = (
                f"NUCODE_AC02B_RELAY:REQUEST:{command}:nonce={nonce}"
            ).encode("ascii")
            expected_response = (
                f"NUCODE_AC02B_RELAY:RESPONSE:{response}:nonce={nonce}"
            ).encode("ascii")
            if line != expected_request:
                raise Ac02bHilFailure(
                    f"DUT relay 순서/nonce 불일치: 기대={expected_request!r}, 실제={line!r}"
                )
            relay_capture.extend(b"DUT:RX:" + line + b"\n")
            write_exact(peer_port, line + b"\r\n", "peer console relay")
            relay_capture.extend(b"PEER:TX:" + line + b"\n")
            wait_peer_relay_response(
                peer_port,
                expected_response,
                peer_pending,
                peer_capture,
                deadline,
                stop_event,
            )
            relay_capture.extend(b"PEER:RX:" + expected_response + b"\n")
            write_exact(dut_port, expected_response + b"\r\n", "DUT relay 응답")
            relay_capture.extend(b"DUT:TX:" + expected_response + b"\n")
            relay_index += 1
            continue
        if line == final:
            if relay_index != len(RELAY_STEPS):
                raise Ac02bHilFailure(
                    f"DUT FINAL 전에 relay가 누락됐습니다: {relay_index}/{len(RELAY_STEPS)}"
                )
            return


## @brief peer FINAL을 nonce exact로 수집합니다.
def wait_peer_final(
    serial_port: Any,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    expected = f"NUCODE_AC02B_PEER:FINAL:PASS:nonce={nonce}".encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(b"NUCODE_AC02B_FAIL:"):
            raise Ac02bHilFailure(f"peer target 실패: {line!r}")
        if line.startswith(b"NUCODE_AC02B_PEER:FINAL:"):
            if line != expected:
                raise Ac02bHilFailure(f"peer FINAL nonce 불일치: {line!r}")
            return


## @brief flash 뒤 재탐색한 DUT console/aux와 peer console로 HIL을 실행합니다.
def execute_ac02b(
    *,
    serial_module: Any,
    list_ports: Any,
    dut_endpoint: RoleEndpoint,
    peer_endpoint: RoleEndpoint,
    dut_image: Path,
    peer_image: Path,
    nonce: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
) -> Ac02bExecution:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise Ac02bHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 600.0:
        raise Ac02bHilFailure("--result-timeout은 30..600초여야 합니다.")

    captures = {"dut": bytearray(), "peer": bytearray(), "aux": bytearray()}
    pending = {"dut": bytearray(), "peer": bytearray(), "aux": bytearray()}
    auxiliary_relay_capture = bytearray()
    console_relay_capture = bytearray()
    flashes = {"dut": ("not-started", "unknown"), "peer": ("not-started", "unknown")}
    runtime_ports: RuntimePorts | None = None
    try:
        flashes["peer"] = flash_image(
            MILESTONE, "peer", peer_endpoint.volume, peer_image, flash_timeout
        )
        flashes["dut"] = flash_image(
            MILESTONE, "dut", dut_endpoint.volume, dut_image, flash_timeout
        )
        runtime_ports = rediscover_runtime_ports(
            dut_endpoint.board_id, peer_endpoint.board_id, list_ports
        )

        with ExitStack() as stack:
            ports: dict[str, Any] = {}
            for role, port_name in (
                ("dut", runtime_ports.dut_console),
                ("peer", runtime_ports.peer_console),
                ("aux", runtime_ports.dut_auxiliary),
            ):
                ports[role] = stack.enter_context(
                    serial_module.Serial(
                        port=port_name,
                        baudrate=baud_rate,
                        bytesize=serial_module.EIGHTBITS,
                        parity=serial_module.PARITY_NONE,
                        stopbits=serial_module.STOPBITS_ONE,
                        timeout=0.1,
                        write_timeout=2.0,
                    )
                )
                ports[role].reset_input_buffer()
            deadline = time.monotonic() + result_timeout
            write_start_command(ports["peer"], MILESTONE, nonce)
            wait_peer_armed(
                ports["peer"], nonce, pending["peer"], captures["peer"], deadline
            )
            write_start_command(ports["dut"], MILESTONE, nonce)

            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        echo_auxiliary_frames,
                        ports["aux"],
                        nonce,
                        pending["aux"],
                        captures["aux"],
                        auxiliary_relay_capture,
                        deadline,
                        stop_event,
                    ),
                    executor.submit(
                        collect_dut_with_relay,
                        ports["dut"],
                        ports["peer"],
                        nonce,
                        pending["dut"],
                        pending["peer"],
                        captures["dut"],
                        captures["peer"],
                        console_relay_capture,
                        deadline,
                        stop_event,
                    ),
                ]
                try:
                    completed, _ = wait(futures, return_when=FIRST_EXCEPTION)
                    for future in completed:
                        future.result()
                except Exception:
                    stop_event.set()
                    raise
            wait_peer_final(
                ports["peer"], nonce, pending["peer"], captures["peer"], deadline
            )
            time.sleep(0.05)
            waiting = int(getattr(ports["aux"], "in_waiting", 0) or 0)
            if waiting > 0:
                captures["aux"].extend(ports["aux"].read(waiting))
    except Exception as error:
        raise Ac02bExecutionFailure(
            str(error),
            bytes(captures["dut"]),
            bytes(captures["peer"]),
            bytes(captures["aux"]),
            bytes(auxiliary_relay_capture + console_relay_capture),
        ) from error

    if runtime_ports is None:
        raise Ac02bHilFailure("runtime COM 재탐색 결과가 없습니다.")
    return Ac02bExecution(
        RoleExecution(*flashes["dut"], bytes(captures["dut"])),
        RoleExecution(*flashes["peer"], bytes(captures["peer"])),
        bytes(captures["aux"]),
        bytes(auxiliary_relay_capture + console_relay_capture),
        runtime_ports,
    )


## @brief evidence와 transcript의 신규 출력 경로를 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path, Path, Path, Path]:
    if not evidence_argument:
        raise Ac02bHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise Ac02bHilFailure("--evidence는 .json 파일이어야 합니다.")
    dut_log = evidence.with_name(f"{evidence.stem}.dut.transcript.log")
    peer_log = evidence.with_name(f"{evidence.stem}.peer.transcript.log")
    auxiliary_log = evidence.with_name(
        f"{evidence.stem}.dut.auxiliary.transcript.log"
    )
    relay_log = evidence.with_name(f"{evidence.stem}.host.relay.transcript.log")
    paths = (evidence, dut_log, peer_log, auxiliary_log, relay_log)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise Ac02bHilFailure(
            "기존 증적을 덮어쓰지 않습니다: "
            + ", ".join(str(path) for path in existing)
        )
    for path in existing:
        if not path.is_file():
            raise Ac02bHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing:
            path.unlink()
    return paths


## @brief 실패 transcript를 PASS evidence 없이 보존합니다.
def save_failure_transcripts(
    dut_path: Path,
    peer_path: Path,
    auxiliary_path: Path,
    relay_path: Path,
    error: Exception,
) -> None:
    if not isinstance(error, Ac02bExecutionFailure):
        return
    dut_path.write_bytes(error.dut_transcript)
    peer_path.write_bytes(error.peer_transcript)
    auxiliary_path.write_bytes(error.auxiliary_transcript)
    relay_path.write_bytes(error.relay_transcript)


## @brief 물리 fixture를 사용자에게 exact 표로 출력합니다.
def print_required_wiring() -> None:
    print("AC-02B WIRING_REQUIRED: 다음 연결을 모두 확인한 뒤 다시 실행하십시오.")
    print("  1. Board A(DUT) GND   <-> Board B(peer) GND")
    print("  2. Board A P1.2 SDA   <-> Board B P1.2 SDA")
    print("  3. Board A P1.3 SCL   <-> Board B P1.3 SCL")
    print("  4. Board A P1.10 PWM  ->  Board B P1.14 capture")
    print("  5. Board B P2.5 GPIO  ->  Board A P1.12/A0")
    print("  6. Board A P2.2 MOSI  <-> Board A P2.4 MISO (같은 보드 loopback)")
    print("Board A Serial1은 같은 UID의 x.1 보조 VCOM을 host가 exact echo합니다.")
    print("기존 P0.0/P0.1 교차선은 남아 있어도 되며 peer uart30은 disabled/high-Z입니다.")
    print("외부 I2C pull-up은 요구하지 않으며 0x6A PMIC에는 접근하지 않습니다.")


## @brief 두 role identity와 image/build record를 flash 전에 검증합니다.
def preflight(
    args: argparse.Namespace,
    serial_module: Any,
    list_ports: Any,
) -> tuple[
    RoleEndpoint,
    RoleEndpoint,
    str,
    Path,
    Path,
    str,
    str,
    dict[str, str],
    dict[str, str],
]:
    dut_endpoint = discover_console_endpoint(
        args.dut_board_id, args.dut_volume, args.dut_port, list_ports
    )
    peer_endpoint = discover_console_endpoint(
        args.peer_board_id, args.peer_volume, args.peer_port, list_ports
    )
    dut_auxiliary_port = find_uid_interface_port(
        dut_endpoint.board_id,
        AUXILIARY_INTERFACE,
        args.dut_aux_port,
        list_ports,
    )
    validate_pair_identity(dut_endpoint, peer_endpoint)
    validate_runtime_ports(
        RuntimePorts(
            dut_endpoint.port_name,
            dut_auxiliary_port,
            peer_endpoint.port_name,
        )
    )
    print(
        "NU54DK AC-02B pair discovery SUCCESS: "
        f"dut={dut_endpoint.board_id}/{dut_endpoint.port_name}/aux={dut_auxiliary_port}, "
        f"peer={peer_endpoint.board_id}/{peer_endpoint.port_name}"
    )
    if args.discover_only:
        return (
            dut_endpoint,
            peer_endpoint,
            dut_auxiliary_port,
            Path(),
            Path(),
            "",
            "",
            {},
            {},
        )

    dut_image = validate_hex_image(args.dut_hex)
    peer_image = validate_hex_image(args.peer_hex)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean()
    dut_record = validate_build_record(
        dut_image, core_revision, board_revision, DUT_APPLICATION
    )
    peer_record = validate_build_record(
        peer_image, core_revision, board_revision, PEER_APPLICATION
    )
    if file_sha256(dut_image) == file_sha256(peer_image):
        raise Ac02bHilFailure("DUT와 peer HEX가 동일하여 role 오배치를 거부했습니다.")
    return (
        dut_endpoint,
        peer_endpoint,
        dut_auxiliary_port,
        dut_image,
        peer_image,
        core_revision,
        board_revision,
        dut_record,
        peer_record,
    )


## @brief 장치 탐색, WIRING_REQUIRED 또는 전체 AC-02B pair gate를 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    serial_module, list_ports = import_pyserial()
    (
        dut_endpoint,
        peer_endpoint,
        dut_auxiliary_port,
        dut_image,
        peer_image,
        core_revision,
        board_revision,
        dut_record,
        peer_record,
    ) = preflight(args, serial_module, list_ports)
    if args.discover_only:
        return 0
    if not args.acknowledge_wiring:
        print_required_wiring()
        return WIRING_REQUIRED_EXIT_CODE

    (
        evidence_path,
        dut_log,
        peer_log,
        auxiliary_log,
        relay_log,
    ) = prepare_output_paths(args.evidence, args.overwrite_evidence)
    nonce = build_nonce(args.nonce)
    dut_size = dut_image.stat().st_size
    peer_size = peer_image.stat().st_size
    dut_sha256 = file_sha256(dut_image)
    peer_sha256 = file_sha256(peer_image)
    try:
        execution = execute_ac02b(
            serial_module=serial_module,
            list_ports=list_ports,
            dut_endpoint=dut_endpoint,
            peer_endpoint=peer_endpoint,
            dut_image=dut_image,
            peer_image=peer_image,
            nonce=nonce,
            baud_rate=args.baud,
            flash_timeout=args.flash_timeout,
            result_timeout=args.result_timeout,
        )
        dut_log.write_bytes(execution.dut.transcript)
        peer_log.write_bytes(execution.peer.transcript)
        auxiliary_log.write_bytes(execution.dut_auxiliary_transcript)
        relay_log.write_bytes(execution.relay_transcript)
        validate_image_unchanged(dut_image, dut_size, dut_sha256)
        validate_image_unchanged(peer_image, peer_size, peer_sha256)
        dut_result = parse_dut_transcript(execution.dut.transcript, nonce)
        peer_result = parse_peer_transcript(execution.peer.transcript, nonce)
        auxiliary_result = parse_auxiliary_transcript(
            execution.dut_auxiliary_transcript, nonce
        )
        relay_result = parse_relay_transcript(execution.relay_transcript, nonce)
        evidence = {
            "schema_version": EVIDENCE_SCHEMA,
            "gate": "ac02b-peripheral-pair-hil",
            "status": "passed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "core_revision": core_revision,
            "board_revision": board_revision,
            "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
            "nonce": nonce,
            "boards": {
                "dut": {
                    "daplink_uid": dut_endpoint.board_id,
                    "msd_root": str(dut_endpoint.volume.root),
                    "preflight_console_port": dut_endpoint.port_name,
                    "preflight_auxiliary_port": dut_auxiliary_port,
                    "runtime_console_port": execution.runtime_ports.dut_console,
                    "runtime_auxiliary_port": execution.runtime_ports.dut_auxiliary,
                },
                "peer": {
                    "daplink_uid": peer_endpoint.board_id,
                    "msd_root": str(peer_endpoint.volume.root),
                    "preflight_console_port": peer_endpoint.port_name,
                    "runtime_console_port": execution.runtime_ports.peer_console,
                },
            },
            "images": {
                "dut": image_record(
                    dut_image, dut_size, dut_sha256, execution.dut, dut_record
                ),
                "peer": image_record(
                    peer_image, peer_size, peer_sha256, execution.peer, peer_record
                ),
            },
            "transcripts": {
                "dut": transcript_record(dut_log, execution.dut.transcript),
                "peer": transcript_record(peer_log, execution.peer.transcript),
                "dut_auxiliary": transcript_record(
                    auxiliary_log, execution.dut_auxiliary_transcript
                ),
                "host_relay": transcript_record(
                    relay_log, execution.relay_transcript
                ),
            },
            "results": {
                "dut": asdict(dut_result),
                "peer": asdict(peer_result),
                "auxiliary": asdict(auxiliary_result),
                "relay": asdict(relay_result),
            },
            "coverage": {
                "serial1_auxiliary_vcom": [
                    "exact-uid-x.1",
                    "post-flash-rediscovery",
                    "setPins",
                    "active-remap-reject",
                    "end-rebegin",
                    "host-exact-echo",
                ],
                "wire_twim22_twis21": ["100k", "400k", "repeated-start", "end-rebegin"],
                "spi00": ["exact-pins", "4MHz-loopback", "interrupt-mask"],
                "pwm20": ["1kHz", "25-percent", "75-percent", "external-edge-capture"],
                "adc_ain5": ["external-low", "external-high", "12-bit"],
            },
            "fixture": {
                "wiring_acknowledged": True,
                "required_wire_count_including_ground": 6,
                "peer_uart30": "disabled-high-z",
                "legacy_p0_cross_wires_required": False,
                "peer_auxiliary_vcom_opened": False,
                "control_transport": "host-console-relay",
                "external_pullup_required": False,
                "pmic_address_accessed": False,
                "mass_erase_requested": False,
            },
        }
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as error:
        save_failure_transcripts(
            dut_log, peer_log, auxiliary_log, relay_log, error
        )
        raise
    print(f"NU54DK AC-02B peripheral pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, OSError, TimeoutError) as error:
        print(f"NU54DK AC-02B peripheral pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
