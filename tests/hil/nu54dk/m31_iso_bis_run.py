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
from m31_iso_bis import parse_bis_transcript, validate_bis_envelope  # noqa: E402
from m31_iso_bis_negative import parse_negative_transcript, validate_negative_envelope  # noqa: E402
from m31_iso_time import parse_time_transcript, validate_time_envelope  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("source", "receiver")
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m31_iso_bis_hil"


class BisExecutionFailure(RuntimeError):
    """! @brief flash·VCOM·BIS protocol의 유한 실패입니다. """


def classify_bis_noise_risk(measurement: object | None) -> dict:
    """! @brief bounded baseline과 미실행 noisy-RF 조건을 별도 상태로 보존합니다. """
    baseline = "FAIL"
    if measurement is not None:
        cycles = getattr(measurement, "cycles", 0)
        sent = getattr(measurement, "total_sent", 0)
        received = getattr(measurement, "total_received", 0)
        minimum = getattr(measurement, "minimum_received", 0)
        if cycles == 20 and sent == 2000 and 1980 <= received <= 2000 and minimum >= 99:
            baseline = "PASS"
    return {
        "issue": "DRGN-29320",
        "bounded_baseline": baseline,
        "baseline_cycles": getattr(measurement, "cycles", 0) if measurement is not None else 0,
        "baseline_sent": getattr(measurement, "total_sent", 0) if measurement is not None else 0,
        "baseline_received": (
            getattr(measurement, "total_received", 0) if measurement is not None else 0
        ),
        "allowed_loss_per_cycle": 1,
        "controlled_noisy_rf": "NOT_RUN",
        "overall_status": "NOT_RUN" if baseline == "PASS" else "FAIL",
        "not_run_is_pass": False,
    }


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


def cleanup_active_session(
    ports: dict[str, object],
    nonce: str | None,
    transcript: list[str],
    timeout_seconds: float = 35.0,
) -> dict:
    """! @brief 예외 뒤에도 활성 BIG/BIS를 양 역할에서 유한 STOP합니다. """

    report = {
        "required": nonce is not None,
        "command_sent": {role: False for role in ROLES},
        "stopped": {role: False for role in ROLES},
        "errors": [],
        "status": "NOT_REQUIRED" if nonce is None else "FAIL",
    }
    if nonce is None:
        return report
    for role, port in ports.items():
        try:
            write_command(port, f"M31BIS|1|STOP|nonce={nonce}")
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
            if not line.startswith("M31BIS|1|"):
                continue
            transcript.append(f"{role}: {line}")
            if line.startswith(f"M31BIS|1|STOPPED|nonce={nonce}"):
                report["stopped"][role] = True
        if ports and all(report["command_sent"][role] and report["stopped"][role]
                         for role in ports) and set(ports) == set(ROLES):
            report["status"] = "PASS"
            return report
        if not progressed:
            time.sleep(0.005)
    report["errors"].append("bounded BIS cleanup evidence incomplete")
    return report


def close_ports(ports: dict[str, object]) -> dict[str, str]:
    """! @brief 부분 serial open을 포함해 handle close 결과를 기록합니다. """

    result = {role: "NOT_OPENED" for role in ROLES}
    for role, port in ports.items():
        try:
            port.close()
            result[role] = "PASS"
        except Exception as error:
            result[role] = f"FAIL:{type(error).__name__}:{error}"
    return result


