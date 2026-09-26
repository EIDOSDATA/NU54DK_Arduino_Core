#!/usr/bin/env python3
"""! @brief M30-OOB-01 유선 SC OOB 20회와 mismatch 거부 HIL을 실행합니다. """

from __future__ import annotations

import argparse
import binascii
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
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m30_ble_oob_hil"
RUNNER_PATH = Path(__file__).resolve()
BOARD_DIRECTORY = "nrf54l15dk_nrf54l15_cpuapp_nu54dk"
TOOLCHAIN_DIRECTORY = "zephyr_gnu"
TEST_DIRECTORY = "m30_ble_oob_hil"
PROTOCOL_PREFIX = b"M30OOB|1|"
FAIL_PREFIX = b"M30OOB|1|FAIL|"
ROUNDS = 20
FRAME_BYTES = 74
FRAME_HEX_CHARACTERS = FRAME_BYTES * 2
MAX_TRANSCRIPT_BYTES = 131072
DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)$")
FRAME_PATTERN = re.compile(rb"\|frame=([0-9a-f]{148})\|")


class M30OobFailure(RuntimeError):
    """! @brief M30-OOB-01 장치·image·protocol·증적 실패입니다. """


@dataclass(frozen=True)
class ImageInput:
    """! @brief 한 role image의 immutable byte와 build identity입니다. """

    path: Path
    size: int
    sha256: str
    build_record: dict[str, str]


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact build root·두 endpoint·bounded timeout을 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M30-OOB-01 유선 SC OOB를 두 NU54DK에서 20회 검증합니다."
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


def scenario_name(role: str) -> str:
    """! @brief role별 canonical Twister scenario를 반환합니다. """

    code = {"peripheral": "p", "central": "c"}.get(role)
    if code is None:
        raise M30OobFailure(f"지원하지 않는 role입니다: {role}")
    return f"nucode.m30.oob.{code}"


def image_path(build_outdir: Path, role: str) -> Path:
    """! @brief canonical Twister output에서 role HEX를 계산합니다. """

    return (
        build_outdir
        / BOARD_DIRECTORY
        / TOOLCHAIN_DIRECTORY
        / scenario_name(role)
        / TEST_DIRECTORY
        / "zephyr/zephyr.hex"
    )


def collect_images(
    build_outdir: Path, core_revision: str, board_revision: str
) -> dict[str, ImageInput]:
    """! @brief 두 image를 exact source·revision·byte와 결합합니다. """

    images: dict[str, ImageInput] = {}
    for role in ("peripheral", "central"):
        path = validate_hex_image(str(image_path(build_outdir, role)))
        try:
            path.relative_to(build_outdir)
        except ValueError as error:
            raise M30OobFailure("HEX가 지정 build outdir 밖에 있습니다.") from error
        images[role] = ImageInput(
            path,
            path.stat().st_size,
            file_sha256(path),
            validate_build_record(
                path, core_revision, board_revision, APPLICATION_ROOT
            ),
        )
    return images


