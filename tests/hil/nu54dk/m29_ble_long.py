#!/usr/bin/env python3
"""! @brief 두 NU54DK의 M29-W02 512-byte long read를 자동 검증합니다. """

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
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
    discover_endpoint_sha256,
    file_sha256,
    flash_image,
    flash_image_pyocd_sha256,
    git_revision,
    image_record,
    public_endpoint,
    prepare_output_paths,
    probe_sha256,
    read_line,
    reset_target_pyocd_sha256,
    save_failure_transcripts,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_endpoint_transports,
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
    parser.add_argument("--probe-peripheral-sha256", required=True)
    parser.add_argument("--probe-central-sha256", required=True)
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
    advertise_fields: str = "status=pass",
) -> None:
    """! @brief peripheral BEGIN과 ADVERTISE를 exact 순서로 소비합니다. """

    suffix = _suffix(nonce, core_revision)
    expected = (
        f"{protocol}|BEGIN|role=peripheral".encode("ascii") + suffix,
        f"{protocol}|ADVERTISE|role=peripheral|{advertise_fields}".encode("ascii")
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


PREQUERY_QUIET_SECONDS = 1.0
PREQUERY_MAX_SECONDS = 8.0
PREQUERY_MAX_BYTES = 65536
PREQUERY_ROLES = ("peripheral", "central")


def _prequery_paths(evidence_path: Path) -> tuple[Path, dict[str, Path]]:
    """! @brief 질의 전 관측 증거를 기존 native 파일 옆에 별도로 배치합니다. """

    return (
        evidence_path.with_name(evidence_path.stem + ".prequery.json"),
        {
            role: evidence_path.with_name(
                evidence_path.stem + f".{role}.prequery.transcript.log"
            )
            for role in PREQUERY_ROLES
        },
    )


def _prequery_failure_marker(raw: bytes) -> bool:
    """! @brief 관측된 명시적 실패 표식을 새 질의로 숨기지 않습니다. """

    upper = raw.upper()
    return any(token in upper for token in (
        b"|FAIL|", b"HARD FAULT", b"MPU FAULT", b"BUS FAULT",
        b"USAGE FAULT", b"ASSERTION FAIL", b"ZEPHYR FATAL ERROR",
    ))


def _query_ready_after_quiet(
    ports: dict[str, Any], query: bytes, evidence_path: Path,
    evidence_reference: dict[str, str], deadline: float,
    protocol: str, nonce: str, core_revision: str,
) -> None:
    """! @brief 제한된 RX 관측을 보존한 뒤 각 보드에 READY?를 한 번만 보냅니다.
    @details quiet는 관측 구간의 무수신이며 USB 전체 비움이나 응답 인과 증명이 아닙니다.
    """

    metadata_path, raw_paths = _prequery_paths(evidence_path)
    started = time.monotonic()
    boundary_deadline = min(deadline, started + PREQUERY_MAX_SECONDS)
    last_data = started
    captures = {role: bytearray() for role in PREQUERY_ROLES}
    record = {
        "schema": "nucode-m29-prequery-observation-v1",
        "status": "OBSERVATION_INCOMPLETE",
        "protocol": protocol,
        "nonce": nonce,
        "core_revision": core_revision,
        "quiet_seconds": PREQUERY_QUIET_SECONDS,
        "max_seconds": PREQUERY_MAX_SECONDS,
        "max_bytes_per_role": PREQUERY_MAX_BYTES,
        "started_monotonic": started,
        "result_deadline_monotonic": deadline,
        "boundary_deadline_monotonic": boundary_deadline,
        "quiet_started_monotonic": None,
        "quiet_observed_monotonic": None,
        "finished_monotonic": None,
        "returned_byte_capture_complete": False,
        "capture_error": None,
        "raw_close_error": None,
        "query_error": None,
        "preservation_errors": [],
        "query_attempts": {role: 0 for role in PREQUERY_ROLES},
        "query_written_bytes": {role: None for role in PREQUERY_ROLES},
        "query_started_monotonic": {role: None for role in PREQUERY_ROLES},
        "read_events": [],
        "raw": {},
        "interpretation": "observed_quiet_only_no_usb_flush_or_response_causality_claim",
    }
    handles = {}
    failure = None
    phase = "capture"

    def preservation_error(operation: str, error: Exception) -> None:
        """! @brief 후속 저장 오류를 추가하되 최초 실패 객체와 원인을 유지합니다. """

        nonlocal failure
        record["preservation_errors"].append({
            "operation": operation, "type": type(error).__name__, "message": str(error),
        })
        if failure is None:
            failure = error

    try:
        for role in PREQUERY_ROLES:
            handles[role] = raw_paths[role].open("xb")
        while True:
            empty_round = True
            for role in PREQUERY_ROLES:
                if time.monotonic() >= boundary_deadline:
                    raise TimeoutError("READY 질의 전 RX 관측 시간 제한을 넘었습니다.")
                waiting = ports[role].in_waiting
                remaining = PREQUERY_MAX_BYTES - len(captures[role])
                chunk = ports[role].read(min(max(waiting, 1), remaining + 1))
                observed = time.monotonic()
                record["read_events"].append({
                    "role": role, "observed_monotonic": observed,
                    "offset": len(captures[role]), "bytes": len(chunk),
                })
                if chunk:
                    captures[role].extend(chunk)
                    written = handles[role].write(chunk)
                    handles[role].flush()
                    if written != len(chunk):
                        raise OSError("READY 질의 전 raw capture가 일부만 저장됐습니다.")
                    last_data = observed
                    empty_round = False
                    if len(captures[role]) > PREQUERY_MAX_BYTES:
                        raise BlePairHilFailure("READY 질의 전 RX 크기 제한을 넘었습니다.")
                    if _prequery_failure_marker(bytes(captures[role])):
                        raise BlePairHilFailure("READY 질의 전 명시적 FAIL/fault가 관측됐습니다.")
                if observed >= boundary_deadline:
                    raise TimeoutError("READY 질의 전 RX 관측 시간 제한을 넘었습니다.")
            observed = time.monotonic()
            if observed >= boundary_deadline:
                raise TimeoutError("READY 질의 전 quiet 판정 시간 제한을 넘었습니다.")
            if empty_round and observed - last_data >= PREQUERY_QUIET_SECONDS:
                record["quiet_started_monotonic"] = last_data
                record["quiet_observed_monotonic"] = observed
                break
        phase = "query"
        for role in PREQUERY_ROLES:
            query_started = time.monotonic()
            if query_started >= boundary_deadline:
                raise TimeoutError("READY 질의 직전 boundary 시간 제한이 만료됐습니다.")
            record["query_attempts"][role] = 1
            record["query_started_monotonic"][role] = query_started
            written = ports[role].write(query)
            record["query_written_bytes"][role] = written
            ports[role].flush()
            if written != len(query):
                raise BlePairHilFailure(f"{role} READY query가 일부만 기록됐습니다.")
            if time.monotonic() >= boundary_deadline:
                raise TimeoutError("READY 질의 중 boundary 시간 제한이 만료됐습니다.")
    except Exception as error:
        record["query_error" if phase == "query" else "capture_error"] = (
            f"{type(error).__name__}: {error}"
        )
        failure = error
    finally:
        for role, handle in handles.items():
            try:
                handle.close()
            except Exception as error:
                record["raw_close_error"] = f"{role}: {type(error).__name__}: {error}"
                preservation_error(f"{role}_raw_close", error)
        record["finished_monotonic"] = time.monotonic()
        for role in handles:
            try:
                record["raw"][role] = {
                    "path": raw_paths[role].name,
                    "sha256": file_sha256(raw_paths[role]),
                    "returned_bytes": len(captures[role]),
                }
            except Exception as error:
                preservation_error(f"{role}_raw_hash", error)
        if failure is None:
            record["returned_byte_capture_complete"] = True
            record["status"] = "OBSERVED_QUIET_QUERY_WRITTEN"
        try:
            payload = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            with metadata_path.open("x", encoding="utf-8", newline="\n") as output:
                if output.write(payload) != len(payload):
                    raise OSError("READY 질의 전 metadata가 일부만 저장됐습니다.")
            evidence_reference.update({
                "path": metadata_path.name, "sha256": file_sha256(metadata_path),
            })
        except Exception as error:
            preservation_error("metadata_write_close_or_hash", error)
    if failure is not None:
        if record["preservation_errors"]:
            summary = json.dumps(record["preservation_errors"], ensure_ascii=False)
            raise BlePairHilFailure(
                f"최초 오류 {type(failure).__name__}: {failure}; 증거 보존 오류: {summary}"
            ) from failure
        raise failure


def validate_prequery_observation(
    record: dict, raw: dict[str, bytes], protocol: str,
    nonce: str, core_revision: str,
) -> None:
    """! @brief 보존된 질의 전 관측을 strict protocol 실적과 분리해 재검증합니다. """

    def require_boundary(value: bool) -> None:
        """! @brief 누락되거나 변조된 관측을 성공 증거로 허용하지 않습니다. """

        if not value:
            raise BlePairHilFailure("READY prequery observation 불일치")

    require_boundary(
        isinstance(record, dict)
        and record.get("schema") == "nucode-m29-prequery-observation-v1"
        and record.get("status") == "OBSERVED_QUIET_QUERY_WRITTEN"
        and record.get("protocol") == protocol
        and record.get("nonce") == nonce
        and record.get("core_revision") == core_revision
        and record.get("quiet_seconds") == PREQUERY_QUIET_SECONDS
        and record.get("max_seconds") == PREQUERY_MAX_SECONDS
        and record.get("max_bytes_per_role") == PREQUERY_MAX_BYTES
        and record.get("returned_byte_capture_complete") is True
        and all(key in record and record[key] is None for key in (
            "capture_error", "raw_close_error", "query_error"
        ))
        and type(record.get("preservation_errors")) is list
        and not record["preservation_errors"]
        and record.get("interpretation") ==
            "observed_quiet_only_no_usb_flush_or_response_causality_claim"
        and set(raw) == set(PREQUERY_ROLES)
        and set(record.get("raw", {})) == set(PREQUERY_ROLES)
    )
    time_keys = (
        "started_monotonic", "result_deadline_monotonic", "boundary_deadline_monotonic",
        "quiet_started_monotonic", "quiet_observed_monotonic", "finished_monotonic",
    )
    require_boundary(all(
        type(record.get(key)) in (int, float) and math.isfinite(record[key])
        for key in time_keys
    ))
    started = record["started_monotonic"]
    quiet_start = record["quiet_started_monotonic"]
    quiet_end = record["quiet_observed_monotonic"]
    require_boundary(
        started <= quiet_start <= quiet_end <= record["finished_monotonic"]
        < record["result_deadline_monotonic"]
        and quiet_end < record["boundary_deadline_monotonic"]
        and record["boundary_deadline_monotonic"] == min(
            record["result_deadline_monotonic"], started + PREQUERY_MAX_SECONDS
        )
        and quiet_end - quiet_start >= PREQUERY_QUIET_SECONDS
    )
    events = record.get("read_events")
    require_boundary(isinstance(events, list) and len(events) >= 2)
    offsets = {role: 0 for role in PREQUERY_ROLES}
    last_data = started
    previous_time = started
    for index, event in enumerate(events):
        require_boundary(isinstance(event, dict) and set(event) == {
            "role", "observed_monotonic", "offset", "bytes"
        })
        role = PREQUERY_ROLES[index % 2]
        observed = event["observed_monotonic"]
        require_boundary(
            event["role"] == role
            and type(event["offset"]) is int and event["offset"] == offsets[role]
            and type(event["bytes"]) is int and event["bytes"] >= 0
            and type(observed) in (int, float) and math.isfinite(observed)
            and previous_time <= observed <= quiet_end
        )
        previous_time = observed
        offsets[role] += event["bytes"]
        if event["bytes"]:
            last_data = observed
    require_boundary(
        len(events) % 2 == 0 and all(row["bytes"] == 0 for row in events[-2:])
        and last_data == quiet_start
    )
    for key in ("query_attempts", "query_written_bytes", "query_started_monotonic"):
        require_boundary(isinstance(record.get(key), dict)
                         and set(record[key]) == set(PREQUERY_ROLES))
    for role in PREQUERY_ROLES:
        row = record["raw"][role]
        when = record["query_started_monotonic"][role]
        require_boundary(
            isinstance(row, dict) and set(row) == {"path", "sha256", "returned_bytes"}
            and type(row["returned_bytes"]) is int
            and row["returned_bytes"] == len(raw[role]) == offsets[role]
            and len(raw[role]) <= PREQUERY_MAX_BYTES
            and not _prequery_failure_marker(raw[role])
            and type(record["query_attempts"][role]) is int
            and record["query_attempts"][role] == 1
            and type(record["query_written_bytes"][role]) is int
            and record["query_written_bytes"][role] == len(f"{protocol}|READY?\r\n".encode("ascii"))
            and type(when) in (int, float) and math.isfinite(when)
            and quiet_end <= when <= record["finished_monotonic"]
            and when < record["boundary_deadline_monotonic"]
        )


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
    prequery_evidence_path: Path | None = None,
    prequery_evidence_reference: dict[str, str] | None = None,
    peripheral_advertise_fields: str = "status=pass",
) -> PairExecution:
    """! @brief 두 image를 flash하고 peripheral 광고 뒤 central을 시작합니다. """

    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 600.0:
        raise BlePairHilFailure("--result-timeout은 30..600초여야 합니다.")
    if ready_query is not None:
        if (not isinstance(prequery_evidence_path, Path)
                or not isinstance(prequery_evidence_reference, dict)
                or prequery_evidence_reference
                or ready_query != f"{protocol}|READY?\r\n".encode("ascii")):
            raise BlePairHilFailure("READY 질의에는 새 prequery evidence가 필요합니다.")
        metadata_path, raw_paths = _prequery_paths(prequery_evidence_path)
        if any(path.exists() for path in (metadata_path, *raw_paths.values())):
            raise BlePairHilFailure("기존 prequery evidence 덮어쓰기를 거부했습니다.")
    endpoints = (peripheral_endpoint, central_endpoint)
    if any(getattr(endpoint, "transport", None) is not None for endpoint in endpoints):
        kind = validate_endpoint_transports(endpoints)
        if kind == "jlink-swd" and flash_backend != "pyocd-sector":
            raise BlePairHilFailure("J-Link endpoint에는 pyocd-sector만 허용합니다.")
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
                    flashes[role] = flash_image_pyocd_sha256(
                        role,
                        probe_sha256(endpoint.board_id),
                        image,
                        flash_timeout,
                        defer_reset=True,
                    )
                else:
                    flashes[role] = flash_image(
                        flash_label, role, endpoint.volume, image, flash_timeout
                    )
            if flash_backend == "pyocd-sector":
                for role, endpoint in (
                    ("peripheral", peripheral_endpoint),
                    ("central", central_endpoint),
                ):
                    ports[role].reset_input_buffer()
                    reset_mode = reset_target_pyocd_sha256(
                        role,
                        probe_sha256(endpoint.board_id),
                        flash_timeout,
                    )
                    from m33_probe_transport import reset_mode as selected_reset_mode

                    if reset_mode != selected_reset_mode():
                        raise BlePairHilFailure(
                            f"{role} software reset mode가 다릅니다: {reset_mode}"
                        )
                    flashes[role] = ("pyocd-sector-sw-reset", flashes[role][1])
            deadline = time.monotonic() + result_timeout
            if ready_query is not None:
                _query_ready_after_quiet(
                    ports, ready_query, prequery_evidence_path,
                    prequery_evidence_reference, deadline, protocol, nonce, core_revision,
                )
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
                peripheral_advertise_fields,
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

    return public_endpoint(endpoint)


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 장치 탐색 또는 전체 W02 pair gate를 실행합니다. """

    args = parse_arguments(arguments)
    serial_module, list_ports = import_pyserial()
    peripheral_endpoint = discover_endpoint_sha256(
        args.probe_peripheral_sha256,
        args.peripheral_volume,
        args.peripheral_port,
        list_ports,
    )
    central_endpoint = discover_endpoint_sha256(
        args.probe_central_sha256,
        args.central_volume,
        args.central_port,
        list_ports,
    )
    validate_pair_identity(peripheral_endpoint, central_endpoint)
    print(
        "NU54DK M29-W02 pair discovery SUCCESS: "
        f"peripheral={_board(peripheral_endpoint)['probe_sha256'][:12]}/{peripheral_endpoint.port_name}, "
        f"central={_board(central_endpoint)['probe_sha256'][:12]}/{central_endpoint.port_name}"
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
