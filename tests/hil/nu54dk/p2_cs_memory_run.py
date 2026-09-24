#!/usr/bin/env python3
"""! @brief 공개 CS 시험 image의 목표 raw RAS와 P2 계측을 exact 두 보드에서 기록합니다. """

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
from p2_gatt_memory_run import read_lines, require_mapping, wait_for_line


RAW_PATTERN = re.compile(
    r"^CS_RAW counter=(\d+) local=(\d+) peer=(\d+) rtt=(\d+) "
    r"tone=(\d+) valid_rtt=(\d+)(?: distance_m=([0-9.]+))?$"
)


def wait_for_new_line(streams: dict[str, serial.Serial],
                      pending: dict[str, bytearray], lines: dict[str, list[str]],
                      role: str, start_index: int, expected: str,
                      timeout: float) -> None:
    """! @brief 이전 세션 문자열을 제외하고 새 STOP·해제 신호만 기다립니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any(line.startswith("P2_FAIL")
               for values in lines.values() for line in values):
            raise RuntimeError("firmware reported P2_FAIL")
        if any(line.startswith(expected) for line in lines[role][start_index:]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report new {expected}")


def wait_for_cleanup_line(streams: dict[str, serial.Serial],
                          pending: dict[str, bytearray],
                          lines: dict[str, list[str]], role: str,
                          start_index: int, expected: str,
                          timeout: float) -> bool:
    """! @brief 실패 뒤에도 순서대로 STOP 신호를 기다려 후속 명령 충돌을 막습니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            read_lines(streams, pending, lines)
        except serial.SerialException:
            return False
        if any(line.startswith(expected) for line in lines[role][start_index:]):
            return True
        time.sleep(0.02)
    return False


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 한 번의 보안 연결에서 목표 raw 수와 양측 정지를 확인합니다. """

    if arguments.raw_target <= 0:
        raise ValueError("--raw-target must be positive")
    if arguments.timeout <= 0:
        raise ValueError("--timeout must be positive")
    if arguments.initiator_uid.lower() == arguments.reflector_uid.lower():
        raise RuntimeError("two distinct probes are required")
    for role in ("initiator", "reflector"):
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
    if {arguments.initiator_uid.lower(), arguments.reflector_uid.lower()} - probes:
        raise RuntimeError("exact probe is not present")

    evidence = {
        "schema_version": 1,
        "case": f"m31-p2-cs-{arguments.raw_target}-raw-memory",
        "raw_target": arguments.raw_target,
        "timeout_s": arguments.timeout,
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in ("initiator", "reflector")
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(
                getattr(arguments, f"{role}_uid").lower().encode("ascii")
            ).hexdigest()
            for role in ("initiator", "reflector")
        },
        "com_mapping": {
            role: {
                suffix: getattr(arguments, f"{role}_{suffix}")
                for suffix in ("app", "aux")
            }
            for role in ("initiator", "reflector")
        },
        "start": {},
        "lines": {"initiator": [], "reflector": []},
        "raw_count": 0,
        "counter_gaps": [],
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    try:
        for role in ("reflector", "initiator"):
            streams[role] = serial.Serial(
                getattr(arguments, f"{role}_app"), 115200, timeout=0.1
            )
            auxiliary[role] = serial.Serial(
                getattr(arguments, f"{role}_aux"), 115200, timeout=0.1
            )
        pending = {role: bytearray() for role in streams}
        lines = evidence["lines"]
        for role in ("reflector", "initiator"):
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            wait_for_line(streams, pending, lines, role,
                          f"P2_READY role=cs-{role}", 20.0)
        start_line_index = max(
            index for index, line in enumerate(lines["initiator"])
            if line.startswith("P2_READY role=cs-initiator")
        ) + 1

        deadline = time.monotonic() + arguments.timeout
        raw_index = 0
        previous_counter: int | None = None
        while time.monotonic() < deadline and raw_index < arguments.raw_target:
            read_lines(streams, pending, lines)
            for line in lines["initiator"][start_line_index:]:
                if (line.startswith("CS initiator failed") or
                        line.startswith("P2_FAIL")):
                    raise RuntimeError("initiator reported failure")
            if any(line.startswith("CS reflector controller error") or
                   line.startswith("P2_FAIL") for line in lines["reflector"]):
                raise RuntimeError("reflector reported failure")
            raw = [line for line in lines["initiator"][start_line_index:]
                   if line.startswith("CS_RAW ")]
            if len(raw) > raw_index:
                for line in raw[raw_index:]:
                    match = RAW_PATTERN.fullmatch(line)
                    if match is None:
                        raise RuntimeError("malformed raw RAS")
                    counter, local, peer, rtt, tone, valid = map(
                        int, match.groups()[:6]
                    )
                    if (previous_counter is not None and
                            counter != ((previous_counter + 1) & 0xFFFF)):
                        evidence["counter_gaps"].append({
                            "before": previous_counter,
                            "after": counter,
                        })
                    if local != peer or local <= 0 or rtt <= 0 or tone <= 0 or valid <= 0:
                        raise RuntimeError("invalid raw RAS")
                    previous_counter = counter
                    raw_index += 1
                    if raw_index == arguments.raw_target:
                        break
            time.sleep(0.02)
        evidence["raw_count"] = raw_index
        if raw_index != arguments.raw_target:
            raise TimeoutError("target raw RAS reports were not observed")

        initiator_stop_index = len(lines["initiator"])
        streams["initiator"].write(b"s")
        wait_for_new_line(streams, pending, lines, "initiator",
                          initiator_stop_index, "P2_STOP role=cs-initiator", 15.0)
        completed = [int(match.group(1)) for line in lines["initiator"]
                     if (match := re.fullmatch(r"P2_CS_STATS completed=(\d+)", line))]
        if len(completed) != 1 or completed[0] < arguments.raw_target:
            raise RuntimeError("initiator completion count is incomplete")
        evidence["firmware_completed"] = completed[0]
        reflector_disconnect_index = len(lines["reflector"])
        streams["initiator"].write(b"d")
        wait_for_new_line(streams, pending, lines, "reflector",
                          reflector_disconnect_index, "CS reflector disconnected", 20.0)
        reflector_stop_index = len(lines["reflector"])
        streams["reflector"].write(b"s")
        wait_for_new_line(streams, pending, lines, "reflector",
                          reflector_stop_index, "P2_STOP role=cs-reflector", 15.0)
        read_lines(streams, pending, lines)
        if any("P2_FAIL" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("firmware fault was observed")
        evidence["result"] = "HOLD" if evidence["counter_gaps"] else "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error).replace(
            arguments.initiator_uid, "<probe>"
        ).replace(arguments.reflector_uid, "<probe>")[:200]
        raise
    finally:
        if evidence["result"] == "FAIL" and streams and pending:
            evidence["cleanup_attempted"] = True
            lines = evidence["lines"]
            observed = {"initiator_stop": False, "reflector_stop": False,
                        "reflector_disconnected": False}
            if "initiator" in streams:
                observed["initiator_stop"] = any(
                    line.startswith("P2_STOP role=cs-initiator")
                    for line in lines["initiator"]
                )
                if not observed["initiator_stop"]:
                    try:
                        start = len(lines["initiator"])
                        streams["initiator"].write(b"s")
                        observed["initiator_stop"] = wait_for_cleanup_line(
                            streams, pending, lines, "initiator", start,
                            "P2_STOP role=cs-initiator", 15.0
                        )
                    except serial.SerialException:
                        pass
                try:
                    start = len(lines["reflector"])
                    streams["initiator"].write(b"d")
                    if "reflector" in streams:
                        observed["reflector_disconnected"] = wait_for_cleanup_line(
                            streams, pending, lines, "reflector", start,
                            "CS reflector disconnected", 10.0
                        )
                except serial.SerialException:
                    pass
            if "reflector" in streams:
                observed["reflector_stop"] = any(
                    line.startswith("P2_STOP role=cs-reflector")
                    for line in lines["reflector"]
                )
                if not observed["reflector_stop"]:
                    try:
                        start = len(lines["reflector"])
                        streams["reflector"].write(b"s")
                        observed["reflector_stop"] = wait_for_cleanup_line(
                            streams, pending, lines, "reflector", start,
                            "P2_STOP role=cs-reflector", 15.0
                        )
                    except serial.SerialException:
                        pass
            evidence["cleanup_observed"] = observed
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return evidence


def main() -> None:
    """! @brief exact pair와 HEX·출력 경로를 명시적으로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("initiator", "reflector"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raw-target", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=600.0)
    evidence = run(parser.parse_args())
    print(f"P2 CS memory HIL: {evidence['result']}")
    if evidence["result"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
