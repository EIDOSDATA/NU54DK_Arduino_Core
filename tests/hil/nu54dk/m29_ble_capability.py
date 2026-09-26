#!/usr/bin/env python3
"""! @brief M29 ATT/GATT·L2CAP capability protocol과 1보드 HIL을 검증합니다. """

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    RoleEndpoint,
    build_nonce,
    discover_endpoint,
    file_sha256,
    flash_image,
    git_revision,
    read_line,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_source_clean,
)
from m6_serial_echo import import_pyserial  # noqa: E402


MILESTONE = "M29"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m29_ble_capability"
READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "m29-ble-readiness.json"
PROTOCOL_PREFIX = "M29CAP|1|"
PROTOCOL_LINE_COUNT = 14
PROTOCOL_RECORD_COUNT = 11
CAPABILITY_COUNT = 7
MAX_TRANSCRIPT_BYTES = 16384
QUIET_SECONDS = 0.1
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)$", re.ASCII)

HOST_FIELDS = (
    ("bt_max_conn", 2),
    ("gatt_client", 1),
    ("dynamic_db", 1),
    ("read_multiple", 1),
    ("service_changed", 1),
    ("caching", 1),
    ("l2cap_dynamic", 1),
    ("signing", 1),
    ("eatt", 1),
    ("eatt_max", 2),
    ("att_tx_count", 8),
    ("prepare_count", 8),
    ("l2cap_tx_mtu", 512),
    ("l2cap_tx_buffers", 4),
)
CONTRACT_FIELDS = (
    ("client_contexts", 2),
    ("value_bytes", 512),
    ("prepare_per_link", 1),
    ("descriptors", 4),
    ("read_multiple_handles", 4),
    ("coc_channels", 2),
    ("coc_sdu_bytes", 512),
    ("eatt_bearers", 2),
)
CAPABILITY_EXPECTATIONS = (
    ("gatt_long_reliable", "stable", "gatt_registered"),
    ("gatt_read_multiple", "stable", "gatt_registered"),
    ("service_changed", "stable", "gatt_registered"),
    ("robust_caching", "stable", "gatt_registered"),
    ("le_coc", "stable", "server_registered"),
    ("signed_write_legacy", "deprecated", "peer_required"),
    ("eatt_experimental", "experimental", "peer_required"),
)


class M29CapabilityFailure(RuntimeError):
    """! @brief M29 capability 입력·protocol·판정 실패를 나타냅니다. """


@dataclass(frozen=True)
class ExpectedIdentity:
    """! @brief transcript가 반드시 포함해야 하는 exact revision 집합입니다. """

    core: str
    board: str
    ncs: str
    zephyr: str


@dataclass(frozen=True)
class CapabilityResult:
    """! @brief 구조·Host 등록·정책 분류를 모두 통과한 결과입니다. """

    nonce: str
    identity: ExpectedIdentity
    host: dict[str, int]
    l2cap_psm: int
    contract: dict[str, int]
    capabilities: tuple[str, ...]


def _record(line: str, kind: str, field_names: tuple[str, ...]) -> dict[str, str]:
    """! @brief record 종류·필드 순서·중복을 동시에 검사합니다. """

    parts = line.split("|")
    expected_length = 3 + len(field_names)
    if parts[:3] != ["M29CAP", "1", kind] or len(parts) != expected_length:
        raise M29CapabilityFailure(f"{kind} record 형식이 다릅니다: {line!r}")
    fields: dict[str, str] = {}
    for part, expected_name in zip(parts[3:], field_names, strict=True):
        if "=" not in part:
            raise M29CapabilityFailure(f"{kind} field에 '='가 없습니다: {part!r}")
        name, value = part.split("=", 1)
        if name != expected_name or name in fields or value == "":
            raise M29CapabilityFailure(
                f"{kind} field 순서·중복·값이 다릅니다: {part!r}"
            )
        fields[name] = value
    return fields


def _decimal(value: str, name: str, maximum: int = 65535) -> int:
    """! @brief 선행 0 없는 bounded decimal만 정수로 변환합니다. """

    if DECIMAL_PATTERN.fullmatch(value) is None:
        raise M29CapabilityFailure(f"{name} decimal 형식이 다릅니다: {value!r}")
    parsed = int(value)
    if parsed > maximum:
        raise M29CapabilityFailure(f"{name} 값이 범위를 넘습니다: {parsed}")
    return parsed


