#!/usr/bin/env python3
"""! @brief 익명 probe 한 개에서 LC3 20-cycle 실제 실행 증거를 수집합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BOARD_ROOT, flash_image_pyocd, git_revision  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_audio_lc3 import parse_lc3_transcript, validate_lc3_envelope  # noqa: E402
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


class AudioExecutionFailure(RuntimeError):
    """! @brief mapping·flash·UART·codec 실행 실패를 나타냅니다. """


def protocol_line(port: object, deadline: float) -> str:
    """! @brief 잡음을 건너뛰고 bounded M31 Audio 행 하나를 읽습니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise AudioExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith("NUCODE_AUDIO|1|"):
            return line
    raise AudioExecutionFailure("serial protocol timeout")


def execute(args: argparse.Namespace) -> dict:
    """! @brief DP/AP 확인부터 sector flash와 20회 codec oracle까지 한 attempt로 묶습니다. """
    image = args.hex.resolve()
    prefix = args.output_prefix.resolve()
    if not image.is_file() or image.suffix.lower() != ".hex":
        raise AudioExecutionFailure("유효한 target Intel HEX가 없습니다")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(".transcript.log").exists():
        raise AudioExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(git_revision(REPOSITORY), git_revision(BOARD_ROOT),
                                git_revision(sdk / "nrf"), git_revision(sdk / "zephyr"))
    if identity.board != lock["board"]["revision"] or identity.ncs != lock["ncs"]["revision"] or (
        identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise AudioExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ("git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise AudioExecutionFailure("exact HIL에는 clean source commit이 필요합니다")

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
            "audio_lc3", raw_uid, image, args.flash_timeout, hardware_reset=True
        )
        time.sleep(2.0)
        with serial_module.Serial(vcom, 115200, timeout=0.15) as port:
            port.reset_input_buffer()
            port.write(b"NUCODE_AUDIO|1|PROBE\n")
            port.flush()
            ready = protocol_line(port, time.monotonic() + 30.0)
            transcript.append(ready)
            if ready != "NUCODE_AUDIO|1|READY|scenario=lc3-loopback|role=codec":
                raise AudioExecutionFailure("LC3 READY mismatch")
            for cycle in range(20):
                nonce = hashlib.sha256(
                    f"{time.time_ns()}:{cycle}:{image_hash}".encode("ascii")
                ).hexdigest()[:32]
                nonces.append(nonce)
                commands = (
                    (f"NUCODE_AUDIO|1|CHECK_INVALID|nonce={nonce}|scenario=lc3-loopback\n",
                     f"NUCODE_AUDIO|1|NEG_END|nonce={nonce}|"),
                    (f"NUCODE_AUDIO|1|START|nonce={nonce}|scenario=lc3-loopback|iterations=100\n",
                     f"NUCODE_AUDIO|1|BEGIN|nonce={nonce}|"),
                )
                for command, expected in commands:
                    port.write(command.encode("ascii"))
                    port.flush()
                    line = protocol_line(port, time.monotonic() + args.timeout_seconds)
                    transcript.append(line)
                    if "|FAIL|" in line or not line.startswith(expected):
                        raise AudioExecutionFailure(f"cycle={cycle} protocol failure")
                    if "|BEGIN|" in line:
                        for event in ("IDENTITY", "END"):
                            line = protocol_line(port, time.monotonic() + args.timeout_seconds)
                            transcript.append(line)
                            if "|FAIL|" in line or not line.startswith(
                                f"NUCODE_AUDIO|1|{event}|nonce={nonce}|"
                            ):
                                raise AudioExecutionFailure(f"cycle={cycle} {event} failure")
                port.write(f"NUCODE_AUDIO|1|STOP|nonce={nonce}\n".encode("ascii"))
                port.flush()
                stopped = protocol_line(port, time.monotonic() + 30.0)
                transcript.append(stopped)
                if stopped != f"NUCODE_AUDIO|1|STOPPED|nonce={nonce}|scenario=lc3-loopback":
                    raise AudioExecutionFailure(f"cycle={cycle} STOP failure")

    raw = ("\n".join(transcript) + "\n").encode("ascii")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    envelope = {
        "test_id": "M31-AUDIO-01:W03-01",
        "status": "PASS_CANDIDATE" if dirty else "PASS",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "nonces": nonces,
        "board": board,
        "transcript": raw,
    }
    result = parse_lc3_transcript(raw, nonces, identity) if dirty else validate_lc3_envelope(
        envelope, image_hash, identity
    )
    evidence = {key: value for key, value in envelope.items() if key != "transcript"}
    evidence["measured"] = vars(result)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return evidence


def main() -> int:
    """! @brief CLI 인자를 제한하고 evidence 경로만 출력합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--hex", type=Path, required=True)
    parser.add_argument("--probe-sha256", required=True)
    parser.add_argument("--sdk-root", type=Path, default=Path("C:/Users/eidos/ncs/v3.4.0"))
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--flash-timeout", type=float, default=120.0)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        evidence = execute(args)
    except Exception as error:
        print(f"M31_AUDIO_LC3_FAIL={type(error).__name__}:{error}", file=sys.stderr)
        return 1
    print(
        f"M31_AUDIO_LC3_{evidence['status']}=cycles={evidence['measured']['cycles']};"
        f"encoded={evidence['measured']['encoded_frames']};"
        f"decoded={evidence['measured']['decoded_frames']};"
        f"rejected={evidence['measured']['rejected_invalid']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
