#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M29-W04 descriptor·authorization을 자동 검증합니다. """

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


PROTOCOL = "M29W04|1"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests/zephyr/m29_ble_descriptor_hil"
DEFAULT_RESULT_TIMEOUT_SECONDS = 360.0


@dataclass(frozen=True)
class DescriptorResult:
    """! @brief 한 role의 고정 W04 protocol 결과입니다. """

    role: str
    mtu: int
    descriptors: int
    reads: int
    handles: int
    payload_bytes: int
    authorization_checks: int
    authorization_allowed: int
    authorization_denied: int
    expected_denials: int
    authorization_errors: int
    descriptor_writes: int
    corrupt_values: int
    stale_events: int
    callback_context: str


def _suffix(nonce: str, core_revision: str) -> bytes:
    """! @brief 모든 session record의 exact identity suffix를 만듭니다. """

    return f"|nonce={nonce}|core={core_revision}".encode("ascii")


def parse_role_transcript(
    transcript: bytes, nonce: str, core_revision: str, role: str
) -> DescriptorResult:
    """! @brief noise·누락·중복·재배치·wrong identity를 fail-closed로 거부합니다. """

    nonce = build_nonce(nonce)
    if role not in ("peripheral", "central"):
        raise BlePairHilFailure(f"알 수 없는 W04 role입니다: {role}")
    if len(core_revision) != 40 or any(
        value not in "0123456789abcdef" for value in core_revision
    ):
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
        raise BlePairHilFailure("W04 transcript에 비 ASCII noise가 있습니다.") from error

    suffix = _suffix(nonce, core_revision)
    ready = f"{PROTOCOL}|READY|role={role}|core={core_revision}".encode("ascii")
    begin = f"{PROTOCOL}|BEGIN|role={role}".encode("ascii") + suffix
    link = f"{PROTOCOL}|LINK|role={role}|mtu=247".encode("ascii") + suffix
    end = f"{PROTOCOL}|END|role={role}|status=pass".encode("ascii") + suffix
    if role == "peripheral":
        expected = (
            ready,
            begin,
            f"{PROTOCOL}|ADVERTISE|role=peripheral|status=pass".encode("ascii")
            + suffix,
            link,
            f"{PROTOCOL}|RESULT|role=peripheral|descriptors=4"
            f"|authorization_checks=402|allowed=401|denied=1|descriptor_writes=0"
            f"|authorization_errors=0|callback_context=pass".encode("ascii")
            + suffix,
            end,
        )
        result = DescriptorResult(
            role, 247, 4, 0, 0, 0, 402, 401, 1, 0, 0, 0, 0, 0, "pass"
        )
    else:
        expected = (
            ready,
            begin,
            f"{PROTOCOL}|SCAN|role=central|status=pass".encode("ascii") + suffix,
            link,
            f"{PROTOCOL}|RESULT|role=central|descriptors=4|reads=100|handles=4"
            f"|bytes=16|expected_denials=1|authorization_errors=0|corrupt=0"
            f"|stale=0|callback_context=pass".encode("ascii")
            + suffix,
            end,
        )
        result = DescriptorResult(
            role, 247, 4, 100, 4, 16, 0, 0, 0, 1, 0, 0, 0, 0, "pass"
        )
    if tuple(lines) != expected:
        raise BlePairHilFailure(
            f"{role} W04 protocol 순서/값이 다릅니다: 기대={expected!r}, 실제={tuple(lines)!r}"
        )
    return result


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact image·board·evidence 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="두 NU54DK로 M29-W04 descriptor 4개와 read-multiple 100회를 검증합니다."
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


def _board(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief evidence용 DAP/UART/MSD identity를 복사합니다. """

    return {
        "daplink_uid": endpoint.board_id,
        "msd_root": str(endpoint.volume.root),
        "uart_port": endpoint.port_name,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 장치 탐색 또는 전체 W04 pair gate를 실행합니다. """

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
        "NU54DK M29-W04 pair discovery SUCCESS: "
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
        "M29W04",
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
        raise BlePairHilFailure("W04 role HEX가 동일하여 오배치를 거부했습니다.")
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
            flash_label="M29W04",
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
            "gate": "m29-w04-descriptor-authorization-pair-hil",
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
                "att_mtu": 247,
                "descriptors": 4,
                "read_multiple_handles": 4,
                "read_multiple_iterations": 100,
                "authorization_expected_denials": 1,
                "authorization_errors": 0,
                "payload_corruption": 0,
                "m29_desc_01_status": "passed",
                "link_notify_indicate": "host-tested-target-built",
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
    print(f"NU54DK M29-W04 descriptor pair HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, PairExecutionFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M29-W04 descriptor pair HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