def _validate_identity(identity: ExpectedIdentity) -> None:
    """! @brief 비교 기준 revision도 full lowercase Git SHA인지 검사합니다. """

    for name, value in asdict(identity).items():
        if REVISION_PATTERN.fullmatch(value) is None:
            raise M29CapabilityFailure(f"expected {name} revision 형식이 다릅니다.")


def _strict_lines(transcript: bytes) -> list[str]:
    """! @brief noise·빈 줄·비 ASCII·과대 transcript를 허용하지 않습니다. """

    if not transcript or len(transcript) > MAX_TRANSCRIPT_BYTES:
        raise M29CapabilityFailure("transcript가 비었거나 크기 상한을 넘었습니다.")
    if not transcript.endswith(b"\n"):
        raise M29CapabilityFailure("transcript 마지막 newline이 없습니다.")
    try:
        lines = [line.decode("ascii") for line in transcript.splitlines()]
    except UnicodeDecodeError as error:
        raise M29CapabilityFailure("transcript에 비 ASCII byte가 있습니다.") from error
    if len(lines) != PROTOCOL_LINE_COUNT or any(not line for line in lines):
        raise M29CapabilityFailure(
            f"protocol line 수 또는 빈 줄이 다릅니다: {len(lines)}"
        )
    if any(not line.startswith(PROTOCOL_PREFIX) for line in lines):
        raise M29CapabilityFailure("protocol 밖 noise line이 있습니다.")
    return lines


def _fixed_values(
    fields: dict[str, str],
    expectations: tuple[tuple[str, int], ...],
    record_name: str,
) -> dict[str, int]:
    """! @brief 고정 정수 필드를 변환하고 기대값과 정확히 대조합니다. """

    values: dict[str, int] = {}
    for name, expected in expectations:
        parsed = _decimal(fields[name], f"{record_name}.{name}")
        if parsed != expected:
            raise M29CapabilityFailure(
                f"{record_name} 고정값이 다릅니다: {name}={parsed}, expected={expected}"
            )
        values[name] = parsed
    return values


def parse_transcript(
    transcript: bytes,
    expected_nonce: str,
    expected_identity: ExpectedIdentity,
) -> CapabilityResult:
    """! @brief M29-CAP-01을 순서·identity·정책까지 fail-closed 검증합니다. """

    nonce = build_nonce(expected_nonce)
    _validate_identity(expected_identity)
    lines = _strict_lines(transcript)
    if lines[0] != f"{PROTOCOL_PREFIX}READY":
        raise M29CapabilityFailure("READY가 없거나 첫 record가 아닙니다.")
    begin = _record(lines[1], "BEGIN", ("nonce",))
    if begin["nonce"] != nonce:
        raise M29CapabilityFailure("BEGIN nonce가 현재 실행과 다릅니다.")

    identity_fields = _record(
        lines[2],
        "IDENTITY",
        ("nonce", "core", "board", "ncs", "zephyr"),
    )
    if identity_fields["nonce"] != nonce:
        raise M29CapabilityFailure("IDENTITY nonce가 현재 실행과 다릅니다.")
    actual_identity = ExpectedIdentity(
        identity_fields["core"],
        identity_fields["board"],
        identity_fields["ncs"],
        identity_fields["zephyr"],
    )
    _validate_identity(actual_identity)
    if actual_identity != expected_identity:
        raise M29CapabilityFailure(
            f"capability image revision이 다릅니다: {actual_identity!r}"
        )

    host_names = ("nonce", *(name for name, _value in HOST_FIELDS))
    host_fields = _record(lines[3], "HOST", host_names)
    if host_fields["nonce"] != nonce:
        raise M29CapabilityFailure("HOST nonce가 현재 실행과 다릅니다.")
    host = _fixed_values(host_fields, HOST_FIELDS, "HOST")

    probe = _record(
        lines[4], "PROBE", ("nonce", "gatt_service", "l2cap_server", "l2cap_psm")
    )
    if probe["nonce"] != nonce:
        raise M29CapabilityFailure("PROBE nonce가 현재 실행과 다릅니다.")
    if _decimal(probe["gatt_service"], "gatt_service", 1) != 1:
        raise M29CapabilityFailure("dynamic GATT service 등록이 성공하지 않았습니다.")
    if _decimal(probe["l2cap_server"], "l2cap_server", 1) != 1:
        raise M29CapabilityFailure("LE CoC server 등록이 성공하지 않았습니다.")
    l2cap_psm = _decimal(probe["l2cap_psm"], "l2cap_psm", 255)
    if not 0x0080 <= l2cap_psm <= 0x00FF:
        raise M29CapabilityFailure(f"동적 LE PSM 범위가 아닙니다: {l2cap_psm}")

    contract_names = ("nonce", *(name for name, _value in CONTRACT_FIELDS))
    contract_fields = _record(lines[5], "CONTRACT", contract_names)
    if contract_fields["nonce"] != nonce:
        raise M29CapabilityFailure("CONTRACT nonce가 현재 실행과 다릅니다.")
    contract = _fixed_values(contract_fields, CONTRACT_FIELDS, "CONTRACT")

    capabilities: list[str] = []
    for line, (identifier, sdk_status, probe_status) in zip(
        lines[6:13], CAPABILITY_EXPECTATIONS, strict=True
    ):
        capability = _record(
            line, "CAP", ("nonce", "id", "sdk", "config", "probe")
        )
        expected = {
            "nonce": nonce,
            "id": identifier,
            "sdk": sdk_status,
            "config": "pass",
            "probe": probe_status,
        }
        if capability != expected:
            raise M29CapabilityFailure(
                f"capability 분류·순서·probe가 다릅니다: {capability!r}"
            )
        capabilities.append(identifier)
    if len(set(capabilities)) != CAPABILITY_COUNT:
        raise M29CapabilityFailure("capability가 중복되거나 누락됐습니다.")

    end = _record(lines[13], "END", ("records", "capabilities", "nonce"))
    if end != {
        "records": str(PROTOCOL_RECORD_COUNT),
        "capabilities": str(CAPABILITY_COUNT),
        "nonce": nonce,
    }:
        raise M29CapabilityFailure("END count 또는 nonce가 다릅니다.")

    return CapabilityResult(
        nonce=nonce,
        identity=actual_identity,
        host=host,
        l2cap_psm=l2cap_psm,
        contract=contract,
        capabilities=tuple(capabilities),
    )


