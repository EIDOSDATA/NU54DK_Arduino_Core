#!/usr/bin/env python3
"""! @brief active CIS·NSE>1·CPU 부하에서 ACL 우선 종료를 20회 검증합니다. """

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

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    flash_image_pyocd,
    git_revision,
    validate_build_record,
)
from m33_sdk_risk_common import (  # noqa: E402
    copy_program_inputs,
    dispatch_attestation,
    exact_program_evidence,
    readback_programmed_images,
    require_exact_clean_source,
    reserve_sidecars,
    validate_programming_receipt,
)
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("central", "peripheral")
PROTOCOL = "M31ISO|1"
ITERATION_TARGET = 20
MINIMUM_LOAD_TICKS = 10
MINIMUM_PAYLOADS = 25
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m31_iso_cis_hil"


class CisAclRiskFailure(RuntimeError):
    """! @brief DRGN-29446 적용 조건이나 종료 증거가 부족한 실패입니다. """


def fields(line: str) -> tuple[str, dict[str, str]]:
    """! @brief 역할 prefix와 중복 없는 ASCII key/value record를 해석합니다. """
    if len(line) > 512 or ": " not in line:
        raise CisAclRiskFailure("malformed protocol line")
    role, payload = line.split(": ", 1)
    if role not in ROLES or not payload.startswith(PROTOCOL + "|"):
        raise CisAclRiskFailure("role/protocol mismatch")
    pieces = payload.split("|")
    values: dict[str, str] = {"event": pieces[2]}
    for piece in pieces[3:]:
        key, separator, value = piece.partition("=")
        if separator != "=" or not key or not value or key in values:
            raise CisAclRiskFailure("duplicate or malformed field")
        values[key] = value
    return role, values


def number(values: dict[str, str], key: str, maximum: int = 1000000) -> int:
    """! @brief 필수 decimal field를 범위 안 정수로 변환합니다. """
    value = values.get(key, "")
    if not value.isdecimal() or int(value) > maximum:
        raise CisAclRiskFailure(f"invalid integer field: {key}")
    return int(value)


def validate_cycle(
    records: dict[str, list[dict[str, str]]],
    nonce: str,
    identity: ExpectedIdentity,
) -> dict[str, dict[str, int]]:
    """! @brief active 조건·ACL 우선 종료·양 역할 자원 반환을 엄격히 판정합니다. """
    expected = (
        "BEGIN", "IDENTITY", "ACL_CONNECTED", "ISO_CONNECTED", "RISK_ACTIVE",
        "ISO_DISCONNECTED", "ACL_DISCONNECTED", "RISK_STOPPED",
    )
    metrics: dict[str, dict[str, int]] = {}
    for role in ROLES:
        role_records = records.get(role, [])
        if tuple(record.get("event") for record in role_records) != expected:
            raise CisAclRiskFailure(f"{role} event sequence mismatch")
        if any(record.get("nonce") != nonce for record in role_records):
            raise CisAclRiskFailure(f"{role} nonce mismatch")
        if role_records[0].get("role") != role:
            raise CisAclRiskFailure(f"{role} BEGIN mismatch")
        identity_record = role_records[1]
        if any(identity_record.get(key) != value for key, value in vars(identity).items()):
            raise CisAclRiskFailure(f"{role} image identity mismatch")
        active = role_records[4]
        stopped = role_records[-1]
        if active.get("role") != role or stopped.get("role") != role:
            raise CisAclRiskFailure(f"{role} risk role mismatch")
        active_nse = number(active, "nse", 31)
        stopped_nse = number(stopped, "nse", 31)
        active_load = number(active, "load_ticks")
        stopped_load = number(stopped, "load_ticks")
        active_payloads = number(active, "payloads", 100)
        transmitted = number(stopped, "tx", 100)
        received = number(stopped, "rx", 100)
        if active_nse <= 1 or stopped_nse != active_nse:
            raise CisAclRiskFailure(f"{role} NSE>1 condition missing")
        if active_load < MINIMUM_LOAD_TICKS or stopped_load < active_load:
            raise CisAclRiskFailure(f"{role} CPU load condition missing")
        if active_payloads < MINIMUM_PAYLOADS or active_payloads >= 100:
            raise CisAclRiskFailure(f"{role} active payload boundary missing")
        if number(stopped, "acl_first", 1) != 1:
            raise CisAclRiskFailure(f"{role} ACL-first teardown missing")
        if role == "central" and transmitted < active_payloads:
            raise CisAclRiskFailure("central transmit count regressed")
        if role == "peripheral" and received < active_payloads:
            raise CisAclRiskFailure("peripheral receive count regressed")
        metrics[role] = {
            "nse": active_nse,
            "load_ticks": stopped_load,
            "payloads_before_abort": active_payloads,
            "transmitted": transmitted,
            "received": received,
        }
    return metrics


