#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M28 ADV·PAwR·privacy HIL을 자동 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    DEFAULT_BAUD_RATE,
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


MILESTONE = "M28B2"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m28_ble_2board_hil"
EVIDENCE_SCHEMA = 1
DEFAULT_RESULT_TIMEOUT_SECONDS = 300.0
PAWR_PATTERN = re.compile(
    rb"^NUCODE_M28B2_(PERIPHERAL|CENTRAL):PAWR:PASS:responses=(\d+)"
    rb":corrupt=0:out_of_window=0:subevent_mask=15:slot_mask=15:drops=0"
)


@dataclass(frozen=True)
class M28TwoBoardRoleResult:
    """! @brief 한 role의 세 RF 단계와 정량 결과입니다. """

    role: str
    advertising_reports: int
    advertising_payload_bytes: int
    pawr_responses: int
    pawr_subevent_mask: int
    pawr_slot_mask: int
    rpa_rotations: int
    connections: int
    reconnects: int
    pairing_events: int
    bond_count: int
    identity_mismatches: int
    stale_events: int


## @brief 두 role UID와 exact image/evidence 인자를 선언합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "두 NU54DK로 M28 255-byte extended advertising, 4x4 PAwR, "
            "RPA 3회와 bonded reconnect 20회를 검증합니다."
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


## @brief PAwR fixed grammar를 소비하고 99%·mask·drop 기준을 검증합니다.
def take_pawr(
    lines: list[bytes], cursor: int, role: str, nonce_suffix: bytes
) -> tuple[int, int]:
    if cursor >= len(lines):
        raise BlePairHilFailure(f"{role} PAwR protocol line이 누락됐습니다.")
    match = PAWR_PATTERN.match(lines[cursor])
    if (
        match is None
        or match.group(1).decode("ascii").lower() != role
        or lines[cursor][match.end() :] != nonce_suffix
    ):
        raise BlePairHilFailure(f"{role} PAwR protocol 형식이 잘못됐습니다: {lines[cursor]!r}")
    responses = int(match.group(2))
    if responses < 99 or responses > 105:
        raise BlePairHilFailure(f"{role} PAwR response 수가 범위를 벗어났습니다: {responses}")
    return cursor + 1, responses


## @brief 한 role의 고정 protocol 순서와 수치를 fail-closed로 검증합니다.
def parse_role_transcript(
    transcript: bytes, nonce: str, role: str
) -> M28TwoBoardRoleResult:
    nonce = build_nonce(nonce)
    if role not in ("peripheral", "central"):
        raise BlePairHilFailure(f"알 수 없는 M28 2보드 role입니다: {role}")
    role_upper = role.upper()
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, MILESTONE, nonce)
    cursor = 0
    cursor = take_exact(
        lines, cursor, f"NUCODE_M28B2_READY:role={role}".encode("ascii")
    )
    if role == "peripheral":
        cursor = take_exact(
            lines,
            cursor,
            b"NUCODE_M28B2_PERIPHERAL:ADVERTISE:PASS" + suffix,
        )
        advertising_reports = 110
    else:
        advertising_reports = 100
    cursor = take_exact(
        lines,
        cursor,
        (
            f"NUCODE_M28B2_{role_upper}:ADV:PASS:reports={advertising_reports}"
            ":payload=255:corrupt=0:stale=0"
        ).encode("ascii")
        + suffix,
    )
    cursor, pawr_responses = take_pawr(lines, cursor, role, suffix)
    cursor = take_exact(
        lines,
        cursor,
        f"NUCODE_M28B2_{role_upper}:RPA:PASS:rotations=3".encode("ascii")
        + suffix,
    )
    cursor = take_exact(
        lines,
        cursor,
        (
            f"NUCODE_M28B2_{role_upper}:PRIV:PASS:connections=21:reconnects=20"
            ":pairings=1:bond_count=1:identity_mismatch=0:stale=0"
        ).encode("ascii")
        + suffix,
    )
    cursor = take_exact(
        lines,
        cursor,
        (
            f"NUCODE_M28B2_{role_upper}:FINAL:PASS:adv=PASS:pawr=PASS"
            ":privacy=PASS"
        ).encode("ascii")
        + suffix,
    )
    if cursor != len(lines):
        raise BlePairHilFailure(
            f"{role} FINAL 뒤 예상 밖 protocol token입니다: {lines[cursor:]!r}"
        )
    return M28TwoBoardRoleResult(
        role,
        advertising_reports,
        255,
        pawr_responses,
        15,
        15,
        3,
        21,
        20,
        1,
        1,
        0,
        0,
    )


## @brief 두 보드·image·transcript와 M28 2보드 coverage를 결합합니다.
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
    flash_backend: str,
    peripheral_result: M28TwoBoardRoleResult,
    central_result: M28TwoBoardRoleResult,
) -> dict[str, Any]:
    def board(endpoint: RoleEndpoint) -> dict[str, str]:
        return {
            "daplink_uid": endpoint.board_id,
            "msd_root": str(endpoint.volume.root),
            "uart_port": endpoint.port_name,
        }

    return {
        "schema_version": EVIDENCE_SCHEMA,
        "gate": "m28-two-board-hil",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "flash_backend": flash_backend,
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
            "test_ids": ["M28-ADV-01", "M28-PAWR-01", "M28-PRIV-01"],
            "extended_payload_bytes": 255,
            "extended_reports": 100,
            "pawr_subevents": 4,
            "pawr_response_slots": 4,
            "pawr_minimum_valid_percent": 99,
            "rpa_rotations": 3,
            "bonded_reconnects": 20,
            "cross_coverage": {
                "bond_reboot_persistence": "M21 BLE security HIL",
                "three_board_tests": [
                    "M28-LINK-01",
                    "M28-PER-01",
                    "M28-CTRL-01",
                    "M28-SOAK-01",
                ],
            },
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    }


## @brief 장치 탐색 또는 전체 M28 2보드 gate를 실행합니다.
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
        "NU54DK M28 2-board discovery SUCCESS: "
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
        raise BlePairHilFailure("M28 role HEX가 동일하여 오배치를 거부했습니다.")

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
            flash_backend=args.flash_backend,
        )
        validate_image_unchanged(peripheral_image, peripheral_size, peripheral_sha256)
        validate_image_unchanged(central_image, central_size, central_sha256)
        peripheral_result = parse_role_transcript(
            execution.peripheral.transcript, nonce, "peripheral"
        )
        central_result = parse_role_transcript(
            execution.central.transcript, nonce, "central"
        )
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
            flash_backend=args.flash_backend,
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
    print(f"NU54DK M28 2-board HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M28 2-board HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
