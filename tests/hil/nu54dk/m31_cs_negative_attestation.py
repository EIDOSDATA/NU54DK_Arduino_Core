#!/usr/bin/env python3
"""! @brief M31 Channel Sounding negative phase의 raw·program 증적을 결합합니다. """

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import subprocess
from typing import Any


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"

from ble_pair_hil_common import validate_build_record  # noqa: E402
from m33_sdk_risk_common import (  # noqa: E402
    copy_program_inputs,
    dispatch_attestation,
    exact_program_evidence,
    readback_programmed_images,
    require_exact_clean_source,
    reserve_sidecars,
    validate_programming_receipt,
)


SHA256 = re.compile(r"[0-9a-f]{64}")


class CsNegativeAttestationFailure(RuntimeError):
    """! @brief CS negative 분모·raw 의미·program provenance 위반입니다. """


@dataclass(frozen=True)
class NegativePhaseSpec:
    """! @brief 한 가지 negative 조건의 실제 역할·분모·의미 계약입니다. """

    identifier: str
    roles: tuple[str, ...]
    cycles: int
    semantics: tuple[str, ...]


@dataclass(frozen=True)
class ProgramPhase:
    """! @brief 실행 전에 보존한 phase별 image·build record입니다. """

    spec: NegativePhaseSpec
    images: dict[str, Path]
    build_records: dict[str, dict[str, str]]
    sidecars: dict[str, dict[str, Path]]
    board_revision: str


PHASES = {
    "stale_key": NegativePhaseSpec(
        "m31_cs_negative_stale_key",
        ("initiator", "reflector"),
        1,
        ("stale_key", "security_rejection", "no_ras_progress", "cleanup"),
    ),
    "insecure_read": NegativePhaseSpec(
        "m31_cs_negative_insecure_read",
        ("client", "reflector"),
        20,
        ("insecure_read", "same_acl", "security_rejection", "cleanup"),
    ),
    "wrong_peer": NegativePhaseSpec(
        "m31_cs_negative_wrong_peer",
        ("initiator", "reflector", "wrong_peer"),
        100,
        ("wrong_peer", "service_identity", "ras_procedures", "cleanup"),
    ),
    "missing_service": NegativePhaseSpec(
        "m31_cs_negative_missing_service",
        ("initiator", "missing_service_peer"),
        20,
        ("missing_service", "gatt_rejection", "no_ras_progress", "cleanup"),
    ),
}