def run_bis_phase(
    ports: dict[str, object],
    phase: str,
    cycles: int,
    identity: ExpectedIdentity,
    image_sha256: str,
    ready_lines: list[str],
    transcript: list[str],
    session_state: dict[str, str | None],
    time_sync: bool = False,
) -> tuple[list[str], bytes, list[dict]]:
    """! @brief typed BIS phase를 독립 nonce로 실행하고 실제 raw 범위를 반환합니다. """

    if phase not in {"baseline", "wrong_broadcast_code", "sync_loss"}:
        raise BisExecutionFailure("unknown BIS phase")
    phase_start = len(transcript)
    nonces: list[str] = []
    records: list[dict] = []
    for cycle in range(cycles):
        cycle_start = len(transcript)
        nonce = hashlib.sha256(
            f"{time.time_ns()}:{phase}:{cycle}:{image_sha256}".encode()
        ).hexdigest()[:32]
        if nonce in nonces:
            raise BisExecutionFailure("BIS phase nonce collision")
        nonces.append(nonce)
        session_state["nonce"] = nonce
        command = f"M31BIS|1|START|nonce={nonce}|count=100"
        if phase == "wrong_broadcast_code" and cycle == 0:
            write_command(ports["receiver"], "M31BIS|1|BAD_CODE")
            wait_event(
                ports["receiver"],
                "receiver",
                transcript,
                "BAD_CODE_READY",
                None,
                10.0,
            )
        write_command(ports["source"], command)
        wait_event(ports["source"], "source", transcript, "BIG_SYNCED", nonce, 60.0)
        write_command(ports["receiver"], command)
        wait_event(
            ports["receiver"], "receiver", transcript, "BIG_SYNCED", nonce, 60.0
        )
        if phase == "sync_loss" and cycle == 0:
            write_command(
                ports["receiver"], f"M31BIS|1|EXPECT_SYNC_LOSS|nonce={nonce}"
            )
            wait_event(
                ports["receiver"], "receiver", transcript, "LOSS_ARMED", nonce, 10.0
            )
            write_command(ports["source"], f"M31BIS|1|STOP|nonce={nonce}")
            wait_event(ports["source"], "source", transcript, "STOPPED", nonce, 35.0)
            wait_event(
                ports["receiver"], "receiver", transcript, "SYNC_LOST", nonce, 35.0
            )
            write_command(ports["receiver"], f"M31BIS|1|STOP|nonce={nonce}")
            wait_event(
                ports["receiver"], "receiver", transcript, "STOPPED", nonce, 35.0
            )
        else:
            write_command(ports["source"], f"M31BIS|1|SEND|nonce={nonce}")
            wait_event(ports["source"], "source", transcript, "TX_END", nonce, 60.0)
            if phase == "wrong_broadcast_code" and cycle == 0:
                time.sleep(1.0)
                write_command(
                    ports["receiver"], f"M31BIS|1|CHECK_BAD_CODE|nonce={nonce}"
                )
                wait_event(
                    ports["receiver"],
                    "receiver",
                    transcript,
                    "BAD_CODE_REJECTED",
                    nonce,
                    10.0,
                )
                for role in ROLES:
                    write_command(ports[role], f"M31BIS|1|STOP|nonce={nonce}")
                for role in ROLES:
                    wait_event(ports[role], role, transcript, "STOPPED", nonce, 35.0)
            elif time_sync:
                wait_event(
                    ports["receiver"], "receiver", transcript, "RX_END", nonce, 60.0
                )
                for role in ROLES:
                    write_command(ports[role], f"M31BIS|1|STOP|nonce={nonce}")
                for role in ROLES:
                    wait_event(ports[role], role, transcript, "STOPPED", nonce, 35.0)
            else:
                time.sleep(0.25)
                write_command(ports["receiver"], f"M31BIS|1|STOP|nonce={nonce}")
                wait_event(
                    ports["receiver"], "receiver", transcript, "RX_END", nonce, 10.0
                )
                wait_event(
                    ports["receiver"], "receiver", transcript, "STOPPED", nonce, 35.0
                )
                write_command(ports["source"], f"M31BIS|1|STOP|nonce={nonce}")
                wait_event(
                    ports["source"], "source", transcript, "STOPPED", nonce, 35.0
                )
        session_state["nonce"] = None
        cycle_lines = transcript[cycle_start:]
        if not cycle_lines:
            raise BisExecutionFailure("empty BIS cycle transcript")
        records.append(
            {
                "cycle": cycle + 1,
                "nonce": nonce,
                "status": "PASS",
                "transcript_line_start": cycle_start + 1,
                "transcript_line_end": len(transcript),
                "transcript_sha256": hashlib.sha256(
                    ("\n".join(cycle_lines) + "\n").encode(
                        "ascii", errors="replace"
                    )
                ).hexdigest(),
            }
        )
    raw_lines = ready_lines + transcript[phase_start:]
    raw = ("\n".join(raw_lines) + "\n").encode("ascii", errors="replace")
    return nonces, raw, records


