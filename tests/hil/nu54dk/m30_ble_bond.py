#!/usr/bin/env python3
"""! @brief M30-BOND-01 migration·privacy·stale key HIL을 실행합니다. """

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
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m30_ble_bond_hil"
RUNNER_PATH = Path(__file__).resolve()
BOARD_DIRECTORY = "nrf54l15dk_nrf54l15_cpuapp_nu54dk"
TOOLCHAIN_DIRECTORY = "zephyr_gnu"
TEST_DIRECTORY = "m30_ble_bond_hil"
PROTOCOL_PREFIX = b"M30BOND|1|"
FAIL_PREFIX = b"M30BOND|1|FAIL|"
ROUNDS = 20
ROTATIONS = 3
MAX_TRANSCRIPT_BYTES = 65536


class M30BondFailure(RuntimeError):
    """! @brief M30-BOND-01 장치·image·protocol·증적 실패입니다. """


@dataclass(frozen=True)
class ImageInput:
    """! @brief 한 role image의 immutable byte와 build identity입니다. """

    path: Path
    size: int
    sha256: str
    build_record: dict[str, str]


@dataclass(frozen=True)
class BondResult:
    """! @brief role별 최종 migration·reconnect·stale key 정량값입니다. """

    role: str
    reconnects: int
    rotations: int
    migration: int
    stale_key_accepts: int
    new_pairings: int
    final_bond_count: int


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact build·두 endpoint·900초 상한을 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M30-BOND-01 migration·privacy·stale key를 두 NU54DK에서 검증합니다."
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
        raise M30BondFailure(f"지원하지 않는 role입니다: {role}")
    return f"nucode.m30.bond.{code}"


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
            raise M30BondFailure("HEX가 지정 build outdir 밖에 있습니다.") from error
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
    """! @brief 신규 JSON과 두 transcript 경로를 준비합니다. """

    if not argument:
        raise M30BondFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise M30BondFailure("--evidence는 .json 파일이어야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    if any(path.exists() for path in paths) and not overwrite:
        raise M30BondFailure("기존 M30-BOND-01 증적을 덮어쓰지 않습니다.")
    for path in paths:
        if path.exists():
            if not path.is_file():
                raise M30BondFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
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
                raise M30BondFailure("미완성 UART line이 허용 크기를 넘었습니다.")
    raise M30BondFailure("M30-BOND-01 UART token timeout")


def capture_line(capture: bytearray, line: bytes) -> None:
    """! @brief ASCII protocol line을 bounded transcript에 추가합니다. """

    try:
        line.decode("ascii")
    except UnicodeDecodeError as error:
        raise M30BondFailure("M30-BOND-01 protocol line이 ASCII가 아닙니다.") from error
    capture.extend(line + b"\n")
    if len(capture) > MAX_TRANSCRIPT_BYTES:
        raise M30BondFailure("M30-BOND-01 transcript가 허용 크기를 넘었습니다.")


def send_line(serial_port: Any, line: str) -> None:
    """! @brief 완전한 ASCII command를 한 번에 VCOM으로 기록합니다. """

    data = (line + "\r\n").encode("ascii")
    if serial_port.write(data) != len(data):
        raise M30BondFailure("VCOM command가 일부만 기록됐습니다.")
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
            raise M30BondFailure(f"target 실패: {line!r}")
        if line.startswith(PROTOCOL_PREFIX) or not allow_boot_noise:
            capture_line(capture, line)
            raise M30BondFailure(f"예상 밖 protocol record입니다: {line!r}")


def collect_expected(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    expected: Sequence[bytes],
    deadline: float,
) -> None:
    """! @brief role별 비동기 record가 고정 순서와 값인지 검사합니다. """

    for wanted in expected:
        wait_exact(serial_port, pending, capture, wanted, deadline)


def suffix(nonce: str, core_revision: str) -> bytes:
    """! @brief session identity의 공통 protocol suffix를 반환합니다. """

    return f"|nonce={nonce}|core={core_revision}".encode("ascii")


def result_pattern(role: str, nonce: str, core_revision: str) -> re.Pattern[bytes]:
    """! @brief final bond_count만 0..1을 허용하는 RESULT pattern을 반환합니다. """

    rotations = rb"\|privacy_rotations=3" if role == "central" else b""
    return re.compile(
        rb"M30BOND\|1\|RESULT\|role="
        + role.encode("ascii")
        + rb"\|bonded_reconnects=20"
        + rotations
        + rb"\|migration=1\|stale_key_accepts=0\|new_pairings=0"
        + rb"\|bond_count=([01])\|callback_context=pass"
        + re.escape(suffix(nonce, core_revision))
    )


def collect_final(
    serial_port: Any,
    role: str,
    nonce: str,
    core_revision: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> BondResult:
    """! @brief stale 거부와 최종 정량 RESULT 두 record를 검사합니다. """

    rejected = re.compile(
        rb"M30BOND\|1\|STALE_REJECTED\|role="
        + role.encode("ascii")
        + rb"\|accepted=0\|reason=(?:0|[1-9][0-9]*)"
        + re.escape(suffix(nonce, core_revision))
    )
    line = read_wire_line(serial_port, pending, deadline)
    capture_line(capture, line)
    if line.startswith(FAIL_PREFIX) or rejected.fullmatch(line) is None:
        raise M30BondFailure(f"{role} stale 거부 record가 잘못됐습니다: {line!r}")
    line = read_wire_line(serial_port, pending, deadline)
    capture_line(capture, line)
    match = result_pattern(role, nonce, core_revision).fullmatch(line)
    if line.startswith(FAIL_PREFIX) or match is None:
        raise M30BondFailure(f"{role} RESULT가 잘못됐습니다: {line!r}")
    return BondResult(
        role=role,
        reconnects=ROUNDS,
        rotations=ROTATIONS if role == "central" else 0,
        migration=1,
        stale_key_accepts=0,
        new_pairings=0,
        final_bond_count=int(match.group(1)),
    )


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
) -> tuple[dict[str, BondResult], dict[str, tuple[list[str], int]]]:
    """! @brief clean→migration→20 reconnect→stale 거부를 두 보드에서 실행합니다. """

    if baud != DEFAULT_BAUD_RATE:
        raise M30BondFailure(f"M30-BOND-01은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
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
        reset = f"M30BOND|1|RESET|core={core_revision}"
        for role in endpoints:
            send_line(ports[role], reset)
        for role in endpoints:
            wait_exact(
                ports[role],
                pending[role],
                captures[role],
                (
                    f"M30BOND|1|RESETTING|role={role}|warm=1|core={core_revision}"
                ).encode("ascii"),
                deadline,
            )
        time.sleep(1.0)

        for role in endpoints:
            send_line(ports[role], "M30BOND|1|READY?")
        for role in endpoints:
            wait_exact(
                ports[role],
                pending[role],
                captures[role],
                (
                    f"M30BOND|1|READY|role={role}|stage=clean|bonds=0|"
                    f"migrations=0|rejected=0|core={core_revision}"
                ).encode("ascii"),
                deadline,
                allow_boot_noise=True,
            )

        start = f"M30BOND|1|START|nonce={nonce}|core={core_revision}"
        send_line(ports["peripheral"], start)
        for wanted in (
            b"M30BOND|1|BEGIN|role=peripheral|phase=prime" + suffix(nonce, core_revision),
            b"M30BOND|1|ADVERTISE|role=peripheral|phase=prime"
            + suffix(nonce, core_revision),
        ):
            wait_exact(
                ports["peripheral"],
                pending["peripheral"],
                captures["peripheral"],
                wanted,
                deadline,
            )
        send_line(ports["central"], start)
        for wanted in (
            b"M30BOND|1|BEGIN|role=central|phase=prime" + suffix(nonce, core_revision),
            b"M30BOND|1|SCAN|role=central|phase=prime" + suffix(nonce, core_revision),
        ):
            wait_exact(
                ports["central"],
                pending["central"],
                captures["central"],
                wanted,
                deadline,
            )

        def prime_records(role: str) -> tuple[bytes, bytes]:
            return (
                (
                    f"M30BOND|1|PAIRED|role={role}|level=2|key_size=16|sc=1|bonded=1"
                ).encode("ascii")
                + suffix(nonce, core_revision),
                (
                    f"M30BOND|1|MIGRATE_REBOOT|role={role}|schema=1|warm=1"
                ).encode("ascii")
                + suffix(nonce, core_revision),
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                role: executor.submit(
                    collect_expected,
                    ports[role],
                    pending[role],
                    captures[role],
                    prime_records(role),
                    deadline,
                )
                for role in endpoints
            }
            for future in futures.values():
                future.result()
        time.sleep(1.0)

        for role in endpoints:
            send_line(ports[role], "M30BOND|1|READY?")
        for role in endpoints:
            wait_exact(
                ports[role],
                pending[role],
                captures[role],
                (
                    f"M30BOND|1|READY|role={role}|stage=resume|bonds=1|"
                    f"migrations=1|rejected=0|core={core_revision}"
                ).encode("ascii"),
                deadline,
                allow_boot_noise=True,
            )

        send_line(ports["peripheral"], start)
        for wanted in (
            b"M30BOND|1|BEGIN|role=peripheral|phase=resume"
            + suffix(nonce, core_revision),
            b"M30BOND|1|ADVERTISE|role=peripheral|phase=resume"
            + suffix(nonce, core_revision),
        ):
            wait_exact(
                ports["peripheral"],
                pending["peripheral"],
                captures["peripheral"],
                wanted,
                deadline,
            )
        send_line(ports["central"], start)
        for wanted in (
            b"M30BOND|1|BEGIN|role=central|phase=resume" + suffix(nonce, core_revision),
            b"M30BOND|1|SCAN|role=central|phase=resume" + suffix(nonce, core_revision),
        ):
            wait_exact(
                ports["central"],
                pending["central"],
                captures["central"],
                wanted,
                deadline,
            )

        reconnect_records: dict[str, list[bytes]] = {
            "peripheral": [],
            "central": [
                b"M30BOND|1|RPA|role=central|rotations=3"
                + suffix(nonce, core_revision)
            ],
        }
        for role in endpoints:
            reconnect_records[role].extend(
                (
                    f"M30BOND|1|RECONNECT|role={role}|count={count}"
                ).encode("ascii")
                + suffix(nonce, core_revision)
                for count in range(1, ROUNDS + 1)
            )
            reconnect_records[role].append(
                (
                    f"M30BOND|1|RECONNECT_DONE|role={role}|count=20"
                ).encode("ascii")
                + suffix(nonce, core_revision)
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                role: executor.submit(
                    collect_expected,
                    ports[role],
                    pending[role],
                    captures[role],
                    reconnect_records[role],
                    deadline,
                )
                for role in endpoints
            }
            for future in futures.values():
                future.result()

        send_line(ports["peripheral"], "M30BOND|1|ERASE_STALE")
        wait_exact(
            ports["peripheral"],
            pending["peripheral"],
            captures["peripheral"],
            b"M30BOND|1|STALE_ERASED|role=peripheral|bond_count=0"
            + suffix(nonce, core_revision),
            deadline,
        )
        send_line(ports["peripheral"], "M30BOND|1|STALE")
        wait_exact(
            ports["peripheral"],
            pending["peripheral"],
            captures["peripheral"],
            b"M30BOND|1|ADVERTISE|role=peripheral|phase=stale"
            + suffix(nonce, core_revision),
            deadline,
        )
        send_line(ports["central"], "M30BOND|1|STALE")
        wait_exact(
            ports["central"],
            pending["central"],
            captures["central"],
            b"M30BOND|1|SCAN|role=central|phase=stale"
            + suffix(nonce, core_revision),
            deadline,
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                role: executor.submit(
                    collect_final,
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
        raise M30BondFailure("DAPLink volume이 Windows drive root가 아닙니다.")
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
    """! @brief preflight 또는 실제 M30-BOND-01을 실행하고 증적을 기록합니다. """

    args = parse_arguments(arguments)
    if not 60.0 <= args.result_timeout <= 900.0:
        raise M30BondFailure("--result-timeout은 60..900초여야 합니다.")
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
        print("M30_BOND_DISCOVERY_PASS=2")
        return 0

    validate_source_clean(MILESTONE, APPLICATION_ROOT, RUNNER_PATH)
    core_revision = git_revision(REPOSITORY)
    if args.expected_core_revision and args.expected_core_revision != core_revision:
        raise M30BondFailure("현재 Core revision이 --expected-core-revision과 다릅니다.")
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    build_outdir = Path(args.build_outdir).resolve()
    if not build_outdir.is_dir():
        raise M30BondFailure("--build-outdir가 directory가 아닙니다.")
    images = collect_images(build_outdir, core_revision, board_revision)
    evidence_path, peripheral_path, central_path = output_paths(
        args.evidence, args.overwrite_evidence
    )
    endpoints = {"peripheral": peripheral, "central": central}
    captures = {"peripheral": bytearray(), "central": bytearray()}
    nonce = build_nonce()
    started = time.monotonic()
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
    duration = time.monotonic() - started
    peripheral_path.write_bytes(captures["peripheral"])
    central_path.write_bytes(captures["central"])
    evidence = {
        "schema_version": 1,
        "test_id": "M30-BOND-01",
        "status": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 3),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "boards": 2,
        "endpoints": {role: endpoint_evidence(value) for role, value in endpoints.items()},
        "images": {role: image_evidence(value) for role, value in images.items()},
        "flash_backend": "pyocd-sector",
        "flash_results": {
            role: {"sequence": value[0][0], "bytes": value[1]}
            for role, value in flash_results.items()
        },
        "warm_reboots": 4,
        "power_cut_injected": False,
        "mass_erase_or_recover": False,
        "bonded_reconnects": min(value.reconnects for value in results.values()),
        "privacy_rotations": results["central"].rotations,
        "metadata_migrations": min(value.migration for value in results.values()),
        "stale_key_attempts": 1,
        "stale_key_accepts": max(value.stale_key_accepts for value in results.values()),
        "new_pairings_after_migration": max(value.new_pairings for value in results.values()),
        "final_bond_counts": {
            role: value.final_bond_count for role, value in results.items()
        },
        "transcripts": {
            "peripheral": transcript_record(peripheral_path, captures["peripheral"]),
            "central": transcript_record(central_path, captures["central"]),
        },
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "M30_BOND_HIL_PASS=20;PRIVACY_ROTATIONS=3;MIGRATIONS=1;"
        "STALE_KEY_ACCEPTS=0;POWER_CUT=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M30BondFailure as error:
        print(f"M30_BOND_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
