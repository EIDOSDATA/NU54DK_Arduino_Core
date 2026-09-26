#!/usr/bin/env python3
"""! @brief 계측용 Nordic RAS 두 image의 실기 결과와 양측 정지를 기록합니다. """

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


PROGRESS = re.compile(r"NATIVE_CS_PROGRESS valid=(\d+) last=(\d+) gaps=(\d+)")
STATS = re.compile(
    r"NATIVE_CS_STATS callbacks=(\d+) aborts=(\d+) busy=(\d+) valid=(\d+) "
    r"errors=(\d+) mismatch=(\d+) empty=(\d+) gaps=(\d+) last=(-?\d+)"
)


def wait_for_prefix(streams: dict[str, serial.Serial],
                    pending: dict[str, bytearray], lines: dict[str, list[str]],
                    role: str, prefix: str, start: int, timeout: float) -> str:
    """! @brief 이전 출력과 구별한 신규 상태 줄을 유한 시간 내에 기다립니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        for line in lines[role][start:]:
            if line.startswith(prefix):
                return line
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief exact probe·COM을 검증한 뒤 목표 건수와 정상 종료를 확인합니다. """

    if arguments.valid_target <= 0 or arguments.timeout <= 0:
        raise ValueError("target and timeout must be positive")
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
        "case": "m31-p2-nordic-ras-comparison",
        "valid_target": arguments.valid_target,
        "timeout_s": arguments.timeout,
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in ("initiator", "reflector")
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_uid").lower().encode()).hexdigest()
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
            start = len(lines[role])
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            wait_for_prefix(streams, pending, lines, role,
                            f"NATIVE_CS_READY role={role}", start, 30.0)

        progress_index = 0
        latest_valid = 0
        deadline = time.monotonic() + arguments.timeout
        while time.monotonic() < deadline and latest_valid < arguments.valid_target:
            read_lines(streams, pending, lines)
            if any("FAULT" in line or "ASSERTION FAIL" in line
                   for values in lines.values() for line in values):
                raise RuntimeError("native fixture fault was observed")
            progress = [line for line in lines["initiator"]
                        if line.startswith("NATIVE_CS_PROGRESS ")]
            for line in progress[progress_index:]:
                match = PROGRESS.fullmatch(line)
                if match is None:
                    raise RuntimeError("malformed native progress")
                latest_valid = int(match.group(1))
            progress_index = len(progress)
            time.sleep(0.02)
        if latest_valid < arguments.valid_target:
            raise TimeoutError("native valid report target not observed")

        start = len(lines["initiator"])
        streams["initiator"].write(b"s")
        stop = wait_for_prefix(streams, pending, lines, "initiator",
                               "NATIVE_CS_STOP role=initiator", start, 15.0)
        stats_lines = [line for line in lines["initiator"] if line.startswith("NATIVE_CS_STATS ")]
        if len(stats_lines) != 1 or (match := STATS.fullmatch(stats_lines[0])) is None:
            raise RuntimeError("native statistics are missing or malformed")
        evidence["statistics"] = dict(zip(
            ("callbacks", "aborts", "busy", "valid", "errors", "mismatch",
             "empty", "gaps", "last"), map(int, match.groups())
        ))
        if evidence["statistics"]["valid"] < arguments.valid_target:
            raise RuntimeError("native final valid count is incomplete")
        if not re.fullmatch(r"NATIVE_CS_STOP role=initiator disable=0 disconnect=0 observed=1", stop):
            raise RuntimeError("initiator did not disconnect cleanly")
        start = len(lines["reflector"])
        streams["reflector"].write(b"s")
        stop = wait_for_prefix(streams, pending, lines, "reflector",
                               "NATIVE_CS_STOP role=reflector", start, 15.0)
        if not re.fullmatch(r"NATIVE_CS_STOP role=reflector disconnect=0 observed=1 adv=0", stop):
            raise RuntimeError("reflector did not stop cleanly")
        evidence["result"] = "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error).replace(
            arguments.initiator_uid, "<probe>"
        ).replace(arguments.reflector_uid, "<probe>")[:200]
        raise
    finally:
        if evidence["result"] != "PASS" and streams and pending:
            evidence["cleanup_attempted"] = True
            evidence["cleanup_observed"] = {}
            for role in ("initiator", "reflector"):
                if role not in streams:
                    continue
                if any(line.startswith(f"NATIVE_CS_STOP role={role}")
                       for line in evidence["lines"][role]):
                    evidence["cleanup_observed"][role] = True
                    continue
                try:
                    start = len(evidence["lines"][role])
                    streams[role].write(b"s")
                    wait_for_prefix(streams, pending, evidence["lines"], role,
                                    f"NATIVE_CS_STOP role={role}", start, 15.0)
                    evidence["cleanup_observed"][role] = True
                except (serial.SerialException, TimeoutError):
                    evidence["cleanup_observed"][role] = False
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        for role in ("initiator", "reflector"):
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
    """! @brief image와 exact 두 보드·목표 건수를 명시적으로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("initiator", "reflector"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--valid-target", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=600.0)
    evidence = run(parser.parse_args())
    print(f"P2 Nordic RAS comparison: {evidence['result']}")


if __name__ == "__main__":
    main()
