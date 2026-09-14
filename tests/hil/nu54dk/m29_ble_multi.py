#!/usr/bin/env python3
"""! @brief 세 NU54DK의 M29 GATT·CoC 동시 2-link HIL을 자동 검증합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

import ble_pair_hil_common as common  # noqa: E402
from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    BlePairHilFailure,
    RoleEndpoint,
    RoleExecution,
    build_nonce,
    discover_endpoint,
    file_sha256,
    git_revision,
    image_record,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_source_clean,
)
from m28_ble_3board import daplink_debug_identity  # noqa: E402
from m29_ble_multi_protocol import (  # noqa: E402
    MultiProtocolFailure,
    MultiRoleResult,
    parse_role_transcript,
    validate_three_role_session,
)
from m6_serial_echo import import_pyserial  # noqa: E402


MILESTONE = "M29W07D"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m29_ble_multi_hil"
ROLES = ("peripheral", "mixed", "central")
DEFAULT_RESULT_TIMEOUT_SECONDS = 900.0


class MultiExecutionFailure(BlePairHilFailure):
    """! @brief 실행 오류와 실패 시점의 세 raw transcript를 함께 보존합니다. """

    def __init__(self, message: str, transcripts: dict[str, bytes]) -> None:
        super().__init__(message)
        self.transcripts = transcripts


@dataclass(frozen=True)
class MultiExecution:
    """! @brief 세 role의 exact image flash와 UART 결과입니다. """

    peripheral: RoleExecution
    mixed: RoleExecution
    central: RoleExecution


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief 세 role UID·image·timeout·evidence 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="세 NU54DK로 M29-MULTI-01 GATT·CoC 2-link traffic을 검증합니다."
    )
    for role in ROLES:
        parser.add_argument(f"--{role}-hex")
        parser.add_argument(f"--{role}-board-id", required=True)
        parser.add_argument(f"--{role}-volume")
        parser.add_argument(f"--{role}-port", default="auto")
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


def validate_three_board_identity(endpoints: dict[str, RoleEndpoint]) -> None:
    """! @brief 세 role의 UID·MSD·UART가 모두 다른지 확인합니다. """

    for attribute, label in (("board_id", "DAPLink UID"), ("port_name", "UART")):
        values = [str(getattr(endpoints[role], attribute)).casefold() for role in ROLES]
        if len(set(values)) != len(ROLES):
            raise BlePairHilFailure(f"세 role의 {label}가 서로 달라야 합니다.")
    volumes = [str(endpoints[role].volume.root.resolve()).casefold() for role in ROLES]
    if len(set(volumes)) != len(ROLES):
        raise BlePairHilFailure("세 role의 DAPLink MSD가 서로 달라야 합니다.")


def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, dict[str, Path]]:
    """! @brief evidence와 세 raw transcript의 신규 경로를 준비합니다. """

    if not evidence_argument:
        raise BlePairHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise BlePairHilFailure("--evidence는 .json 파일이어야 합니다.")
    transcripts = {
        role: evidence.with_name(f"{evidence.stem}.{role}.transcript.log")
        for role in ROLES
    }
    existing = [path for path in (evidence, *transcripts.values()) if path.exists()]
    if existing and not overwrite:
        raise BlePairHilFailure(
            "기존 증적을 덮어쓰지 않습니다: " + ", ".join(map(str, existing))
        )
    for path in existing:
        if not path.is_file():
            raise BlePairHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing:
            path.unlink()
    return evidence, transcripts


def _write_line(serial_port: Any, line: str) -> None:
    """! @brief ASCII command 한 줄이 전부 기록됐는지 확인합니다. """

    data = (line + "\r\n").encode("ascii")
    written = serial_port.write(data)
    serial_port.flush()
    if written != len(data):
        raise BlePairHilFailure("M29-W07-D UART command가 일부만 기록됐습니다.")


def _read_checked_line(
    serial_port: Any,
    role: str,
    nonce: str,
    revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event | None = None,
) -> bytes:
    """! @brief noise·target FAIL·stale identity를 수집 단계에서 즉시 거부합니다. """

    line = common.read_line(
        serial_port, pending, capture, deadline, stop_event=stop_event
    )
    prefix = b"M29W07D|1|"
    if not line.startswith(prefix):
        raise BlePairHilFailure(f"{role} UART noise를 거부했습니다: {line!r}")
    if line.startswith(prefix + b"FAIL|"):
        raise BlePairHilFailure(f"{role} target 실패: {line!r}")
    ready = f"M29W07D|1|READY|role={role}|core={revision}".encode("ascii")
    if line != ready:
        suffix = f"|nonce={nonce}|core={revision}".encode("ascii")
        if not line.endswith(suffix):
            raise BlePairHilFailure(f"{role} stale nonce/revision record입니다: {line!r}")
    return line


def _wait_for(
    serial_port: Any,
    role: str,
    expected: bytes,
    nonce: str,
    revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    """! @brief 고정 stage token까지 모든 앞선 record를 identity 검사하며 수집합니다. """

    while True:
        line = _read_checked_line(
            serial_port, role, nonce, revision, pending, capture, deadline
        )
        if line == expected:
            return


def _collect_until_end(
    serial_port: Any,
    role: str,
    nonce: str,
    revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    """! @brief role END까지 bounded UART를 수집하고 다른 role 실패를 전파합니다. """

    expected = (
        f"M29W07D|1|END|role={role}|status=pass|nonce={nonce}|core={revision}"
    ).encode("ascii")
    try:
        while True:
            line = _read_checked_line(
                serial_port,
                role,
                nonce,
                revision,
                pending,
                capture,
                deadline,
                stop_event,
            )
            print(f"[{role}] {line.decode('ascii')}")
            if line == expected:
                return
    except Exception:
        stop_event.set()
        raise


def execute_three_board(
    *,
    serial_module: Any,
    endpoints: dict[str, RoleEndpoint],
    images: dict[str, Path],
    nonce: str,
    revision: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
    flash_backend: str,
) -> MultiExecution:
    """! @brief 세 image를 exact UID에 기록하고 chain 연결 뒤 END를 동시 수집합니다. """

    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 1200.0:
        raise BlePairHilFailure("--result-timeout은 30..1200초여야 합니다.")
    captures = {role: bytearray() for role in ROLES}
    pending = {role: bytearray() for role in ROLES}
    flashes = {role: ("not-started", "unknown") for role in ROLES}
    try:
        for role in ROLES:
            if flash_backend == "pyocd-sector":
                flashes[role] = common.flash_image_pyocd(
                    role,
                    endpoints[role].board_id,
                    images[role],
                    flash_timeout,
                )
            else:
                flashes[role] = common.flash_image(
                    MILESTONE,
                    role,
                    endpoints[role].volume,
                    images[role],
                    flash_timeout,
                )
        with ExitStack() as stack:
            ports = {
                role: stack.enter_context(
                    serial_module.Serial(
                        port=endpoints[role].port_name,
                        baudrate=baud_rate,
                        bytesize=serial_module.EIGHTBITS,
                        parity=serial_module.PARITY_NONE,
                        stopbits=serial_module.STOPBITS_ONE,
                        timeout=0.1,
                        write_timeout=2.0,
                    )
                )
                for role in ROLES
            }
            for role in ROLES:
                ports[role].reset_input_buffer()
                _write_line(ports[role], "M29W07D|1|READY?")
            deadline = time.monotonic() + result_timeout
            for role in ROLES:
                ready = f"M29W07D|1|READY|role={role}|core={revision}".encode("ascii")
                _wait_for(
                    ports[role],
                    role,
                    ready,
                    nonce,
                    revision,
                    pending[role],
                    captures[role],
                    deadline,
                )
            start = f"M29W07D|1|START|test=M29-MULTI-01|nonce={nonce}|core={revision}"
            _write_line(ports["peripheral"], start)
            peripheral_advertise = (
                "M29W07D|1|ADVERTISE|role=peripheral|marker=161|psm=129|status=pass"
                f"|nonce={nonce}|core={revision}"
            ).encode("ascii")
            _wait_for(
                ports["peripheral"],
                "peripheral",
                peripheral_advertise,
                nonce,
                revision,
                pending["peripheral"],
                captures["peripheral"],
                deadline,
            )
            _write_line(ports["mixed"], start)
            mixed_advertise = (
                "M29W07D|1|ADVERTISE|role=mixed|marker=178|psm=129|status=pass"
                f"|nonce={nonce}|core={revision}"
            ).encode("ascii")
            _wait_for(
                ports["mixed"],
                "mixed",
                mixed_advertise,
                nonce,
                revision,
                pending["mixed"],
                captures["mixed"],
                deadline,
            )
            _write_line(ports["central"], start)
            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(
                        _collect_until_end,
                        ports[role],
                        role,
                        nonce,
                        revision,
                        pending[role],
                        captures[role],
                        deadline,
                        stop_event,
                    )
                    for role in ROLES
                ]
                try:
                    for future in futures:
                        future.result()
                except Exception:
                    stop_event.set()
                    raise
    except Exception as error:
        raise MultiExecutionFailure(
            str(error), {role: bytes(captures[role]) for role in ROLES}
        ) from error
    records = {
        role: RoleExecution(*flashes[role], bytes(captures[role])) for role in ROLES
    }
    return MultiExecution(**records)


def _board(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief evidence용 DAP/UART/MSD identity를 복사합니다. """

    return {
        "daplink_uid": endpoint.board_id,
        "msd_root": str(endpoint.volume.root),
        "uart_port": endpoint.port_name,
    }


