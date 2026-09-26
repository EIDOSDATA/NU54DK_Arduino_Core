#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M29-W05 robust GATT cache migration을 자동 검증합니다. """

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


PROTOCOL = "M29W05|1"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests/zephyr/m29_ble_cache_hil"
DEFAULT_RESULT_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True)
class CacheResult:
    """! @brief 한 role의 고정 W05 정량 결과입니다. """

    role: str
    stage: int
    bonded: int
    reconnects: int
    hash_reads: int
    cache_saved: int
    cache_restored: int
    invalidated: int
    service_changed: int
    corrupt_rejected: int
    stale_handles: int
    callback_context: str


def _suffix(nonce: str, core_revision: str) -> bytes:
    """! @brief 모든 session record의 exact identity suffix를 만듭니다. """

    return f"|nonce={nonce}|core={core_revision}".encode("ascii")


def _valid_revision(core_revision: str) -> None:
    """! @brief exact Core revision 문법을 fail-closed로 검증합니다. """

    if len(core_revision) != 40 or any(
        value not in "0123456789abcdef" for value in core_revision
    ):
        raise BlePairHilFailure("Core revision은 소문자 40자리 SHA-1이어야 합니다.")


def parse_role_transcript(
    transcript: bytes, nonce: str, core_revision: str, role: str
) -> CacheResult:
    """! @brief noise·누락·중복·재배치·wrong identity를 fail-closed로 거부합니다. """

    nonce = build_nonce(nonce)
    _valid_revision(core_revision)
    if role not in ("peripheral", "central"):
        raise BlePairHilFailure(f"알 수 없는 W05 role입니다: {role}")
    try:
        lines = tuple(
            line.strip()
            for line in transcript.replace(b"\r", b"").split(b"\n")
            if line.strip()
        )
        for line in lines:
            line.decode("ascii")
    except UnicodeDecodeError as error:
        raise BlePairHilFailure("W05 transcript에 비 ASCII noise가 있습니다.") from error

    suffix = _suffix(nonce, core_revision)
    ready = (
        f"{PROTOCOL}|READY|role={role}|stage=1|core={core_revision}".encode("ascii")
    )
    begin = f"{PROTOCOL}|BEGIN|role={role}".encode("ascii") + suffix
    end = f"{PROTOCOL}|END|role={role}|status=pass".encode("ascii") + suffix
    if role == "peripheral":
        expected = (
            ready,
            begin,
            f"{PROTOCOL}|ADVERTISE|role=peripheral|stage=1".encode("ascii")
            + suffix,
            f"{PROTOCOL}|SERVICE_CHANGED|role=peripheral|status=requested".encode(
                "ascii"
            )
            + suffix,
            f"{PROTOCOL}|MIGRATE_REBOOT|role=peripheral|stage=2".encode("ascii")
            + suffix,
            f"{PROTOCOL}|REBOOT|role=peripheral|stage=2".encode("ascii") + suffix,
            f"{PROTOCOL}|ADVERTISE|role=peripheral|stage=2".encode("ascii")
            + suffix,
            (
                f"{PROTOCOL}|RESULT|role=peripheral|stage=2"
                f"|service_changed_requests=1|migration_requests=1"
                f"|callback_context=pass"
            ).encode("ascii")
            + suffix,
            end,
        )
        if lines != expected:
            raise BlePairHilFailure(
                f"peripheral W05 protocol 순서/값이 다릅니다: "
                f"기대={expected!r}, 실제={lines!r}"
            )
        return CacheResult("peripheral", 2, 1, 20, 0, 0, 0, 0, 1, 0, 0, "pass")

    if len(lines) != 13:
        raise BlePairHilFailure(f"central W05 record 수가 13이 아닙니다: {len(lines)}")
    fixed = (
        ready,
        begin,
        f"{PROTOCOL}|SCAN|role=central|stage=1".encode("ascii") + suffix,
    )
    if lines[:3] != fixed:
        raise BlePairHilFailure("central W05 READY/BEGIN/SCAN 순서가 다릅니다.")
    prime_pattern = re.compile(
        rb"M29W05\|1\|PRIME\|role=central\|cache_saved=1\|handle=([1-9][0-9]*)"
        + re.escape(suffix)
    )
    migration_pattern = re.compile(
        rb"M29W05\|1\|MIGRATION\|role=central\|old_handle=([1-9][0-9]*)"
        rb"\|new_handle=([1-9][0-9]*)\|invalidated=2"
        + re.escape(suffix)
    )
    prime = prime_pattern.fullmatch(lines[3])
    migration = migration_pattern.fullmatch(lines[6])
    if prime is None or migration is None:
        raise BlePairHilFailure("central W05 handle record 문법이 다릅니다.")
    old_handle = int(prime.group(1))
    if int(migration.group(1)) != old_handle or int(migration.group(2)) == old_handle:
        raise BlePairHilFailure("migration 전후 handle 관계가 잘못됐습니다.")
    expected_tail = (
        f"{PROTOCOL}|SERVICE_CHANGED|role=central|events=1|invalidated=1".encode(
            "ascii"
        )
        + suffix,
        f"{PROTOCOL}|RESTORES|role=central|count=20|cache_restored=20|stale=0".encode(
            "ascii"
        )
        + suffix,
        f"{PROTOCOL}|CORRUPT_REBOOT|role=central|status=requested".encode("ascii")
        + suffix,
        f"{PROTOCOL}|REBOOT|role=central|phase=corrupt".encode("ascii") + suffix,
        f"{PROTOCOL}|SCAN|role=central|stage=2".encode("ascii") + suffix,
        f"{PROTOCOL}|CORRUPT|role=central|rejected=1|restored=0".encode("ascii")
        + suffix,
        (
            f"{PROTOCOL}|RESULT|role=central|bonded=1|reconnects=20|hash_reads=24"
            f"|cache_saved=4|cache_restored=20|invalidated=2|service_changed=1"
            f"|corrupt_rejected=1|stale=0|callback_context=pass"
        ).encode("ascii")
        + suffix,
        end,
    )
    if lines[4:6] != expected_tail[:2] or lines[7:] != expected_tail[2:]:
        raise BlePairHilFailure("central W05 고정 정량 record 순서/값이 다릅니다.")
    return CacheResult("central", 2, 1, 20, 24, 4, 20, 2, 1, 1, 0, "pass")


