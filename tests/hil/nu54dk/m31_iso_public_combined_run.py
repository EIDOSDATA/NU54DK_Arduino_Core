#!/usr/bin/env python3
"""! @brief 세 Arduino 공개 예제의 CIS 수신→BIS 전달을 실기합니다. """

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
from threading import Thread
import time

from pyocd.core.helpers import ConnectHelper
import serial

from ble_pair_hil_common import flash_image_pyocd
from m31_iso_public_bis_pair_run import reset


ROOT = Path(__file__).resolve().parents[3]
ROLES = ("peer", "bridge", "receiver")
BOOT = {
    "peer": "CIS peer core revision=",
    "bridge": "CIS bridge core revision=",
    "receiver": "CIS BIS core revision=",
}
RESULT = {
    "peer": re.compile(r"^CIS peer sent frames=100$"),
    "bridge": re.compile(r"^CIS bridge received=100 forwarded=100 errors=0$"),
    "receiver": re.compile(r"^CIS BIS received frames=(99|100) missing=(0|1) errors=0$"),
}
STOPPED = {
    "peer": "CIS peer stopped",
    "bridge": "CIS bridge stopped",
    "receiver": "CIS BIS stopped",
}
ERROR = re.compile(
    r"^(?:CIS peer|CIS bridge|CIS BIS) (?:.*failed:|.*error:|"
    r".*timeout|invalid frame:|peer stopped before enough frames:)"
)


## @brief UID 원문은 메모리에서만 쓰고 세 probe의 해시만 반환합니다.
def resolve_probes(expected: dict[str, str]) -> dict[str, str]:
    connected = {
        hashlib.sha256(probe.unique_id.encode()).hexdigest(): probe.unique_id
        for probe in ConnectHelper.get_all_connected_probes()
    }
    if len(set(expected.values())) != len(ROLES) or any(
        digest not in connected for digest in expected.values()
    ):
        raise RuntimeError("세 CMSIS-DAP V2 probe SHA mapping이 일치하지 않습니다")
    return {role: connected[digest] for role, digest in expected.items()}


## @brief 각 image의 마지막 hardware reset 이후 줄만 셉니다.
def after_final_boot(lines: list[dict], role: str, revision: str) -> list[dict]:
    banner = BOOT[role] + revision
    positions = [index for index, item in enumerate(lines)
                 if item["text"].endswith(banner)]
    return lines[positions[-1] + 1:] if positions else []


## @brief 세 보드의 원본 UART 줄을 종료 확인까지 수집합니다.
def capture(ports: dict[str, str], probe_ids: dict[str, str],
            seconds: float, cycles: int, revision: str) -> dict[str, list[dict]]:
    streams = {role: serial.Serial(ports[role], 115200, timeout=0.1)
               for role in ROLES}
    lines: dict[str, list[dict]] = {role: [] for role in ROLES}
    pending = {role: b"" for role in ROLES}
    reset_failures: list[Exception] = []

    def reset_all() -> None:
        try:
            for role in ("receiver", "peer", "bridge"):
                reset(probe_ids[role])
        except Exception as error:
            reset_failures.append(error)

    reset_thread = Thread(target=reset_all, daemon=True)
    try:
        for stream in streams.values():
            stream.reset_input_buffer()
        reset_thread.start()
        start = time.monotonic()
        deadline: float | None = None
        while deadline is None or time.monotonic() < deadline:
            for role, stream in streams.items():
                pending[role] += stream.read(4096)
                while b"\n" in pending[role]:
                    line, pending[role] = pending[role].split(b"\n", 1)
                    lines[role].append({
                        "at_s": round(time.monotonic() - start, 3),
                        "text": line.rstrip(b"\r").decode("utf-8", errors="replace"),
                    })
            if not reset_thread.is_alive() and deadline is None:
                deadline = time.monotonic() + seconds
            after = {role: after_final_boot(lines[role], role, revision)
                     for role in ROLES}
            if deadline is not None and all(
                sum(bool(RESULT[role].fullmatch(item["text"]))
                    for item in after[role]) >= cycles and
                sum(item["text"] == STOPPED[role]
                    for item in after[role]) >= cycles
                for role in ROLES
            ):
                break
    finally:
        if reset_thread.ident is not None:
            reset_thread.join()
        for stream in streams.values():
            stream.close()
    if reset_failures:
        raise RuntimeError("CMSIS-DAP hardware reset 실패") from reset_failures[0]
    return lines


