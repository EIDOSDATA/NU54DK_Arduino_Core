#!/usr/bin/env python3
"""! @brief 256-step CS 절차 중 reflector reset과 자동 복구를 검증합니다. """

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


RAW = re.compile(
    r"CS_RAW counter=(\d+) local=(\d+) peer=(\d+) rtt=(\d+) tone=(\d+) "
    r"valid_rtt=(\d+)(?: distance_m=(-?[0-9.]+))?"
)


def resolve_probes(expected: dict[str, str]) -> dict[str, str]:
    """! @brief 두 SHA-256 identity를 현재 exact probe에 결합합니다. """

    connected = {
        hashlib.sha256(probe.unique_id.lower().encode()).hexdigest(): probe.unique_id
        for probe in ConnectHelper.get_all_connected_probes(
            blocking=False, print_wait_message=False
        )
    }
    if len(set(expected.values())) != 2 or any(
        value not in connected for value in expected.values()
    ):
        raise RuntimeError("exact two-probe SHA mapping is not present")
    return {role: connected[value] for role, value in expected.items()}


def wait_for(streams: dict[str, serial.Serial], pending: dict[str, bytearray],
             lines: dict[str, list[str]], role: str, prefix: str,
             start: int, timeout: float, *, allow_transient_failure: bool = False) -> None:
    """! @brief fault를 감시하며 새 단계 신호를 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("P2_FAIL" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("CS firmware reported a fault")
        if not allow_transient_failure and any(
            line.startswith("CS initiator failed:")
            for line in lines["initiator"][start:]
        ):
            raise RuntimeError("unexpected CS initiator failure")
        if any(line.startswith(prefix) for line in lines[role][start:]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def wait_for_valid_raw(streams: dict[str, serial.Serial],
                       pending: dict[str, bytearray], lines: dict[str, list[str]],
                       start: int, target: int, timeout: float) -> list[int]:
    """! @brief 복구 뒤 정확한 256/256 유효 raw만 목표 수까지 받습니다. """

    deadline = time.monotonic() + timeout
    counters: list[int] = []
    consumed = start
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("P2_FAIL" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("CS firmware reported a fault")
        for line in lines["initiator"][consumed:]:
            match = RAW.fullmatch(line)
            if match is None:
                continue
            counter, local, peer, rtt, tone, valid = map(int, match.groups()[:6])
            if local != 256 or peer != 256 or rtt <= 0 or tone <= 0 or valid <= 0:
                raise RuntimeError("recovered max-procedure raw is invalid")
            counters.append(counter)
        consumed = len(lines["initiator"])
        if len(counters) >= target:
            return counters
        time.sleep(0.02)
    raise TimeoutError("recovered 256-step raw target was not reached")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 첫 max procedure 활성 구간에 peer를 reset하고 같은 image로 복구합니다. """

    roles = ("initiator", "reflector")
    images = {role: getattr(arguments, f"{role}_hex").resolve() for role in roles}
    if any(path.suffix.lower() != ".hex" or not path.is_file()
           for path in images.values()):
        raise RuntimeError("two exact HEX images are required")
    hashes = {role: getattr(arguments, f"{role}_probe_sha256") for role in roles}
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes.values()):
        raise ValueError("probe identities must be lowercase SHA-256")
    probe_ids = resolve_probes(hashes)
    ports = {
        role: {
            "app": getattr(arguments, f"{role}_app"),
            "aux": getattr(arguments, f"{role}_aux"),
        }
        for role in roles
    }
    for role in roles:
        for port in ports[role].values():
            require_mapping(port, probe_ids[role])

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-cs-256-step-peer-loss-recovery-memory",
        "contract": {
            "role": "one RAS initiator and one reflector",
            "security": "LE security before CS configuration",
            "procedure": "256 local and peer steps per valid raw",
            "injection": "reflector reset after procedures-enabled and before first raw",
            "expected_error": "bounded ACL disconnect; transient controller error is recorded",
            "recovery": f"automatic reconnect and {arguments.raw_target} new valid raw reports",
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
        "peer_restart": None,
        "lines": {role: [] for role in roles},
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    try:
        with ProbeLocks(probe_ids.values()):
            for role in ("reflector", "initiator"):
                evidence["flash"][role] = flash_image_pyocd(
                    role, probe_ids[role], images[role], 120.0
                )
            for role in roles:
                streams[role] = serial.Serial(ports[role]["app"], 115200, timeout=0.1)
                auxiliary[role] = serial.Serial(ports[role]["aux"], 115200, timeout=0.1)
            pending = {role: bytearray() for role in roles}
            lines = evidence["lines"]
            for role in ("reflector", "initiator"):
                start = len(lines[role])
                evidence["start"][role] = reset_halted_start(
                    {"app": streams[role], "aux": auxiliary[role]}, probe_ids[role]
                )
                wait_for(streams, pending, lines, role,
                         f"P2_READY role=cs-{role}", start, 30.0)

            active_start = len(lines["reflector"])
            wait_for(streams, pending, lines, "reflector",
                     "CS procedures enabled", active_start, 60.0)
            read_lines(streams, pending, lines)
            if any(RAW.fullmatch(line) is not None
                   for line in lines["initiator"]):
                raise RuntimeError("first raw completed before peer-loss injection")
            time.sleep(arguments.injection_delay_ms / 1000.0)
            disconnect_start = len(lines["initiator"])
            reflector_ready_start = len(lines["reflector"])
            evidence["peer_restart"] = reset_halted_start(
                {"app": streams["reflector"], "aux": auxiliary["reflector"]},
                probe_ids["reflector"],
            )
            evidence["injection_observed_at"] = "procedures-enabled-before-first-raw"
            wait_for(streams, pending, lines, "initiator",
                     "CS initiator disconnected", disconnect_start, 30.0,
                     allow_transient_failure=True)
            wait_for(streams, pending, lines, "reflector",
                     "P2_READY role=cs-reflector", reflector_ready_start, 30.0,
                     allow_transient_failure=True)

            recovered_start = len(lines["initiator"])
            wait_for(streams, pending, lines, "initiator",
                     "CS procedures requested", recovered_start, 60.0,
                     allow_transient_failure=True)
            counters = wait_for_valid_raw(
                streams, pending, lines, recovered_start,
                arguments.raw_target, arguments.timeout / 2.0
            )
            if len(counters) != len(set(counters)):
                raise RuntimeError("recovered counters contain duplicates")

            initiator_stop = len(lines["initiator"])
            streams["initiator"].write(b"s")
            wait_for(streams, pending, lines, "initiator",
                     "P2_STOP role=cs-initiator", initiator_stop, 20.0,
                     allow_transient_failure=True)
            reflector_disconnect = len(lines["reflector"])
            streams["initiator"].write(b"d")
            wait_for(streams, pending, lines, "reflector",
                     "CS reflector disconnected", reflector_disconnect, 20.0,
                     allow_transient_failure=True)
            reflector_stop = len(lines["reflector"])
            streams["reflector"].write(b"s")
            wait_for(streams, pending, lines, "reflector",
                     "P2_STOP role=cs-reflector", reflector_stop, 20.0,
                     allow_transient_failure=True)
            evidence["observed"] = {
                "peer_loss_before_first_raw": True,
                "initiator_disconnect": True,
                "reflector_reboot_ready": True,
                "recovered_raw_count": len(counters),
                "recovered_first_counter": counters[0],
                "recovered_last_counter": counters[-1],
                "duplicates": 0,
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
            for role in roles:
                if role in streams:
                    try:
                        streams[role].write(b"s")
                    except serial.SerialException:
                        pass
            end = time.monotonic() + 10.0
            while time.monotonic() < end:
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
    """! @brief exact image·SHA identity·COM·최대 시간을 입력받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("initiator", "reflector"):
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raw-target", type=int, default=20)
    parser.add_argument("--injection-delay-ms", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=300.0)
    arguments = parser.parse_args()
    if arguments.raw_target <= 0 or arguments.injection_delay_ms < 0 or arguments.timeout <= 0:
        parser.error("targets and timeout must be positive")
    evidence = run(arguments)
    print(f"P2 CS peer-loss HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
