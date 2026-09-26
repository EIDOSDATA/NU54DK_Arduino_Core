#!/usr/bin/env python3
"""! @brief 암호화 LC3/BIS 방송의 source reset·sink 재가입 메모리를 검증합니다. """

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


DECODED = re.compile(r"P2_AUDIO_DECODED frames=(\d+) dropped=(\d+) energy=(\d+)")
SINK_CYCLE = re.compile(r"P2_AUDIO_CYCLE_MEMORY decoded=(\d+) dropped=(\d+)")
SOURCE_CYCLE = re.compile(r"P2_AUDIO_CYCLE_MEMORY sent=(\d+)")
SINK_STOP = re.compile(r"P2_STOP role=audio-broadcast-sink decoded=(\d+) dropped=(\d+)")
SOURCE_STOP = re.compile(r"P2_STOP role=audio-broadcast-source sent=(\d+)")
STACK = re.compile(r"P2_STACK name=(.+) reserved=(\d+) used=(\d+)")
MALLOC = re.compile(r"P2_MALLOC free=(\d+) allocated=(\d+) peak=(\d+)")


def wait_line(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
              lines: dict[str, list[str]], role: str, prefix: str, start: int,
              timeout: float) -> str:
    """! @brief 해당 cycle의 신규 UART 줄만 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        for values in lines.values():
            if any("FAULT" in line or "ASSERTION FAIL" in line for line in values):
                raise RuntimeError("broadcast firmware fault")
        for line in lines[role][start:]:
            if line.startswith(prefix):
                return line
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def wait_sink_stream(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
                     lines: dict[str, list[str]], start: int,
                     timeout: float) -> bool:
    """! @brief 동기화 성공 또는 stage 실패를 구분해 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("FAULT" in line or "ASSERTION FAIL" in line
               for values in lines.values() for line in values):
            raise RuntimeError("broadcast firmware fault")
        for line in lines["sink"][start:]:
            if line.startswith("P2_AUDIO_STREAM role=broadcast-sink"):
                return True
            if line.startswith("P2_AUDIO_FAIL sink-stage"):
                return False
            if line.startswith("P2_AUDIO_FAIL"):
                raise RuntimeError(f"sink failed before streaming: {line}")
        time.sleep(0.02)
    return False


def rejoin_sink(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
                lines: dict[str, list[str]], initial_start: int,
                max_requests: int) -> int:
    """! @brief 첫 동기화와 명시적 재가입을 한정 횟수만 시도합니다. """

    start = initial_start
    requests = 0
    while True:
        if wait_sink_stream(streams, pending, lines, start, 30.0):
            return requests
        if requests >= max_requests:
            raise RuntimeError("sink sync failed after bounded rejoin requests")
        start = len(lines["sink"])
        streams["sink"].write(b"r")
        wait_line(streams, pending, lines, "sink",
                  "P2_AUDIO_REJOIN_REQUESTED", start, 20.0)
        requests += 1


