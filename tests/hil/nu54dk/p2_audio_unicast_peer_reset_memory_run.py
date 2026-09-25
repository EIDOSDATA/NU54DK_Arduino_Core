#!/usr/bin/env python3
"""! @brief LC3/CIS source reset 뒤 sink 재연결의 메모리 고점을 검증합니다. """

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
from p2_audio_broadcast_rejoin_memory_run import summarize_memory, wait_line
from p2_gatt_memory_run import read_lines, require_mapping


DECODED = re.compile(r"P2_AUDIO_DECODED frames=(\d+) dropped=(\d+) energy=(\d+)")
SENT = re.compile(r"P2_AUDIO_SENT frames=(\d+)")
SINK_STOP = re.compile(r"P2_STOP role=audio-sink decoded=(\d+) dropped=(\d+)")
SOURCE_STOP = re.compile(r"P2_STOP role=audio-source sent=(\d+)")


def wait_session(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
                 lines: dict[str, list[str]], sink_active: int,
                 source_active: int, target: int, timeout: float) -> dict:
    """! @brief 누적 sink 복호화와 현재 source 수명의 100 frame을 확인합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        current_sink = lines["sink"][sink_active:]
        current_source = lines["source"][source_active:]
        if any("FAULT" in line or "ASSERTION FAIL" in line or
               "P2_AUDIO_FAIL" in line
               for line in (*current_sink, *current_source)):
            raise RuntimeError("unicast firmware reported failure or fault")
        decoded = [tuple(map(int, match.groups())) for line in current_sink
                   if (match := DECODED.fullmatch(line))]
        sent = [int(match.group(1)) for line in current_source
                if (match := SENT.fullmatch(line))]
        expected_sink = list(range(100, 100 * (len(decoded) + 1), 100))
        expected_source = list(range(100, 100 * (len(sent) + 1), 100))
        if [item[0] for item in decoded] != expected_sink or sent != expected_source:
            raise RuntimeError("unicast frame milestone gap or duplicate")
        if any(drop != 0 or energy <= 0 for _, drop, energy in decoded):
            raise RuntimeError("unicast dropped a frame or decoded silence")
        if decoded and decoded[-1][0] >= target and sent and sent[-1] >= 100:
            return {"decoded": decoded[-1][0], "source_sent": sent[-1]}
        time.sleep(0.02)
    raise TimeoutError(f"unicast session did not reach sink {target} / source 100")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief exact 두 보드에서 source SWD reset과 sink 누적 고점을 기록합니다. """

    roles = ("sink", "source")
    if arguments.cycles <= 0 or arguments.sink_uid.lower() == arguments.source_uid.lower():
        raise ValueError("positive cycles and two distinct probes are required")
    if arguments.output.exists():
        raise RuntimeError("refusing to overwrite existing evidence")
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
        "case": "m31-p2-audio-unicast-source-reset-sink-memory",
        "cycles_target": arguments.cycles,
        "cycles_completed": 0,
        "frames_per_session": 100,
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in roles
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_uid").lower().encode()).hexdigest()
            for role in roles
        },
        "com_mapping": {
            role: {suffix: getattr(arguments, f"{role}_{suffix}")
                   for suffix in ("app", "aux")}
            for role in roles
        },
        "start": {},
        "source_restart": [],
        "sessions": [],
        "lines": {role: [] for role in roles},
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    try:
        for role in roles:
            streams[role] = serial.Serial(getattr(arguments, f"{role}_app"),
                                          115200, timeout=0.1)
            auxiliary[role] = serial.Serial(getattr(arguments, f"{role}_aux"),
                                            115200, timeout=0.1)
        pending = {role: bytearray() for role in roles}
        lines = evidence["lines"]
        for role in roles:
            start = len(lines[role])
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            wait_line(streams, pending, lines, role,
                      f"P2_READY role=audio-{role}", start, 30.0)
            if role == "sink":
                wait_line(streams, pending, lines, role,
                          "P2_AUDIO_ADVERTISING role=sink", start, 20.0)
        sink_active = max(index for index, line in enumerate(lines["sink"])
                          if line == "P2_READY role=audio-sink") + 1
        source_active = max(index for index, line in enumerate(lines["source"])
                            if line == "P2_READY role=audio-source") + 1
        evidence["sessions"].append(wait_session(
            streams, pending, lines, sink_active, source_active, 100, 60.0
        ))

        for cycle in range(1, arguments.cycles + 1):
            start = len(lines["source"])
            evidence["source_restart"].append(reset_halted_start(
                {"app": streams["source"], "aux": auxiliary["source"]},
                arguments.source_uid,
            ))
            wait_line(streams, pending, lines, "source",
                      "P2_READY role=audio-source", start, 30.0)
            source_active = max(index for index, line in enumerate(lines["source"])
                                if line == "P2_READY role=audio-source") + 1
            evidence["sessions"].append(wait_session(
                streams, pending, lines, sink_active, source_active,
                100 * (cycle + 1), 60.0
            ))
            evidence["cycles_completed"] = cycle

        source_start = len(lines["source"])
        streams["source"].write(b"s")
        source_stop = wait_line(streams, pending, lines, "source",
                                "P2_STOP role=audio-source", source_start, 30.0)
        sink_start = len(lines["sink"])
        streams["sink"].write(b"s")
        sink_stop = wait_line(streams, pending, lines, "sink",
                              "P2_STOP role=audio-sink", sink_start, 30.0)
        source_match = SOURCE_STOP.fullmatch(source_stop)
        sink_match = SINK_STOP.fullmatch(sink_stop)
        if source_match is None or sink_match is None:
            raise RuntimeError("unicast STOP counters are malformed")
        evidence["source_sent_last_session"] = int(source_match.group(1))
        evidence["decoded_frames"] = int(sink_match.group(1))
        evidence["dropped_frames"] = int(sink_match.group(2))
        if (evidence["source_sent_last_session"] < 100 or
                evidence["decoded_frames"] < 100 * (arguments.cycles + 1) or
                evidence["dropped_frames"] != 0):
            raise RuntimeError("unicast STOP counters are below the load")
        if sum(line == "P2_READY role=audio-source"
               for line in lines["source"]) != arguments.cycles + 1:
            raise RuntimeError("unicast source restart count mismatch")
        if any("P2_AUDIO_FAIL" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("unicast firmware reported a failure")
        evidence["memory_summary"] = summarize_memory(lines, 2)
        if evidence["memory_summary"]["source"]["malloc_reports"] < arguments.cycles + 2:
            raise RuntimeError("unicast source lifetime telemetry is incomplete")
        evidence["result"] = "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error).replace(
            arguments.sink_uid, "<probe>"
        ).replace(arguments.source_uid, "<probe>")[:200]
        raise
    finally:
        if evidence["result"] != "PASS" and streams and pending:
            evidence["cleanup_attempted"] = True
            evidence["cleanup_observed"] = {}
            for role in ("source", "sink"):
                if role not in streams:
                    continue
                prefix = f"P2_STOP role=audio-{role}"
                if any(line.startswith(prefix) for line in evidence["lines"][role]):
                    evidence["cleanup_observed"][role] = True
                    continue
                try:
                    start = len(evidence["lines"][role])
                    streams[role].write(b"s")
                    wait_line(streams, pending, evidence["lines"], role,
                              prefix, start, 30.0)
                    evidence["cleanup_observed"][role] = True
                except (serial.SerialException, TimeoutError, RuntimeError):
                    evidence["cleanup_observed"][role] = False
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        for role in roles:
            values = evidence["lines"][role]
            ready = [index for index, line in enumerate(values)
                     if line == f"P2_READY role=audio-{role}"]
            if ready:
                values = values[ready[0]:]
            evidence["lines"][role] = [
                re.sub(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b", "<peer>", line)
                for line in values
            ]
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return evidence


def main() -> None:
    """! @brief 두 exact image·probe/COM과 재시작 횟수를 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("sink", "source"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--output", required=True, type=Path)
    evidence = run(parser.parse_args())
    print(f"P2 Audio unicast peer-reset HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
