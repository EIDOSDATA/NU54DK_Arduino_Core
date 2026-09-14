#!/usr/bin/env python3
"""! @brief M30-BOOT-01 MCUboot 서명·부정 image HIL을 실행합니다. """

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    BlePairHilFailure,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    RoleEndpoint,
    discover_endpoint,
    file_sha256,
    flash_image_pyocd,
    git_revision,
    transcript_record,
    validate_board_revision,
    validate_image_unchanged,
    validate_source_clean,
)
from m6_serial_echo import import_pyserial  # noqa: E402


MILESTONE = "M30"
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m30_mcuboot_hil"
RUNNER_PATH = Path(__file__).resolve()
BOARD_DIRECTORY = "nrf54l15dk_nrf54l15_cpuapp_nu54dk"
TOOLCHAIN_DIRECTORY = "zephyr_gnu"
SCENARIO = "nucode.m30.mcuboot_hil"
APPLICATION_DOMAIN = "m30_mcuboot_hil"
BOOT_DOMAIN = "mcuboot"
PROTOCOL_PREFIX = b"M30BOOT|1|"
FAIL_PREFIX = b"M30BOOT|1|FAIL|"
SLOT1_OFFSET = 794624
SLOT1_SIZE = 729088
SLOT1_END = SLOT1_OFFSET + SLOT1_SIZE
SIGNED_BOOTS = 20
MCUBOOT_MAGIC = 0x96F3B83D
PRIMARY_VERSION = (0, 0, 0, 0)
WRONG_KEY_VERSION = (9, 0, 0, 0)
MAX_TRANSCRIPT_BYTES = 131072


class M30BootFailure(RuntimeError):
    """! @brief M30-BOOT-01 build·device·protocol 실패입니다. """


@dataclass(frozen=True)
class ImageInput:
    """! @brief immutable image byte와 MCUboot header identity입니다. """

    path: Path
    size: int
    sha256: str
    version: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class BuildInputs:
    """! @brief exact sysbuild에서 검증한 boot·application image 묶음입니다. """

    root: Path
    boot: ImageInput
    signed: ImageInput
    signed_hex: ImageInput
    raw: ImageInput
    public_key_source: Path
    public_key_sha256: str


@dataclass(frozen=True)
class ReadyRecord:
    """! @brief target READY에서 해석한 활성 image 상태입니다. """

    active_slot: int
    confirmed: int
    confirm_rc: int
    version: tuple[int, int, int, int]
    core_revision: str


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact build·key·endpoint·900초 상한을 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M30-BOOT-01 MCUboot P-256 서명과 부정 image를 검증합니다."
    )
    parser.add_argument("--build-outdir", required=True)
    parser.add_argument("--board-id", required=True)
    parser.add_argument("--volume")
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=120.0)
    parser.add_argument("--result-timeout", type=float, default=900.0)
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--trust-signing-key", required=True)
    parser.add_argument("--wrong-signing-key", required=True)
    parser.add_argument("--imgtool-python", required=True)
    parser.add_argument("--imgtool", required=True)
    parser.add_argument("--evidence")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def resolve_sysbuild_root(argument: str) -> Path:
    """! @brief direct 또는 canonical Twister sysbuild root를 반환합니다. """

    outdir = Path(argument).resolve()
    direct = outdir / "domains.yaml"
    canonical = outdir / BOARD_DIRECTORY / TOOLCHAIN_DIRECTORY / SCENARIO / "domains.yaml"
    matches = [path.parent for path in (direct, canonical) if path.is_file()]
    if len(matches) != 1:
        raise M30BootFailure(
            "--build-outdir에서 exact domains.yaml 하나를 찾지 못했습니다."
        )
    return matches[0]


