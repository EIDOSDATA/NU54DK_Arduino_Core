#!/usr/bin/env python3
"""! @brief LE CoC 두 채널·512 B echo와 메모리 high-water를 실기 기록합니다. """

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
from p2_cs_memory_run import wait_for_new_line


ECHO_PATTERN = re.compile(r"^LE CoC echo PASS, count=(\d+)$")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief exact 두 보드에서 100회 512 B echo와 양측 STOP을 확인합니다. """

    if arguments.client_uid.lower() == arguments.server_uid.lower():
        raise RuntimeError("two distinct probes are required")
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
        "case": "m31-p2-coc-two-channel-512-memory",
        "image_sha256": {
            role: hashlib.sha256(getattr(arguments, f"{role}_hex").read_bytes()).hexdigest()
            for role in ("client", "server")
        },
        "probe_uid_sha256": {
            role: hashlib.sha256(
                getattr(arguments, f"{role}_uid").lower().encode("ascii")
            ).hexdigest()
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
        "lines": {"client": [], "server": []},
        "echo_count": 0,
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    try:
        for role in ("server", "client"):
            streams[role] = serial.Serial(
                getattr(arguments, f"{role}_app"), 115200, timeout=0.1
            )
            auxiliary[role] = serial.Serial(
                getattr(arguments, f"{role}_aux"), 115200, timeout=0.1
            )
        pending = {role: bytearray() for role in streams}
        lines = evidence["lines"]
        for role in ("server", "client"):
            evidence["start"][role] = reset_halted_start(
                {"app": streams[role], "aux": auxiliary[role]},
                getattr(arguments, f"{role}_uid"),
            )
            start_index = len(lines[role])
            wait_for_new_line(streams, pending, lines, role, start_index,
                              f"P2_READY role=coc-{role}", 20.0)

        start_index = max(
            index for index, line in enumerate(lines["client"])
            if line.startswith("P2_READY role=coc-client")
        ) + 1
        deadline = time.monotonic() + 180.0
        echo_count = 0
        while time.monotonic() < deadline and echo_count < 100:
            read_lines(streams, pending, lines)
            if any("P2_FAIL" in line or "echo corrupt" in line or
                   "echo failed" in line for values in lines.values()
                   for line in values):
                raise RuntimeError("CoC reported failure or corrupted echo")
            echoes = [int(match.group(1)) for line in lines["client"][start_index:]
                      if (match := ECHO_PATTERN.fullmatch(line))]
            if echoes:
                if echoes != list(range(1, len(echoes) + 1)):
                    raise RuntimeError("CoC echo count gap or duplicate")
                echo_count = len(echoes)
            time.sleep(0.02)
        evidence["echo_count"] = echo_count
        if echo_count < 100:
            raise TimeoutError("100 full-size CoC echoes were not observed")

        client_stop_index = len(lines["client"])
        server_disconnect_index = len(lines["server"])
        streams["client"].write(b"s")
        wait_for_new_line(streams, pending, lines, "client", client_stop_index,
                          "P2_STOP role=coc-client", 15.0)
        wait_for_new_line(streams, pending, lines, "server", server_disconnect_index,
                          "LE CoC disconnected", 20.0)
        server_stop_index = len(lines["server"])
        streams["server"].write(b"s")
        wait_for_new_line(streams, pending, lines, "server", server_stop_index,
                          "P2_STOP role=coc-server", 15.0)
        read_lines(streams, pending, lines)
        if any("P2_FAIL" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("CoC firmware fault was observed")
        evidence["result"] = "PASS"
    finally:
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
    for role in ("server", "client"):
        parser.add_argument(f"--{role}-uid", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    evidence = run(parser.parse_args())
    print(f"P2 CoC memory HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
