#!/usr/bin/env python3
"""! @brief M30-PROFILE-01 일곱 BLE profile의 2보드 HIL을 실행합니다. """

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
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m30_ble_profile_hil"
RUNNER_PATH = Path(__file__).resolve()
BOARD_DIRECTORY = "nrf54l15dk_nrf54l15_cpuapp_nu54dk"
TOOLCHAIN_DIRECTORY = "zephyr_gnu"
TEST_DIRECTORY = "m30_ble_profile_hil"
PROTOCOL_PREFIX = b"M30PROFILE|1|"
FAIL_PREFIX = b"M30PROFILE|1|FAIL|"
CATALOG = (
    "battery",
    "device_information",
    "hid_keyboard",
    "hid_mouse",
    "hid_consumer_control",
    "heart_rate",
    "environmental_sensing",
)
OPERATIONS = 100
MAX_TRANSCRIPT_BYTES = 65536


class M30ProfileFailure(RuntimeError):
    """! @brief M30-PROFILE-01 장치·image·protocol·증적 실패입니다. """


@dataclass(frozen=True)
class ImageInput:
    """! @brief 한 role image의 immutable byte와 build identity입니다. """

    path: Path
    size: int
    sha256: str
    build_record: dict[str, str]


@dataclass(frozen=True)
class ProfileResult:
    """! @brief role별 catalog·operation·오류 정량값입니다. """

    role: str
    catalog: int
    operations: int
    payload_errors: int
    driver_errors: int


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact build·두 endpoint·900초 상한을 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M30-PROFILE-01 일곱 BLE profile을 두 NU54DK에서 검증합니다."
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
    parser.add_argument("--result-timeout", type=float, default=900.0)
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--evidence")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def scenario_name(role: str) -> str:
    """! @brief role별 canonical Twister scenario를 반환합니다. """

    code = {"peripheral": "p", "central": "c"}.get(role)
    if code is None:
        raise M30ProfileFailure(f"지원하지 않는 role입니다: {role}")
    return f"nucode.m30.profile.{code}"


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
            raise M30ProfileFailure("HEX가 지정 build outdir 밖에 있습니다.") from error
        images[role] = ImageInput(
            path,
            path.stat().st_size,
            file_sha256(path),
            validate_build_record(path, core_revision, board_revision, APPLICATION_ROOT),
        )
    return images


