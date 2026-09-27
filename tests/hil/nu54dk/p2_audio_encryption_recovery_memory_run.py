#!/usr/bin/env python3
"""! @brief 지원 encrypted BIS의 wrong-code 오류와 올바른 code 복구를 검증합니다. """

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


REJECTED = re.compile(r"P2_AUDIO_ENCRYPTION_REJECTED native=(-?\d+) decoded=(\d+) dropped=(\d+)")
RECOVERED = re.compile(r"P2_AUDIO_ENCRYPTION_RECOVERED frames=(\d+) dropped=(\d+) energy=(\d+)")


def resolve_probes(expected: dict[str, str]) -> dict[str, str]:
    """! @brief SHA-256 identity와 현재 probe를 원시 UID 비기록 상태로 결합합니다. """

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
             start: int, timeout: float) -> None:
    """! @brief 오류·fault를 감시하며 단계 완료를 유한 대기합니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        if any("P2_AUDIO_FAIL" in line or "FAULT" in line
               for values in lines.values() for line in values):
            raise RuntimeError("audio firmware reported a failure")
        if any(line.startswith(prefix) for line in lines[role][start:]):
            return
        time.sleep(0.02)
    raise TimeoutError(f"{role} did not report {prefix}")


def run(arguments: argparse.Namespace) -> dict:
    """! @brief 두 exact image를 sector flash하고 오류·복구·메모리·STOP을 기록합니다. """

    roles = ("source", "sink")
    images = {role: getattr(arguments, f"{role}_hex").resolve() for role in roles}
    if any(path.suffix.lower() != ".hex" or not path.is_file()
           for path in images.values()):
        raise RuntimeError("two exact HEX images are required")
    hashes = {role: getattr(arguments, f"{role}_probe_sha256") for role in roles}
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes.values()):
        raise ValueError("probe identities must be lowercase SHA-256")
    probe_ids = resolve_probes(hashes)
    ports = {role: getattr(arguments, f"{role}_port") for role in roles}
    for role in roles:
        require_mapping(ports[role], probe_ids[role])

    evidence = {
        "schema_version": 1,
        "case": "m31-p2-audio-supported-encrypted-bis-error-recovery-memory",
        "contract": {
            "role": "one encrypted LC3 BIS source and one sink",
            "streams": 1,
            "codec": "LC3 16 kHz mono, 40-byte/10-ms frame",
            "security": "16-byte Broadcast Code; first code differs by one byte",
            "expected_error": -61,
            "recovery": "same source, correct code, at least 100 decoded frames",
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
        "lines": {role: [] for role in roles},
        "result": "FAIL",
    }
    streams: dict[str, serial.Serial] = {}
    auxiliary: dict[str, serial.Serial] = {}
    pending: dict[str, bytearray] = {}
    try:
        with ProbeLocks(probe_ids.values()):
            for role in ("sink", "source"):
                evidence["flash"][role] = flash_image_pyocd(
                    role, probe_ids[role], images[role], 120.0
                )
            for role in roles:
                streams[role] = serial.Serial(ports[role], 115200, timeout=0.1)
                auxiliary[role] = serial.Serial(
                    getattr(arguments, f"{role}_aux"), 115200, timeout=0.1
                )
            pending = {role: bytearray() for role in roles}
            lines = evidence["lines"]
            for role in ("source", "sink"):
                start = len(lines[role])
                evidence["start"][role] = reset_halted_start(
                    {"app": streams[role], "aux": auxiliary[role]}, probe_ids[role]
                )
                wait_for(streams, pending, lines, role,
                         "P2_READY role=audio-broadcast-source" if role == "source"
                         else "P2_READY role=audio-broadcast-error-sink",
                         start, 30.0)

            wait_for(streams, pending, lines, "sink",
                     "P2_AUDIO_ENCRYPTION_REJECTED", 0, arguments.timeout / 2.0)
            rejected = next(
                (match for line in lines["sink"] if (match := REJECTED.fullmatch(line))),
                None,
            )
            if rejected is None or tuple(map(int, rejected.groups())) != (-61, 0, 0):
                raise RuntimeError("wrong-code error contract mismatch")
            wait_for(streams, pending, lines, "sink",
                     "P2_AUDIO_ENCRYPTION_RECOVERY_STARTED", 0, 15.0)
            wait_for(streams, pending, lines, "sink",
                     "P2_AUDIO_ENCRYPTION_RECOVERED", 0, arguments.timeout / 2.0)
            recovered = next(
                (match for line in lines["sink"] if (match := RECOVERED.fullmatch(line))),
                None,
            )
            if recovered is None:
                raise RuntimeError("encrypted audio recovery record is missing")
            frames, dropped, energy = map(int, recovered.groups())
            if frames < 100 or dropped != 0 or energy == 0:
                raise RuntimeError("encrypted audio recovery payload contract mismatch")

            for role in ("sink", "source"):
                start = len(lines[role])
                streams[role].write(b"s")
                wait_for(streams, pending, lines, role,
                         "P2_STOP role=audio-broadcast-error-sink" if role == "sink"
                         else "P2_STOP role=audio-broadcast-source", start, 20.0)
            evidence["observed"] = {
                "expected_native_error": -61,
                "frames_before_error": 0,
                "recovered_frames": frames,
                "dropped_frames": dropped,
                "nonzero_pcm_energy": True,
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
    """! @brief image·SHA identity·COM·유한 timeout을 입력받습니다. """

    parser = argparse.ArgumentParser()
    for role in ("source", "sink"):
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-port", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--{role}-hex", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=180.0)
    arguments = parser.parse_args()
    if arguments.timeout <= 0:
        parser.error("timeout must be positive")
    evidence = run(arguments)
    print(f"P2 encrypted audio recovery HIL: {evidence['result']}")


if __name__ == "__main__":
    main()
