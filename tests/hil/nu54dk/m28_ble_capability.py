#!/usr/bin/env python3
"""! @brief M28 controller/host capability protocol과 1보드 HIL을 검증합니다. """

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


MILESTONE = "M28"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m28_ble_capability"
READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "m28-ble-readiness.json"
PROTOCOL_PREFIX = "M28CAP|1|"
PROTOCOL_LINE_COUNT = 15
PROTOCOL_RECORD_COUNT = 12
CAPABILITY_COUNT = 6
MAX_TRANSCRIPT_BYTES = 32768
QUIET_SECONDS = 0.1
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
HEX_16_PATTERN = re.compile(r"^[0-9a-f]{16}$", re.ASCII)
HEX_128_PATTERN = re.compile(r"^[0-9a-f]{128}$", re.ASCII)
DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)$", re.ASCII)

HOST_FIELDS = (
    ("bt_max_conn", 2),
    ("peripheral_count", 1),
    ("central_count", 1),
    ("ext_adv", 1),
    ("per_adv", 1),
    ("per_adv_sync", 1),
    ("past_sender", 1),
    ("past_receiver", 1),
    ("pawr_adv", 1),
    ("pawr_sync", 1),
    ("privacy", 1),
    ("settings", 1),
    ("data_len_update", 1),
    ("remote_info", 1),
    ("user_phy_update", 1),
)
CAPABILITY_EVIDENCE = (
    ("multi_role_multi_link", "config+commands"),
    ("extended_advertising_scanning", "le_feature+commands+resource"),
    ("periodic_advertising_sync_past", "le_feature+commands+resource"),
    ("pawr_advertiser_scanner", "le_feature"),
    ("privacy_rpa", "le_feature+commands+resource"),
    ("per_link_control", "le_feature+commands"),
)
COMMAND_REQUIREMENTS = {
    "multi_role_multi_link": ((26, 4), (36, 2)),
    "extended_advertising_scanning": (
        (36, 1),
        (36, 2),
        (36, 3),
        (36, 4),
        (36, 5),
        (36, 6),
        (36, 7),
        (37, 0),
        (37, 1),
        (37, 5),
        (37, 6),
    ),
    "periodic_advertising_sync_past": (
        (37, 2),
        (37, 3),
        (37, 4),
        (38, 0),
        (38, 1),
        (38, 2),
        (38, 3),
        (38, 4),
        (38, 5),
        (38, 6),
        (40, 6),
        (40, 7),
        (41, 0),
        (41, 1),
    ),
    "privacy_rpa": (
        (34, 3),
        (34, 4),
        (34, 5),
        (34, 6),
        (34, 7),
        (35, 0),
        (35, 1),
        (35, 2),
        (39, 2),
    ),
    "per_link_control": (
        (0, 5),
        (27, 2),
        (27, 5),
        (33, 6),
        (35, 3),
        (35, 4),
        (35, 6),
    ),
}
FEATURE_REQUIREMENTS = {
    "extended_advertising_scanning": (12,),
    "periodic_advertising_sync_past": (13, 24, 25),
    "pawr_advertiser_scanner": (43, 44),
    "privacy_rpa": (6,),
    "per_link_control": (5,),
}


class M28CapabilityFailure(RuntimeError):
    """! @brief M28 capability 입력·protocol·판정 실패를 나타냅니다. """


@dataclass(frozen=True)
class ExpectedIdentity:
    """! @brief transcript가 반드시 포함해야 하는 exact revision 집합입니다. """

    core: str
    board: str
    ncs: str
    zephyr: str


@dataclass(frozen=True)
class CapabilityResult:
    """! @brief 구조와 HCI/Host 필수 판정을 모두 통과한 결과입니다. """

    nonce: str
    identity: ExpectedIdentity
    hci_version: int
    hci_revision: int
    manufacturer: int
    lmp_subversion: int
    supported_commands: str
    le_features: str
    maximum_advertising_data_length: int
    advertising_sets: int
    periodic_advertiser_list_size: int
    resolving_list_size: int
    capabilities: tuple[str, ...]