def path_is_within(path: Path, parent: Path) -> bool:
    """! @brief path가 parent 내부인지 symlink 해석 후 판정합니다. """

    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def validate_private_key(argument: str, label: str) -> Path:
    """! @brief 저장소 밖 PEM private key만 허용합니다. """

    path = Path(argument).resolve()
    if not path.is_file() or path.suffix.casefold() != ".pem":
        raise M30BootFailure(f"{label}가 외부 PEM 파일이 아닙니다.")
    if path_is_within(path, REPOSITORY):
        raise M30BootFailure(f"{label}를 저장소 내부에 둘 수 없습니다.")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise M30BootFailure(f"{label}를 읽지 못했습니다: {error}") from error
    headers = (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN EC PRIVATE KEY-----")
    if not any(header in data for header in headers):
        raise M30BootFailure(f"{label}에 private-key PEM header가 없습니다.")
    return path


def parse_mcuboot_version(path: Path) -> tuple[int, int, int, int] | None:
    """! @brief MCUboot v1 header의 semantic version을 읽습니다. """

    try:
        header = path.read_bytes()[:32]
    except OSError as error:
        raise M30BootFailure(f"image header를 읽지 못했습니다: {path}: {error}") from error
    if len(header) < 32:
        raise M30BootFailure(f"image가 MCUboot header보다 작습니다: {path}")
    magic = struct.unpack_from("<I", header, 0)[0]
    if magic != MCUBOOT_MAGIC:
        return None
    header_size = struct.unpack_from("<H", header, 8)[0]
    if header_size != 0x800:
        raise M30BootFailure(f"MCUboot header size가 0x800이 아닙니다: {path}")
    major, minor, revision, build_num = struct.unpack_from("<BBHI", header, 20)
    return major, minor, revision, build_num


def immutable_image(
    path: Path, *, expected_version: tuple[int, int, int, int] | None
) -> ImageInput:
    """! @brief image 형식·크기·hash를 한 번만 수집합니다. """

    path = path.resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise M30BootFailure(f"image가 없습니다: {path}")
    if path.stat().st_size > SLOT1_SIZE:
        raise M30BootFailure(f"image가 712 KiB slot을 넘습니다: {path}")
    version = parse_mcuboot_version(path) if path.suffix.casefold() == ".bin" else None
    if version != expected_version:
        raise M30BootFailure(
            f"image version이 다릅니다: {path.name}: {version}, "
            f"expected={expected_version}"
        )
    return ImageInput(path, path.stat().st_size, file_sha256(path), version)


def parse_domains(root: Path) -> None:
    """! @brief sysbuild domain과 flash 순서를 exact 두 domain으로 고정합니다. """

    path = root / "domains.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise M30BootFailure(f"domains.yaml을 읽지 못했습니다: {error}") from error
    if len(text) > 8192:
        raise M30BootFailure("domains.yaml 크기가 허용 범위를 넘습니다.")
    entries = re.findall(
        r"(?m)^  - name: ([a-z0-9_]+)\r?\n    build_dir: (.+)$", text
    )
    if [name for name, _directory in entries] != [APPLICATION_DOMAIN, BOOT_DOMAIN]:
        raise M30BootFailure(f"sysbuild domain 구성이 다릅니다: {entries!r}")
    for name, directory in entries:
        expected = (root / name).resolve()
        if Path(directory.strip()).resolve() != expected:
            raise M30BootFailure(f"{name} build_dir가 sysbuild root 밖이거나 다릅니다.")
    flash_match = re.search(r"(?ms)^flash_order:\r?\n((?:  - [a-z0-9_]+\r?\n?)+)", text)
    if flash_match is None:
        raise M30BootFailure("domains.yaml에 flash_order가 없습니다.")
    flash_order = re.findall(r"(?m)^  - ([a-z0-9_]+)$", flash_match.group(1))
    if flash_order != [BOOT_DOMAIN, APPLICATION_DOMAIN]:
        raise M30BootFailure(f"sysbuild flash_order가 다릅니다: {flash_order!r}")


def require_config_tokens(path: Path, tokens: Sequence[str]) -> str:
    """! @brief 생성 Kconfig에서 보안·layout token을 확인합니다. """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise M30BootFailure(f"생성 Kconfig를 읽지 못했습니다: {path}: {error}") from error
    for token in tokens:
        if token not in text:
            raise M30BootFailure(f"생성 Kconfig token이 없습니다: {token}")
    return text


def collect_build_inputs(argument: str, core_revision: str, trust_key: Path) -> BuildInputs:
    """! @brief exact source·layout·P-256 key와 sysbuild image를 결합합니다. """

    root = resolve_sysbuild_root(argument)
    parse_domains(root)
    app = root / APPLICATION_DOMAIN
    boot = root / BOOT_DOMAIN
    app_config = require_config_tokens(
        app / "zephyr/.config",
        (
            "CONFIG_BOOTLOADER_MCUBOOT=y",
            'CONFIG_MCUBOOT_EXTRA_IMGTOOL_ARGS="--security-counter 1"',
        ),
    )
    boot_config = require_config_tokens(
        boot / "zephyr/.config",
        (
            "CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION_SECURITY_COUNTER=y",
        ),
    )
    del app_config
    key_match = re.search(r'^CONFIG_BOOT_SIGNATURE_KEY_FILE="(.+)"$', boot_config, re.M)
    if key_match is None:
        raise M30BootFailure("MCUboot build의 signing key identity가 없습니다.")
    configured_key = Path(key_match.group(1)).resolve()
    if configured_key != trust_key:
        raise M30BootFailure("MCUboot build key가 --trust-signing-key와 다릅니다.")
    if path_is_within(configured_key, REPOSITORY):
        raise M30BootFailure("MCUboot build key가 저장소 내부를 가리킵니다.")

    raw_path = app / "zephyr/zephyr.bin"
    try:
        raw_bytes = raw_path.read_bytes()
    except OSError as error:
        raise M30BootFailure(f"raw application image를 읽지 못했습니다: {error}") from error
    if core_revision.encode("ascii") not in raw_bytes:
        raise M30BootFailure("application image에 exact 40자리 Core revision이 없습니다.")
    public_key = boot / "zephyr/autogen-pubkey.c"
    if not public_key.is_file() or public_key.stat().st_size <= 0:
        raise M30BootFailure("MCUboot 생성 public key source가 없습니다.")
    return BuildInputs(
        root=root,
        boot=immutable_image(
            boot / "zephyr/zephyr.hex", expected_version=None
        ),
        signed=immutable_image(
            app / "zephyr/zephyr.signed.bin", expected_version=PRIMARY_VERSION
        ),
        signed_hex=immutable_image(
            app / "zephyr/zephyr.signed.hex", expected_version=None
        ),
        raw=immutable_image(raw_path, expected_version=None),
        public_key_source=public_key,
        public_key_sha256=file_sha256(public_key),
    )


def create_wrong_key_image(
    inputs: BuildInputs,
    wrong_key: Path,
    imgtool_python: Path,
    imgtool: Path,
    output: Path,
) -> ImageInput:
    """! @brief 다른 P-256 key와 높은 version으로 secondary image를 생성합니다. """

    for label, path in (("imgtool Python", imgtool_python), ("imgtool", imgtool)):
        if not path.is_file():
            raise M30BootFailure(f"{label} 실행 파일이 없습니다: {path}")
    command = (
        str(imgtool_python),
        str(imgtool),
        "sign",
        "--version",
        "9.0.0+0",
        "--slot-size",
        hex(SLOT1_SIZE),
        "--header-size",
        "0x800",
        "--align",
        "16",
        "--rom-fixed",
        "0x10000",
        "--key",
        str(wrong_key),
        "--security-counter",
        "2",
        str(inputs.raw.path),
        str(output),
    )
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=60.0,
            check=False,
            env=imgtool_environment(imgtool_python),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise M30BootFailure(f"wrong-key image 생성 실패: {error}") from error
    if result.returncode != 0:
        message = (result.stdout + result.stderr).decode(
            "utf-8", errors="backslashreplace"
        )
        raise M30BootFailure(f"wrong-key image 서명 실패: {message}")
    return immutable_image(output, expected_version=WRONG_KEY_VERSION)


def imgtool_environment(imgtool_python: Path) -> dict[str, str]:
    """! @brief imgtool 자식에만 NCS toolchain Python 환경을 격리합니다. """

    bundle = imgtool_python.resolve().parents[2]
    descriptor = bundle / "environment.json"
    try:
        document = json.loads(descriptor.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M30BootFailure(f"toolchain environment를 읽지 못했습니다: {error}") from error
    specifications = document.get("env_vars")
    if not isinstance(specifications, list):
        raise M30BootFailure("toolchain environment의 env_vars가 배열이 아닙니다.")
    environment = os.environ.copy()
    for specification in specifications:
        if not isinstance(specification, dict):
            raise M30BootFailure("toolchain environment 항목이 객체가 아닙니다.")
        key = specification.get("key")
        if not isinstance(key, str) or not key:
            raise M30BootFailure("toolchain environment key가 잘못됐습니다.")
        if specification.get("type") == "relative_paths":
            values = specification.get("values")
            if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values
            ):
                raise M30BootFailure(f"toolchain environment path가 잘못됐습니다: {key}")
            value = os.pathsep.join(str(bundle / item) for item in values)
            if specification.get("existing_value_treatment") == "prepend_to":
                existing = environment.get(key)
                if existing:
                    value = f"{value}{os.pathsep}{existing}"
        else:
            value = specification.get("value")
            if not isinstance(value, str):
                raise M30BootFailure(f"toolchain environment value가 잘못됐습니다: {key}")
        environment[key] = value
    return environment


def pyocd_command_prefix(subcommand: str, board_id: str) -> tuple[str, ...]:
    """! @brief subcommand 뒤 exact UID·no auto unlock 인자를 반환합니다. """

    return (
        sys.executable,
        "-I",
        "-m",
        "pyocd",
        subcommand,
        "--uid",
        board_id,
        "--target",
        "nrf54l",
        "--frequency",
        "500000",
        "-O",
        "cmsis_dap.limit_packets=true",
        "-O",
        "auto_unlock=false",
    )


def run_pyocd(command: Sequence[str], label: str, timeout_seconds: float) -> bytes:
    """! @brief bounded pyOCD 명령을 실행하고 전체 출력을 반환합니다. """

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise M30BootFailure(f"{label} 실패: {error}") from error
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise M30BootFailure(
            f"{label} 실패: {output.decode('utf-8', errors='backslashreplace')}"
        )
    return output


def erase_secondary_slot(board_id: str, timeout_seconds: float) -> None:
    """! @brief secondary slot의 exact sector 범위만 지웁니다. """

    command = (
        *pyocd_command_prefix("erase", board_id),
        "--sector",
        f"{hex(SLOT1_OFFSET)}-{hex(SLOT1_END)}",
    )
    run_pyocd(command, "secondary exact-sector erase", timeout_seconds)


def flash_secondary_binary(
    board_id: str, image: Path, timeout_seconds: float, label: str
) -> str:
    """! @brief secondary offset에 binary를 sector erase 방식으로 기록합니다. """

    command = (
        *pyocd_command_prefix("flash", board_id),
        "--erase",
        "sector",
        "--format",
        "bin",
        "--base-address",
        hex(SLOT1_OFFSET),
        str(image),
    )
    output = run_pyocd(command, f"{label} secondary flash", timeout_seconds)
    match = re.search(rb"programmed\s+(\d+)\s+bytes", output)
    if match is None:
        raise M30BootFailure(f"{label} pyOCD programmed byte 증거가 없습니다.")
    return match.group(1).decode("ascii")


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
                raise M30BootFailure("미완성 UART line이 허용 크기를 넘었습니다.")
    raise M30BootFailure("M30-BOOT-01 UART token timeout")


def capture_line(capture: bytearray, line: bytes) -> None:
    """! @brief ASCII protocol line을 bounded transcript에 추가합니다. """

    try:
        decoded = line.decode("ascii")
    except UnicodeDecodeError as error:
        raise M30BootFailure("MCUboot protocol line이 ASCII가 아닙니다.") from error
    capture.extend(line + b"\n")
    if len(capture) > MAX_TRANSCRIPT_BYTES:
        raise M30BootFailure("MCUboot transcript가 허용 크기를 넘었습니다.")
    print(f"M30_BOOT_PROGRESS={decoded}", flush=True)


def send_line(serial_port: Any, line: str) -> None:
    """! @brief 완전한 ASCII command를 한 번에 VCOM으로 기록합니다. """

    data = (line + "\r\n").encode("ascii")
    if serial_port.write(data) != len(data):
        raise M30BootFailure("VCOM command가 일부만 기록됐습니다.")
    serial_port.flush()


READY_PATTERN = re.compile(
    rb"^M30BOOT\|1\|READY\|active_slot=(\d+)\|confirmed=(\d+)"
    rb"\|confirm_rc=(-?\d+)\|version=(\d+)\.(\d+)\.(\d+)\+(\d+)"
    rb"\|core=([0-9a-f]{40})$"
)


def parse_ready(line: bytes) -> ReadyRecord:
    """! @brief exact READY record를 정량 객체로 변환합니다. """

    match = READY_PATTERN.fullmatch(line)
    if match is None:
        raise M30BootFailure(f"READY record가 잘못됐습니다: {line!r}")
    values = [int(value) for value in match.groups()[:7]]
    return ReadyRecord(
        active_slot=values[0],
        confirmed=values[1],
        confirm_rc=values[2],
        version=(values[3], values[4], values[5], values[6]),
        core_revision=match.group(8).decode("ascii"),
    )


def wait_ready(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    core_revision: str,
) -> ReadyRecord:
    """! @brief boot noise를 건너뛰고 exact READY 또는 FAIL을 찾습니다. """

    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line.startswith(PROTOCOL_PREFIX):
            capture_line(capture, line)
        if line.startswith(FAIL_PREFIX):
            raise M30BootFailure(f"target 실패: {line!r}")
        if line.startswith(b"M30BOOT|1|READY|"):
            ready = parse_ready(line)
            if ready.core_revision != core_revision:
                raise M30BootFailure("READY Core revision이 current exact commit과 다릅니다.")
            if ready.confirmed != 1 or ready.confirm_rc != 0:
                raise M30BootFailure(f"실행 image가 confirmed 상태가 아닙니다: {ready}")
            return ready


def wait_exact(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    expected: bytes,
    deadline: float,
) -> None:
    """! @brief boot noise 뒤 exact protocol record 하나를 기다립니다. """

    while True:
        line = read_wire_line(serial_port, pending, deadline)
        if line.startswith(PROTOCOL_PREFIX):
            capture_line(capture, line)
        if line == expected:
            return
        if line.startswith(FAIL_PREFIX):
            raise M30BootFailure(f"target 실패: {line!r}")
        if line.startswith(PROTOCOL_PREFIX):
            raise M30BootFailure(f"예상 밖 protocol record입니다: {line!r}")


def open_serial(serial_module: Any, endpoint: RoleEndpoint, baud: int) -> Any:
    """! @brief exact target VCOM을 bounded read/write 설정으로 엽니다. """

    if baud != DEFAULT_BAUD_RATE:
        raise M30BootFailure(f"M30-BOOT-01은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    return serial_module.Serial(
        endpoint.port_name,
        baudrate=baud,
        timeout=0.05,
        write_timeout=2.0,
    )


def query_ready(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    core_revision: str,
) -> ReadyRecord:
    """! @brief PING으로 현재 image 상태를 능동 조회합니다. """

    send_line(serial_port, "M30BOOT|1|PING")
    return wait_ready(serial_port, pending, capture, deadline, core_revision)


def synchronize_ready(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    core_revision: str,
) -> ReadyRecord:
    """! @brief port-open reset의 자동 READY 뒤에만 명령 전송을 시작합니다. """

    startup_deadline = min(deadline, time.monotonic() + 5.0)
    try:
        return wait_ready(
            serial_port, pending, capture, startup_deadline, core_revision
        )
    except M30BootFailure as error:
        if "UART token timeout" not in str(error):
            raise
    return query_ready(serial_port, pending, capture, deadline, core_revision)


def warm_reboot(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    core_revision: str,
) -> ReadyRecord:
    """! @brief warm reboot acknowledgement와 다음 READY를 검증합니다. """

    suffix = f"|core={core_revision}".encode("ascii")
    send_line(serial_port, "M30BOOT|1|REBOOT")
    wait_exact(
        serial_port,
        pending,
        capture,
        b"M30BOOT|1|REBOOTING" + suffix,
        deadline,
    )
    return wait_ready(serial_port, pending, capture, deadline, core_revision)


def request_test_upgrade(
    serial_port: Any,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    core_revision: str,
) -> None:
    """! @brief secondary image를 1회 test upgrade로 표시합니다. """

    send_line(serial_port, "M30BOOT|1|REQUEST_TEST")
    wait_exact(
        serial_port,
        pending,
        capture,
        f"M30BOOT|1|REQUEST_TEST|rc=0|core={core_revision}".encode("ascii"),
        deadline,
    )


def exercise_current_image(
    serial_module: Any,
    endpoint: RoleEndpoint,
    baud: int,
    capture: bytearray,
    deadline: float,
    core_revision: str,
    reboots: int,
) -> list[ReadyRecord]:
    """! @brief 현재 image의 initial query와 지정 횟수 warm boot를 수집합니다. """

    records: list[ReadyRecord] = []
    with open_serial(serial_module, endpoint, baud) as serial_port:
        serial_port.reset_input_buffer()
        pending = bytearray()
        records.append(
            synchronize_ready(
                serial_port, pending, capture, deadline, core_revision
            )
        )
        for _index in range(reboots):
            records.append(
                warm_reboot(serial_port, pending, capture, deadline, core_revision)
            )
    return records


def exercise_candidate(
    serial_module: Any,
    endpoint: RoleEndpoint,
    baud: int,
    capture: bytearray,
    deadline: float,
    core_revision: str,
) -> ReadyRecord:
    """! @brief secondary test request 뒤 boot된 image 상태를 반환합니다. """

    with open_serial(serial_module, endpoint, baud) as serial_port:
        serial_port.reset_input_buffer()
        pending = bytearray()
        baseline = synchronize_ready(
            serial_port, pending, capture, deadline, core_revision
        )
        if baseline.version != PRIMARY_VERSION:
            raise M30BootFailure(f"candidate 전 primary version이 다릅니다: {baseline}")
        request_test_upgrade(serial_port, pending, capture, deadline, core_revision)
        return warm_reboot(serial_port, pending, capture, deadline, core_revision)


def endpoint_evidence(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief raw UID 없이 exact volume·COM·UID hash를 기록합니다. """

    match = re.match(r"^([A-Za-z]):(?:[\\/]|$)", str(endpoint.volume.root))
    if match is None:
        raise M30BootFailure("DAPLink volume이 Windows drive root가 아닙니다.")
    return {
        "board_id_sha256": hashlib.sha256(endpoint.board_id.encode("ascii")).hexdigest(),
        "volume": f"{match.group(1).upper()}:",
        "port": endpoint.port_name,
    }


def image_evidence(image: ImageInput) -> dict[str, Any]:
    """! @brief key 경로 없는 image byte identity를 반환합니다. """

    return {
        "name": image.path.name,
        "size": image.size,
        "sha256": image.sha256,
        "version": list(image.version) if image.version is not None else None,
    }


def output_paths(argument: str | None, overwrite: bool) -> tuple[Path, Path]:
    """! @brief 신규 JSON과 raw transcript 경로를 준비합니다. """

    if not argument:
        raise M30BootFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.casefold() != ".json":
        raise M30BootFailure("--evidence는 .json 파일이어야 합니다.")
    transcript = evidence.with_name(f"{evidence.stem}.transcript.log")
    paths = (evidence, transcript)
    if any(path.exists() for path in paths) and not overwrite:
        raise M30BootFailure("기존 M30-BOOT-01 증적을 덮어쓰지 않습니다.")
    for path in paths:
        if path.exists():
            if not path.is_file():
                raise M30BootFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
            path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return paths


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief preflight 또는 실제 M30-BOOT-01을 실행하고 증적을 기록합니다. """

    args = parse_arguments(arguments)
    if not 60.0 <= args.result_timeout <= 900.0:
        raise M30BootFailure("--result-timeout은 60..900초여야 합니다.")
    serial_module, list_ports = import_pyserial()
    endpoint = discover_endpoint(args.board_id, args.volume, args.port, list_ports)
    if args.discover_only:
        print("M30_BOOT_DISCOVERY_PASS=1")
        return 0

    validate_source_clean(MILESTONE, APPLICATION_ROOT, RUNNER_PATH)
    core_revision = git_revision(REPOSITORY)
    if args.expected_core_revision and args.expected_core_revision != core_revision:
        raise M30BootFailure("현재 Core revision이 --expected-core-revision과 다릅니다.")
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    trust_key = validate_private_key(args.trust_signing_key, "trust signing key")
    wrong_key = validate_private_key(args.wrong_signing_key, "wrong signing key")
    if trust_key.read_bytes() == wrong_key.read_bytes():
        raise M30BootFailure("trust key와 wrong key가 같습니다.")
    inputs = collect_build_inputs(args.build_outdir, core_revision, trust_key)
    evidence_path, transcript_path = output_paths(
        args.evidence, args.overwrite_evidence
    )
    capture = bytearray()
    started = time.monotonic()
    deadline = started + args.result_timeout
    flash_results: dict[str, Any] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="n54-m30-wrong-") as directory:
            wrong = create_wrong_key_image(
                inputs,
                wrong_key,
                Path(args.imgtool_python).resolve(),
                Path(args.imgtool).resolve(),
                Path(directory) / "wrong-key-v9.bin",
            )
            erase_secondary_slot(endpoint.board_id, args.flash_timeout)
            flash_results["boot"] = flash_image_pyocd(
                "bootloader", endpoint.board_id, inputs.boot.path, args.flash_timeout
            )
            flash_results["primary"] = flash_image_pyocd(
                "signed-primary",
                endpoint.board_id,
                inputs.signed_hex.path,
                args.flash_timeout,
            )
            boot_records = exercise_current_image(
                serial_module,
                endpoint,
                args.baud,
                capture,
                deadline,
                core_revision,
                SIGNED_BOOTS - 1,
            )
            signed_boots = sum(
                record.version == PRIMARY_VERSION for record in boot_records
            )

            erase_secondary_slot(endpoint.board_id, args.flash_timeout)
            flash_results["unsigned_secondary_bytes"] = flash_secondary_binary(
                endpoint.board_id,
                inputs.raw.path,
                args.flash_timeout,
                "unsigned",
            )
            unsigned_result = exercise_candidate(
                serial_module,
                endpoint,
                args.baud,
                capture,
                deadline,
                core_revision,
            )
            unsigned_accepts = int(unsigned_result.version != PRIMARY_VERSION)

            erase_secondary_slot(endpoint.board_id, args.flash_timeout)
            flash_results["wrong_key_secondary_bytes"] = flash_secondary_binary(
                endpoint.board_id,
                wrong.path,
                args.flash_timeout,
                "wrong-key",
            )
            wrong_result = exercise_candidate(
                serial_module,
                endpoint,
                args.baud,
                capture,
                deadline,
                core_revision,
            )
            wrong_key_accepts = int(wrong_result.version != PRIMARY_VERSION)
            wrong_evidence = image_evidence(wrong)
            validate_image_unchanged(wrong.path, wrong.size, wrong.sha256)
    except Exception as error:
        transcript_path.write_bytes(capture)
        if isinstance(error, (M30BootFailure, BlePairHilFailure)):
            raise M30BootFailure(
                f"{error}; 실패 transcript: {transcript_path.name}"
            ) from error
        raise

    for image in (inputs.boot, inputs.signed, inputs.signed_hex, inputs.raw):
        validate_image_unchanged(image.path, image.size, image.sha256)
    if signed_boots != SIGNED_BOOTS:
        raise M30BootFailure(f"signed boot 수가 다릅니다: {signed_boots}")
    if unsigned_accepts != 0 or wrong_key_accepts != 0:
        raise M30BootFailure(
            f"부정 image가 수락됐습니다: unsigned={unsigned_accepts}, "
            f"wrong_key={wrong_key_accepts}"
        )

    duration = time.monotonic() - started
    transcript_path.write_bytes(capture)
    evidence = {
        "schema_version": 1,
        "test_id": "M30-BOOT-01",
        "status": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 3),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "boards": 1,
        "signed_boots": signed_boots,
        "unsigned_accepts": unsigned_accepts,
        "wrong_key_accepts": wrong_key_accepts,
        "endpoint": endpoint_evidence(endpoint),
        "images": {
            "bootloader": image_evidence(inputs.boot),
            "primary_signed": image_evidence(inputs.signed),
            "primary_signed_hex": image_evidence(inputs.signed_hex),
            "unsigned_candidate": image_evidence(inputs.raw),
            "wrong_key_candidate": wrong_evidence,
        },
        "trust_public_key_source_sha256": inputs.public_key_sha256,
        "flash_backend": "pyocd-exact-sector",
        "flash_results": flash_results,
        "secondary_slot": {
            "offset": SLOT1_OFFSET,
            "size": SLOT1_SIZE,
            "erase_end_exclusive": SLOT1_END,
        },
        "power_cut_injected": False,
        "physical_power_loss_claim": False,
        "mass_erase_or_recover": False,
        "transcript": transcript_record(transcript_path, capture),
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("M30_BOOT_HIL_PASS=20;UNSIGNED_ACCEPTS=0;WRONG_KEY_ACCEPTS=0;POWER_CUT=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (M30BootFailure, BlePairHilFailure) as error:
        print(f"M30_BOOT_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
