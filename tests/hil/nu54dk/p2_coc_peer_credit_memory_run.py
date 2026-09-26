#!/usr/bin/env python3
"""! @brief 상대 CoC 초기 credit 1개를 고갈하고 대기 중인 3개 SDU의 복구를 검증합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from pyocd.core.helpers import ConnectHelper
import serial

from ble_pair_hil_common import flash_image_pyocd
from onboard_start import reset_halted_start
from p2_gatt_memory_run import read_lines, require_mapping
from v04_protocol import ProbeLocks


ECHO = re.compile(r"LE CoC echo PASS, count=(\d+)")
WAIT = re.compile(r"P2_COC_CREDIT_WAIT available=(\d+) sent=(\d+) received=(\d+)")


def resolve_probes(expected: dict[str, str]) -> dict[str, str]:
    """! @brief 원시 UID를 결과에 남기지 않고 SHA-256 identity로 현재 probe를 확정합니다. """

    connected = {
        hashlib.sha256(probe.unique_id.lower().encode()).hexdigest(): probe.unique_id
        for probe in ConnectHelper.get_all_connected_probes(
            blocking=False, print_wait_message=False
        )
    }
    if len(set(expected.values())) != 2 or any(
        digest not in connected for digest in expected.values()
    ):
        raise RuntimeError("exact two-probe SHA mapping is not present")
    return {role: connected[digest] for role, digest in expected.items()}


def wait_for(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
             lines: dict[str, list[str]], role: str, prefix: str,
             start: int, timeout: float) -> None:
    """! @brief 새 출력에서 오류 없이 지정 신호를 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("P2_FAIL" in line or "FAULT" in line or "echo corrupt" in line
               for values in lines.values() for line in values):
            raise RuntimeError("CoC firmware reported a failure")
        if any(line.startswith(prefix) for line in lines[role][start:]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief flash·credit 고갈·2초 dwell·반환·새 SDU 복구·STOP을 기록합니다. """

    images = {
        "client": arguments.client_hex.resolve(),
        "peer": arguments.peer_hex.resolve(),
    }
    if any(path.suffix.lower() != ".hex" or not path.is_file()
           for path in images.values()):
        raise RuntimeError("two exact HEX images are required")
    hashes = {
        "client": arguments.client_probe_sha256,
        "peer": arguments.peer_probe_sha256,
    }
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes.values()):
        raise ValueError("probe identities must be lowercase SHA-256")
    probe_ids = resolve_probes(hashes)
    ports = {"client": arguments.client_port, "peer": arguments.peer_port}
    for role in ports:
        require_mapping(ports[role], probe_ids[role])

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-coc-direct-peer-credit-exhaustion-recovery-memory",
        "contract": {
            "role": "one Arduino central, one native peripheral",
            "channels": 2,
            "sdu_bytes": 512,
            "peer_initial_credits": 1,
            "client_submitted_sdus": 4,
            "dwell_ms": arguments.dwell_ms,
            "expected_error": "finite remote-credit wait; no synthetic PASS retry",
            "recovery": (
                "return the one held peer credit, drain three queued SDUs, "
                "and echo one new 512-byte SDU"
            ),
            "timeout_s": arguments.timeout,
        },
        "probe_uid_sha256": hashes,
        "com_mapping": ports,
        "image_sha256": {
            role: hashlib.sha256(path.read_bytes()).hexdigest()
            for role, path in images.items()
        },
        "flash": {},
        "start": {},
        "lines": {"client": [], "peer": []},
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    deadline = time.monotonic() + arguments.timeout
    try:
        with ProbeLocks(probe_ids.values()):
            for role in ("peer", "client"):
                evidence["flash"][role] = flash_image_pyocd(
                    role, probe_ids[role], images[role], 120.0
                )
            for role in ports:
                streams[role] = serial.Serial(ports[role], 115200, timeout=0.1)
                auxiliary[role] = serial.Serial(
                    arguments.client_aux if role == "client" else arguments.peer_aux,
                    115200, timeout=0.1
                )
            pending = {role: bytearray() for role in streams}
            lines = evidence["lines"]
            for role in ("peer", "client"):
                start = len(lines[role])
                evidence["start"][role] = reset_halted_start(
                    {"app": streams[role], "aux": auxiliary[role]}, probe_ids[role]
                )
                wait_for(streams, pending, lines, role,
                         "P2_READY role=coc-credit-peer" if role == "peer"
                         else "P2_READY role=coc-client", start, 30.0)
            wait_for(streams, pending, lines, "client",
                     "LE CoC channel ready, count=2", 0, 45.0)
            wait_for(streams, pending, lines, "client",
                     "LE CoC echo PASS, count=2", 0, 30.0)

            peer_start = len(lines["peer"])
            streams["peer"].write(b"h")
            wait_for(streams, pending, lines, "peer",
                     "P2_COC_PEER_HOLD_ARMED", peer_start, 10.0)
            client_start = len(lines["client"])
            streams["client"].write(b"c")
            wait_for(streams, pending, lines, "client",
                     "P2_COC_CREDIT_SENT accepted=4", client_start, 10.0)
            wait_for(streams, pending, lines, "peer",
                     "P2_COC_PEER_CREDITS_EXHAUSTED held=1", peer_start, 15.0)
            exhausted_at = time.monotonic()
            held_before = sum(line.startswith("P2_COC_PEER_CREDIT_HELD")
                              for line in lines["peer"][peer_start:])
            while time.monotonic() - exhausted_at < arguments.dwell_ms / 1000.0:
                if time.monotonic() >= deadline:
                    raise TimeoutError("global command lease expired")
                read_lines(streams, pending, lines)
                if any("P2_FAIL" in line or "FAULT" in line
                       for values in lines.values() for line in values):
                    raise RuntimeError("failure during peer-credit dwell")
                time.sleep(0.02)
            held_after = sum(line.startswith("P2_COC_PEER_CREDIT_HELD")
                             for line in lines["peer"][peer_start:])
            if held_before != 1 or held_after != 1:
                raise RuntimeError("held credit count changed during bounded dwell")

            query_start = len(lines["client"])
            streams["client"].write(b"q")
            wait_for(streams, pending, lines, "client",
                     "P2_COC_CREDIT_WAIT", query_start, 10.0)
            wait_match = next(
                (match for line in lines["client"][query_start:]
                 if (match := WAIT.fullmatch(line))), None
            )
            if wait_match is None or int(wait_match.group(3)) != 2:
                raise RuntimeError("client received data while peer credits were exhausted")

            release_start = len(lines["peer"])
            streams["peer"].write(b"r")
            wait_for(streams, pending, lines, "peer",
                     "P2_COC_PEER_CREDITS_RELEASED count=1", release_start, 10.0)
            wait_for(streams, pending, lines, "client",
                     "LE CoC echo PASS, count=5", query_start, 20.0)
            recovery_start = len(lines["client"])
            streams["client"].write(b"v")
            wait_for(streams, pending, lines, "client",
                     "P2_COC_CREDIT_RECOVERY_SENT", recovery_start, 10.0)
            wait_for(streams, pending, lines, "client",
                     "P2_COC_CREDIT_RECOVERED echoes=1", recovery_start, 20.0)

            client_stop = len(lines["client"])
            streams["client"].write(b"s")
            wait_for(streams, pending, lines, "client",
                     "P2_STOP role=coc-client", client_stop, 15.0)
            wait_for(streams, pending, lines, "peer",
                     "P2_COC_PEER_DISCONNECTED", release_start, 15.0)
            peer_stop = len(lines["peer"])
            streams["peer"].write(b"s")
            wait_for(streams, pending, lines, "peer",
                     "P2_STOP role=coc-credit-peer bt_disable=0", peer_stop, 15.0)
            evidence["observed"] = {
                "initial_echoes": 2,
                "held_credits": held_after,
                "dwell_ms": arguments.dwell_ms,
                "queued_echoes_after_credit_return": 3,
                "new_sdu_echoes": 1,
                "both_stopped": True,
            }
            evidence["result"] = "PASS"
    except Exception as error:
        evidence["failure_class"] = type(error).__name__
        evidence["failure_detail"] = str(error)[:240]
        raise
    finally:
        if evidence["result"] != "PASS" and streams and pending:
            evidence["cleanup_attempted"] = True
            for role in ("client", "peer"):
                if role in streams:
                    try:
                        streams[role].write(b"s")
                    except serial.SerialException:
                        pass
            stop_deadline = time.monotonic() + 10.0
            while time.monotonic() < stop_deadline:
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
    """! @brief SHA identity·COM·두 image·유한 lease를 명시적으로 받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("client", "peer"):
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-port", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dwell-ms", type=int, default=2500)
    parser.add_argument("--timeout", type=float, default=240.0)
    arguments = parser.parse_args()
    if arguments.dwell_ms < 2000 or arguments.timeout <= 0:
        parser.error("dwell must be at least 2000 ms and timeout must be positive")
    evidence = run(arguments)
    print(f"P2 CoC peer credit HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
