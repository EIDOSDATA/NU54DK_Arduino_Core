#!/usr/bin/env python3
"""! @brief BIS 100 SDU × 20세션과 양 역할 메모리 high-water를 기록합니다. """

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
from p2_cs_memory_run import wait_for_new_line
from p2_gatt_memory_run import read_lines, require_mapping


SENT = re.compile(r"^P2_BIS_SENT cycle=(\d+) frames=100$")
RECEIVED = re.compile(
    r"^P2_BIS_RECV cycle=(\d+) frames=(99|100) missing=([01]) errors=0$"
)


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 두 exact 보드의 20 BIG 세션과 손실 상한을 검증합니다. """

    roles = ("receiver", "source")
    if arguments.receiver_uid.lower() == arguments.source_uid.lower():
        raise RuntimeError("two distinct probes are required")
    for role in roles:
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
    if {getattr(arguments, f"{role}_uid").lower() for role in roles} - probes:
        raise RuntimeError("exact probe is not present")

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-iso-bis-100-frame-20-cycle-memory",
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in roles
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(
                getattr(arguments, f"{role}_uid").lower().encode("ascii")
            ).hexdigest()
            for role in roles
        },
        "com_mapping": {
            role: {suffix: getattr(arguments, f"{role}_{suffix}")
                   for suffix in ("app", "aux")}
            for role in roles
        },
        "start": {},
        "lines": {role: [] for role in roles},
        "sent_cycles": 0,
        "received_cycles": 0,
        "missing_total": 0,
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    active_start: dict[str, int] = {}
    try:
        for role in roles:
            streams[role] = serial.Serial(
                getattr(arguments, f"{role}_app"), 115200, timeout=0.1
            )
            auxiliary[role] = serial.Serial(
                getattr(arguments, f"{role}_aux"), 115200, timeout=0.1
            )
        pending = {role: bytearray() for role in roles}
        lines = evidence["lines"]
        for role in roles:
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            start_index = len(lines[role])
            wait_for_new_line(streams, pending, lines, role, start_index,
                              f"P2_READY role=bis-{role}", 20.0)
            active_start[role] = max(
                index for index, line in enumerate(lines[role])
                if line == f"P2_READY role=bis-{role}"
            )
        read_lines(streams, pending, lines)
        active_start["receiver"] = len(lines["receiver"])

        deadline = time.monotonic() + 300.0
        while time.monotonic() < deadline:
            read_lines(streams, pending, lines)
            current = {role: lines[role][active_start[role]:] for role in roles}
            if any("P2_BIS_FAIL" in line or "FAULT" in line
                   for values in current.values() for line in values):
                raise RuntimeError("BIS firmware failure or fault")
            sent = [int(match.group(1)) for line in current["source"]
                    if (match := SENT.fullmatch(line))]
            received = [tuple(int(value) for value in match.groups())
                        for line in current["receiver"]
                        if (match := RECEIVED.fullmatch(line))]
            if sent != list(range(1, len(sent) + 1)) or [item[0] for item in received] != list(
                range(1, len(received) + 1)
            ):
                raise RuntimeError("BIS cycle gap or duplicate")
            if any(frames + missing != 100 for _, frames, missing in received):
                raise RuntimeError("BIS loss accounting mismatch")
            evidence["sent_cycles"] = len(sent)
            evidence["received_cycles"] = len(received)
            evidence["missing_total"] = sum(item[2] for item in received)
            if len(sent) == 20 and len(received) == 20:
                if ("P2_STOP role=bis-source cycles=20" in current["source"] and
                        "P2_STOP role=bis-receiver cycles=20" in current["receiver"]):
                    evidence["result"] = "PASS"
                    break
            time.sleep(0.02)
        if evidence["result"] != "PASS":
            raise TimeoutError("20 complete BIS cycles and both STOPs were not observed")
    finally:
        for stream in streams.values():
            try:
                stream.write(b"s")
            except serial.SerialException:
                pass
        if streams and pending:
            end = time.monotonic() + 5.0
            while time.monotonic() < end:
                read_lines(streams, pending, evidence["lines"])
                time.sleep(0.02)
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return evidence


def main() -> None:
    """! @brief exact probe·COM·HEX와 원본 증거 경로를 CLI로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("receiver", "source"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    evidence = run(parser.parse_args())
    print(f"P2 ISO BIS memory HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
