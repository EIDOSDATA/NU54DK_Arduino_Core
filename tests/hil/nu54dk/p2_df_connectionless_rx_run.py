#!/usr/bin/env python3
"""! @brief Zephyr LL connectionless IQ 수신과 Arduino beacon을 함께 검증합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import serial
from pyocd.core.helpers import ConnectHelper

from onboard_start import reset_halted_start
from p2_gatt_memory_run import read_lines, require_mapping


IQ = re.compile(r"M31_RX\|1\|IQ\|count=(\d+)\|type=(\d+)\|status=(\d+)\|rssi=(-?\d+)")
STATS = re.compile(r"DF_CL\|STATS\|reports=(\d+)\|samples=(\d+)")


def wait_for_prefix(streams: dict[str, serial.Serial],
                    pending: dict[str, bytearray], lines: dict[str, list[str]],
                    role: str, prefix: str, start: int, timeout: float) -> str:
    """! @brief 신규 출력 중 지정 상태가 나타날 때까지 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        for line in lines[role][start:]:
            if line.startswith(prefix):
                return line
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief exact 두 보드를 시작하고 IQ 보고와 양측 STOP을 판정합니다. """

    if arguments.iq_target <= 0 or arguments.timeout <= 0:
        raise ValueError("target and timeout must be positive")
    if arguments.receiver_uid.lower() == arguments.beacon_uid.lower():
        raise RuntimeError("two distinct probes are required")
    for role in ("receiver", "beacon"):
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
    if {arguments.receiver_uid.lower(), arguments.beacon_uid.lower()} - probes:
        raise RuntimeError("exact probe is not present")

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-df-connectionless-iq",
        "iq_target": arguments.iq_target,
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in ("receiver", "beacon")
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_uid").lower().encode()).hexdigest()
            for role in ("receiver", "beacon")
        },
        "com_mapping": {
            role: {
                suffix: getattr(arguments, f"{role}_{suffix}")
                for suffix in ("app", "aux")
            }
            for role in ("receiver", "beacon")
        },
        "start": {},
        "lines": {"receiver": [], "beacon": []},
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    try:
        for role in ("beacon", "receiver"):
            streams[role] = serial.Serial(getattr(arguments, f"{role}_app"),
                                          115200, timeout=0.1)
            auxiliary[role] = serial.Serial(getattr(arguments, f"{role}_aux"),
                                            115200, timeout=0.1)
        pending = {role: bytearray() for role in streams}
        lines = evidence["lines"]
        for role in ("beacon", "receiver"):
            start = len(lines[role])
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            wait_for_prefix(streams, pending, lines, role,
                            f"P2_READY role=df-{'beacon' if role == 'beacon' else 'connectionless-receiver'}",
                            start, 30.0)
        deadline = time.monotonic() + arguments.timeout
        reports = 0
        while time.monotonic() < deadline and reports < arguments.iq_target:
            read_lines(streams, pending, lines)
            if any("FAULT" in line or "ASSERTION FAIL" in line
                   for values in lines.values() for line in values):
                raise RuntimeError("DF fixture fault was observed")
            if any(line.startswith("M31_RX|1|SYNC_TIMEOUT")
                   for line in lines["receiver"]):
                raise RuntimeError("periodic sync timed out")
            reports = sum(IQ.fullmatch(line) is not None for line in lines["receiver"])
            time.sleep(0.02)
        if reports < arguments.iq_target:
            raise TimeoutError("IQ report target not observed")

        start = len(lines["receiver"])
        streams["receiver"].write(b"s")
        wait_for_prefix(streams, pending, lines, "receiver",
                        "P2_STOP role=df-connectionless-receiver", start, 15.0)
        stats_lines = [line for line in lines["receiver"]
                       if line.startswith("DF_CL|STATS|")]
        if len(stats_lines) != 1 or (match := STATS.fullmatch(stats_lines[0])) is None:
            raise RuntimeError("receiver statistics are missing")
        evidence["iq_reports"], evidence["iq_samples"] = map(int, match.groups())
        if evidence["iq_reports"] < arguments.iq_target or evidence["iq_samples"] <= 0:
            raise RuntimeError("receiver did not count positive IQ samples")
        start = len(lines["beacon"])
        streams["beacon"].write(b"s")
        wait_for_prefix(streams, pending, lines, "beacon",
                        "P2_STOP role=df-beacon", start, 15.0)
        evidence["result"] = "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error).replace(
            arguments.receiver_uid, "<probe>"
        ).replace(arguments.beacon_uid, "<probe>")[:200]
        raise
    finally:
        if evidence["result"] != "PASS" and streams and pending:
            evidence["cleanup_attempted"] = True
            evidence["cleanup_observed"] = {}
            for role in ("receiver", "beacon"):
                if role not in streams:
                    continue
                prefix = ("P2_STOP role=df-connectionless-receiver" if role == "receiver"
                          else "P2_STOP role=df-beacon")
                if any(line.startswith(prefix) for line in evidence["lines"][role]):
                    evidence["cleanup_observed"][role] = True
                    continue
                try:
                    start = len(evidence["lines"][role])
                    streams[role].write(b"s")
                    wait_for_prefix(streams, pending, evidence["lines"], role,
                                    prefix, start, 15.0)
                    evidence["cleanup_observed"][role] = True
                except (serial.SerialException, TimeoutError):
                    evidence["cleanup_observed"][role] = False
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        for role in ("receiver", "beacon"):
            evidence["lines"][role] = [
                re.sub(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b", "<peer>", line)
                for line in evidence["lines"][role]
            ]
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return evidence


def main() -> None:
    """! @brief exact probe·COM·image와 IQ 목표를 명시적으로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("receiver", "beacon"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--iq-target", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=120.0)
    evidence = run(parser.parse_args())
    print(f"P2 DF connectionless IQ HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