def protocol_line(role: str, port: object, deadline: float) -> str:
    """! @brief raw fault를 거부하며 해당 역할의 CIS protocol 줄을 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise CisAclRiskFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        lowered = line.lower()
        if any(marker in lowered for marker in (
            "fatal error", "fault", "assert", "z_fatal_error", "oops", "panic"
        )):
            raise CisAclRiskFailure(f"{role} target fault")
        if line.startswith(PROTOCOL + "|"):
            return f"{role}: {line}"
    raise CisAclRiskFailure(f"{role} serial timeout")


def collect_until(
    ports: dict[str, object],
    records: dict[str, list[dict[str, str]]],
    transcript: list[str],
    target: str,
    timeout_seconds: float,
) -> None:
    """! @brief 양 역할이 지정 event를 한 번씩 보고할 때까지 함께 수집합니다. """
    observed: set[str] = set()
    deadline = time.monotonic() + timeout_seconds
    while observed != set(ROLES):
        progressed = False
        for role, port in ports.items():
            if role in observed:
                continue
            payload = port.readline()
            if not payload:
                continue
            progressed = True
            if len(payload) > 512:
                raise CisAclRiskFailure("serial line overlong")
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                lowered = line.lower()
                if any(marker in lowered for marker in (
                    "fatal error", "fault", "assert", "z_fatal_error", "oops", "panic"
                )):
                    raise CisAclRiskFailure(f"{role} target fault")
                continue
            tagged = f"{role}: {line}"
            transcript.append(tagged)
            parsed_role, record = fields(tagged)
            if record["event"] == "FAIL":
                raise CisAclRiskFailure(f"{role} target FAIL: {record.get('stage')}")
            if record["event"] in {"TX_END", "RX_END"}:
                raise CisAclRiskFailure("CIS finished before ACL risk teardown")
            records[parsed_role].append(record)
            if record["event"] == target:
                observed.add(role)
        if time.monotonic() >= deadline:
            raise CisAclRiskFailure(f"{target} timeout")
        if not progressed:
            time.sleep(0.005)


def cleanup_active_session(
    ports: dict[str, object],
    nonce: str | None,
    transcript: list[str],
    timeout_seconds: float = 12.0,
) -> dict:
    """! @brief 실패 중에도 ACL 종료와 양 endpoint STOP을 끝까지 시도합니다. """

    report = {
        "required": nonce is not None,
        "abort_acl_sent": False,
        "stop_sent": {role: False for role in ROLES},
        "observed": {role: [] for role in ROLES},
        "errors": [],
        "status": "NOT_REQUIRED" if nonce is None else "FAIL",
    }
    if nonce is None:
        return report

    if "central" in ports:
        try:
            ports["central"].write(
                f"{PROTOCOL}|ABORT_ACL|nonce={nonce}\n".encode("ascii")
            )
            ports["central"].flush()
            report["abort_acl_sent"] = True
        except Exception as error:
            report["errors"].append(f"central ABORT_ACL: {type(error).__name__}: {error}")

    deadline = time.monotonic() + timeout_seconds
    stop_phase = False
    while time.monotonic() < deadline:
        if not stop_phase and time.monotonic() >= deadline - (timeout_seconds / 2.0):
            stop_phase = True
            for role, port in ports.items():
                try:
                    port.write(f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii"))
                    port.flush()
                    report["stop_sent"][role] = True
                except Exception as error:
                    report["errors"].append(
                        f"{role} STOP: {type(error).__name__}: {error}"
                    )
        progressed = False
        for role, port in ports.items():
            try:
                payload = port.readline()
            except Exception as error:
                report["errors"].append(
                    f"{role} cleanup read: {type(error).__name__}: {error}"
                )
                continue
            if not payload:
                continue
            progressed = True
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                continue
            tagged = f"{role}: {line}"
            transcript.append(tagged)
            try:
                parsed_role, record = fields(tagged)
            except Exception as error:
                report["errors"].append(
                    f"{role} cleanup parse: {type(error).__name__}: {error}"
                )
                continue
            if record.get("nonce") == nonce:
                report["observed"][parsed_role].append(record.get("event", ""))
        complete = (
            set(ports) == set(ROLES)
            and all(report["stop_sent"][role] for role in ROLES)
            and all(
                "ACL_DISCONNECTED" in report["observed"][role]
                and any(event in report["observed"][role]
                        for event in ("RISK_STOPPED", "STOPPED"))
                for role in ROLES
            )
        )
        if complete:
            report["status"] = "PASS"
            return report
        if not progressed:
            time.sleep(0.005)
    report["errors"].append("bounded cleanup evidence incomplete")
    return report


def close_ports(ports: dict[str, object]) -> dict:
    """! @brief 부분적으로 열린 serial handle도 모두 닫고 결과를 기록합니다. """

    result = {role: "NOT_OPENED" for role in ROLES}
    for role, port in ports.items():
        try:
            port.close()
            result[role] = "PASS"
        except Exception as error:
            result[role] = f"FAIL:{type(error).__name__}:{error}"
    return result


def execute(args: argparse.Namespace) -> dict:
    """! @brief 두 exact image를 sector flash하고 ACL 우선 종료 20회를 수행합니다. """
    prefix = args.output_prefix.resolve()
    native_path = prefix.with_suffix(".json")
    transcript_path = prefix.with_suffix(".transcript.log")
    if native_path.exists() or transcript_path.exists():
        raise CisAclRiskFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(
        git_revision(REPOSITORY), git_revision(BOARD_ROOT),
        git_revision(sdk / "nrf"), git_revision(sdk / "zephyr"),
    )
    if (identity.board != lock["board"]["revision"] or
            identity.ncs != lock["ncs"]["revision"] or
            identity.zephyr != lock["zephyr"]["revision"]):
        raise CisAclRiskFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise CisAclRiskFailure("exact HIL에는 clean source commit이 필요합니다")
    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    build_records: dict[str, dict[str, str]] = {}
    images: dict[str, Path] = {}
    for role in ROLES:
        image = getattr(args, f"hex_{role}").resolve()
        digest = getattr(args, f"probe_{role}_sha256")
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise CisAclRiskFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        images[role] = image
        build_records[role] = validate_build_record(
            image, identity.core, identity.board, APPLICATION_ROOT
        )
        boards[role] = {
            "uid": uid, "image": image, "probe_sha256": digest,
            "volume": volume, "vcom": vcom,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["central"]["uid"] == boards["peripheral"]["uid"]:
        raise CisAclRiskFailure("양 역할이 동일 probe에 매핑됨")
    sidecars = reserve_sidecars(native_path, ROLES)
    copy_program_inputs(images, sidecars)
    program_images = {role: sidecars[role]["image"] for role in ROLES}
    transcript: list[str] = []
    cycles: list[dict] = []
    status = "FAIL"
    reason: str | None = None
    ports: dict[str, object] = {}
    active_nonce: str | None = None
    flash_records: dict[str, dict[str, str]] = {}
    readback_records: dict[str, dict] = {}
    programming_receipt = None
    cleanup = cleanup_active_session({}, None, transcript)
    close_result = {role: "NOT_OPENED" for role in ROLES}
    try:
        with ProbeLocks([board["uid"] for board in boards.values()]):
            for role, board in boards.items():
                board["registers"] = collect_register_identity(
                    board["uid"], board["volume"]
                )
                mode, programmed_bytes = flash_image_pyocd(
                    role, board["uid"], program_images[role], 120.0,
                    hardware_reset=True, preserve_nrf54l_access=True,
                )
                board["flash_mode"] = mode
                board["flash_bytes"] = programmed_bytes
                flash_records[role] = {
                    "mode": mode,
                    "bytes": str(programmed_bytes),
                }
            readback_records, programming_receipt = readback_programmed_images(
                {role: board["uid"] for role, board in boards.items()},
                {role: board["probe_sha256"] for role, board in boards.items()},
                program_images,
                sidecars,
            )
            time.sleep(2.0)
            for role, board in boards.items():
                ports[role] = serial_module.Serial(
                    board["vcom"], 115200, timeout=0.05
                )
            for role, port in ports.items():
                port.reset_input_buffer()
                port.write(f"{PROTOCOL}|PROBE\n".encode("ascii"))
                port.flush()
                line = protocol_line(role, port, time.monotonic() + 10.0)
                transcript.append(line)
                _parsed_role, record = fields(line)
                if record != {"event": "READY", "role": role}:
                    raise CisAclRiskFailure(f"{role} READY mismatch")
            for cycle in range(ITERATION_TARGET):
                nonce = hashlib.sha256(
                    f"{time.time_ns()}:{cycle}:{identity.core}".encode("ascii")
                ).hexdigest()[:32]
                active_nonce = nonce
                records = {role: [] for role in ROLES}
                command = f"{PROTOCOL}|START_RISK|nonce={nonce}|count=100\n".encode("ascii")
                for role in ("peripheral", "central"):
                    ports[role].write(command)
                    ports[role].flush()
                collect_until(ports, records, transcript, "RISK_ACTIVE", 120.0)
                abort = f"{PROTOCOL}|ABORT_ACL|nonce={nonce}\n".encode("ascii")
                ports["central"].write(abort)
                ports["central"].flush()
                collect_until(ports, records, transcript, "RISK_STOPPED", 35.0)
                cycles.append({
                    "cycle": cycle + 1,
                    "nonce": nonce,
                    "status": "PASS",
                    "roles": validate_cycle(records, nonce, identity),
                })
                active_nonce = None
            status = "PASS_CANDIDATE" if dirty else "PASS"
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
    finally:
        try:
            cleanup = cleanup_active_session(ports, active_nonce, transcript)
        except Exception as error:
            cleanup = {
                "required": active_nonce is not None,
                "status": "FAIL",
                "errors": [f"cleanup exception: {type(error).__name__}: {error}"],
            }
        finally:
            close_result = close_ports(ports)
        if cleanup["status"] == "FAIL" or any(
                value.startswith("FAIL:") for value in close_result.values()):
            status = "FAIL"
            cleanup_reason = "resource cleanup was not proven"
            reason = cleanup_reason if reason is None else f"{reason}; {cleanup_reason}"

    exact_program: dict[str, dict] = {}
    if status.startswith("PASS"):
        try:
            if len(cycles) != ITERATION_TARGET:
                raise CisAclRiskFailure("cycle denominator mismatch")
            if status == "PASS":
                require_exact_clean_source(REPOSITORY, identity.core)
            validate_programming_receipt(programming_receipt, ROLES, readback_records)
            exact_program = exact_program_evidence(
                ROLES,
                {role: boards[role]["probe_sha256"] for role in ROLES},
                sidecars,
                flash_records,
                build_records,
                readback_records,
            )
        except Exception as error:
            status = "FAIL"
            reason = f"exact programming proof: {type(error).__name__}: {error}"
    public_boards = {
        role: {key: value for key, value in board.items() if key not in {"uid", "image"}}
        for role, board in boards.items()
    }
    evidence = {
        "test_id": "M33-REG-01:DRGN-29446",
        "status": status,
        "scope": "active_cis_nse_gt_one_cpu_load_acl_first_teardown",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "iterations": ITERATION_TARGET,
        "cycles": cycles,
        "cleanup": cleanup,
        "serial_close": close_result,
        "exact_programming": exact_program,
        "allowed_failures": 0,
        "reason": reason,
    }
    if status == "PASS":
        evidence["m33_dispatch_attestation"] = dispatch_attestation(
            "m33_cis_acl_risk",
            identity.core,
            ITERATION_TARGET,
            ("active_cis", "nse_gt_one", "cpu_load", "acl_first_teardown", "cleanup"),
            ROLES,
            exact_program,
        )
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise CisAclRiskFailure("raw probe UID in transcript")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    transcript_path.write_bytes(raw)
    native_path.write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    return evidence


def main() -> int:
    """! @brief raw UID 없이 DRGN-29446 exact HIL을 실행합니다. """
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
        print(f"M33_CIS_ACL_RISK_FAIL: {type(error).__name__}: {str(error)[:400]}", file=sys.stderr)
        return 1
    print(f"M33_CIS_ACL_RISK={result['status']};CYCLES={len(result['cycles'])}")
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
