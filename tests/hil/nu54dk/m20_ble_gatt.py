#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M20 범용 GATT server/client HIL을 자동 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
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
    build_nonce,
    discover_endpoint,
    execute_pair,
    file_sha256,
    git_revision,
    image_record,
    prepare_output_paths,
    protocol_lines,
    save_failure_transcripts,
    take_exact,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_pair_identity,
    validate_source_clean,
)
from m6_serial_echo import import_pyserial  # noqa: E402


MILESTONE = "M20"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m20_ble_gatt_hil"
EVIDENCE_SCHEMA = 1


@dataclass(frozen=True)
class GattCentralResult:
    """! @brief central이 검증한 범용 GATT client operation 결과입니다. """

    nonce: str
    connection_rounds: tuple[int, ...]
    discovery_rounds: tuple[int, ...]
    nonce_challenge: str
    read: str
    write_response: str
    write_command: str
    notification_rounds: tuple[int, ...]
    indication: str
    handle_invalidation_rounds: tuple[int, ...]
    callback_context: str


@dataclass(frozen=True)
class GattPeripheralResult:
    """! @brief peripheral이 검증한 server write·indication·재광고 결과입니다. """

    nonce: str
    connection_rounds: tuple[int, ...]
    write_response: str
    write_command: str
    indication_confirmation: str
    callback_context: str


## @brief 두 role UID와 image/evidence 인자를 선언합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "두 NU54DK로 M20 GATT discovery/read/write/notify/indicate/"
            "reconnect를 자동 검증합니다."
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
    parser.add_argument("--evidence")
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


## @brief central transcript의 모든 client operation과 재발견 순서를 검증합니다.
def parse_central_transcript(transcript: bytes, nonce: str) -> GattCentralResult:
    nonce = build_nonce(nonce)
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, MILESTONE, nonce)
    expected = (
        b"NUCODE_M20_READY:role=central",
        b"NUCODE_M20_CENTRAL:SCAN_FILTER:PASS" + suffix,
        b"NUCODE_M20_EVENT:CONNECTED:round=1" + suffix,
        b"NUCODE_M20_CENTRAL:DISCOVERY:PASS:round=1" + suffix,
        b"NUCODE_M20_CENTRAL:NONCE_CHALLENGE:PASS" + suffix,
        b"NUCODE_M20_CENTRAL:READ:PASS" + suffix,
        b"NUCODE_M20_CENTRAL:WRITE_RESPONSE:PASS" + suffix,
        b"NUCODE_M20_CENTRAL:WRITE_COMMAND:PASS" + suffix,
        b"NUCODE_M20_CENTRAL:SUBSCRIBE_NOTIFY:PASS:round=1" + suffix,
        b"NUCODE_M20_CENTRAL:NOTIFICATION:PASS:round=1" + suffix,
        b"NUCODE_M20_CENTRAL:UNSUBSCRIBE_NOTIFY:PASS:round=1" + suffix,
        b"NUCODE_M20_CENTRAL:SUBSCRIBE_INDICATE:PASS" + suffix,
        b"NUCODE_M20_CENTRAL:INDICATION:PASS" + suffix,
        b"NUCODE_M20_CENTRAL:UNSUBSCRIBE_INDICATE:PASS" + suffix,
        b"NUCODE_M20_EVENT:DISCONNECTED:count=1" + suffix,
        b"NUCODE_M20_CENTRAL:HANDLES_INVALIDATED:PASS:round=1" + suffix,
        b"NUCODE_M20_CENTRAL:RECONNECT_REQUEST:PASS" + suffix,
        b"NUCODE_M20_EVENT:CONNECTED:round=2" + suffix,
        b"NUCODE_M20_CENTRAL:DISCOVERY:PASS:round=2" + suffix,
        b"NUCODE_M20_CENTRAL:SUBSCRIBE_NOTIFY:PASS:round=2" + suffix,
        b"NUCODE_M20_CENTRAL:NOTIFICATION:PASS:round=2" + suffix,
        b"NUCODE_M20_CENTRAL:UNSUBSCRIBE_NOTIFY:PASS:round=2" + suffix,
        b"NUCODE_M20_EVENT:DISCONNECTED:count=2" + suffix,
        b"NUCODE_M20_CENTRAL:HANDLES_INVALIDATED:PASS:round=2" + suffix,
        b"NUCODE_M20_CENTRAL:FINAL:PASS:callback_context=PASS:rediscovery=PASS"
        + suffix,
    )
    cursor = 0
    for line in expected:
        cursor = take_exact(lines, cursor, line)
    if cursor != len(lines):
        raise BlePairHilFailure(
            f"central FINAL 뒤 예상 밖 M20 token이 있습니다: {lines[cursor:]!r}"
        )
    return GattCentralResult(
        nonce,
        (1, 2),
        (1, 2),
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        (1, 2),
        "PASS",
        (1, 2),
        "PASS",
    )