def collect_transcript(
    serial_port: Any,
    nonce: str,
    timeout_seconds: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> bytes:
    """! @brief READY부터 END까지 한 deadline 안에서 수집하고 trailing byte도 거부합니다. """

    nonce = build_nonce(nonce)
    if not 1.0 <= timeout_seconds <= 180.0:
        raise M29CapabilityFailure("M29-CAP-01 timeout은 1..180초여야 합니다.")
    deadline = monotonic() + timeout_seconds
    pending = bytearray()
    capture = bytearray()
    serial_port.reset_input_buffer()
    probe = b"M29CAP|1|PROBE\r\n"
    written = serial_port.write(probe)
    serial_port.flush()
    if written != len(probe):
        raise M29CapabilityFailure("PROBE command가 일부만 기록됐습니다.")
    first = read_line(serial_port, pending, capture, deadline)
    if first != b"M29CAP|1|READY":
        raise M29CapabilityFailure(f"READY 앞 noise 또는 stale record입니다: {first!r}")
    request = f"M29CAP|1|START|nonce={nonce}\r\n".encode("ascii")
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise M29CapabilityFailure("START command가 일부만 기록됐습니다.")

    expected_end = (
        f"M29CAP|1|END|records={PROTOCOL_RECORD_COUNT}|"
        f"capabilities={CAPABILITY_COUNT}|nonce={nonce}"
    ).encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if not line.startswith(PROTOCOL_PREFIX.encode("ascii")):
            raise M29CapabilityFailure(f"protocol 밖 noise line입니다: {line!r}")
        if line.startswith(b"M29CAP|1|FAIL|"):
            raise M29CapabilityFailure(f"target capability 수집 실패입니다: {line!r}")
        if line == expected_end:
            break
    sleeper(QUIET_SECONDS)
    waiting = int(getattr(serial_port, "in_waiting", 0))
    if waiting > 0:
        capture.extend(serial_port.read(waiting))
    if pending or waiting > 0 or len(capture) > MAX_TRANSCRIPT_BYTES:
        raise M29CapabilityFailure("END 뒤 trailing byte가 있거나 transcript가 너무 큽니다.")
    return bytes(capture)


def _expected_identity(core_revision: str, board_revision: str) -> ExpectedIdentity:
    """! @brief Git checkout과 readiness lock에서 HIL 비교 identity를 만듭니다. """

    readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    baseline = readiness["baseline"]
    return ExpectedIdentity(
        core_revision,
        board_revision,
        baseline["ncs_revision"],
        baseline["zephyr_revision"],
    )


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact 보드·image·bounded timeout 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="NU54DK 한 대에서 M29-CAP-01 ATT/GATT·L2CAP capability를 확인합니다."
    )
    parser.add_argument("--hex", required=True)
    parser.add_argument("--board-id", required=True)
    parser.add_argument("--volume")
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument("--result-timeout", type=float, default=180.0)
    parser.add_argument("--evidence")
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def _output_paths(argument: str | None, overwrite: bool) -> tuple[Path, Path]:
    """! @brief 새 JSON과 raw transcript 경로를 fail-closed 준비합니다. """

    if not argument:
        raise M29CapabilityFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    transcript = evidence.with_name(f"{evidence.stem}.transcript.log")
    if evidence.suffix.lower() != ".json":
        raise M29CapabilityFailure("--evidence는 .json 파일이어야 합니다.")
    existing = [path for path in (evidence, transcript) if path.exists()]
    if existing and not overwrite:
        raise M29CapabilityFailure(
            "기존 증적을 덮어쓰지 않습니다: " + ", ".join(map(str, existing))
        )
    for path in existing:
        if not path.is_file():
            raise M29CapabilityFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
        path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, transcript


