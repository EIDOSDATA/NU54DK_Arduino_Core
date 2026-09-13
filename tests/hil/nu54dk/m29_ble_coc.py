#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M29-W06 LE CoC와 negative 회수를 자동 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence


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
    build_nonce,
    discover_endpoint,
    file_sha256,
    git_revision,
    image_record,
    prepare_output_paths,
    save_failure_transcripts,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_pair_identity,
    validate_source_clean,
)
from m29_ble_long import execute_long_pair  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402


PROTOCOL = "M29W06|1"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests/zephyr/m29_ble_coc_hil"
DEFAULT_RESULT_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True)
class CocResult:
    """! @brief 한 role의 고정 W06 정량 결과입니다. """

    role: str
    channels: int
    sdu_bytes: int
    tx_per_channel: int
    rx_per_channel: int
    malformed_rejected: int
    offset_rejected: int
    execute_rejected: int
    psm_rejected: int
    credit_rejected: int
    unexpected_accepts: int
    recovery_failures: int
    stale_accepts: int
    cross_channel_events: int
    callback_context: str


def _suffix(nonce: str, core_revision: str) -> bytes:
    """! @brief 모든 session record의 exact identity suffix를 만듭니다. """

    return f"|nonce={nonce}|core={core_revision}".encode("ascii")


def parse_role_transcript(
    transcript: bytes, nonce: str, core_revision: str, role: str
) -> CocResult:
    """! @brief noise·누락·중복·재배치·wrong identity를 fail-closed로 거부합니다. """

    nonce = build_nonce(nonce)
    if role not in ("peripheral", "central"):
        raise BlePairHilFailure(f"알 수 없는 W06 role입니다: {role}")
    if len(core_revision) != 40 or any(
        value not in "0123456789abcdef" for value in core_revision
    ):
        raise BlePairHilFailure("Core revision은 소문자 40자리 SHA-1이어야 합니다.")
    try:
        lines = tuple(
            line.strip()
            for line in transcript.replace(b"\r", b"").split(b"\n")
            if line.strip()
        )
        for line in lines:
            line.decode("ascii")
    except UnicodeDecodeError as error:
        raise BlePairHilFailure("W06 transcript에 비 ASCII noise가 있습니다.") from error

    suffix = _suffix(nonce, core_revision)
    ready = f"{PROTOCOL}|READY|role={role}|core={core_revision}".encode("ascii")
    begin = f"{PROTOCOL}|BEGIN|role={role}".encode("ascii") + suffix
    channels = (
        f"{PROTOCOL}|CHANNELS|role={role}|connected=2|local_mtu=512"
        "|remote_mtu=512"
    ).encode("ascii") + suffix
    coc = (
        f"{PROTOCOL}|COC|role={role}|channels=2|sdu=512|tx_per_channel=1000"
        "|rx_per_channel=1000|payload_errors=0"
    ).encode("ascii") + suffix
    end = f"{PROTOCOL}|END|role={role}|status=pass".encode("ascii") + suffix
    if role == "peripheral":
        expected = (
            ready,
            begin,
            f"{PROTOCOL}|ADVERTISE|role=peripheral|psm=128|status=pass".encode(
                "ascii"
            )
            + suffix,
            f"{PROTOCOL}|NEG|role=peripheral|class=offset|attempts=20"
            f"|rejected=20|unexpected=0".encode("ascii")
            + suffix,
            f"{PROTOCOL}|NEG|role=peripheral|class=execute|attempts=20"
            f"|rejected=20|unexpected=0".encode("ascii")
            + suffix,
            channels,
            coc,
            f"{PROTOCOL}|RECOVERY|role=peripheral|new_channels=2|echoes=2"
            f"|failures=0".encode("ascii")
            + suffix,
            f"{PROTOCOL}|RESULT|role=peripheral|offset=20|execute=20"
            f"|unexpected=0|recovery_failures=0|cross_channel=0"
            f"|callback_context=pass".encode("ascii")
            + suffix,
            end,
        )
        result = CocResult(
            role, 2, 512, 1000, 1000, 0, 20, 20, 0, 0, 0, 0, 0, 0, "pass"
        )
    else:
        expected = (
            ready,
            begin,
            f"{PROTOCOL}|SCAN|role=central|status=pass".encode("ascii") + suffix,
            channels,
            f"{PROTOCOL}|NEG|role=central|class=malformed|attempts=20"
            f"|rejected=20|unexpected=0".encode("ascii")
            + suffix,
            f"{PROTOCOL}|NEG|role=central|class=psm|attempts=20"
            f"|rejected=20|unexpected=0".encode("ascii")
            + suffix,
            f"{PROTOCOL}|NEG|role=central|class=credit|attempts=20"
            f"|rejected=20|unexpected=0".encode("ascii")
            + suffix,
            coc,
            f"{PROTOCOL}|RECOVERY|role=central|old_rejected=2|new_channels=2"
            f"|echoes=2|failures=0".encode("ascii")
            + suffix,
            f"{PROTOCOL}|RESULT|role=central|malformed=20|psm=20|credit=20"
            f"|unexpected=0|recovery_failures=0|stale=0"
            f"|callback_context=pass".encode("ascii")
            + suffix,
            end,
        )
        result = CocResult(
            role, 2, 512, 1000, 1000, 20, 0, 0, 20, 20, 0, 0, 0, 0, "pass"
        )
    if lines != expected:
        raise BlePairHilFailure(
            f"{role} W06 protocol 순서/값이 다릅니다: 기대={expected!r}, 실제={lines!r}"
        )
    return result


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact image·board·evidence 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="두 NU54DK로 M29-W06 CoC 2채널과 5개 negative 오류군을 검증합니다."
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
        "--flash-backend", choices=("pyocd-sector", "daplink-msd"),
        default="pyocd-sector"
    )
    parser.add_argument(
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
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
    """! @brief 장치 탐색 또는 전체 W06 pair gate를 실행합니다. """

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
        "NU54DK M29-W06 pair discovery SUCCESS: "
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
        "M29W06",
        APPLICATION_SOURCE_ROOT,
        Path(__file__).resolve(),
        additional_paths=(HIL_DIRECTORY / "m29_ble_long.py",),
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
        raise BlePairHilFailure("W06 role HEX가 동일하여 오배치를 거부했습니다.")
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
            protocol=PROTOCOL,
            flash_label="M29W06",
            ready_query=f"{PROTOCOL}|READY?\r\n".encode("ascii"),
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
            "gate": "m29-w06-coc-negative-pair-hil",
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
                    peripheral_image, peripheral_size, peripheral_sha256,
                    execution.peripheral, peripheral_record
                ),
                "central": image_record(
                    central_image, central_size, central_sha256,
                    execution.central, central_record
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
                "channels": 2,
                "sdu_bytes": 512,
                "sdus_per_channel_per_direction": 1000,
                "payload_errors": 0,
                "negative_iterations_per_class": 20,
                "negative_classes": ["malformed", "offset", "execute", "psm", "credit"],
                "unexpected_accepts": 0,
                "resource_recovery_failures": 0,
                "m29_coc_01_status": "passed",
                "m29_neg_01_status": "passed",
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
    print(f"NU54DK M29-W06 CoC pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, PairExecutionFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M29-W06 CoC pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