def _digest(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_hash(raw_uid: str) -> str:
    """! @brief 실제 probe UID를 dispatcher와 같은 방식으로 hash합니다. """

    normalized = raw_uid.strip().lower()
    if not normalized or not normalized.isascii():
        raise CsNegativeAttestationFailure("probe UID가 비어 있거나 ASCII가 아닙니다")
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def _board_revision() -> str:
    """! @brief 현재 clean source에 결합된 board submodule revision을 반환합니다. """

    try:
        revision = subprocess.check_output(
            ["git", "-C", str(BOARD_ROOT), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise CsNegativeAttestationFailure(
            "board submodule revision을 확인하지 못했습니다"
        ) from error
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise CsNegativeAttestationFailure("board submodule revision 형식이 잘못됐습니다")
    return revision


def prepare_program_phase(
    evidence_path: Path,
    phase_name: str,
    source_revision: str,
    images: dict[str, Path],
    application_roots: dict[str, Path],
) -> ProgramPhase:
    """! @brief phase의 exact build와 실제 program 입력 byte를 실행 전에 보존합니다. """

    spec = PHASES.get(phase_name)
    if spec is None:
        raise CsNegativeAttestationFailure("알 수 없는 CS negative phase입니다")
    if (
        set(images) != set(spec.roles)
        or set(application_roots) != set(spec.roles)
        or evidence_path.exists()
    ):
        raise CsNegativeAttestationFailure("phase role 또는 output 계약이 다릅니다")
    require_exact_clean_source(REPOSITORY, source_revision)
    board_revision = _board_revision()
    build_records = {
        role: validate_build_record(
            images[role].resolve(),
            source_revision,
            board_revision,
            application_roots[role].resolve(),
        )
        for role in spec.roles
    }
    sidecars = reserve_sidecars(evidence_path.resolve(), spec.roles)
    copied = copy_program_inputs(
        {role: images[role].resolve() for role in spec.roles}, sidecars
    )
    for role in spec.roles:
        if (
            copied[role]["image_sha256"] != _digest(images[role])
            or copied[role]["build_record_sha256"]
            != build_records[role].get("record_sha256")
        ):
            raise CsNegativeAttestationFailure(
                f"{phase_name}/{role} program 입력 byte가 build와 다릅니다"
            )
    return ProgramPhase(
        spec,
        {role: images[role].resolve() for role in spec.roles},
        build_records,
        sidecars,
        board_revision,
    )


def complete_program_phase(
    phase: ProgramPhase,
    source_revision: str,
    probe_ids: dict[str, str],
    declared_probe_hashes: dict[str, str],
    flash_results: dict[str, tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """! @brief sector program과 모든 HEX range의 same-process live readback을 결합합니다. """

    roles = phase.spec.roles
    if (
        set(probe_ids) != set(roles)
        or set(declared_probe_hashes) != set(roles)
        or set(flash_results) != set(roles)
    ):
        raise CsNegativeAttestationFailure("program probe·flash role 분모가 다릅니다")
    require_exact_clean_source(REPOSITORY, source_revision)
    actual_hashes = {role: probe_hash(probe_ids[role]) for role in roles}
    if actual_hashes != declared_probe_hashes or any(
        SHA256.fullmatch(value) is None for value in actual_hashes.values()
    ):
        raise CsNegativeAttestationFailure("실제 probe와 선언 hash가 다릅니다")
    readbacks, receipt = readback_programmed_images(
        probe_ids, actual_hashes, phase.images, phase.sidecars
    )
    validate_programming_receipt(receipt, roles, readbacks)
    flash_records: dict[str, dict[str, str]] = {}
    for role in roles:
        result = flash_results[role]
        if (
            not isinstance(result, tuple)
            or len(result) != 2
            or not isinstance(result[0], str)
            or not result[0].startswith("pyocd-sector")
            or not isinstance(result[1], str)
            or not result[1].isdecimal()
            or int(result[1]) <= 0
        ):
            raise CsNegativeAttestationFailure(
                f"{phase.spec.identifier}/{role} sector program 증거가 없습니다"
            )
        flash_records[role] = {"mode": result[0], "bytes": result[1]}
    return exact_program_evidence(
        roles,
        actual_hashes,
        phase.sidecars,
        flash_records,
        phase.build_records,
        readbacks,
    )


def _cleanup_rows(
    cleanup: dict[str, dict[str, str]], spec: NegativePhaseSpec
) -> None:
    """! @brief phase별 STOP·disconnect·serial close의 완전한 역할 분모를 검사합니다. """

    if set(cleanup) != set(spec.roles):
        raise CsNegativeAttestationFailure("cleanup role 분모가 다릅니다")
    for role, row in cleanup.items():
        if (
            set(row) != {"stop", "disconnect", "serial_close"}
            or row["stop"] not in {"PASS", "NOT_APPLICABLE"}
            or row["disconnect"] not in {"PASS", "NOT_APPLICABLE"}
            or row["serial_close"] != "PASS"
        ):
            raise CsNegativeAttestationFailure(f"{role} cleanup이 완전하지 않습니다")


def _records(spec: NegativePhaseSpec) -> list[dict[str, Any]]:
    """! @brief 검증된 실제 분모를 dispatcher cycle record로 변환합니다. """

    semantics = {token: "PASS" for token in spec.semantics}
    return [
        {"cycle": cycle, "status": "PASS", "semantics": dict(semantics)}
        for cycle in range(1, spec.cycles + 1)
    ]


def _stale_status(role: str, lines: list[str]) -> dict[str, int]:
    """! @brief stale-key transcript의 마지막 exact status를 role별로 파싱합니다. """

    tail = "raw" if role == "initiator" else "active"
    pattern = re.compile(
        rf"CSKEY {role} status bonds=(\d+) pairing_requests=(\d+) "
        rf"pairing_rejected=(\d+) security_errors=(\d+) "
        rf"security_reason=(\d+) disconnects=(\d+) "
        rf"disconnect_reason=(\d+) l2=(\d+) ready=(\d+) "
        rf"{tail}=(\d+) connected=([01])"
    )
    names = (
        "bonds",
        "pairing_requests",
        "pairing_rejected",
        "security_errors",
        "security_reason",
        "disconnects",
        "disconnect_reason",
        "l2",
        "ready",
        tail,
        "connected",
    )
    for line in reversed(lines):
        match = pattern.fullmatch(line)
        if match is not None:
            return dict(zip(names, map(int, match.groups()), strict=True))
    raise CsNegativeAttestationFailure(f"{role} stale-key raw status가 없습니다")


def _stale_rejection_path(
    initiator: dict[str, int], reflector: dict[str, int]
) -> str:
    """! @brief raw status만으로 stale-key의 실제 보안 거부 경로를 판정합니다. """

    for row in (initiator, reflector):
        if row["pairing_requests"] != row["pairing_rejected"]:
            raise CsNegativeAttestationFailure("stale-key repair 요청이 거부되지 않았습니다")
        if row["security_errors"] > 0 and row["security_reason"] == 0:
            raise CsNegativeAttestationFailure("stale-key security reason이 없습니다")
        if row["disconnects"] > 0 and row["disconnect_reason"] == 0:
            raise CsNegativeAttestationFailure("stale-key disconnect reason이 없습니다")
    if any(row["pairing_rejected"] > 0 for row in (initiator, reflector)):
        return "application_repair_rejected"
    if not any(
        row["security_errors"] > 0 or row["disconnects"] > 0
        for row in (initiator, reflector)
    ):
        raise CsNegativeAttestationFailure("stale-key raw 거부 신호가 없습니다")
    if initiator["connected"] != 0 or reflector["connected"] != 0:
        if not any(row["security_errors"] > 0 for row in (initiator, reflector)):
            raise CsNegativeAttestationFailure("연결 유지 중 security error가 없습니다")
        return "security_error_acl_retained"
    return "controller_key_failure_disconnect"


def build_stale_key_records(
    record: dict[str, Any], cleanup: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    """! @brief one-sided stale key 1회의 보안 거부와 CS 무진행을 raw에서 재도출합니다. """

    spec = PHASES["stale_key"]
    _cleanup_rows(cleanup, spec)
    initiator_lines = record.get("initiator_lines", [])
    reflector_lines = record.get("reflector_lines", [])
    if not isinstance(initiator_lines, list) or not isinstance(
        reflector_lines, list
    ):
        raise CsNegativeAttestationFailure("stale-key transcript가 list가 아닙니다")
    initiator = _stale_status("initiator", initiator_lines)
    reflector = _stale_status("reflector", reflector_lines)
    rejection_path = _stale_rejection_path(initiator, reflector)
    prime_raw = sum(
        "CSKEY initiator prime ready raw=" in line for line in initiator_lines
    )
    negative_raw = sum(
        line == "CSKEY initiator negative raw UNEXPECTED"
        for line in initiator_lines
    )
    if (
        record.get("test") != "one_sided_stale_key_rejection"
        or record.get("arbitrary_unequal_ltk_injection") is not False
        or prime_raw < 1
        or record.get("prime_raw_reports") != prime_raw
        or negative_raw != 0
        or record.get("negative_raw_reports") != negative_raw
        or record.get("rejection_path") != rejection_path
        or record.get("initiator_negative") != initiator
        or record.get("reflector_negative") != reflector
        or initiator.get("bonds") != 1
        or reflector.get("bonds") != 0
        or any(initiator.get(name) != 0 for name in ("l2", "ready", "raw"))
        or any(reflector.get(name) != 0 for name in ("l2", "ready", "active"))
        or not all(
            cleanup[role]["stop"] == "PASS"
            and cleanup[role]["disconnect"] == "PASS"
            for role in spec.roles
        )
    ):
        raise CsNegativeAttestationFailure("stale-key raw 의미 또는 분모가 다릅니다")
    for role, lines in (
        ("initiator", initiator_lines),
        ("reflector", reflector_lines),
    ):
        if not isinstance(lines, list) or f"CSKEY {role} STOPPED" not in lines:
            raise CsNegativeAttestationFailure("stale-key STOP raw marker가 없습니다")
    return _records(spec)


def build_insecure_read_records(
    record: dict[str, Any], cleanup: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    """! @brief 동일 ACL의 미암호화 Ranging Features 거부 20회를 재도출합니다. """

    spec = PHASES["insecure_read"]
    _cleanup_rows(cleanup, spec)
    lines = record.get("client_lines", [])
    pattern = re.compile(r"CS insecure read rejected att=(5|15) count=(\d+) ms=(\d+)")
    matches = [pattern.fullmatch(line) for line in lines if pattern.fullmatch(line)]
    counters = [int(match.group(2)) for match in matches]
    timestamps = [int(match.group(3)) for match in matches]
    bad = (
        "CS insecure read ACCEPTED",
        "CS insecure retry rejected",
        "CS insecure unexpected att=",
    )
    if (
        record.get("test") != "unencrypted_ranging_features_read_20"
        or record.get("same_acl") is not True
        or record.get("mode") != "same_acl"
        or record.get("cycles_expected") != 20
        or record.get("rejected") != 20
        or record.get("connections") != 1
        or record.get("connection_events_observed") != sum(
            line.startswith("CS insecure peer connected count=") for line in lines
        )
        or record.get("connection_events_observed") != 1
        or record.get("discovery_events_observed") != sum(
            line == "CS insecure RAS discovered" for line in lines
        )
        or record.get("discovery_events_observed") != 1
        or record.get("unexpected_disconnects") != 0
        or counters != list(range(1, 21))
        or timestamps != record.get("read_timestamps_ms")
        or any(right - left < 50 for left, right in zip(timestamps, timestamps[1:]))
        or any(any(marker in line for marker in bad) for line in lines)
        or sum(line == "CS insecure retry requested" for line in lines) != 19
        or not any(
            line.startswith("CS insecure peer disconnected reason=")
            or line == "CS insecure stop complete"
            for line in lines
        )
        or not any(
            line == "CS reflector disconnected"
            for line in record.get("reflector_lines", [])
        )
        or any("CS reflector secure L2" in line
               for line in record.get("reflector_lines", []))
        or cleanup["client"]["stop"] != "PASS"
        or cleanup["client"]["disconnect"] != "PASS"
        or cleanup["reflector"]["disconnect"] != "PASS"
    ):
        raise CsNegativeAttestationFailure("insecure same-ACL raw 의미 또는 분모가 다릅니다")
    cycles = record.get("cycles")
    if (
        not isinstance(cycles, list)
        or [row.get("cycle") for row in cycles] != list(range(1, 21))
        or len(record.get("att_errors", [])) != 20
    ):
        raise CsNegativeAttestationFailure("insecure typed cycle 분모가 다릅니다")
    return _records(spec)


def build_wrong_peer_records(
    record: dict[str, Any], cleanup: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    """! @brief third peer를 고르지 않은 실제 RAS procedure 100회를 재도출합니다. """

    spec = PHASES["wrong_peer"]
    _cleanup_rows(cleanup, spec)
    raw_pattern = re.compile(
        r"CS_RAW counter=(\d+) local=(\d+) peer=(\d+) .*valid_rtt=([1-9]\d*)"
    )
    raw = []
    for line in record.get("initiator_lines", []):
        match = raw_pattern.fullmatch(line)
        if match is not None:
            raw.append(tuple(map(int, match.groups())))
    if (
        record.get("test") != "same_name_wrong_service_third_peer"
        or record.get("procedures") != 100
        or [row[0] for row in raw] != list(range(100))
        or any(row[1] != row[2] for row in raw)
        or not any(
            line == "CS wrong peer advertising"
            for line in record.get("wrong_peer_lines", [])
        )
        or any(
            "wrong peer connected" in line
            for line in record.get("wrong_peer_lines", [])
        )
        or not any(
            line == "CS reflector connected"
            for line in record.get("reflector_lines", [])
        )
        or not any(
            line == "CS procedures stop requested"
            for line in record.get("initiator_lines", [])
        )
        or not any(
            line == "CS initiator disconnected"
            for line in record.get("initiator_lines", [])
        )
        or not any(
            line == "CS reflector disconnected"
            for line in record.get("reflector_lines", [])
        )
        or not all(
            cleanup[role]["serial_close"] == "PASS" for role in spec.roles
        )
        or cleanup["initiator"]["stop"] != "PASS"
        or cleanup["initiator"]["disconnect"] != "PASS"
        or cleanup["reflector"]["disconnect"] != "PASS"
        or cleanup["wrong_peer"]["disconnect"] != "NOT_APPLICABLE"
    ):
        raise CsNegativeAttestationFailure("wrong-peer raw 의미 또는 분모가 다릅니다")
    return _records(spec)


def build_missing_service_records(
    record: dict[str, Any], cleanup: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    """! @brief Ranging UUID만 가진 peer의 GATT 거부 20회와 무진행을 재도출합니다. """

    spec = PHASES["missing_service"]
    _cleanup_rows(cleanup, spec)
    initiator_lines = record.get("initiator_lines", [])
    peer_lines = record.get("missing_service_peer_lines", [])
    failures = sum(line == "CS initiator failed: -2" for line in initiator_lines)
    connections = sum(line == "CS missing service connected" for line in peer_lines)
    if (
        record.get("test") != "advertised_ranging_uuid_without_gatt_service"
        or record.get("cycles_expected") != 20
        or record.get("cycles_rejected") != 20
        or failures != 20
        or connections < 20
        or any(
            line.startswith("CS_RAW counter=") or line == "CS procedures requested"
            for line in initiator_lines
        )
        or record.get("initiator_disconnects", 0) < 20
        or record.get("peer_disconnects", 0) < 20
        or cleanup["initiator"]["disconnect"] != "PASS"
        or cleanup["missing_service_peer"]["disconnect"] != "PASS"
    ):
        raise CsNegativeAttestationFailure(
            "missing-service raw 의미 또는 분모가 다릅니다"
        )
    return _records(spec)


def make_attestation(
    phase: ProgramPhase,
    source_revision: str,
    exact_program: dict[str, dict[str, Any]],
    cycle_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """! @brief 한 phase의 실제 분모만 독립 native attestation으로 만듭니다. """

    spec = phase.spec
    if len(cycle_records) != spec.cycles:
        raise CsNegativeAttestationFailure("phase cycle 분모가 다릅니다")
    return dispatch_attestation(
        spec.identifier,
        source_revision,
        spec.cycles,
        spec.semantics,
        spec.roles,
        exact_program,
        cycle_records=cycle_records,
    )


def phase_contract(phase: ProgramPhase) -> dict[str, Any]:
    """! @brief aggregate adapter가 사용할 독립 phase 계약을 반환합니다. """

    return {
        "id": phase.spec.identifier,
        "roles": list(phase.spec.roles),
        "cycles": phase.spec.cycles,
        "semantics": list(phase.spec.semantics),
        "board_revision": phase.board_revision,
    }