def wait_decoded(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
                 lines: dict[str, list[str]], start: int, target: int,
                 timeout: float) -> None:
    """! @brief 누적 100-frame milestone과 drop·PCM energy를 검사합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("FAULT" in line or "ASSERTION FAIL" in line
               for values in lines.values() for line in values):
            raise RuntimeError("broadcast firmware fault")
        milestones = [tuple(map(int, match.groups()))
                      for line in lines["sink"][start:]
                      if (match := DECODED.fullmatch(line))]
        if [item[0] for item in milestones] != [100 * index
                                                 for index in range(1, len(milestones) + 1)]:
            raise RuntimeError("decoded frame milestone gap or duplicate")
        if any(dropped != 0 or energy <= 0 for _, dropped, energy in milestones):
            raise RuntimeError("broadcast dropped a frame or decoded silence")
        if milestones and milestones[-1][0] >= target:
            return
        time.sleep(0.02)
    raise TimeoutError(f"sink did not decode {target} frames")


def check_cycle_memory(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
                       lines: dict[str, list[str]], target: int) -> dict[str, int]:
    """! @brief reset 전 두 역할의 frame/drop와 phase별 메모리 보고를 묶습니다. """

    starts = {role: len(lines[role]) for role in ("sink", "source")}
    for role in ("sink", "source"):
        streams[role].write(b"m")
    sink_line = wait_line(streams, pending, lines, "sink",
                          "P2_AUDIO_CYCLE_MEMORY", starts["sink"], 15.0)
    source_line = wait_line(streams, pending, lines, "source",
                            "P2_AUDIO_CYCLE_MEMORY", starts["source"], 15.0)
    sink = SINK_CYCLE.fullmatch(sink_line)
    source = SOURCE_CYCLE.fullmatch(source_line)
    if sink is None or source is None:
        raise RuntimeError("broadcast cycle memory report is malformed")
    decoded, dropped = map(int, sink.groups())
    sent = int(source.group(1))
    if decoded < target or dropped != 0 or sent < 100:
        raise RuntimeError("broadcast cycle frame/drop count is invalid")
    return {"decoded": decoded, "dropped": dropped, "source_sent": sent}


def summarize_memory(lines: dict[str, list[str]], minimum_reports: int) -> dict:
    """! @brief 역할별 stack 최고치와 malloc 종료 상태를 검증합니다. """

    summary = {}
    for role in ("sink", "source"):
        stacks: dict[str, dict[str, int]] = {}
        malloc = []
        for line in lines[role]:
            if match := STACK.fullmatch(line):
                name, reserved_text, used_text = match.groups()
                reserved = int(reserved_text)
                used = int(used_text)
                if reserved <= 0 or used > reserved:
                    raise RuntimeError(f"{role} stack reservation is invalid")
                old = stacks.get(name)
                if old is not None and old["reserved"] != reserved:
                    raise RuntimeError(f"{role} stack reservation changed within one image")
                stacks[name] = {"reserved": reserved,
                                "used_peak": max(used, old["used_peak"] if old else 0)}
            if match := MALLOC.fullmatch(line):
                malloc.append(tuple(map(int, match.groups())))
        if len(malloc) < minimum_reports or not stacks:
            raise RuntimeError(f"{role} memory telemetry is incomplete")
        if malloc[-1][1] != 0:
            raise RuntimeError(f"{role} retained libc allocation after STOP")
        summary[role] = {
            "malloc_reports": len(malloc),
            "malloc_free_after_stop": malloc[-1][0],
            "malloc_allocated_after_stop": malloc[-1][1],
            "malloc_peak": max(item[2] for item in malloc),
            "stacks": stacks,
        }
    return summary


def run(arguments: argparse.Namespace) -> dict:
    """! @brief exact 두 보드의 source reset 뒤 공개 sink 재가입을 계측합니다. """

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
        "case": "m31-p2-audio-broadcast-source-reset-rejoin-memory",
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
        "initial_rejoin_requests": 0,
        "cycle_rejoin_requests": [],
        "cycle_memory": [],
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
                      f"P2_READY role=audio-broadcast-{role}", start, 30.0)
        sink_active = max(index for index, line in enumerate(lines["sink"])
                          if line == "P2_READY role=audio-broadcast-sink") + 1
        evidence["initial_rejoin_requests"] = rejoin_sink(
            streams, pending, lines, sink_active, 3
        )
        wait_decoded(streams, pending, lines, sink_active, 100, 45.0)
        evidence["cycle_memory"].append(
            check_cycle_memory(streams, pending, lines, 100)
        )

        for cycle in range(1, arguments.cycles + 1):
            source_start = len(lines["source"])
            evidence["source_restart"].append(reset_halted_start(
                {"app": streams["source"], "aux": auxiliary["source"]},
                arguments.source_uid,
            ))
            wait_line(streams, pending, lines, "source",
                      "P2_READY role=audio-broadcast-source", source_start, 30.0)
            rejoin_start = len(lines["sink"])
            streams["sink"].write(b"r")
            wait_line(streams, pending, lines, "sink",
                      "P2_AUDIO_REJOIN_REQUESTED", rejoin_start, 20.0)
            requests = 1 + rejoin_sink(
                streams, pending, lines, rejoin_start, 2
            )
            evidence["cycle_rejoin_requests"].append(requests)
            target = 100 * (cycle + 1)
            wait_decoded(streams, pending, lines, sink_active, target, 45.0)
            evidence["cycle_memory"].append(
                check_cycle_memory(streams, pending, lines, target)
            )
            evidence["cycles_completed"] = cycle

        starts = {role: len(lines[role]) for role in roles}
        streams["sink"].write(b"s")
        sink_stop = wait_line(streams, pending, lines, "sink",
                              "P2_STOP role=audio-broadcast-sink", starts["sink"], 30.0)
        streams["source"].write(b"s")
        source_stop = wait_line(streams, pending, lines, "source",
                                "P2_STOP role=audio-broadcast-source", starts["source"], 30.0)
        sink_match = SINK_STOP.fullmatch(sink_stop)
        source_match = SOURCE_STOP.fullmatch(source_stop)
        if sink_match is None or source_match is None:
            raise RuntimeError("broadcast STOP counters are malformed")
        evidence["decoded_frames"] = int(sink_match.group(1))
        evidence["dropped_frames"] = int(sink_match.group(2))
        evidence["source_sent_last_session"] = int(source_match.group(1))
        if (evidence["decoded_frames"] < 100 * (arguments.cycles + 1) or
                evidence["dropped_frames"] != 0 or
                evidence["source_sent_last_session"] < 100):
            raise RuntimeError("broadcast STOP counts are below the load")
        if (sum(line == "P2_READY role=audio-broadcast-source"
                for line in lines["source"]) != arguments.cycles + 1 or
                sum(line == "P2_AUDIO_REJOIN_REQUESTED"
                    for line in lines["sink"]) !=
                evidence["initial_rejoin_requests"] +
                sum(evidence["cycle_rejoin_requests"])):
            raise RuntimeError("broadcast rejoin count mismatch")
        if any("P2_AUDIO_FAIL" in line or "FAULT" in line
               for line in lines["source"]):
            raise RuntimeError("source firmware reported a failure")
        if any(line.startswith("P2_AUDIO_FAIL") and
               not line.startswith("P2_AUDIO_FAIL sink-stage")
               for line in lines["sink"]):
            raise RuntimeError("sink firmware reported an unexpected failure")
        evidence["memory_summary"] = summarize_memory(
            lines, arguments.cycles + 2
        )
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
            for role in roles:
                if role not in streams:
                    continue
                prefix = f"P2_STOP role=audio-broadcast-{role}"
                if any(line.startswith(prefix) for line in evidence["lines"][role]):
                    evidence["cleanup_observed"][role] = True
                    continue
                try:
                    start = len(evidence["lines"][role])
                    streams[role].write(b"s")
                    wait_line(streams, pending, evidence["lines"], role,
                              prefix, start, 20.0)
                    evidence["cleanup_observed"][role] = True
                except (serial.SerialException, TimeoutError, RuntimeError):
                    evidence["cleanup_observed"][role] = False
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        for role in roles:
            values = evidence["lines"][role]
            ready = [index for index, line in enumerate(values)
                     if line == f"P2_READY role=audio-broadcast-{role}"]
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
    """! @brief exact 이미지·두 probe/COM과 source reset 횟수를 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("sink", "source"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    evidence = run(parser.parse_args())
    print(f"P2 Audio broadcast rejoin HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
