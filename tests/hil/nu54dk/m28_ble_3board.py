#!/usr/bin/env python3
"""! @brief 세 NU54DK의 M28 LINK·PER·CTRL·SOAK HIL을 자동 검증합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import string
import subprocess
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
    protocol_lines,
    take_exact,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_source_clean,
)
from m6_serial_echo import (  # noqa: E402
    DaplinkVolume,
    detail_value,
    find_serial_port,
    import_pyserial,
    normalize_board_id,
    read_details,
)


MILESTONE = "M28B3"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m28_ble_3board_hil"
EVIDENCE_SCHEMA = 1
ROLES = ("peripheral", "mixed", "central")
TEST_NAMES = {
    "M28-LINK-01": "LINK",
    "M28-PER-01": "PER",
    "M28-CTRL-01": "CTRL",
    "M28-SOAK-01": "SOAK",
}
DEFAULT_TIMEOUTS = {
    "M28-LINK-01": 1200.0,
    "M28-PER-01": 900.0,
    "M28-CTRL-01": 900.0,
    "M28-SOAK-01": 2100.0,
}
SWD_DP_IDCODE = "0x6ba02477"
PY_OCD_AHB_AP_IDR = 0x84770001
PY_OCD_CTRL_AP_IDR = 0x32880000
PY_OCD_CSW_DEVICE_ENABLE = 0x00000040


class ThreeBoardExecutionFailure(BlePairHilFailure):
    """! @brief 실행 오류와 실패 시점의 세 raw transcript를 보존합니다. """

    def __init__(self, message: str, transcripts: dict[str, bytes]) -> None:
        super().__init__(message)
        self.transcripts = transcripts


@dataclass(frozen=True)
class ThreeBoardExecution:
    """! @brief 세 role의 exact image flash와 UART 결과입니다. """

    peripheral: RoleExecution
    mixed: RoleExecution
    central: RoleExecution


@dataclass(frozen=True)
class M28ThreeBoardRoleResult:
    """! @brief 한 role의 고정 protocol 정량 결과입니다. """

    role: str
    test_id: str
    metrics: dict[str, int | str]


## @brief pyOCD backend에서 UID·전압·SWD DP가 일치하는 MSD를 찾습니다.
def find_pyocd_volume(board_id: str, explicit_volume: str | None) -> DaplinkVolume:
    roots = (
        (Path(explicit_volume).resolve(),)
        if explicit_volume
        else tuple(Path(f"{letter}:/") for letter in string.ascii_uppercase)
    )
    candidates: list[DaplinkVolume] = []
    rejected: list[str] = []
    for root in roots:
        details = read_details(root)
        if details is None or (detail_value(details, "Unique ID") or "").lower() != board_id:
            continue
        target = detail_value(details, "Target Detect")
        idcode = (detail_value(details, "SWD DP IDCODE") or "").lower()
        voltage = detail_value(details, "Target Voltage") or ""
        voltage_match = re.fullmatch(r"([0-9]+) mV \(present\)", voltage)
        voltage_mv = int(voltage_match.group(1)) if voltage_match else 0
        if (
            target not in ("nRF54L15", "unsupported target")
            or idcode != SWD_DP_IDCODE
            or not 2800 <= voltage_mv <= 3600
        ):
            rejected.append(
                f"{root}(target={target}, idcode={idcode}, voltage={voltage})"
            )
            continue
        candidates.append(DaplinkVolume(root=root, details=details))
    if len(candidates) != 1:
        roots_text = ", ".join(str(candidate.root) for candidate in candidates) or "없음"
        rejected_text = "; ".join(rejected) or "없음"
        raise BlePairHilFailure(
            "pyOCD용 UID·전압·SWD DP 일치 MSD가 정확히 하나여야 합니다: "
            f"발견={len(candidates)}, 후보={roots_text}, 거부={rejected_text}"
        )
    return candidates[0]


## @brief flash backend별 fail-closed 장치 탐색 경계를 적용합니다.
def discover_role_endpoint(
    board_id: str,
    explicit_volume: str | None,
    explicit_port: str,
    list_ports: Any,
    flash_backend: str,
) -> RoleEndpoint:
    if flash_backend != "pyocd-sector":
        return discover_endpoint(board_id, explicit_volume, explicit_port, list_ports)
    normalized = normalize_board_id(board_id)
    return RoleEndpoint(
        normalized,
        find_pyocd_volume(normalized, explicit_volume),
        find_serial_port(normalized, explicit_port, list_ports),
    )


## @brief pyOCD low-level 출력에서 Nordic nRF54L·AP·보호 상태를 검증합니다.
def parse_pyocd_identity(output: str) -> dict[str, str]:
    patterns = {
        "target_id": r"DP register 0x24 = 0x([0-9a-fA-F]{8})",
        "ahb_ap_idr": r"AP register 0xfc = 0x([0-9a-fA-F]{8})",
        "ahb_ap_csw": r"AP register 0x0 = 0x([0-9a-fA-F]{8})",
        "ctrl_ap_idr": r"AP register 0x20000fc = 0x([0-9a-fA-F]{8})",
        "approtect_status": r"AP register 0x2000014 = 0x([0-9a-fA-F]{8})",
    }
    values: dict[str, int] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match is None:
            raise BlePairHilFailure(f"pyOCD identity record 누락: {key}")
        values[key] = int(match.group(1), 16)
    target_id = values["target_id"]
    if target_id & 0xFFF != 0x289 or target_id & 0xF0000 != 0xC0000:
        raise BlePairHilFailure(f"Nordic nRF54L TARGETID 불일치: 0x{target_id:08x}")
    if values["ahb_ap_idr"] != PY_OCD_AHB_AP_IDR:
        raise BlePairHilFailure(
            f"nRF54L AHB-AP IDR 불일치: 0x{values['ahb_ap_idr']:08x}"
        )
    if values["ctrl_ap_idr"] != PY_OCD_CTRL_AP_IDR:
        raise BlePairHilFailure(
            f"nRF54L CTRL-AP IDR 불일치: 0x{values['ctrl_ap_idr']:08x}"
        )
    if values["ahb_ap_csw"] & PY_OCD_CSW_DEVICE_ENABLE == 0:
        raise BlePairHilFailure("nRF54L AHB-AP가 보호 상태입니다.")
    if values["approtect_status"] != 0:
        raise BlePairHilFailure(
            f"nRF54L APPROTECT가 활성 상태입니다: 0x{values['approtect_status']:08x}"
        )
    return {key: f"0x{value:08x}" for key, value in values.items()}


## @brief 실행 중인 target을 멈추지 않고 DP·AP identity를 UID에 결합합니다.
def probe_pyocd_identity(board_id: str) -> dict[str, str]:
    command = (
        sys.executable,
        "-I",
        "-m",
        "pyocd",
        "commander",
        "--uid",
        board_id,
        "--target",
        "nrf54l",
        "--frequency",
        "100000",
        "-O",
        "cmsis_dap.limit_packets=true",
        "-O",
        "auto_unlock=false",
        "--no-init",
    )
    commands = "\n".join(
        (
            "initdp",
            "makeap 0",
            "makeap 2",
            "readdp 0x24",
            "readap 0 0xfc",
            "readap 0 0x00",
            "readap 2 0xfc",
            "readap 2 0x14",
            "exit",
            "",
        )
    )
    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        input=commands,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        env=environment,
    )
    output = result.stdout + "\n" + result.stderr
    if result.returncode != 0:
        raise BlePairHilFailure(
            f"pyOCD identity probe 실패: uid={board_id}, rc={result.returncode}"
        )
    return parse_pyocd_identity(output)


## @brief DAPLink가 직접 판독한 target identity를 고정 필드로 보존합니다.
def daplink_debug_identity(endpoint: RoleEndpoint) -> dict[str, str]:
    target = detail_value(endpoint.volume.details, "Target Detect") or ""
    idcode = (detail_value(endpoint.volume.details, "SWD DP IDCODE") or "").lower()
    voltage = detail_value(endpoint.volume.details, "Target Voltage") or ""
    voltage_match = re.fullmatch(r"([0-9]+) mV \(present\)", voltage)
    voltage_mv = int(voltage_match.group(1)) if voltage_match else 0
    if target != "nRF54L15":
        raise BlePairHilFailure(f"DAPLink nRF54L15 target 불일치: {target or '누락'}")
    if idcode != SWD_DP_IDCODE:
        raise BlePairHilFailure(f"DAPLink SWD DP IDCODE 불일치: {idcode or '누락'}")
    if not 2800 <= voltage_mv <= 3600:
        raise BlePairHilFailure(f"DAPLink target 전압 범위 불일치: {voltage or '누락'}")
    return {
        "source": "daplink-details",
        "target": target,
        "swd_dp_idcode": idcode,
        "target_voltage": voltage,
    }


## @brief flash backend에 맞는 비파괴 debug identity 검사를 선택합니다.
def collect_debug_identities(
    endpoints: dict[str, RoleEndpoint], flash_backend: str
) -> dict[str, dict[str, str]]:
    if flash_backend == "pyocd-sector":
        return {
            role: {"source": "pyocd-direct", **probe_pyocd_identity(endpoint.board_id)}
            for role, endpoint in endpoints.items()
        }
    return {
        role: daplink_debug_identity(endpoint) for role, endpoint in endpoints.items()
    }


## @brief 세 role의 UID·image·timeout·evidence 인자를 선언합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="세 NU54DK로 M28 mixed-role LINK/PER/CTRL/SOAK를 검증합니다."
    )
    parser.add_argument("--test-id", choices=tuple(TEST_NAMES), required=True)
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
    parser.add_argument("--result-timeout", type=float)
    parser.add_argument("--evidence")
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


## @brief 세 role이 서로 다른 UID·MSD·UART에 정확히 결합됐는지 검사합니다.
def validate_three_board_identity(endpoints: dict[str, RoleEndpoint]) -> None:
    for attribute, label in (
        ("board_id", "DAPLink UID"),
        ("port_name", "UART"),
    ):
        values = [str(getattr(endpoints[role], attribute)).casefold() for role in ROLES]
        if len(set(values)) != len(ROLES):
            raise BlePairHilFailure(f"세 role의 {label}가 서로 달라야 합니다.")
    volumes = [str(endpoints[role].volume.root.resolve()).casefold() for role in ROLES]
    if len(set(volumes)) != len(ROLES):
        raise BlePairHilFailure("세 role의 DAPLink MSD가 서로 달라야 합니다.")


## @brief evidence와 세 raw transcript의 신규 출력 경로를 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, dict[str, Path]]:
    if not evidence_argument:
        raise BlePairHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise BlePairHilFailure("--evidence는 .json 파일이어야 합니다.")
    transcripts = {
        role: evidence.with_name(f"{evidence.stem}.{role}.transcript.log")
        for role in ROLES
    }
    paths = (evidence, *transcripts.values())
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise BlePairHilFailure(
            "기존 증적을 덮어쓰지 않습니다: "
            + ", ".join(str(path) for path in existing)
        )
    for path in existing:
        if not path.is_file():
            raise BlePairHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing:
            path.unlink()
    return evidence, transcripts


## @brief test·role에 맞는 READY 또는 ADVERTISE exact token까지 수집합니다.
def wait_exact_token(
    serial_port: Any,
    role: str,
    expected: bytes,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    prefix = b"NUCODE_M28B3_"
    fail_prefix = b"NUCODE_M28B3_FAIL:"
    while True:
        line = common.read_line(serial_port, pending, capture, deadline)
        if line.startswith(fail_prefix):
            raise BlePairHilFailure(f"{role} target 실패: {line!r}")
        if line.startswith(prefix) and line != expected:
            raise BlePairHilFailure(
                f"{role} 기대 token 앞 stale/예상 밖 protocol입니다: {line!r}"
            )
        if line == expected:
            return


## @brief 현재 test·nonce START command를 한 role UART에 기록합니다.
def write_start_command(serial_port: Any, test_name: str, nonce: str) -> None:
    request = f"NUCODE_M28B3_START:{test_name}:{nonce}\r\n".encode("ascii")
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise BlePairHilFailure("M28 3보드 START command가 일부만 기록됐습니다.")


## @brief 한 role의 현재 test·nonce FINAL까지 raw UART를 수집합니다.
def collect_until_final(
    serial_port: Any,
    role: str,
    test_name: str,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    final = (
        f"NUCODE_M28B3_{role}:FINAL:PASS:test={test_name}:nonce={nonce}"
    ).encode("ascii")
    fail_prefix = b"NUCODE_M28B3_FAIL:"
    try:
        while True:
            line = common.read_line(
                serial_port,
                pending,
                capture,
                deadline,
                stop_event=stop_event,
            )
            if line:
                print(f"[{role}] {line.decode('utf-8', errors='backslashreplace')}")
            if line.startswith(fail_prefix):
                raise BlePairHilFailure(f"{role} target 실패: {line!r}")
            if line == final:
                return
            if line.startswith(b"NUCODE_M28B3_") and not line.endswith(
                f":nonce={nonce}".encode("ascii")
            ):
                raise BlePairHilFailure(f"{role} stale nonce token입니다: {line!r}")
    except Exception:
        stop_event.set()
        raise


## @brief 세 image를 exact UID에 기록하고 순차 START 뒤 FINAL을 동시 수집합니다.
def execute_three_board(
    *,
    serial_module: Any,
    endpoints: dict[str, RoleEndpoint],
    images: dict[str, Path],
    test_name: str,
    nonce: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
    flash_backend: str,
) -> ThreeBoardExecution:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 2200.0:
        raise BlePairHilFailure("--result-timeout은 30..2200초여야 합니다.")
    captures = {role: bytearray() for role in ROLES}
    pending = {role: bytearray() for role in ROLES}
    flashes = {role: ("not-started", "unknown") for role in ROLES}
    try:
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

            deadline = time.monotonic() + result_timeout
            for role in ROLES:
                ready = (
                    f"NUCODE_M28B3_READY:role={role}:test={test_name}"
                ).encode("ascii")
                wait_exact_token(
                    ports[role], role, ready, pending[role], captures[role], deadline
                )

            suffix = f":test={test_name}:nonce={nonce}".encode("ascii")
            write_start_command(ports["peripheral"], test_name, nonce)
            wait_exact_token(
                ports["peripheral"],
                "peripheral",
                b"NUCODE_M28B3_peripheral:ADVERTISE:PASS" + suffix,
                pending["peripheral"],
                captures["peripheral"],
                deadline,
            )
            write_start_command(ports["mixed"], test_name, nonce)
            wait_exact_token(
                ports["mixed"],
                "mixed",
                b"NUCODE_M28B3_mixed:ADVERTISE:PASS" + suffix,
                pending["mixed"],
                captures["mixed"],
                deadline,
            )
            write_start_command(ports["central"], test_name, nonce)

            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(
                        collect_until_final,
                        ports[role],
                        role,
                        test_name,
                        nonce,
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
        raise ThreeBoardExecutionFailure(
            str(error), {role: bytes(captures[role]) for role in ROLES}
        ) from error

    records = {
        role: RoleExecution(*flashes[role], bytes(captures[role])) for role in ROLES
    }
    return ThreeBoardExecution(**records)


## @brief regex 한 줄을 strict 순서로 소비하고 named 정수를 반환합니다.
def take_pattern(
    lines: list[bytes], cursor: int, pattern: bytes
) -> tuple[int, re.Match[bytes]]:
    if cursor >= len(lines):
        raise BlePairHilFailure(f"protocol 정규식 line 누락: {pattern!r}")
    match = re.fullmatch(pattern, lines[cursor])
    if match is None:
        raise BlePairHilFailure(
            f"protocol 정규식 불일치: pattern={pattern!r}, actual={lines[cursor]!r}"
        )
    return cursor + 1, match


## @brief 한 role의 fixed protocol 순서·수치·nonce를 fail-closed로 검증합니다.
def parse_role_transcript(
    transcript: bytes, nonce: str, test_id: str, role: str
) -> M28ThreeBoardRoleResult:
    nonce = build_nonce(nonce)
    if test_id not in TEST_NAMES or role not in ROLES:
        raise BlePairHilFailure(f"알 수 없는 M28 3보드 test/role입니다: {test_id}/{role}")
    test_name = TEST_NAMES[test_id]
    suffix = f":nonce={nonce}".encode("ascii")
    lines = protocol_lines(transcript, MILESTONE, nonce)
    cursor = take_exact(
        lines,
        0,
        f"NUCODE_M28B3_READY:role={role}:test={test_name}".encode("ascii"),
    )
    if role in ("peripheral", "mixed"):
        cursor = take_exact(
            lines,
            cursor,
            f"NUCODE_M28B3_{role}:ADVERTISE:PASS:test={test_name}".encode("ascii")
            + suffix,
        )
    metrics: dict[str, int | str] = {}

    if test_name == "LINK":
        expected_tx = 1000 if role in ("mixed", "central") else 0
        expected_rx = 1000 if role in ("peripheral", "mixed") else 0
        cursor = take_exact(
            lines,
            cursor,
            (
                f"NUCODE_M28B3_{role}:TRACE:PASS:test=LINK:source=rf-gatt"
                f":tx={expected_tx}:rx={expected_rx}"
            ).encode("ascii")
            + suffix,
        )
        if role == "mixed":
            result = (
                b"NUCODE_M28B3_mixed:LINK:PASS:links=2:central=1:peripheral=1"
                b":reconnects_per_link=20:sequence_per_link=1000"
            )
        else:
            result = (
                f"NUCODE_M28B3_{role}:LINK:PASS:links=1:reconnects=20"
                ":sequence=1000"
            ).encode("ascii")
        cursor = take_exact(
            lines,
            cursor,
            result
            + b":loss=0:corrupt=0:duplicate=0:stale=0:drops=0"
            + suffix,
        )
        metrics = {"links": 2 if role == "mixed" else 1, "sequence": 1000}
    elif test_name == "PER":
        if role == "peripheral":
            cursor = take_exact(
                lines,
                cursor,
                b"NUCODE_M28B3_peripheral:PERIODIC:STARTED:sid=7" + suffix,
            )
            cursor = take_exact(
                lines,
                cursor,
                b"NUCODE_M28B3_peripheral:PER:PASS:emitted=1000:corrupt=0:drops=0"
                + suffix,
            )
            metrics = {"emitted": 1000}
        elif role == "mixed":
            cursor = take_exact(
                lines,
                cursor,
                b"NUCODE_M28B3_mixed:PERIODIC:SYNCED:sid=7" + suffix,
            )
            cursor, match = take_pattern(
                lines,
                cursor,
                (
                    rb"NUCODE_M28B3_mixed:PER:PASS:past_sent=20"
                    rb":source_reports=([0-9]+):corrupt=0:drops=0:nonce="
                    + nonce.encode("ascii")
                ),
            )
            source_reports = int(match.group(1))
            if source_reports < 1:
                raise BlePairHilFailure("mixed periodic source report가 없습니다.")
            metrics = {"past_sent": 20, "source_reports": source_reports}
        else:
            pattern = (
                rb"NUCODE_M28B3_central:TRACE:PASS:test=PER:source=rf-periodic"
                rb":denominator=1000:received=([0-9]+):loss=([0-9]+):nonce="
                + nonce.encode("ascii")
            )
            cursor, match = take_pattern(lines, cursor, pattern)
            reports = int(match.group(1))
            loss = int(match.group(2))
            if reports < 990 or reports > 1000 or loss != 1000 - reports:
                raise BlePairHilFailure(
                    f"periodic 수신률/분모 불일치: reports={reports}, loss={loss}"
                )
            cursor = take_exact(
                lines,
                cursor,
                (
                    f"NUCODE_M28B3_central:PER:PASS:reports={reports}"
                    f":denominator=1000:loss={loss}:corrupt=0:past=20:drops=0"
                ).encode("ascii")
                + suffix,
            )
            metrics = {"reports": reports, "loss": loss, "past_received": 20}
    elif test_name == "CTRL":
        if role == "mixed":
            cursor = take_exact(
                lines,
                cursor,
                (
                    b"NUCODE_M28B3_mixed:CTRL:PASS:links=2:requests_per_link=20"
                    b":cross_state=0:stale=0:unreported_driver=0"
                    b":unexpected_disconnect=0:drops=0"
                )
                + suffix,
            )
            metrics = {"links": 2, "requests_per_link": 20}
        else:
            cursor = take_exact(
                lines,
                cursor,
                (
                    f"NUCODE_M28B3_{role}:CTRL:PASS:links=1:rounds=20"
                    ":unexpected_disconnect=0:drops=0"
                ).encode("ascii")
                + suffix,
            )
            metrics = {"links": 1, "rounds": 20}
    else:
        expected_tx = 10000 if role in ("mixed", "central") else 0
        expected_rx = 10000 if role in ("peripheral", "mixed") else 0
        cursor = take_exact(
            lines,
            cursor,
            (
                f"NUCODE_M28B3_{role}:TRACE:PASS:test=SOAK:source=rf-gatt"
                f":tx={expected_tx}:rx={expected_rx}"
            ).encode("ascii")
            + suffix,
        )
        if role == "mixed":
            result = (
                b"NUCODE_M28B3_mixed:SOAK:PASS:duration_s=1800:links=2"
                b":sequence_per_link=10000"
            )
        else:
            result = (
                f"NUCODE_M28B3_{role}:SOAK:PASS:duration_s=1800:links=1"
                ":sequence=10000"
            ).encode("ascii")
        cursor = take_exact(
            lines,
            cursor,
            result
            + b":loss=0:corrupt=0:duplicate=0:unexpected_disconnect=0"
            + b":recovery_failures=0:drops=0"
            + suffix,
        )
        metrics = {
            "duration_seconds": 1800,
            "links": 2 if role == "mixed" else 1,
            "sequence": 10000,
        }

    cursor = take_exact(
        lines,
        cursor,
        f"NUCODE_M28B3_{role}:FINAL:PASS:test={test_name}".encode("ascii")
        + suffix,
    )
    if cursor != len(lines):
        raise BlePairHilFailure(
            f"{role} FINAL 뒤 예상 밖 protocol token입니다: {lines[cursor:]!r}"
        )
    return M28ThreeBoardRoleResult(role, test_id, metrics)


## @brief 세 보드·image·packet trace·정량 결과를 한 evidence로 결합합니다.
def build_evidence(
    *,
    test_id: str,
    core_revision: str,
    board_revision: str,
    nonce: str,
    endpoints: dict[str, RoleEndpoint],
    images: dict[str, Path],
    image_sizes: dict[str, int],
    image_hashes: dict[str, str],
    build_records: dict[str, dict[str, str]],
    transcript_paths: dict[str, Path],
    execution: ThreeBoardExecution,
    flash_backend: str,
    results: dict[str, M28ThreeBoardRoleResult],
    debug_identities: dict[str, dict[str, str]],
) -> dict[str, Any]:
    executions = {role: getattr(execution, role) for role in ROLES}
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "gate": "m28-three-board-hil",
        "status": "passed",
        "test_id": test_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "flash_backend": flash_backend,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "nonce": nonce,
        "boards": {
            role: {
                "daplink_uid": endpoints[role].board_id,
                "msd_root": str(endpoints[role].volume.root),
                "uart_port": endpoints[role].port_name,
                "debug_identity": debug_identities[role],
            }
            for role in ROLES
        },
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
        "packet_trace": {
            "method": "three-node-receiver-validated-sequence",
            "binding": "same-run-128-bit-nonce-and-three-uart-transcripts",
            "denominator": (
                "periodic-advertiser-emitted-sequence"
                if test_id == "M28-PER-01"
                else "gatt-sender-write-completion-sequence"
            ),
            "payload_integrity": "nonce-phase-sender-sequence-fnv1a",
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    }


## @brief 실패 시점의 세 transcript를 새 evidence 경로에 보존합니다.
def save_failure_transcripts(
    transcript_paths: dict[str, Path], error: Exception
) -> bool:
    if not isinstance(error, ThreeBoardExecutionFailure):
        return False
    for role in ROLES:
        transcript_paths[role].write_bytes(error.transcripts[role])
    return True


## @brief 장치 탐색 또는 선택한 M28 3보드 gate 전체를 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    serial_module, list_ports = import_pyserial()
    endpoints = {
        role: discover_role_endpoint(
            getattr(args, f"{role}_board_id"),
            getattr(args, f"{role}_volume"),
            getattr(args, f"{role}_port"),
            list_ports,
            args.flash_backend,
        )
        for role in ROLES
    }
    validate_three_board_identity(endpoints)
    debug_identities = collect_debug_identities(endpoints, args.flash_backend)
    print(
        "NU54DK M28 3-board discovery SUCCESS: "
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
    validate_source_clean(MILESTONE, APPLICATION_SOURCE_ROOT, Path(__file__).resolve())
    build_records = {
        role: validate_build_record(
            images[role], core_revision, board_revision, APPLICATION_SOURCE_ROOT
        )
        for role in ROLES
    }
    image_sizes = {role: images[role].stat().st_size for role in ROLES}
    image_hashes = {role: file_sha256(images[role]) for role in ROLES}
    if len(set(image_hashes.values())) != len(ROLES):
        raise BlePairHilFailure("M28 3보드 role HEX가 동일하여 오배치를 거부했습니다.")
    nonce = build_nonce()
    timeout = (
        args.result_timeout
        if args.result_timeout is not None
        else DEFAULT_TIMEOUTS[args.test_id]
    )
    try:
        execution = execute_three_board(
            serial_module=serial_module,
            endpoints=endpoints,
            images=images,
            test_name=TEST_NAMES[args.test_id],
            nonce=nonce,
            baud_rate=args.baud,
            flash_timeout=args.flash_timeout,
            result_timeout=timeout,
            flash_backend=args.flash_backend,
        )
        for role in ROLES:
            validate_image_unchanged(
                images[role], image_sizes[role], image_hashes[role]
            )
        results = {
            role: parse_role_transcript(
                getattr(execution, role).transcript, nonce, args.test_id, role
            )
            for role in ROLES
        }
        for role in ROLES:
            transcript_paths[role].write_bytes(getattr(execution, role).transcript)
        evidence = build_evidence(
            test_id=args.test_id,
            core_revision=core_revision,
            board_revision=board_revision,
            nonce=nonce,
            endpoints=endpoints,
            images=images,
            image_sizes=image_sizes,
            image_hashes=image_hashes,
            build_records=build_records,
            transcript_paths=transcript_paths,
            execution=execution,
            flash_backend=args.flash_backend,
            results=results,
            debug_identities=debug_identities,
        )
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as error:
        save_failure_transcripts(transcript_paths, error)
        raise
    print(f"NU54DK M28 3-board {args.test_id} HIL PASS: evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, OSError, TimeoutError) as error:
        print(f"NU54DK M28 3-board HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
