#!/usr/bin/env python3
"""! @brief 공개 CTE beacon API의 20회 제어·오류·재시작 실기를 수집합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BOARD_ROOT, flash_image_pyocd, git_revision  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


class BeaconExecutionFailure(RuntimeError):
    """! @brief probe·flash·UART·CTE 제어 계약 오류입니다. """


def protocol_line(port: object, deadline: float) -> str:
    """! @brief bounded CTE 행을 읽고 다른 boot 출력을 건너뜁니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise BeaconExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith("NUCODE_DF|1|"):
            return line
    raise BeaconExecutionFailure("serial protocol timeout")


def read_expected(port: object, prefix: str, deadline: float) -> str:
    """! @brief nonce와 event가 일치하는 한 행만 수락합니다. """
    line = protocol_line(port, deadline)
    if not line.startswith(prefix):
        raise BeaconExecutionFailure(f"unexpected CTE event: {line[:80]}")
    return line


def execute(args: argparse.Namespace) -> dict:
    """! @brief 비파괴 board 확인부터 20회 start/stop까지 한 시도로 실행합니다. """
    image = args.hex.resolve()
    prefix = args.output_prefix.resolve()
    if not image.is_file() or image.suffix.lower() != ".hex":
        raise BeaconExecutionFailure("target Intel HEX missing")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(".transcript.log").exists():
        raise BeaconExecutionFailure("existing evidence must not be overwritten")
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    revisions = {
        "core": git_revision(REPOSITORY),
        "board": git_revision(BOARD_ROOT),
        "ncs": git_revision(args.sdk_root / "nrf"),
        "zephyr": git_revision(args.sdk_root / "zephyr"),
    }
    if revisions["board"] != lock["board"]["revision"] or (
        revisions["ncs"] != lock["ncs"]["revision"] or
        revisions["zephyr"] != lock["zephyr"]["revision"]
    ):
        raise BeaconExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ("git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise BeaconExecutionFailure("exact HIL requires clean source commit")

    serial_module, list_ports = import_pyserial()
    raw_uid, volume, vcom = discover(args.probe_sha256, list_ports)
    image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    transcript: list[str] = []
    nonces: list[str] = []
    board = {
        "probe_sha256": args.probe_sha256,
        "volume": volume,
        "vcom": vcom,
        "image_sha256": image_hash,
    }
    with ProbeLocks([raw_uid]):
        board["registers"] = collect_register_identity(raw_uid, volume)
        board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
            "df_beacon", raw_uid, image, args.flash_timeout, hardware_reset=True
        )
        time.sleep(2.0)
        with serial_module.Serial(vcom, 115200, timeout=0.15) as port:
            port.reset_input_buffer()
            probe_nonce = hashlib.sha256(f"{time.time_ns()}:{image_hash}".encode()).hexdigest()[:32]
            port.write(f"PROBE|nonce={probe_nonce}\n".encode("ascii"))
            port.flush()
            ready = read_expected(
                port, f"NUCODE_DF|1|READY|nonce={probe_nonce}|role=beacon|",
                time.monotonic() + 30.0,
            )
            transcript.append(ready)
            expected_identity = "|".join(f"{key}={value}" for key, value in revisions.items())
            if ready != f"NUCODE_DF|1|READY|nonce={probe_nonce}|role=beacon|{expected_identity}":
                raise BeaconExecutionFailure("firmware/source revision mismatch")
            for cycle in range(20):
                nonce = hashlib.sha256(
                    f"{time.time_ns()}:{cycle}:{image_hash}".encode()
                ).hexdigest()[:32]
                nonces.append(nonce)
                for command, event in (
                    ("INVALID", "REJECTED"), ("START", "STARTED"), ("STOP", "STOPPED")
                ):
                    port.write(f"{command}|nonce={nonce}\n".encode("ascii"))
                    port.flush()
                    line = read_expected(
                        port, f"NUCODE_DF|1|{event}|nonce={nonce}|",
                        time.monotonic() + 30.0,
                    )
                    if command == "INVALID" and line != (
                        f"NUCODE_DF|1|REJECTED|nonce={nonce}|reason=cte_length"
                    ):
                        raise BeaconExecutionFailure("invalid CTE length accepted")
                    if command != "INVALID" and line != (
                        f"NUCODE_DF|1|{event}|nonce={nonce}|count={cycle + 1}"
                    ):
                        raise BeaconExecutionFailure("start/stop denominator mismatch")
                    transcript.append(line)
                    if command == "START":
                        time.sleep(args.advertising_seconds)

    raw = ("\n".join(transcript) + "\n").encode("ascii")
    if re.search(rb"\b(?:uid|probe_id|serial_number)=", raw, flags=re.IGNORECASE):
        raise BeaconExecutionFailure("raw probe identity in transcript")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    evidence = {
        "test_id": "M31-DF-01:connectionless_cte_tx:controller_acceptance",
        "status": "PASS_CONTROL_CANDIDATE" if dirty else "PASS_CONTROL",
        "source_clean": not bool(dirty),
        "identity": revisions,
        "probe_nonce": probe_nonce,
        "nonces": nonces,
        "board": board,
        "measured": {"cycles": 20, "starts": 20, "stops": 20, "invalid_rejected": 20},
        "transcript_sha256": hashlib.sha256(raw).hexdigest(),
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "controller_acceptance_only_no_over_air_iq_proof",
    }
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return evidence


def main() -> int:
    """! @brief 오류를 redaction한 뒤 결과 경계만 출력합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--hex", type=Path, required=True)
    parser.add_argument("--probe-sha256", required=True)
    parser.add_argument("--sdk-root", type=Path, default=Path("C:/Users/eidos/ncs/v3.4.0"))
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--flash-timeout", type=float, default=120.0)
    parser.add_argument("--advertising-seconds", type=float, default=1.0)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = str(error) if isinstance(error, BeaconExecutionFailure) else "probe/flash execution failure"
        print(f"M31_DF_BEACON_FAIL={type(error).__name__}:{message[:180]}", file=sys.stderr)
        return 1
    print(
        f"M31_DF_BEACON_{result['status']}=cycles={result['measured']['cycles']};"
        f"invalid_rejected={result['measured']['invalid_rejected']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