def output_paths(argument: str | None, overwrite: bool) -> tuple[Path, Path, Path]:
    """! @brief 신규 JSON과 두 sanitized transcript 경로를 준비합니다. """

    if not argument:
        raise M30OobFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise M30OobFailure("--evidence는 .json 파일이어야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise M30OobFailure("기존 M30-OOB-01 증적을 덮어쓰지 않습니다.")
    for path in existing:
        if not path.is_file():
            raise M30OobFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
        path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return paths


def read_wire_line(serial_port: Any, pending: bytearray, deadline: float) -> bytes:
    """! @brief 완전한 UART 한 줄만 bounded buffer로 반환합니다. """

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
                raise M30OobFailure("미완성 UART line이 허용 크기를 넘었습니다.")
    raise M30OobFailure("M30-OOB-01 UART token timeout")


def sanitized_line(line: bytes) -> bytes:
    """! @brief raw SC OOB material을 진단 가능한 SHA-256으로 치환합니다. """

    match = FRAME_PATTERN.search(line)
    if match is None:
        return line
    raw_frame = bytes.fromhex(match.group(1).decode("ascii"))
    digest = hashlib.sha256(raw_frame).hexdigest().encode("ascii")
    return (
        line[: match.start()]
        + b"|frame_sha256="
        + digest
        + b"|"
        + line[match.end() :]
    )


def capture_sanitized(capture: bytearray, line: bytes) -> None:
    """! @brief raw SC OOB material 없이 protocol line을 transcript에 기록합니다. """

    capture.extend(sanitized_line(line) + b"\n")
    if len(capture) > MAX_TRANSCRIPT_BYTES:
        raise M30OobFailure("sanitized transcript가 허용 크기를 넘었습니다.")


def parse_fields(line: bytes, kind: str) -> dict[str, str]:
    """! @brief 고정 prefix 뒤 key=value를 중복 없이 파싱합니다. """

    prefix = f"M30OOB|1|{kind}|".encode("ascii")
    if not line.startswith(prefix):
        raise M30OobFailure(f"{kind} record가 아닙니다.")
    fields: dict[str, str] = {}
    for part in line[len(prefix) :].split(b"|"):
        if part.count(b"=") != 1:
            raise M30OobFailure("protocol field 형식이 잘못됐습니다.")
        key_bytes, value_bytes = part.split(b"=", 1)
        try:
            key = key_bytes.decode("ascii")
            value = value_bytes.decode("ascii")
        except UnicodeDecodeError as error:
            raise M30OobFailure("protocol field가 ASCII가 아닙니다.") from error
        if not key or key in fields:
            raise M30OobFailure("protocol field가 비었거나 중복됐습니다.")
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
    command = f"M30OOB|1|{verb}|{round_index}|{nonce}{suffix}\r\n".encode(
        "ascii"
    )
    if serial_port.write(command) != len(command):
        raise M30OobFailure(f"{verb} command가 일부만 기록됐습니다.")
    serial_port.flush()


def wait_line(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    expected: bytes,
    *,
    allow_boot_noise: bool = False,
) -> None:
    """! @brief exact token 전 target FAIL과 protocol noise를 거부합니다. """

    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line == expected:
            capture_sanitized(capture, line)
            return
        if line.startswith(FAIL_PREFIX):
            capture_sanitized(capture, line)
            raise M30OobFailure(f"target 실패: {sanitized_line(line)!r}")
        if line.startswith(PROTOCOL_PREFIX) or not allow_boot_noise:
            capture_sanitized(capture, line)
            raise M30OobFailure(
                f"예상 밖 protocol line입니다: {sanitized_line(line)!r}"
            )


def wait_ready(
    serial_port: Any,
    role: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    nonce: str,
) -> None:
    """! @brief nonce 결합 READY와 frame/NDEF/bond 범위를 검증합니다. """

    prefix = (
        f"M30OOB|1|READY|role={role}|round=1|frame_bytes=74|"
        "ndef_enabled=1|bond_count="
    ).encode("ascii")
    suffix = f"|nonce={nonce}".encode("ascii")
    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line.startswith(FAIL_PREFIX):
            capture_sanitized(capture, line)
            raise M30OobFailure(f"{role} setup 실패: {sanitized_line(line)!r}")
        if line.startswith(prefix) and line.endswith(suffix):
            count = line[len(prefix) : -len(suffix)].decode("ascii", errors="strict")
            if DECIMAL_PATTERN.fullmatch(count) is None or int(count) > 4:
                raise M30OobFailure("READY bond_count가 잘못됐습니다.")
            capture_sanitized(capture, line)
            return
        if line.startswith(PROTOCOL_PREFIX):
            capture_sanitized(capture, line)
            raise M30OobFailure(
                f"stale READY protocol입니다: {sanitized_line(line)!r}"
            )


def validate_frame(frame_hex: str, role: str, nonce: str) -> bytes:
    """! @brief target frame의 magic·schema·role·길이·nonce·CRC를 독립 검사합니다. """

    if re.fullmatch(r"[0-9a-f]{148}", frame_hex) is None:
        raise M30OobFailure("LOCAL frame이 고정 소문자 hex가 아닙니다.")
    frame = bytes.fromhex(frame_hex)
    expected_role = 1 if role == "peripheral" else 2
    if (
        frame[:4] != b"N30O"
        or frame[4] != 1
        or frame[5] != expected_role
        or int.from_bytes(frame[6:8], "little") != FRAME_BYTES
        or frame[8] not in (0, 1)
        or frame[15] not in (0, 1)
        or frame[54:70] != bytes.fromhex(nonce)
        or int.from_bytes(frame[70:74], "little")
        != (binascii.crc32(frame[:70]) & 0xFFFFFFFF)
    ):
        raise M30OobFailure("LOCAL frame 계약이 일치하지 않습니다.")
    return frame


def receive_local(
    serial_port: Any,
    role: str,
    round_index: int,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> bytes:
    """! @brief raw LOCAL frame을 메모리에서만 읽고 sanitized transcript를 남깁니다. """

    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line.startswith(FAIL_PREFIX):
            capture_sanitized(capture, line)
            raise M30OobFailure(
                f"{role} local OOB 실패: {sanitized_line(line)!r}"
            )
        if line.startswith(b"M30OOB|1|LOCAL|"):
            fields = parse_fields(line, "LOCAL")
            if set(fields) != {"role", "round", "frame", "nonce"}:
                raise M30OobFailure("LOCAL field 집합이 다릅니다.")
            if (
                fields["role"] != role
                or fields["round"] != str(round_index)
                or fields["nonce"] != nonce
            ):
                raise M30OobFailure("LOCAL identity가 다릅니다.")
            frame = validate_frame(fields["frame"], role, nonce)
            capture_sanitized(capture, line)
            return frame
        if line.startswith(PROTOCOL_PREFIX):
            capture_sanitized(capture, line)
            raise M30OobFailure(
                f"LOCAL 전 예상 밖 protocol입니다: {sanitized_line(line)!r}"
            )


def collect_passes(
    ports: dict[str, Any],
    pending: dict[str, bytearray],
    captures: dict[str, bytearray],
    round_index: int,
    nonce: str,
    deadline: float,
) -> None:
    """! @brief 양쪽 exact OOB PASS가 도착할 때까지 교대로 읽습니다. """

    expected_common = {
        "round": str(round_index),
        "method": "oob",
        "level": "4",
        "key_size": "16",
        "sc": "1",
        "oob": "1",
        "nonce": nonce,
    }
    passed: set[str] = set()
    roles = ("peripheral", "central")
    next_role = 0
    while len(passed) != 2:
        role = roles[next_role]
        next_role = (next_role + 1) % 2
        serial_port = ports[role]
        if int(getattr(serial_port, "in_waiting", 0)) == 0:
            if time.monotonic() >= deadline:
                raise M30OobFailure("OOB PASS deadline이 끝났습니다.")
            time.sleep(0.002)
            continue
        line = read_wire_line(serial_port, pending[role], deadline)
        capture_sanitized(captures[role], line)
        if line.startswith(FAIL_PREFIX):
            raise M30OobFailure(f"{role} target 실패: {sanitized_line(line)!r}")
        if not line.startswith(b"M30OOB|1|PASS|"):
            raise M30OobFailure(
                f"PASS 전 예상 밖 protocol입니다: {sanitized_line(line)!r}"
            )
        fields = parse_fields(line, "PASS")
        expected = {"role": role, **expected_common}
        if fields != expected or role in passed:
            raise M30OobFailure("PASS field가 다르거나 중복됐습니다.")
        passed.add(role)


def execute_hil(
    serial_module: Any,
    endpoints: dict[str, RoleEndpoint],
    images: dict[str, ImageInput],
    baud: int,
    flash_timeout: float,
    deadline: float,
    captures: dict[str, bytearray],
) -> tuple[list[dict[str, Any]], dict[str, tuple[list[str], int]]]:
    """! @brief 두 image를 flash하고 20회 유선 OOB exchange와 RF pairing을 실행합니다. """

    if baud != DEFAULT_BAUD_RATE:
        raise M30OobFailure(f"M30-OOB-01은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            role: executor.submit(
                flash_image_pyocd,
                role,
                endpoints[role].board_id,
                images[role].path,
                flash_timeout,
            )
            for role in endpoints
        }
        flash_results = {role: future.result() for role, future in futures.items()}
    time.sleep(0.5)

    pending = {"peripheral": bytearray(), "central": bytearray()}
    results: list[dict[str, Any]] = []
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
        ready_nonces = {role: build_nonce() for role in endpoints}
        for role in endpoints:
            send_command(ports[role], "IDENTIFY", 1, ready_nonces[role])
        for role in endpoints:
            wait_ready(
                ports[role],
                role,
                pending[role],
                captures[role],
                deadline,
                ready_nonces[role],
            )

        for round_index in range(1, ROUNDS + 1):
            nonce = build_nonce()
            for role in endpoints:
                send_command(ports[role], "CLEAR", round_index, nonce)
            for role in endpoints:
                wait_line(
                    ports[role],
                    pending[role],
                    captures[role],
                    deadline,
                    (
                        f"M30OOB|1|CLEARED|role={role}|round={round_index}|"
                        f"bond_count=0|nonce={nonce}"
                    ).encode("ascii"),
                )
            time.sleep(0.5)

            for role in endpoints:
                send_command(ports[role], "PREPARE", round_index, nonce)
            frames = {
                role: receive_local(
                    ports[role],
                    role,
                    round_index,
                    nonce,
                    pending[role],
                    captures[role],
                    deadline,
                )
                for role in endpoints
            }

            for role in endpoints:
                corrupt = bytearray(frames["central" if role == "peripheral" else "peripheral"])
                corrupt[70] ^= 0x01
                send_command(ports[role], "REJECT", round_index, nonce, corrupt.hex())
            for role in endpoints:
                wait_line(
                    ports[role],
                    pending[role],
                    captures[role],
                    deadline,
                    (
                        f"M30OOB|1|REJECTED|role={role}|round={round_index}|"
                        f"class=crc|nonce={nonce}"
                    ).encode("ascii"),
                )

            send_command(
                ports["peripheral"],
                "REMOTE",
                round_index,
                nonce,
                frames["central"].hex(),
            )
            send_command(
                ports["central"],
                "REMOTE",
                round_index,
                nonce,
                frames["peripheral"].hex(),
            )
            for role in endpoints:
                wait_line(
                    ports[role],
                    pending[role],
                    captures[role],
                    deadline,
                    (
                        f"M30OOB|1|ARMED|role={role}|round={round_index}|"
                        f"nonce={nonce}"
                    ).encode("ascii"),
                )

            send_command(ports["peripheral"], "START", round_index, nonce)
            wait_line(
                ports["peripheral"],
                pending["peripheral"],
                captures["peripheral"],
                deadline,
                (
                    f"M30OOB|1|STARTED|role=peripheral|round={round_index}|"
                    f"nonce={nonce}"
                ).encode("ascii"),
            )
            send_command(ports["central"], "START", round_index, nonce)
            wait_line(
                ports["central"],
                pending["central"],
                captures["central"],
                deadline,
                (
                    f"M30OOB|1|STARTED|role=central|round={round_index}|"
                    f"nonce={nonce}"
                ).encode("ascii"),
            )
            collect_passes(ports, pending, captures, round_index, nonce, deadline)
            results.append(
                {
                    "round": round_index,
                    "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
                    "peripheral_frame_sha256": hashlib.sha256(
                        frames["peripheral"]
                    ).hexdigest(),
                    "central_frame_sha256": hashlib.sha256(
                        frames["central"]
                    ).hexdigest(),
                    "security_level": 4,
                    "key_size": 16,
                    "mismatch_attempts": 2,
                    "mismatch_accepts": 0,
                }
            )
            print(f"M30_OOB_PROGRESS={round_index}/{ROUNDS}")

    for role in endpoints:
        image = images[role]
        validate_image_unchanged(image.path, image.size, image.sha256)
    return results, flash_results


def endpoint_evidence(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief raw UID 없이 exact volume·COM·UID hash를 기록합니다. """

    match = re.match(r"^([A-Za-z]):(?:[\\/]|$)", str(endpoint.volume.root))
    if match is None:
        raise M30OobFailure("DAPLink volume이 Windows drive root가 아닙니다.")
    return {
        "board_id_sha256": hashlib.sha256(endpoint.board_id.encode("ascii")).hexdigest(),
        "volume": f"{match.group(1).upper()}:",
        "port": endpoint.port_name,
    }


def image_evidence(image: ImageInput) -> dict[str, Any]:
    """! @brief 경로 비의존 image byte·build identity를 반환합니다. """

    return {
        "name": image.path.name,
        "size": image.size,
        "sha256": image.sha256,
        "build_record": image.build_record,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief preflight 또는 20회 실제 OOB HIL과 증적 기록을 실행합니다. """

    args = parse_arguments(arguments)
    if not 30.0 <= args.result_timeout <= 600.0:
        raise M30OobFailure("--result-timeout은 30..600초여야 합니다.")
    serial_module, list_ports = import_pyserial()
    peripheral = discover_endpoint(
        args.peripheral_board_id,
        args.peripheral_volume,
        args.peripheral_port,
        list_ports,
    )
    central = discover_endpoint(
        args.central_board_id,
        args.central_volume,
        args.central_port,
        list_ports,
    )
    validate_pair_identity(peripheral, central)
    if args.discover_only:
        print("M30_OOB_DISCOVERY_PASS=2")
        return 0

    validate_source_clean(MILESTONE, APPLICATION_ROOT, RUNNER_PATH)
    core_revision = git_revision(REPOSITORY)
    if args.expected_core_revision and args.expected_core_revision != core_revision:
        raise M30OobFailure("현재 Core revision이 --expected-core-revision과 다릅니다.")
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    build_outdir = Path(args.build_outdir).resolve()
    if not build_outdir.is_dir():
        raise M30OobFailure("--build-outdir가 directory가 아닙니다.")
    images = collect_images(build_outdir, core_revision, board_revision)
    evidence_path, peripheral_path, central_path = output_paths(
        args.evidence, args.overwrite_evidence
    )
    endpoints = {"peripheral": peripheral, "central": central}
    captures = {"peripheral": bytearray(), "central": bytearray()}
    started = time.monotonic()
    rounds, flash_results = execute_hil(
        serial_module,
        endpoints,
        images,
        args.baud,
        args.flash_timeout,
        started + args.result_timeout,
        captures,
    )

    peripheral_path.write_bytes(bytes(captures["peripheral"]))
    central_path.write_bytes(bytes(captures["central"]))
    evidence = {
        "schema_version": 1,
        "test_id": "M30-OOB-01",
        "status": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "ncs_revision": "99553055607b2e9885fbc80ccd11fa9da81c2df0",
        "zephyr_revision": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
        "boards": 2,
        "endpoints": {
            role: endpoint_evidence(endpoint) for role, endpoint in endpoints.items()
        },
        "images": {role: image_evidence(image) for role, image in images.items()},
        "flash_backend": "pyocd-sector",
        "flash_results": {
            role: {"sequence": result[0], "bytes": result[1]}
            for role, result in flash_results.items()
        },
        "wired_carrier": "daplink_vcom",
        "wired_pairings": len(rounds),
        "mitm_links": len(rounds),
        "mismatch_attempts": sum(item["mismatch_attempts"] for item in rounds),
        "mismatched_payload_accepts": 0,
        "nfc_adapter_target_builds": 2,
        "nfc_rf_runs": 0,
        "raw_oob_evidence_policy": "sha256_only",
        "rounds": rounds,
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
        "M30_OOB_HIL_PASS=20;MITM_LINKS=20;MISMATCH_ACCEPTS=0;NFC_RF_RUNS=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (M30OobFailure, OSError, ValueError) as error:
        print(f"M30_OOB_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
