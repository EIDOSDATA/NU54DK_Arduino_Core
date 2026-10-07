#!/usr/bin/env python3
"""! @brief active CS와 scan이 겹친 상태의 ACL 종료·재연결을 20회 검증합니다. """

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
from typing import Any


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
from onboard_start import reset_halted_start  # noqa: E402
from p2_gatt_memory_run import import_pyserial, read_lines, require_mapping  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("initiator", "reflector")
ITERATION_TARGET = 20
ACTIVE = re.compile(
    r"P2_CS_RISK_ACTIVE cycle=(\d+) radio=scan acl=connected"
)
ABORT = re.compile(
    r"P2_CS_RISK_ABORT cycle=(\d+) radio=scan acl=disconnect-requested"
)
DISCONNECTED = re.compile(
    r"P2_CS_RISK_DISCONNECTED cycle=(\d+) radio_scan=([01])"
)
FAULT_MARKERS = (
    "p2_fail",
    "fatal error",
    "fault",
    "assert",
    "z_fatal_error",
    "oops",
    "panic",
    " failed",
    "cs initiator failed:",
    "cs reflector controller error:",
)


class CsAclRadioRiskFailure(RuntimeError):
    """! @brief DRGN-29669의 활성·radio·종료·복구 증거가 부족한 실패입니다. """


def _single_position(lines: list[str], expected: str) -> int:
    """! @brief cycle 구간에서 exact 문자열이 한 번만 나온 위치를 반환합니다. """

    positions = [index for index, line in enumerate(lines) if line == expected]
    if len(positions) != 1:
        raise CsAclRadioRiskFailure(f"exact marker count mismatch: {expected}")
    return positions[0]


def _single_match(lines: list[str], pattern: re.Pattern[str]) -> tuple[int, re.Match[str]]:
    """! @brief cycle 구간에서 정규식 record가 한 번만 나온 위치와 값을 반환합니다. """

    matches = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := pattern.fullmatch(line)) is not None
    ]
    if len(matches) != 1:
        raise CsAclRadioRiskFailure("risk record count mismatch")
    return matches[0]


def reject_faults(lines: dict[str, list[str]]) -> None:
    """! @brief target fault와 library 오류를 원인 추정 없이 즉시 거부합니다. """

    for role, role_lines in lines.items():
        for line in role_lines:
            lowered = line.lower()
            if any(marker in lowered for marker in FAULT_MARKERS):
                raise CsAclRadioRiskFailure(f"{role} target failure marker")


def validate_cycle(lines: dict[str, list[str]], cycle: int) -> dict[str, Any]:
    """! @brief 활성 CS·scan 겹침부터 ACL 반환·재활성까지 exact 순서를 검사합니다. """

    if set(lines) != set(ROLES) or cycle <= 0:
        raise CsAclRadioRiskFailure("cycle input mismatch")
    reject_faults(lines)
    initiator = lines["initiator"]
    reflector = lines["reflector"]
    active_position, active = _single_match(initiator, ACTIVE)
    abort_position, abort = _single_match(initiator, ABORT)
    risk_position, disconnected = _single_match(initiator, DISCONNECTED)
    if any(int(match.group(1)) != cycle for match in (active, abort, disconnected)):
        raise CsAclRadioRiskFailure("risk cycle number mismatch")
    if disconnected.group(2) != "1":
        raise CsAclRadioRiskFailure("scan was not active at ACL disconnect callback")
    link_down_position = _single_position(initiator, "CS initiator disconnected")
    connected_position = _single_position(
        initiator, "CS initiator connected; securing"
    )
    requested_position = _single_position(initiator, "CS procedures requested")
    if not (
        active_position < abort_position < risk_position < link_down_position <
        connected_position < requested_position
    ):
        raise CsAclRadioRiskFailure("initiator teardown/recovery order mismatch")
    reflector_down = _single_position(reflector, "CS reflector disconnected")
    reflector_connected = _single_position(reflector, "CS reflector connected")
    reflector_active = _single_position(reflector, "CS procedures enabled")
    if not (reflector_down < reflector_connected < reflector_active):
        raise CsAclRadioRiskFailure("reflector teardown/recovery order mismatch")
    return {
        "cycle": cycle,
        "radio_schedule": "scan",
        "radio_active_at_disconnect_callback": True,
        "acl_teardown": "observed_both_roles",
        "automatic_recovery": "cs_active",
    }


