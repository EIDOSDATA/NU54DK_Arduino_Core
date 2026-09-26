#!/usr/bin/env python3
"""! @brief P2 GATT 512 B·20회 복구 계측을 exact probe/COM으로 실행합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import serial
from serial.tools import list_ports
from pyocd.core.helpers import ConnectHelper

from onboard_start import reset_halted_start


def require_mapping(port: str, uid: str) -> None:
    """! @brief 현재 USB serial number가 요청 probe와 일치하는지 검사합니다. """

    observed = {item.device.upper(): item for item in list_ports.comports()}
    device = observed.get(port.upper())
    if device is None or (device.serial_number or "").lower() != uid.lower():
        raise RuntimeError(f"COM/probe mapping mismatch: {port}")


def read_lines(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
               lines: dict[str, list[str]]) -> None:
    """! @brief 두 역할의 줄 단위 UART 기록을 유실 없이 누적합니다. """

    for role, stream in streams.items():
        count = stream.in_waiting
        if count <= 0:
            continue
        pending[role].extend(stream.read(count))
        while b"\n" in pending[role]:
            raw, _, remainder = pending[role].partition(b"\n")
            pending[role] = bytearray(remainder)
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                lines[role].append(line)


def wait_for_line(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
                  lines: dict[str, list[str]], role: str, expected: str,
                  timeout: float) -> None:
    """! @brief 지정된 준비·종료 신호를 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any(line.startswith("P2_FAIL") for values in lines.values() for line in values):
            raise RuntimeError("firmware reported P2_FAIL")
        if any(line.startswith(expected) for line in lines[role]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {expected}")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 현재 mapping·image를 확정하고 20회 회복 뒤 양측 STOP을 확인합니다. """

    if arguments.peripheral_uid.lower() == arguments.central_uid.lower():
        raise RuntimeError("two distinct probes are required")
    for role in ("peripheral", "central"):
        uid = getattr(arguments, f"{role}_uid")
        for suffix in ("app", "aux"):
            require_mapping(getattr(arguments, f"{role}_{suffix}"), uid)
        if not getattr(arguments, f"{role}_hex").is_file():
            raise RuntimeError(f"{role} HEX is missing")

    probes = {
        probe.unique_id.lower()
        for probe in ConnectHelper.get_all_connected_probes(
            blocking=False, print_wait_message=False
        )
    }
    if {arguments.peripheral_uid.lower(), arguments.central_uid.lower()} - probes:
        raise RuntimeError("exact probe is not present")

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-gatt-512-recovery-20",
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in ("peripheral", "central")
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(
                getattr(arguments, f"{role}_uid").lower().encode("ascii")
            ).hexdigest()
            for role in ("peripheral", "central")
        },
        "com_mapping": {
            role: {
                suffix: getattr(arguments, f"{role}_{suffix}")
                for suffix in ("app", "aux")
            }
            for role in ("peripheral", "central")
        },
        "start": {},
        "lines": {"peripheral": [], "central": []},
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    try:
        for role in ("peripheral", "central"):
            streams[role] = serial.Serial(
                getattr(arguments, f"{role}_app"), 115200, timeout=0.1
            )
            auxiliary[role] = serial.Serial(
                getattr(arguments, f"{role}_aux"), 115200, timeout=0.1
            )
        pending = {role: bytearray() for role in streams}
        lines = evidence["lines"]

        for role in ("peripheral", "central"):
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            wait_for_line(streams, pending, lines, role,
                          f"P2_READY role={role}", 20.0)

        wait_for_line(streams, pending, lines, "central", "P2_DONE cycles=20", 600.0)
        streams["peripheral"].write(b"s")
        wait_for_line(streams, pending, lines, "peripheral", "P2_STOP writes=20", 20.0)
        read_lines(streams, pending, lines)

        cycles = [int(match.group(1)) for line in lines["central"]
                  if (match := re.fullmatch(r"P2_CYCLE pass=(\d+)", line))]
        writes = [int(match.group(1)) for line in lines["peripheral"]
                  if (match := re.fullmatch(r"P2_RX writes=(\d+)", line))]
        if cycles != list(range(1, 21)) or writes != list(range(1, 21)):
            raise RuntimeError("cycle/write sequence is incomplete or duplicated")
        if not any(line == "P2_DONE cycles=20 writes=20" for line in lines["central"]):
            raise RuntimeError("central completion count mismatch")
        if any(line.startswith("P2_FAIL") or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("firmware fault was observed")
        evidence["result"] = "PASS"
    finally:
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return evidence


def main() -> None:
    """! @brief exact pair와 출력 경로를 명시적으로 요구합니다. """

    parser = argparse.ArgumentParser()
    for role in ("peripheral", "central"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    evidence = run(parser.parse_args())
    print(f"P2 GATT memory HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