def _save_failure_transcripts(paths: dict[str, Path], error: Exception) -> None:
    """! @brief 실행 실패 시점의 세 raw transcript를 신규 경로에 보존합니다. """

    if isinstance(error, MultiExecutionFailure):
        for role in ROLES:
            paths[role].write_bytes(error.transcripts[role])


def _evidence(
    *,
    core_revision: str,
    board_revision: str,
    nonce: str,
    endpoints: dict[str, RoleEndpoint],
    debug_identities: dict[str, dict[str, str]],
    images: dict[str, Path],
    image_sizes: dict[str, int],
    image_hashes: dict[str, str],
    build_records: dict[str, dict[str, str]],
    transcript_paths: dict[str, Path],
    execution: MultiExecution,
    results: dict[str, MultiRoleResult],
    flash_backend: str,
) -> dict[str, Any]:
    """! @brief exact image·장치·receiver 분모를 단일 PASS evidence로 결합합니다. """

    executions = {role: getattr(execution, role) for role in ROLES}
    return {
        "schema_version": 1,
        "gate": "m29-w07-d-three-board-multi-link-hil",
        "test_id": "M29-MULTI-01",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "nonce": nonce,
        "flash_backend": flash_backend,
        "boards": {role: _board(endpoints[role]) for role in ROLES},
        "debug_identities": debug_identities,
        "images": {
            role: image_record(
                images[role],
                image_sizes[role],
                image_hashes[role],
                executions[role],
                build_records[role],
            )
            for role in ROLES
        },
        "transcripts": {
            role: transcript_record(transcript_paths[role], executions[role].transcript)
            for role in ROLES
        },
        "results": {role: asdict(results[role]) for role in ROLES},
        "coverage": {
            "simultaneous_links": 2,
            "gatt_operations_per_link": 1000,
            "coc_operations_per_link": 1000,
            "cross_link_events": 0,
            "payload_errors": 0,
            "dropped_events": 0,
            "m29_multi_01_status": "passed",
        },
        "packet_trace": {
            "method": "three-node-receiver-validated-gatt-and-coc-sequence",
            "binding": "same-run-128-bit-rf-nonce-and-three-uart-transcripts",
            "denominator": "receiver-validated-per-link-sequence",
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 장치 탐색 또는 전체 M29-MULTI-01 gate를 실행합니다. """

    args = parse_arguments(arguments)
    serial_module, list_ports = import_pyserial()
    endpoints = {
        role: discover_endpoint(
            getattr(args, f"{role}_board_id"),
            getattr(args, f"{role}_volume"),
            getattr(args, f"{role}_port"),
            list_ports,
        )
        for role in ROLES
    }
    validate_three_board_identity(endpoints)
    debug_identities = {
        role: daplink_debug_identity(endpoints[role]) for role in ROLES
    }
    print(
        "NU54DK M29-W07-D discovery SUCCESS: "
        + ", ".join(
            f"{role}={endpoints[role].board_id}/{endpoints[role].port_name}"
            for role in ROLES
        )
    )
    if args.discover_only:
        return 0
    evidence_path, transcript_paths = prepare_output_paths(
        args.evidence, args.overwrite_evidence
    )
    images = {
        role: validate_hex_image(getattr(args, f"{role}_hex")) for role in ROLES
    }
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean(
        MILESTONE,
        APPLICATION_SOURCE_ROOT,
        Path(__file__).resolve(),
        additional_paths=(
            HIL_DIRECTORY / "m28_ble_3board.py",
            HIL_DIRECTORY / "m29_ble_multi_protocol.py",
        ),
    )
    build_records = {
        role: validate_build_record(
            images[role], core_revision, board_revision, APPLICATION_SOURCE_ROOT
        )
        for role in ROLES
    }
    image_sizes = {role: images[role].stat().st_size for role in ROLES}
    image_hashes = {role: file_sha256(images[role]) for role in ROLES}
    if len(set(image_hashes.values())) != len(ROLES):
        raise BlePairHilFailure("세 role HEX가 서로 달라야 합니다.")
    nonce = build_nonce()
    try:
        execution = execute_three_board(
            serial_module=serial_module,
            endpoints=endpoints,
            images=images,
            nonce=nonce,
            revision=core_revision,
            baud_rate=args.baud,
            flash_timeout=args.flash_timeout,
            result_timeout=args.result_timeout,
            flash_backend=args.flash_backend,
        )
        for role in ROLES:
            validate_image_unchanged(images[role], image_sizes[role], image_hashes[role])
        results = {
            role: parse_role_transcript(
                getattr(execution, role).transcript, role, nonce, core_revision
            )
            for role in ROLES
        }
        validate_three_role_session(results)
        for role in ROLES:
            transcript_paths[role].write_bytes(getattr(execution, role).transcript)
        evidence = _evidence(
            core_revision=core_revision,
            board_revision=board_revision,
            nonce=nonce,
            endpoints=endpoints,
            debug_identities=debug_identities,
            images=images,
            image_sizes=image_sizes,
            image_hashes=image_hashes,
            build_records=build_records,
            transcript_paths=transcript_paths,
            execution=execution,
            results=results,
            flash_backend=args.flash_backend,
        )
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as error:
        _save_failure_transcripts(transcript_paths, error)
        raise
    print(f"NU54DK M29-MULTI-01 HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, MultiProtocolFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M29-W07-D HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