def resolve_probes(expected: dict[str, str]) -> dict[str, str]:
    """! @brief SHA-256 identity 두 개를 현재 exact probe UID에 결합합니다. """

    from pyocd.core.helpers import ConnectHelper

    connected = {
        hashlib.sha256(probe.unique_id.lower().encode("ascii")).hexdigest():
            probe.unique_id
        for probe in ConnectHelper.get_all_connected_probes(
            blocking=False, print_wait_message=False
        )
    }
    if len(set(expected.values())) != len(ROLES) or any(
        digest not in connected for digest in expected.values()
    ):
        raise CsAclRadioRiskFailure("exact two-probe SHA mapping is not present")
    return {role: connected[digest] for role, digest in expected.items()}


def wait_for_new(
    streams: dict[str, Any],
    pending: dict[str, bytearray],
    lines: dict[str, list[str]],
    role: str,
    start: int,
    expected: str,
    timeout_seconds: float,
) -> None:
    """! @brief fault를 감시하며 현재 cycle의 새 문자열을 유한 대기합니다. """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        read_lines(streams, pending, lines)
        reject_faults(lines)
        if any(line == expected for line in lines[role][start:]):
            return
        time.sleep(0.02)
    raise CsAclRadioRiskFailure(f"{role} marker timeout: {expected}")


