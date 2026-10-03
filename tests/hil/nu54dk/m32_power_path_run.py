#!/usr/bin/env python3
"""! @brief 두 SHA-256 NU54DK 역할의 Power/Path Loss HIL 증거를 수집합니다. """

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
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("central", "peripheral")
PROTOCOL = "M32PWR|1"
POWER_TARGET = 20
PATH_TARGET = 60


class PowerPathExecutionFailure(RuntimeError):
    """! @brief mapping·flash·UART·분모 검증의 제한된 실패입니다. """


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 M32 Power protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise PowerPathExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise PowerPathExecutionFailure("serial line timeout")


def _fields(line: str) -> dict[str, str]:
    """! @brief key=value field 중 중복이 없는 record만 허용합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise PowerPathExecutionFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief attempt 원본과 SHA-256을 덮어쓰기 없이 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise PowerPathExecutionFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise PowerPathExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def execute(args: argparse.Namespace) -> dict:
    """! @brief 두 image를 sector flash하고 20/40/60 분모와 STOP을 검증합니다. """
    prefix = args.output_prefix.resolve()
    lock = json.loads(
        (REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
    )
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(
        git_revision(REPOSITORY),
        git_revision(BOARD_ROOT),
        git_revision(sdk / "nrf"),
        git_revision(sdk / "zephyr"),
    )
    if (
        identity.board != lock["board"]["revision"]
        or identity.ncs != lock["ncs"]["revision"]
        or identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise PowerPathExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise PowerPathExecutionFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise PowerPathExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        boards[role] = {
            "uid": uid,
            "image": image,
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["central"]["uid"] == boards["peripheral"]["uid"]:
        raise PowerPathExecutionFailure("양 역할이 동일 probe에 매핑됨")

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    power_counts = {role: 0 for role in ROLES}
    power_min = {role: 127 for role in ROLES}
    power_max = {role: -127 for role in ROLES}
    path_count = 0
    path_min = 0xff
    path_max = 0
    event_times: dict[str, float] = {}
    maximum_gap_ms = {"power_central": 0.0, "power_peripheral": 0.0, "path": 0.0}
    status = "FAIL"
    reason: str | None = None

    with ProbeLocks([board["uid"] for board in boards.values()]):
        for role in ROLES:
            board = boards[role]
            board["registers"] = collect_register_identity(board["uid"], board["volume"])
            board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
                role,
                board["uid"],
                board["image"],
                120.0,
                hardware_reset=True,
                preserve_nrf54l_access=True,
            )
        time.sleep(2.0)
        ports = {
            role: serial_module.Serial(board["vcom"], 115200, timeout=0.1)
            for role, board in boards.items()
        }
        try:
            for port in ports.values():
                port.reset_input_buffer()
                port.write((PROTOCOL + "|PROBE\n").encode("ascii"))
                port.flush()
            for role in ROLES:
                line = _line(ports[role], time.monotonic() + 30.0)
                transcript.append(f"{role}: {line}")
                expected = f"{PROTOCOL}|READY|role={role}|core={identity.core}"
                if line != expected:
                    raise PowerPathExecutionFailure(f"{role} READY mismatch")

            start = f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n".encode(
                "ascii"
            )
            for port in ports.values():
                port.write(start)
                port.flush()

            ends: set[str] = set()
            deadline = time.monotonic() + 240.0
            while time.monotonic() < deadline and ends != set(ROLES):
                for role in ROLES:
                    payload = ports[role].readline()
                    if not payload:
                        continue
                    if len(payload) > 512:
                        raise PowerPathExecutionFailure("serial line overlong")
                    line = payload.decode("ascii", errors="replace").strip()
                    if not line.startswith(PROTOCOL + "|"):
                        continue
                    transcript.append(f"{role}: {line}")
                    fields = _fields(line)
                    if fields.get("nonce") != nonce or fields.get("core") != identity.core:
                        raise PowerPathExecutionFailure("nonce 또는 source revision mismatch")
                    if "|FAIL|" in line:
                        raise PowerPathExecutionFailure(f"{role} target FAIL")
                    now = time.monotonic()
                    if "|POWER|" in line:
                        index = int(fields["index"])
                        level = int(fields["level"])
                        if index != power_counts[role] + 1 or not -127 <= level <= 20:
                            raise PowerPathExecutionFailure("power report sequence/range")
                        power_counts[role] = index
                        power_min[role] = min(power_min[role], level)
                        power_max[role] = max(power_max[role], level)
                        key = "power_" + role
                        if key in event_times:
                            maximum_gap_ms[key] = max(
                                maximum_gap_ms[key], (now - event_times[key]) * 1000.0
                            )
                        event_times[key] = now
                    elif "|PATH|" in line:
                        if role != "central":
                            raise PowerPathExecutionFailure("path event role mismatch")
                        index = int(fields["index"])
                        zone = int(fields["zone"])
                        loss = int(fields["loss"])
                        if (
                            index != path_count + 1
                            or zone != (path_count % 3)
                            or not 0 <= loss <= 254
                        ):
                            raise PowerPathExecutionFailure("path report sequence/range")
                        path_count = index
                        path_min = min(path_min, loss)
                        path_max = max(path_max, loss)
                        if "path" in event_times:
                            maximum_gap_ms["path"] = max(
                                maximum_gap_ms["path"],
                                (now - event_times["path"]) * 1000.0,
                            )
                        event_times["path"] = now
                    elif line.startswith(f"{PROTOCOL}|END|"):
                        if fields.get("role") != role or fields.get("status") != "pass":
                            raise PowerPathExecutionFailure("END record mismatch")
                        ends.add(role)
            if ends != set(ROLES):
                raise PowerPathExecutionFailure("role END timeout")
            if power_counts != {"central": POWER_TARGET, "peripheral": POWER_TARGET}:
                raise PowerPathExecutionFailure(f"power denominator mismatch: {power_counts}")
            if path_count != PATH_TARGET:
                raise PowerPathExecutionFailure(f"path denominator mismatch: {path_count}")
            if any(value > 5000.0 for value in maximum_gap_ms.values()):
                raise PowerPathExecutionFailure(f"event latency limit: {maximum_gap_ms}")

            for role in ROLES:
                ports[role].write(f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii"))
                ports[role].flush()
                stop_deadline = time.monotonic() + 30.0
                while True:
                    line = _line(ports[role], stop_deadline)
                    transcript.append(f"{role}: {line}")
                    if "|FAIL|" in line:
                        raise PowerPathExecutionFailure(f"{role} STOP FAIL")
                    if line.startswith(f"{PROTOCOL}|STOPPED|role={role}"):
                        break
            status = "PASS_CANDIDATE" if dirty else "PASS"
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(
                r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason
            )
        finally:
            for port in ports.values():
                port.close()

    public_boards = {
        role: {
            key: value
            for key, value in board.items()
            if key not in {"uid", "image"}
        }
        for role, board in boards.items()
    }
    evidence = {
        "test_ids": ["M32-PWR-01:primary", "M32-PATH-01:primary"],
        "status": status,
        "scope": "two_board_power_and_path_loss_twenty_iterations",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "nonce": nonce,
        "iterations": 20,
        "power_reports": power_counts,
        "power_denominator": sum(power_counts.values()),
        "power_range_dbm": {role: [power_min[role], power_max[role]] for role in ROLES},
        "path_reports": path_count,
        "path_denominator": PATH_TARGET,
        "path_range_db": [path_min, path_max],
        "maximum_event_gap_ms": maximum_gap_ms,
        "allowed_loss": {"power": 0, "path": 1},
        "lost_reports": {"power": 40 - sum(power_counts.values()), "path": 60 - path_count},
        "reason": reason,
    }
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 두 역할의 exact HIL을 실행합니다. """
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
        print(
            f"M32_POWER_PATH_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_POWER_PATH_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