def _board_record(endpoint: RoleEndpoint) -> dict[str, Any]:
    """! @brief 공개 증적에는 raw UID 대신 hash와 endpoint index만 남깁니다. """

    return {
        "daplink_uid_sha256": hashlib.sha256(
            endpoint.board_id.encode("ascii")
        ).hexdigest(),
        "msd_root": str(endpoint.volume.root),
        "uart_port": endpoint.port_name,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 보드 식별·flash·수집·strict parse·증적 저장을 한 번 수행합니다. """

    args = parse_arguments(arguments)
    if args.baud != DEFAULT_BAUD_RATE:
        raise M29CapabilityFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    serial_module, list_ports = import_pyserial()
    endpoint = discover_endpoint(args.board_id, args.volume, args.port, list_ports)
    print(
        "NU54DK M29 capability discovery SUCCESS: "
        f"board={hashlib.sha256(endpoint.board_id.encode('ascii')).hexdigest()[:12]}/"
        f"{endpoint.port_name}"
    )
    if args.discover_only:
        return 0

    evidence_path, transcript_path = _output_paths(
        args.evidence, args.overwrite_evidence
    )
    image = validate_hex_image(args.hex)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean(MILESTONE, APPLICATION_SOURCE_ROOT, Path(__file__).resolve())
    build_record = validate_build_record(
        image, core_revision, board_revision, APPLICATION_SOURCE_ROOT
    )
    image_size = image.stat().st_size
    image_sha256 = file_sha256(image)
    nonce = build_nonce()

    with ExitStack() as stack:
        serial_port = stack.enter_context(
            serial_module.Serial(
                port=endpoint.port_name,
                baudrate=args.baud,
                bytesize=serial_module.EIGHTBITS,
                parity=serial_module.PARITY_NONE,
                stopbits=serial_module.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=2.0,
            )
        )
        serial_port.reset_input_buffer()
        flash_sequence, flash_bytes = flash_image(
            MILESTONE,
            "capability",
            endpoint.volume,
            image,
            args.flash_timeout,
        )
        transcript = collect_transcript(serial_port, nonce, args.result_timeout)

    validate_image_unchanged(image, image_size, image_sha256)
    result = parse_transcript(
        transcript,
        nonce,
        _expected_identity(core_revision, board_revision),
    )
    transcript_path.write_bytes(transcript)
    evidence = {
        "schema_version": 1,
        "protocol": "M29CAP/1",
        "test_id": "M29-CAP-01",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "identity": asdict(result.identity),
        "nonce": nonce,
        "board": _board_record(endpoint),
        "image": {
            "name": image.name,
            "size": image_size,
            "sha256": image_sha256,
            "build_record": build_record,
            "flash_sequence": flash_sequence,
            "flash_bytes": flash_bytes,
        },
        "transcript": transcript_record(transcript_path, transcript),
        "result": asdict(result),
        "source_capability_status": "candidate-preserved-separately",
        "peer_negotiated_features": {
            "signed_write": "not_run",
            "eatt": "not_run",
        },
        "safety": {
            "external_gpio_wiring_required": False,
            "mass_erase_requested": False,
            "recover_requested": False,
        },
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "NU54DK M29 capability HIL PASS: "
        f"capabilities={len(result.capabilities)};evidence={evidence_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (M29CapabilityFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M29 capability HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
