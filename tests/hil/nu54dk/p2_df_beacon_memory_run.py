#!/usr/bin/env python3
"""! @brief AoA CTE beacon 20회 TX 수명과 메모리 high-water를 기록합니다. """

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


CYCLE = re.compile(r"^P2_DF_CYCLE count=(\d+)$")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief exact 한 보드의 negative·20회 start/stop·종료를 검증합니다. """

    require_mapping(arguments.app, arguments.uid)
    require_mapping(arguments.aux, arguments.uid)
    if not arguments.hex.is_file():
        raise RuntimeError("beacon HEX is missing")
    probes = {
        probe.unique_id.lower()
        for probe in ConnectHelper.get_all_connected_probes(
            blocking=False, print_wait_message=False
        )
    }
    if arguments.uid.lower() not in probes:
        raise RuntimeError("exact probe is not present")

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-df-cte-beacon-20-cycle-memory",
        "image_sha256": hashlib.sha256(arguments.hex.read_bytes()).hexdigest(),
        "probe_uid_sha256": hashlib.sha256(
            arguments.uid.lower().encode("ascii")
        ).hexdigest(),
        "com_mapping": {"app": arguments.app, "aux": arguments.aux},
        "start": {},
        "lines": {"beacon": []},
        "cycles": 0,
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: serial.Serial | None = None
    pending: dict[str, bytearray] = {}
    try:
        streams["beacon"] = serial.Serial(arguments.app, 115200, timeout=0.1)
        auxiliary = serial.Serial(arguments.aux, 115200, timeout=0.1)
        pending = {"beacon": bytearray()}
        lines = evidence["lines"]
        evidence["start"] = reset_halted_start(
            {"app": streams["beacon"], "aux": auxiliary}, arguments.uid
        )
        start_index = len(lines["beacon"])
        wait_for_new_line(streams, pending, lines, "beacon", start_index,
                          "P2_READY role=df-beacon", 20.0)
        active_start = max(
            index for index, line in enumerate(lines["beacon"])
            if line == "P2_READY role=df-beacon"
        )
        deadline = time.monotonic() + 100.0
        while time.monotonic() < deadline:
            read_lines(streams, pending, lines)
            current = lines["beacon"][active_start:]
            if any("P2_DF_FAIL" in line or "FAULT" in line for line in current):
                raise RuntimeError("DF firmware failure or fault")
            cycles = [int(match.group(1)) for line in current
                      if (match := CYCLE.fullmatch(line))]
            if cycles != list(range(1, len(cycles) + 1)):
                raise RuntimeError("DF cycle gap or duplicate")
            evidence["cycles"] = len(cycles)
            if (len(cycles) == 20 and
                    "P2_DF_REJECTED cte-length" in current and
                    "P2_STOP role=df-beacon cycles=20" in current):
                evidence["result"] = "PASS"
                break
            time.sleep(0.02)
        if evidence["result"] != "PASS":
            raise TimeoutError("DF negative, 20 cycles, or STOP was not observed")
    finally:
        for stream in streams.values():
            try:
                stream.write(b"s")
            except serial.SerialException:
                pass
        if streams and pending:
            end = time.monotonic() + 3.0
            while time.monotonic() < end:
                read_lines(streams, pending, evidence["lines"])
                time.sleep(0.02)
        for stream in streams.values():
            stream.close()
        if auxiliary is not None:
            auxiliary.close()
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return evidence


def main() -> None:
    """! @brief exact probe·COM·HEX와 증거 경로를 CLI로 받습니다. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--aux", required=True)
    parser.add_argument("--hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    evidence = run(parser.parse_args())
    print(f"P2 DF beacon memory HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