def _write_exact(serial_port: Any, data: bytes, label: str) -> None:
    """! @brief UART command가 일부만 기록되면 즉시 실패합니다. """

    written = serial_port.write(data)
    serial_port.flush()
    if written != len(data):
        raise BlePairHilFailure(f"{label} command가 일부만 기록됐습니다.")


def _wait_exact(
    serial_port: Any,
    wanted: bytes,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    """! @brief wanted 이전의 protocol·binary noise를 허용하지 않습니다. """

    line = read_line(serial_port, pending, capture, deadline)
    if line != wanted:
        raise BlePairHilFailure(f"protocol record 불일치: 기대={wanted!r}, 실제={line!r}")


def _collect_end(
    serial_port: Any,
    role: str,
    nonce: str,
    core_revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    """! @brief warm reboot를 포함해 exact END까지 모든 line을 보존합니다. """

    expected_end = (
        f"{PROTOCOL}|END|role={role}|status=pass".encode("ascii")
        + _suffix(nonce, core_revision)
    )
    try:
        while True:
            line = read_line(
                serial_port, pending, capture, deadline, stop_event=stop_event
            )
            if line:
                print(f"[{role}] {line.decode('utf-8', errors='backslashreplace')}")
            if line.startswith(f"{PROTOCOL}|FAIL|".encode("ascii")):
                raise BlePairHilFailure(f"{role} target 실패: {line!r}")
            if line == expected_end:
                return
            if line.startswith(f"{PROTOCOL}|END|".encode("ascii")):
                raise BlePairHilFailure(f"{role} END identity/status 불일치: {line!r}")
    except Exception:
        stop_event.set()
        raise


def execute_cache_pair(
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
) -> PairExecution:
    """! @brief 두 image를 sector flash하고 clean state에서 self-contained cache 시험을 실행합니다. """

    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 60.0 <= result_timeout <= 660.0:
        raise BlePairHilFailure("--result-timeout은 60..660초여야 합니다.")
    captures = {"peripheral": bytearray(), "central": bytearray()}
    pending = {"peripheral": bytearray(), "central": bytearray()}
    flashes = {
        "peripheral": ("not-started", "unknown"),
        "central": ("not-started", "unknown"),
    }
    try:
        with ExitStack() as stack:
            ports: dict[str, Any] = {}
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
                        "M29W05", role, endpoint.volume, image, flash_timeout
                    )

            time.sleep(2.0)
            reset = f"{PROTOCOL}|RESET|core={core_revision}\r\n".encode("ascii")
            for role in ("peripheral", "central"):
                ports[role].reset_input_buffer()
                _write_exact(ports[role], reset, f"{role} reset")
            time.sleep(2.0)

            ready_query = f"{PROTOCOL}|READY?\r\n".encode("ascii")
            ready_deadline = time.monotonic() + 30.0
            for role in ("peripheral", "central"):
                ports[role].reset_input_buffer()
                pending[role].clear()
                captures[role].clear()
                _write_exact(ports[role], ready_query, f"{role} ready")
                _wait_exact(
                    ports[role],
                    f"{PROTOCOL}|READY|role={role}|stage=1|core={core_revision}".encode(
                        "ascii"
                    ),
                    pending[role],
                    captures[role],
                    ready_deadline,
                )

            start = (
                f"{PROTOCOL}|START|nonce={nonce}|core={core_revision}\r\n".encode(
                    "ascii"
                )
            )
            deadline = time.monotonic() + result_timeout
            _write_exact(ports["peripheral"], start, "peripheral start")
            for wanted in (
                f"{PROTOCOL}|BEGIN|role=peripheral".encode("ascii")
                + _suffix(nonce, core_revision),
                f"{PROTOCOL}|ADVERTISE|role=peripheral|stage=1".encode("ascii")
                + _suffix(nonce, core_revision),
            ):
                _wait_exact(
                    ports["peripheral"],
                    wanted,
                    pending["peripheral"],
                    captures["peripheral"],
                    deadline,
                )
            _write_exact(ports["central"], start, "central start")

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


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact image·board·evidence 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="두 NU54DK로 M29-W05 cache migration과 손상 거부를 검증합니다."
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
    parser.add_argument("--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS)
    parser.add_argument("--evidence")
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def _board(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief evidence용 DAP/UART/MSD identity를 복사합니다. """

    return {
        "daplink_uid": endpoint.board_id,
        "msd_root": str(endpoint.volume.root),
        "uart_port": endpoint.port_name,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 장치 탐색 또는 전체 W05 pair gate를 실행합니다. """

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
        "NU54DK M29-W05 pair discovery SUCCESS: "
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
        "M29W05", APPLICATION_SOURCE_ROOT, Path(__file__).resolve()
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
        raise BlePairHilFailure("W05 role HEX가 동일하여 오배치를 거부했습니다.")
    nonce = build_nonce()
    try:
        execution = execute_cache_pair(
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
            "gate": "m29-w05-robust-gatt-cache-pair-hil",
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
                "bonded_reconnects": 20,
                "database_hash_reads": 24,
                "service_changed_events": 1,
                "database_migrations": 1,
                "cache_corruption_accepts": 0,
                "stale_handle_uses": 0,
                "m29_cache_01_status": "passed",
            },
            "safety": {
                "external_wiring_required": False,
                "mass_erase_requested": False,
                "sector_flash": args.flash_backend == "pyocd-sector",
                "warm_reboots": 2,
            },
        }
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as error:
        save_failure_transcripts(peripheral_log, central_log, error)
        raise
    print(f"NU54DK M29-W05 cache pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, PairExecutionFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M29-W05 cache pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
