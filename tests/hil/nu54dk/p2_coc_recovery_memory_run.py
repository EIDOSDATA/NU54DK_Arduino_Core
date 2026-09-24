#!/usr/bin/env python3
"""! @brief 두 채널 512 B CoC의 반복 ACL/peer reset 복구를 검증합니다. """

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


ECHO = re.compile(r"LE CoC echo PASS, count=(\d+)")


def wait_for_prefix(streams: dict[str, serial.Serial],
                    pending: dict[str, bytearray], lines: dict[str, list[str]],
                    role: str, prefix: str, start: int, timeout: float) -> None:
    """! @brief 직전 단계 이후의 출력에서 원하는 신호만 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("P2_FAIL" in line or "echo corrupt" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("CoC firmware reported a failure")
        if any(line.startswith(prefix) for line in lines[role][start:]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def wait_for_echoes(streams: dict[str, serial.Serial],
                    pending: dict[str, bytearray], lines: dict[str, list[str]],
                    start: int, target: int, timeout: float) -> None:
    """! @brief 512 B echo 누적수가 건너뛰지 않고 목표에 도달하는지 검사합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("P2_FAIL" in line or "echo corrupt" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("CoC firmware reported a failure")
        counts = [int(match.group(1)) for line in lines["client"][start:]
                  if (match := ECHO.fullmatch(line))]
        if counts != list(range(1, len(counts) + 1)):
            raise RuntimeError("CoC echo count gap or duplicate")
        if len(counts) >= target:
            return
        time.sleep(0.02)
    raise TimeoutError(f"CoC did not reach {target} echoes")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief exact 두 보드의 반복 복구와 STOP을 기록합니다. """

    if arguments.cycles <= 0 or arguments.client_uid.lower() == arguments.server_uid.lower():
        raise ValueError("positive cycles and two distinct probes are required")
    for role in ("client", "server"):
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
    if {arguments.client_uid.lower(), arguments.server_uid.lower()} - probes:
        raise RuntimeError("exact probe is not present")

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-coc-two-channel-512-recovery-memory",
        "recovery_mode": arguments.recovery_mode,
        "cycles_target": arguments.cycles,
        "cycles_completed": 0,
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in ("client", "server")
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_uid").lower().encode()).hexdigest()
            for role in ("client", "server")
        },
        "com_mapping": {
            role: {
                suffix: getattr(arguments, f"{role}_{suffix}")
                for suffix in ("app", "aux")
            }
            for role in ("client", "server")
        },
        "start": {},
        "peer_restart": [],
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
        client_active_start = 0
        for role in ("server", "client"):
            start = len(lines[role])
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            wait_for_prefix(streams, pending, lines, role,
                            f"P2_READY role=coc-{role}", start, 30.0)
            if role == "client":
                client_active_start = max(
                    index for index, line in enumerate(lines["client"])
                    if line == "P2_READY role=coc-client"
                ) + 1
        wait_for_echoes(streams, pending, lines, client_active_start, 2, 30.0)

        for cycle in range(1, arguments.cycles + 1):
            client_start = len(lines["client"])
            server_start = len(lines["server"])
            if arguments.recovery_mode == "acl-disconnect":
                streams["client"].write(b"d")
                wait_for_prefix(streams, pending, lines, "client",
                                "P2_COC_DISCONNECT_REQUESTED", client_start, 15.0)
                wait_for_prefix(streams, pending, lines, "client",
                                "P2_COC_DISCONNECTED", client_start, 20.0)
                wait_for_prefix(streams, pending, lines, "server",
                                "LE CoC disconnected", server_start, 20.0)
            else:
                evidence["peer_restart"].append(reset_halted_start(
                    {"app": streams["server"], "aux": auxiliary["server"]},
                    arguments.server_uid,
                ))
                wait_for_prefix(streams, pending, lines, "server",
                                "P2_READY role=coc-server", server_start, 30.0)
                wait_for_prefix(streams, pending, lines, "client",
                                "P2_COC_DISCONNECTED", client_start, 30.0)
            wait_for_prefix(streams, pending, lines, "client",
                            "LE CoC channel ready, count=2", client_start, 45.0)
            wait_for_echoes(streams, pending, lines, client_active_start,
                            (cycle + 1) * 2, 45.0)
            evidence["cycles_completed"] = cycle

        client_start = len(lines["client"])
        server_start = len(lines["server"])
        streams["client"].write(b"s")
        wait_for_prefix(streams, pending, lines, "client",
                        "P2_STOP role=coc-client", client_start, 20.0)
        wait_for_prefix(streams, pending, lines, "server",
                        "LE CoC disconnected", server_start, 20.0)
        server_start = len(lines["server"])
        streams["server"].write(b"s")
        wait_for_prefix(streams, pending, lines, "server",
                        "P2_STOP role=coc-server", server_start, 20.0)
        evidence["echo_count"] = sum(ECHO.fullmatch(line) is not None
                                     for line in lines["client"][client_active_start:])
        expected_echoes = (arguments.cycles + 1) * 2
        ready_channels = sum(line == "LE CoC channel ready, count=2"
                             for line in lines["client"][client_active_start:])
        if evidence["echo_count"] != expected_echoes or ready_channels != arguments.cycles + 1:
            raise RuntimeError("CoC recovery completion count mismatch")
        if arguments.recovery_mode == "peer-reset":
            server_ready = sum(line == "P2_READY role=coc-server"
                               for line in lines["server"])
            if server_ready != arguments.cycles + 1 or len(evidence["peer_restart"]) != arguments.cycles:
                raise RuntimeError("CoC peer restart count mismatch")
        evidence["result"] = "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error).replace(
            arguments.client_uid, "<probe>"
        ).replace(arguments.server_uid, "<probe>")[:200]
        raise
    finally:
        if evidence["result"] != "PASS" and streams and pending:
            evidence["cleanup_attempted"] = True
            evidence["cleanup_observed"] = {}
            for role in ("client", "server"):
                if role not in streams:
                    continue
                prefix = f"P2_STOP role=coc-{role}"
                if any(line.startswith(prefix) for line in evidence["lines"][role]):
                    evidence["cleanup_observed"][role] = True
                    continue
                try:
                    start = len(evidence["lines"][role])
                    streams[role].write(b"s")
                    wait_for_prefix(streams, pending, evidence["lines"], role,
                                    prefix, start, 20.0)
                    evidence["cleanup_observed"][role] = True
                except (serial.SerialException, TimeoutError, RuntimeError):
                    evidence["cleanup_observed"][role] = False
        for stream in (*streams.values(), *auxiliary.values()):
            stream.close()
        for role in ("client", "server"):
            values = evidence["lines"][role]
            ready = [index for index, line in enumerate(values)
                     if line == f"P2_READY role=coc-{role}"]
            if ready:
                first_active = ready[0] if arguments.recovery_mode == "peer-reset" else ready[-1]
                values = values[first_active:]
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
    """! @brief exact image·UID/COM과 반복 횟수를 명시적으로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("client", "server"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--recovery-mode", choices=("acl-disconnect", "peer-reset"),
                        default="acl-disconnect")
    evidence = run(parser.parse_args())
    print(f"P2 CoC recovery HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