def validate_aggregate_phase_records(records: list[dict], transcript: list[str]) -> None:
    """! @brief baseline 20회와 두 negative 2+2의 typed raw 결합을 검사합니다. """

    expected = (("baseline", 20), ("wrong_broadcast_code", 2), ("sync_loss", 2))
    if [(row.get("phase"), row.get("cycles")) for row in records] != list(expected):
        raise BisExecutionFailure("BIS aggregate phase denominator mismatch")
    if transcript[:2] != [
        "source: M31BIS|1|READY|role=source",
        "receiver: M31BIS|1|READY|role=receiver",
    ]:
        raise BisExecutionFailure("BIS aggregate READY evidence mismatch")
    all_nonces: list[str] = []
    expected_start = 3
    for row in records:
        if row.get("status") != "PASS" or row.get("measurement") is None:
            raise BisExecutionFailure("BIS aggregate phase semantic mismatch")
        cycles = row.get("cycle_records", [])
        if len(cycles) != row["cycles"] or cycles[0].get("cycle") != 1 or \
                row.get("nonces") != [cycle.get("nonce") for cycle in cycles]:
            raise BisExecutionFailure("BIS aggregate raw cycle mismatch")
        phase_start = cycles[0].get("transcript_line_start")
        phase_end = cycles[-1].get("transcript_line_end")
        if not isinstance(phase_start, int) or not isinstance(phase_end, int):
            raise BisExecutionFailure("BIS aggregate phase range mismatch")
        phase_raw = ("\n".join(transcript[:2] + transcript[phase_start - 1:phase_end]) +
                     "\n").encode("ascii", errors="replace")
        if row.get("transcript_sha256") != hashlib.sha256(phase_raw).hexdigest():
            raise BisExecutionFailure("BIS aggregate phase digest mismatch")
        for expected_cycle, cycle in enumerate(cycles, start=1):
            start = cycle.get("transcript_line_start")
            end = cycle.get("transcript_line_end")
            nonce = cycle.get("nonce", "")
            if cycle.get("cycle") != expected_cycle or cycle.get("status") != "PASS" or \
                    re.fullmatch(r"[0-9a-f]{32}", nonce) is None or \
                    not isinstance(start, int) or not isinstance(end, int) or \
                    start != expected_start or end < start or end > len(transcript):
                raise BisExecutionFailure("BIS aggregate raw range mismatch")
            cycle_lines = transcript[start - 1:end]
            raw = ("\n".join(cycle_lines) + "\n").encode(
                "ascii", errors="replace"
            )
            if cycle.get("transcript_sha256") != hashlib.sha256(raw).hexdigest():
                raise BisExecutionFailure("BIS aggregate raw digest mismatch")
            for role in ROLES:
                for event in ("BEGIN", "STOPPED"):
                    marker = f"{role}: M31BIS|1|{event}|nonce={nonce}"
                    if sum(line.startswith(marker) for line in cycle_lines) != 1:
                        raise BisExecutionFailure("BIS aggregate raw event mismatch")
            if row["phase"] == "wrong_broadcast_code" and expected_cycle == 1 and \
                    not any("|BAD_CODE_REJECTED|" in line for line in cycle_lines):
                raise BisExecutionFailure("BIS wrong-code raw evidence missing")
            if row["phase"] == "sync_loss" and expected_cycle == 1 and \
                    not any("|SYNC_LOST|" in line for line in cycle_lines):
                raise BisExecutionFailure("BIS sync-loss raw evidence missing")
            all_nonces.append(nonce)
            expected_start = end + 1
        measurement = row["measurement"]
        if row["phase"] == "baseline":
            if measurement.get("cycles") != 20 or \
                    measurement.get("total_sent") != 2000 or \
                    not 1980 <= measurement.get("total_received", 0) <= 2000 or \
                    measurement.get("minimum_received", 0) < 99:
                raise BisExecutionFailure("BIS baseline measurement mismatch")
        elif measurement.get("negative_class") != row["phase"] or \
                measurement.get("cycles") != 2 or \
                measurement.get("rejected_payloads") != 0 or \
                measurement.get("recovery_sent") != 100 or \
                measurement.get("recovery_received", 0) < 99:
            raise BisExecutionFailure("BIS negative measurement mismatch")
    if len(all_nonces) != 24 or len(set(all_nonces)) != 24:
        raise BisExecutionFailure("BIS aggregate nonce uniqueness mismatch")


