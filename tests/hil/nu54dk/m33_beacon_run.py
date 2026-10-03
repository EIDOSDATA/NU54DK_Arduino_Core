#!/usr/bin/env python3
"""! @brief 두 SHA-256 NU54DK 역할의 M33 Beacon HIL 증거를 수집합니다. """

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


ROLES = ("advertiser", "observer")
PROTOCOL = "M33BEACON|1"
PACKET_TARGET = 600
PER_FORMAT_TARGET = 150
UNIQUE_TARGET = 10
SWITCH_TARGET = 90
STOP_TAIL_SECONDS = 0.25


class BeaconExecutionFailure(RuntimeError):
    """! @brief mapping·flash·UART·분모 검증의 제한된 실패입니다. """


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 M33 Beacon protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise BeaconExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise BeaconExecutionFailure("serial line timeout")


def _fields(line: str) -> dict[str, str]:
    """! @brief key=value field 중 중복이 없는 record만 허용합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise BeaconExecutionFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise BeaconExecutionFailure(f"invalid integer field: {key}")
    return int(value)


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief attempt 원본과 SHA-256을 덮어쓰기 없이 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise BeaconExecutionFailure("raw probe UID in transcript")
    json_path = prefix.with_suffix(".json")
    transcript_path = prefix.with_suffix(".transcript.log")
    if json_path.exists() or transcript_path.exists():
        raise BeaconExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    transcript_path.write_bytes(raw)
    json_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def _validate_results(results: dict[str, dict[str, str]]) -> None:
    """! @brief advertiser와 observer의 고정 분모·negative 결과를 검증합니다. """
    advertiser = results["advertiser"]
    if _integer(advertiser, "switches") != SWITCH_TARGET:
        raise BeaconExecutionFailure("advertiser switch denominator mismatch")
    for key in ("ibeacon_sequences", "eddystone_sequences", "bthome_sequences"):
        if _integer(advertiser, key) != SWITCH_TARGET // 3:
            raise BeaconExecutionFailure(f"advertiser {key} mismatch")
    if advertiser.get("codec_negative") != "pass":
        raise BeaconExecutionFailure("advertiser codec negative mismatch")

    observer = results["observer"]
    if _integer(observer, "raw") < PACKET_TARGET:
        raise BeaconExecutionFailure("observer packet denominator mismatch")
    for key in ("ibeacon_raw", "eddystone_raw", "bthome_raw"):
        if _integer(observer, key) < PER_FORMAT_TARGET:
            raise BeaconExecutionFailure(f"observer {key} mismatch")
    for key in ("ibeacon_unique", "eddystone_unique", "bthome_unique"):
        if _integer(observer, key) < UNIQUE_TARGET:
            raise BeaconExecutionFailure(f"observer {key} mismatch")
    if _integer(observer, "semantic_errors") != 0:
        raise BeaconExecutionFailure("observer semantic corruption")
    if observer.get("callback_context") != "pass":
        raise BeaconExecutionFailure("observer callback context mismatch")
    if observer.get("codec_negative") != "pass":
        raise BeaconExecutionFailure("observer codec negative mismatch")


def _validate_stop_record(
    role: str,
    line: str,
    nonce: str,
    core: str,
    stopped: bool,
) -> bool:
    """! @brief STOP 뒤 target record와 자원 해제 상태를 fail-closed로 검증합니다. """
    fields = _fields(line)
    record = line.split("|", 3)[2]
    if record == "FAIL":
        raise BeaconExecutionFailure(
            f"{role} target FAIL after STOP: {fields.get('stage', 'unknown')}"
        )
    if record != "STOPPED":
        raise BeaconExecutionFailure(f"{role} unexpected record after STOP: {record}")
    if stopped:
        raise BeaconExecutionFailure(f"{role} duplicate STOPPED record")
    if (
        fields.get("role") != role
        or fields.get("nonce") != nonce
        or fields.get("core") != core
    ):
        raise BeaconExecutionFailure(f"{role} STOP identity mismatch")
    for resource in ("advertising", "scan", "device"):
        if fields.get(resource) != "0":
            raise BeaconExecutionFailure(
                f"{role} STOP cleanup resource mismatch: {resource}"
            )
    return True


def execute(args: argparse.Namespace) -> dict:
    """! @brief 두 image를 sector flash하고 600개 세 형식 광고와 STOP을 검증합니다. """
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
        raise BeaconExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise BeaconExecutionFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise BeaconExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        boards[role] = {
            "uid": uid,
            "image": image,
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["advertiser"]["uid"] == boards["observer"]["uid"]:
        raise BeaconExecutionFailure("두 역할이 서로 다른 probe에 매핑되지 않음")

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
                    raise BeaconExecutionFailure(f"{role} READY mismatch")

            start = f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n".encode("ascii")
            ports["observer"].write(start)
            ports["observer"].flush()
            time.sleep(0.3)
            ports["advertiser"].write(start)
            ports["advertiser"].flush()

            begins: set[str] = set()
            ends: set[str] = set()
            deadline = time.monotonic() + 190.0
            while time.monotonic() < deadline and ends != set(ROLES):
                progressed = False
                for role in ROLES:
                    payload = ports[role].readline()
                    if not payload:
                        continue
                    progressed = True
                    if len(payload) > 512:
                        raise BeaconExecutionFailure("serial line overlong")
                    line = payload.decode("ascii", errors="replace").strip()
                    if not line.startswith(PROTOCOL + "|"):
                        continue
                    transcript.append(f"{role}: {line}")
                    fields = _fields(line)
                    if "|FAIL|" in line:
                        raise BeaconExecutionFailure(
                            f"{role} target FAIL: {fields.get('stage')}"
                        )
                    if fields.get("nonce") != nonce or fields.get("core") != identity.core:
                        raise BeaconExecutionFailure(f"{role} identity mismatch")
                    if line.startswith(f"{PROTOCOL}|BEGIN|"):
                        if fields.get("role") != role or role in begins:
                            raise BeaconExecutionFailure("BEGIN mismatch")
                        begins.add(role)
                    elif line.startswith(f"{PROTOCOL}|RESULT|"):
                        if fields.get("role") != role or role in results:
                            raise BeaconExecutionFailure("RESULT mismatch")
                        results[role] = fields
                    elif line.startswith(f"{PROTOCOL}|END|"):
                        if fields.get("role") != role or fields.get("status") != "pass":
                            raise BeaconExecutionFailure("END mismatch")
                        ends.add(role)
                if not progressed:
                    time.sleep(0.005)

            if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
                raise BeaconExecutionFailure("role result timeout")
            _validate_results(results)
            status = "DEVELOPMENT_PASS" if dirty else "PASS"
        except BaseException as error:
            reason = str(error)
        finally:
            stop_errors: list[str] = []
            for role in ROLES:
                try:
                    ports[role].write(f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii"))
                    ports[role].flush()
                    stop_deadline = time.monotonic() + 20.0
                    stopped = False
                    while True:
                        try:
                            line = _line(ports[role], stop_deadline)
                        except BeaconExecutionFailure as error:
                            if stopped and str(error) == "serial line timeout":
                                break
                            raise
                        transcript.append(f"{role}: {line}")
                        stopped = _validate_stop_record(
                            role, line, nonce, identity.core, stopped
                        )
                        if stopped:
                            stop_deadline = min(
                                stop_deadline,
                                time.monotonic() + STOP_TAIL_SECONDS,
                            )
                except BaseException as error:
                    stop_errors.append(f"{role}: {error}")
                finally:
                    ports[role].close()
            if stop_errors:
                status = "FAIL"
                cleanup_reason = "; ".join(stop_errors)
                if reason is None:
                    reason = cleanup_reason
                else:
                    reason = f"{reason}; cleanup: {cleanup_reason}"

    evidence = {
        "schema": "nucode-m33-beacon-hil-v1",
        "status": status,
        "reason": reason,
        "development": bool(dirty),
        "source_revision": identity.core,
        "board_revision": identity.board,
        "ncs_revision": identity.ncs,
        "zephyr_revision": identity.zephyr,
        "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
        "denominator": {
            "packets": PACKET_TARGET,
            "per_format": PER_FORMAT_TARGET,
            "unique_per_format": UNIQUE_TARGET,
            "switches": SWITCH_TARGET,
        },
        "results": results,
        "boards": {
            role: {
                "probe_sha256": board["probe_sha256"],
                "image_sha256": board["image_sha256"],
                "flash_mode": board["flash_mode"],
                "flash_bytes": board["flash_bytes"],
                "registers": board["registers"],
            }
            for role, board in boards.items()
        },
    }
    _save(prefix, evidence, transcript)
    if status == "FAIL":
        raise BeaconExecutionFailure(reason or "beacon HIL failed")
    return evidence


def main() -> int:
    """! @brief CLI 인자를 검증하고 M33 Beacon HIL을 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--probe-advertiser-sha256", required=True)
    parser.add_argument("--probe-observer-sha256", required=True)
    parser.add_argument("--hex-advertiser", type=Path, required=True)
    parser.add_argument("--hex-observer", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        evidence = execute(args)
    except (BeaconExecutionFailure, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"M33 Beacon HIL FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