def cleanup_active_session(
    streams: dict[str, Any],
    pending: dict[str, bytearray],
    lines: dict[str, list[str]],
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """! @brief 실패 지점과 무관하게 disconnect와 양 STOP을 독립 시도합니다. """

    offsets = {role: len(lines[role]) for role in ROLES}
    report: dict[str, Any] = {
        "required": bool(streams),
        "commands": {
            "initiator_stop": False,
            "initiator_disconnect": False,
            "reflector_stop": False,
        },
        "observed": {},
        "errors": [],
        "status": "NOT_REQUIRED" if not streams else "FAIL",
    }
    commands = (
        ("initiator", b"s", "initiator_stop"),
        ("initiator", b"d", "initiator_disconnect"),
        ("reflector", b"s", "reflector_stop"),
    )
    for role, command, label in commands:
        stream = streams.get(role)
        if stream is None:
            report["errors"].append(f"{role} app serial was not opened")
            continue
        try:
            stream.write(command)
            stream.flush()
            report["commands"][label] = True
        except Exception as error:
            report["errors"].append(
                f"{label}: {type(error).__name__}: {error}"
            )

    deadline = time.monotonic() + timeout_seconds
    while streams and pending and time.monotonic() < deadline:
        try:
            read_lines(streams, pending, lines)
        except Exception as error:
            report["errors"].append(
                f"cleanup read: {type(error).__name__}: {error}"
            )
        report["observed"] = {
            "initiator_stop": any(
                line == "P2_STOP role=cs-initiator"
                for line in lines["initiator"][offsets["initiator"]:]
            ),
            "initiator_disconnected": any(
                line == "CS initiator disconnected"
                for line in lines["initiator"][offsets["initiator"]:]
            ),
            "reflector_stop": any(
                line == "P2_STOP role=cs-reflector"
                for line in lines["reflector"][offsets["reflector"]:]
            ),
            "reflector_disconnected": any(
                line == "CS reflector disconnected"
                for line in lines["reflector"][offsets["reflector"]:]
            ),
        }
        if (
            all(report["commands"].values())
            and report["observed"]["initiator_stop"]
            and report["observed"]["reflector_stop"]
            and (
                report["observed"]["initiator_disconnected"]
                or report["observed"]["reflector_disconnected"]
            )
        ):
            report["status"] = "PASS"
            return report
        time.sleep(0.02)
    if streams:
        report["errors"].append("bounded CS cleanup evidence incomplete")
    return report


def close_serial_handles(
    streams: dict[str, Any], auxiliary: dict[str, Any]
) -> dict[str, str]:
    """! @brief app·aux의 부분 open handle을 역할별로 모두 닫습니다. """

    result = {
        f"{role}_{channel}": "NOT_OPENED"
        for role in ROLES
        for channel in ("app", "aux")
    }
    for channel, handles in (("app", streams), ("aux", auxiliary)):
        for role, stream in handles.items():
            try:
                stream.close()
                result[f"{role}_{channel}"] = "PASS"
            except Exception as error:
                result[f"{role}_{channel}"] = (
                    f"FAIL:{type(error).__name__}:{error}"
                )
    return result


def execute(args: argparse.Namespace) -> dict[str, Any]:
    """! @brief exact image를 sector flash하고 active CS ACL 종료·복구를 20회 수행합니다. """

    output = args.output.resolve()
    transcript_output = output.with_suffix(".transcript.log")
    if output.exists() or transcript_output.exists():
        raise CsAclRadioRiskFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    sdk = args.sdk_root.resolve()
    lock = json.loads(
        (REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
    )
    identity = {
        "core": git_revision(REPOSITORY),
        "board": git_revision(BOARD_ROOT),
        "ncs": git_revision(sdk / "nrf"),
        "zephyr": git_revision(sdk / "zephyr"),
    }
    if (
        identity["board"] != lock["board"]["revision"] or
        identity["ncs"] != lock["ncs"]["revision"] or
        identity["zephyr"] != lock["zephyr"]["revision"]
    ):
        raise CsAclRadioRiskFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise CsAclRadioRiskFailure("exact HIL에는 clean source commit이 필요합니다")
    hashes = {
        role: getattr(args, f"probe_{role}_sha256")
        for role in ROLES
    }
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes.values()):
        raise CsAclRadioRiskFailure("probe identity는 lowercase SHA-256이어야 합니다")
    probe_ids = resolve_probes(hashes)
    images = {role: getattr(args, f"hex_{role}").resolve() for role in ROLES}
    ports = {
        role: {
            "app": getattr(args, f"{role}_app"),
            "aux": getattr(args, f"{role}_aux"),
        }
        for role in ROLES
    }
    applications = {
        "initiator": REPOSITORY / "tests/arduino-cli/p2_cs_initiator",
        "reflector": REPOSITORY / "tests/arduino-cli/p2_cs_reflector",
    }
    build_records: dict[str, dict[str, str]] = {}
    for role in ROLES:
        if not images[role].is_file() or images[role].suffix.lower() != ".hex":
            raise CsAclRadioRiskFailure(f"{role} exact HEX가 없습니다")
        for port in ports[role].values():
            require_mapping(port, probe_ids[role])
        build_records[role] = validate_build_record(
            images[role], identity["core"], identity["board"], applications[role]
        )
    sidecars = reserve_sidecars(output, ROLES)
    copy_program_inputs(images, sidecars)
    program_images = {role: sidecars[role]["image"] for role in ROLES}
    serial_module, _list_ports = import_pyserial()
    lines: dict[str, list[str]] = {role: [] for role in ROLES}
    streams: dict[str, Any] = {}
    auxiliary: dict[str, Any] = {}
    pending: dict[str, bytearray] = {}
    cycles: list[dict[str, Any]] = []
    flash: dict[str, dict[str, str]] = {}
    readback_records: dict[str, dict] = {}
    programming_receipt = None
    start: dict[str, Any] = {}
    status = "FAIL"
    reason: str | None = None
    cleanup: dict[str, Any] = {
        "required": False,
        "status": "NOT_REQUIRED",
    }
    close_result: dict[str, str] = {}
    try:
        with ProbeLocks(probe_ids.values()):
            for role in ("reflector", "initiator"):
                mode, byte_count = flash_image_pyocd(
                    role,
                    probe_ids[role],
                    program_images[role],
                    120.0,
                    preserve_nrf54l_access=True,
                )
                flash[role] = {"mode": mode, "bytes": str(byte_count)}
            readback_records, programming_receipt = readback_programmed_images(
                probe_ids, hashes, program_images, sidecars
            )
            for role in ROLES:
                streams[role] = serial_module.Serial(
                    ports[role]["app"], 115200, timeout=0.1
                )
            for role in ROLES:
                auxiliary[role] = serial_module.Serial(
                    ports[role]["aux"], 115200, timeout=0.1
                )
            pending = {role: bytearray() for role in ROLES}
            for role in ("reflector", "initiator"):
                marker_start = len(lines[role])
                if role == "initiator":
                    initial_active = len(lines["reflector"])
                start[role] = reset_halted_start(
                    {"app": streams[role], "aux": auxiliary[role]}, probe_ids[role]
                )
                wait_for_new(
                    streams,
                    pending,
                    lines,
                    role,
                    marker_start,
                    f"P2_READY role=cs-{role}",
                    30.0,
                )
            wait_for_new(
                streams,
                pending,
                lines,
                "reflector",
                initial_active,
                "CS procedures enabled",
                90.0,
            )
            for cycle in range(1, ITERATION_TARGET + 1):
                offsets = {role: len(lines[role]) for role in ROLES}
                streams["initiator"].write(b"x")
                streams["initiator"].flush()
                wait_for_new(
                    streams,
                    pending,
                    lines,
                    "initiator",
                    offsets["initiator"],
                    f"P2_CS_RISK_DISCONNECTED cycle={cycle} radio_scan=1",
                    30.0,
                )
                wait_for_new(
                    streams,
                    pending,
                    lines,
                    "initiator",
                    offsets["initiator"],
                    "CS procedures requested",
                    90.0,
                )
                wait_for_new(
                    streams,
                    pending,
                    lines,
                    "reflector",
                    offsets["reflector"],
                    "CS procedures enabled",
                    90.0,
                )
                read_lines(streams, pending, lines)
                cycle_lines = {
                    role: lines[role][offsets[role]:]
                    for role in ROLES
                }
                cycles.append(validate_cycle(cycle_lines, cycle))
            status = "PASS_CANDIDATE" if dirty else "PASS"
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
    finally:
        try:
            cleanup = cleanup_active_session(streams, pending, lines)
        except Exception as error:
            cleanup = {
                "required": bool(streams),
                "status": "FAIL",
                "errors": [f"cleanup exception: {type(error).__name__}: {error}"],
            }
        finally:
            close_result = close_serial_handles(streams, auxiliary)
        if cleanup["status"] == "FAIL" or any(
                value.startswith("FAIL:") for value in close_result.values()):
            status = "FAIL"
            cleanup_reason = "resource cleanup was not proven"
            reason = cleanup_reason if reason is None else f"{reason}; {cleanup_reason}"

    exact_program: dict[str, dict] = {}
    if status.startswith("PASS"):
        try:
            if len(cycles) != ITERATION_TARGET:
                raise CsAclRadioRiskFailure("cycle denominator mismatch")
            if status == "PASS":
                require_exact_clean_source(REPOSITORY, identity["core"])
            validate_programming_receipt(programming_receipt, ROLES, readback_records)
            exact_program = exact_program_evidence(
                ROLES,
                hashes,
                sidecars,
                flash,
                build_records,
                readback_records,
            )
        except Exception as error:
            status = "FAIL"
            reason = f"exact programming proof: {type(error).__name__}: {error}"
    transcript = "".join(
        f"{role}: {line}\n"
        for role in ROLES
        for line in lines[role]
    ).encode("utf-8", errors="backslashreplace")
    if b"uid=" in transcript.lower() or b"probe_id=" in transcript.lower():
        raise CsAclRadioRiskFailure("raw probe UID in transcript")
    evidence = {
        "test_id": "M33-REG-01:DRGN-29669",
        "status": status,
        "scope": "active_cs_scan_overlap_acl_teardown_and_recovery",
        "source_clean": not bool(dirty),
        "identity": identity,
        "probe_uid_sha256": hashes,
        "com_mapping": ports,
        "image_sha256": {
            role: hashlib.sha256(image.read_bytes()).hexdigest()
            for role, image in images.items()
        },
        "build_records": build_records,
        "flash": flash,
        "start": start,
        "iterations": ITERATION_TARGET,
        "cycles": cycles,
        "cleanup": cleanup,
        "serial_close": close_result,
        "exact_programming": exact_program,
        "allowed_failures": 0,
        "reason": reason,
        "transcript_sha256": hashlib.sha256(transcript).hexdigest(),
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "not_run_is_pass": False,
    }
    if status == "PASS":
        evidence["m33_dispatch_attestation"] = dispatch_attestation(
            "m33_cs_acl_radio_risk",
            identity["core"],
            ITERATION_TARGET,
            (
                "active_cs",
                "scan_overlap",
                "acl_teardown",
                "radio_schedule",
                "bounded_reconnect",
                "cleanup",
            ),
            ROLES,
            exact_program,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    transcript_output.write_bytes(transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 DRGN-29669 exact HIL을 실행합니다. """

    parser = argparse.ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--probe-{role}-sha256", required=True)
        parser.add_argument(f"--{role}-app", required=True)
        parser.add_argument(f"--{role}-aux", required=True)
        parser.add_argument(f"--hex-{role}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        print(
            f"M33_CS_ACL_RADIO_RISK_FAIL: {type(error).__name__}: {str(error)[:400]}",
            file=sys.stderr,
        )
        return 1
    print(f"M33_CS_ACL_RADIO_RISK={result['status']};CYCLES={len(result['cycles'])}")
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