def execute(args: argparse.Namespace) -> dict:
    """! @brief source 먼저 광고하고 receiver 동기 뒤 SEND로 SDU를 시작합니다. """
    prefix = args.output_prefix.resolve()
    native_path = prefix.with_suffix(".json")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(".transcript.log").exists():
        raise BisExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    if args.cycles < 1 or args.cycles > 20:
        raise BisExecutionFailure("development cycle 분모는 1..20입니다")
    if args.negative and args.cycles != 2:
        raise BisExecutionFailure("BIS negative는 실패 1회·복구 1회입니다")
    if args.negative and args.time_sync:
        raise BisExecutionFailure("negative BIS와 ISO timestamp는 별도 기능 gate입니다")
    if args.cycles != (2 if args.negative else 20) and not args.development:
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
    images: dict[str, Path] = {}
    build_records: dict[str, dict[str, str]] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise BisExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        images[role] = image
        build_records[role] = validate_build_record(
            image, identity.core, identity.board, APPLICATION_ROOT
        )
        boards[role] = {
            "uid": uid, "image": image, "probe_sha256": digest, "volume": volume,
            "vcom": vcom, "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if boards["source"]["uid"] == boards["receiver"]["uid"]:
        raise BisExecutionFailure("양 역할이 동일 probe에 매핑됨")
    sidecars = reserve_sidecars(native_path, ROLES)
    copy_program_inputs(images, sidecars)
    program_images = {role: sidecars[role]["image"] for role in ROLES}
    transcript: list[str] = []
    nonces: list[str] = []
    phase_records: list[dict] = []
    phase_measurements: dict[str, dict] = {}
    reason = None
    status = "FAIL"
    measured = None
    aggregate = False
    ports: dict[str, object] = {}
    session_state: dict[str, str | None] = {"nonce": None}
    flash_records: dict[str, dict[str, str]] = {}
    readback_records: dict[str, dict] = {}
    programming_receipt = None
    cleanup: dict = {"required": False, "status": "NOT_REQUIRED"}
    close_result = {role: "NOT_OPENED" for role in ROLES}
    try:
        with ProbeLocks([board["uid"] for board in boards.values()]):
            for role in ROLES:
                board = boards[role]
                board["registers"] = collect_register_identity(board["uid"], board["volume"])
                mode, byte_count = flash_image_pyocd(
                    role, board["uid"], program_images[role], 120.0, hardware_reset=True
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
                    board["vcom"], 115200, timeout=0.15
                )
            for role in ROLES:
                ports[role].reset_input_buffer()
                write_command(ports[role], "M31BIS|1|PROBE")
            for role in ROLES:
                line = wait_event(ports[role], role, transcript, "READY", None, 30.0)
                if line != f"M31BIS|1|READY|role={role}":
                    raise BisExecutionFailure(f"{role} READY mismatch")
            ready_lines = list(transcript)
            public_boards = {
                role: {
                    key: value
                    for key, value in board.items()
                    if key not in {"uid", "image"}
                }
                for role, board in boards.items()
            }
            image_hashes = {
                role: board["image_sha256"] for role, board in boards.items()
            }
            aggregate = (
                not args.development
                and not args.time_sync
                and args.negative is None
                and args.cycles == 20
            )
            plans = (
                (("baseline", 20), ("wrong_broadcast_code", 2), ("sync_loss", 2))
                if aggregate
                else ((args.negative or "baseline", args.cycles),)
            )
            for phase, phase_cycles in plans:
                phase_nonces, raw, raw_records = run_bis_phase(
                    ports,
                    phase,
                    phase_cycles,
                    identity,
                    boards["source"]["image_sha256"],
                    ready_lines,
                    transcript,
                    session_state,
                    time_sync=args.time_sync,
                )
                nonces.extend(phase_nonces)
                phase_measurement = None
                if phase_cycles == 20:
                    if args.time_sync:
                        phase_measurement = (
                            parse_time_transcript(raw, phase_nonces, identity)
                            if dirty
                            else validate_time_envelope(
                                {
                                    "source_clean": True,
                                    "test_id": "M31-ISO-01:time_sync",
                                    "transcript": raw,
                                    "nonces": phase_nonces,
                                    "boards": public_boards,
                                },
                                image_hashes,
                                identity,
                            )
                        )
                    else:
                        phase_measurement = (
                            parse_bis_transcript(raw, phase_nonces, identity)
                            if dirty
                            else validate_bis_envelope(
                                {
                                    "source_clean": True,
                                    "test_id": "M31-ISO-01:bis",
                                    "transcript": raw,
                                    "nonces": phase_nonces,
                                    "boards": public_boards,
                                },
                                image_hashes,
                                identity,
                            )
                        )
                elif phase in {"wrong_broadcast_code", "sync_loss"}:
                    phase_measurement = (
                        parse_negative_transcript(raw, phase_nonces, identity, phase)
                        if dirty
                        else validate_negative_envelope(
                            {
                                "source_clean": True,
                                "test_id": "M31-ISO-01:bis",
                                "negative_class": phase,
                                "transcript": raw,
                                "nonces": phase_nonces,
                                "boards": public_boards,
                            },
                            image_hashes,
                            identity,
                        )
                    )
                if phase_measurement is not None:
                    phase_measurements[phase] = vars(phase_measurement)
                phase_records.append(
                    {
                        "phase": phase,
                        "status": "PASS" if phase_measurement is not None else "DEV_PROBE",
                        "cycles": phase_cycles,
                        "nonces": phase_nonces,
                        "transcript_sha256": hashlib.sha256(raw).hexdigest(),
                        "cycle_records": raw_records,
                        "measurement": (
                            vars(phase_measurement)
                            if phase_measurement is not None
                            else None
                        ),
                    }
                )
                if phase == "baseline":
                    measured = phase_measurement
            if aggregate:
                validate_aggregate_phase_records(phase_records, transcript)
            status = (
                "PASS_CANDIDATE"
                if dirty and measured is not None
                else "PASS"
                if all(row["status"] == "PASS" for row in phase_records)
                else "DEV_PROBE"
            )
    except Exception as error:
        reason = type(error).__name__ + ": " + str(error)
        reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
        reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)
    finally:
        try:
            cleanup = cleanup_active_session(ports, session_state["nonce"], transcript)
        except Exception as error:
            cleanup = {
                "required": session_state["nonce"] is not None,
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
    attestation: dict | None = None
    if status in {"PASS", "PASS_CANDIDATE", "DEV_PROBE"}:
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
            if status == "PASS" and aggregate:
                attestation = dispatch_attestation(
                    "m31_iso_bis",
                    identity.core,
                    20,
                    (
                        "bis_sdu",
                        "wrong_broadcast_code",
                        "sync_loss",
                        "bounded_packet_loss",
                        "cleanup",
                    ),
                    ROLES,
                    exact_program,
                )
        except Exception as error:
            status = "FAIL"
            reason = f"exact programming proof: {type(error).__name__}: {error}"
    public_boards = {role: {key: value for key, value in board.items()
                           if key not in {"uid", "image"}} for role, board in boards.items()}
    evidence = {
        "test_id": "M31-ISO-01:time_sync" if args.time_sync else "M31-ISO-01:bis",
        "scope": "two_board_iso_timestamp_twenty_cycles" if args.time_sync else
                 "two_board_bis_negative_and_recovery" if args.negative else
                 "two_board_bis_twenty_plus_negative_two_plus_two"
                 if aggregate else "two_board_bis_twenty_cycles",
        "negative_class": args.negative,
        "status": status, "source_clean": not bool(dirty), "identity": vars(identity),
        "boards": public_boards, "nonces": nonces, "cycles": args.cycles,
        "physical_sessions": len(nonces),
        "phase_records": phase_records,
        "phase_measurements": phase_measurements,
        "build_records": build_records,
        "cleanup": cleanup,
        "serial_close": close_result,
        "exact_programming": exact_program,
        "reason": reason, "measurement": vars(measured) if measured is not None else None,
        "sdk_risk_regression": {
            "DRGN-29320": classify_bis_noise_risk(measured)
            if not args.negative and not args.time_sync
            else {
                "issue": "DRGN-29320",
                "overall_status": "NOT_RUN",
                "reason": "separate_baseline_required",
                "not_run_is_pass": False,
            },
        },
    }
    if attestation is not None:
        evidence["m33_dispatch_attestation"] = attestation
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
    parser.add_argument("--negative", choices=("wrong_broadcast_code", "sync_loss"))
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
