#!/usr/bin/env python3
"""! @brief 두 익명 NU54DK의 BIS BIG 동기·SDU·재시작 증거를 수집합니다. """

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
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m31_iso_bis import parse_bis_transcript, validate_bis_envelope  # noqa: E402
from m31_iso_time import parse_time_transcript, validate_time_envelope  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("source", "receiver")


class BisExecutionFailure(RuntimeError):
    """! @brief flash·VCOM·BIS protocol의 유한 실패입니다. """


def protocol_line(port: object, role: str, transcript: list[str], deadline: float) -> str:
    """! @brief DAPLink VCOM 출력에서 512-byte BIS protocol 줄만 수락합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise BisExecutionFailure(f"{role} serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if not line.startswith("M31BIS|1|"):
            continue
        transcript.append(f"{role}: {line}")
        if "|FAIL|" in line:
            raise BisExecutionFailure(f"{role} target FAIL: {line.split('|stage=')[-1][:80]}")
        return line
    raise BisExecutionFailure(f"{role} serial line timeout")


def wait_event(port: object, role: str, transcript: list[str], event: str,
               nonce: str | None, seconds: float) -> str:
    """! @brief 정확한 role·nonce의 다음 상태를 유한 시간 안에서 확인합니다. """
    prefix = f"M31BIS|1|{event}"
    if nonce is not None:
        prefix += f"|nonce={nonce}"
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        line = protocol_line(port, role, transcript, deadline)
        if line.startswith(prefix):
            return line
    raise BisExecutionFailure(f"{role} {event} timeout")


def write_command(port: object, command: str) -> None:
    """! @brief 동일 세션 nonce의 줄 하나를 VCOM으로 전송합니다. """
    port.write((command + "\n").encode("ascii"))
    port.flush()


def save_attempt(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief attempt를 덮지 않고 raw protocol과 SHA-256을 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise BisExecutionFailure("raw probe UID in transcript")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def execute(args: argparse.Namespace) -> dict:
    """! @brief source 먼저 광고하고 receiver 동기 뒤 SEND로 SDU를 시작합니다. """
    prefix = args.output_prefix.resolve()
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(".transcript.log").exists():
        raise BisExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    if args.cycles < 1 or args.cycles > 20:
        raise BisExecutionFailure("development cycle 분모는 1..20입니다")
    if args.cycles != 20 and not args.development:
        raise BisExecutionFailure("exact HIL은 20-cycle만 허용합니다")
    sdk = args.sdk_root.resolve()
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    identity = ExpectedIdentity(git_revision(REPOSITORY), git_revision(BOARD_ROOT),
                                git_revision(sdk / "nrf"), git_revision(sdk / "zephyr"))
    if identity.board != lock["board"]["revision"] or identity.ncs != lock["ncs"]["revision"] or (
        identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise BisExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise BisExecutionFailure("exact HIL에는 clean source commit이 필요합니다")
    serial_module, list_ports = import_pyserial()
    boards = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise BisExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        boards[role] = {
            "uid": uid, "image": image, "probe_sha256": digest, "volume": volume,
            "vcom": vcom, "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["source"]["uid"] == boards["receiver"]["uid"]:
        raise BisExecutionFailure("양 역할이 동일 probe에 매핑됨")
    transcript: list[str] = []
    nonces: list[str] = []
    reason = None
    status = "FAIL"
    measured = None
    with ProbeLocks([board["uid"] for board in boards.values()]):
        ports = {}
        try:
            for role in ROLES:
                board = boards[role]
                board["registers"] = collect_register_identity(board["uid"], board["volume"])
                board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
                    role, board["uid"], board["image"], 120.0
                )
            time.sleep(2.0)
            ports = {role: serial_module.Serial(board["vcom"], 115200, timeout=0.15)
                     for role, board in boards.items()}
            for role in ROLES:
                ports[role].reset_input_buffer()
                write_command(ports[role], "M31BIS|1|PROBE")
            for role in ROLES:
                line = wait_event(ports[role], role, transcript, "READY", None, 30.0)
                if line != f"M31BIS|1|READY|role={role}":
                    raise BisExecutionFailure(f"{role} READY mismatch")
            for cycle in range(args.cycles):
                nonce = hashlib.sha256(
                    f"{time.time_ns()}:{cycle}:{boards['source']['image_sha256']}".encode()
                ).hexdigest()[:32]
                nonces.append(nonce)
                command = f"M31BIS|1|START|nonce={nonce}|count=100"
                write_command(ports["source"], command)
                wait_event(ports["source"], "source", transcript, "BIG_SYNCED", nonce, 60.0)
                write_command(ports["receiver"], command)
                wait_event(ports["receiver"], "receiver", transcript, "BIG_SYNCED", nonce, 60.0)
                write_command(ports["source"], f"M31BIS|1|SEND|nonce={nonce}")
                wait_event(ports["source"], "source", transcript, "TX_END", nonce, 60.0)
                wait_event(ports["receiver"], "receiver", transcript, "RX_END", nonce, 60.0)
                for role in ROLES:
                    write_command(ports[role], f"M31BIS|1|STOP|nonce={nonce}")
                for role in ROLES:
                    wait_event(ports[role], role, transcript, "STOPPED", nonce, 35.0)
            if args.cycles == 20:
                raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
                test_id = "M31-ISO-01:time_sync" if args.time_sync else "M31-ISO-01:bis"
                public_boards = {role: {key: value for key, value in board.items()
                                       if key not in {"uid", "image"}} for role, board in boards.items()}
                if dirty:
                    measured = (parse_time_transcript(raw, nonces, identity) if args.time_sync else
                                parse_bis_transcript(raw, nonces, identity))
                    status = "PASS_CANDIDATE"
                else:
                    envelope = {
                        "source_clean": True, "test_id": test_id, "transcript": raw,
                        "nonces": nonces, "boards": public_boards,
                    }
                    images = {role: board["image_sha256"] for role, board in boards.items()}
                    measured = (validate_time_envelope(envelope, images, identity) if args.time_sync else
                                validate_bis_envelope(envelope, images, identity))
                    status = "PASS"
            else:
                status = "DEV_PROBE"
        except Exception as error:
            reason = type(error).__name__ + ": " + str(error)
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)
        finally:
            for port in ports.values():
                port.close()
    public_boards = {role: {key: value for key, value in board.items()
                           if key not in {"uid", "image"}} for role, board in boards.items()}
    evidence = {
        "test_id": "M31-ISO-01:time_sync" if args.time_sync else "M31-ISO-01:bis",
        "scope": "two_board_iso_timestamp_twenty_cycles" if args.time_sync else
                 "two_board_bis_twenty_cycles",
        "status": status, "source_clean": not bool(dirty), "identity": vars(identity),
        "boards": public_boards, "nonces": nonces, "cycles": args.cycles,
        "reason": reason, "measurement": vars(measured) if measured is not None else None,
    }
    save_attempt(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 대신 probe SHA-256과 역할 image를 명령으로 받습니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--probe-{role}-sha256", required=True)
        parser.add_argument(f"--hex-{role}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--time-sync", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(f"M31_ISO_BIS_FAIL: {type(error).__name__}: {message[:400]}", file=sys.stderr)
        return 1
    print(f"M31_ISO_BIS_STATUS={result['status']};SOURCE_CLEAN={str(result['source_clean']).lower()}")
    return 0 if result["status"] == "PASS" or args.development and result["status"] in {
        "PASS_CANDIDATE", "DEV_PROBE"
    } else 1


if __name__ == "__main__":
    sys.exit(main())