def output_paths(argument: str | None, overwrite: bool) -> tuple[Path, Path, Path]:
    """! @brief 신규 JSON과 두 transcript 경로를 준비합니다. """

    if not argument:
        raise M30ProfileFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise M30ProfileFailure("--evidence는 .json 파일이어야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    if any(path.exists() for path in paths) and not overwrite:
        raise M30ProfileFailure("기존 M30-PROFILE-01 증적을 덮어쓰지 않습니다.")
    for path in paths:
        if path.exists():
            if not path.is_file():
                raise M30ProfileFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
            path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return paths


def read_wire_line(serial_port: Any, pending: bytearray, deadline: float) -> bytes:
    """! @brief bounded buffer에서 완전한 VCOM 한 줄을 반환합니다. """

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
                raise M30ProfileFailure("미완성 UART line이 허용 크기를 넘었습니다.")
    raise M30ProfileFailure("M30-PROFILE-01 UART token timeout")


def capture_line(capture: bytearray, line: bytes) -> None:
    """! @brief ASCII protocol line을 bounded transcript에 추가합니다. """

    try:
        decoded = line.decode("ascii")
    except UnicodeDecodeError as error:
        raise M30ProfileFailure("profile protocol line이 ASCII가 아닙니다.") from error
    capture.extend(line + b"\n")
    if len(capture) > MAX_TRANSCRIPT_BYTES:
        raise M30ProfileFailure("profile transcript가 허용 크기를 넘었습니다.")
    print(f"M30_PROFILE_PROGRESS={decoded}", flush=True)


def send_line(serial_port: Any, line: str) -> None:
    """! @brief 완전한 ASCII command를 한 번에 VCOM으로 기록합니다. """

    data = (line + "\r\n").encode("ascii")
    if serial_port.write(data) != len(data):
        raise M30ProfileFailure("VCOM command가 일부만 기록됐습니다.")
    serial_port.flush()


def wait_exact(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    expected: bytes,
    deadline: float,
    *,
    allow_boot_noise: bool = False,
) -> None:
    """! @brief exact record 전 FAIL·다른 protocol record를 거부합니다. """

    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line == expected:
            capture_line(capture, line)
            return
        if line.startswith(FAIL_PREFIX):
            capture_line(capture, line)
            raise M30ProfileFailure(f"target 실패: {line!r}")
        if line.startswith(PROTOCOL_PREFIX) or not allow_boot_noise:
            capture_line(capture, line)
            raise M30ProfileFailure(f"예상 밖 protocol record입니다: {line!r}")


def suffix(nonce: str, core_revision: str) -> bytes:
    """! @brief session identity의 공통 protocol suffix를 반환합니다. """

    return f"|nonce={nonce}|core={core_revision}".encode("ascii")


def expected_result(role: str, nonce: str, core_revision: str) -> bytes:
    """! @brief role별 정량 RESULT의 canonical byte를 반환합니다. """

    if role == "peripheral":
        fields = (
            "|bas=100|keyboard=100|mouse=100|consumer=100|hrs=100"
            "|ess_temperature=100|ess_humidity=100|driver_errors=0"
        )
    elif role == "central":
        fields = (
            "|bas=100|dis=100|keyboard=100|mouse=100|consumer=100"
            "|hrs=100|ess_temperature=100|ess_humidity=100|payload_errors=0"
        )
    else:
        raise M30ProfileFailure(f"지원하지 않는 role입니다: {role}")
    return (
        f"M30PROFILE|1|RESULT|role={role}|catalog=7|operations=100{fields}".encode(
            "ascii"
        )
        + suffix(nonce, core_revision)
    )


def parse_result(
    line: bytes, role: str, nonce: str, core_revision: str
) -> ProfileResult:
    """! @brief exact RESULT만 정량 객체로 변환합니다. """

    if line != expected_result(role, nonce, core_revision):
        raise M30ProfileFailure(f"{role} RESULT가 잘못됐습니다: {line!r}")
    return ProfileResult(
        role=role,
        catalog=len(CATALOG),
        operations=OPERATIONS,
        payload_errors=0,
        driver_errors=0,
    )


def collect_result(
    serial_port: Any,
    role: str,
    nonce: str,
    core_revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> ProfileResult:
    """! @brief role별 final RESULT를 읽고 exact 값을 검사합니다. """

    line = read_wire_line(serial_port, pending, deadline)
    capture_line(capture, line)
    if line.startswith(FAIL_PREFIX):
        raise M30ProfileFailure(f"target 실패: {line!r}")
    return parse_result(line, role, nonce, core_revision)


def execute_hil(
    serial_module: Any,
    endpoints: dict[str, RoleEndpoint],
    images: dict[str, ImageInput],
    baud: int,
    flash_timeout: float,
    result_timeout: float,
    core_revision: str,
    nonce: str,
    captures: dict[str, bytearray],
) -> tuple[dict[str, ProfileResult], dict[str, tuple[list[str], int]]]:
    """! @brief flash→보안→구독→profile 100회 protocol을 실행합니다. """

    if baud != DEFAULT_BAUD_RATE:
        raise M30ProfileFailure(
            f"M30-PROFILE-01은 {DEFAULT_BAUD_RATE} baud만 허용합니다."
        )
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
        deadline = time.monotonic() + result_timeout

        for role in endpoints:
            send_line(ports[role], "M30PROFILE|1|READY?")
        for role in endpoints:
            wait_exact(
                ports[role],
                pending[role],
                captures[role],
                (
                    f"M30PROFILE|1|BOOT|role={role}|catalog=7|core={core_revision}"
                ).encode("ascii"),
                deadline,
                allow_boot_noise=True,
            )

        start = f"M30PROFILE|1|START|nonce={nonce}|core={core_revision}"
        send_line(ports["peripheral"], start)
        wait_exact(
            ports["peripheral"],
            pending["peripheral"],
            captures["peripheral"],
            b"M30PROFILE|1|BEGIN|role=peripheral" + suffix(nonce, core_revision),
            deadline,
        )
        send_line(ports["central"], start)
        wait_exact(
            ports["central"],
            pending["central"],
            captures["central"],
            b"M30PROFILE|1|BEGIN|role=central" + suffix(nonce, core_revision),
            deadline,
        )
        wait_exact(
            ports["central"],
            pending["central"],
            captures["central"],
            b"M30PROFILE|1|READY|role=central|catalog=7|dis_reads=100"
            + suffix(nonce, core_revision),
            deadline,
        )
        send_line(ports["peripheral"], "M30PROFILE|1|RUN")
        wait_exact(
            ports["peripheral"],
            pending["peripheral"],
            captures["peripheral"],
            b"M30PROFILE|1|RUNNING|role=peripheral|operations=100"
            + suffix(nonce, core_revision),
            deadline,
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                role: executor.submit(
                    collect_result,
                    ports[role],
                    role,
                    nonce,
                    core_revision,
                    pending[role],
                    captures[role],
                    deadline,
                )
                for role in endpoints
            }
            results = {role: future.result() for role, future in futures.items()}

    for role in endpoints:
        image = images[role]
        validate_image_unchanged(image.path, image.size, image.sha256)
    return results, flash_results


def endpoint_evidence(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief raw UID 없이 exact volume·COM·UID hash를 기록합니다. """

    match = re.match(r"^([A-Za-z]):(?:[\\/]|$)", str(endpoint.volume.root))
    if match is None:
        raise M30ProfileFailure("DAPLink volume이 Windows drive root가 아닙니다.")
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
    """! @brief preflight 또는 실제 M30-PROFILE-01을 실행하고 증적을 기록합니다. """

    args = parse_arguments(arguments)
    if not 60.0 <= args.result_timeout <= 900.0:
        raise M30ProfileFailure("--result-timeout은 60..900초여야 합니다.")
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
        print("M30_PROFILE_DISCOVERY_PASS=2")
        return 0

    validate_source_clean(MILESTONE, APPLICATION_ROOT, RUNNER_PATH)
    core_revision = git_revision(REPOSITORY)
    if args.expected_core_revision and args.expected_core_revision != core_revision:
        raise M30ProfileFailure("현재 Core revision이 --expected-core-revision과 다릅니다.")
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    build_outdir = Path(args.build_outdir).resolve()
    if not build_outdir.is_dir():
        raise M30ProfileFailure("--build-outdir가 directory가 아닙니다.")
    images = collect_images(build_outdir, core_revision, board_revision)
    evidence_path, peripheral_path, central_path = output_paths(
        args.evidence, args.overwrite_evidence
    )
    endpoints = {"peripheral": peripheral, "central": central}
    captures = {"peripheral": bytearray(), "central": bytearray()}
    nonce = build_nonce()
    started = time.monotonic()
    try:
        results, flash_results = execute_hil(
            serial_module,
            endpoints,
            images,
            args.baud,
            args.flash_timeout,
            args.result_timeout,
            core_revision,
            nonce,
            captures,
        )
    except M30ProfileFailure as error:
        peripheral_path.write_bytes(captures["peripheral"])
        central_path.write_bytes(captures["central"])
        raise M30ProfileFailure(
            f"{error}; 실패 transcript: {peripheral_path.name}, {central_path.name}"
        ) from error
    duration = time.monotonic() - started
    peripheral_path.write_bytes(captures["peripheral"])
    central_path.write_bytes(captures["central"])
    evidence = {
        "schema_version": 1,
        "test_id": "M30-PROFILE-01",
        "status": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 3),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "boards": 2,
        "catalog": list(CATALOG),
        "catalog_entries": len(CATALOG),
        "operations_per_service": min(value.operations for value in results.values()),
        "payload_errors": max(value.payload_errors for value in results.values()),
        "driver_errors": max(value.driver_errors for value in results.values()),
        "endpoints": {role: endpoint_evidence(value) for role, value in endpoints.items()},
        "images": {role: image_evidence(value) for role, value in images.items()},
        "flash_backend": "pyocd-sector",
        "flash_results": {
            role: {"sequence": value[0][0], "bytes": value[1]}
            for role, value in flash_results.items()
        },
        "power_cut_injected": False,
        "mass_erase_or_recover": False,
        "transcripts": {
            "peripheral": transcript_record(peripheral_path, captures["peripheral"]),
            "central": transcript_record(central_path, captures["central"]),
        },
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("M30_PROFILE_HIL_PASS=7;OPERATIONS=100;PAYLOAD_ERRORS=0;POWER_CUT=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M30ProfileFailure as error:
        print(f"M30_PROFILE_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
