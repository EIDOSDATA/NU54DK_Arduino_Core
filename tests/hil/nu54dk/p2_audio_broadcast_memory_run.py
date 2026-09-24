#!/usr/bin/env python3
"""! @brief 암호화 broadcast LC3/BIS frame과 메모리 high-water를 기록합니다. """

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


SENT = re.compile(r"^P2_AUDIO_SENT frames=(\d+)$")
DECODED = re.compile(r"^P2_AUDIO_DECODED frames=(\d+) dropped=(\d+) energy=(\d+)$")
SOURCE_STOP = re.compile(r"^P2_STOP role=audio-broadcast-source sent=(\d+)$")
SINK_STOP = re.compile(r"^P2_STOP role=audio-broadcast-sink decoded=(\d+) dropped=(\d+)$")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 두 exact 보드의 목표 frame·drop 0·양쪽 종료를 검증합니다. """

    roles = ("sink", "source")
    if arguments.frames <= 0 or arguments.frames % 100 != 0:
        raise ValueError("--frames must be a positive multiple of 100")
    if arguments.timeout <= 0:
        raise ValueError("--timeout must be positive")
    if arguments.sink_uid.lower() == arguments.source_uid.lower():
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
        "case": f"m31-p2-audio-broadcast-lc3-{arguments.frames}-frame-memory",
        "target_frames": arguments.frames,
        "timeout_s": arguments.timeout,
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
        "sent": 0,
        "decoded": 0,
        "dropped": 0,
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
                              f"P2_READY role=audio-broadcast-{role}", 20.0)
            active_start[role] = max(
                index for index, line in enumerate(lines[role])
                if line == f"P2_READY role=audio-broadcast-{role}"
            )
        read_lines(streams, pending, lines)
        active_start["sink"] = len(lines["sink"])

        deadline = time.monotonic() + arguments.timeout
        while time.monotonic() < deadline:
            read_lines(streams, pending, lines)
            current = {role: lines[role][active_start[role]:] for role in roles}
            if any("P2_AUDIO_FAIL" in line or "FAULT" in line
                   for values in current.values() for line in values):
                raise RuntimeError("broadcast Audio firmware failure or fault")
            sent = [int(match.group(1)) for line in current["source"]
                    if (match := SENT.fullmatch(line))]
            decoded = [tuple(int(value) for value in match.groups())
                       for line in current["sink"]
                       if (match := DECODED.fullmatch(line))]
            if sent != list(range(100, 100 * (len(sent) + 1), 100)):
                raise RuntimeError("source frame count gap or duplicate")
            if [item[0] for item in decoded] != list(
                range(100, 100 * (len(decoded) + 1), 100)
            ):
                raise RuntimeError("sink frame count gap or duplicate")
            if any(dropped != 0 or energy <= 0 for _, dropped, energy in decoded):
                raise RuntimeError("broadcast frame dropped or invalid PCM")
            evidence["sent"] = sent[-1] if sent else 0
            evidence["decoded"] = decoded[-1][0] if decoded else 0
            if evidence["sent"] >= arguments.frames and evidence["decoded"] >= arguments.frames:
                break
            if evidence["sent"] >= arguments.frames + 2000 and evidence["decoded"] < arguments.frames:
                raise RuntimeError("broadcast sink did not keep up with source")
            time.sleep(0.02)
        if evidence["sent"] < arguments.frames or evidence["decoded"] < arguments.frames:
            raise TimeoutError("target broadcast LC3 frames were not observed")

        sink_stop_index = len(lines["sink"])
        streams["sink"].write(b"s")
        wait_for_new_line(streams, pending, lines, "sink", sink_stop_index,
                          "P2_STOP role=audio-broadcast-sink", 30.0)
        source_stop_index = len(lines["source"])
        streams["source"].write(b"s")
        wait_for_new_line(streams, pending, lines, "source", source_stop_index,
                          "P2_STOP role=audio-broadcast-source", 30.0)
        read_lines(streams, pending, lines)
        source_stop = [match.group(1) for line in lines["source"][active_start["source"]:]
                       if (match := SOURCE_STOP.fullmatch(line))]
        sink_stop = [match.groups() for line in lines["sink"][active_start["sink"]:]
                     if (match := SINK_STOP.fullmatch(line))]
        if not source_stop or not sink_stop:
            raise RuntimeError("broadcast stop counters are missing")
        if (int(source_stop[-1]) < arguments.frames or
                int(sink_stop[-1][0]) < arguments.frames):
            raise RuntimeError("broadcast stop counters are below the load")
        evidence["dropped"] = int(sink_stop[-1][1])
        if evidence["dropped"] != 0:
            raise RuntimeError("broadcast sink dropped frames")
        if any("P2_AUDIO_FAIL" in line or "FAULT" in line
               for role in roles for line in lines[role][active_start[role]:]):
            raise RuntimeError("broadcast firmware failure or fault")
        evidence["result"] = "PASS"
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
    """! @brief exact probe·COM·HEX와 원본 증거 경로를 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("sink", "source"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=180.0)
    evidence = run(parser.parse_args())
    print(f"P2 Audio broadcast memory HIL: {evidence['result']}")
    if evidence["result"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