## @brief clean source·HEX·probe를 결합해 20회 사용자 payload 경로를 판정합니다.
def main() -> int:
    parser = ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--{role}-image", type=Path, required=True)
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-port", required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--allow-dirty-candidate", action="store_true")
    args = parser.parse_args()
    if args.cycles <= 0 or args.seconds <= 0:
        parser.error("cycles와 seconds는 양수여야 합니다")
    revision = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT,
                                       text=True).strip()
    dirty = subprocess.check_output(("git", "status", "--porcelain"), cwd=ROOT,
                                    text=True).strip()
    if dirty and not args.allow_dirty_candidate:
        raise RuntimeError("Core source가 clean 상태가 아닙니다")
    images = {role: getattr(args, f"{role}_image").resolve() for role in ROLES}
    if any(path.suffix.lower() != ".hex" or not path.is_file()
           for path in images.values()):
        raise RuntimeError("세 역할의 Intel HEX image가 필요합니다")
    hashes = {role: getattr(args, f"{role}_probe_sha256") for role in ROLES}
    if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None
           for digest in hashes.values()):
        parser.error("probe SHA-256은 64자리 소문자 hex여야 합니다")
    ports = {role: getattr(args, f"{role}_port") for role in ROLES}
    if len(set(ports.values())) != len(ROLES):
        parser.error("세 역할의 COM port가 같으면 안 됩니다")
    probe_ids = resolve_probes(hashes)
    flash = {}
    for role in ("receiver", "bridge", "peer"):
        flash[role] = flash_image_pyocd(role, probe_ids[role], images[role],
                                        120.0, hardware_reset=True)
    lines = capture(ports, probe_ids, args.seconds, args.cycles, revision)
    after = {role: after_final_boot(lines[role], role, revision) for role in ROLES}
    matches = {
        role: [match for item in after[role]
               if (match := RESULT[role].fullmatch(item["text"])) is not None]
        for role in ROLES
    }
    counts = {role: len(matches[role]) for role in ROLES}
    stopped = {role: sum(item["text"] == STOPPED[role]
                         for item in after[role]) for role in ROLES}
    payload_frames = sum(int(match.group(1)) for match in matches["receiver"])
    missing_frames = sum(int(match.group(2)) for match in matches["receiver"])
    bad = [dict(role=role, **item) for role in ROLES for item in after[role]
           if ERROR.search(item["text"]) or
           (item["text"].startswith("CIS BIS received frames=") and
            RESULT["receiver"].fullmatch(item["text"]) is None)]
    confirmed = {role: any(item["text"].endswith(BOOT[role] + revision)
                           for item in lines[role]) for role in ROLES}
    accepted = (all(counts[role] == args.cycles and stopped[role] == args.cycles
                    for role in ROLES) and
                payload_frames + missing_frames == args.cycles * 100 and
                missing_frames <= args.cycles and not bad and all(confirmed.values()))
    status = ("CANDIDATE_PASS" if dirty else "PASS") if accepted else "FAIL"
    result = {
        "status": status,
        "test": "arduino_public_cis_to_bis_three_board",
        "core_revision": revision,
        "source_clean": not bool(dirty),
        "probe_sha256": hashes,
        "ports": ports,
        "image_sha256": {role: hashlib.sha256(path.read_bytes()).hexdigest()
                         for role, path in images.items()},
        "flash": flash,
        "requested_cycles": args.cycles,
        "completed_cycles": counts,
        "stopped_cycles": stopped,
        "payload_frames": payload_frames,
        "missing_frames": missing_frames,
        "allowed_missing": args.cycles,
        "image_revision_confirmed": confirmed,
        "excluded_pre_boot_lines": {role: len(lines[role]) - len(after[role])
                                    for role in ROLES},
        "failed_lines": bad,
        "lines": lines,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    if args.evidence.exists():
        raise RuntimeError("기존 evidence를 덮어쓰지 않습니다")
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print("ARDUINO_PUBLIC_COMBINED=" + status + ";CYCLES=" +
          "/".join(str(counts[role]) for role in ROLES))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
