#!/usr/bin/env python3
"""! @file m31_iso_combined_run.py
@brief 세 NU54DK의 CIS peer→combined central/BIS source→BIS receiver 원본을 수집합니다.
"""

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
CORE = HIL.parents[2]
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BOARD_ROOT, flash_image_pyocd, git_revision  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m31_iso_combined import validate_combined_envelope  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("peer", "combined", "receiver")
PROTOCOL = {"peer": "M31ISO|1|", "combined": "M31COMB|1|", "receiver": "M31BIS|1|"}
CAPTURE_HCI_LOG = False


class CombinedFailure(RuntimeError):
    """! @brief 세 보드 flash·VCOM·기능 protocol의 유한 오류입니다. """


def write_command(port: object, payload: str) -> None:
    """! @brief 정확한 한 줄 command만 해당 VCOM에 전송합니다. """
    port.write((payload + "\n").encode("ascii"))
    port.flush()


def protocol_line(port: object, role: str, transcript: list[str], deadline: float) -> str:
    """! @brief 512-byte ASCII protocol 행을 순서대로 기록하고 target FAIL을 거부합니다. """
    while time.monotonic() < deadline:
        raw = port.readline()
        if len(raw) > 512:
            raise CombinedFailure(f"{role} serial line overlong")
        line = raw.decode("ascii", errors="replace").strip()
        if not line.startswith(PROTOCOL[role]):
            if CAPTURE_HCI_LOG and role == "peer":
                matched = re.search(r"opcode\s+0x206e\s+status\s+0x([0-9a-fA-F]{2})", line)
                if matched:
                    transcript.append(f"peer: HCI_SETUP_ISO_PATH_STATUS|status={matched.group(1).lower()}")
            continue
        transcript.append(f"{role}: {line}")
        if "|FAIL|" in line:
            raise CombinedFailure(f"{role} target FAIL: {line.split('|stage=')[-1][:80]}")
        return line
    raise CombinedFailure(f"{role} serial line timeout")


def wait_events(port: object, role: str, transcript: list[str], events: set[str],
                nonce: str | None, seconds: float) -> dict[str, str]:
    """! @brief 같은 nonce의 여러 상태를 임의 callback 순서에서도 모두 수집합니다. """
    deadline = time.monotonic() + seconds
    observed: dict[str, str] = {}
    while time.monotonic() < deadline and set(observed) != events:
        line = protocol_line(port, role, transcript, deadline)
        for event in events - set(observed):
            prefix = PROTOCOL[role] + event
            if nonce is not None:
                prefix += f"|nonce={nonce}"
            if line.startswith(prefix):
                observed[event] = line
                break
    if set(observed) != events:
        raise CombinedFailure(f"{role} events {sorted(events - set(observed))} timeout")
    return observed