def _record(
    line: str,
    kind: str,
    field_names: tuple[str, ...],
) -> dict[str, str]:
    """! @brief record 종류·필드 순서·중복을 동시에 검사합니다. """

    parts = line.split("|")
    expected_length = 3 + len(field_names)
    if parts[:3] != ["M28CAP", "1", kind] or len(parts) != expected_length:
        raise M28CapabilityFailure(f"{kind} record 형식이 다릅니다: {line!r}")
    fields: dict[str, str] = {}
    for part, expected_name in zip(parts[3:], field_names, strict=True):
        if "=" not in part:
            raise M28CapabilityFailure(f"{kind} field에 '='가 없습니다: {part!r}")
        name, value = part.split("=", 1)
        if name != expected_name or name in fields or value == "":
            raise M28CapabilityFailure(
                f"{kind} field 순서·중복·값이 다릅니다: {part!r}"
            )
        fields[name] = value
    return fields


def _decimal(value: str, name: str, maximum: int = 65535) -> int:
    """! @brief 선행 0 없는 bounded decimal만 정수로 변환합니다. """

    if DECIMAL_PATTERN.fullmatch(value) is None:
        raise M28CapabilityFailure(f"{name} decimal 형식이 다릅니다: {value!r}")
    parsed = int(value)
    if parsed > maximum:
        raise M28CapabilityFailure(f"{name} 값이 범위를 넘습니다: {parsed}")
    return parsed


def _validate_identity(identity: ExpectedIdentity) -> None:
    """! @brief 비교 기준 revision도 full lowercase Git SHA인지 검사합니다. """

    for name, value in asdict(identity).items():
        if REVISION_PATTERN.fullmatch(value) is None:
            raise M28CapabilityFailure(f"expected {name} revision 형식이 다릅니다.")


def _command_supported(commands: bytes, octet: int, bit: int) -> bool:
    """! @brief Read Supported Commands의 지정 bit를 검사합니다. """

    return (commands[octet] & (1 << bit)) != 0


def _feature_supported(features: bytes, bit: int) -> bool:
    """! @brief LE Local Supported Features의 지정 bit를 검사합니다. """

    return (features[bit >> 3] & (1 << (bit & 7))) != 0


def _controller_results(
    commands: bytes,
    features: bytes,
    resources: dict[str, int],
) -> dict[str, bool]:
    """! @brief raw HCI bit와 자원 값을 6개 기능군 판정으로 변환합니다. """

    results: dict[str, bool] = {}
    for identifier, _evidence in CAPABILITY_EVIDENCE:
        command_pass = all(
            _command_supported(commands, octet, bit)
            for octet, bit in COMMAND_REQUIREMENTS.get(identifier, ())
        )
        feature_pass = all(
            _feature_supported(features, bit)
            for bit in FEATURE_REQUIREMENTS.get(identifier, ())
        )
        results[identifier] = command_pass and feature_pass
    results["extended_advertising_scanning"] &= (
        resources["max_adv_data_len"] >= 255 and resources["adv_sets"] >= 1
    )
    results["periodic_advertising_sync_past"] &= resources["per_adv_list"] >= 1
    results["privacy_rpa"] &= resources["resolving_list"] >= 1
    return results


def _strict_lines(transcript: bytes) -> list[str]:
    """! @brief noise·빈 줄·비 ASCII·과대 transcript를 허용하지 않습니다. """

    if not transcript or len(transcript) > MAX_TRANSCRIPT_BYTES:
        raise M28CapabilityFailure("transcript가 비었거나 크기 상한을 넘었습니다.")
    if not transcript.endswith(b"\n"):
        raise M28CapabilityFailure("transcript 마지막 newline이 없습니다.")
    try:
        lines = [line.decode("ascii") for line in transcript.splitlines()]
    except UnicodeDecodeError as error:
        raise M28CapabilityFailure("transcript에 비 ASCII byte가 있습니다.") from error
    if len(lines) != PROTOCOL_LINE_COUNT or any(not line for line in lines):
        raise M28CapabilityFailure(
            f"protocol line 수 또는 빈 줄이 다릅니다: {len(lines)}"
        )
    if any(not line.startswith(PROTOCOL_PREFIX) for line in lines):
        raise M28CapabilityFailure("protocol 밖 noise line이 있습니다.")
    return lines


