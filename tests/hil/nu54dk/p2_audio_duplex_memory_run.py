#!/usr/bin/env python3
"""! @brief 공개 양방향 LC3/CIS 예제의 두 역할 high-water를 실기로 계측합니다. """

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


RECEIVED = re.compile(r"LE Audio duplex received=(\d+) energy=(\d+) dropped=(\d+)")
CLIENT_SENT = re.compile(r"LE Audio duplex sent frames=(\d+)")
SERVER_SENT = re.compile(r"LE Audio duplex sent=(\d+)")
STACK = re.compile(r"P2_STACK name=(.+) reserved=(\d+) used=(\d+)")
MALLOC = re.compile(r"P2_MALLOC free=(\d+) allocated=(\d+) peak=(\d+)")


def check_faults(lines: dict[str, list[str]]) -> None:
    """! @brief UART에서 controller fault와 예제 오류를 즉시 구분합니다. """

    for role, values in lines.items():
        for line in values:
            if ("FAULT" in line or "ASSERTION FAIL" in line or
                    "failed" in line.lower() or "decode failed" in line.lower()):
                raise RuntimeError(f"{role} reported {line[:100]}")


def wait_prefix(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
                lines: dict[str, list[str]], role: str, prefix: str,
                start: int, timeout: float) -> None:
    """! @brief 현재 시작 이후의 준비·정지 신호만 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        check_faults(lines)
        if any(line.startswith(prefix) for line in lines[role][start:]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def stop_role(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
              lines: dict[str, list[str]], role: str, timeout: float,
              strict: bool = True) -> None:
    """! @brief 원본 예제 입력 루프와 경쟁하는 종료 명령을 유한 재전송합니다. """

    prefix = f"P2_STOP role=audio-duplex-{role}"
    start = len(lines[role])
    deadline = time.monotonic() + timeout
    next_request = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_request:
            streams[role].write(b"x")
            next_request = now + 0.5
        read_lines(streams, pending, lines)
        if strict:
            check_faults(lines)
        if any(line.startswith(prefix) for line in lines[role][start:]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def check_memory(lines: list[str]) -> dict[str, object]:
    """! @brief 종료 phase의 예약 대비 사용량과 libc 할당 회수를 확인합니다. """

    stopped = max((index for index, line in enumerate(lines)
                   if line == "P2_PHASE name=stopped"), default=-1)
    if stopped < 0:
        raise RuntimeError("stopped memory phase is missing")
    stacks = [match.groups() for line in lines[stopped:]
              if (match := STACK.fullmatch(line))]
    malloc = [match.groups() for line in lines[stopped:]
              if (match := MALLOC.fullmatch(line))]
    if len(stacks) < 5 or len(malloc) != 1:
        raise RuntimeError("stack or malloc telemetry is incomplete")
    if any(int(used) >= int(reserved) for _, reserved, used in stacks):
        raise RuntimeError("stack high-water reached reservation")
    if int(malloc[0][1]) != 0:
        raise RuntimeError("libc allocation remained at STOP")
    return {
        "stacks": {name: {"reserved": int(reserved), "used": int(used)}
                   for name, reserved, used in stacks},
        "malloc": {"free": int(malloc[0][0]), "allocated": int(malloc[0][1]),
                   "peak": int(malloc[0][2])},
    }


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 두 방향 각각의 송신·복호화와 종료 계측을 원본으로 보존합니다. """

    if arguments.target <= 0 or arguments.timeout <= 0:
        raise ValueError("positive target and timeout are required")
    if arguments.client_uid.lower() == arguments.server_uid.lower():
        raise ValueError("two distinct probes are required")
    for role in ("client", "server"):
        uid = getattr(arguments, f"{role}_uid")
        for suffix in ("app", "aux"):
            require_mapping(getattr(arguments, f"{role}_{suffix}"), uid)
        if not getattr(arguments, f"{role}_hex").is_file():
            raise RuntimeError(f"{role} image is missing")
    probes = {probe.unique_id.lower()
              for probe in ConnectHelper.get_all_connected_probes(
                  blocking=False, print_wait_message=False)}
    if {arguments.client_uid.lower(), arguments.server_uid.lower()} - probes:
        raise RuntimeError("exact probe is not present")

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-audio-duplex-lc3-cis-memory",
        "target_frames_each_direction": arguments.target,
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in ("client", "server")
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_uid").lower().encode()).hexdigest()
            for role in ("client", "server")
        },
        "com_mapping": {
            role: {suffix: getattr(arguments, f"{role}_{suffix}")
                   for suffix in ("app", "aux")}
            for role in ("client", "server")
        },
        "start": {},
        "lines": {"client": [], "server": []},
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    try:
        for role in ("server", "client"):
            streams[role] = serial.Serial(getattr(arguments, f"{role}_app"),
                                          115200, timeout=0.1)
            auxiliary[role] = serial.Serial(getattr(arguments, f"{role}_aux"),
                                            115200, timeout=0.1)
        pending = {role: bytearray() for role in streams}
        lines = evidence["lines"]
        for role in ("server", "client"):
            start = len(lines[role])
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            wait_prefix(streams, pending, lines, role,
                        f"P2_READY role=audio-duplex-{role}", start, 30.0)
        active = {role: max(index for index, line in enumerate(lines[role])
                            if line == f"P2_READY role=audio-duplex-{role}") + 1
                  for role in ("client", "server")}
        deadline = time.monotonic() + arguments.timeout
        totals: dict[str, dict[str, int]] = {}
        while time.monotonic() < deadline:
            read_lines(streams, pending, lines)
            check_faults(lines)
            totals = {}
            for role in ("client", "server"):
                values = lines[role][active[role]:]
                received = [tuple(map(int, match.groups())) for line in values
                            if (match := RECEIVED.fullmatch(line))]
                sent_pattern = CLIENT_SENT if role == "client" else SERVER_SENT
                sent = [int(match.group(1)) for line in values
                        if (match := sent_pattern.fullmatch(line))]
                if any(energy <= 0 or dropped != 0 for _, energy, dropped in received):
                    raise RuntimeError(f"{role} decoded silence or dropped frames")
                if received and [count for count, _, _ in received] != [
                        100 * index for index in range(1, len(received) + 1)]:
                    raise RuntimeError(f"{role} received milestone gap")
                totals[role] = {"received": received[-1][0] if received else 0,
                                "sent": sent[-1] if sent else 0}
            if all(value >= arguments.target for role in totals.values()
                   for value in role.values()):
                break
            time.sleep(0.02)
        else:
            raise TimeoutError("both-direction LC3 frame target was not observed")
        evidence["frames"] = totals
        for role in ("client", "server"):
            stop_role(streams, pending, lines, role, 20.0)
        read_lines(streams, pending, lines)
        check_faults(lines)
        evidence["memory"] = {
            role: check_memory(lines[role][active[role]:])
            for role in ("client", "server")
        }
        evidence["result"] = "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error).replace(
            arguments.client_uid, "<probe>").replace(
                arguments.server_uid, "<probe>")[:200]
        raise
    finally:
        if evidence["result"] != "PASS" and streams and pending:
            evidence["cleanup_attempted"] = True
            evidence["cleanup_observed"] = {}
            for role in ("client", "server"):
                if role not in streams:
                    continue
                prefix = f"P2_STOP role=audio-duplex-{role}"
                if any(line.startswith(prefix) for line in evidence["lines"][role]):
                    evidence["cleanup_observed"][role] = True
                    continue
                try:
                    stop_role(streams, pending, evidence["lines"], role, 20.0,
                              strict=False)
                    evidence["cleanup_observed"][role] = True
                except (serial.SerialException, RuntimeError, TimeoutError):
                    evidence["cleanup_observed"][role] = False
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return evidence


def main() -> None:
    """! @brief exact 역할·image와 양방향 frame 목표를 인자로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("client", "server"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--target", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", required=True, type=Path)
    evidence = run(parser.parse_args())
    print(f"P2 Audio duplex HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
