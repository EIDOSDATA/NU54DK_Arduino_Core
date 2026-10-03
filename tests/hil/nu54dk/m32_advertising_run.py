#!/usr/bin/env python3
"""! @brief 세 SHA-256 NU54DK 역할의 W04 multi-set HIL 증거를 수집합니다. """

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


ROLES = ("advertiser_a", "advertiser_b", "scanner")
PROTOCOL = "M32ADV|1"
ITERATION_TARGET = 20
PACKET_TARGET = 600
UNIQUE_TARGET = 120
ALLOWED_LOSS = 6


class AdvertisingExecutionFailure(RuntimeError):
    """! @brief mapping·flash·UART·분모 검증의 제한된 실패입니다. """


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 M32 ADV protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise AdvertisingExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise AdvertisingExecutionFailure("serial line timeout")


def _fields(line: str) -> dict[str, str]:
    """! @brief key=value field 중 중복이 없는 record만 허용합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise AdvertisingExecutionFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise AdvertisingExecutionFailure(f"invalid integer field: {key}")
    return int(value)


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief attempt 원본과 SHA-256을 덮어쓰기 없이 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise AdvertisingExecutionFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise AdvertisingExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def execute(args: argparse.Namespace) -> dict:
    """! @brief 세 image를 sector flash하고 6-set 양·음수 경로와 STOP을 검증합니다. """
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
        raise AdvertisingExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise AdvertisingExecutionFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise AdvertisingExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        boards[role] = {
            "uid": uid,
            "image": image,
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if len({board["uid"] for board in boards.values()}) != len(ROLES):
        raise AdvertisingExecutionFailure("세 역할이 서로 다른 probe에 매핑되지 않음")

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    results: dict[str, dict[str, str]] = {}
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
            role: serial_module.Serial(board["vcom"], 115200, timeout=0.05)
            for role, board in boards.items()
        }
        try:
            for port in ports.values():
                port.reset_input_buffer()
            for role in ROLES:
                ports[role].write(f"{PROTOCOL}|PROBE\n".encode("ascii"))
                ports[role].flush()
                line = _line(ports[role], time.monotonic() + 10.0)
                transcript.append(f"{role}: {line}")
                fields = _fields(line)
                if (
                    not line.startswith(f"{PROTOCOL}|READY|")
                    or fields.get("role") != role
                    or fields.get("core") != identity.core
                ):
                    raise AdvertisingExecutionFailure(f"{role} READY mismatch")

            start = f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n".encode("ascii")
            ports["scanner"].write(start)
            ports["scanner"].flush()
            time.sleep(0.3)
            for role in ("advertiser_a", "advertiser_b"):
                ports[role].write(start)
                ports[role].flush()

            begins: set[str] = set()
            ends: set[str] = set()
            deadline = time.monotonic() + 290.0
            while time.monotonic() < deadline and ends != set(ROLES):
                progressed = False
                for role in ROLES:
                    payload = ports[role].readline()
                    if not payload:
                        continue
                    progressed = True
                    if len(payload) > 512:
                        raise AdvertisingExecutionFailure("serial line overlong")
                    line = payload.decode("ascii", errors="replace").strip()
                    if not line.startswith(PROTOCOL + "|"):
                        continue
                    transcript.append(f"{role}: {line}")
                    fields = _fields(line)
                    if "|FAIL|" in line:
                        raise AdvertisingExecutionFailure(
                            f"{role} target FAIL: {fields.get('stage')}"
                        )
                    if fields.get("nonce") != nonce or fields.get("core") != identity.core:
                        raise AdvertisingExecutionFailure(f"{role} identity mismatch")
                    if line.startswith(f"{PROTOCOL}|BEGIN|"):
                        if fields.get("role") != role or role in begins:
                            raise AdvertisingExecutionFailure("BEGIN mismatch")
                        begins.add(role)
                    elif line.startswith(f"{PROTOCOL}|RESULT|"):
                        if fields.get("role") != role or role in results:
                            raise AdvertisingExecutionFailure("RESULT mismatch")
                        results[role] = fields
                    elif line.startswith(f"{PROTOCOL}|END|"):
                        if fields.get("role") != role or fields.get("status") != "pass":
                            raise AdvertisingExecutionFailure("END mismatch")
                        ends.add(role)
                if not progressed:
                    time.sleep(0.005)

            if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
                raise AdvertisingExecutionFailure("role result timeout")
            for role in ("advertiser_a", "advertiser_b"):
                fields = results[role]
                if _integer(fields, "updates") != ITERATION_TARGET or _integer(
                    fields, "sets"
                ) != 3:
                    raise AdvertisingExecutionFailure(f"{role} update/set denominator mismatch")
                for key in ("over_capacity_rejected", "stale_set_rejected"):
                    if _integer(fields, key) != 1:
                        raise AdvertisingExecutionFailure(f"{role} {key} mismatch")
            scanner = results["scanner"]
            if _integer(scanner, "raw") < PACKET_TARGET:
                raise AdvertisingExecutionFailure("scanner packet denominator mismatch")
            if _integer(scanner, "unique") != UNIQUE_TARGET:
                raise AdvertisingExecutionFailure("scanner unique denominator mismatch")
            if _integer(scanner, "corrupt") != 0:
                raise AdvertisingExecutionFailure("scanner payload/SID corruption")
            if _integer(scanner, "dropped") > ALLOWED_LOSS:
                raise AdvertisingExecutionFailure("scan queue loss limit")
            if _integer(scanner, "scan_initiate_conflict_rejected") != 1:
                raise AdvertisingExecutionFailure("scan/initiate conflict path mismatch")
            for role, fields in results.items():
                if fields.get("callback_context") != "pass":
                    raise AdvertisingExecutionFailure(f"{role} callback context")

            for role in ROLES:
                ports[role].write(f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii"))
                ports[role].flush()
                stop_deadline = time.monotonic() + 30.0
                while True:
                    line = _line(ports[role], stop_deadline)
                    transcript.append(f"{role}: {line}")
                    if "|FAIL|" in line:
                        raise AdvertisingExecutionFailure(f"{role} STOP FAIL")
                    fields = _fields(line)
                    if fields.get("nonce") != nonce or fields.get("core") != identity.core:
                        raise AdvertisingExecutionFailure(f"{role} STOP identity mismatch")
                    if line.startswith(f"{PROTOCOL}|STOPPED|role={role}"):
                        break
            status = "PASS_CANDIDATE" if dirty else "PASS"
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)
        finally:
            for port in ports.values():
                port.close()

    public_boards = {
        role: {key: value for key, value in board.items() if key not in {"uid", "image"}}
        for role, board in boards.items()
    }
    scanner = results.get("scanner", {})
    raw_reports = int(scanner.get("raw", "0"))
    evidence = {
        "test_ids": ["M32-ADV-01:primary"],
        "status": status,
        "scope": "three_board_extended_advertising_set_sid_contract",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "nonce": nonce,
        "iterations": ITERATION_TARGET,
        "packet_denominator": PACKET_TARGET,
        "unique_denominator": UNIQUE_TARGET,
        "results": results,
        "negative_denominators": {
            "over_capacity": sum(
                int(results.get(role, {}).get("over_capacity_rejected", "0"))
                for role in ("advertiser_a", "advertiser_b")
            ),
            "stale_set": sum(
                int(results.get(role, {}).get("stale_set_rejected", "0"))
                for role in ("advertiser_a", "advertiser_b")
            ),
            "scan_initiate_conflict": int(
                scanner.get("scan_initiate_conflict_rejected", "0")
            ),
        },
        "allowed_loss": {"scan_queue": ALLOWED_LOSS},
        "lost": {
            "reports": max(0, PACKET_TARGET - raw_reports),
            "scan_queue": int(scanner.get("dropped", "0")),
        },
        "reason": reason,
    }
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 세 역할의 exact W04 advertising HIL을 실행합니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--probe-{role.replace('_', '-')}-sha256", required=True)
        parser.add_argument(f"--hex-{role.replace('_', '-')}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(
            f"M32_ADV_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_ADV_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