def parse_transcript(
    transcript: bytes,
    expected_nonce: str,
    expected_identity: ExpectedIdentity,
) -> CapabilityResult:
    """! @brief M28-CAP-01 transcript를 순서·identity·HCI 결과까지 fail-closed 검증합니다. """

    nonce = build_nonce(expected_nonce)
    _validate_identity(expected_identity)
    lines = _strict_lines(transcript)
    if lines[0] != f"{PROTOCOL_PREFIX}READY":
        raise M28CapabilityFailure("READY가 없거나 첫 record가 아닙니다.")
    begin = _record(lines[1], "BEGIN", ("nonce",))
    if begin["nonce"] != nonce:
        raise M28CapabilityFailure("BEGIN nonce가 현재 실행과 다릅니다.")

    identity_fields = _record(
        lines[2],
        "IDENTITY",
        ("nonce", "core", "board", "ncs", "zephyr"),
    )
    if identity_fields["nonce"] != nonce:
        raise M28CapabilityFailure("IDENTITY nonce가 현재 실행과 다릅니다.")
    actual_identity = ExpectedIdentity(
        identity_fields["core"],
        identity_fields["board"],
        identity_fields["ncs"],
        identity_fields["zephyr"],
    )
    _validate_identity(actual_identity)
    if actual_identity != expected_identity:
        raise M28CapabilityFailure(
            f"capability image revision이 다릅니다: {actual_identity!r}"
        )

    host_names = ("nonce", *(name for name, _value in HOST_FIELDS))
    host = _record(lines[3], "HOST", host_names)
    if host["nonce"] != nonce:
        raise M28CapabilityFailure("HOST nonce가 현재 실행과 다릅니다.")
    for name, expected in HOST_FIELDS:
        if _decimal(host[name], name, 250) != expected:
            raise M28CapabilityFailure(
                f"필수 Host 구성이 꺼졌거나 값이 다릅니다: {name}={host[name]}"
            )

    version = _record(
        lines[4],
        "HCI_VERSION",
        ("nonce", "hci_version", "hci_revision", "manufacturer", "lmp_subversion"),
    )
    if version["nonce"] != nonce:
        raise M28CapabilityFailure("HCI_VERSION nonce가 현재 실행과 다릅니다.")
    version_values = {
        name: _decimal(version[name], name, 65535)
        for name in ("hci_version", "hci_revision", "manufacturer", "lmp_subversion")
    }
    if version_values["hci_version"] > 255:
        raise M28CapabilityFailure("HCI version이 uint8 범위를 넘습니다.")

    command_record = _record(lines[5], "HCI_COMMANDS", ("nonce", "commands"))
    feature_record = _record(lines[6], "LE_FEATURES", ("nonce", "features"))
    if command_record["nonce"] != nonce or feature_record["nonce"] != nonce:
        raise M28CapabilityFailure("raw HCI record nonce가 현재 실행과 다릅니다.")
    if HEX_128_PATTERN.fullmatch(command_record["commands"]) is None:
        raise M28CapabilityFailure("Read Supported Commands는 64-byte lowercase hex여야 합니다.")
    if HEX_16_PATTERN.fullmatch(feature_record["features"]) is None:
        raise M28CapabilityFailure("LE Local Supported Features는 8-byte lowercase hex여야 합니다.")
    command_bytes = bytes.fromhex(command_record["commands"])
    feature_bytes = bytes.fromhex(feature_record["features"])

    resource_record = _record(
        lines[7],
        "RESOURCES",
        ("nonce", "max_adv_data_len", "adv_sets", "per_adv_list", "resolving_list"),
    )
    if resource_record["nonce"] != nonce:
        raise M28CapabilityFailure("RESOURCES nonce가 현재 실행과 다릅니다.")
    resources = {
        "max_adv_data_len": _decimal(
            resource_record["max_adv_data_len"], "max_adv_data_len", 65535
        ),
        "adv_sets": _decimal(resource_record["adv_sets"], "adv_sets", 255),
        "per_adv_list": _decimal(
            resource_record["per_adv_list"], "per_adv_list", 255
        ),
        "resolving_list": _decimal(
            resource_record["resolving_list"], "resolving_list", 255
        ),
    }
    controller = _controller_results(command_bytes, feature_bytes, resources)

    capabilities: list[str] = []
    for line, (identifier, evidence) in zip(
        lines[8:14], CAPABILITY_EVIDENCE, strict=True
    ):
        capability = _record(
            line,
            "CAP",
            ("nonce", "id", "host", "controller", "evidence"),
        )
        if capability != {
            "nonce": nonce,
            "id": identifier,
            "host": "pass",
            "controller": "pass" if controller[identifier] else "fail",
            "evidence": evidence,
        }:
            raise M28CapabilityFailure(
                f"capability record가 raw HCI/Host 판정과 다릅니다: {identifier}"
            )
        if not controller[identifier]:
            raise M28CapabilityFailure(f"필수 controller capability가 없습니다: {identifier}")
        capabilities.append(identifier)

    end = _record(lines[14], "END", ("records", "capabilities", "nonce"))
    if end != {
        "records": str(PROTOCOL_RECORD_COUNT),
        "capabilities": str(CAPABILITY_COUNT),
        "nonce": nonce,
    }:
        raise M28CapabilityFailure("END count 또는 nonce가 다릅니다.")
    if len(set(capabilities)) != CAPABILITY_COUNT:
        raise M28CapabilityFailure("capability가 중복되거나 누락됐습니다.")

    return CapabilityResult(
        nonce=nonce,
        identity=actual_identity,
        hci_version=version_values["hci_version"],
        hci_revision=version_values["hci_revision"],
        manufacturer=version_values["manufacturer"],
        lmp_subversion=version_values["lmp_subversion"],
        supported_commands=command_record["commands"],
        le_features=feature_record["features"],
        maximum_advertising_data_length=resources["max_adv_data_len"],
        advertising_sets=resources["adv_sets"],
        periodic_advertiser_list_size=resources["per_adv_list"],
        resolving_list_size=resources["resolving_list"],
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
        raise M28CapabilityFailure("M28-CAP-01 timeout은 1..180초여야 합니다.")
    deadline = monotonic() + timeout_seconds
    pending = bytearray()
    capture = bytearray()
    serial_port.reset_input_buffer()
    probe = b"M28CAP|1|PROBE\r\n"
    written = serial_port.write(probe)
    serial_port.flush()
    if written != len(probe):
        raise M28CapabilityFailure("PROBE command가 일부만 기록됐습니다.")
    first = read_line(serial_port, pending, capture, deadline)
    if first != b"M28CAP|1|READY":
        raise M28CapabilityFailure(f"READY 앞 noise 또는 stale record입니다: {first!r}")
    request = f"M28CAP|1|START|nonce={nonce}\r\n".encode("ascii")
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise M28CapabilityFailure("START command가 일부만 기록됐습니다.")

    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if not line.startswith(PROTOCOL_PREFIX.encode("ascii")):
            raise M28CapabilityFailure(f"protocol 밖 noise line입니다: {line!r}")
        if line.startswith(b"M28CAP|1|FAIL|"):
            raise M28CapabilityFailure(f"target capability 수집 실패입니다: {line!r}")
        if line == f"M28CAP|1|END|records=12|capabilities=6|nonce={nonce}".encode(
            "ascii"
        ):
            break
    sleeper(QUIET_SECONDS)
    waiting = int(getattr(serial_port, "in_waiting", 0))
    if waiting > 0:
        capture.extend(serial_port.read(waiting))
    if pending or waiting > 0 or len(capture) > MAX_TRANSCRIPT_BYTES:
        raise M28CapabilityFailure("END 뒤 trailing byte가 있거나 transcript가 너무 큽니다.")
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
        description="NU54DK 한 대에서 M28-CAP-01 controller/host capability를 조회합니다."
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
        raise M28CapabilityFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    transcript = evidence.with_name(f"{evidence.stem}.transcript.log")
    if evidence.suffix.lower() != ".json":
        raise M28CapabilityFailure("--evidence는 .json 파일이어야 합니다.")
    existing = [path for path in (evidence, transcript) if path.exists()]
    if existing and not overwrite:
        raise M28CapabilityFailure(
            "기존 증적을 덮어쓰지 않습니다: " + ", ".join(map(str, existing))
        )
    for path in existing:
        if not path.is_file():
            raise M28CapabilityFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
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
        raise M28CapabilityFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    serial_module, list_ports = import_pyserial()
    endpoint = discover_endpoint(args.board_id, args.volume, args.port, list_ports)
    print(
        "NU54DK M28 capability discovery SUCCESS: "
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
        transcript = collect_transcript(
            serial_port, nonce, args.result_timeout
        )

    validate_image_unchanged(image, image_size, image_sha256)
    result = parse_transcript(
        transcript,
        nonce,
        _expected_identity(core_revision, board_revision),
    )
    transcript_path.write_bytes(transcript)
    evidence = {
        "schema_version": 1,
        "protocol": "M28CAP/1",
        "test_id": "M28-CAP-01",
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
        "runtime_hci_status": "passed",
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
        "NU54DK M28 capability HIL PASS: "
        f"capabilities={len(result.capabilities)};evidence={evidence_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (M28CapabilityFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M28 capability HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
