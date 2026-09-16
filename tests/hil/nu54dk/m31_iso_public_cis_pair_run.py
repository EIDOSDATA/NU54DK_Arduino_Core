#!/usr/bin/env python3
"""! @brief 공개 RawCis Arduino 두 예제의 SDU·해제 반복을 실제 보드에서 검증합니다. """

from __future__ import annotations

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import time

from pyocd.core.helpers import ConnectHelper
import serial

from ble_pair_hil_common import flash_image_pyocd


ROOT = Path(__file__).resolve().parents[3]
SENT = re.compile(r"^CIS sent frames=100$")
RECEIVED = re.compile(r"^CIS received frames=100 errors=0$")
RECEIVE_END = re.compile(r"^CIS received frames=")
ERROR = re.compile(r"^CIS (?:start|send) failed:|^CIS error:")


## @brief probe UID는 메모리에서만 사용하고 결과에는 SHA-256만 기록합니다.
def resolve_probes(expected: dict[str, str]) -> dict[str, str]:
    connected = {
        hashlib.sha256(probe.unique_id.encode()).hexdigest(): probe.unique_id
        for probe in ConnectHelper.get_all_connected_probes()
    }
    if len(set(expected.values())) != 2 or any(
        digest not in connected for digest in expected.values()
    ):
        raise RuntimeError("두 역할의 CMSIS-DAP V2 probe SHA mapping이 일치하지 않습니다")
    return {role: connected[digest] for role, digest in expected.items()}


## @brief sector flash 이후 두 보드에 비파괴 hardware reset을 보냅니다.
def reset(uid: str) -> None:
    result = subprocess.run(
        (
            sys.executable, "-I", "-m", "pyocd", "reset", "--uid", uid,
            "--target", "nrf54l", "--frequency", "500000", "--connect",
            "under-reset", "-O", "cmsis_dap.limit_packets=true", "-O",
            "cmsis_dap.prefer_v1=false", "-O", "auto_unlock=false",
            "--method", "hw",
        ),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("CMSIS-DAP hardware reset 실패")


## @brief 두 COM의 완결된 줄을 원본 순서와 시간과 함께 저장합니다.
def capture(ports: dict[str, str], probe_ids: dict[str, str],
            seconds: float, cycles: int) -> dict[str, list[dict]]:
    streams = {role: serial.Serial(port, 115200, timeout=0.1)
               for role, port in ports.items()}
    lines: dict[str, list[dict]] = {role: [] for role in ports}
    pending = {role: b"" for role in ports}
    try:
        for stream in streams.values():
            stream.reset_input_buffer()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(reset, (probe_ids[role]
                                  for role in ("peripheral", "central"))))
        start = time.monotonic()
        deadline = start + seconds
        while time.monotonic() < deadline:
            for role, stream in streams.items():
                pending[role] += stream.read(4096)
                while b"\n" in pending[role]:
                    line, pending[role] = pending[role].split(b"\n", 1)
                    lines[role].append({
                        "at_s": round(time.monotonic() - start, 3),
                        "text": line.rstrip(b"\r").decode("utf-8", errors="replace"),
                    })
            if (sum(bool(SENT.fullmatch(item["text"])) for item in lines["central"]) >= cycles and
                sum(bool(RECEIVED.fullmatch(item["text"])) for item in lines["peripheral"]) >= cycles):
                break
    finally:
        for stream in streams.values():
            stream.close()
    return lines


## @brief exact source·image·probe 결합을 확인하고 20회 사용자 payload 경로를 실행합니다.
def main() -> int:
    parser = ArgumentParser()
    for role in ("central", "peripheral"):
        parser.add_argument(f"--{role}-image", type=Path, required=True)
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-port", required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if args.cycles <= 0 or args.seconds <= 0:
        parser.error("cycles와 seconds는 양수여야 합니다")
    revision = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT,
                                       text=True).strip()
    dirty = subprocess.check_output(("git", "status", "--porcelain"), cwd=ROOT,
                                    text=True).strip()
    if dirty:
        raise RuntimeError("Core source가 clean 상태가 아닙니다")
    images = {role: getattr(args, f"{role}_image").resolve()
              for role in ("central", "peripheral")}
    if any(path.suffix.lower() != ".hex" or not path.is_file()
           for path in images.values()):
        raise RuntimeError("두 역할의 Intel HEX image가 필요합니다")
    probe_hashes = {role: getattr(args, f"{role}_probe_sha256")
                    for role in images}
    if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None
           for digest in probe_hashes.values()):
        parser.error("probe SHA-256은 64자리 소문자 hex여야 합니다")
    probe_ids = resolve_probes(probe_hashes)
    ports = {role: getattr(args, f"{role}_port") for role in images}
    if len(set(ports.values())) != 2:
        parser.error("두 역할의 COM port가 같으면 안 됩니다")
    flash = {}
    for role in ("peripheral", "central"):
        flash[role] = flash_image_pyocd(role, probe_ids[role], images[role],
                                        120.0, hardware_reset=True)
    lines = capture(ports, probe_ids, args.seconds, args.cycles)
    sent = sum(bool(SENT.fullmatch(item["text"])) for item in lines["central"])
    received = sum(bool(RECEIVED.fullmatch(item["text"])) for item in lines["peripheral"])
    bad = [item for role in lines for item in lines[role]
           if ERROR.search(item["text"]) or
           (RECEIVE_END.search(item["text"]) and not RECEIVED.fullmatch(item["text"]))]
    image_revision_confirmed = {
        role: any(item["text"] == f"CIS core revision={revision}"
                  for item in lines[role])
        for role in lines
    }
    status = "PASS" if (sent == args.cycles and received == args.cycles and
                        not bad and all(image_revision_confirmed.values())) else "FAIL"
    result = {
        "status": status,
        "test": "arduino_public_raw_cis_pair",
        "core_revision": revision,
        "source_clean": True,
        "probe_sha256": probe_hashes,
        "ports": ports,
        "image_sha256": {role: hashlib.sha256(path.read_bytes()).hexdigest()
                         for role, path in images.items()},
        "flash": flash,
        "requested_cycles": args.cycles,
        "completed_cycles": {"central": sent, "peripheral": received},
        "image_revision_confirmed": image_revision_confirmed,
        "failed_lines": bad,
        "lines": lines,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    if args.evidence.exists():
        raise RuntimeError("기존 evidence를 덮어쓰지 않습니다")
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(f"ARDUINO_PUBLIC_CIS_PAIR={status};CYCLES={sent}/{received}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
