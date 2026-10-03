#!/usr/bin/env python3
"""! @brief 두 NU54DK에서 W05 Nordic extension exact HIL을 실행합니다. """

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
PROTOCOL = "M32NOR|1"
ITERATION_TARGET = 20
QOS_TARGET = 200
SURVEY_TARGET = 20
ANCHOR_TARGET = 1000
EVENT_TARGET = 200
PREPARE_TARGET = 200
ANCHOR_GAP_LIMIT_US = 5000
EVENT_GAP_LIMIT_MS = 5
LLPM_INTERVAL_LIMIT_US = 1000


class NordicExtensionFailure(RuntimeError):
    """! @brief mapping·flash·UART·Nordic 분모 실패를 나타냅니다. """


def _fields(line: str) -> dict[str, str]:
    """! @brief 중복 없는 key=value field만 반환합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise NordicExtensionFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise NordicExtensionFailure(f"invalid integer field: {key}")
    return int(value)


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 W05 protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 768:
            raise NordicExtensionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise NordicExtensionFailure("serial line timeout")


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief 실패 원본을 포함한 attempt를 덮어쓰기 없이 저장합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise NordicExtensionFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise NordicExtensionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def _validate_result(role: str, fields: dict[str, str]) -> None:
    """! @brief 역할별 callback 분모·latency·negative·ACL 경계를 판정합니다. """
    expected = {
        "qos": QOS_TARGET,
        "survey": SURVEY_TARGET,
        "anchors": ANCHOR_TARGET,
        "events": EVENT_TARGET,
        "prepares": PREPARE_TARGET,
        "iterations": ITERATION_TARGET,
    }
    for key, value in expected.items():
        if _integer(fields, key) != value:
            raise NordicExtensionFailure(f"{role} {key} denominator mismatch")
    interval = _integer(fields, "llpm_interval_us")
    if interval == 0 or interval > LLPM_INTERVAL_LIMIT_US:
        raise NordicExtensionFailure(f"{role} LLPM interval limit")
    if _integer(fields, "max_anchor_gap_us") > ANCHOR_GAP_LIMIT_US:
        raise NordicExtensionFailure(f"{role} anchor latency limit")
    if _integer(fields, "max_event_gap_ms") > EVENT_GAP_LIMIT_MS:
        raise NordicExtensionFailure(f"{role} event latency limit")
    for key in (
        "overflow_observed",
        "invalid_survey_rejected",
        "invalid_event_task_rejected",
        "duplicate_reservation_bounded",
        "disabled_callback_quiet",
        "projection_wrap_pass",
        "acl_controller_experimental",
    ):
        if _integer(fields, key) != 1:
            raise NordicExtensionFailure(f"{role} {key} boundary")
    if role == "central" and _integer(fields, "invalid_llpm_rejected") != 1:
        raise NordicExtensionFailure("central invalid LLPM boundary")
    if _integer(fields, "acl_host_transmit_path") != 0 or _integer(
        fields, "acl_usable"
    ) != 0:
        raise NordicExtensionFailure(f"{role} ACL support boundary")
    if fields.get("callback_context") != "pass":
        raise NordicExtensionFailure(f"{role} callback context")


def _read_session(ports: dict[str, object], nonce: str, core: str,
                  transcript: list[str]) -> dict[str, dict[str, str]]:
    """! @brief 두 UART를 함께 읽어 BEGIN·RESULT·END를 엄격히 수집합니다. """
    begins: set[str] = set()
    ends: set[str] = set()
    results: dict[str, dict[str, str]] = {}
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline and ends != set(ROLES):
        progressed = False
        for role, port in ports.items():
            payload = port.readline()
            if not payload:
                continue
            progressed = True
            if len(payload) > 768:
                raise NordicExtensionFailure("serial line overlong")
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                if line:
                    transcript.append(f"{role}-raw: {line}")
                continue
            transcript.append(f"{role}: {line}")
            fields = _fields(line)
            if "|FAIL|" in line:
                raise NordicExtensionFailure(
                    f"{role} target FAIL: {fields.get('stage')}"
                )
            if fields.get("nonce") != nonce or fields.get("core") != core:
                raise NordicExtensionFailure(f"{role} identity mismatch")
            if line.startswith(f"{PROTOCOL}|BEGIN|"):
                if fields.get("role") != role or role in begins:
                    raise NordicExtensionFailure("BEGIN mismatch")
                begins.add(role)
            elif line.startswith(f"{PROTOCOL}|RESULT|"):
                if fields.get("role") != role or role in results:
                    raise NordicExtensionFailure("RESULT mismatch")
                _validate_result(role, fields)
                results[role] = fields
            elif line.startswith(f"{PROTOCOL}|END|"):
                if fields.get("role") != role or fields.get("status") != "pass":
                    raise NordicExtensionFailure("END mismatch")
                ends.add(role)
        if not progressed:
            time.sleep(0.005)
    if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
        raise NordicExtensionFailure("role result timeout")
    return results


def _stop_both(ports: dict[str, object], nonce: str, core: str,
               transcript: list[str]) -> None:
    """! @brief 두 STOP을 먼저 전송한 뒤 각 cleanup 완료를 검증합니다. """
    command = f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
    for port in ports.values():
        port.write(command)
        port.flush()
    for role, port in ports.items():
        deadline = time.monotonic() + 30.0
        while True:
            line = _line(port, deadline)
            transcript.append(f"{role}: {line}")
            fields = _fields(line)
            if "|FAIL|" in line:
                raise NordicExtensionFailure(f"{role} STOP FAIL")
            if line.startswith(f"{PROTOCOL}|STOPPED|role={role}"):
                if (
                    fields.get("cleanup") != "pass"
                    or fields.get("nonce") != nonce
                    or fields.get("core") != core
                ):
                    raise NordicExtensionFailure(f"{role} STOP mismatch")
                break


def execute(args: argparse.Namespace) -> dict:
    """! @brief 두 image를 V2 sector flash하고 W05 계약과 STOP을 검증합니다. """
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
        raise NordicExtensionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise NordicExtensionFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise NordicExtensionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        boards[role] = {
            "uid": uid,
            "volume": volume,
            "vcom": vcom,
            "image": image,
            "probe_sha256": digest,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["central"]["uid"] == boards["peripheral"]["uid"]:
        raise NordicExtensionFailure("양 역할이 동일 probe에 매핑됨")

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    results: dict[str, dict[str, str]] = {}
    status = "FAIL"
    reason: str | None = None
    with ProbeLocks([board["uid"] for board in boards.values()]):
        try:
            for role in ("peripheral", "central"):
                board = boards[role]
                board["registers"] = collect_register_identity(
                    board["uid"], board["volume"]
                )
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
                for role, port in ports.items():
                    port.write(f"{PROTOCOL}|PROBE\n".encode("ascii"))
                    port.flush()
                    line = _line(port, time.monotonic() + 10.0)
                    transcript.append(f"{role}: {line}")
                    fields = _fields(line)
                    if (
                        not line.startswith(f"{PROTOCOL}|READY|")
                        or fields.get("role") != role
                        or fields.get("core") != identity.core
                    ):
                        raise NordicExtensionFailure(f"{role} READY mismatch")

                start = (
                    f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n"
                ).encode("ascii")
                ports["peripheral"].write(start)
                ports["peripheral"].flush()
                time.sleep(0.2)
                ports["central"].write(start)
                ports["central"].flush()
                results = _read_session(ports, nonce, identity.core, transcript)
                _stop_both(ports, nonce, identity.core, transcript)
                status = "PASS_CANDIDATE" if dirty else "PASS"
            finally:
                for port in ports.values():
                    port.close()
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)

    public_boards = {
        role: {key: value for key, value in board.items() if key not in {"uid", "image"}}
        for role, board in boards.items()
    }
    evidence = {
        "test_ids": [
            "M32-NORDIC-01:primary",
            "M32-SYNC-01:primary",
            "M32-EVENT-01:primary",
        ],
        "status": status,
        "scope": "two_board_nordic_extension_contract",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "nonce": nonce,
        "iterations": ITERATION_TARGET,
        "denominators": {
            "qos_per_role": QOS_TARGET,
            "survey_per_role": SURVEY_TARGET,
            "anchor_per_role": ANCHOR_TARGET,
            "event_per_role": EVENT_TARGET,
            "radio_prepare_per_role": PREPARE_TARGET,
        },
        "latency_limits": {
            "anchor_gap_us": ANCHOR_GAP_LIMIT_US,
            "event_gap_ms": EVENT_GAP_LIMIT_MS,
            "llpm_interval_us": LLPM_INTERVAL_LIMIT_US,
        },
        "results": results,
        "acl_boundary": {
            "controller_experimental": True,
            "host_transmit_path": False,
            "usable": False,
            "classification": "unsupported_host_transmit_path",
        },
        "reason": reason,
    }
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 두 역할의 W05 HIL을 실행합니다. """
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
            f"M32_NORDIC_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_NORDIC_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
