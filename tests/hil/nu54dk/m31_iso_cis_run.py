#!/usr/bin/env python3
"""! @brief 두 SHA-256 NU54DK 역할의 20-cycle CIS 실기 증거를 안전하게 수집합니다. """

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
from m31_iso_cis import parse_cis_transcript, validate_cis_envelope  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("central", "peripheral")


class IsoExecutionFailure(RuntimeError):
    """! @brief 연결·flash·serial 단계의 유한 실패를 나타냅니다. """


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink VCOM 잡음 속에서 512-byte protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise IsoExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith("M31ISO|1|"):
            return line
    raise IsoExecutionFailure("serial line timeout")


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief 동일 attempt를 덮어쓰지 않고 raw 출력과 SHA-256을 함께 남깁니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise IsoExecutionFailure("raw probe UID in transcript")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def execute(args: argparse.Namespace) -> dict:
    """! @brief 두 image·AP identity·무선 데이터·STOP의 exact session을 검사합니다. """
    prefix = args.output_prefix.resolve()
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(".transcript.log").exists():
        raise IsoExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(git_revision(REPOSITORY), git_revision(BOARD_ROOT),
                                git_revision(sdk / "nrf"), git_revision(sdk / "zephyr"))
    if identity.board != lock["board"]["revision"] or identity.ncs != lock["ncs"]["revision"] or (
        identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise IsoExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise IsoExecutionFailure("exact HIL에는 clean source commit이 필요합니다")
    serial_module, list_ports = import_pyserial()
    boards = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise IsoExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        boards[role] = {
            "uid": uid, "image": image, "probe_sha256": digest, "volume": volume,
            "vcom": vcom, "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["central"]["uid"] == boards["peripheral"]["uid"]:
        raise IsoExecutionFailure("양 역할이 동일 probe에 매핑됨")
    transcript: list[str] = []
    nonces: list[str] = []
    reason = None
    status = "FAIL"
    measured = None
    with ProbeLocks([board["uid"] for board in boards.values()]):
        for role in ROLES:
            board = boards[role]
            board["registers"] = collect_register_identity(board["uid"], board["volume"])
            board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
                role, board["uid"], board["image"], 120.0, hardware_reset=True
            )
        time.sleep(2.0)
        ports = {role: serial_module.Serial(board["vcom"], 115200, timeout=0.15)
                 for role, board in boards.items()}
        try:
            for port in ports.values():
                port.reset_input_buffer()
                port.write(b"M31ISO|1|PROBE\n")
                port.flush()
            for role in ROLES:
                line = _line(ports[role], time.monotonic() + 30.0)
                transcript.append(f"{role}: {line}")
                if line != f"M31ISO|1|READY|role={role}":
                    raise IsoExecutionFailure(f"{role} READY mismatch")
            for cycle in range(20):
                nonce = hashlib.sha256(f"{time.time_ns()}:{cycle}:{boards['central']['image_sha256']}".encode()).hexdigest()[:32]
                nonces.append(nonce)
                for port in ports.values():
                    port.write(f"M31ISO|1|START|nonce={nonce}|count=100\n".encode("ascii"))
                    port.flush()
                ends = set()
                deadline = time.monotonic() + 180.0
                while time.monotonic() < deadline and ends != set(ROLES):
                    for role in ROLES:
                        payload = ports[role].readline()
                        if not payload:
                            continue
                        if len(payload) > 512:
                            raise IsoExecutionFailure("serial line overlong")
                        line = payload.decode("ascii", errors="replace").strip()
                        if not line.startswith("M31ISO|1|"):
                            continue
                        transcript.append(f"{role}: {line}")
                        if "|FAIL|" in line or "|RX_BAD_LENGTH|" in line:
                            raise IsoExecutionFailure(f"{role} target FAIL")
                        if line.startswith(f"M31ISO|1|TX_END|nonce={nonce}") and role == "central":
                            ends.add(role)
                        if line.startswith(f"M31ISO|1|RX_END|nonce={nonce}") and role == "peripheral":
                            ends.add(role)
                if ends != set(ROLES):
                    raise IsoExecutionFailure(f"CIS cycle={cycle} end timeout")
                for port in ports.values():
                    port.write(f"M31ISO|1|STOP|nonce={nonce}\n".encode("ascii"))
                    port.flush()
                for role in ROLES:
                    deadline = time.monotonic() + 35.0
                    while True:
                        line = _line(ports[role], deadline)
                        transcript.append(f"{role}: {line}")
                        if "|FAIL|" in line:
                            raise IsoExecutionFailure(f"{role} target STOP FAIL")
                        if line.startswith(f"M31ISO|1|STOPPED|nonce={nonce}"):
                            break
            raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
            if dirty:
                measured = parse_cis_transcript(raw, nonces, identity)
                status = "PASS_CANDIDATE"
            else:
                measured = validate_cis_envelope({
                    "source_clean": True, "test_id": "M31-ISO-01:cis", "transcript": raw,
                    "nonces": nonces,
                    "boards": {role: {key: value for key, value in board.items()
                                      if key not in {"uid", "image"}} for role, board in boards.items()},
                }, {role: board["image_sha256"] for role, board in boards.items()}, identity)
                status = "PASS"
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
        "test_id": "M31-ISO-01:cis", "status": status, "scope": "two_board_cis_twenty_cycles",
        "source_clean": not bool(dirty), "identity": vars(identity), "boards": public_boards,
        "nonces": nonces, "cycles": 20, "reason": reason,
        "measurement": vars(measured) if measured is not None else None,
    }
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 대신 probe SHA-256과 각 역할 HEX만 명령으로 받습니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--probe-{role}-sha256", required=True)
        parser.add_argument(f"--hex-{role}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(f"M31_ISO_CIS_FAIL: {type(error).__name__}: {message[:400]}", file=sys.stderr)
        return 1
    print(f"M31_ISO_CIS_STATUS={result['status']};SOURCE_CLEAN={str(result['source_clean']).lower()}")
    return 0 if result["status"] == "PASS" or args.development and result["status"] == "PASS_CANDIDATE" else 1


if __name__ == "__main__":
    sys.exit(main())