def save_attempt(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief 기존 attempt를 덮지 않고 probe UID가 없는 raw와 SHA를 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise CombinedFailure("raw UID in transcript")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def execute(args: argparse.Namespace) -> dict:
    """! @brief 독립 세 probe와 clean build의 20회×100 CIS→BIS session을 실행합니다. """
    prefix = args.output_prefix.resolve()
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(".transcript.log").exists():
        raise CombinedFailure("기존 attempt evidence를 덮지 않습니다")
    if not (1 <= args.cycles <= 20) or (args.cycles != 20 and not args.development):
        raise CombinedFailure("exact combined HIL은 20-cycle입니다")
    if args.capture_hci_log and not args.development:
        raise CombinedFailure("HCI debug log는 개발 시도에만 기록합니다")
    global CAPTURE_HCI_LOG
    CAPTURE_HCI_LOG = args.capture_hci_log
    sdk = args.sdk_root.resolve()
    lock = json.loads((CORE / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    identity = ExpectedIdentity(git_revision(CORE), git_revision(BOARD_ROOT),
                                git_revision(sdk / "nrf"), git_revision(sdk / "zephyr"))
    if identity.board != lock["board"]["revision"] or identity.ncs != lock["ncs"]["revision"] or (
        identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise CombinedFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(CORE), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise CombinedFailure("exact 3-board HIL에는 clean source commit이 필요합니다")
    serial_module, list_ports = import_pyserial()
    boards = {}
    for role in ROLES:
        probe = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise CombinedFailure(f"{role} image missing")
        uid, volume, vcom = discover(probe, list_ports)
        boards[role] = {
            "uid": uid, "volume": volume, "vcom": vcom, "image": image,
            "probe_sha256": probe, "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if len({board["uid"] for board in boards.values()}) != 3:
        raise CombinedFailure("3 role을 서로 다른 probe에 매핑해야 합니다")
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
                    role, board["uid"], board["image"], 120.0, hardware_reset=True
                )
            time.sleep(2.0)
            ports = {role: serial_module.Serial(board["vcom"], 115200, timeout=0.15)
                     for role, board in boards.items()}
            for role in ROLES:
                ports[role].reset_input_buffer()
                write_command(ports[role], PROTOCOL[role] + "PROBE")
            for role in ROLES:
                ready = wait_events(ports[role], role, transcript, {"READY"}, None, 30.0)["READY"]
                expected_role = {"peer": "peripheral", "combined": "combined",
                                 "receiver": "receiver"}[role]
                if ready != PROTOCOL[role] + "READY|role=" + expected_role:
                    raise CombinedFailure(f"{role} READY mismatch")
            for cycle in range(args.cycles):
                nonce = hashlib.sha256(
                    f"{time.time_ns()}:{cycle}:{boards['combined']['image_sha256']}".encode()
                ).hexdigest()[:32]
                nonces.append(nonce)
                write_command(ports["peer"], f"M31ISO|1|START|nonce={nonce}|count=100")
                write_command(ports["combined"], f"M31COMB|1|START|nonce={nonce}|count=100")
                wait_events(ports["combined"], "combined", transcript,
                            {"CIS_CONNECTED", "BIG_SYNCED"}, nonce, 60.0)
                wait_events(ports["peer"], "peer", transcript, {"ISO_CONNECTED"}, nonce, 60.0)
                write_command(ports["receiver"], f"M31BIS|1|START|nonce={nonce}|count=100")
                wait_events(ports["receiver"], "receiver", transcript, {"BIG_SYNCED"}, nonce, 60.0)
                write_command(ports["peer"], f"M31ISO|1|SEND|nonce={nonce}")
                wait_events(ports["peer"], "peer", transcript, {"TX_END"}, nonce, 60.0)
                wait_events(ports["combined"], "combined", transcript,
                            {"CIS_RX_END", "BIS_TX_END"}, nonce, 60.0)
                wait_events(ports["receiver"], "receiver", transcript, {"RX_END"}, nonce, 60.0)
                for role in ("receiver", "peer", "combined"):
                    write_command(ports[role], PROTOCOL[role] + f"STOP|nonce={nonce}")
                    wait_events(ports[role], role, transcript, {"STOPPED"}, nonce, 35.0)
            if args.cycles == 20:
                if dirty:
                    status = "PASS_CANDIDATE"
                else:
                    public_boards = {
                        role: {key: value for key, value in board.items()
                               if key not in {"uid", "image"}}
                        for role, board in boards.items()
                    }
                    raw = ("\n".join(transcript) + "\n").encode("ascii")
                    images = {role: board["image_sha256"] for role, board in boards.items()}
                    measured = validate_combined_envelope({
                        "source_clean": True,
                        "test_id": "M31-ISO-01:bis_cis_combined",
                        "identity": vars(identity),
                        "cycles": args.cycles,
                        "boards": public_boards,
                        "nonces": nonces,
                        "transcript": raw,
                    }, images, identity)
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
        "test_id": "M31-ISO-01:bis_cis_combined",
        "scope": "three_board_cis_receive_bis_forward_twenty_cycles",
        "status": status, "source_clean": not bool(dirty), "identity": vars(identity),
        "boards": public_boards, "nonces": nonces, "cycles": args.cycles,
        "reason": reason, "measurement": vars(measured) if measured is not None else None,
    }
    save_attempt(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief 이미지·probe는 익명 SHA-256으로만 명령에서 선택합니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--probe-{role}-sha256", required=True)
        parser.add_argument(f"--hex-{role}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--capture-hci-log", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(f"M31_ISO_COMBINED_FAIL: {type(error).__name__}: {message[:400]}", file=sys.stderr)
        return 1
    print(f"M31_ISO_COMBINED_STATUS={result['status']};SOURCE_CLEAN={str(result['source_clean']).lower()}")
    return 0 if result["status"] == "PASS" or args.development and result["status"] in {
        "DEV_PROBE", "PASS_CANDIDATE"
    } else 1


if __name__ == "__main__":
    sys.exit(main())