## @brief peripheral transcript의 server callback과 재광고 순서를 검증합니다.
def parse_peripheral_transcript(
    transcript: bytes, nonce: str
) -> GattPeripheralResult:
    nonce = build_nonce(nonce)
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, MILESTONE, nonce)
    expected = (
        b"NUCODE_M20_READY:role=peripheral",
        b"NUCODE_M20_PERIPHERAL:ADVERTISE:PASS" + suffix,
        b"NUCODE_M20_EVENT:CONNECTED:round=1" + suffix,
        b"NUCODE_M20_PERIPHERAL:WRITE_RESPONSE:PASS" + suffix,
        b"NUCODE_M20_PERIPHERAL:WRITE_COMMAND:PASS" + suffix,
        b"NUCODE_M20_PERIPHERAL:INDICATION_CONFIRMED:PASS" + suffix,
        b"NUCODE_M20_EVENT:DISCONNECTED:count=1" + suffix,
        b"NUCODE_M20_PERIPHERAL:READVERTISE:PASS" + suffix,
        b"NUCODE_M20_EVENT:CONNECTED:round=2" + suffix,
        b"NUCODE_M20_EVENT:DISCONNECTED:count=2" + suffix,
        b"NUCODE_M20_PERIPHERAL:FINAL:PASS:callback_context=PASS:rediscovery=PASS"
        + suffix,
    )
    cursor = 0
    for line in expected:
        cursor = take_exact(lines, cursor, line)
    if cursor != len(lines):
        raise BlePairHilFailure(
            f"peripheral FINAL 뒤 예상 밖 M20 token이 있습니다: {lines[cursor:]!r}"
        )
    return GattPeripheralResult(
        nonce, (1, 2), "PASS", "PASS", "PASS", "PASS"
    )


## @brief 두 보드·image·transcript·GATT coverage를 PASS evidence로 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    nonce: str,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    peripheral_image: Path,
    central_image: Path,
    peripheral_size: int,
    central_size: int,
    peripheral_sha256: str,
    central_sha256: str,
    peripheral_build_record: dict[str, str],
    central_build_record: dict[str, str],
    peripheral_transcript_path: Path,
    central_transcript_path: Path,
    execution: Any,
    peripheral_result: GattPeripheralResult,
    central_result: GattCentralResult,
) -> dict[str, Any]:
    def board(endpoint: RoleEndpoint) -> dict[str, str]:
        return {
            "daplink_uid": endpoint.board_id,
            "msd_root": str(endpoint.volume.root),
            "uart_port": endpoint.port_name,
        }

    return {
        "schema_version": EVIDENCE_SCHEMA,
        "gate": "m20-ble-generic-gatt-pair-hil",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "nonce": nonce,
        "boards": {
            "peripheral": board(peripheral_endpoint),
            "central": board(central_endpoint),
        },
        "images": {
            "peripheral": image_record(
                peripheral_image,
                peripheral_size,
                peripheral_sha256,
                execution.peripheral,
                peripheral_build_record,
            ),
            "central": image_record(
                central_image,
                central_size,
                central_sha256,
                execution.central,
                central_build_record,
            ),
        },
        "transcripts": {
            "peripheral": transcript_record(
                peripheral_transcript_path, execution.peripheral.transcript
            ),
            "central": transcript_record(
                central_transcript_path, execution.central.transcript
            ),
        },
        "results": {
            "peripheral": asdict(peripheral_result),
            "central": asdict(central_result),
        },
        "coverage": {
            "service_registration": True,
            "exact_service_characteristic_discovery": True,
            "gatt_nonce_challenge_bits": 128,
            "cached_read": True,
            "write_with_response": True,
            "write_without_response": True,
            "notification_subscribe_unsubscribe": True,
            "indication_confirmation": True,
            "disconnect_handle_invalidation": True,
            "reconnect_rediscovery_resubscribe": True,
            "callback_context": "arduino-main-thread",
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    }


## @brief 장치 탐색 또는 전체 M20 pair gate를 실행합니다.
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
        "NU54DK M20 pair discovery SUCCESS: "
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
    validate_source_clean(MILESTONE, APPLICATION_SOURCE_ROOT, Path(__file__).resolve())
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
        raise BlePairHilFailure("M20 role HEX가 동일하여 오배치를 거부했습니다.")

    nonce = build_nonce()
    try:
        execution = execute_pair(
            serial_module=serial_module,
            milestone=MILESTONE,
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
            peripheral_image, peripheral_size, peripheral_sha256
        )
        validate_image_unchanged(central_image, central_size, central_sha256)
        peripheral_result = parse_peripheral_transcript(
            execution.peripheral.transcript, nonce
        )
        central_result = parse_central_transcript(execution.central.transcript, nonce)
        peripheral_log.write_bytes(execution.peripheral.transcript)
        central_log.write_bytes(execution.central.transcript)
        evidence = build_evidence(
            core_revision=core_revision,
            board_revision=board_revision,
            nonce=nonce,
            peripheral_endpoint=peripheral_endpoint,
            central_endpoint=central_endpoint,
            peripheral_image=peripheral_image,
            central_image=central_image,
            peripheral_size=peripheral_size,
            central_size=central_size,
            peripheral_sha256=peripheral_sha256,
            central_sha256=central_sha256,
            peripheral_build_record=peripheral_record,
            central_build_record=central_record,
            peripheral_transcript_path=peripheral_log,
            central_transcript_path=central_log,
            execution=execution,
            peripheral_result=peripheral_result,
            central_result=central_result,
        )
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as error:
        save_failure_transcripts(peripheral_log, central_log, error)
        raise
    print(f"NU54DK M20 generic GATT pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M20 generic GATT pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
