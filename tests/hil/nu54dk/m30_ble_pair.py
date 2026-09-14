#!/usr/bin/env python3
"""! @brief M30-PAIR-01의 5 IO capability x 10회 두 보드 HIL을 실행합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Sequence


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
    flash_image_pyocd,
    git_revision,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_pair_identity,
    validate_source_clean,
)
from m6_serial_echo import import_pyserial  # noqa: E402


MILESTONE = "M30"
APPLICATION_ROOT = REPOSITORY / "tests" / "zephyr" / "m30_ble_pair_hil"
RUNNER_PATH = Path(__file__).resolve()
BOARD_DIRECTORY = "nrf54l15dk_nrf54l15_cpuapp_nu54dk"
TOOLCHAIN_DIRECTORY = "zephyr_gnu"
TEST_DIRECTORY = "m30_ble_pair_hil"
PROTOCOL_PREFIX = b"M30PAIR|1|"
FAIL_PREFIX = b"M30PAIR|1|FAIL|"
ROUNDS_PER_CAPABILITY = 10
CAPABILITY_COUNT = 5
MAX_TRANSCRIPT_BYTES = 262144
PASSKEY_PATTERN = re.compile(rb"\|value=([0-9]{6})$")
DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)$")


class M30PairFailure(RuntimeError):
    """! @brief M30-PAIR-01 장치·image·protocol·증적 실패입니다. """


@dataclass(frozen=True)
class CapabilityCase:
    """! @brief 한 IO 조합의 image와 기대 association method입니다. """

    slug: str
    case_name: str
    peripheral_io: int
    central_io: int
    method: str


CASES = (
    CapabilityCase("no_io", "no_input_output", 0, 0, "just_works"),
    CapabilityCase("display_keyboard", "display_keyboard", 1, 2, "passkey_entry"),
    CapabilityCase("keyboard_display", "keyboard_display", 2, 1, "passkey_entry"),
    CapabilityCase("yes_no", "display_yes_no", 3, 3, "numeric_comparison"),
    CapabilityCase(
        "keyboard_display_full",
        "keyboard_display_full",
        4,
        4,
        "numeric_comparison",
    ),
)

SCENARIO_CODES = {
    "no_io": "ni",
    "display_keyboard": "dk",
    "keyboard_display": "kd",
    "yes_no": "yn",
    "keyboard_display_full": "kdf",
}


@dataclass(frozen=True)
class ImageInput:
    """! @brief 한 role image의 immutable byte·build record identity입니다. """

    path: Path
    size: int
    sha256: str
    build_record: dict[str, str]


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact build root·두 endpoint·bounded timeout을 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M30-PAIR-01의 5 IO capability를 각각 10회 실제 검증합니다."
    )
    parser.add_argument("--build-outdir", required=True)
    parser.add_argument("--peripheral-board-id", required=True)
    parser.add_argument("--central-board-id", required=True)
    parser.add_argument("--peripheral-volume")
    parser.add_argument("--central-volume")
    parser.add_argument("--peripheral-port", default="auto")
    parser.add_argument("--central-port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=90.0)
    parser.add_argument("--result-timeout", type=float, default=600.0)
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--evidence")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def scenario_name(case: CapabilityCase, role: str) -> str:
    """! @brief Windows 경로 한계를 피하는 짧은 Twister 이름을 결정합니다. """

    role_code = {"peripheral": "p", "central": "c"}.get(role)
    if role_code is None:
        raise M30PairFailure(f"지원하지 않는 role입니다: {role}")
    return f"nucode.m30.pair.{SCENARIO_CODES[case.slug]}.{role_code}"


def image_path(build_outdir: Path, case: CapabilityCase, role: str) -> Path:
    """! @brief canonical Twister output에서 role HEX 경로를 계산합니다. """

    return (
        build_outdir
        / BOARD_DIRECTORY
        / TOOLCHAIN_DIRECTORY
        / scenario_name(case, role)
        / TEST_DIRECTORY
        / "zephyr"
        / "zephyr.hex"
    )


def collect_images(
    build_outdir: Path, core_revision: str, board_revision: str
) -> dict[tuple[str, str], ImageInput]:
    """! @brief 10개 image를 exact source·revision·byte와 결합합니다. """

    images: dict[tuple[str, str], ImageInput] = {}
    for case in CASES:
        for role in ("peripheral", "central"):
            path = validate_hex_image(str(image_path(build_outdir, case, role)))
            try:
                path.relative_to(build_outdir)
            except ValueError as error:
                raise M30PairFailure("HEX가 지정 build outdir 밖에 있습니다.") from error
            size = path.stat().st_size
            digest = file_sha256(path)
            record = validate_build_record(
                path, core_revision, board_revision, APPLICATION_ROOT
            )
            images[(case.slug, role)] = ImageInput(path, size, digest, record)
    return images


def output_paths(argument: str | None, overwrite: bool) -> tuple[Path, Path, Path]:
    """! @brief 신규 JSON과 두 sanitized transcript 경로를 준비합니다. """

    if not argument:
        raise M30PairFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise M30PairFailure("--evidence는 .json 파일이어야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise M30PairFailure("기존 M30-PAIR-01 증적을 덮어쓰지 않습니다.")
    for path in existing:
        if not path.is_file():
            raise M30PairFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
        path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return paths


def read_wire_line(serial_port: Any, pending: bytearray, deadline: float) -> bytes:
    """! @brief passkey를 기록하지 않고 wire에서 완전한 한 줄만 반환합니다. """

    while time.monotonic() < deadline:
        newline = pending.find(b"\n")
        if newline >= 0:
            line = bytes(pending[:newline]).rstrip(b"\r")
            del pending[: newline + 1]
            return line
        waiting = int(getattr(serial_port, "in_waiting", 0))
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            pending.extend(chunk)
            if len(pending) > 16384:
                raise M30PairFailure("미완성 UART line이 허용 크기를 넘었습니다.")
    raise M30PairFailure("M30-PAIR-01 UART token timeout")


def capture_sanitized(capture: bytearray, line: bytes) -> None:
    """! @brief 표시 passkey를 evidence에 남기지 않고 protocol line을 보존합니다. """

    sanitized = PASSKEY_PATTERN.sub(b"|value=<redacted>", line)
    capture.extend(sanitized + b"\n")
    if len(capture) > MAX_TRANSCRIPT_BYTES:
        raise M30PairFailure("sanitized transcript가 허용 크기를 넘었습니다.")


def parse_fields(line: bytes, kind: str) -> dict[str, str]:
    """! @brief 고정 prefix 뒤 key=value field를 중복 없이 파싱합니다. """

    prefix = f"M30PAIR|1|{kind}|".encode("ascii")
    if not line.startswith(prefix):
        raise M30PairFailure(f"{kind} record가 아닙니다: {line!r}")
    fields: dict[str, str] = {}
    for part in line[len(prefix) :].split(b"|"):
        if part.count(b"=") != 1:
            raise M30PairFailure(f"field 형식이 잘못됐습니다: {line!r}")
        key_bytes, value_bytes = part.split(b"=", 1)
        try:
            key = key_bytes.decode("ascii")
            value = value_bytes.decode("ascii")
        except UnicodeDecodeError as error:
            raise M30PairFailure("protocol field가 ASCII가 아닙니다.") from error
        if not key or key in fields:
            raise M30PairFailure("protocol field가 비었거나 중복됐습니다.")
        fields[key] = value
    return fields


def send_command(
    serial_port: Any,
    verb: str,
    round_index: int,
    nonce: str,
    argument: str | None = None,
) -> None:
    """! @brief 완전한 ASCII command를 한 번에 기록합니다. """

    suffix = "" if argument is None else f"|{argument}"
    command = f"M30PAIR|1|{verb}|{round_index}|{nonce}{suffix}\r\n".encode(
        "ascii"
    )
    if serial_port.write(command) != len(command):
        raise M30PairFailure(f"{verb} command가 일부만 기록됐습니다.")
    serial_port.flush()


def wait_expected(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    expected: bytes,
    *,
    allow_boot_noise: bool = False,
) -> None:
    """! @brief exact token 전의 protocol noise와 target FAIL을 거부합니다. """

    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line == expected:
            capture_sanitized(capture, line)
            return
        if line.startswith(FAIL_PREFIX):
            capture_sanitized(capture, line)
            raise M30PairFailure(f"target 실패: {line!r}")
        if line.startswith(PROTOCOL_PREFIX) or not allow_boot_noise:
            capture_sanitized(capture, line)
            raise M30PairFailure(f"예상 밖 protocol line입니다: {line!r}")


def ready_line(case: CapabilityCase, role: str) -> bytes:
    """! @brief role image의 exact READY line을 생성합니다. """

    io_value = case.peripheral_io if role == "peripheral" else case.central_io
    return (
        f"M30PAIR|1|READY|role={role}|case={case.case_name}|"
        f"io={io_value}|bond_count="
    ).encode("ascii")


def wait_ready(
    serial_port: Any,
    case: CapabilityCase,
    role: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    """! @brief flash 뒤 현재 case의 READY와 bounded bond count를 검증합니다. """

    prefix = ready_line(case, role)
    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line.startswith(FAIL_PREFIX):
            capture_sanitized(capture, line)
            raise M30PairFailure(f"{role} setup 실패: {line!r}")
        if line.startswith(prefix):
            count = line[len(prefix) :].decode("ascii", errors="strict")
            if DECIMAL_PATTERN.fullmatch(count) is None or int(count) > 4:
                raise M30PairFailure("READY bond_count가 잘못됐습니다.")
            capture_sanitized(capture, line)
            return
        if line.startswith(PROTOCOL_PREFIX):
            capture_sanitized(capture, line)
            raise M30PairFailure(f"stale READY protocol입니다: {line!r}")


def validate_common_fields(
    fields: dict[str, str], case: CapabilityCase, role: str, round_index: int, nonce: str
) -> None:
    """! @brief 모든 round record의 role·case·round·nonce를 검증합니다. """

    for key, expected in (
        ("role", role),
        ("case", case.case_name),
        ("round", str(round_index)),
        ("nonce", nonce),
    ):
        if fields.get(key) != expected:
            raise M30PairFailure(f"{key} 불일치: {fields!r}")


def collect_round(
    ports: dict[str, Any],
    pending: dict[str, bytearray],
    captures: dict[str, bytearray],
    case: CapabilityCase,
    round_index: int,
    nonce: str,
    deadline: float,
) -> None:
    """! @brief 양쪽 PASS까지 passkey 사용자 I/O를 메모리에서만 중계합니다. """

    passed: set[str] = set()
    input_role: str | None = None
    displayed_passkey: str | None = None
    key_sent = False
    next_role = 0
    roles = ("peripheral", "central")
    while len(passed) != 2:
        role = roles[next_role]
        next_role = (next_role + 1) % len(roles)
        serial_port = ports[role]
        if int(getattr(serial_port, "in_waiting", 0)) == 0:
            if time.monotonic() >= deadline:
                raise M30PairFailure("pairing PASS deadline이 끝났습니다.")
            time.sleep(0.002)
            continue
        line = read_wire_line(serial_port, pending[role], deadline)
        capture_sanitized(captures[role], line)
        if not line.startswith(PROTOCOL_PREFIX):
            raise M30PairFailure(f"protocol 밖 UART line입니다: {line!r}")
        if line.startswith(FAIL_PREFIX):
            raise M30PairFailure(f"{role} target 실패: {line!r}")
        kind = line.split(b"|", 4)[2].decode("ascii", errors="strict")
        fields = parse_fields(line, kind)
        validate_common_fields(fields, case, role, round_index, nonce)
        if kind == "DISPLAY":
            if displayed_passkey is not None or PASSKEY_PATTERN.search(line) is None:
                raise M30PairFailure("표시 passkey가 누락되거나 중복됐습니다.")
            displayed_passkey = PASSKEY_PATTERN.search(line).group(1).decode("ascii")
        elif kind == "INPUT":
            if input_role is not None:
                raise M30PairFailure("passkey input 요청이 중복됐습니다.")
            input_role = role
        elif kind == "PASS":
            expected = {
                "role": role,
                "case": case.case_name,
                "round": str(round_index),
                "method": case.method,
                "level": "4",
                "key_size": "16",
                "paired": "1",
                "unexpected_auth_failures": "0",
                "nonce": nonce,
            }
            if fields != expected or role in passed:
                raise M30PairFailure(f"PASS field가 다르거나 중복됐습니다: {fields!r}")
            passed.add(role)
        else:
            raise M30PairFailure(f"round 중 예상하지 않은 record입니다: {kind}")
        if displayed_passkey is not None and input_role is not None and not key_sent:
            send_command(
                ports[input_role], "KEY", round_index, nonce, displayed_passkey
            )
            key_sent = True
    if case.method == "passkey_entry" and not key_sent:
        raise M30PairFailure("passkey entry case에서 사용자 I/O 중계가 없었습니다.")
    if case.method != "passkey_entry" and (
        displayed_passkey is not None or input_role is not None
    ):
        raise M30PairFailure("예상 method 밖 passkey entry event가 발생했습니다.")


def execute_case(
    serial_module: Any,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    images: dict[tuple[str, str], ImageInput],
    case: CapabilityCase,
    baud: int,
    flash_timeout: float,
    deadline: float,
    captures: dict[str, bytearray],
) -> list[dict[str, Any]]:
    """! @brief 한 capability image pair를 flash하고 10회 pairing합니다. """

    if baud != DEFAULT_BAUD_RATE:
        raise M30PairFailure(f"M30-PAIR-01은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    endpoints = {"peripheral": peripheral_endpoint, "central": central_endpoint}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            role: executor.submit(
                flash_image_pyocd,
                role,
                endpoints[role].board_id,
                images[(case.slug, role)].path,
                flash_timeout,
            )
            for role in endpoints
        }
        flash_results = {role: future.result() for role, future in futures.items()}
    time.sleep(0.5)

    pending = {"peripheral": bytearray(), "central": bytearray()}
    with ExitStack() as stack:
        ports = {
            role: stack.enter_context(
                serial_module.Serial(
                    endpoints[role].port_name,
                    baudrate=baud,
                    timeout=0.05,
                    write_timeout=2.0,
                )
            )
            for role in endpoints
        }
        for port in ports.values():
            port.reset_input_buffer()
        for role in ("peripheral", "central"):
            wait_ready(ports[role], case, role, pending[role], captures[role], deadline)

        results: list[dict[str, Any]] = []
        for round_index in range(1, ROUNDS_PER_CAPABILITY + 1):
            nonce = build_nonce()
            for role in ("peripheral", "central"):
                send_command(ports[role], "CLEAR", round_index, nonce)
            for role in ("peripheral", "central"):
                expected = (
                    f"M30PAIR|1|CLEARED|role={role}|case={case.case_name}|"
                    f"round={round_index}|bond_count=0|nonce={nonce}"
                ).encode("ascii")
                wait_expected(
                    ports[role], pending[role], captures[role], deadline, expected
                )
            time.sleep(0.75)
            send_command(ports["peripheral"], "START", round_index, nonce)
            peripheral_started = (
                f"M30PAIR|1|STARTED|role=peripheral|case={case.case_name}|"
                f"round={round_index}|io={case.peripheral_io}|nonce={nonce}"
            ).encode("ascii")
            wait_expected(
                ports["peripheral"],
                pending["peripheral"],
                captures["peripheral"],
                deadline,
                peripheral_started,
            )
            send_command(ports["central"], "START", round_index, nonce)
            central_started = (
                f"M30PAIR|1|STARTED|role=central|case={case.case_name}|"
                f"round={round_index}|io={case.central_io}|nonce={nonce}"
            ).encode("ascii")
            wait_expected(
                ports["central"],
                pending["central"],
                captures["central"],
                deadline,
                central_started,
            )
            collect_round(ports, pending, captures, case, round_index, nonce, deadline)
            results.append(
                {
                    "round": round_index,
                    "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
                    "method": case.method,
                    "security_level": 4,
                    "key_size": 16,
                    "unexpected_auth_failures": 0,
                }
            )
            print(
                f"M30_PAIR_PROGRESS case={case.case_name} "
                f"round={round_index}/{ROUNDS_PER_CAPABILITY}"
            )

    for role in ("peripheral", "central"):
        image = images[(case.slug, role)]
        validate_image_unchanged(image.path, image.size, image.sha256)
        results[0][f"{role}_flash_sequence"] = flash_results[role][0]
        results[0][f"{role}_flash_bytes"] = flash_results[role][1]
    return results


def image_evidence(image: ImageInput) -> dict[str, Any]:
    """! @brief HEX의 경로 비의존 byte·build record identity를 반환합니다. """

    return {
        "name": image.path.name,
        "size": image.size,
        "sha256": image.sha256,
        "build_record": image.build_record,
    }


def endpoint_evidence(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief raw UID를 공개하지 않고 endpoint exact identity를 기록합니다. """

    return {
        "board_id_sha256": hashlib.sha256(endpoint.board_id.encode("ascii")).hexdigest(),
        "volume": endpoint.volume.root.name,
        "port": endpoint.port_name,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief preflight 또는 50회 실제 pairing과 증적 기록을 실행합니다. """

    args = parse_arguments(arguments)
    if not 30.0 <= args.result_timeout <= 600.0:
        raise M30PairFailure("--result-timeout은 30..600초여야 합니다.")
    serial_module = import_pyserial()
    peripheral = discover_endpoint(
        args.peripheral_board_id,
        args.peripheral_volume,
        args.peripheral_port,
        serial_module.tools.list_ports,
    )
    central = discover_endpoint(
        args.central_board_id,
        args.central_volume,
        args.central_port,
        serial_module.tools.list_ports,
    )
    validate_pair_identity(peripheral, central)
    if args.discover_only:
        print("M30_PAIR_DISCOVERY_PASS=2")
        return 0

    validate_source_clean(MILESTONE, APPLICATION_ROOT, RUNNER_PATH)
    core_revision = git_revision(REPOSITORY)
    if args.expected_core_revision and args.expected_core_revision != core_revision:
        raise M30PairFailure("현재 Core revision이 --expected-core-revision과 다릅니다.")
    board_revision = validate_board_revision(REPOSITORY, BOARD_ROOT)
    build_outdir = Path(args.build_outdir).resolve()
    if not build_outdir.is_dir():
        raise M30PairFailure("--build-outdir가 directory가 아닙니다.")
    images = collect_images(build_outdir, core_revision, board_revision)
    evidence_path, peripheral_path, central_path = output_paths(
        args.evidence, args.overwrite_evidence
    )
    captures = {"peripheral": bytearray(), "central": bytearray()}
    started = time.monotonic()
    deadline = started + args.result_timeout
    case_results: list[dict[str, Any]] = []
    for case in CASES:
        rounds = execute_case(
            serial_module,
            peripheral,
            central,
            images,
            case,
            args.baud,
            args.flash_timeout,
            deadline,
            captures,
        )
        case_results.append(
            {
                "case": case.case_name,
                "peripheral_io": case.peripheral_io,
                "central_io": case.central_io,
                "method": case.method,
                "rounds": rounds,
                "images": {
                    role: image_evidence(images[(case.slug, role)])
                    for role in ("peripheral", "central")
                },
            }
        )

    peripheral_path.write_bytes(bytes(captures["peripheral"]))
    central_path.write_bytes(bytes(captures["central"]))
    evidence = {
        "schema_version": 1,
        "test_id": "M30-PAIR-01",
        "status": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "ncs_revision": "99553055607b2e9885fbc80ccd11fa9da81c2df0",
        "zephyr_revision": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
        "boards": 2,
        "endpoints": {
            "peripheral": endpoint_evidence(peripheral),
            "central": endpoint_evidence(central),
        },
        "flash_backend": "pyocd-sector",
        "io_capabilities": CAPABILITY_COUNT,
        "rounds_per_capability": ROUNDS_PER_CAPABILITY,
        "total_pairings": CAPABILITY_COUNT * ROUNDS_PER_CAPABILITY,
        "unexpected_auth_failures": 0,
        "passkey_evidence_policy": "redacted",
        "cases": case_results,
        "transcripts": {
            "peripheral": transcript_record(
                peripheral_path, bytes(captures["peripheral"])
            ),
            "central": transcript_record(central_path, bytes(captures["central"])),
        },
        "duration_seconds": round(time.monotonic() - started, 3),
        "power_cut_injected": False,
        "mass_erase_or_recover": False,
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "M30_PAIR_HIL_PASS=50;IO_CAPABILITIES=5;ROUNDS_PER_CAPABILITY=10;"
        "UNEXPECTED_AUTH_FAILURES=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (M30PairFailure, OSError, ValueError) as error:
        print(f"M30_PAIR_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
