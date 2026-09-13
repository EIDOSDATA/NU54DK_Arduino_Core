#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M29-W02 512-byte long read를 자동 검증합니다. """

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    BlePairHilFailure,
    PairExecution,
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


PROTOCOL = "M29W02|1"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests/zephyr/m29_ble_long_hil"
DEFAULT_RESULT_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class LongReadResult:
    """! @brief 한 role의 고정 W02 protocol 결과입니다. """

    role: str
    mtu: int
    reads: int
    payload_bytes: int
    corrupt_reads: int
    stale_events: int
    callback_context: str


def _suffix(nonce: str, core_revision: str) -> bytes:
    """! @brief 모든 session record의 exact identity suffix를 만듭니다. """

    return f"|nonce={nonce}|core={core_revision}".encode("ascii")


def parse_role_transcript(
    transcript: bytes, nonce: str, core_revision: str, role: str
) -> LongReadResult:
    """! @brief noise·누락·중복·재배치·wrong identity를 fail-closed로 거부합니다. """

    nonce = build_nonce(nonce)
    if role not in ("peripheral", "central"):
        raise BlePairHilFailure(f"알 수 없는 W02 role입니다: {role}")
    if len(core_revision) != 40 or any(value not in "0123456789abcdef" for value in core_revision):
        raise BlePairHilFailure("Core revision은 소문자 40자리 SHA-1이어야 합니다.")
    try:
        lines = [
            line.strip()
            for line in transcript.replace(b"\r", b"").split(b"\n")
            if line.strip()
        ]
        for line in lines:
            line.decode("ascii")
    except UnicodeDecodeError as error:
        raise BlePairHilFailure("W02 transcript에 비 ASCII noise가 있습니다.") from error

    suffix = _suffix(nonce, core_revision)
    ready = f"{PROTOCOL}|READY|role={role}|core={core_revision}".encode("ascii")
    begin = f"{PROTOCOL}|BEGIN|role={role}".encode("ascii") + suffix
    link = f"{PROTOCOL}|LINK|role={role}|mtu=247".encode("ascii") + suffix
    end = (
        f"{PROTOCOL}|END|role={role}|status=pass".encode("ascii") + suffix
    )
    if role == "peripheral":
        expected = (
            ready,
            begin,
            f"{PROTOCOL}|ADVERTISE|role=peripheral|status=pass".encode("ascii")
            + suffix,
            link,
            f"{PROTOCOL}|RESULT|role=peripheral|peer_disconnect=pass"
            f"|callback_context=pass".encode("ascii")
            + suffix,
            end,
        )
        result = LongReadResult(role, 247, 0, 512, 0, 0, "pass")
    else:
        expected = (
            ready,
            begin,
            f"{PROTOCOL}|SCAN|role=central|status=pass".encode("ascii") + suffix,
            link,
            f"{PROTOCOL}|RESULT|role=central|reads=100|bytes=512|corrupt=0"
            f"|stale=0|callback_context=pass".encode("ascii")
            + suffix,
            end,
        )
        result = LongReadResult(role, 247, 100, 512, 0, 0, "pass")
    if tuple(lines) != expected:
        raise BlePairHilFailure(
            f"{role} W02 protocol 순서/값이 다릅니다: 기대={expected!r}, 실제={tuple(lines)!r}"
        )
    return result


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact image·board·evidence 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="두 NU54DK로 M29-W02 MTU 247·512-byte long read 100회를 검증합니다."
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
        "--flash-backend",
        choices=("pyocd-sector", "daplink-msd"),
        default="pyocd-sector",
    )
    parser.add_argument(
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--evidence")
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def _wait_ready(
    serial_port: Any,
    role: str,
    core_revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    protocol: str = PROTOCOL,
) -> None:
    """! @brief READY 앞 noise와 다른 revision token을 즉시 거부합니다. """

    expected = f"{protocol}|READY|role={role}|core={core_revision}".encode("ascii")
    line = read_line(serial_port, pending, capture, deadline)
    if line != expected:
        raise BlePairHilFailure(
            f"{role} READY 불일치: 기대={expected!r}, 실제={line!r}"
        )


def _write_start(
    serial_port: Any, nonce: str, core_revision: str, protocol: str = PROTOCOL
) -> None:
    """! @brief nonce와 exact Core revision이 결합된 start record를 기록합니다. """

    request = (
        f"{protocol}|START|nonce={nonce}|core={core_revision}\r\n".encode("ascii")
    )
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise BlePairHilFailure("W02 start record가 일부만 기록됐습니다.")


def _wait_advertising(
    serial_port: Any,
    nonce: str,
    core_revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    protocol: str = PROTOCOL,
) -> None:
    """! @brief peripheral BEGIN과 ADVERTISE를 exact 순서로 소비합니다. """

    suffix = _suffix(nonce, core_revision)
    expected = (
        f"{protocol}|BEGIN|role=peripheral".encode("ascii") + suffix,
        f"{protocol}|ADVERTISE|role=peripheral|status=pass".encode("ascii")
        + suffix,
    )
    for wanted in expected:
        line = read_line(serial_port, pending, capture, deadline)
        if line != wanted:
            raise BlePairHilFailure(
                f"peripheral 광고 전 protocol 불일치: 기대={wanted!r}, 실제={line!r}"
            )


def _collect_end(
    serial_port: Any,
    role: str,
    nonce: str,
    core_revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
    protocol: str = PROTOCOL,
) -> None:
    """! @brief END까지 모든 protocol line을 보존하며 FAIL·timeout을 전파합니다. """

    expected_end = (
        f"{protocol}|END|role={role}|status=pass".encode("ascii")
        + _suffix(nonce, core_revision)
    )
    try:
        while True:
            line = read_line(serial_port, pending, capture, deadline, stop_event=stop_event)
            if line:
                print(f"[{role}] {line.decode('utf-8', errors='backslashreplace')}")
            if line.startswith(f"{protocol}|FAIL|".encode("ascii")):
                raise BlePairHilFailure(f"{role} target 실패: {line!r}")
            if line == expected_end:
                return
            if line.startswith(f"{protocol}|END|".encode("ascii")):
                raise BlePairHilFailure(f"{role} END identity/status 불일치: {line!r}")
    except Exception:
        stop_event.set()
        raise


def execute_long_pair(
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
    protocol: str = PROTOCOL,
    flash_label: str = "M29W02",
    ready_query: bytes | None = None,
) -> PairExecution:
    """! @brief 두 image를 flash하고 peripheral 광고 뒤 central을 시작합니다. """

    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 600.0:
        raise BlePairHilFailure("--result-timeout은 30..600초여야 합니다.")
    captures = {"peripheral": bytearray(), "central": bytearray()}
    pending = {"peripheral": bytearray(), "central": bytearray()}
    flashes = {
        "peripheral": ("not-started", "unknown"),
        "central": ("not-started", "unknown"),
    }
    try:
        with ExitStack() as stack:
            ports = {}
            for role, endpoint in (
                ("peripheral", peripheral_endpoint),
                ("central", central_endpoint),
            ):
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
                        flash_label, role, endpoint.volume, image, flash_timeout
                    )
            if ready_query is not None:
                for role in ("peripheral", "central"):
                    ports[role].reset_input_buffer()
                    written = ports[role].write(ready_query)
                    ports[role].flush()
                    if written != len(ready_query):
                        raise BlePairHilFailure(
                            f"{role} READY query가 일부만 기록됐습니다."
                        )
            deadline = time.monotonic() + result_timeout
            for role in ("peripheral", "central"):
                _wait_ready(
                    ports[role],
                    role,
                    core_revision,
                    pending[role],
                    captures[role],
                    deadline,
                    protocol,
                )
            _write_start(ports["peripheral"], nonce, core_revision, protocol)
            _wait_advertising(
                ports["peripheral"],
                nonce,
                core_revision,
                pending["peripheral"],
                captures["peripheral"],
                deadline,
                protocol,
            )
            _write_start(ports["central"], nonce, core_revision, protocol)
            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _collect_end,
                        ports[role],
                        role,
                        nonce,
                        core_revision,
                        pending[role],
                        captures[role],
                        deadline,
                        stop_event,
                        protocol,
                    )
                    for role in ("peripheral", "central")
                ]
                for future in futures:
                    future.result()
    except Exception as error:
        raise PairExecutionFailure(
            str(error), bytes(captures["peripheral"]), bytes(captures["central"])
        ) from error
    return PairExecution(
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
    """! @brief 장치 탐색 또는 전체 W02 pair gate를 실행합니다. """

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
        "NU54DK M29-W02 pair discovery SUCCESS: "
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
    validate_source_clean("M29W02", APPLICATION_SOURCE_ROOT, Path(__file__).resolve())
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
        raise BlePairHilFailure("W02 role HEX가 동일하여 오배치를 거부했습니다.")
    nonce = build_nonce()
    try:
        execution = execute_long_pair(
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
        peripheral_log.write_bytes(execution.peripheral.transcript)
        central_log.write_bytes(execution.central.transcript)
        evidence = {
            "schema_version": 1,
            "gate": "m29-w02-long-read-pair-hil",
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
                "peripheral": transcript_record(peripheral_log, execution.peripheral.transcript),
                "central": transcript_record(central_log, execution.central.transcript),
            },
            "results": {
                "peripheral": asdict(peripheral_result),
                "central": asdict(central_result),
            },
            "coverage": {
                "att_mtu": 247,
                "long_read_bytes": 512,
                "long_read_iterations": 100,
                "payload_corruption": 0,
                "long_write": "deferred-to-M29-W03",
                "m29_long_01_status": "not-yet-complete",
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
    print(f"NU54DK M29-W02 long read pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M29-W02 long read pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
