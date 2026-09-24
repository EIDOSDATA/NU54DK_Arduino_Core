#!/usr/bin/env python3
"""! @brief unicast LC3 frame 송수신과 메모리 high-water를 기록합니다. """

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
from p2_cs_memory_run import wait_for_cleanup_line, wait_for_new_line
from p2_gatt_memory_run import read_lines, require_mapping


SENT = re.compile(r"^P2_AUDIO_SENT frames=(\d+)$")
DECODED = re.compile(r"^P2_AUDIO_DECODED frames=(\d+) dropped=(\d+) energy=(\d+)$")
SOURCE_STOP = re.compile(r"^P2_STOP role=audio-source sent=(\d+)$")
SINK_STOP = re.compile(r"^P2_STOP role=audio-sink decoded=(\d+) dropped=(\d+)$")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 양 역할의 목표 frame·drop 0·양측 STOP을 검증합니다. """

    roles = ("sink", "source")
    if arguments.frame_target <= 0 or arguments.frame_target % 100 != 0:
        raise ValueError("--frame-target must be a positive multiple of 100")
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
        "case": f"m31-p2-audio-unicast-lc3-{arguments.frame_target}-frame-memory",
        "frame_target": arguments.frame_target,
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
                              f"P2_READY role=audio-{role}", 20.0)
            active_start[role] = max(
                index for index, line in enumerate(lines[role])
                if line == f"P2_READY role=audio-{role}"
            )
            if role == "sink":
                wait_for_new_line(streams, pending, lines, role, start_index,
                                  "P2_AUDIO_ADVERTISING role=sink", 20.0)
        read_lines(streams, pending, lines)
        active_start["sink"] = len(lines["sink"])

        deadline = time.monotonic() + arguments.timeout
        while time.monotonic() < deadline:
            read_lines(streams, pending, lines)
            current = {
                role: lines[role][active_start[role]:] for role in roles
            }
            if any("P2_AUDIO_FAIL" in line or "FAULT" in line
                   for values in current.values() for line in values):
                raise RuntimeError("Audio firmware failure or fault")
            sent = [int(match.group(1)) for line in current["source"]
                    if (match := SENT.fullmatch(line))]
            decoded = [tuple(int(value) for value in match.groups())
                       for line in current["sink"]
                       if (match := DECODED.fullmatch(line))]
            if sent != list(range(100, 100 * (len(sent) + 1), 100)):
                raise RuntimeError("Audio source frame count gap or duplicate")
            if [item[0] for item in decoded] != list(
                range(100, 100 * (len(decoded) + 1), 100)
            ):
                raise RuntimeError("Audio sink frame count gap or duplicate")
            if any(dropped != 0 or energy <= 0 for _, dropped, energy in decoded):
                raise RuntimeError("Audio frame dropped or silent/invalid PCM")
            evidence["sent"] = sent[-1] if sent else 0
            evidence["decoded"] = decoded[-1][0] if decoded else 0
            if (evidence["sent"] >= arguments.frame_target and
                    evidence["decoded"] >= arguments.frame_target):
                break
            if (evidence["sent"] >= arguments.frame_target * 2 and
                    evidence["decoded"] < arguments.frame_target):
                raise RuntimeError("Audio sink did not keep up with source")
            time.sleep(0.02)
        if (evidence["sent"] < arguments.frame_target or
                evidence["decoded"] < arguments.frame_target):
            raise TimeoutError("target LC3 send/decode frames were not observed")

        source_stop_index = len(lines["source"])
        streams["source"].write(b"s")
        wait_for_new_line(streams, pending, lines, "source", source_stop_index,
                          "P2_STOP role=audio-source", 30.0)
        sink_stop_index = len(lines["sink"])
        streams["sink"].write(b"s")
        wait_for_new_line(streams, pending, lines, "sink", sink_stop_index,
                          "P2_STOP role=audio-sink", 20.0)
        read_lines(streams, pending, lines)
        source_stop = [SOURCE_STOP.fullmatch(line)
                       for line in lines["source"][active_start["source"]:]
                       if SOURCE_STOP.fullmatch(line)]
        sink_stop = [SINK_STOP.fullmatch(line)
                     for line in lines["sink"][active_start["sink"]:]
                     if SINK_STOP.fullmatch(line)]
        if not source_stop or not sink_stop:
            raise RuntimeError("Audio stop counters are missing")
        if (int(source_stop[-1].group(1)) < arguments.frame_target or
                int(sink_stop[-1].group(1)) < arguments.frame_target):
            raise RuntimeError("Audio stop counters are below the load")
        evidence["dropped"] = int(sink_stop[-1].group(2))
        if evidence["dropped"] != 0:
            raise RuntimeError("Audio sink dropped frames")
        if any("P2_AUDIO_FAIL" in line or "FAULT" in line
               for role in roles
               for line in lines[role][active_start[role]:]):
            raise RuntimeError("Audio firmware failure or fault")
        evidence["result"] = "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error).replace(
            arguments.sink_uid, "<probe>"
        ).replace(arguments.source_uid, "<probe>")[:200]
        raise
    finally:
        if streams and pending:
            cleanup = {}
            for role in ("source", "sink"):
                expected = f"P2_STOP role=audio-{role}"
                cleanup[f"{role}_stop"] = any(
                    line.startswith(expected) for line in evidence["lines"][role]
                )
                if not cleanup[f"{role}_stop"] and role in streams:
                    try:
                        start = len(evidence["lines"][role])
                        streams[role].write(b"s")
                        cleanup[f"{role}_stop"] = wait_for_cleanup_line(
                            streams, pending, evidence["lines"], role,
                            start, expected, 30.0 if role == "source" else 20.0
                        )
                    except serial.SerialException:
                        pass
            evidence["cleanup_observed"] = cleanup
            if not all(cleanup.values()):
                evidence["result"] = "FAIL"
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return evidence


def main() -> None:
    """! @brief exact probe·COM·HEX와 증거 경로를 CLI로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("sink", "source"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frame-target", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=120.0)
    evidence = run(parser.parse_args())
    print(f"P2 Audio unicast memory HIL: {evidence['result']}")
    if evidence["result"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
