#!/usr/bin/env python3
"""! @brief M30 legacy HIL의 원시 의미와 exact program 증적을 결합합니다. """

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent

from m33_sdk_risk_common import (  # noqa: E402
    copy_program_inputs,
    dispatch_attestation,
    exact_program_evidence,
    intel_hex_ranges,
    readback_programmed_images,
    require_exact_clean_source,
    reserve_sidecars,
    validate_programming_receipt,
)


ROLES = ("peripheral", "central")
PAIR_SEMANTICS = ("five_io_capabilities", "mitm_policy", "key_identity", "cleanup")
OOB_SEMANTICS = ("wired_oob", "mismatch_rejection", "mitm", "cleanup")
BOND_SEMANTICS = (
    "bond_migration",
    "privacy_rotation",
    "stale_key",
    "reboot_restore",
    "cleanup",
)
PROFILE_SEMANTICS = ("seven_profiles", "typed_payload", "security", "cleanup")
DFU_SEMANTICS = (
    "signed_update",
    "wrong_key_rejection",
    "rollback",
    "secondary_slot_cleanup",
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
PHASE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


class M30AttestationFailure(RuntimeError):
    """! @brief M30 원시 분모 또는 program provenance 불일치입니다. """


@dataclass(frozen=True)
class ProgramPhase:
    """! @brief 실제 program 입력을 인접 sidecar byte에 예약한 phase입니다. """

    name: str
    roles: tuple[str, ...]
    images: dict[str, Path]
    build_records: dict[str, dict[str, str]]
    build_record_paths: dict[str, Path]
    sidecars: dict[str, dict[str, Path]]


def _digest(path: Path) -> str:
    """! @brief 파일 전체 byte의 SHA-256을 반환합니다. """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_hash(board_id: str) -> str:
    """! @brief dispatcher와 같은 정규화로 raw probe ID를 SHA-256 처리합니다. """

    normalized = board_id.strip().lower()
    if not normalized or not normalized.isascii():
        raise M30AttestationFailure("probe ID가 비어 있거나 ASCII가 아닙니다")
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def _phase_native_path(evidence_path: Path, phase: str) -> Path:
    """! @brief phase별 sidecar 이름의 기준이 되는 인접 JSON 경로를 만듭니다. """

    if PHASE_PATTERN.fullmatch(phase) is None:
        raise M30AttestationFailure("program phase 이름이 안전하지 않습니다")
    return evidence_path.with_name(f"{evidence_path.stem}.{phase}.json")


def prepare_program_phase(
    evidence_path: Path,
    phase: str,
    roles: tuple[str, ...],
    images: dict[str, Path],
    build_records: dict[str, dict[str, str]],
    *,
    build_record_paths: dict[str, Path] | None = None,
    overwrite: bool = False,
) -> ProgramPhase:
    """! @brief 검증할 image·build record 실제 byte를 실행 전에 보존합니다. """

    if not roles or set(images) != set(roles) or set(build_records) != set(roles):
        raise M30AttestationFailure("program phase role 분모가 다릅니다")
    native_path = _phase_native_path(evidence_path, phase)
    if overwrite:
        for role in roles:
            for suffix in ("image.hex", "build-record", "readback.json"):
                path = native_path.with_name(
                    f"{native_path.stem}.{role}.{suffix}"
                )
                if path.exists():
                    if not path.is_file():
                        raise M30AttestationFailure(
                            "program phase sidecar가 일반 파일이 아닙니다"
                        )
                    path.unlink()
    sidecars = reserve_sidecars(native_path, roles)
    if build_record_paths is None:
        copied = copy_program_inputs(images, sidecars)
        resolved_records = {
            role: images[role].with_suffix(".nu54-build.json")
            for role in roles
        }
        for role in roles:
            if not resolved_records[role].is_file():
                resolved_records[role] = (
                    images[role].parent.parent / "nucode_arduino_core_build.yml"
                )
    else:
        if set(build_record_paths) != set(roles):
            raise M30AttestationFailure("program phase build-record role 분모가 다릅니다")
        resolved_records = {
            role: Path(build_record_paths[role]).resolve() for role in roles
        }
        copied = {}
        for role in roles:
            image = images[role].resolve()
            record = resolved_records[role]
            if not image.is_file() or not record.is_file():
                raise M30AttestationFailure("program phase 입력 byte가 없습니다")
            shutil.copyfile(image, sidecars[role]["image"])
            shutil.copyfile(record, sidecars[role]["build_record"])
            copied[role] = {
                "image_sha256": _digest(sidecars[role]["image"]),
                "build_record_sha256": _digest(sidecars[role]["build_record"]),
            }
    for role in roles:
        record_digest = build_records[role].get("record_sha256", "")
        if (
            copied[role]["image_sha256"] != _digest(images[role])
            or SHA256_PATTERN.fullmatch(record_digest) is None
            or copied[role]["build_record_sha256"] != record_digest
        ):
            raise M30AttestationFailure(f"{phase}/{role} program 입력 byte가 다릅니다")
    return ProgramPhase(
        phase,
        roles,
        images,
        build_records,
        resolved_records,
        sidecars,
    )


def complete_program_phase(
    repository: Path,
    source_revision: str,
    phase: ProgramPhase,
    probe_ids: dict[str, str],
    flash_results: dict[str, tuple[str, str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """! @brief sector flash 결과와 모든 HEX range live readback을 phase에 결합합니다. """

    if set(probe_ids) != set(phase.roles) or set(flash_results) != set(phase.roles):
        raise M30AttestationFailure("program phase probe·flash role 분모가 다릅니다")
    require_exact_clean_source(repository, source_revision)
    hashes = {role: probe_hash(probe_ids[role]) for role in phase.roles}
    readbacks, receipt = readback_programmed_images(
        probe_ids, hashes, phase.images, phase.sidecars
    )
    validate_programming_receipt(receipt, phase.roles, readbacks)
    flash_records: dict[str, dict[str, str]] = {}
    for role in phase.roles:
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
            raise M30AttestationFailure(f"{phase.name}/{role} sector flash 결과가 없습니다")
        flash_records[role] = {"mode": result[0], "bytes": result[1]}
    exact = exact_program_evidence(
        phase.roles,
        hashes,
        phase.sidecars,
        flash_records,
        phase.build_records,
        readbacks,
    )
    return exact, {
        "phase": phase.name,
        "hardware": [
            {
                "role": role,
                **exact[role],
                "build_identity": dict(phase.build_records[role]),
            }
            for role in phase.roles
        ],
    }


def _rows(capture: bytes, protocol: str) -> list[tuple[str, dict[str, str]]]:
    """! @brief raw transcript의 protocol record를 중복 field 없이 파싱합니다. """

    output: list[tuple[str, dict[str, str]]] = []
    prefix = protocol + "|"
    for raw in capture.splitlines():
        try:
            line = raw.decode("ascii")
        except UnicodeDecodeError as error:
            raise M30AttestationFailure("transcript에 비 ASCII byte가 있습니다") from error
        if not line.startswith(prefix):
            continue
        pieces = line.split("|")
        if len(pieces) < 3 or pieces[2] == "FAIL":
            raise M30AttestationFailure("target FAIL 또는 잘린 protocol record입니다")
        fields: dict[str, str] = {}
        for piece in pieces[3:]:
            if "=" not in piece:
                continue
            key, value = piece.split("=", 1)
            if not key or key in fields:
                raise M30AttestationFailure("protocol field가 비었거나 중복됐습니다")
            fields[key] = value
        output.append((pieces[2], fields))
    if not output:
        raise M30AttestationFailure("typed protocol transcript가 비었습니다")
    return output


def _cycle_records(count: int, semantics: tuple[str, ...]) -> list[dict[str, Any]]:
    """! @brief 검증을 통과한 실제 분모만 dispatcher cycle record로 변환합니다. """

    statuses = {token: "PASS" for token in semantics}
    return [
        {"cycle": cycle, "status": "PASS", "semantics": dict(statuses)}
        for cycle in range(1, count + 1)
    ]


def _typed_denominator(
    campaign_id: str,
    total: int,
    groups: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """! @brief 서로 다른 phase 분모를 합성 cycle로 평탄화하지 않고 보존합니다. """

    normalized = [dict(group) for group in groups]
    if total <= 0 or not normalized:
        raise M30AttestationFailure("typed denominator가 비었습니다")
    for group in normalized:
        if (
            set(group) != {"name", "unit", "count"}
            or not isinstance(group["name"], str)
            or not isinstance(group["unit"], str)
            or not isinstance(group["count"], int)
            or group["count"] <= 0
        ):
            raise M30AttestationFailure("typed denominator group이 잘못됐습니다")
    return {
        "schema_version": 1,
        "kind": "m30_typed_denominator",
        "campaign_id": campaign_id,
        "total_primary_cycles": total,
        "groups": normalized,
    }


def pair_typed_denominator() -> dict[str, Any]:
    """! @brief capability별 10회와 전체 50회를 별도 group으로 보존합니다. """

    return _typed_denominator(
        "m30_pair",
        50,
        [
            {"name": name, "unit": "pairing", "count": 10}
            for name in (
                "no_input_output",
                "display_keyboard",
                "keyboard_display",
                "display_yes_no",
                "keyboard_display_full",
            )
        ],
    )


def oob_typed_denominator() -> dict[str, Any]:
    """! @brief 유선 OOB pairing 20회의 실제 분모를 반환합니다. """

    return _typed_denominator(
        "m30_oob", 20, [{"name": "wired_oob", "unit": "pairing", "count": 20}]
    )


def bond_typed_denominator() -> dict[str, Any]:
    """! @brief bond campaign의 서로 다른 event 분모를 보존합니다. """

    return _typed_denominator(
        "m30_bond",
        20,
        [
            {"name": "bonded_reconnect", "unit": "reconnect", "count": 20},
            {"name": "metadata_migration", "unit": "migration", "count": 1},
            {"name": "privacy_rotation", "unit": "rotation", "count": 3},
            {"name": "stale_key_rejection", "unit": "attempt", "count": 1},
            {"name": "final_reset", "unit": "role", "count": 2},
        ],
    )


def profile_typed_denominator() -> dict[str, Any]:
    """! @brief profile operation·catalog·security·cleanup 분모를 보존합니다. """

    return _typed_denominator(
        "m30_profiles",
        100,
        [
            {"name": "operation_round", "unit": "round", "count": 100},
            {"name": "profile_catalog", "unit": "profile", "count": 7},
            {"name": "encrypted_link", "unit": "role", "count": 2},
            {"name": "base_restore", "unit": "role", "count": 2},
        ],
    )


def dfu_typed_denominator() -> dict[str, Any]:
    """! @brief DFU 정상·5종 부정·rollback·cleanup 분모를 각각 보존합니다. """

    return _typed_denominator(
        "m30_dfu",
        10,
        [
            {"name": "signed_update", "unit": "update", "count": 10},
            {"name": "unsigned_rejection", "unit": "attempt", "count": 20},
            {"name": "wrong_key_rejection", "unit": "attempt", "count": 20},
            {"name": "corrupt_rejection", "unit": "attempt", "count": 20},
            {"name": "truncated_rejection", "unit": "attempt", "count": 20},
            {"name": "downgrade_rejection", "unit": "attempt", "count": 20},
            {"name": "rollback", "unit": "attempt", "count": 1},
            {"name": "secondary_slot_cleanup", "unit": "range", "count": 1},
            {"name": "base_restore", "unit": "role", "count": 2},
        ],
    )


def _validate_serial_cleanup(cleanup: dict[str, str]) -> None:
    """! @brief 두 역할의 실제 context close 결과가 모두 PASS인지 검사합니다. """

    if set(cleanup) != set(ROLES) or any(
            value != "PASS" for value in cleanup.values()):
        raise M30AttestationFailure("serial cleanup 결과가 완전하지 않습니다")


def _matching(
    rows: list[tuple[str, dict[str, str]]],
    kind: str,
    required: dict[str, str],
) -> list[dict[str, str]]:
    """! @brief kind와 필수 field가 모두 같은 raw record를 반환합니다. """

    return [
        fields
        for observed_kind, fields in rows
        if observed_kind == kind
        and all(fields.get(key) == value for key, value in required.items())
    ]


def _value(row: Any, name: str, legacy: str | None = None) -> Any:
    """! @brief 실행 dataclass와 직렬화 JSON에서 같은 typed field를 읽습니다. """

    if isinstance(row, dict):
        if name in row:
            return row[name]
        if legacy is not None:
            return row.get(legacy)
        return None
    return getattr(row, name)


def build_pair_cycle_records(
    cases: Sequence[dict[str, Any]],
    captures: dict[str, bytes],
    cleanup_records: Sequence[dict[str, str]],
) -> list[dict[str, Any]]:
    """! @brief 5 IO capability의 raw CLEAR·START·PASS 50회를 재도출합니다. """

    expected = (
        ("no_input_output", "just_works", 2, 0, 0),
        ("display_keyboard", "passkey_entry", 4, 1, 2),
        ("keyboard_display", "passkey_entry", 4, 2, 1),
        ("display_yes_no", "numeric_comparison", 4, 3, 3),
        ("keyboard_display_full", "numeric_comparison", 4, 4, 4),
    )
    if (len(cases) != len(expected) or set(captures) != set(ROLES) or
            len(cleanup_records) != len(expected)):
        raise M30AttestationFailure("pair capability 또는 role 분모가 다릅니다")
    for cleanup in cleanup_records:
        _validate_serial_cleanup(cleanup)
    parsed = {role: _rows(captures[role], "M30PAIR|1") for role in ROLES}
    nonces: set[str] = set()
    for case, contract in zip(cases, expected, strict=True):
        name, method, level, peripheral_io, central_io = contract
        if (
            case.get("case") != name
            or case.get("method") != method
            or case.get("peripheral_io") != peripheral_io
            or case.get("central_io") != central_io
            or not isinstance(case.get("rounds"), list)
            or len(case["rounds"]) != 10
        ):
            raise M30AttestationFailure("pair capability typed 결과가 다릅니다")
        for round_index, typed in enumerate(case["rounds"], 1):
            if (
                typed.get("round") != round_index
                or typed.get("method") != method
                or typed.get("security_level") != level
                or typed.get("key_size") != 16
                or typed.get("unexpected_auth_failures") != 0
                or SHA256_PATTERN.fullmatch(typed.get("nonce_sha256", "")) is None
            ):
                raise M30AttestationFailure("pair round typed 결과가 다릅니다")
            per_role: list[str] = []
            for role, io_value in (
                ("peripheral", peripheral_io),
                ("central", central_io),
            ):
                common = {"role": role, "case": name, "round": str(round_index)}
                passes = _matching(parsed[role], "PASS", common)
                starts = _matching(parsed[role], "STARTED", common)
                clears = _matching(parsed[role], "CLEARED", common)
                expected_clears = 2 if round_index == 10 else 1
                if (
                    len(passes) != 1
                    or len(starts) != 1
                    or len(clears) != expected_clears
                ):
                    raise M30AttestationFailure("pair raw round record 분모가 다릅니다")
                passed = passes[0]
                if (
                    passed.get("method") != method
                    or passed.get("level") != str(level)
                    or passed.get("key_size") != "16"
                    or passed.get("paired") != "1"
                    or passed.get("unexpected_auth_failures") != "0"
                    or starts[0].get("io") != str(io_value)
                    or clears[0].get("bond_count") != "0"
                ):
                    raise M30AttestationFailure("pair raw 보안·cleanup 의미가 다릅니다")
                nonce = passed.get("nonce", "")
                if (
                    re.fullmatch(r"[0-9a-f]{32}", nonce) is None
                    or starts[0].get("nonce") != nonce
                    or any(clear.get("nonce") != nonce for clear in clears)
                ):
                    raise M30AttestationFailure("pair raw nonce chain이 다릅니다")
                per_role.append(nonce)
            if (
                len(set(per_role)) != 1
                or hashlib.sha256(per_role[0].encode("ascii")).hexdigest()
                != typed["nonce_sha256"]
                or per_role[0] in nonces
            ):
                raise M30AttestationFailure("pair round identity가 중복되거나 다릅니다")
            nonces.add(per_role[0])
    if len(nonces) != 50:
        raise M30AttestationFailure("pair 실제 cycle 분모가 50이 아닙니다")
    return _cycle_records(50, PAIR_SEMANTICS)


def build_oob_cycle_records(
    rounds: Sequence[dict[str, Any]],
    captures: dict[str, bytes],
    cleanup: dict[str, str],
) -> list[dict[str, Any]]:
    """! @brief 유선 OOB frame·CRC mismatch·L4 PASS 20회를 재도출합니다. """

    if len(rounds) != 20 or set(captures) != set(ROLES):
        raise M30AttestationFailure("OOB cycle 또는 role 분모가 다릅니다")
    _validate_serial_cleanup(cleanup)
    parsed = {role: _rows(captures[role], "M30OOB|1") for role in ROLES}
    nonces: set[str] = set()
    for index, typed in enumerate(rounds, 1):
        if (
            typed.get("round") != index
            or typed.get("security_level") != 4
            or typed.get("key_size") != 16
            or typed.get("mismatch_attempts") != 2
            or typed.get("mismatch_accepts") != 0
        ):
            raise M30AttestationFailure("OOB typed round가 다릅니다")
        per_role: list[str] = []
        for role in ROLES:
            common = {"role": role, "round": str(index)}
            kinds = {
                kind: _matching(parsed[role], kind, common)
                for kind in ("CLEARED", "LOCAL", "REJECTED", "ARMED", "STARTED", "PASS")
            }
            if any(
                len(values) != (2 if kind == "CLEARED" and index == 20 else 1)
                for kind, values in kinds.items()
            ):
                raise M30AttestationFailure("OOB raw round record 분모가 다릅니다")
            nonce = kinds["PASS"][0].get("nonce", "")
            if any(
                item.get("nonce") != nonce
                for values in kinds.values()
                for item in values
            ):
                raise M30AttestationFailure("OOB raw nonce chain이 다릅니다")
            frame_digest = typed[f"{role}_frame_sha256"]
            if (
                SHA256_PATTERN.fullmatch(str(frame_digest)) is None
                or re.fullmatch(r"[0-9a-f]{32}", nonce) is None
                or any(row.get("bond_count") != "0" for row in kinds["CLEARED"])
                or kinds["LOCAL"][0].get("frame_sha256") != frame_digest
                or kinds["REJECTED"][0].get("class") != "crc"
                or kinds["PASS"][0].get("method") != "oob"
                or kinds["PASS"][0].get("level") != "4"
                or kinds["PASS"][0].get("key_size") != "16"
                or kinds["PASS"][0].get("sc") != "1"
                or kinds["PASS"][0].get("oob") != "1"
            ):
                raise M30AttestationFailure("OOB raw 보안·mismatch·cleanup 의미가 다릅니다")
            per_role.append(nonce)
        if (
            len(set(per_role)) != 1
            or hashlib.sha256(per_role[0].encode("ascii")).hexdigest()
            != typed.get("nonce_sha256")
            or per_role[0] in nonces
        ):
            raise M30AttestationFailure("OOB round identity가 중복되거나 다릅니다")
        nonces.add(per_role[0])
    return _cycle_records(20, OOB_SEMANTICS)


def build_bond_cycle_records(
    results: dict[str, Any],
    captures: dict[str, bytes],
    nonce: str,
    core_revision: str,
    cleanup: dict[str, str],
) -> list[dict[str, Any]]:
    """! @brief migration·RPA·stale 거부와 20 reconnect raw record를 재도출합니다. """

    if set(results) != set(ROLES) or set(captures) != set(ROLES):
        raise M30AttestationFailure("bond result 또는 role 분모가 다릅니다")
    _validate_serial_cleanup(cleanup)
    parsed = {role: _rows(captures[role], "M30BOND|1") for role in ROLES}
    for role in ROLES:
        typed = results[role]
        if (
            _value(typed, "role") not in (None, role)
            or _value(typed, "reconnects", "bonded_reconnects") != 20
            or _value(typed, "migration", "metadata_migrations") != 1
            or _value(typed, "stale_key_accepts") != 0
            or _value(typed, "new_pairings") != 0
            or _value(typed, "final_bond_count") not in (0, 1)
            or (role == "peripheral" and
                _value(typed, "rotations", "privacy_rotations") != 3)
            or (role == "central" and
                _value(typed, "rotations", "privacy_rotations") != 0)
        ):
            raise M30AttestationFailure("bond typed 결과가 다릅니다")
        identity = {"role": role, "nonce": nonce, "core": core_revision}
        reconnects = _matching(parsed[role], "RECONNECT", identity)
        if [row.get("count") for row in reconnects] != [str(value) for value in range(1, 21)]:
            raise M30AttestationFailure("bond raw reconnect 20회가 다릅니다")
        result_fields = {
            **identity,
            "bonded_reconnects": "20",
            "migration": "1",
            "stale_key_accepts": "0",
            "new_pairings": "0",
            "bond_count": str(_value(typed, "final_bond_count")),
            "callback_context": "pass",
        }
        if role == "peripheral":
            result_fields["privacy_rotations"] = "3"
        required = (
            ("MIGRATE_REBOOT", {**identity, "schema": "1", "warm": "1"}),
            ("STALE_REJECTED", {**identity, "accepted": "0"}),
            ("RESULT", result_fields),
        )
        if any(len(_matching(parsed[role], kind, fields)) != 1 for kind, fields in required):
            raise M30AttestationFailure("bond raw migration·stale·RESULT가 다릅니다")
        resetting = _matching(
            parsed[role],
            "RESETTING",
            {"role": role, "warm": "1", "core": core_revision},
        )
        if len(resetting) != 2:
            raise M30AttestationFailure("bond initial/final RESETTING 분모가 다릅니다")
    erased = _matching(
        parsed["peripheral"],
        "STALE_ERASED",
        {"role": "peripheral", "bond_count": "0", "nonce": nonce, "core": core_revision},
    )
    rotations = _matching(
        parsed["peripheral"],
        "RPA",
        {"role": "peripheral", "rotations": "3", "nonce": nonce, "core": core_revision},
    )
    if len(erased) != 1 or len(rotations) != 1:
        raise M30AttestationFailure("bond raw privacy 또는 stale cleanup이 다릅니다")
    return _cycle_records(20, BOND_SEMANTICS)


def build_profile_cycle_records(
    results: dict[str, Any],
    captures: dict[str, bytes],
    nonce: str,
    core_revision: str,
    cleanup: dict[str, str],
) -> list[dict[str, Any]]:
    """! @brief 두 역할의 exact 7-profile RESULT에서 100 operation cycle을 재도출합니다. """

    if set(results) != set(ROLES) or set(captures) != set(ROLES):
        raise M30AttestationFailure("profile result 또는 role 분모가 다릅니다")
    _validate_serial_cleanup(cleanup)
    parsed = {role: _rows(captures[role], "M30PROFILE|1") for role in ROLES}
    for role in ROLES:
        typed = results[role]
        if (
            _value(typed, "role") not in (None, role)
            or _value(typed, "catalog") != 7
            or _value(typed, "operations") != 100
            or _value(typed, "payload_errors") != 0
            or _value(typed, "driver_errors") != 0
        ):
            raise M30AttestationFailure("profile typed 결과가 다릅니다")
        identity = {"role": role, "nonce": nonce, "core": core_revision}
        begins = _matching(parsed[role], "BEGIN", identity)
        results_raw = _matching(parsed[role], "RESULT", identity)
        security_gate = _matching(
            parsed[role],
            "RUNNING" if role == "peripheral" else "READY",
            identity,
        )
        if len(begins) != 1 or len(results_raw) != 1 or len(security_gate) != 1:
            raise M30AttestationFailure("profile raw BEGIN·RESULT가 다릅니다")
        raw = results_raw[0]
        if raw.get("catalog") != "7" or raw.get("operations") != "100":
            raise M30AttestationFailure("profile raw catalog·operation 분모가 다릅니다")
        expected_errors = (
            {"driver_errors": "0"}
            if role == "peripheral"
            else {"payload_errors": "0"}
        )
        if any(raw.get(key) != value for key, value in expected_errors.items()):
            raise M30AttestationFailure("profile raw payload·driver 오류가 있습니다")
    return _cycle_records(100, PROFILE_SEMANTICS)


def build_dfu_cycle_records(
    results: dict[str, Any],
    candidates: dict[str, Any],
    captures: dict[str, bytes],
    nonce: str,
    core_revision: str,
    cleanup: dict[str, str],
    secondary_cleanup: dict[str, Any],
) -> dict[str, Any]:
    """! @brief 서로 다른 DFU phase 분모를 평탄화하지 않고 strict 재도출합니다. """

    _validate_serial_cleanup(cleanup)
    if (
        secondary_cleanup.get("mode") != "nrf54l-rram-fill-verified"
        or secondary_cleanup.get("start") != 794624
        or secondary_cleanup.get("end_exclusive") != 1523712
        or secondary_cleanup.get("bytes") != 729088
        or secondary_cleanup.get("erase_value") != "0xff"
        or secondary_cleanup.get("verified_words") != 182272
        or secondary_cleanup.get("expected_sha256") != hashlib.sha256(
            b"\xff" * 729088
        ).hexdigest()
        or secondary_cleanup.get("observed_sha256") !=
        secondary_cleanup.get("expected_sha256")
        or secondary_cleanup.get("readback_backend") != "pyocd-live-target"
    ):
        raise M30AttestationFailure("DFU secondary slot cleanup readback이 다릅니다")
    positive = results.get("M30-DFU-01", {})
    negative = results.get("M30-DFU-NEG-01", {})
    classes = negative.get("classes", {})
    expected_classes = {"unsigned", "wrong_key", "corrupt", "truncated", "downgrade"}
    if (
        set(results) != {"M30-DFU-01", "M30-DFU-NEG-01"}
        or positive.get("status") != "passed"
        or positive.get("updates") != 10
        or not isinstance(positive.get("records"), list)
        or len(positive["records"]) != 10
        or positive.get("hash_mismatches") != 0
        or positive.get("unconfirmed_boots") != 0
        or negative.get("status") != "passed"
        or set(classes) != expected_classes
        or negative.get("invalid_accepts") != 0
        or negative.get("unconfirmed_first_boots") != 1
        or negative.get("rollback_accepts") != 0
        or negative.get("recovered_version") != [10, 0, 0, 0]
    ):
        raise M30AttestationFailure("DFU typed 정상·negative·rollback 결과가 다릅니다")
    positives = candidates.get("positive")
    negatives = candidates.get("negative")
    rollback = candidates.get("unconfirmed")
    all_rows = (
        positives + list(negatives.values()) + [rollback]
        if isinstance(positives, list)
        and isinstance(negatives, dict)
        and set(negatives) == expected_classes
        and isinstance(rollback, dict)
        else []
    )
    if len(positives or []) != 10 or len(all_rows) != 16 or any(
        not isinstance(row, dict)
        or SHA256_PATTERN.fullmatch(row.get("sha256", "")) is None
        or SHA256_PATTERN.fullmatch(row.get("image_hash", "")) is None
        or not isinstance(row.get("path"), str)
        or Path(row["path"]).name != row["path"]
        or not isinstance(row.get("class"), str)
        for row in all_rows
    ):
        raise M30AttestationFailure("DFU candidate byte identity 분모가 다릅니다")
    if len({row["sha256"] for row in all_rows}) != len(all_rows):
        raise M30AttestationFailure("DFU candidate byte identity가 중복됐습니다")
    if (
        [row.get("version") for row in positives]
        != [[index, 0, 0, 0] for index in range(1, 11)]
        or any(row.get("class") != "positive" for row in positives)
        or {
            name: (row.get("class"), row.get("version"))
            for name, row in negatives.items()
        } != {
            "unsigned": ("unsigned", [20, 0, 0, 0]),
            "wrong_key": ("wrong_key", [20, 0, 0, 1]),
            "corrupt": ("corrupt", [20, 0, 0, 2]),
            "truncated": ("truncated", [20, 0, 0, 3]),
            "downgrade": ("downgrade", [9, 0, 0, 0]),
        }
        or rollback.get("class") != "rollback"
        or rollback.get("version") != [11, 0, 0, 0]
    ):
        raise M30AttestationFailure("DFU candidate class·version identity가 다릅니다")
    for name, row in classes.items():
        if (
            row.get("attempts") != 20
            or row.get("invalid_accepts") != 0
            or row.get("state_rejects") != 0
            or row.get("boot_rejects") != 20
            or row.get("upload_requests", 0) <= 0
            or not isinstance(row.get("records"), list)
            or len(row["records"]) != 20
        ):
            raise M30AttestationFailure(f"DFU {name} negative 분모가 다릅니다")
        for attempt, record in enumerate(row["records"], 1):
            if (
                record.get("attempt") != attempt
                or record.get("class") != name
                or record.get("outcome") != "boot_rejected"
                or record.get("request_error_group") is not None
                or record.get("request_error_code") != 0
                or record.get("candidate_sha256") != negatives[name]["sha256"]
                or record.get("candidate_image_hash") !=
                negatives[name]["image_hash"]
                or record.get("recovered_version") != [10, 0, 0, 0]
                or record.get("active_candidate") is not False
            ):
                raise M30AttestationFailure(f"DFU {name} attempt raw state가 다릅니다")
    if set(captures) != set(ROLES):
        raise M30AttestationFailure("DFU transcript role 분모가 다릅니다")
    parsed = {role: _rows(captures[role], "M30DFU|1") for role in ROLES}
    for role in ROLES:
        links = _matching(
            parsed[role],
            "LINK",
            {"role": role, "nonce": nonce, "core": core_revision},
        )
        if not links or any(
            row.get("level") != "4"
            or row.get("key_size") != "16"
            or row.get("smp") != "1"
            for row in links
        ):
            raise M30AttestationFailure("DFU raw L4 SMP link 증거가 없습니다")
    for index, record in enumerate(positive["records"], 1):
        candidate = candidates["positive"][index - 1]
        if (
            record.get("update") != index
            or record.get("candidate_sha256") != candidate["sha256"]
            or record.get("candidate_image_hash") != candidate["image_hash"]
            or record.get("version") != [index, 0, 0, 0]
            or record.get("confirmed") is not True
            or record.get("active") is not True
        ):
            raise M30AttestationFailure("DFU positive typed record가 다릅니다")
    rollback_record = negative.get("rollback_record")
    if (
        not isinstance(rollback_record, dict)
        or rollback_record.get("candidate_sha256") != rollback["sha256"]
        or rollback_record.get("candidate_image_hash") != rollback["image_hash"]
        or rollback_record.get("first_boot_version") != [11, 0, 0, 0]
        or rollback_record.get("recovered_version") != [10, 0, 0, 0]
        or rollback_record.get("rollback_accepts") != 0
    ):
        raise M30AttestationFailure("DFU rollback typed record가 다릅니다")
    return dfu_typed_denominator()


def preserve_dfu_candidates(
    evidence_path: Path,
    positives: Sequence[Any],
    negatives: dict[str, Any],
    rollback: Any,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """! @brief ephemeral DFU candidate 16개의 실제 byte를 evidence 옆에 보존합니다. """

    expected_negative = ("unsigned", "wrong_key", "corrupt", "truncated", "downgrade")
    if len(positives) != 10 or tuple(negatives) != expected_negative:
        raise M30AttestationFailure("DFU candidate 분모가 다릅니다")

    def preserve(label: str, candidate_class: str, artifact: Any) -> dict[str, Any]:
        source = Path(artifact.path).resolve()
        destination = evidence_path.with_name(
            f"{evidence_path.stem}.dfu-candidate-{label}.bin"
        )
        if destination.exists():
            if not overwrite or not destination.is_file():
                raise M30AttestationFailure("DFU candidate sidecar 덮어쓰기를 거부합니다")
            destination.unlink()
        if not source.is_file():
            raise M30AttestationFailure("DFU candidate 원본 byte가 없습니다")
        shutil.copyfile(source, destination)
        digest = _digest(destination)
        image_hash = artifact.image_hash.hex()
        version = list(artifact.version)
        if (
            digest != artifact.sha256
            or SHA256_PATTERN.fullmatch(image_hash) is None
            or destination.stat().st_size != artifact.size
            or len(version) != 4
        ):
            raise M30AttestationFailure("DFU candidate sidecar identity가 다릅니다")
        return {
            "path": destination.name,
            "class": candidate_class,
            "size": destination.stat().st_size,
            "sha256": digest,
            "image_hash": image_hash,
            "version": version,
        }

    return {
        "positive": [
            preserve(f"positive-{index:02d}", "positive", artifact)
            for index, artifact in enumerate(positives, 1)
        ],
        "negative": {
            name: preserve(
                f"negative-{name.replace('_', '-')}", name, negatives[name]
            )
            for name in expected_negative
        },
        "unconfirmed": preserve("rollback-unconfirmed", "rollback", rollback),
    }


def _adjacent_record(
    native_path: Path,
    reference: dict[str, Any],
    label: str,
) -> Path:
    """! @brief basename reference를 native evidence 인접 실제 byte에 고정합니다. """

    if (
        not isinstance(reference, dict)
        or set(reference) != {"path", "sha256"}
        or not isinstance(reference.get("path"), str)
        or Path(reference["path"]).name != reference["path"]
        or SHA256_PATTERN.fullmatch(reference.get("sha256", "")) is None
    ):
        raise M30AttestationFailure(f"{label} reference가 잘못됐습니다")
    path = (native_path.parent / reference["path"]).resolve()
    if path.parent != native_path.parent.resolve() or not path.is_file():
        raise M30AttestationFailure(f"{label} 인접 byte가 없습니다")
    if _digest(path) != reference["sha256"]:
        raise M30AttestationFailure(f"{label} digest가 다릅니다")
    return path


def _mcuboot_candidate_identity(path: Path) -> tuple[list[int], str]:
    """! @brief 정상·손상·tail 절단 candidate의 header version과 SHA TLV를 읽습니다. """

    data = path.read_bytes()
    if len(data) < 32:
        raise M30AttestationFailure("DFU candidate header가 잘렸습니다")
    magic, _load, header_size, protected_size, image_size, _flags = \
        struct.unpack_from("<IIHHII", data, 0)
    if magic != 0x96F3B83D or header_size != 0x800:
        raise M30AttestationFailure("DFU candidate MCUboot header가 다릅니다")
    version = list(struct.unpack_from("<BBHI", data, 20))
    cursor = header_size + image_size
    if cursor + protected_size > len(data):
        raise M30AttestationFailure("DFU candidate protected TLV가 잘렸습니다")
    if protected_size:
        protected_magic, protected_total = struct.unpack_from("<HH", data, cursor)
        if protected_magic != 0x6908 or protected_total != protected_size:
            raise M30AttestationFailure("DFU candidate protected TLV가 다릅니다")
        cursor += protected_size
    if cursor + 4 > len(data):
        raise M30AttestationFailure("DFU candidate 일반 TLV header가 없습니다")
    tlv_magic, tlv_total = struct.unpack_from("<HH", data, cursor)
    if tlv_magic != 0x6907 or tlv_total < 4:
        raise M30AttestationFailure("DFU candidate 일반 TLV가 다릅니다")
    declared_end = cursor + tlv_total
    cursor += 4
    hashes: list[bytes] = []
    while cursor + 4 <= min(declared_end, len(data)):
        tlv_type, _pad, length = struct.unpack_from("<BBH", data, cursor)
        cursor += 4
        if cursor + length > len(data):
            break
        if tlv_type == 0x10:
            hashes.append(data[cursor : cursor + length])
        cursor += length
    if len(hashes) != 1 or len(hashes[0]) != 32:
        raise M30AttestationFailure("DFU candidate SHA-256 TLV가 다릅니다")
    return version, hashes[0].hex()


def validate_program_phases(
    native: dict[str, Any],
    native_path: Path,
    expected: dict[str, tuple[str, ...]],
) -> None:
    """! @brief 모든 phase의 image·build·sector program·live readback을 재검증합니다. """

    phases = native.get("program_phases")
    if not isinstance(phases, list) or len(phases) != len(expected):
        raise M30AttestationFailure("program phase 분모가 다릅니다")
    by_name = {
        phase.get("phase"): phase
        for phase in phases
        if isinstance(phase, dict)
    }
    if set(by_name) != set(expected):
        raise M30AttestationFailure("program phase 이름이 다릅니다")
    for phase_name, roles in expected.items():
        hardware = by_name[phase_name].get("hardware")
        if (
            not isinstance(hardware, list)
            or len(hardware) != len(roles)
            or {row.get("role") for row in hardware if isinstance(row, dict)} != set(roles)
        ):
            raise M30AttestationFailure(f"{phase_name} hardware role 분모가 다릅니다")
        for row in hardware:
            if set(row) != {
                "role", "probe_sha256", "image", "build_record", "flash", "readback",
                "build_identity",
            } or SHA256_PATTERN.fullmatch(row.get("probe_sha256", "")) is None:
                raise M30AttestationFailure(f"{phase_name} hardware schema가 다릅니다")
            image = _adjacent_record(native_path, row["image"], "program image")
            _adjacent_record(native_path, row["build_record"], "build record")
            readback_path = _adjacent_record(native_path, row["readback"], "readback")
            build = row["build_identity"]
            core_revision = native.get("core_revision")
            board_revision = native.get("board_revision")
            if (
                not isinstance(build, dict)
                or not isinstance(core_revision, str)
                or re.fullmatch(r"[0-9a-f]{40}", core_revision) is None
                or not isinstance(board_revision, str)
                or re.fullmatch(r"[0-9a-f]{40}", board_revision) is None
                or build.get("record_sha256") != row["build_record"]["sha256"]
                or build.get("core_revision") not in {
                    core_revision, core_revision[:12]
                }
                or build.get("board_revision") not in {
                    board_revision, board_revision[:12]
                }
                or build.get("ncs_revision") not in {
                    "99553055607b2e9885fbc80ccd11fa9da81c2df0",
                    "99553055607b",
                }
                or build.get("zephyr_revision") not in {
                    "bf801e4e3d19e1ffa76164346480cb7734dd2800",
                    "bf801e4e3d19",
                }
                or build.get("board") != "nrf54l15dk"
                or build.get("board_qualifiers") != "nrf54l15/cpuapp/nu54dk"
                or not isinstance(build.get("cxx_compiler"), str)
                or "14.3.0" not in build["cxx_compiler"]
            ):
                raise M30AttestationFailure(
                    f"{phase_name} build identity가 current source와 다릅니다"
                )
            if build.get("record_format") == "nu54-build-json":
                if build.get("toolchain_bundle_id") != "dcbdc366a1":
                    raise M30AttestationFailure(
                        f"{phase_name} Arduino toolchain identity가 다릅니다"
                    )
            elif (
                build.get("toolchain_variant") != "zephyr"
                or any(
                    SHA256_PATTERN.fullmatch(str(build.get(key, ""))) is None
                    for key in (
                        "core_source_sha256",
                        "application_source_sha256",
                        "board_source_sha256",
                    )
                )
            ):
                raise M30AttestationFailure(
                    f"{phase_name} native source digest가 없습니다"
                )
            flash = row["flash"]
            if (
                not isinstance(flash, dict)
                or flash.get("erase") != "sector"
                or flash.get("auto_unlock") is not False
                or flash.get("mass_erase") is not False
                or flash.get("automatic_recover") is not False
                or not str(flash.get("mode", "")).startswith("pyocd-sector")
                or not isinstance(flash.get("programmed_bytes"), int)
                or flash["programmed_bytes"] <= 0
            ):
                raise M30AttestationFailure(f"{phase_name} sector program receipt가 다릅니다")
            try:
                readback = json.loads(readback_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise M30AttestationFailure("readback sidecar를 읽지 못했습니다") from error
            ranges = readback.get("ranges")
            expected_ranges = [
                {
                    "start": start,
                    "length": len(raw),
                    "expected_sha256": hashlib.sha256(raw).hexdigest(),
                }
                for start, raw in intel_hex_ranges(image)
            ]
            pre_state = readback.get("pre_state")
            if (
                readback.get("schema_version") != 1
                or readback.get("kind") != "m33_exact_program_readback"
                or readback.get("status") != "PASS"
                or readback.get("role") != row["role"]
                or readback.get("probe_sha256") != row["probe_sha256"]
                or readback.get("image_sha256") != _digest(image)
                or readback.get("backend") != "pyocd-live-target"
                or readback.get("halted") is not True
                or pre_state not in {"RUNNING", "HALTED"}
                or readback.get("post_state") != pre_state
                or readback.get("restored") is not True
                or readback.get("resumed") is not (pre_state == "RUNNING")
                or not isinstance(ranges, list)
                or len(ranges) != len(expected_ranges)
                or any(
                    not isinstance(item, dict)
                    or item.get("status") != "PASS"
                    or item.get("expected_sha256") != item.get("observed_sha256")
                    or {
                        "start": item.get("start"),
                        "length": item.get("length"),
                        "expected_sha256": item.get("expected_sha256"),
                    } != expected_range
                    for item, expected_range in zip(
                        ranges, expected_ranges, strict=True
                    )
                )
            ):
                raise M30AttestationFailure(f"{phase_name} live readback이 다릅니다")


def _transcript_bytes(native: dict[str, Any], native_path: Path) -> dict[str, bytes]:
    """! @brief role transcript reference와 실제 인접 byte를 결합합니다. """

    records = native.get("transcripts")
    if not isinstance(records, dict) or set(records) != set(ROLES):
        raise M30AttestationFailure("transcript role 분모가 다릅니다")
    captures: dict[str, bytes] = {}
    for role in ROLES:
        record = records[role]
        if (
            not isinstance(record, dict)
            or set(record) != {"name", "size", "sha256"}
            or Path(str(record.get("name", ""))).name != record.get("name")
            or SHA256_PATTERN.fullmatch(str(record.get("sha256", ""))) is None
        ):
            raise M30AttestationFailure("transcript reference가 잘못됐습니다")
        path = (native_path.parent / record["name"]).resolve()
        if path.parent != native_path.parent.resolve() or not path.is_file():
            raise M30AttestationFailure("transcript 인접 byte가 없습니다")
        raw = path.read_bytes()
        if len(raw) != record["size"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise M30AttestationFailure("transcript byte identity가 다릅니다")
        captures[role] = raw
    return captures


def _require_target_cleanup(cleanup: Any, expected: str) -> None:
    """! @brief 두 역할의 target 종료 receipt가 실제 명령 결과인지 검사합니다. """

    if (
        not isinstance(cleanup, dict)
        or set(cleanup) != set(ROLES)
        or any(cleanup[role] != expected for role in ROLES)
    ):
        raise M30AttestationFailure("target cleanup receipt가 다릅니다")


def _session_identity(captures: dict[str, bytes], protocol: str) -> tuple[str, str]:
    """! @brief 두 role raw record가 공유하는 단일 nonce·revision을 반환합니다. """

    identities: set[tuple[str, str]] = set()
    for role in ROLES:
        for _kind, fields in _rows(captures[role], protocol):
            nonce = fields.get("nonce")
            core = fields.get("core")
            if nonce is not None and core is not None:
                identities.add((nonce, core))
    if len(identities) != 1:
        raise M30AttestationFailure("raw session nonce·revision이 단일 값이 아닙니다")
    nonce, core = next(iter(identities))
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None or re.fullmatch(
        r"[0-9a-f]{40}", core
    ) is None:
        raise M30AttestationFailure("raw session identity 형식이 다릅니다")
    return nonce, core


def validate_m30_native_evidence(
    campaign_id: str,
    native: dict[str, Any],
    native_path: Path,
) -> dict[str, Any]:
    """! @brief acceptance가 호출할 M30 campaign별 순수 raw validator입니다. """

    captures = _transcript_bytes(native, native_path)
    if campaign_id == "m30_pair":
        expected = {
            f"pair-{name}": ROLES
            for name in (
                "no_io",
                "display_keyboard",
                "keyboard_display",
                "yes_no",
                "keyboard_display_full",
            )
        }
        validate_program_phases(native, native_path, expected)
        cleanup_rows = native.get("cleanup", [])
        if not isinstance(cleanup_rows, list) or len(cleanup_rows) != 5:
            raise M30AttestationFailure("pair cleanup phase 분모가 다릅니다")
        for row in cleanup_rows:
            _require_target_cleanup(row.get("target"), "CLEAR_ACK")
        records = build_pair_cycle_records(
            native.get("cases", {}),
            captures,
            [row.get("serial", {}) for row in cleanup_rows],
        )
        if records != native.get("dispatch_cycle_records"):
            raise M30AttestationFailure("pair dispatch cycle 재도출이 다릅니다")
        denominator = pair_typed_denominator()
    elif campaign_id == "m30_oob":
        validate_program_phases(native, native_path, {"oob": ROLES})
        _require_target_cleanup(native.get("cleanup", {}).get("target"), "CLEAR_ACK")
        records = build_oob_cycle_records(
            native.get("rounds", {}), captures, native.get("cleanup", {}).get("serial", {})
        )
        if records != native.get("dispatch_cycle_records"):
            raise M30AttestationFailure("OOB dispatch cycle 재도출이 다릅니다")
        denominator = oob_typed_denominator()
    elif campaign_id == "m30_bond":
        validate_program_phases(native, native_path, {"bond": ROLES})
        _require_target_cleanup(
            native.get("cleanup", {}).get("target"), "RESET_CLEAR_ACK"
        )
        nonce, core = _session_identity(captures, "M30BOND|1")
        records = build_bond_cycle_records(
            native.get("results", {}), captures, nonce, core,
            native.get("cleanup", {}).get("serial", {}),
        )
        if records != native.get("dispatch_cycle_records"):
            raise M30AttestationFailure("bond dispatch cycle 재도출이 다릅니다")
        denominator = bond_typed_denominator()
    elif campaign_id == "m30_profiles":
        validate_program_phases(native, native_path, {"profiles": ROLES})
        _require_target_cleanup(
            native.get("cleanup", {}).get("target"), "SECTOR_REPROGRAM_RESET"
        )
        nonce, core = _session_identity(captures, "M30PROFILE|1")
        records = build_profile_cycle_records(
            native.get("results", {}), captures, nonce, core,
            native.get("cleanup", {}).get("serial", {}),
        )
        if records != native.get("dispatch_cycle_records"):
            raise M30AttestationFailure("profile dispatch cycle 재도출이 다릅니다")
        denominator = profile_typed_denominator()
    elif campaign_id == "m30_dfu":
        expected_phases = {
            "dfu-initial-peripheral-bootloader": ("peripheral_bootloader",),
            "dfu-initial-peripheral-application": ("peripheral_application",),
            "dfu-initial-central-bootloader": ("central_bootloader",),
            "dfu-initial-central-application": ("central_application",),
            "dfu-cleanup": ROLES,
        }
        validate_program_phases(native, native_path, expected_phases)
        _require_target_cleanup(
            native.get("cleanup", {}).get("target"), "SECTOR_REPROGRAM_RESET"
        )
        nonce, core = _session_identity(captures, "M30DFU|1")
        denominator = build_dfu_cycle_records(
            native.get("results", {}), native.get("candidates", {}), captures,
            nonce, core, native.get("cleanup", {}).get("serial", {}),
            native.get("cleanup", {}).get("secondary_slot", {}),
        )
        rows = (
            native["candidates"]["positive"]
            + list(native["candidates"]["negative"].values())
            + [native["candidates"]["unconfirmed"]]
        )
        for row in rows:
            path = (native_path.parent / row["path"]).resolve()
            if (
                path.parent != native_path.parent.resolve()
                or not path.is_file()
                or path.stat().st_size != row["size"]
                or _digest(path) != row["sha256"]
            ):
                raise M30AttestationFailure("DFU candidate 인접 byte가 다릅니다")
            version, image_hash = _mcuboot_candidate_identity(path)
            if version != row["version"] or image_hash != row["image_hash"]:
                raise M30AttestationFailure(
                    "DFU candidate header·SHA TLV identity가 다릅니다"
                )
    else:
        raise M30AttestationFailure(f"지원하지 않는 M30 campaign입니다: {campaign_id}")
    if native.get("typed_denominator") != denominator:
        raise M30AttestationFailure("serialized typed denominator가 재도출과 다릅니다")
    return denominator


def make_dispatch_attestation(
    campaign_id: str,
    source_revision: str,
    semantics: tuple[str, ...],
    roles: tuple[str, ...],
    exact_program: dict[str, dict[str, Any]],
    cycle_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """! @brief raw-derived cycle과 same-process program receipt를 결합합니다. """

    return dispatch_attestation(
        campaign_id,
        source_revision,
        len(cycle_records),
        semantics,
        roles,
        exact_program,
        cycle_records=cycle_records,
    )
