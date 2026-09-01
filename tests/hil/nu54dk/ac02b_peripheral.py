#!/usr/bin/env python3
"""! @brief 두 NU54DK의 AC-02B 주변장치 물리 HIL을 fail-closed로 실행합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
    PairExecutionFailure,
    RoleEndpoint,
    RoleExecution,
    build_nonce,
    collect_until_final,
    discover_endpoint,
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
    wait_ready,
    write_start_command,
)
from m6_serial_echo import import_pyserial  # noqa: E402


MILESTONE = "AC02B"
DUT_APPLICATION = REPOSITORY / "tests" / "zephyr" / "ac02b_hil_dut"
PEER_APPLICATION = REPOSITORY / "tests" / "zephyr" / "ac02b_hil_peer"
EVIDENCE_SCHEMA = 1
WIRING_REQUIRED_EXIT_CODE = 3


class Ac02bHilFailure(BlePairHilFailure):
    """! @brief AC-02B 전용 fail-closed 오류입니다. """


class Ac02bExecutionFailure(PairExecutionFailure):
    """! @brief 실패 시점 DUT·peer transcript를 보존합니다. """


@dataclass(frozen=True)
class Ac02bExecution:
    """! @brief 두 role의 flash 결과와 raw transcript입니다. """

    dut: RoleExecution
    peer: RoleExecution


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
    serial_cycles: int
    wire_bytes: int
    pwm_duties: tuple[int, int]
    adc_levels: tuple[int, int]


## @brief 두 role image, UID, UART와 물리 fixture 승인 인자를 선언합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "두 NU54DK로 AC-02B Serial1/Wire/SPI/PWM/ADC 물리 HIL을 실행합니다. "
            "--acknowledge-wiring 없이는 flash하지 않고 WIRING_REQUIRED로 멈춥니다."
        )
    )
    parser.add_argument("--dut-hex")
    parser.add_argument("--peer-hex")
    parser.add_argument("--dut-board-id", required=True)
    parser.add_argument("--peer-board-id", required=True)
    parser.add_argument("--dut-volume")
    parser.add_argument("--peer-volume")
    parser.add_argument("--dut-port", default="auto")
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
        help="README의 GND 포함 8가닥 fixture를 실제 확인했음을 승인",
    )
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


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
    expected_prefix = (
        b"NUCODE_AC02B_READY:role=dut",
        b"NUCODE_AC02B_DUT:SERIAL1:PASS:baud=115200:cycles=2:bytes=64" + suffix,
        b"NUCODE_AC02B_DUT:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32:restart=2"
        + suffix,
        b"NUCODE_AC02B_DUT:SPI:PASS:frequency=4000000:bytes=40:interrupt-mask=1"
        + suffix,
        b"NUCODE_AC02B_DUT:PWM:PASS:frequency=1000:duty=25,75" + suffix,
    )
    cursor = 0
    for expected in expected_prefix:
        cursor = take_exact(lines, cursor, expected)
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
    expected = (
        b"NUCODE_AC02B_READY:role=peer",
        b"NUCODE_AC02B_PEER:ARMED:PASS:address=0x52" + suffix,
        b"NUCODE_AC02B_PEER:SERIAL1:PASS:baud=115200:cycles=2:bytes=64" + suffix,
        b"NUCODE_AC02B_PEER:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32"
        + suffix,
        b"NUCODE_AC02B_PEER:PWM:PASS:frequency=1000:duty=25,75" + suffix,
        b"NUCODE_AC02B_PEER:ADC:PASS:levels=0,1" + suffix,
        b"NUCODE_AC02B_PEER:FINAL:PASS" + suffix,
    )
    cursor = 0
    for line in expected:
        cursor = take_exact(lines, cursor, line)
    if cursor != len(lines):
        raise Ac02bHilFailure(
            f"peer FINAL 뒤 예상 밖 token이 있습니다: {lines[cursor:]!r}"
        )
    return PeerResult(nonce, 0x52, 2, 32, (25, 75), (0, 1))


## @brief peer의 exact ARMED token까지 기다립니다.
def wait_peer_armed(
    serial_port: Any,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    expected = (
        f"NUCODE_AC02B_PEER:ARMED:PASS:address=0x52:nonce={nonce}"
    ).encode("ascii")
    prefix = b"NUCODE_AC02B_"
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(b"NUCODE_AC02B_FAIL:"):
            raise Ac02bHilFailure(f"peer target 실패: {line!r}")
        if line.startswith(prefix) and line != expected:
            raise Ac02bHilFailure(f"peer ARMED 앞 stale token입니다: {line!r}")
        if line == expected:
            return


## @brief 두 UART를 flash 전에 열고 peer arm 뒤 DUT를 시작합니다.
def execute_ac02b(
    *,
    serial_module: Any,
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

    captures = {"dut": bytearray(), "peer": bytearray()}
    pending = {"dut": bytearray(), "peer": bytearray()}
    flashes = {"dut": ("not-started", "unknown"), "peer": ("not-started", "unknown")}
    try:
        with ExitStack() as stack:
            ports: dict[str, Any] = {}
            for role, endpoint in (("dut", dut_endpoint), ("peer", peer_endpoint)):
                ports[role] = stack.enter_context(
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
                ports[role].reset_input_buffer()

            flashes["peer"] = flash_image(
                MILESTONE, "peer", peer_endpoint.volume, peer_image, flash_timeout
            )
            flashes["dut"] = flash_image(
                MILESTONE, "dut", dut_endpoint.volume, dut_image, flash_timeout
            )
            deadline = time.monotonic() + result_timeout
            for role in ("peer", "dut"):
                wait_ready(
                    ports[role], MILESTONE, role, pending[role], captures[role], deadline
                )

            write_start_command(ports["peer"], MILESTONE, nonce)
            wait_peer_armed(
                ports["peer"], nonce, pending["peer"], captures["peer"], deadline
            )
            write_start_command(ports["dut"], MILESTONE, nonce)

            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        collect_until_final,
                        ports[role],
                        MILESTONE,
                        role,
                        nonce,
                        pending[role],
                        captures[role],
                        deadline,
                        stop_event,
                    )
                    for role in ("dut", "peer")
                ]
                try:
                    for future in futures:
                        future.result()
                except Exception:
                    stop_event.set()
                    raise
    except Exception as error:
        raise Ac02bExecutionFailure(
            str(error), bytes(captures["dut"]), bytes(captures["peer"])
        ) from error

    return Ac02bExecution(
        RoleExecution(*flashes["dut"], bytes(captures["dut"])),
        RoleExecution(*flashes["peer"], bytes(captures["peer"])),
    )


## @brief evidence와 transcript의 신규 출력 경로를 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path, Path]:
    if not evidence_argument:
        raise Ac02bHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise Ac02bHilFailure("--evidence는 .json 파일이어야 합니다.")
    dut_log = evidence.with_name(f"{evidence.stem}.dut.transcript.log")
    peer_log = evidence.with_name(f"{evidence.stem}.peer.transcript.log")
    paths = (evidence, dut_log, peer_log)
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
def save_failure_transcripts(dut_path: Path, peer_path: Path, error: Exception) -> None:
    if not isinstance(error, Ac02bExecutionFailure):
        return
    dut_path.write_bytes(error.peripheral_transcript)
    peer_path.write_bytes(error.central_transcript)


## @brief 물리 fixture를 사용자에게 exact 표로 출력합니다.
def print_required_wiring() -> None:
    print("AC-02B WIRING_REQUIRED: 다음 연결을 모두 확인한 뒤 다시 실행하십시오.")
    print("  1. Board A(DUT) GND   <-> Board B(peer) GND")
    print("  2. Board A P0.0 TX    ->  Board B P0.1 RX")
    print("  3. Board A P0.1 RX    <-  Board B P0.0 TX")
    print("  4. Board A P1.2 SDA   <-> Board B P1.2 SDA")
    print("  5. Board A P1.3 SCL   <-> Board B P1.3 SCL")
    print("  6. Board A P1.10 PWM  ->  Board B P1.14 capture")
    print("  7. Board B P2.5 GPIO  ->  Board A P1.12/A0")
    print("  8. Board A P2.2 MOSI  <-> Board A P2.4 MISO (같은 보드 loopback)")
    print("외부 I2C pull-up은 요구하지 않으며 0x6A PMIC에는 접근하지 않습니다.")


## @brief 두 role identity와 image/build record를 flash 전에 검증합니다.
def preflight(
    args: argparse.Namespace,
    serial_module: Any,
    list_ports: Any,
) -> tuple[
    RoleEndpoint,
    RoleEndpoint,
    Path,
    Path,
    str,
    str,
    dict[str, str],
    dict[str, str],
]:
    dut_endpoint = discover_endpoint(
        args.dut_board_id, args.dut_volume, args.dut_port, list_ports
    )
    peer_endpoint = discover_endpoint(
        args.peer_board_id, args.peer_volume, args.peer_port, list_ports
    )
    validate_pair_identity(dut_endpoint, peer_endpoint)
    print(
        "NU54DK AC-02B pair discovery SUCCESS: "
        f"dut={dut_endpoint.board_id}/{dut_endpoint.port_name}, "
        f"peer={peer_endpoint.board_id}/{peer_endpoint.port_name}"
    )
    if args.discover_only:
        return (
            dut_endpoint,
            peer_endpoint,
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

    evidence_path, dut_log, peer_log = prepare_output_paths(
        args.evidence, args.overwrite_evidence
    )
    nonce = build_nonce(args.nonce)
    dut_size = dut_image.stat().st_size
    peer_size = peer_image.stat().st_size
    dut_sha256 = file_sha256(dut_image)
    peer_sha256 = file_sha256(peer_image)
    try:
        execution = execute_ac02b(
            serial_module=serial_module,
            dut_endpoint=dut_endpoint,
            peer_endpoint=peer_endpoint,
            dut_image=dut_image,
            peer_image=peer_image,
            nonce=nonce,
            baud_rate=args.baud,
            flash_timeout=args.flash_timeout,
            result_timeout=args.result_timeout,
        )
        validate_image_unchanged(dut_image, dut_size, dut_sha256)
        validate_image_unchanged(peer_image, peer_size, peer_sha256)
        dut_result = parse_dut_transcript(execution.dut.transcript, nonce)
        peer_result = parse_peer_transcript(execution.peer.transcript, nonce)
        dut_log.write_bytes(execution.dut.transcript)
        peer_log.write_bytes(execution.peer.transcript)
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
                    "uart_port": dut_endpoint.port_name,
                },
                "peer": {
                    "daplink_uid": peer_endpoint.board_id,
                    "msd_root": str(peer_endpoint.volume.root),
                    "uart_port": peer_endpoint.port_name,
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
            },
            "results": {
                "dut": asdict(dut_result),
                "peer": asdict(peer_result),
            },
            "coverage": {
                "serial1_uart30": ["setPins", "active-remap-reject", "end-rebegin", "rx-tx"],
                "wire_twim22_twis21": ["100k", "400k", "repeated-start", "end-rebegin"],
                "spi00": ["exact-pins", "4MHz-loopback", "interrupt-mask"],
                "pwm20": ["1kHz", "25-percent", "75-percent", "external-edge-capture"],
                "adc_ain5": ["external-low", "external-high", "12-bit"],
            },
            "fixture": {
                "wiring_acknowledged": True,
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
        save_failure_transcripts(dut_log, peer_log, error)
        raise
    print(f"NU54DK AC-02B peripheral pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, OSError, TimeoutError) as error:
        print(f"NU54DK AC-02B peripheral pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
