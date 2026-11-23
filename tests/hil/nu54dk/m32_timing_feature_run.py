#!/usr/bin/env python3
"""! @brief 두 SHA-256 NU54DK 역할의 W03 timing·feature HIL 증거를 수집합니다. """

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
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("central", "peripheral")
PROTOCOL = "M32TIM|1"
PROCEDURE_TARGET = 20
PACKET_TARGET = 2000
FEATURE_TARGET = 20
SCA_TARGET = 10
SUBRATE_INCREASE_TARGET = PROCEDURE_TARGET // 2
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m32_ble_timing_hil"


class TimingFeatureExecutionFailure(RuntimeError):
    """! @brief mapping·flash·UART·분모 검증의 제한된 실패입니다. """


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 M32 timing protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise TimingFeatureExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise TimingFeatureExecutionFailure("serial line timeout")


def _fields(line: str) -> dict[str, str]:
    """! @brief key=value field 중 중복이 없는 record만 허용합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise TimingFeatureExecutionFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief attempt 원본과 SHA-256을 덮어쓰기 없이 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise TimingFeatureExecutionFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise TimingFeatureExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise TimingFeatureExecutionFailure(f"invalid integer field: {key}")
    return int(value)


def valid_subrate_ack(
    iteration: int,
    status: int,
    factor: int,
    continuation_number: int,
    peripheral_latency: int,
    supervision_timeout_10ms: int,
) -> bool:
    """! @brief target과 같은 Subrate ACK factor·latency·timeout 경계를 판정합니다. """

    increased = (iteration & 1) != 0
    expected_factor = 4 if increased else 2
    maximum_latency = 3 if increased else 0
    expected_timeout = 800 if increased else 400
    return (
        status == 0
        and factor == expected_factor
        and continuation_number == 0
        and 0 <= peripheral_latency <= maximum_latency
        and supervision_timeout_10ms == expected_timeout
    )


def validate_timing_results(
    results: dict[str, dict[str, str]],
) -> dict[str, int | str]:
    """! @brief timing 결과와 Subrate ACK 전후 payload 경계를 함께 판정합니다. """
    if set(results) != set(ROLES):
        raise TimingFeatureExecutionFailure("role result mismatch")
    central = results["central"]
    peripheral = results["peripheral"]
    if _integer(central, "tx") != PACKET_TARGET or _integer(
        peripheral, "rx"
    ) != PACKET_TARGET:
        raise TimingFeatureExecutionFailure("packet denominator mismatch")
    if _integer(central, "rx") != 0 or _integer(peripheral, "tx") != 0:
        raise TimingFeatureExecutionFailure("packet role mismatch")
    for role, fields in results.items():
        for key in ("subrate", "subrate_ack", "boundary"):
            if _integer(fields, key) != PROCEDURE_TARGET:
                raise TimingFeatureExecutionFailure(
                    f"{role} {key} denominator mismatch"
                )
        if _integer(fields, "subrate_increase_ack") != SUBRATE_INCREASE_TARGET:
            raise TimingFeatureExecutionFailure(
                f"{role} increased Subrate ACK denominator mismatch"
            )
        if _integer(fields, "rate") != PROCEDURE_TARGET:
            raise TimingFeatureExecutionFailure(f"{role} rate denominator mismatch")
        if _integer(fields, "feature") != FEATURE_TARGET or _integer(
            fields, "sca"
        ) != SCA_TARGET:
            raise TimingFeatureExecutionFailure(f"{role} feature/SCA denominator mismatch")
        if fields.get("callback_context") != "pass":
            raise TimingFeatureExecutionFailure(f"{role} callback context")
        if _integer(fields, "packet_gap_ms") > 50:
            raise TimingFeatureExecutionFailure(f"{role} packet latency limit")
        if _integer(fields, "procedure_gap_ms") > 5000:
            raise TimingFeatureExecutionFailure(f"{role} procedure latency limit")
    if _integer(central, "frame") != PROCEDURE_TARGET or _integer(
        peripheral, "frame"
    ) != 2:
        raise TimingFeatureExecutionFailure("frame-space callback denominator mismatch")
    if _integer(central, "channel") != PROCEDURE_TARGET or _integer(
        peripheral, "channel"
    ) != 0:
        raise TimingFeatureExecutionFailure("channel classification denominator mismatch")
    if _integer(central, "min_interval_us") > 750:
        raise TimingFeatureExecutionFailure("minimum interval capability mismatch")
    return {
        "issue": "DRGN-29270",
        "acknowledged_transitions": PROCEDURE_TARGET * len(ROLES),
        "increased_latency_timeout_acknowledgements": (
            SUBRATE_INCREASE_TARGET * len(ROLES)
        ),
        "boundary_payloads": PROCEDURE_TARGET * len(ROLES),
    }


def cleanup_ports(
    ports: dict[str, object],
    nonce: str,
    core: str,
    transcript: list[str],
    timeout_seconds: float = 30.0,
) -> dict:
    """! @brief 성공·실패와 무관하게 열린 모든 endpoint의 STOP을 검증합니다. """

    report = {
        "required": bool(ports),
        "command_sent": {role: False for role in ROLES},
        "stopped": {role: False for role in ROLES},
        "errors": [],
        "status": "NOT_REQUIRED" if not ports else "FAIL",
    }
    command = f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
    for role, port in ports.items():
        try:
            port.write(command)
            port.flush()
            report["command_sent"][role] = True
        except Exception as error:
            report["errors"].append(f"{role} STOP: {type(error).__name__}: {error}")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        progressed = False
        for role, port in ports.items():
            if report["stopped"][role]:
                continue
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
            transcript.append(f"{role}: {line}")
            try:
                parsed = _fields(line)
            except Exception as error:
                report["errors"].append(
                    f"{role} cleanup parse: {type(error).__name__}: {error}"
                )
                continue
            if (
                line.startswith(f"{PROTOCOL}|STOPPED|")
                and parsed.get("role") == role
                and parsed.get("nonce") == nonce
                and parsed.get("core") == core
            ):
                report["stopped"][role] = True
        if ports and all(report["command_sent"][role] and report["stopped"][role]
                         for role in ports):
            report["status"] = "PASS"
            return report
        if not progressed:
            time.sleep(0.005)
    if ports:
        report["errors"].append("bounded STOP evidence incomplete")
    return report


def close_ports(ports: dict[str, object]) -> dict[str, str]:
    """! @brief 부분 serial open을 포함해 handle close 결과를 보존합니다. """

    result = {role: "NOT_OPENED" for role in ROLES}
    for role, port in ports.items():
        try:
            port.close()
            result[role] = "PASS"
        except Exception as error:
            result[role] = f"FAIL:{type(error).__name__}:{error}"
    return result


def execute(args: argparse.Namespace) -> dict:
    """! @brief 두 image를 sector flash하고 W03 네 시험군과 STOP을 검증합니다. """
    prefix = args.output_prefix.resolve()
    native_path = prefix.with_suffix(".json")
    if native_path.exists() or prefix.with_suffix(".transcript.log").exists():
        raise TimingFeatureExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
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
        raise TimingFeatureExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise TimingFeatureExecutionFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    images: dict[str, Path] = {}
    build_records: dict[str, dict[str, str]] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise TimingFeatureExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        images[role] = image
        build_records[role] = validate_build_record(
            image, identity.core, identity.board, APPLICATION_ROOT
        )
        boards[role] = {
            "uid": uid,
            "image": image,
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["central"]["uid"] == boards["peripheral"]["uid"]:
        raise TimingFeatureExecutionFailure("양 역할이 동일 probe에 매핑됨")
    sidecars = reserve_sidecars(native_path, ROLES)
    copy_program_inputs(images, sidecars)
    program_images = {role: sidecars[role]["image"] for role in ROLES}

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    results: dict[str, dict[str, str]] = {}
    subrate_ack_boundary: dict[str, int | str] = {}
    status = "FAIL"
    reason: str | None = None
    ports: dict[str, object] = {}
    flash_records: dict[str, dict[str, str]] = {}
    readback_records: dict[str, dict] = {}
    programming_receipt = None
    cleanup: dict = {"required": False, "status": "NOT_REQUIRED"}
    close_result = {role: "NOT_OPENED" for role in ROLES}

    try:
        with ProbeLocks([board["uid"] for board in boards.values()]):
            for role in ("peripheral", "central"):
                board = boards[role]
                board["registers"] = collect_register_identity(
                    board["uid"], board["volume"]
                )
                mode, byte_count = flash_image_pyocd(
                    role,
                    board["uid"],
                    program_images[role],
                    120.0,
                    hardware_reset=True,
                    preserve_nrf54l_access=True,
                )
                board["flash_mode"] = mode
                board["flash_bytes"] = byte_count
                flash_records[role] = {"mode": mode, "bytes": str(byte_count)}
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
                    raise TimingFeatureExecutionFailure(f"{role} READY mismatch")

            start = f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n".encode("ascii")
            ports["peripheral"].write(start)
            ports["peripheral"].flush()
            time.sleep(0.2)
            ports["central"].write(start)
            ports["central"].flush()

            begins: set[str] = set()
            ends: set[str] = set()
            deadline = time.monotonic() + 250.0
            while time.monotonic() < deadline and ends != set(ROLES):
                progressed = False
                for role in ROLES:
                    payload = ports[role].readline()
                    if not payload:
                        continue
                    progressed = True
                    if len(payload) > 512:
                        raise TimingFeatureExecutionFailure("serial line overlong")
                    line = payload.decode("ascii", errors="replace").strip()
                    if not line.startswith(PROTOCOL + "|"):
                        continue
                    transcript.append(f"{role}: {line}")
                    fields = _fields(line)
                    if "|FAIL|" in line:
                        raise TimingFeatureExecutionFailure(f"{role} target FAIL: {fields.get('stage')}")
                    if fields.get("nonce") != nonce or fields.get("core") != identity.core:
                        raise TimingFeatureExecutionFailure(f"{role} identity mismatch")
                    if line.startswith(f"{PROTOCOL}|BEGIN|"):
                        if fields.get("role") != role or role in begins:
                            raise TimingFeatureExecutionFailure("BEGIN mismatch")
                        begins.add(role)
                    elif line.startswith(f"{PROTOCOL}|RESULT|"):
                        if fields.get("role") != role or role in results:
                            raise TimingFeatureExecutionFailure("RESULT mismatch")
                        results[role] = fields
                    elif line.startswith(f"{PROTOCOL}|END|"):
                        if fields.get("role") != role or fields.get("status") != "pass":
                            raise TimingFeatureExecutionFailure("END mismatch")
                        ends.add(role)
                if not progressed:
                    time.sleep(0.005)

            if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
                raise TimingFeatureExecutionFailure("role result timeout")
            subrate_ack_boundary = validate_timing_results(results)
            status = "PASS_CANDIDATE" if dirty else "PASS"
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
        reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)
    finally:
        try:
            cleanup = cleanup_ports(ports, nonce, identity.core, transcript)
        except Exception as error:
            cleanup = {
                "required": bool(ports),
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
        "test_ids": [
            "M32-SUB-01:primary",
            "M32-SCA-01:primary",
            "M32-TIME-01:primary",
            "M32-FEAT-01:primary",
        ],
        "status": status,
        "scope": "two_board_timing_feature_and_packet_contract",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "nonce": nonce,
        "iterations": PROCEDURE_TARGET,
        "packet_denominator": PACKET_TARGET,
        "feature_samples": FEATURE_TARGET * 2,
        "sca_support_samples": SCA_TARGET * 2,
        "results": results,
        "build_records": build_records,
        "cleanup": cleanup,
        "serial_close": close_result,
        "exact_programming": exact_program,
        "sdk_risk_regression": {
            "DRGN-29270": subrate_ack_boundary if status.startswith("PASS") else {
                "issue": "DRGN-29270",
                "status": "FAIL",
            },
        },
        "allowed_loss": {"packets": 20, "procedures": 0, "features": 0},
        "lost": {
            "packets": PACKET_TARGET - int(results.get("peripheral", {}).get("rx", "0")),
            "procedures": {
                key: PROCEDURE_TARGET - int(results.get("central", {}).get(key, "0"))
                for key in ("subrate", "frame", "rate", "channel")
            },
        },
        "sca_boundary": {
            "controller_procedure": True,
            "host_request_and_report": False,
            "classification": "unsupported_host_initiator_api",
        },
        "reason": reason,
    }
    if status == "PASS":
        evidence["m33_dispatch_attestation"] = dispatch_attestation(
            "m32_timing",
            identity.core,
            PROCEDURE_TARGET,
            (
                "subrating_ack_boundary",
                "latency_timeout",
                "sca",
                "frame_space",
                "bounded_reconnect",
            ),
            ROLES,
            exact_program,
        )
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 두 역할의 exact W03 HIL을 실행합니다. """
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
            f"M32_TIMING_FEATURE_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_TIMING_FEATURE_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
