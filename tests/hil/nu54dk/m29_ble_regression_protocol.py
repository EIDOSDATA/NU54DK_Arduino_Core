#!/usr/bin/env python3
"""! @brief M29-W07-E 회귀 증거 묶음을 fail-closed로 검증합니다. """

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


BOARD_TARGET = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
GROUP_ORDER = ("m19", "m20", "m21", "m28")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
NONCE_PATTERN = re.compile(r"[0-9a-f]{32}")
UID_PATTERN = re.compile(r"[0-9a-f]{32}")

GROUP_CONTRACTS: dict[str, dict[str, Any]] = {
    "m19": {
        "schema_version": 1,
        "gate": "m19-ble-gap-pair-hil",
        "coverage": {
            "legacy_advertising": True,
            "service_uuid_filter": True,
            "manufacturer_data": True,
            "rf_nonce_binding_bits": 128,
            "connect_disconnect": True,
            "explicit_reconnect": True,
            "callback_context": "arduino-main-thread",
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    },
    "m20": {
        "schema_version": 1,
        "gate": "m20-ble-generic-gatt-pair-hil",
        "coverage": {
            "service_registration": True,
            "exact_service_characteristic_discovery": True,
            "gatt_nonce_challenge_bits": 128,
            "cached_read": True,
            "write_with_response": True,
            "write_without_response": True,
            "notification_subscribe_unsubscribe": True,
            "indication_confirmation": True,
            "disconnect_handle_invalidation": True,
            "reconnect_rediscovery_resubscribe": True,
            "callback_context": "arduino-main-thread",
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    },
    "m21": {
        "schema_version": 3,
        "gate": "m21-ble-security-profile-pair-hil",
        "coverage": {
            "pairing": True,
            "bond_warm_reboot_restore": True,
            "bond_delete_warm_reboot_zero": True,
            "old_key_reconnect_rejected": True,
            "bond_repair": True,
            "encrypted_gatt_negative": True,
            "bas_read_and_notify": True,
            "dis_read": True,
            "hid_report_protocol": True,
        },
        "safety": {
            "factory_reset_executed": False,
            "mass_erase_requested": False,
        },
    },
    "m28": {
        "schema_version": 1,
        "gate": "m28-two-board-hil",
        "coverage": {
            "test_ids": ["M28-ADV-01", "M28-PAWR-01", "M28-PRIV-01"],
            "extended_payload_bytes": 255,
            "extended_reports": 100,
            "pawr_subevents": 4,
            "pawr_response_slots": 4,
            "pawr_minimum_valid_percent": 99,
            "rpa_rotations": 3,
            "bonded_reconnects": 20,
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    },
}


class RegressionEvidenceFailure(RuntimeError):
    """! @brief 회귀 증거가 고정 schema·identity·coverage를 위반한 경우입니다. """


@dataclass(frozen=True)
class RegressionGroupResult:
    """! @brief 검증을 마친 한 회귀군의 불변 identity와 원본 hash입니다. """

    group: str
    gate: str
    nonce: str
    board_uids: tuple[str, str]
    evidence_name: str
    evidence_sha256: str
    transcript_sha256: tuple[str, str]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """! @brief JSON object의 중복 key를 일반 parser보다 먼저 거부합니다. """

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegressionEvidenceFailure(f"중복 JSON key를 거부했습니다: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    """! @brief UTF-8 JSON object 하나만 읽고 중복 key·후행 data를 거부합니다. """

    if path.suffix.lower() != ".json" or not path.is_file():
        raise RegressionEvidenceFailure(f"JSON 증거 파일이 아닙니다: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RegressionEvidenceFailure(f"증거 JSON을 읽을 수 없습니다: {path}") from error
    if not isinstance(value, dict):
        raise RegressionEvidenceFailure(f"증거 root는 object여야 합니다: {path}")
    return value


def _sha256(path: Path) -> str:
    """! @brief 파일 전체 SHA-256을 계산합니다. """

    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                digest.update(block)
    except OSError as error:
        raise RegressionEvidenceFailure(f"증거 파일을 읽을 수 없습니다: {path}") from error
    return digest.hexdigest()


def _require_string(value: Any, label: str, pattern: re.Pattern[str] | None = None) -> str:
    """! @brief 필수 문자열과 선택 정규식을 함께 검사합니다. """

    if not isinstance(value, str) or value == "":
        raise RegressionEvidenceFailure(f"{label}은 non-empty string이어야 합니다.")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise RegressionEvidenceFailure(f"{label} 형식이 잘못되었습니다: {value!r}")
    return value


def _require_exact_subset(actual: Any, expected: dict[str, Any], label: str) -> None:
    """! @brief object의 필수 값이 type까지 정확히 같은지 검사합니다. """

    if not isinstance(actual, dict):
        raise RegressionEvidenceFailure(f"{label}은 object여야 합니다.")
    for key, expected_value in expected.items():
        if key not in actual:
            raise RegressionEvidenceFailure(f"{label}.{key}가 누락되었습니다.")
        actual_value = actual[key]
        if type(actual_value) is not type(expected_value) or actual_value != expected_value:
            raise RegressionEvidenceFailure(
                f"{label}.{key} 불일치: actual={actual_value!r}, expected={expected_value!r}"
            )


def _validate_boards(value: Any, group: str) -> tuple[str, str]:
    """! @brief 한 회귀군의 peripheral·central UID가 정확히 둘인지 검사합니다. """

    if not isinstance(value, dict) or set(value) != {"peripheral", "central"}:
        raise RegressionEvidenceFailure(f"{group}.boards는 두 고정 role만 가져야 합니다.")
    uids: list[str] = []
    for role in ("peripheral", "central"):
        board = value[role]
        if not isinstance(board, dict):
            raise RegressionEvidenceFailure(f"{group}.boards.{role}은 object여야 합니다.")
        uids.append(
            _require_string(
                board.get("daplink_uid"), f"{group}.boards.{role}.daplink_uid", UID_PATTERN
            )
        )
    if uids[0] == uids[1]:
        raise RegressionEvidenceFailure(f"{group}의 두 role UID가 중복되었습니다.")
    return (uids[0], uids[1])


def _validate_named_transcript(
    evidence_path: Path, value: Any, group: str, role: str
) -> str:
    """! @brief 이름·크기·hash로 한 raw transcript를 검증합니다. """

    if not isinstance(value, dict) or set(value) != {"name", "size", "sha256"}:
        raise RegressionEvidenceFailure(f"{group}.transcripts.{role} schema가 다릅니다.")
    name = _require_string(value.get("name"), f"{group}.{role}.transcript.name")
    if Path(name).name != name:
        raise RegressionEvidenceFailure(f"{group}.{role} transcript 이름에 경로가 포함됐습니다.")
    size = value.get("size")
    if type(size) is not int or size <= 0:
        raise RegressionEvidenceFailure(f"{group}.{role} transcript 크기가 잘못되었습니다.")
    expected_hash = _require_string(
        value.get("sha256"), f"{group}.{role}.transcript.sha256", re.compile(r"[0-9a-f]{64}")
    )
    transcript_path = evidence_path.with_name(name)
    if not transcript_path.is_file() or transcript_path.stat().st_size != size:
        raise RegressionEvidenceFailure(f"{group}.{role} transcript 크기·존재가 일치하지 않습니다.")
    if _sha256(transcript_path) != expected_hash:
        raise RegressionEvidenceFailure(f"{group}.{role} transcript hash가 일치하지 않습니다.")
    return expected_hash


def _validate_transcripts(
    evidence_path: Path, value: Any, group: str
) -> tuple[str, str]:
    """! @brief runner schema 차이를 보존하며 양쪽 raw transcript hash를 검증합니다. """

    if group != "m21":
        if not isinstance(value, dict) or set(value) != {"peripheral", "central"}:
            raise RegressionEvidenceFailure(f"{group}.transcripts role set이 다릅니다.")
        return (
            _validate_named_transcript(evidence_path, value["peripheral"], group, "peripheral"),
            _validate_named_transcript(evidence_path, value["central"], group, "central"),
        )
    if not isinstance(value, dict) or set(value) != {
        "peripheral_sha256",
        "central_sha256",
    }:
        raise RegressionEvidenceFailure("m21.transcripts schema가 다릅니다.")
    hashes: list[str] = []
    for role in ("peripheral", "central"):
        expected_hash = _require_string(
            value.get(f"{role}_sha256"),
            f"m21.transcripts.{role}_sha256",
            re.compile(r"[0-9a-f]{64}"),
        )
        transcript_path = evidence_path.with_name(
            f"{evidence_path.stem}.{role}.transcript.log"
        )
        if not transcript_path.is_file() or _sha256(transcript_path) != expected_hash:
            raise RegressionEvidenceFailure(f"m21.{role} transcript hash가 일치하지 않습니다.")
        hashes.append(expected_hash)
    return (hashes[0], hashes[1])


def validate_group_evidence(
    group: str,
    evidence_path: Path,
    expected_core_revision: str,
    expected_board_revision: str,
) -> RegressionGroupResult:
    """! @brief 한 기존 runner 증거의 revision·board·coverage·원본을 검증합니다. """

    if group not in GROUP_CONTRACTS:
        raise RegressionEvidenceFailure(f"알 수 없는 회귀군입니다: {group}")
    expected_core_revision = _require_string(
        expected_core_revision, "expected core revision", REVISION_PATTERN
    )
    expected_board_revision = _require_string(
        expected_board_revision, "expected board revision", REVISION_PATTERN
    )
    evidence_path = evidence_path.resolve()
    data = _read_json(evidence_path)
    required = {
        "schema_version",
        "gate",
        "status",
        "core_revision",
        "board_revision",
        "nonce",
        "boards",
        "transcripts",
        "coverage",
        "safety",
    }
    if group != "m21":
        required.add("board_target")
    missing = required.difference(data)
    if missing:
        raise RegressionEvidenceFailure(f"{group} 필수 key 누락: {sorted(missing)}")
    contract = GROUP_CONTRACTS[group]
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != contract["schema_version"]
    ):
        raise RegressionEvidenceFailure(
            f"{group}.schema_version은 {contract['schema_version']}이어야 합니다."
        )
    if data["gate"] != contract["gate"] or data["status"] != "passed":
        raise RegressionEvidenceFailure(f"{group} gate 또는 status가 PASS가 아닙니다.")
    if data["core_revision"] != expected_core_revision:
        raise RegressionEvidenceFailure(f"{group} core revision이 일치하지 않습니다.")
    if data["board_revision"] != expected_board_revision:
        raise RegressionEvidenceFailure(f"{group} board revision이 일치하지 않습니다.")
    if "board_target" in data and data["board_target"] != BOARD_TARGET:
        raise RegressionEvidenceFailure(f"{group} board target이 일치하지 않습니다.")
    nonce = _require_string(data["nonce"], f"{group}.nonce", NONCE_PATTERN)
    board_uids = _validate_boards(data["boards"], group)
    _require_exact_subset(data["coverage"], contract["coverage"], f"{group}.coverage")
    _require_exact_subset(data["safety"], contract["safety"], f"{group}.safety")
    transcript_hashes = _validate_transcripts(evidence_path, data["transcripts"], group)
    return RegressionGroupResult(
        group=group,
        gate=contract["gate"],
        nonce=nonce,
        board_uids=board_uids,
        evidence_name=evidence_path.name,
        evidence_sha256=_sha256(evidence_path),
        transcript_sha256=transcript_hashes,
    )


def validate_regression_session(
    evidence_paths: dict[str, Path],
    expected_core_revision: str,
    expected_board_revision: str,
) -> dict[str, RegressionGroupResult]:
    """! @brief 네 회귀군·고유 nonce·정확히 세 보드 참여를 함께 검증합니다. """

    if set(evidence_paths) != set(GROUP_ORDER) or len(evidence_paths) != len(GROUP_ORDER):
        raise RegressionEvidenceFailure("M19/M20/M21/M28 증거가 정확히 한 개씩 필요합니다.")
    resolved_paths = [evidence_paths[group].resolve() for group in GROUP_ORDER]
    if len(set(resolved_paths)) != len(resolved_paths):
        raise RegressionEvidenceFailure("같은 증거 파일을 둘 이상의 회귀군에 사용할 수 없습니다.")
    results = {
        group: validate_group_evidence(
            group,
            evidence_paths[group],
            expected_core_revision,
            expected_board_revision,
        )
        for group in GROUP_ORDER
    }
    nonces = {result.nonce for result in results.values()}
    if len(nonces) != len(GROUP_ORDER):
        raise RegressionEvidenceFailure("회귀군별 nonce는 모두 달라야 합니다.")
    board_uids = {
        uid for result in results.values() for uid in result.board_uids
    }
    if len(board_uids) != 3:
        raise RegressionEvidenceFailure("M29-REG-01에는 정확히 세 DAPLink UID가 참여해야 합니다.")
    return results
