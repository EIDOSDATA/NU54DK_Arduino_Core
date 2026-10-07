#!/usr/bin/env python3
"""! @brief M33 실제 campaign을 실행·정규화하고 3보드 finite soak를 검증합니다.

@note plan과 validate 명령은 보드에 접근하지 않습니다. execute-campaign은 등록된
runner와 명시적 실행 spec만 허용하며 generic raw 경로를 제공하지 않습니다.
@note pre-run 복원 실패는 부분 증거를 보존하는 fail-stop입니다. 재시도에는 새 output
root가 필요하며 기존 증거를 덮어쓰지 않습니다.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/bluetooth"))
import m33_execution as execution
from m33_regression import (CAMPAIGNS, CAMPAIGN_REGISTRIES, REV, SHA,
                             _validate_campaign_receipt,
                             adjacent_evidence_file, campaign_matrix_paths,
                             campaign_plan, digest, hil_contract,
                            intel_hex_ranges, integer,
                            read_json, require, validate_campaign_evidence,
                            validate_image_evidence, validate_peer,
                            validate_peer_evidence, validate_source_manifest)
from m33_sdk_risk_common import (build_record_path, copy_program_inputs,
                                 exact_program_evidence,
                                 readback_state_restored,
                                 readback_programmed_images_by_hash,
                                reserve_sidecars,
                                validate_programming_receipt)

ROLES = ("peripheral", "mixed", "central")
SOAK_HOST_MINIMUM_MS = 1800000
SOAK_HOST_MAXIMUM_MS = 2460000
SOAK_ALLOWED_LOSS_PACKETS = 100
FIRMWARE_SOURCE = ROOT / "tests/zephyr/m28_ble_3board_hil/src/main.cpp"


def validate_cleanup_source_binding(contract: dict, manifest_sha256: str) -> str:
    """! @brief FINAL이 BLEDevice.end와 zero-link 검사 뒤에만 나오는 source를 고정합니다. """
    expected_path = FIRMWARE_SOURCE.relative_to(ROOT).as_posix()
    require(contract == {"path": expected_path, "sha256": digest(FIRMWARE_SOURCE),
                          "source_manifest_sha256": manifest_sha256,
                          "mode": "autonomous_finite_cleanup_final", "stop_token": False},
            "firmware cleanup source binding mismatch")
    source = FIRMWARE_SOURCE.read_text(encoding="utf-8")
    start = source.find("void finishSoak()")
    finish = source.find("/** @brief periodic advertiser", start)
    require(start >= 0 and finish > start, "firmware finishSoak source missing")
    body = source[start:finish]
    end_call = body.find("BLEDevice.end();")
    zero_guard = body.find("BLEDevice.initialized() || BLEConnection.count() != 0U")
    final = body.find(":FINAL:PASS:test=SOAK")
    require(0 <= end_call < zero_guard < final and 'fail("resource-recovery")' in body,
            "firmware FINAL is not bound to end/zero-link cleanup")
    return contract["sha256"]


def validate_execution_receipt(receipt: dict, evidence: dict, nonce: str) -> None:
    """! @brief 실행 중 생성된 probe/image/readback/UART receipt의 불변 결합을 검사합니다. """
    required = {"schema_version", "kind", "producer_sha256", "nonce_sha256",
                "source_manifest_sha256", "active_started_ns", "active_finished_ns",
                "roles", "sha256"}
    require(isinstance(receipt, dict) and set(receipt) == required and
            receipt["schema_version"] == 1 and
            receipt["kind"] == "pyocd-sector-uart-live-session-v1",
            "execution receipt schema mismatch")
    payload = {key: receipt[key] for key in required - {"sha256"}}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(receipt["sha256"] == hashlib.sha256(encoded).hexdigest(),
            "execution receipt digest mismatch")
    require(receipt["producer_sha256"] == evidence["producer"]["route_sha256"] and
            receipt["source_manifest_sha256"] == evidence["source_manifest"]["sha256"] and
            receipt["nonce_sha256"] == hashlib.sha256(nonce.encode("ascii")).hexdigest(),
            "execution receipt identity mismatch")
    require(type(receipt["active_started_ns"]) is int and
            type(receipt["active_finished_ns"]) is int and
            receipt["active_finished_ns"] > receipt["active_started_ns"] and
            (receipt["active_finished_ns"] - receipt["active_started_ns"]) // 1000000 ==
            evidence["host_monotonic_elapsed_ms"], "execution receipt active interval mismatch")
    require(set(receipt["roles"]) == set(ROLES), "execution receipt role denominator")
    require(all(isinstance(evidence.get(field), dict) and
                set(evidence[field]) == set(ROLES)
                for field in ("boards", "images", "transcripts")),
            "execution receipt evidence role denominator")
    for role in ROLES:
        row = receipt["roles"][role]
        require(set(row) == {"probe_sha256", "image_sha256", "readback_sha256",
                             "flash_record_sha256", "transcript_sha256"} and
                row["probe_sha256"] == evidence["boards"][role]["probe_sha256"] and
                row["image_sha256"] == evidence["images"][role]["file"]["sha256"] and
                row["readback_sha256"] == evidence["images"][role]["readback"]["sha256"] and
                row["flash_record_sha256"] ==
                evidence["images"][role]["flash_record"]["sha256"] and
                row["transcript_sha256"] == evidence["transcripts"][role]["sha256"],
                "execution receipt role binding mismatch")


def validate_soak(path: Path, revision: str, development: bool = False,
                  allow_fixture: bool = False,
                  allow_physical_audit: bool = False) -> dict:
    """! @brief 저장 soak 원본의 integrity를 검사하되 actual-run으로 승격하지 않습니다. """
    require(REV.fullmatch(revision), "exact expected revision required")
    evidence = read_json(path)
    require(evidence.get("schema_version") == 3 and evidence.get("evidence_kind") == "m33_fresh_soak",
            "fresh W06 soak evidence required")
    producer = evidence.get("producer", {})
    producer_route = ROOT / "tests/hil/nu54dk/m32_regression_soak_run.py"
    require(set(producer) == {"schema_version", "kind", "route", "route_sha256", "protocol"} and
            producer["schema_version"] == 1 and
            producer["route"] == "tests/hil/nu54dk/m32_regression_soak_run.py" and
            producer["route_sha256"] == digest(producer_route) and
            producer["protocol"] == "NUCODE_M28B3_SOAK_V3" and
            producer["kind"] in ("physical_hil", "schema_fixture"),
            "soak producer identity mismatch")
    require(producer["kind"] == "physical_hil" or allow_fixture,
            "schema fixture cannot satisfy physical soak closure")
    if producer["kind"] == "physical_hil":
        require(allow_physical_audit,
                "stored physical soak evidence is audit-only and cannot close actual-run")
    require(evidence.get("status") in (("PASS", "PASS_CANDIDATE") if development else ("PASS",)), "soak did not pass")
    require(type(evidence.get("source_clean")) is bool and
            ((evidence["status"] == "PASS" and evidence["source_clean"] is True) or
             (development and evidence["status"] == "PASS_CANDIDATE" and
              evidence["source_clean"] is False)), "clean exact soak required")
    lock = read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
    identity = evidence.get("identity", {})
    require(set(identity) == {"core", "board", "ncs", "zephyr"} and
            all(isinstance(value, str) and REV.fullmatch(value) for value in identity.values()),
            "full exact soak identity required")
    require(identity.get("core") == revision, "historical or wrong source soak")
    for name in ("board", "ncs", "zephyr"):
        require(identity.get(name) == lock[name]["revision"], "soak fixed SDK/board mismatch")
    source_manifest = evidence.get("source_manifest", {})
    validate_source_manifest(source_manifest, revision, lock)
    require(source_manifest["firmware_source_sha256"] == digest(FIRMWARE_SOURCE) and
            source_manifest["application_cmake_sha256"] ==
            digest(ROOT / "tests/zephyr/m32_regression_soak_hil/CMakeLists.txt") and
            source_manifest["application_config_sha256"] ==
            digest(ROOT / "tests/zephyr/m32_regression_soak_hil/prj.conf"),
            "soak current source manifest mismatch")
    require(evidence.get("scope") == "three_board_bounded_gatt_soak", "wrong soak scope")
    require(evidence.get("test_ids") == ["M32-SOAK-01:primary", "M33-REG-01:representative_soak"],
            "wrong fresh W06 soak test IDs")
    for field, expected in (("duration_seconds", 1800), ("packet_denominator_per_link", 10000),
                            ("allowed_loss_packets", SOAK_ALLOWED_LOSS_PACKETS),
                            ("observed_loss_packets", 0), ("latency_limit_ms", 500),
                            ("recovery_timeout_s", 30)):
        require(type(evidence.get(field)) is int and evidence[field] == expected, "soak denominator/bound changed")
    require(evidence.get("host_monotonic_scope") == "central_start_to_all_final" and
            type(evidence.get("host_monotonic_elapsed_ms")) is int and
            SOAK_HOST_MINIMUM_MS <= evidence["host_monotonic_elapsed_ms"] <= SOAK_HOST_MAXIMUM_MS,
            "host monotonic soak duration outside fixed range")
    safety = evidence.get("safety", {})
    require(set(safety) == {"cmsis_dap", "auto_unlock", "erase", "reset", "automatic_recover",
                            "mass_erase", "termination", "stop_token"}, "soak safety fields")
    require(safety.get("cmsis_dap") == "v2-only" and safety.get("erase") == "sector" and
            safety.get("reset") == "software", "soak safety mode")
    require(all(safety.get(key) is False for key in ("auto_unlock", "automatic_recover", "mass_erase")), "unsafe soak operation")
    require(safety["termination"] == "autonomous_finite_cleanup_final" and safety["stop_token"] is False,
            "unsupported STOP claim or termination mode")
    firmware_source_sha256 = validate_cleanup_source_binding(
        evidence.get("firmware_cleanup_contract", {}), source_manifest["sha256"]
    )
    for field in ("boards", "images", "transcripts", "results"):
        require(set(evidence.get(field, {})) == set(ROLES), "missing/duplicate three-board role")
    probes, ports, images, nonces, results = set(), set(), set(), set(), {}
    ## @brief 기존 parser는 firmware의 sequence/counter·gap·STOP 분모를 이미 strict하게 검증합니다.
    from m32_regression_soak_run import _parse_role
    for role in ROLES:
        board, image = evidence["boards"][role], evidence["images"][role]
        require(isinstance(board, dict) and isinstance(board.get("probe_sha256"), str) and
                SHA.fullmatch(board["probe_sha256"]) and isinstance(board.get("vcom"), str) and
                board["vcom"], "probe/VCOM proof missing")
        require(isinstance(board.get("registers"), dict) and board["registers"], "actual debugger preflight missing")
        probes.add(board["probe_sha256"])
        ports.add(board["vcom"].casefold())
        validated_image = validate_image_evidence(
            image, path.parent, revision, lock, role,
            producer["kind"] == "physical_hil"
        )
        require(validated_image["probe_sha256"] == board["probe_sha256"],
                "flash record probe does not match role board")
        require(image["source_manifest"] == source_manifest and
                image["source_manifest"]["firmware_source_sha256"] == firmware_source_sha256,
                "image embedded identity is not bound to cleanup source")
        images.add(validated_image["image_sha256"])
        transcript = evidence["transcripts"][role]
        name = transcript.get("name", "")
        require(isinstance(name, str) and Path(name).name == name and name, "transcript must be adjacent evidence file")
        raw_path = (path.parent / name).resolve()
        require(raw_path.parent == path.parent.resolve() and raw_path.is_file() and
                digest(raw_path) == transcript.get("sha256") and
                raw_path.stat().st_size == transcript.get("size"), "transcript file/hash/size mismatch")
        raw = raw_path.read_bytes()
        role_nonces = set(re.findall(rb":nonce=([0-9a-f]{32})(?:\s|$)", raw))
        require(len(role_nonces) == 1, "missing or mixed session nonce")
        nonce = next(iter(role_nonces)).decode("ascii")
        require(nonce != "0" * 32, "zero nonce")
        nonces.add(nonce)
        results[role] = _parse_role(raw, nonce, role, source_manifest)
        require(evidence["results"][role] == results[role], "summary differs from raw soak protocol")
    require(len(probes) == len(ports) == len(images) == 3 and len(nonces) == 1, "role/image/session isolation mismatch")
    receipt = evidence.get("execution_receipt", {})
    validate_execution_receipt(receipt, evidence, next(iter(nonces)))
    return {"schema_version": 1, "test_id": "M33-REG-01:representative_soak",
            "status": "SCHEMA_VALID" if producer["kind"] == "schema_fixture" else "AUDIT_ONLY",
            "actual_run": "NOT_VERIFIED", "source_revision": revision,
            "scope": "stored-three-board-soak-integrity",
            "source_evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "results": results}



FORBIDDEN_EXECUTION_OPTIONS = {
    "--development", "--discover-only", "--help",
    "--overwrite-evidence", "--reuse-build-root",
}
OUTPUT_ARGUMENT_MODES = {
    "--evidence": "file",
    "--output": "file",
    "--output-prefix": "prefix",
    "--work-root": "directory",
    "--build-outdir": "directory",
    "--peripheral-build-outdir": "directory",
}
SHELL_META = re.compile(r"[\r\n\x00;&|\x60$<>]")
MAX_ARGUMENT_VALUES = 32
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 14400
## @brief profile의 20회 reboot chain은 각 phase의 기존 1,800초 상한을 합산합니다.
PROFILE_PHASE_TIMEOUT_SECONDS = 1800
PROFILE_PHASE_COUNTS = {"m33_profiles_standard": 2, "m33_profiles_native": 3}
PRE_RUN_STATE_RESTORE = {
    "m31_bap_duplex": "direct",
    "m33_ecosystem": "ecosystem_isolated",
    "m33_diagnostics_dtm": "third_idle",
}
RESTORE_TIMEOUT_SECONDS = 120.0
_RESTORE_AUTHORITY_SECRET = object()


class _RestoreAuthority:
    """! @brief 직렬화할 수 없는 same-process parent probe-lock 권한입니다. """

    def __init__(self, secret: object, hashes: list[str]):
        require(secret is _RESTORE_AUTHORITY_SECRET,
                "restore authority construction refused")
        self._secret = secret
        self.hashes = tuple(sorted(hashes))
        self.active = True

    def close(self) -> None:
        """! @brief lock scope 종료와 동시에 권한을 폐기합니다. """

        self.active = False

NATIVE_ADAPTER_FAMILIES = {
    "legacy_hil": (
        "m28_link", "m28_adv_pawr_privacy", "m28_periodic_past",
        "m28_link_control", "m29_long_read", "m29_reliable_write",
        "m29_descriptor", "m29_cache", "m29_coc", "m29_signed_eatt",
        "m29_multi", "m30_pair", "m30_oob", "m30_bond", "m30_profiles",
        "m30_dfu", "m30_multi",
    ),
    "modern_hil": (
        "m31_iso_cis", "m33_cis_acl_risk", "m31_iso_bis",
        "m31_iso_combined", "m31_df_tx", "m32_power", "m32_timing",
        "m32_advertising", "m32_privacy", "m32_ead", "m32_nordic",
        "m32_mesh", "m32_mesh_management", "m32_mesh_update",
        "m32_mesh_dfu", "m32_standalone_radio", "m32_coexistence",
        "m33_beacons",
    ),
    "flat_hil": (
        "m31_bap_duplex", "m31_cs_ras", "m33_cs_acl_radio_risk",
        "m31_cs_negative_stale_key", "m31_cs_negative_insecure_read",
        "m31_cs_negative_wrong_peer", "m31_cs_negative_missing_service",
    ),
    "profile_hil": (
        "m33_profiles_standard", "m33_profiles_native",
    ),
    "ecosystem_hil": ("m33_ecosystem",),
    "build_semantic": (
        "m33_ecosystem_templates", "m33_diagnostics_build",
    ),
    "diagnostic_hil": ("m33_diagnostics_dtm",),
}
NATIVE_ADAPTER_REGISTRY = {
    campaign_id: family
    for family, campaign_ids in NATIVE_ADAPTER_FAMILIES.items()
    for campaign_id in campaign_ids
}
if set(NATIVE_ADAPTER_REGISTRY) != set(CAMPAIGNS) or \
        len(NATIVE_ADAPTER_REGISTRY) != sum(
            len(campaign_ids) for campaign_ids in NATIVE_ADAPTER_FAMILIES.values()
        ):
    raise RuntimeError("every actual campaign requires exactly one native adapter")

CAMPAIGN_PREPARATION_MODE = {
    campaign_id: (
        "profile_standard" if campaign_id == "m33_profiles_standard" else
        "profile_phase_manifest" if campaign_id == "m33_profiles_native" else
        "ecosystem_fixture" if campaign_id == "m33_ecosystem" else
        "template_aggregate" if campaign_id == "m33_ecosystem_templates" else
        "diagnostic_pair" if campaign_id == "m33_diagnostics_dtm" else
        "diagnostic_build" if campaign_id == "m33_diagnostics_build" else
        family
    )
    for campaign_id, family in NATIVE_ADAPTER_REGISTRY.items()
}
if set(CAMPAIGN_PREPARATION_MODE) != set(CAMPAIGNS):
    raise RuntimeError("every unique campaign requires deterministic preparation")

NATIVE_SUCCESS_STATUS = {
    "m31_bap_duplex": "ARDUINO_BAP_DUPLEX_STOP_RELEASE_PASS",
    "m31_df_tx": "PASS_CONTROL",
}
NATIVE_ATTESTATION_KIND = "m33_native_campaign_attestation"
CAMPAIGN_SUBCOMMAND = {
    "m33_ecosystem": "run",
    "m33_diagnostics_build": "build",
}
CAMPAIGN_FIXED_ARGUMENTS = {
    "m28_link": (("--test-id", "M28-LINK-01"),),
    "m28_periodic_past": (("--test-id", "M28-PER-01"),),
    "m28_link_control": (("--test-id", "M28-CTRL-01"),),
    "m31_cs_ras": (("--disconnect-cycles", "20"),),
}
INTENTIONAL_DISPATCH_BLOCKERS = {
    "m31_iso_bis": "baseline_20_and_negative_2_plus_2_are_separate_native_runs",
    "m32_mesh": "native_runner_has_one_session_not_twenty_sessions",
    "m32_mesh_dfu": "active_watchdog_runtime_erase_swap_hash_attestation_missing",
}
DERIVED_LEGACY_CAMPAIGNS = {
    "m28_link", "m28_adv_pawr_privacy", "m28_periodic_past",
    "m28_link_control", "m29_long_read", "m29_reliable_write",
    "m29_descriptor", "m29_cache", "m29_coc", "m29_signed_eatt",
    "m29_multi", "m30_multi",
}
HASH_ONLY_LEGACY_CAMPAIGNS = set(DERIVED_LEGACY_CAMPAIGNS)
RAW_PROBE_IDENTITY = re.compile(
    rb"(?i)(?:daplink(?:[_ -]?uid)?|board[_ -]?id|probe[_ -]?uid)"
    rb"\s*[=:]\s*[\"']?[0-9a-f]{16,64}"
)
RAW_HEX_IDENTITY = re.compile(rb"(?i)(?<![0-9a-f])([0-9a-f]{16,64})(?![0-9a-f])")
DERIVED_FLAT_CAMPAIGNS = {"m31_bap_duplex", "m31_cs_ras"}
DERIVED_BUILD_CAMPAIGNS = {"m33_diagnostics_build"}
DERIVED_FIXTURE_CAMPAIGNS = {"m33_ecosystem"}
M30_NATIVE_CAMPAIGNS = {
    "m30_pair", "m30_oob", "m30_bond", "m30_profiles", "m30_dfu",
}
DERIVED_DISPATCH_CAMPAIGNS = (
    DERIVED_LEGACY_CAMPAIGNS | DERIVED_FLAT_CAMPAIGNS |
    DERIVED_BUILD_CAMPAIGNS | DERIVED_FIXTURE_CAMPAIGNS | {"m30_dfu"}
)
MODERN_DIRECT_RAW_CAMPAIGNS = {
    "m31_iso_cis", "m31_iso_combined", "m31_df_tx", "m32_power",
    "m32_advertising", "m32_privacy", "m32_ead", "m32_nordic",
    "m32_mesh_management", "m32_mesh_update", "m33_beacons",
}
MULTIPHASE_DIRECT_RAW_CAMPAIGNS = {
    "m32_standalone_radio", "m32_coexistence",
}
CS_NEGATIVE_CAMPAIGNS = {
    "m31_cs_negative_stale_key": "stale_key",
    "m31_cs_negative_insecure_read": "insecure_read",
    "m31_cs_negative_wrong_peer": "wrong_peer",
    "m31_cs_negative_missing_service": "missing_service",
}


def _artifact_path(root: Path, campaign_id: str, name: str,
                   directory: bool = False) -> Path:
    """! @brief 고정 artifact layout에서 유일한 runner 입력을 선택합니다. """
    base = root / campaign_id
    candidates = [base / name]
    if not directory:
        candidates.extend(base / f"{name}{suffix}"
                          for suffix in (".hex", ".json", ".conf", ".pem"))
    predicate = Path.is_dir if directory else Path.is_file
    matches = [path.resolve() for path in candidates if predicate(path)]
    require(len(matches) == 1, f"campaign artifact is missing or ambiguous: {name}")
    return matches[0]


def _preparation_roles(expected: dict) -> tuple[str, ...]:
    """! @brief runner 준비에 필요한 실제 동시 보드 역할을 반환합니다. """

    roles = tuple(expected["roles"])
    if expected["id"] in {"m33_ecosystem", "m33_diagnostics_dtm"}:
        roles += ("third",)
    return roles


def _board_inventory(document: dict, revision: str,
                     plan: dict) -> dict[str, dict[str, dict]]:
    """! @brief 논리 역할을 최대 3개 hash-only 물리 slot에 campaign별로 결합합니다.

    schema v1은 기존 단일 논리 역할 표를 읽기 위한 호환 경로입니다. schema v2는
    순차 campaign마다 물리 slot을 다시 배정하되 같은 campaign 안에서는 probe 재사용을
    허용하지 않습니다. 어느 schema도 raw probe UID를 받거나 실행 spec에 기록하지 않습니다.
    """

    require(isinstance(document, dict) and
            document.get("kind") == "m33_board_inventory" and
            document.get("source_revision") == revision and
            document.get("source_clean") is True and
            isinstance(plan, dict) and isinstance(plan.get("campaigns"), list),
            "board inventory schema mismatch")
    allowed_io = {"port", "volume", "app", "aux"}
    if document.get("schema_version") == 1:
        require(set(document) == {"schema_version", "kind", "source_revision",
                                  "source_clean", "boards"} and
                isinstance(document["boards"], list),
                "board inventory schema mismatch")
        allowed = {"role", "probe_sha256"} | allowed_io
        boards = {}
        for row in document["boards"]:
            require(isinstance(row, dict) and set(row).issubset(allowed) and
                    set(row) >= {"role", "probe_sha256"} and
                    isinstance(row["role"], str) and
                    row["role"] not in boards and
                    SHA.fullmatch(row["probe_sha256"]),
                    "board inventory role identity mismatch")
            require(all(value is None or isinstance(value, str) and value
                        for key, value in row.items()
                        if key not in {"role", "probe_sha256"}),
                    "board inventory optional value mismatch")
            boards[row["role"]] = row
        require(len({row["probe_sha256"] for row in boards.values()}) ==
                len(boards), "board inventory probes must be distinct")
        _reject_raw_probe_identity_bytes(
            json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            "board inventory", {row["probe_sha256"] for row in boards.values()}
        )
        by_campaign = {}
        for expected in plan["campaigns"]:
            roles = _preparation_roles(expected)
            require(all(role in boards for role in roles),
                    f"board inventory lacks campaign role: {expected['id']}")
            by_campaign[expected["id"]] = {
                role: boards[role] for role in roles
            }
        return by_campaign

    require(document.get("schema_version") == 2 and
            set(document) == {"schema_version", "kind", "source_revision",
                              "source_clean", "physical_slots",
                              "campaign_bindings"} and
            isinstance(document["physical_slots"], list) and
            isinstance(document["campaign_bindings"], list),
            "board inventory schema mismatch")
    slots = {}
    allowed_slot = {"slot", "probe_sha256"} | allowed_io
    for row in document["physical_slots"]:
        require(isinstance(row, dict) and set(row).issubset(allowed_slot) and
                set(row) >= {"slot", "probe_sha256"} and
                isinstance(row["slot"], str) and
                re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", row["slot"]) and
                row["slot"] not in slots and SHA.fullmatch(row["probe_sha256"]),
                "physical board slot identity mismatch")
        require(all(value is None or isinstance(value, str) and value
                    for key, value in row.items()
                    if key not in {"slot", "probe_sha256"}),
                "physical board slot optional value mismatch")
        slots[row["slot"]] = row
    require(1 <= len(slots) <= 3 and
            len({row["probe_sha256"] for row in slots.values()}) == len(slots),
            "physical board inventory requires one to three distinct probes")
    _reject_raw_probe_identity_bytes(
        json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        "board inventory", {row["probe_sha256"] for row in slots.values()}
    )
    expected_by_id = {
        expected["id"]: expected for expected in plan["campaigns"]
        if _preparation_roles(expected)
    }
    canonical_by_id = {
        campaign_id: {
            "id": campaign_id,
            "roles": list(definition["roles"]),
        }
        for campaign_id, definition in CAMPAIGNS.items()
        if _preparation_roles({
            "id": campaign_id,
            "roles": list(definition["roles"]),
        })
    }
    bindings = document["campaign_bindings"]
    binding_ids = [row.get("campaign_id") for row in bindings
                   if isinstance(row, dict)]
    require(binding_ids in (list(expected_by_id), list(canonical_by_id)),
            "campaign board binding denominator/order mismatch")
    binding_expected = (canonical_by_id if binding_ids == list(canonical_by_id)
                        else expected_by_id)
    by_campaign = {}
    for binding in bindings:
        require(isinstance(binding, dict) and
                set(binding) == {"campaign_id", "roles"} and
                binding["campaign_id"] in binding_expected and
                isinstance(binding["roles"], list),
                "campaign board binding schema mismatch")
        expected = binding_expected[binding["campaign_id"]]
        roles = _preparation_roles(expected)
        role_rows = binding["roles"]
        require([row.get("role") for row in role_rows
                 if isinstance(row, dict)] == list(roles) and
                all(set(row) == {"role", "slot"} and row["slot"] in slots
                    for row in role_rows),
                "campaign board role binding mismatch")
        selected_slots = [row["slot"] for row in role_rows]
        require(len(set(selected_slots)) == len(selected_slots),
                "same campaign roles require distinct physical probes")
        if binding["campaign_id"] not in expected_by_id:
            continue
        by_campaign[expected["id"]] = {}
        for row in role_rows:
            physical = slots[row["slot"]]
            by_campaign[expected["id"]][row["role"]] = {
                "role": row["role"],
                "probe_sha256": physical["probe_sha256"],
                **{key: physical[key] for key in allowed_io if key in physical},
            }
    for expected in plan["campaigns"]:
        by_campaign.setdefault(expected["id"], {})
    return by_campaign


def _prepared_arguments(expected: dict, boards: dict[str, dict],
                        artifact_root: Path, output_root: Path,
                        sdk_root: Path, toolchain: Path,
                        revision: str) -> tuple[str | None, list[dict], str]:
    """! @brief runner option을 보드 mapping·고정 artifact layout에서 결정합니다. """
    campaign_id = expected["id"]
    runner = ROOT / expected["runner"]["path"]
    subcommand = CAMPAIGN_SUBCOMMAND.get(campaign_id)
    options, subcommands = _runner_interface(runner, subcommand)
    require((not subcommands and subcommand is None) or subcommand in subcommands,
            "campaign subcommand preparation mismatch")
    arguments = []

    def add(option: str, *values: str) -> None:
        if option in options:
            arguments.append({"option": option, "values": list(values)})

    for role in expected["roles"]:
        require(role in boards, f"board inventory lacks role: {role}")
    output_base = output_root / "native" / campaign_id
    if "--evidence" in options:
        native = output_base.with_suffix(".json")
        add("--evidence", str(native))
    elif "--output-prefix" in options:
        native = output_base.with_suffix(".json")
        add("--output-prefix", str(output_base))
    elif "--work-root" in options:
        native = output_base / "companion-build-results.json"
        add("--work-root", str(output_base))
    elif "--output" in options:
        if campaign_id == "m33_ecosystem":
            native = output_base / "result.json"
            add("--output", str(output_base))
        elif campaign_id == "m33_diagnostics_build":
            native = output_base / "manifest.json"
            add("--output", str(output_base))
        else:
            native = output_base.with_suffix(".json")
            add("--output", str(native))
    else:
        raise ValueError("registered runner has no deterministic output option")
    add("--sdk-root", str(sdk_root.resolve()))
    add("--sdk", str(sdk_root.resolve()))
    add("--toolchain", str(toolchain.resolve()))
    add("--toolchain-root", str(toolchain.resolve()))
    add("--expected-core-revision", revision)
    add("--core-revision", revision)
    add("--cycles", str(expected["minimum_cycles"]))
    add("--procedures", str(expected["minimum_cycles"]))
    if "--source-clean" in options:
        add("--source-clean")
    if "--flash" in options:
        add("--flash")
    if "--post-flash-reset" in options:
        add("--post-flash-reset")
    if "--execute" in options and campaign_id in {
            "m33_profiles_standard", "m33_profiles_native", "m33_diagnostics_dtm"}:
        add("--execute")
    if campaign_id == "m33_diagnostics_build":
        add("--routes", "controller", "scan_request")
    add("--flash-backend", "pyocd-sector")
    add("--flash-timeout", "120")
    add("--family", "native" if campaign_id == "m33_profiles_native" else "standard")
    for option, value in CAMPAIGN_FIXED_ARGUMENTS.get(campaign_id, ()):
        add(option, value)
    if campaign_id == "m31_cs_negative_insecure_read":
        add("--same-acl")
    for role in expected["roles"]:
        board = boards[role]
        cli_role = role.replace("_", "-")
        for option in (f"--probe-{cli_role}-sha256",
                       f"--{cli_role}-probe-sha256"):
            add(option, board["probe_sha256"])
        for field, suffix in (("port", "port"), ("volume", "volume"),
                              ("app", "app"),
                              ("aux", "aux")):
            option = f"--{cli_role}-{suffix}"
            if option in options:
                require(board.get(field), f"board inventory lacks {role}.{field}")
                add(option, board[field])
        for option in (f"--hex-{cli_role}", f"--{cli_role}-hex",
                       f"--{cli_role}-image"):
            if option in options:
                add(option, str(_artifact_path(
                    artifact_root, campaign_id, option[2:]
                )))
        for option in (f"--{cli_role}-config", f"--{cli_role}-flash-record"):
            if option in options:
                add(option, str(_artifact_path(
                    artifact_root, campaign_id, option[2:]
                )))
    if "--probe-sha256" in options:
        add("--probe-sha256", boards[expected["roles"][0]]["probe_sha256"])
    if "--hex" in options:
        add("--hex", str(_artifact_path(artifact_root, campaign_id, "hex")))
    special_probes = {
        "--probe-first-sha256": 0, "--probe-second-sha256": 1,
        "--probe-dut-sha256": 0, "--probe-radio-sha256": 1,
        "--probe-ble-sha256": 2,
    }
    for option, index in special_probes.items():
        if option in options:
            probe = boards[expected["roles"][index]]["probe_sha256"]
            existing = [row["values"] for row in arguments
                        if row["option"] == option]
            if existing:
                require(existing == [[probe]],
                        "prepared probe alias conflicts with role mapping")
            else:
                add(option, probe)
    path_tokens = ("hex-", "build-", "build-outdir", "signing-key", "imgtool",
                   "config", "flash-record", "fixture", "prior-evidence",
                   "fresh", "restored", "second-peer")
    populated = {row["option"] for row in arguments}
    for option in sorted(options - populated - FORBIDDEN_EXECUTION_OPTIONS):
        name = option[2:]
        if campaign_id in {"m33_profiles_standard", "m33_profiles_native"} and option in {
            "--build-record", "--second-peer-role", "--second-peer-build-record",
        }:
            continue
        if campaign_id == "m33_diagnostics_dtm" and option in {
            "--build-manifest", "--twowire-hex", "--h4-hex",
            "--third-idle-fixture",
        }:
            continue
        if any(token in name for token in path_tokens):
            directory = "build" in name and "record" not in name and \
                "info" not in name
            add(option, str(_artifact_path(
                artifact_root, campaign_id, name, directory=directory
            )))
    if campaign_id in {"m33_profiles_standard", "m33_profiles_native"}:
        physical_roles = ("server", "client", "watcher")
        for role in physical_roles:
            cli_role = role.replace("_", "-")
            board_role = "second_peer" if (
                campaign_id == "m33_profiles_native" and role == "watcher"
            ) else role
            artifact_name = (f"hex-{cli_role}-idle" if
                             campaign_id == "m33_profiles_native" and role == "watcher"
                             else f"hex-{cli_role}")
            image = _artifact_path(artifact_root, campaign_id, artifact_name)
            add("--role", role, boards[board_role]["probe_sha256"], str(image))
            record = _artifact_path(artifact_root, campaign_id,
                                    f"build-record-{cli_role}-idle" if
                                    campaign_id == "m33_profiles_native" and role == "watcher"
                                    else f"build-record-{cli_role}")
            add("--build-record", role, str(record))
        if campaign_id == "m33_profiles_native":
            image = _artifact_path(artifact_root, campaign_id, "hex-second-peer")
            record = _artifact_path(
                artifact_root, campaign_id, "build-record-second-peer"
            )
            add("--second-peer-role", boards["second_peer"]["probe_sha256"],
                str(image))
            add("--second-peer-build-record", str(record))
    if campaign_id == "m33_diagnostics_dtm":
        require("third" in boards, "board inventory lacks DTM third role")
        add("--third-probe-sha256", boards["third"]["probe_sha256"])
        for option, name in (("--build-manifest", "build-manifest"),
                             ("--twowire-hex", "twowire-hex"),
                             ("--h4-hex", "h4-hex"),
                             ("--third-idle-fixture", "third-idle-fixture")):
            add(option, str(_artifact_path(artifact_root, campaign_id, name)))
    return subcommand, arguments, native.relative_to(output_root).as_posix()


def prepare_execution_spec(field: str, identifier: str, board_inventory: dict,
                           artifact_root: Path, output_root: Path,
                           sdk_root: Path, toolchain: Path,
                           root: Path = ROOT) -> dict:
    """! @brief 현재 clean source에서 wrapper의 exact 실행/reuse spec을 생성합니다. """
    revision, clean = _git_identity(root)
    require(clean, "campaign preparation requires clean source")
    plan = campaign_plan(field, identifier, root)
    campaign_boards = _board_inventory(board_inventory, revision, plan)
    output_root = output_root.resolve()
    require(output_root.is_dir() and not output_root.resolve().is_relative_to(root.resolve()),
            "existing external output root required")
    rows = []
    for expected in plan["campaigns"]:
        boards = campaign_boards[expected["id"]]
        receipt = output_root / f"campaign.{expected['id']}.receipt.json"
        native_name = f"native/{expected['id']}.json"
        child_name = f"campaign.{expected['id']}.child.json"
        reuse = None
        arguments = []
        subcommand = CAMPAIGN_SUBCOMMAND.get(expected["id"])
        if receipt.is_file():
            receipt_value = read_json(receipt)
            child_reference = receipt_value.get("child_evidence", {})
            require(isinstance(child_reference, dict) and
                    Path(child_reference.get("path", "")).name ==
                    child_reference.get("path") and
                    (output_root / child_reference["path"]).is_file(),
                    "reusable receipt child is incomplete")
            child_name = child_reference["path"]
            child_value = read_json(output_root / child_name)
            native_name = child_value.get("native_evidence", {}).get("path", "")
            reuse = {"path": receipt.name, "sha256": digest(receipt)}
        else:
            subcommand, arguments, native_name = _prepared_arguments(
                expected, boards, artifact_root.resolve(), output_root,
                sdk_root, toolchain, revision
            )
        role_rows = [{"role": role,
                      "probe_sha256": boards[role]["probe_sha256"]}
                     for role in _preparation_roles(expected)]
        rows.append({
            "id": expected["id"], "verification": expected["verification"],
            "runner": expected["runner"], "applications": expected["applications"],
            "roles": expected["roles"], "cycles": expected["minimum_cycles"],
            "semantics": expected["semantics"], "subcommand": subcommand,
            "arguments": arguments, "timeout_seconds": campaign_timeout_seconds(expected),
            "boards": role_rows, "native_evidence": native_name,
            "child_evidence": child_name, "reuse_receipt": reuse,
        })
    spec = {
        "schema_version": 1, "kind": "m33_campaign_execution_spec",
        "field": field, "id": identifier, "source_revision": revision,
        "source_clean": True, "campaign_plan": plan, "campaigns": rows,
    }
    if field == "families" and identifier == "ecosystem_templates":
        spec["external_interoperability"] = "NOT_RUN"
    elif field == "automatic_peers":
        spec["external_interoperability"] = "NOT_RUN"
    return spec


def campaign_timeout_seconds(expected: dict) -> int:
    """! @brief 단일 campaign과 20회 profile phase chain의 유한 실행 상한을 구분합니다. """

    phases = PROFILE_PHASE_COUNTS.get(expected["id"])
    if phases is None:
        return MAX_TIMEOUT_SECONDS
    return expected["minimum_cycles"] * phases * PROFILE_PHASE_TIMEOUT_SECONDS


def _git_identity(root: Path) -> tuple[str, bool]:
    """! @brief dispatcher 실행 전후의 full revision과 clean 상태를 직접 확인합니다. """
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        text=True,
    ).strip()
    return revision, not dirty


def _runner_interface(path: Path,
                      subcommand: str | None = None) -> tuple[set[str], set[str]]:
    """! @brief exact runner source의 argparse option과 subcommand만 허용 목록으로 읽습니다. """
    require(path.is_file(), "registered runner missing")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    options = set()
    subcommands = set()
    dynamic = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "add_argument":
            for argument in node.args:
                if isinstance(argument, ast.Constant) and \
                        isinstance(argument.value, str) and \
                        argument.value.startswith("--"):
                    options.add(argument.value)
                elif isinstance(argument, ast.JoinedStr):
                    rendered = [""]
                    for part in argument.values:
                        if isinstance(part, ast.Constant) and \
                                isinstance(part.value, str):
                            rendered = [value + part.value for value in rendered]
                        elif isinstance(part, ast.FormattedValue) and \
                                isinstance(part.value, ast.Name):
                            values = constants.get(part.value.id.upper() + "S", ())
                            if isinstance(values, (tuple, list)) and values and \
                                    all(isinstance(value, str) for value in values):
                                rendered = [prefix + value for prefix in rendered
                                            for value in values]
                            else:
                                dynamic = True
                                rendered = []
                        else:
                            dynamic = True
                            rendered = []
                    options.update(value for value in rendered if value.startswith("--"))
        elif node.func.attr == "add_parser" and node.args and \
                isinstance(node.args[0], ast.Constant) and \
                isinstance(node.args[0].value, str):
            subcommands.add(node.args[0].value)
    if subcommand is not None:
        require(subcommand in subcommands,
                "registered runner subcommand cannot be resolved")
        help_result = subprocess.run(
            [sys.executable, "-B", str(path), subcommand, "--help"],
            cwd=str(ROOT), capture_output=True, encoding="utf-8", timeout=30,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            shell=False, check=False
        )
        require(help_result.returncode == 0,
                f"registered runner subcommand help cannot be resolved: {path.name} "
                f"(exit {help_result.returncode})")
        options = set(re.findall(
            r"(?<![A-Za-z0-9_-])(--[a-z0-9][a-z0-9-]*)",
            help_result.stdout + help_result.stderr,
        ))
    elif dynamic:
        help_result = subprocess.run(
            [sys.executable, "-B", str(path), "--help"], cwd=str(ROOT),
            capture_output=True, encoding="utf-8", timeout=30, shell=False, check=False,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        require(help_result.returncode == 0,
                f"registered runner help interface cannot be resolved: {path.name} "
                f"(exit {help_result.returncode})")
        options.update(re.findall(
            r"(?<![A-Za-z0-9_-])(--[a-z0-9][a-z0-9-]*)",
            help_result.stdout + help_result.stderr,
        ))
    return options, subcommands


def _safe_argument_value(value: str) -> bool:
    """! @brief shell을 사용하지 않아도 option 위장과 제어문자를 실행 spec에서 거부합니다. """
    return isinstance(value, str) and 0 < len(value) <= 4096 and \
        SHELL_META.search(value) is None and not value.startswith("-")


def _resolve_argument_path(value: str, root: Path) -> Path:
    """! @brief runner의 cwd 기준으로 output 인자 경로를 해석합니다. """
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _arguments_to_argv(rows: list[dict], allowed: set[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """! @brief 구조화된 option/value만 argv로 변환하고 임의 positional 삽입을 거부합니다. """
    require(isinstance(rows, list) and rows, "campaign arguments required")
    argv = []
    outputs = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"option", "values"} and
                row["option"] in allowed and
                row["option"] not in FORBIDDEN_EXECUTION_OPTIONS and
                isinstance(row["values"], list) and
                len(row["values"]) <= MAX_ARGUMENT_VALUES and
                all(_safe_argument_value(value) for value in row["values"]),
                "campaign argument is not allowed")
        argv.append(row["option"])
        argv.extend(row["values"])
        if row["option"] in OUTPUT_ARGUMENT_MODES:
            outputs.extend((row["option"], value) for value in row["values"])
    return argv, outputs


def _argument_values(rows: list[dict]) -> dict[str, list[list[str]]]:
    """! @brief 구조화 argv를 option별 occurrence로 보존합니다. """

    result: dict[str, list[list[str]]] = {}
    for row in rows:
        result.setdefault(row["option"], []).append(row["values"])
    return result


def _direct_program_images(expected: dict, rows: list[dict]) -> dict[str, Path]:
    """! @brief argv에서 역할별 단 하나의 직접 program HEX만 추출합니다. """

    arguments = _argument_values(rows)
    roles = expected["roles"]
    if not roles:
        return {}
    if expected["id"] == "m33_ecosystem":
        fixtures = arguments.get("--fixture", [])
        require(len(fixtures) == 1 and len(fixtures[0]) == 1,
                "ecosystem prepared fixture argument mismatch")
        fixture = read_json(_resolve_argument_path(fixtures[0][0], ROOT))
        boards = fixture.get("boards", [])
        require(isinstance(boards, list) and
                {row.get("role") for row in boards
                 if isinstance(row, dict)} == set(roles),
                "ecosystem fixture role denominator mismatch")
        return {
            row["role"]: Path(row["image"]).resolve()
            for row in boards
        }
    if expected["id"] == "m33_profiles_standard":
        occurrences = arguments.get("--role", [])
        require(len(occurrences) == len(roles) and
                all(len(values) == 3 for values in occurrences),
                "profile direct program role arguments mismatch")
        images = {values[0]: Path(values[2]).resolve() for values in occurrences}
        require(set(images) == set(roles), "profile direct program role denominator")
        return images
    images = {}
    for role in roles:
        cli_role = role.replace("_", "-")
        candidates = []
        for option in (f"--hex-{cli_role}", f"--{cli_role}-hex",
                       f"--{cli_role}-image"):
            candidates.extend(arguments.get(option, []))
        if len(roles) == 1:
            candidates.extend(arguments.get("--hex", []))
        if len(candidates) != 1 or len(candidates[0]) != 1:
            return {}
        images[role] = Path(candidates[0][0]).resolve()
    return images


def _validate_argument_board_binding(expected: dict, rows: list[dict],
                                     board_plan: dict[str, str]) -> None:
    """! @brief runner argv의 role probe 선택을 실행 spec mapping과 일치시킵니다. """

    arguments = _argument_values(rows)
    require(not any(option == "--board-id" or option.endswith("-board-id")
                    for option in arguments),
            "campaign execution spec cannot store a raw board ID")
    if expected["id"] == "m33_ecosystem":
        fixtures = arguments.get("--fixture", [])
        require(len(fixtures) == 1 and len(fixtures[0]) == 1,
                "ecosystem fixture board mapping missing")
        fixture = read_json(_resolve_argument_path(fixtures[0][0], ROOT))
        boards = fixture.get("boards", [])
        fixture_plan = {
            row.get("role"): row.get("probe_sha256") for row in boards
            if isinstance(row, dict)
        }
        require(isinstance(boards, list) and
                fixture_plan == {
                    role: board_plan[role] for role in expected["roles"]
                } and
                fixture.get("isolated_probe_sha256") == [board_plan["third"]],
                "ecosystem fixture probe mapping differs from board plan")
    special = {
        "--probe-first-sha256": expected["roles"][0] if expected["roles"] else None,
        "--probe-second-sha256": expected["roles"][1] if len(expected["roles"]) > 1 else None,
        "--probe-dut-sha256": expected["roles"][0] if expected["roles"] else None,
        "--probe-radio-sha256": expected["roles"][1] if len(expected["roles"]) > 1 else None,
        "--probe-ble-sha256": expected["roles"][2] if len(expected["roles"]) > 2 else None,
    }
    for option, role in special.items():
        if option in arguments:
            values = arguments[option]
            require(role is not None and values == [[board_plan[role]]],
                    "special probe argument differs from board plan")
    if "--probe-sha256" in arguments:
        require(len(expected["roles"]) == 1 and
                arguments["--probe-sha256"] == [[board_plan[expected["roles"][0]]]],
                "single probe argument differs from board plan")
    role_arguments = arguments.get("--role", [])
    if expected["id"] in {"m33_profiles_standard", "m33_profiles_native"}:
        role_mapping = {role: role for role in ("server", "client", "watcher")}
        if expected["id"] == "m33_profiles_native":
            role_mapping["watcher"] = "second_peer"
            second = arguments.get("--second-peer-role", [])
            require(len(second) == 1 and len(second[0]) == 2 and
                    second[0][0] == board_plan["second_peer"],
                    "profile second-peer probe argument differs from board plan")
        else:
            require(not arguments.get("--second-peer-role"),
                    "standard profile cannot select a second-peer phase")
        require(len(role_arguments) == len(role_mapping) and
                all(len(values) == 3 and values[0] in role_mapping and
                    values[1] == board_plan[role_mapping[values[0]]]
                    for values in role_arguments) and
                {values[0] for values in role_arguments} == set(role_mapping),
                "profile role probe argument differs from board plan")
    elif role_arguments:
        require(all(len(values) == 3 and values[0] in board_plan and
                    values[1] == board_plan[values[0]]
                    for values in role_arguments),
                "profile role probe argument differs from board plan")
    for role, expected_probe in board_plan.items():
        cli_role = role.replace("_", "-")
        candidates = []
        for option in (f"--probe-{cli_role}-sha256",
                       f"--{cli_role}-probe-sha256"):
            candidates.extend(arguments.get(option, []))
        if candidates:
            require(candidates == [[expected_probe]],
                    "role probe argument differs from board plan")
        require(not arguments.get(f"--{cli_role}-board-id", []),
                "campaign execution spec cannot store a raw board ID")


def _reject_raw_probe_identity_bytes(raw: bytes, label: str,
                                     probe_hashes: set[str] | None = None) -> None:
    """! @brief 외부 증거에 raw probe UID marker가 남는 것을 거부합니다. """
    require(RAW_PROBE_IDENTITY.search(raw) is None,
            f"{label} exposes a raw probe identity")
    if probe_hashes:
        exposed = any(
            hashlib.sha256(match.group(1).lower()).hexdigest() in probe_hashes
            for match in RAW_HEX_IDENTITY.finditer(raw)
        )
        require(not exposed, f"{label} exposes a bare raw probe identity")


def _single_argument(arguments: dict[str, list[list[str]]], option: str) -> str:
    """! @brief 준비 argv의 단일 option·단일 값을 fail-closed로 반환합니다. """

    values = arguments.get(option, [])
    require(len(values) == 1 and len(values[0]) == 1,
            f"campaign restore argument mismatch: {option}")
    return values[0][0]


def _read_regular_bytes(path: Path, label: str) -> bytes:
    """! @brief symlink를 거부하고 단일 descriptor에서 regular file byte를 읽습니다. """

    path = path.absolute()
    before = path.lstat()
    require(not stat.S_ISLNK(before.st_mode) and stat.S_ISREG(before.st_mode),
            f"{label} must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | \
        getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode),
                f"{label} descriptor is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read()
        after = path.lstat()
        require(not stat.S_ISLNK(after.st_mode) and
                (before.st_dev, before.st_ino, before.st_size,
                 before.st_mtime_ns) ==
                (opened.st_dev, opened.st_ino, opened.st_size,
                 opened.st_mtime_ns) and
                (opened.st_dev, opened.st_ino, opened.st_size) ==
                (after.st_dev, after.st_ino, after.st_size) and
                opened.st_mtime_ns == after.st_mtime_ns,
                f"{label} changed while reading")
        return raw
    finally:
        os.close(descriptor)


def _copy_new_regular(source: Path, target: Path, label: str,
                      probe_hashes: set[str], expected_sha256: str | None = None) -> str:
    """! @brief 원본을 no-follow로 읽고 새 regular file에 배타적으로 복사합니다. """

    raw = _read_regular_bytes(source, label + " source")
    source_hash = hashlib.sha256(raw).hexdigest()
    require(expected_sha256 is None or source_hash == expected_sha256,
            f"{label} source changed after plan validation")
    _reject_raw_probe_identity_bytes(raw, label + " source", probe_hashes)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    copied = _read_regular_bytes(target, label + " copy")
    require(copied == raw, f"{label} copy byte mismatch")
    _reject_raw_probe_identity_bytes(copied, label + " copy", probe_hashes)
    copied_hash = hashlib.sha256(copied).hexdigest()
    require(copied_hash == source_hash,
            f"{label} copy digest mismatch")
    return copied_hash


def _write_new_bytes(path: Path, raw: bytes, label: str) -> str:
    """! @brief transcript byte를 배타 생성하고 같은 regular file byte를 재확인합니다. """

    execution.write_new_bytes(path, raw)
    copied = _read_regular_bytes(path, label)
    require(copied == raw, f"{label} byte mismatch")
    return hashlib.sha256(copied).hexdigest()


def _watcher_fixture_bundle(fixture_path: Path, expected_hash: str,
                            probe: str, revision: str) -> tuple[dict, dict[str, Path]]:
    """! @brief third fixture descriptor를 basename·부모 경계 안에서 검증합니다. """

    import m33_diagnostics as diagnostics

    raw = _read_regular_bytes(fixture_path, "third-idle fixture")
    require(hashlib.sha256(raw).hexdigest() == expected_hash,
            "third-idle fixture hash mismatch")
    data = json.loads(raw.decode("utf-8"))
    descriptors = data.get("files")
    require(isinstance(descriptors, dict) and
            set(descriptors) == set(diagnostics.THIRD_IDLE_FILES),
            "third-idle fixture file denominator mismatch")
    parent = fixture_path.parent.resolve()
    files = {}
    for label, descriptor in descriptors.items():
        require(isinstance(descriptor, dict) and
                set(descriptor) == {"path", "sha256"} and
                isinstance(descriptor["path"], str) and
                Path(descriptor["path"]).name == descriptor["path"] and
                SHA.fullmatch(descriptor["sha256"]),
                f"third-idle {label} descriptor mismatch")
        path = fixture_path.parent / descriptor["path"]
        require(path.absolute().parent.resolve() == parent,
                f"third-idle {label} escapes fixture directory")
        file_raw = _read_regular_bytes(path, f"third-idle {label}")
        require(hashlib.sha256(file_raw).hexdigest() == descriptor["sha256"],
                f"third-idle {label} hash mismatch")
        files[label] = path.absolute()
    watcher = diagnostics.load_watcher_fixture(
        fixture_path, expected_hash, probe
    )
    require(watcher["data"].get("revisions", {}).get("core") == revision,
            "third-idle restore source revision mismatch")
    return watcher, files


def _seal_restore_plan(plan: dict) -> dict:
    """! @brief 검증된 모든 복원 입력의 byte digest snapshot을 plan에 고정합니다. """

    observed = {
        "images": {
            role: hashlib.sha256(_read_regular_bytes(
                path, f"{role} restore image snapshot"
            )).hexdigest()
            for role, path in plan["images"].items()
        },
        "records": {
            role: hashlib.sha256(_read_regular_bytes(
                path, f"{role} restore record snapshot"
            )).hexdigest()
            for role, path in plan["records"].items()
        },
        "contract": {
            label: hashlib.sha256(_read_regular_bytes(
                path, f"{label} restore contract snapshot"
            )).hexdigest()
            for label, path in plan["contract_inputs"].items()
        },
    }
    expected = plan.pop("validated_sha256", observed)
    require(observed == expected,
            "restore input changed between provenance validation and snapshot")
    plan["input_sha256"] = expected
    return plan


def _state_restore_plan(expected: dict, row: dict, revision: str,
                        root: Path = ROOT) -> dict | None:
    """! @brief 덮인 보드 상태를 복원할 exact image·record·probe 계약을 계산합니다. """

    mode = PRE_RUN_STATE_RESTORE.get(expected["id"])
    if mode is None:
        return None
    arguments = _argument_values(row["arguments"])
    if mode in {"direct", "ecosystem_isolated"}:
        active_roles = tuple(expected["roles"])
        roles = _preparation_roles(expected)
        images = _direct_program_images(expected, row["arguments"])
        board_probes = {
            entry["role"]: entry["probe_sha256"] for entry in row["boards"]
        }
        require(set(images) == set(active_roles) and
                set(board_probes) == set(roles) and
                len(set(board_probes.values())) == len(roles) and
                all(SHA.fullmatch(value) for value in board_probes.values()),
                "direct state restore role/probe denominator mismatch")
        records: dict[str, Path] = {}
        contract_inputs: dict[str, Path] = {}
        validated_sha256 = {
            "images": {}, "records": {}, "contract": {},
        }
        if expected["id"] == "m33_ecosystem":
            fixture_path = _resolve_argument_path(
                _single_argument(arguments, "--fixture"), root
            )
            import m33_ecosystem_hil as ecosystem
            import m33_w06_runtime_fixture as runtime_fixture

            fixture_raw = _read_regular_bytes(
                fixture_path, "ecosystem restore fixture"
            )
            fixture = json.loads(fixture_raw.decode("utf-8"))
            ecosystem.validate_fixture(fixture)
            boards = {
                entry.get("role"): entry for entry in fixture.get("boards", [])
                if isinstance(entry, dict)
            }
            require(set(boards) == set(active_roles) and
                    fixture.get("isolated_probe_sha256") ==
                    [board_probes["third"]],
                    "ecosystem restore fixture role denominator mismatch")
            for role in active_roles:
                record = Path(boards[role].get("build_record", "")).resolve()
                require(record.is_file() and
                        digest(record) == boards[role].get("build_record_sha256") and
                        Path(boards[role].get("image", "")).resolve() == images[role] and
                        digest(images[role]) == boards[role].get("image_sha256") and
                        boards[role].get("probe_sha256") == board_probes[role],
                        f"ecosystem {role} restore provenance mismatch")
                records[role] = record
                validated_sha256["images"][role] = \
                    boards[role]["image_sha256"]
                validated_sha256["records"][role] = \
                    boards[role]["build_record_sha256"]
            preflight_path = Path(fixture.get("preflight_evidence", "")).absolute()
            require(preflight_path.parent.resolve() == fixture_path.parent.resolve() and
                    preflight_path.name == "ecosystem-preflight.json",
                    "ecosystem preflight path escapes fixture directory")
            preflight_raw = _read_regular_bytes(
                preflight_path, "ecosystem preflight"
            )
            require(hashlib.sha256(preflight_raw).hexdigest() ==
                    fixture.get("preflight_sha256"),
                    "ecosystem preflight hash mismatch")
            preflight = json.loads(preflight_raw.decode("utf-8"))
            third_fixture = (fixture_path.parent / "third-idle" /
                             "third-idle-fixture.json").absolute()
            watcher, files = _watcher_fixture_bundle(
                third_fixture,
                preflight.get("third", {}).get("fixture_sha256", ""),
                board_probes["third"], revision
            )
            ports = {role: boards[role]["port"] for role in active_roles}
            runtime_fixture.validate_third_board_audit(
                preflight.get("third"),
                {
                    "client": board_probes["client"],
                    "peer": board_probes["peer"],
                    "third": board_probes["third"],
                },
                ports,
                third_fixture,
            )
            images["third"] = files["image"]
            records["third"] = third_fixture
            contract_inputs = {
                "ecosystem_fixture": fixture_path,
                "ecosystem_preflight": preflight_path,
                "third_fixture": third_fixture,
                **{f"third_{label}": path for label, path in files.items()},
            }
            validated_sha256["images"]["third"] = \
                watcher["data"]["files"]["image"]["sha256"]
            validated_sha256["records"]["third"] = \
                preflight["third"]["fixture_sha256"]
            validated_sha256["contract"] = {
                "ecosystem_fixture": hashlib.sha256(fixture_raw).hexdigest(),
                "ecosystem_preflight": hashlib.sha256(preflight_raw).hexdigest(),
                "third_fixture": preflight["third"]["fixture_sha256"],
                **{
                    f"third_{label}": watcher["data"]["files"][label]["sha256"]
                    for label in files
                },
            }
        else:
            require(expected["id"] == "m31_bap_duplex",
                    "unknown direct state restore campaign")
            from ble_pair_hil_common import validate_build_record

            lock = read_json(root / "tools/ci/ncs-3.4.0.lock.json")
            applications = {
                role: root / source["path"]
                for role, source in zip(
                    active_roles, expected["applications"], strict=True
                )
            }
            for role in active_roles:
                record = build_record_path(images[role])
                validated = validate_build_record(
                    images[role], revision, lock["board"]["revision"],
                    applications[role]
                )
                require(validated.get("record_sha256") == digest(record),
                        f"BAP {role} restore build record mismatch")
                records[role] = record
                validated_sha256["images"][role] = validated["hex_sha256"]
                validated_sha256["records"][role] = validated["record_sha256"]
                cli_role = role.replace("_", "-")
                config = _resolve_argument_path(
                    _single_argument(arguments, f"--{cli_role}-config"), root
                )
                config_raw = _read_regular_bytes(config, f"BAP {role} config")
                lines = config_raw.decode("utf-8").splitlines()
                require("CONFIG_LIBLC3=y" in lines and "CONFIG_FPU=y" in lines,
                        f"BAP {role} restore config mismatch")
                contract_inputs[f"{role}_config"] = config
                validated_sha256["contract"][f"{role}_config"] = \
                    hashlib.sha256(config_raw).hexdigest()
        require(all(image.is_file() and image.suffix.lower() == ".hex"
                    for image in images.values()) and
                all(record.is_file() for record in records.values()),
                "direct state restore input is missing")
        return _seal_restore_plan({
            "mode": mode,
            "campaign_id": expected["id"],
            "revision": revision,
            "roles": roles,
            "images": images,
            "records": records,
            "probes": board_probes,
            "all_probes": board_probes,
            "contract_inputs": contract_inputs,
            "validated_sha256": validated_sha256,
            **({
                "ports": ports,
                "fixture": third_fixture,
                "watcher": watcher,
            } if mode == "ecosystem_isolated" else {}),
        })

    require(mode == "third_idle" and
            expected["id"] == "m33_diagnostics_dtm",
            "unknown third-idle state restore campaign")
    fixture_path = _resolve_argument_path(
        _single_argument(arguments, "--third-idle-fixture"), root
    )
    argument_probes = {
        "tx": _single_argument(arguments, "--tx-probe-sha256"),
        "rx": _single_argument(arguments, "--rx-probe-sha256"),
        "third": _single_argument(arguments, "--third-probe-sha256"),
    }
    board_probes = {
        entry["role"]: entry["probe_sha256"] for entry in row["boards"]
    }
    require(board_probes == argument_probes and
            all(SHA.fullmatch(value) for value in argument_probes.values()) and
            len(set(argument_probes.values())) == 3,
            "third-idle restore probe denominator mismatch")
    fixture_hash = hashlib.sha256(_read_regular_bytes(
        fixture_path, "third-idle fixture"
    )).hexdigest()
    watcher, files = _watcher_fixture_bundle(
        fixture_path, fixture_hash, argument_probes["third"], revision
    )
    ports = {
        "tx": _single_argument(arguments, "--tx-port"),
        "rx": _single_argument(arguments, "--rx-port"),
    }
    return _seal_restore_plan({
        "mode": mode,
        "campaign_id": expected["id"],
        "revision": revision,
        "roles": ("third",),
        "images": {"third": files["image"]},
        "records": {"third": fixture_path},
        "probes": {"third": argument_probes["third"]},
        "all_probes": argument_probes,
        "ports": ports,
        "fixture": fixture_path,
        "watcher": watcher,
        "contract_inputs": {"fixture": fixture_path, **files},
        "validated_sha256": {
            "images": {
                "third": watcher["data"]["files"]["image"]["sha256"],
            },
            "records": {"third": fixture_hash},
            "contract": {
                "fixture": fixture_hash,
                **{
                    label: watcher["data"]["files"][label]["sha256"]
                    for label in files
                },
            },
        },
    })


def _restore_contract_files(plan: dict, receipt_path: Path) -> dict[str, dict]:
    """! @brief 복원 판단에 사용한 config·fixture byte를 receipt 옆에 보존합니다. """

    references = {}
    probe_hashes = set(plan["all_probes"].values())
    for label, source in plan["contract_inputs"].items():
        suffix = source.suffix if source.suffix else ".bin"
        target = receipt_path.with_name(
            f"{receipt_path.stem}.contract-{label}{suffix}"
        )
        copied_hash = _copy_new_regular(
            source, target, f"state restore {label}", probe_hashes,
            plan["input_sha256"]["contract"][label]
        )
        references[label] = {
            "path": target.name,
            "sha256": copied_hash,
        }
    return references


def _restore_action_order(plan: dict) -> list[str]:
    """! @brief 복원 receipt의 program-reset-readback-state 순서를 반환합니다. """

    order = [
        f"{role}:sector-program-no-reset" for role in plan["roles"]
    ] + [
        f"{role}:software-reset" for role in plan["roles"]
    ] + ["all:live-readback"]
    if plan["mode"] in {"third_idle", "ecosystem_isolated"}:
        order.extend(("third:uart-stop", "third:halt-read-only-audit"))
    return order


def _wait_watcher_record(port, kinds: set[str], revision: str,
                         deadline: float, transcript: list[str]) -> tuple[str, dict]:
    """! @brief 복원한 watcher의 bounded UART record를 strict protocol로 읽습니다. """

    from m33_profile_run import fields

    while time.monotonic() < deadline:
        line = port.readline().decode("ascii", errors="strict").strip()
        if not line:
            continue
        require(len(line) <= 512, "restored watcher protocol line too long")
        transcript.append(line)
        if not line.startswith("M33PROFILE|1|"):
            continue
        pieces = line.split("|")
        require(len(pieces) >= 4, "restored watcher protocol record malformed")
        kind = pieces[2]
        values = fields(line)
        require(values.get("role") == "watcher" and
                values.get("core") == revision,
                "restored watcher role/source mismatch")
        require(kind != "FAIL", "restored watcher reported FAIL")
        if kind in kinds:
            return kind, values
    raise ValueError("restored watcher protocol timeout")


def _stop_restored_watcher(plan: dict, transcript_path: Path) -> dict:
    """! @brief third image를 reset 뒤 미시작 STOPPED 상태로 결정적으로 되돌립니다. """

    from m32_ble_capability_run import discover
    from m33_profile_run import validate_stop_record
    from m6_serial_echo import import_pyserial

    serial_module, list_ports = import_pyserial()
    _uid, _volume, port_name = discover(
        plan["probes"]["third"], list_ports
    )
    fixture_port = plan["watcher"]["data"].get("port")
    require(isinstance(fixture_port, str) and
            fixture_port.casefold() == port_name.casefold(),
            "third-idle restore VCOM/probe mapping changed")
    transcript: list[str] = []
    serial_port = serial_module.Serial(
        port_name, 115200, timeout=0.05, write_timeout=1.0
    )
    try:
        serial_port.reset_input_buffer()
        serial_port.write(b"M33PROFILE|1|PROBE\n")
        serial_port.flush()
        kind, values = _wait_watcher_record(
            serial_port, {"READY"}, plan["revision"],
            time.monotonic() + 10.0, transcript
        )
        require(kind == "READY" and values.get("nonce") == "",
                "restored watcher is not fresh READY")
        nonce = plan["watcher"]["data"]["nonce"]
        serial_port.write(
            f"M33PROFILE|1|STOP|nonce={nonce}\n".encode("ascii")
        )
        serial_port.flush()
        deadline = time.monotonic() + 15.0
        server_stats = False
        stopped = False
        while time.monotonic() < deadline and not stopped:
            kind, values = _wait_watcher_record(
                serial_port, {"SERVER_STATS", "STOPPED"},
                plan["revision"], deadline, transcript
            )
            if kind == "SERVER_STATS":
                require(not server_stats and values.get("nonce") == nonce,
                        "restored watcher SERVER_STATS mismatch")
                server_stats = True
            else:
                stopped = validate_stop_record(kind, values, nonce, stopped)
        require(server_stats and stopped,
                "restored watcher STOPPED denominator missing")
    finally:
        serial_port.close()
    require(getattr(serial_port, "is_open", False) is False,
            "restored watcher serial port remained open")
    transcript_raw = ("\n".join(transcript) + "\n").encode("ascii")
    transcript_hash = _write_new_bytes(
        transcript_path, transcript_raw, "restored watcher transcript"
    )
    return {
        "port_binding": "probe_sha256_verified",
        "ready": "PASS",
        "server_stats": "PASS",
        "stopped": "PASS",
        "serial_close": "PASS",
        "transcript": {
            "path": transcript_path.name,
            "sha256": transcript_hash,
        },
    }


def _validate_restored_watcher_transcript(path: Path, revision: str,
                                          nonce: str) -> None:
    """! @brief 저장 transcript를 READY→SERVER_STATS→STOPPED로 재파싱합니다. """

    from m33_profile_run import fields, validate_stop_record

    raw = _read_regular_bytes(path, "restored watcher transcript")
    lines = raw.decode("ascii", errors="strict").splitlines()
    require(len(lines) == 3, "restored watcher transcript denominator mismatch")
    records = []
    for line in lines:
        require(len(line) <= 512 and line.startswith("M33PROFILE|1|"),
                "restored watcher transcript protocol mismatch")
        pieces = line.split("|")
        require(len(pieces) >= 4, "restored watcher transcript malformed")
        values = fields(line)
        require(values.get("role") == "watcher" and
                values.get("core") == revision and pieces[2] != "FAIL",
                "restored watcher transcript role/source mismatch")
        records.append((pieces[2], values))
    require([kind for kind, _values in records] ==
            ["READY", "SERVER_STATS", "STOPPED"] and
            records[0][1].get("nonce") == "" and
            records[1][1].get("nonce") == nonce,
            "restored watcher transcript lifecycle mismatch")
    require(validate_stop_record(
        records[2][0], records[2][1], nonce, False
    ), "restored watcher STOPPED record mismatch")


def _validate_state_restore_receipt(path: Path, expected: dict, row: dict,
                                    revision: str, root: Path = ROOT) -> dict:
    """! @brief pre-run sector program·readback·상태 복원 receipt를 재검증합니다. """

    plan = _state_restore_plan(expected, row, revision, root)
    require(plan is not None,
            "required pre-run state restore receipt is missing")
    receipt = json.loads(_read_regular_bytes(
        path, "pre-run state restore receipt"
    ).decode("utf-8"))
    required = {
        "schema_version", "kind", "campaign_id", "mode", "source_revision",
        "source_clean", "started_ns", "finished_ns", "safety", "contract",
        "hardware", "post_reset", "state", "action_order", "sha256",
    }
    require(set(receipt) == required and receipt["schema_version"] == 1 and
            receipt["kind"] == "m33_campaign_pre_run_state_restore" and
            receipt["campaign_id"] == expected["id"] and
            receipt["mode"] == plan["mode"] and
            receipt["source_revision"] == revision and
            receipt["source_clean"] is True and
            type(receipt["started_ns"]) is int and
            type(receipt["finished_ns"]) is int and
            receipt["finished_ns"] > receipt["started_ns"] and
            receipt["safety"] == {
                "probe_identity": "sha256-only",
                "erase": "sector",
                "auto_unlock": False,
                "mass_erase": False,
                "automatic_recover": False,
                "reset": "software",
                "lock_authority": "parent-continuous",
                "child_lock_namespace": "private",
                "failure_recovery": "new-output-root-required",
            }, "pre-run state restore receipt mismatch")
    contract = receipt["contract"]
    require(isinstance(contract, dict) and
            set(contract) == set(plan["contract_inputs"]),
            "pre-run state restore contract denominator mismatch")
    for label, reference in contract.items():
        copied = _adjacent_native_file(
            reference, path.parent, f"state restore {label}"
        )
        copied_raw = _read_regular_bytes(copied, f"state restore {label} copy")
        source_raw = _read_regular_bytes(
            plan["contract_inputs"][label], f"state restore {label} source"
        )
        probe_hashes = set(plan["all_probes"].values())
        _reject_raw_probe_identity_bytes(
            copied_raw, f"state restore {label} copy", probe_hashes
        )
        _reject_raw_probe_identity_bytes(
            source_raw, f"state restore {label} source", probe_hashes
        )
        require(copied_raw == source_raw,
                f"state restore {label} source byte mismatch")
    hardware = receipt["hardware"]
    require(isinstance(hardware, list) and
            [entry.get("role") for entry in hardware
             if isinstance(entry, dict)] == list(plan["roles"]),
            "pre-run state restore hardware denominator mismatch")
    validated = {
        entry["role"]: _validate_exact_program_row(
            entry, path, entry.get("role", "")
        )
        for entry in hardware
    }
    exact_program_bytes = {
        entry["role"]: sum(
            len(raw) for _address, raw in intel_hex_ranges(
                _adjacent_native_file(
                    entry["image"], path.parent,
                    f"{entry['role']} stored restore image"
                )
            )
        )
        for entry in hardware
    }
    require({role: value["probe_sha256"] for role, value in validated.items()} ==
            plan["probes"] and
            all(value["program_mode"] == "pyocd-sector-no-reset" and
                value["programmed_bytes"] == exact_program_bytes[role]
                for role, value in validated.items()) and
            all(value["image_sha256"] == hashlib.sha256(_read_regular_bytes(
                    plan["images"][role], f"{role} restore image source"
                )).hexdigest()
                for role, value in validated.items()) and
            all(value["build_record_sha256"] == hashlib.sha256(
                    _read_regular_bytes(
                        plan["records"][role],
                        f"{role} restore build record source"
                    )
                ).hexdigest()
                for role, value in validated.items()),
            "pre-run state restore exact no-reset program mismatch")
    reset_states = {}
    for entry in hardware:
        readback_path = _adjacent_native_file(
            entry["readback"], path.parent,
            f"{entry['role']} post-reset readback"
        )
        readback = json.loads(_read_regular_bytes(
            readback_path, f"{entry['role']} post-reset readback"
        ).decode("utf-8"))
        reset_states[entry["role"]] = {
            "pre_state": readback.get("pre_state"),
            "post_state": readback.get("post_state"),
            "resumed": readback.get("resumed"),
            "restored": readback.get("restored"),
        }
    require(receipt["post_reset"] == reset_states and
            set(reset_states) == set(plan["roles"]) and
            all(value == {
                "pre_state": "RUNNING",
                "post_state": "RUNNING",
                "resumed": True,
                "restored": True,
            } for value in reset_states.values()),
            "pre-run software reset did not leave every role RUNNING")
    require(receipt["action_order"] == _restore_action_order(plan),
            "pre-run state restore action order mismatch")
    if plan["mode"] in {"third_idle", "ecosystem_isolated"}:
        state = receipt["state"]
        require(isinstance(state, dict) and set(state) == {
                    "port_binding", "ready", "server_stats", "stopped",
                    "serial_close", "transcript", "idle_audit",
                } and
                state.get("ready") == "PASS" and
                state.get("server_stats") == "PASS" and
                state.get("stopped") == "PASS" and
                state.get("serial_close") == "PASS" and
                state.get("port_binding") == "probe_sha256_verified" and
                isinstance(state.get("idle_audit"), dict) and
                state["idle_audit"].get("probe_sha256") ==
                plan["probes"]["third"],
                "third-idle restored lifecycle mismatch")
        transcript_path = _adjacent_native_file(
            state["transcript"], path.parent,
            "third-idle restore transcript"
        )
        _validate_restored_watcher_transcript(
            transcript_path, revision, plan["watcher"]["data"]["nonce"]
        )
        import m33_w06_runtime_fixture as runtime_fixture

        if plan["mode"] == "ecosystem_isolated":
            audit_hashes = plan["all_probes"]
            audit_ports = plan["ports"]
        else:
            audit_hashes = {
                "client": plan["all_probes"]["tx"],
                "peer": plan["all_probes"]["rx"],
                "third": plan["all_probes"]["third"],
            }
            audit_ports = {
                "client": plan["ports"]["tx"],
                "peer": plan["ports"]["rx"],
            }
        runtime_fixture.validate_third_board_audit(
            state["idle_audit"], audit_hashes, audit_ports, plan["fixture"]
        )
    else:
        require(receipt["state"] == {"runtime": "software_reset_ready"},
                "direct campaign restored state mismatch")
    unsigned = {key: value for key, value in receipt.items() if key != "sha256"}
    require(receipt["sha256"] == hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest(), "pre-run state restore digest mismatch")
    return receipt


def _restore_campaign_state(expected: dict, row: dict, native_path: Path,
                            revision: str, root: Path = ROOT,
                            plan: dict | None = None,
                            authority: _RestoreAuthority | None = None) -> Path | None:
    """! @brief 선택 campaign 직전에 exact state를 sector program·readback으로 복원합니다. """

    plan = plan or _state_restore_plan(expected, row, revision, root)
    if plan is None:
        return None
    require(isinstance(authority, _RestoreAuthority) and
            authority._secret is _RESTORE_AUTHORITY_SECRET and
            authority.active and authority.hashes == tuple(sorted(
                plan["all_probes"].values()
            )), "active parent probe-lock authority required")
    receipt_path = native_path.with_name(
        f"{native_path.stem}.pre-run-restore.json"
    )
    require(not receipt_path.exists(), "pre-run state restore overwrite refused")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    sidecars = reserve_sidecars(receipt_path, plan["roles"])
    probe_hashes = set(plan["all_probes"].values())
    for role in plan["roles"]:
        _copy_new_regular(
            plan["images"][role], sidecars[role]["image"],
            f"{role} restore image", probe_hashes,
            plan["input_sha256"]["images"][role]
        )
        _copy_new_regular(
            plan["records"][role], sidecars[role]["build_record"],
            f"{role} restore build record", probe_hashes,
            plan["input_sha256"]["records"][role]
        )
    contract = _restore_contract_files(plan, receipt_path)
    flash_records = {}
    started_ns = time.monotonic_ns()
    from ble_pair_hil_common import (
        flash_image_pyocd_sha256, reset_target_pyocd_sha256,
    )
    for role in plan["roles"]:
        mode, programmed = flash_image_pyocd_sha256(
            role, plan["probes"][role], sidecars[role]["image"],
            RESTORE_TIMEOUT_SECONDS, defer_reset=True,
            expected_sha256=plan["input_sha256"]["images"][role]
        )
        flash_records[role] = {"mode": mode, "bytes": programmed}
    for role in plan["roles"]:
        reset_target_pyocd_sha256(
            role, plan["probes"][role], RESTORE_TIMEOUT_SECONDS
        )
    readbacks, authority = readback_programmed_images_by_hash(
        plan["probes"],
        {role: sidecars[role]["image"] for role in plan["roles"]},
        sidecars,
    )
    validate_programming_receipt(authority, plan["roles"], readbacks)
    post_reset = {
        role: {
            "pre_state": readbacks[role].get("pre_state"),
            "post_state": readbacks[role].get("post_state"),
            "resumed": readbacks[role].get("resumed"),
            "restored": readbacks[role].get("restored"),
        }
        for role in plan["roles"]
    }
    require(all(value == {
        "pre_state": "RUNNING",
        "post_state": "RUNNING",
        "resumed": True,
        "restored": True,
    } for value in post_reset.values()),
            "software reset did not leave every restored role RUNNING")
    if plan["mode"] in {"third_idle", "ecosystem_isolated"}:
        transcript_path = receipt_path.with_name(
            f"{receipt_path.stem}.third.transcript.log"
        )
        state = _stop_restored_watcher(plan, transcript_path)
        from m33_w06_runtime_fixture import (
            audit_third_board, validate_third_board_audit,
        )

        if plan["mode"] == "ecosystem_isolated":
            audit_hashes = plan["all_probes"]
            audit_ports = plan["ports"]
        else:
            audit_hashes = {
                "client": plan["all_probes"]["tx"],
                "peer": plan["all_probes"]["rx"],
                "third": plan["all_probes"]["third"],
            }
            audit_ports = {
                "client": plan["ports"]["tx"],
                "peer": plan["ports"]["rx"],
            }
        state["idle_audit"] = audit_third_board(
            audit_hashes, audit_ports, plan["fixture"]
        )
        validate_third_board_audit(
            state["idle_audit"], audit_hashes, audit_ports, plan["fixture"]
        )
    else:
        state = {"runtime": "software_reset_ready"}
    build_records = {
        role: {"record_sha256": hashlib.sha256(_read_regular_bytes(
            sidecars[role]["build_record"], f"{role} build record copy"
        )).hexdigest()}
        for role in plan["roles"]
    }
    exact = exact_program_evidence(
        plan["roles"], plan["probes"], sidecars, flash_records,
        build_records, readbacks
    )
    revision_after, clean_after = _git_identity(root)
    require(clean_after and revision_after == revision,
            "source changed during pre-run state restore")
    finished_ns = max(time.monotonic_ns(), started_ns + 1)
    receipt = {
        "schema_version": 1,
        "kind": "m33_campaign_pre_run_state_restore",
        "campaign_id": expected["id"],
        "mode": plan["mode"],
        "source_revision": revision,
        "source_clean": True,
        "started_ns": started_ns,
        "finished_ns": finished_ns,
        "safety": {
            "probe_identity": "sha256-only",
            "erase": "sector",
            "auto_unlock": False,
            "mass_erase": False,
            "automatic_recover": False,
            "reset": "software",
            "lock_authority": "parent-continuous",
            "child_lock_namespace": "private",
            "failure_recovery": "new-output-root-required",
        },
        "contract": contract,
        "hardware": [
            {"role": role, **exact[role]} for role in plan["roles"]
        ],
        "post_reset": post_reset,
        "state": state,
        "action_order": _restore_action_order(plan),
    }
    receipt["sha256"] = hashlib.sha256(json.dumps(
        receipt, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    _write_new_json(receipt_path, receipt)
    _validate_state_restore_receipt(
        receipt_path, expected, row, revision, root
    )
    return receipt_path


@contextmanager
def _campaign_probe_authority(plan: dict | None, native_path: Path):
    """! @brief parent lock을 복원부터 child 증거 확정까지 연속 소유합니다. """

    if plan is None:
        yield None, None
        return
    from m33_diagnostics import HashedProbeLocks

    native_path.parent.mkdir(parents=True, exist_ok=True)
    hashes = list(plan["all_probes"].values())
    with HashedProbeLocks(hashes):
        authority = _RestoreAuthority(_RESTORE_AUTHORITY_SECRET, hashes)
        try:
            with tempfile.TemporaryDirectory(
                    prefix=f".{native_path.stem}.child-locks-",
                    dir=native_path.parent) as lock_directory:
                environment = os.environ.copy()
                environment.update({
                    "TMPDIR": lock_directory,
                    "TEMP": lock_directory,
                    "TMP": lock_directory,
                })
                yield environment, authority
        finally:
            authority.close()


def _central_program_hardware(expected: dict, row: dict,
                              native_path: Path) -> list[dict]:
    """! @brief direct HEX군을 live probe hash에 결합해 same-process readback합니다. """

    images = _direct_program_images(expected, row["arguments"])
    require(set(images) == set(expected["roles"]),
            "campaign has no unique direct program image mapping")
    require(all(path.is_file() and path.suffix.lower() == ".hex"
                for path in images.values()), "direct program HEX is missing")
    probes = {
        entry["role"]: entry["probe_sha256"] for entry in row["boards"]
        if entry["role"] in expected["roles"]
    }
    require(set(probes) == set(images), "direct program probe mapping mismatch")
    native = read_json(native_path)
    declared = native.get("m33_dispatch_attestation", {}).get("hardware", [])
    declared_by_role = {
        entry.get("role"): entry for entry in declared if isinstance(entry, dict)
    }
    copied_build_records: dict[str, Path] | None = None
    if expected["id"] == "m33_ecosystem" and not declared_by_role:
        arguments = _argument_values(row["arguments"])
        fixtures = arguments.get("--fixture", [])
        require(len(fixtures) == 1 and len(fixtures[0]) == 1,
                "ecosystem fixture program mapping missing")
        fixture = read_json(_resolve_argument_path(fixtures[0][0], ROOT))
        board_rows = {
            entry.get("role"): entry for entry in fixture.get("boards", [])
            if isinstance(entry, dict)
        }
        require(set(board_rows) == set(expected["roles"]) and
                fixture.get("identity") == native.get("identity") and
                fixture.get("identity", "")[:40] ==
                native.get("identity", "")[:40],
                "ecosystem fixture/native identity mismatch")
        copied_build_records = {}
        for role in expected["roles"]:
            board = board_rows[role]
            record_path = Path(board.get("build_record", "")).resolve()
            record = read_json(record_path)
            flash = board.get("flash")
            require(board.get("probe_sha256") == probes[role] and
                    Path(board.get("image", "")).resolve() == images[role] and
                    board.get("image_sha256") == digest(images[role]) and
                    board.get("build_record_sha256") == digest(record_path) and
                    record.get("source_revision") == native["identity"][:40] and
                    record.get("source_clean") is True and
                    record.get("identity") == native["identity"] and
                    record.get("role") == role and
                    record.get("image_sha256") == digest(images[role]) and
                    isinstance(flash, dict),
                    f"ecosystem {role} build/program provenance mismatch")
            declared_by_role[role] = {"flash": flash}
            copied_build_records[role] = record_path
    if expected["id"] in DERIVED_FLAT_CAMPAIGNS and not declared_by_role:
        from ble_pair_hil_common import validate_build_record

        argument_values = _argument_values(row["arguments"])
        applications = {
            role: ROOT / application
            for role, application in zip(
                expected["roles"], expected["applications"], strict=True
            )
        }
        lock = read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        validated_build_records = {
            role: validate_build_record(
                images[role], native["core_revision"],
                lock["board"]["revision"], applications[role]
            )
            for role in expected["roles"]
        }
        require(native.get("build_records") == validated_build_records,
                "flat native strict build record mismatch")
        for role in expected["roles"]:
            cli_role = role.replace("_", "-")
            require(native.get(f"{role}_probe_sha256") == probes[role] and
                    native.get(f"{role}_image_sha256") == digest(images[role]),
                    "flat native probe or image mapping mismatch")
            if expected["id"] == "m31_bap_duplex":
                config_value = argument_values.get(f"--{cli_role}-config", [])
                flash_value = argument_values.get(
                    f"--{cli_role}-flash-record", []
                )
                require(len(config_value) == 1 and len(config_value[0]) == 1 and
                        len(flash_value) == 1 and len(flash_value[0]) == 1,
                        "BAP config/flash argument mapping mismatch")
                config_path = _resolve_argument_path(config_value[0][0], ROOT)
                flash_path = _resolve_argument_path(flash_value[0][0], ROOT)
                require(digest(config_path) == native.get(
                    f"{role}_config_sha256"
                ) and digest(flash_path) == native.get(
                    f"{role}_flash_record_sha256"
                ), "BAP config/flash byte mismatch")
                flash_record = json.loads(
                    flash_path.read_text(encoding="utf-8-sig")
                )
                flash = flash_record.get(f"{role}_flash", {})
                require(flash_record.get("status") == "FLASH_PREPARED" and
                        flash_record.get(f"{role}_probe_sha256") == probes[role] and
                        flash_record.get(f"{role}_image_sha256") == digest(images[role]) and
                        flash_record.get("auto_unlock") is False and
                        flash_record.get("erase") == "sector" and
                        isinstance(flash.get("mode"), str) and
                        flash["mode"].startswith("pyocd-sector") and
                        integer(flash.get("bytes"), 1),
                        "BAP prepared sector flash mismatch")
                mode = flash["mode"]
                programmed_bytes = flash["bytes"]
            else:
                flash = native.get(f"{role}_flash")
                require(isinstance(flash, list) and len(flash) == 2 and
                        isinstance(flash[0], str) and
                        flash[0].startswith("pyocd-sector") and
                        isinstance(flash[1], str) and flash[1].isdecimal() and
                        int(flash[1]) > 0,
                        "CS RAS sector flash mismatch")
                mode = flash[0]
                programmed_bytes = int(flash[1])
            declared_by_role[role] = {
                "flash": {
                    "mode": mode,
                    "programmed_bytes": programmed_bytes,
                    "erase": "sector",
                    "auto_unlock": False,
                    "mass_erase": False,
                    "automatic_recover": False,
                },
            }
    if expected["id"] in DERIVED_LEGACY_CAMPAIGNS and not declared_by_role:
        image_rows = native.get("images", {})
        board_rows = native.get("boards", {})
        require(isinstance(image_rows, dict) and
                set(image_rows) == set(expected["roles"]) and
                isinstance(board_rows, dict) and
                set(board_rows) == set(expected["roles"]),
                "legacy native program role denominator mismatch")
        for role in expected["roles"]:
            board = board_rows[role]
            probe_sha256 = board.get("probe_sha256")
            if expected["id"] in HASH_ONLY_LEGACY_CAMPAIGNS:
                require(set(board).issuperset({"probe_sha256"}) and
                        "daplink_uid" not in board and
                        probe_sha256 == probes[role],
                        "hash-only legacy native probe mapping mismatch")
            else:
                board_id = board.get("daplink_uid", "")
                require(isinstance(board_id, str) and board_id and
                        hashlib.sha256(
                            board_id.strip().lower().encode("ascii")
                        ).hexdigest() == probes[role],
                        "legacy native board ID mapping mismatch")
            flash_mode = image_rows[role].get("flash_sequence")
            flash_bytes = image_rows[role].get("flash_bytes")
            require(isinstance(flash_mode, str) and
                    flash_mode.startswith("pyocd-sector") and
                    isinstance(flash_bytes, str) and
                    flash_bytes.isdecimal() and int(flash_bytes) > 0 and
                    image_rows[role].get("size") == images[role].stat().st_size and
                    image_rows[role].get("sha256") == digest(images[role]) and
                    SHA.fullmatch(image_rows[role].get(
                        "build_record", {}
                    ).get("record_sha256", "")),
                    "legacy native probe or sector program mismatch")
            declared_by_role[role] = {
                "flash": {
                    "mode": flash_mode,
                    "programmed_bytes": int(flash_bytes),
                    "erase": "sector",
                    "auto_unlock": False,
                    "mass_erase": False,
                    "automatic_recover": False,
                },
            }
    require(set(declared_by_role) == set(expected["roles"]),
            "native program safety role denominator mismatch")
    dispatcher_path = native_path.with_name(
        native_path.stem + ".dispatcher.json"
    )
    sidecars = reserve_sidecars(dispatcher_path, tuple(expected["roles"]))
    if copied_build_records is None:
        copy_program_inputs(images, sidecars)
    else:
        for role in expected["roles"]:
            shutil.copyfile(images[role], sidecars[role]["image"])
            shutil.copyfile(
                copied_build_records[role], sidecars[role]["build_record"]
            )
    if expected["id"] in DERIVED_LEGACY_CAMPAIGNS:
        require(all(
            digest(sidecars[role]["build_record"]) ==
            native["images"][role]["build_record"]["record_sha256"]
            for role in expected["roles"]
        ), "legacy native build record byte mismatch")
    records, receipt = readback_programmed_images_by_hash(
        probes, images, sidecars
    )
    validate_programming_receipt(receipt, tuple(expected["roles"]), records)
    return [
        {
            "role": role,
            "probe_sha256": probes[role],
            "image": {"path": sidecars[role]["image"].name,
                      "sha256": digest(sidecars[role]["image"])},
            "build_record": {"path": sidecars[role]["build_record"].name,
                             "sha256": digest(sidecars[role]["build_record"])},
            "flash": declared_by_role[role].get("flash"),
            "readback": {"path": sidecars[role]["readback"].name,
                         "sha256": digest(sidecars[role]["readback"])},
        }
        for role in expected["roles"]
    ]


def campaign_dispatch_matrix(root: Path = ROOT) -> dict:
    """! @brief 등록된 unique campaign의 실제 dispatch 가능성과 차단 원인을 계산합니다. """

    rows = []
    for campaign_id, definition in CAMPAIGNS.items():
        runner = root / definition["runner"]
        source = runner.read_text(encoding="utf-8")
        direct_options = _runner_interface(
            runner, CAMPAIGN_SUBCOMMAND.get(campaign_id)
        )[0]
        role_options = all(
            any(option in direct_options for option in (
                f"--hex-{role.replace('_', '-')}",
                f"--{role.replace('_', '-')}-hex",
                f"--{role.replace('_', '-')}-image",
            ))
            for role in definition["roles"]
        ) if definition["roles"] else False
        if len(definition["roles"]) == 1 and "--hex" in direct_options:
            role_options = True
        if campaign_id == "m33_ecosystem" and "--fixture" in direct_options:
            role_options = True
        native_attestation = "dispatch_attestation(" in source or \
            '"m33_dispatch_attestation"' in source or \
            campaign_id in DERIVED_DISPATCH_CAMPAIGNS
        if native_attestation:
            status = "DISPATCH_READY"
            reason = None
        else:
            status = "BLOCKED"
            reason = INTENTIONAL_DISPATCH_BLOCKERS.get(campaign_id)
            if reason is None:
                reason = ("native_cycle_semantic_attestation_missing"
                          if role_options else
                          "native_program_or_phase_receipt_adapter_missing")
        rows.append({
            "id": campaign_id,
            "status": status,
            "reason": reason,
            "native_attestation": native_attestation,
            "central_direct_readback": role_options,
            "runner": definition["runner"],
        })
    require(len(rows) == len(CAMPAIGNS) and
            {row["id"] for row in rows} == set(CAMPAIGNS),
            "dispatch matrix campaign denominator mismatch")
    return {
        "schema_version": 1,
        "kind": "m33_campaign_dispatch_matrix",
        "status": "READY" if all(row["status"] == "DISPATCH_READY"
                                   for row in rows) else "BLOCKED",
        "unique_campaigns": len(rows),
        "unique_runners": len({row["runner"] for row in rows}),
        "physical_campaigns": sum(
            definition["verification"] == "physical_hil"
            for definition in CAMPAIGNS.values()
        ),
        "build_semantic_campaigns": sum(
            definition["verification"] == "build_semantic"
            for definition in CAMPAIGNS.values()
        ),
        "dispatch_ready": sum(row["status"] == "DISPATCH_READY" for row in rows),
        "campaigns": rows,
    }


def _output_is_bound(outputs: list[tuple[str, str]], child: Path, root: Path) -> bool:
    """! @brief runner output option이 새 child evidence 위치를 실제로 소유하는지 확인합니다. """
    for option, value in outputs:
        candidate = _resolve_argument_path(value, root)
        mode = OUTPUT_ARGUMENT_MODES[option]
        if mode == "file" and candidate == child:
            return True
        if option == "--output" and child.parent == candidate and \
                child.name in {"result.json", "manifest.json"}:
            return True
        if mode == "prefix" and child.parent == candidate.parent and \
                child.name.startswith(candidate.name):
            return True
        if mode == "directory":
            try:
                child.relative_to(candidate)
                return True
            except ValueError:
                pass
    return False


def _validate_hardware(rows: list[dict], roles: list[str]) -> list[dict]:
    """! @brief child adapter의 역할별 probe·image·readback identity를 검증합니다. """
    require(isinstance(rows, list), "campaign hardware list required")
    if not roles:
        require(rows == [], "build-semantic campaign cannot carry hardware")
        return []
    require(len(rows) == len(roles) and
            {row.get("role") for row in rows if isinstance(row, dict)} == set(roles),
            "campaign hardware role mapping mismatch")
    for row in rows:
        require(set(row) == {"role", "probe_sha256", "image_sha256",
                             "build_record_sha256", "readback_sha256",
                             "program_mode", "programmed_bytes", "erase",
                             "auto_unlock", "mass_erase", "automatic_recover"} and
                all(SHA.fullmatch(row.get(key, "")) for key in
                    ("probe_sha256", "image_sha256", "build_record_sha256",
                     "readback_sha256")) and
                str(row["program_mode"]).startswith("pyocd-sector") and
                integer(row["programmed_bytes"], 1) and row["erase"] == "sector" and
                row["auto_unlock"] is False and row["mass_erase"] is False and
                row["automatic_recover"] is False,
                "campaign hardware identity missing")
    require(len({row["probe_sha256"] for row in rows}) == len(rows),
            "campaign probes must be distinct")
    return rows


def _validate_board_plan(rows: list[dict], expected: dict) -> dict[str, str]:
    """! @brief 실행 전에 역할별 물리 probe mapping을 고정하고 build-only와 분리합니다. """
    roles = _preparation_roles(expected)
    require(isinstance(rows, list), "campaign board plan required")
    if expected["verification"] == "build_semantic":
        require(not roles and rows == [],
                "build-semantic campaign cannot declare physical boards")
        return {}
    require(expected["verification"] == "physical_hil" and
            len(rows) == len(roles) and
            {row.get("role") for row in rows if isinstance(row, dict)} == set(roles),
            "campaign board role denominator mismatch")
    require(all(set(row) == {"role", "probe_sha256"} and
                SHA.fullmatch(row.get("probe_sha256", "")) for row in rows),
            "campaign board identity missing")
    require(len({row["probe_sha256"] for row in rows}) == len(rows),
            "campaign board probes must be distinct")
    return {row["role"]: row["probe_sha256"] for row in rows}


def _validate_semantic_status(expected: dict,
                              value: dict[str, str]) -> dict[str, str]:
    """! @brief 조건 미충족을 PASS와 분리하고 허용된 SDK 조건에만 한정합니다. """

    require(isinstance(value, dict) and
            set(value) == set(expected["semantics"]) and
            all(status in ("PASS", "NOT_APPLICABLE")
                for status in value.values()),
            "campaign semantic status mismatch")
    not_applicable = {
        token for token, status in value.items() if status == "NOT_APPLICABLE"
    }
    require(not not_applicable or
            (expected["id"] == "m32_mesh_dfu" and
             not_applicable == {"active_watchdog_condition"}),
            "campaign semantic NOT_APPLICABLE is not allowed")
    return value


def _validate_child_adapter(path: Path, expected: dict, revision: str,
                            cycles: int, native: Path | None = None) -> list[dict]:
    """! @brief 새 native byte에서 정규화된 child evidence를 다시 검증합니다. """
    child = read_json(path)
    required = {
        "schema_version", "kind", "campaign_id", "status", "source_revision",
        "source_clean", "cycles", "semantics", "hardware", "native_evidence",
        "semantic_status",
    }
    if expected["verification"] == "build_semantic":
        required.add("external_interoperability")
    require(set(child) == required and child["schema_version"] == 1 and
            child["kind"] == "m33_campaign_child_result" and
            child["campaign_id"] == expected["id"] and child["status"] == "PASS" and
            child["source_revision"] == revision and child["source_clean"] is True and
            child["cycles"] == cycles and child["semantics"] == expected["semantics"],
            "campaign child adapter identity/result mismatch")
    _validate_semantic_status(expected, child["semantic_status"])
    reference = child["native_evidence"]
    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"} and
            isinstance(reference["path"], str) and reference["path"] and
            SHA.fullmatch(reference.get("sha256", "")),
            "campaign native evidence reference mismatch")
    native_path = (path.parent / reference["path"]).resolve()
    try:
        native_path.relative_to(path.parent.resolve())
        inside_bundle = True
    except ValueError:
        inside_bundle = False
    require(inside_bundle and native_path.is_file() and
            digest(native_path) == reference["sha256"] and
            (native is None or native_path.resolve() == native.resolve()),
            "campaign native evidence byte mismatch")
    if expected["verification"] == "build_semantic":
        require(child["external_interoperability"] == "NOT_RUN",
                "build semantic cannot claim external interoperability")
    return _validate_hardware(child["hardware"], expected["roles"])


def _native_revision(native: dict, family: str) -> str | None:
    """! @brief 서로 다른 native schema의 core revision을 고정 순서로 추출합니다. """
    if family == "legacy_hil":
        return native.get("core_revision")
    if family == "modern_hil":
        identity = native.get("identity", {})
        return identity.get("core") if isinstance(identity, dict) else None
    if family == "diagnostic_hil":
        return native.get("source_revision")
    if family == "flat_hil":
        return native.get("core_revision", native.get("source_revision"))
    if family == "profile_hil":
        revisions = native.get("revisions", {})
        return revisions.get("core") if isinstance(revisions, dict) else None
    if family == "ecosystem_hil":
        identity = native.get("identity", "")
        return identity[:40] if isinstance(identity, str) and len(identity) >= 40 else None
    if family == "build_semantic":
        return native.get("source_revision")
    return None


def _native_transcript(native: dict, native_path: Path) -> list[str]:
    """! @brief native JSON과 같은 stem의 UART byte와 기록 digest를 재검증합니다. """

    path = native_path.with_suffix(".transcript.log")
    require(path.is_file() and
            digest(path) == native.get("transcript_sha256"),
            "native transcript byte mismatch")
    return path.read_text(encoding="ascii", errors="replace").splitlines()


def _validate_mesh_native_raw(native: dict, native_path: Path) -> None:
    """! @brief Mesh 20개 독립 세션을 기존 strict parser로 다시 판정합니다. """

    from m32_mesh_run import CYCLE_TARGET, validate_cycle_records

    transcript = _native_transcript(native, native_path)
    records = native.get("cycle_records")
    require(native.get("cycles") == CYCLE_TARGET and
            isinstance(records, list), "Mesh native cycle denominator mismatch")
    validate_cycle_records(records, transcript)
    require(native.get("cleanup", {}).get("status") == "PASS" and
            all(value == "PASS"
                for value in native.get("serial_close", {}).values()),
            "Mesh native cleanup mismatch")


def _validate_bis_native_raw(native: dict, native_path: Path) -> None:
    """! @brief BIS baseline 20회와 negative 2+2를 원시 phase record로 재검증합니다. """

    from m31_iso_bis_run import validate_aggregate_phase_records

    transcript = _native_transcript(native, native_path)
    require(native.get("scope") == "two_board_bis_twenty_plus_negative_two_plus_two" and
            native.get("cycles") == 20 and native.get("physical_sessions") == 24 and
            isinstance(native.get("phase_records"), list),
            "BIS native aggregate denominator mismatch")
    validate_aggregate_phase_records(native["phase_records"], transcript)
    require(native.get("cleanup", {}).get("status") in {"PASS", "NOT_REQUIRED"} and
            all(value == "PASS"
                for value in native.get("serial_close", {}).values()),
            "BIS native cleanup mismatch")


def _watchdog_reference(reference: dict, native_path: Path,
                        label: str) -> Path:
    """! @brief watchdog 조건 sidecar를 native evidence와 같은 디렉터리로 한정합니다. """

    return _adjacent_native_file(reference, native_path.parent, label)


def _validate_mesh_dfu_native_raw(native: dict, native_path: Path,
                                  revision: str) -> None:
    """! @brief Mesh DFU 10 target 결과와 비활성 WDT exact config byte를 검증합니다. """

    from m32_mesh_dfu_run import ImageInput, build_dispatch_cycle_records

    transcript = _native_transcript(native, native_path)
    records = native.get("dispatch_cycle_records")
    statuses = {
        "signed_mesh_dfu": "PASS",
        "rollback": "PASS",
        "active_watchdog_condition": "NOT_APPLICABLE",
        "cleanup": "PASS",
    }
    require(native.get("iterations") == 5 and native.get("cycles") == 10 and
            native.get("firmware_distribution_targets") == 10 and
            isinstance(records, list) and len(records) == 10 and
            [row.get("cycle") for row in records] == list(range(1, 11)),
            "Mesh DFU raw target denominator mismatch")
    require(all(row.get("status") == "PASS" and
                row.get("semantics") == statuses and
                row.get("iteration") == ((index - 1) // 2) + 1 and
                row.get("target") == ("target_a" if index % 2 else "target_b")
                for index, row in enumerate(records, start=1)),
            "Mesh DFU raw cycle semantic mismatch")
    iterations = native.get("iteration_records")
    require(isinstance(iterations, list) and
            [row.get("iteration") for row in iterations] == list(range(1, 6)),
            "Mesh DFU iteration denominator mismatch")
    candidate_row = native.get("images", {}).get("candidate", {})
    version = candidate_row.get("version")
    require(isinstance(candidate_row.get("size"), int) and
            candidate_row["size"] > 0 and
            SHA.fullmatch(candidate_row.get("sha256", "")) and
            isinstance(version, list) and len(version) == 4 and
            all(isinstance(value, int) for value in version),
            "Mesh DFU candidate identity mismatch")
    candidate = ImageInput(
        native_path,
        candidate_row["size"],
        candidate_row["sha256"],
        tuple(version),
    )
    regenerated = build_dispatch_cycle_records(
        iterations,
        native.get("rollback_records", []),
        transcript,
        candidate,
    )
    require(regenerated == records,
            "Mesh DFU regenerated typed records mismatch")
    for row in iterations:
        start = row.get("transcript_line_start")
        end = row.get("transcript_line_end")
        require(isinstance(start, int) and isinstance(end, int) and
                1 <= start <= end <= len(transcript),
                "Mesh DFU iteration transcript range mismatch")
        raw = ("\n".join(transcript[start - 1:end]) + "\n").encode(
            "ascii", errors="replace"
        )
        require(hashlib.sha256(raw).hexdigest() == row.get("transcript_sha256"),
                "Mesh DFU iteration transcript digest mismatch")
    condition = native.get("watchdog_condition_evidence")
    require(isinstance(condition, dict) and
            set(condition) == {"schema_version", "kind", "status",
                               "condition", "builds"} and
            condition["schema_version"] == 1 and
            condition["kind"] == "m33_mcuboot_watchdog_condition" and
            condition["status"] == "NOT_APPLICABLE" and
            condition["condition"] == "application_watchdog_disabled" and
            set(condition["builds"]) == {"distributor", "target_a",
                                          "target_b", "candidate"},
            "Mesh DFU watchdog condition schema mismatch")
    for role, build in condition["builds"].items():
        require(isinstance(build, dict) and
                set(build) == {"status", "condition", "symbols",
                               "boot_feed_configured", "application_config",
                               "mcuboot_config", "build_record"} and
                build["status"] == "NOT_APPLICABLE" and
                build["condition"] == "application_watchdog_disabled" and
                build["symbols"] == {"CONFIG_WATCHDOG": "n"} and
                isinstance(build["boot_feed_configured"], bool),
                f"Mesh DFU {role} watchdog classification mismatch")
        application = _watchdog_reference(
            build["application_config"], native_path,
            f"Mesh DFU {role} application config"
        )
        _watchdog_reference(
            build["mcuboot_config"], native_path,
            f"Mesh DFU {role} MCUboot config"
        )
        build_record = _watchdog_reference(
            build["build_record"], native_path,
            f"Mesh DFU {role} build record"
        )
        application_text = application.read_text(encoding="utf-8")
        require("CONFIG_WATCHDOG=y" not in application_text and
                ("CONFIG_WATCHDOG=n" in application_text or
                 "# CONFIG_WATCHDOG is not set" in application_text),
                f"Mesh DFU {role} application watchdog byte mismatch")
        build_record_text = build_record.read_text(encoding="utf-8")
        match = re.search(r"(?m)^  core_revision:\s*['\"]?([0-9a-f]{12})['\"]?\s*$",
                          build_record_text)
        require(match is not None and match.group(1) == revision[:12],
                f"Mesh DFU {role} build record revision mismatch")
    require(native.get("cleanup", {}).get("status") == "PASS" and
            all(value == "PASS"
                for value in native.get("serial_close", {}).values()),
            "Mesh DFU cleanup mismatch")


def _validate_template_native_raw(native: dict, native_path: Path,
                                  revision: str) -> None:
    """! @brief ecosystem 네 template build와 credential negative log를 재검증합니다. """
    kinds = ("fast_pair_input", "fast_pair_locator", "enocean", "mds")
    source_paths = {
        "fast_pair_input": "nrf/samples/bluetooth/fast_pair/input_device",
        "fast_pair_locator": "nrf/samples/bluetooth/fast_pair/locator_tag",
        "enocean": "nrf/samples/bluetooth/enocean",
        "mds": "nrf/samples/bluetooth/peripheral_mds",
    }
    expected_artifacts = {
        kind: {
            "build/source/zephyr/zephyr.elf",
            "build/source/zephyr/zephyr.hex",
            "build/source/zephyr/.config",
        } | ({
            "build/modules/nrf/subsys/bluetooth/fast_pair/"
            "fp_provisioning_data.hex",
        } if kind.startswith("fast_pair_") else set())
        for kind in kinds
    }
    negative_ids = {
        "test_credentials_reject_missing_unknown_and_invalid_fast_pair_values",
        "test_credentials_reject_production_debug_and_low_entropy_values",
        "test_mds_credentials_reject_invalid_and_placeholder_values",
        "test_prepare_rejects_missing_internal_or_drifted_inputs",
    }
    lock = read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
    require(native.get("schema_version") == 1 and
            native.get("kind") == "m33_ecosystem_template_builds" and
            native.get("status") == "PASS" and
            native.get("source_revision") == revision and
            native.get("source_clean") is True and
            native.get("ncs_revision") == lock["ncs"]["revision"] and
            native.get("zephyr_revision") == lock["zephyr"]["revision"] and
            native.get("board_revision") == lock["board"]["revision"] and
            native.get("external_interoperability") == "NOT_RUN",
            "template aggregate identity mismatch")
    negative = native.get("credential_negative")
    require(isinstance(negative, dict) and
            set(negative) == {"path", "sha256", "test_ids", "exit_code"} and
            negative["exit_code"] == 0 and
            set(negative["test_ids"]) == negative_ids,
            "template credential negative denominator mismatch")
    negative_log = _adjacent_native_file(
        {"path": negative["path"], "sha256": negative["sha256"]},
        native_path.parent, "template credential negative log"
    ).read_text(encoding="utf-8", errors="replace")
    require("Ran 4 tests" in negative_log and
            negative_log.rstrip().endswith("OK") and
            all(test_id in negative_log for test_id in negative_ids),
            "template credential negative log mismatch")
    results = native.get("results")
    require(isinstance(results, list) and
            [row.get("kind") for row in results] == list(kinds),
            "template result denominator mismatch")
    expected_keys = {
        "kind", "status", "exit_code", "runtime", "source_path",
        "credential_mode", "manifest", "build_log", "artifacts",
        "artifact_files", "command", "command_sha256", "upstream_files",
        "generated_source_sha256", "automatic_flash",
        "external_interoperability",
    }
    for row in results:
        kind = row["kind"]
        require(set(row) == expected_keys and row["status"] == "PASS" and
                row["exit_code"] == 0 and row["runtime"] == "NOT_RUN" and
                row["source_path"] == source_paths[kind] and
                row["credential_mode"] ==
                ("none" if kind == "enocean" else "test") and
                row["automatic_flash"] is False and
                row["external_interoperability"] == "NOT_RUN" and
                isinstance(row["artifacts"], dict) and
                set(row["artifacts"]) == expected_artifacts[kind] and
                all(isinstance(path, str) and SHA.fullmatch(value)
                    for path, value in row["artifacts"].items()),
                f"{kind} template typed result mismatch")
        files = row["artifact_files"]
        require(isinstance(files, dict) and set(files) == set(row["artifacts"]),
                f"{kind} retained artifact denominator mismatch")
        for relative, reference in files.items():
            artifact = _adjacent_native_file(
                {"path": reference.get("path"),
                 "sha256": reference.get("sha256")},
                native_path.parent, f"{kind} retained artifact"
            )
            require(set(reference) == {"path", "sha256", "size",
                                       "confidentiality"} and
                    reference["sha256"] == row["artifacts"][relative] and
                    artifact.stat().st_size == reference.get("size") and
                    reference.get("confidentiality") in {
                        "external-test-credential-evidence",
                        "external-build-evidence",
                    }, f"{kind} retained artifact byte mismatch")
        manifest_path = _adjacent_native_file(
            row["manifest"], native_path.parent, f"{kind} template manifest"
        )
        _adjacent_native_file(
            row["build_log"], native_path.parent, f"{kind} template build log"
        )
        manifest = read_json(manifest_path)
        command = row["command"]
        require(isinstance(command, list) and command and
                all(isinstance(value, str) and value for value in command) and
                row["command_sha256"] == hashlib.sha256(json.dumps(
                    command, separators=(",", ":")
                ).encode("utf-8")).hexdigest() and
                isinstance(row["upstream_files"], dict) and
                bool(row["upstream_files"]) and
                isinstance(row["generated_source_sha256"], dict) and
                bool(row["generated_source_sha256"]) and
                all(isinstance(path, str) and SHA.fullmatch(value)
                    for path, value in row["upstream_files"].items()) and
                all(isinstance(path, str) and SHA.fullmatch(value)
                    for path, value in
                    row["generated_source_sha256"].items()),
                f"{kind} template command/source identity mismatch")
        require(manifest.get("schema_version") == 1 and
                manifest.get("kind") == kind and
                manifest.get("source_path") == source_paths[kind] and
                manifest.get("ncs_revision") == lock["ncs"]["revision"] and
                manifest.get("zephyr_revision") == lock["zephyr"]["revision"] and
                manifest.get("board_revision") == lock["board"]["revision"] and
                manifest.get("automatic_flash") is False and
                manifest.get("external_interoperability") == "NOT_RUN" and
                manifest.get("build_exit_code") == 0 and
                manifest.get("command") == command and
                manifest.get("upstream_files") == row["upstream_files"] and
                manifest.get("generated_source_sha256") ==
                row["generated_source_sha256"] and
                manifest.get("artifacts") == row["artifacts"],
                f"{kind} template manifest mismatch")


def _legacy_transcript(native_path: Path, reference: dict,
                       role: str) -> bytes:
    """! @brief legacy transcript의 실제 byte·크기·digest를 인접 bundle에서 읽습니다. """

    require(isinstance(reference, dict) and
            set(reference) == {"name", "size", "sha256"} and
            isinstance(reference.get("name"), str) and
            Path(reference["name"]).name == reference["name"] and
            integer(reference.get("size"), 1) and
            SHA.fullmatch(reference.get("sha256", "")),
            f"legacy {role} transcript reference mismatch")
    path = (native_path.parent / reference["name"]).resolve()
    require(path.parent == native_path.parent.resolve() and path.is_file() and
            path.stat().st_size == reference["size"] and
            digest(path) == reference["sha256"],
            f"legacy {role} transcript byte mismatch")
    return path.read_bytes()


def _validate_legacy_native_raw(native: dict, native_path: Path,
                                expected: dict, revision: str) -> None:
    """! @brief legacy runner의 기존 strict parser로 UART byte와 typed result를 재구성합니다. """

    campaign_id = expected["id"]
    parser_plan = {
        "m28_link": ("m28_ble_3board", "M28-LINK-01", "m28_three"),
        "m28_adv_pawr_privacy": ("m28_ble_2board", None, "m28_two"),
        "m28_periodic_past": ("m28_ble_3board", "M28-PER-01", "m28_three"),
        "m28_link_control": ("m28_ble_3board", "M28-CTRL-01", "m28_three"),
        "m29_long_read": ("m29_ble_long", None, "pair"),
        "m29_reliable_write": ("m29_ble_long_write", None, "pair"),
        "m29_descriptor": ("m29_ble_descriptor", None, "pair"),
        "m29_cache": ("m29_ble_cache", None, "pair"),
        "m29_coc": ("m29_ble_coc", None, "pair"),
        "m29_signed_eatt": ("m29_ble_signed_eatt", None, "pair"),
        "m29_multi": ("m29_ble_multi_protocol", None, "multi"),
        "m30_multi": ("m30_ble_multi_protocol", None, "multi"),
    }
    require(campaign_id in parser_plan and native.get("core_revision") == revision,
            "legacy native identity mismatch")
    module_name, test_id, parser_kind = parser_plan[campaign_id]
    module = __import__(module_name, fromlist=["parse_role_transcript"])
    if campaign_id in HASH_ONLY_LEGACY_CAMPAIGNS:
        identity_boards = native.get("boards", {})
        probe_hashes = {
            board.get("probe_sha256")
            for board in identity_boards.values()
            if isinstance(board, dict) and
            SHA.fullmatch(board.get("probe_sha256", ""))
        } if isinstance(identity_boards, dict) else set()
        _reject_raw_probe_identity_bytes(
            json.dumps(native, sort_keys=True).encode("utf-8"),
            "legacy native evidence",
            probe_hashes,
        )
    if parser_kind == "multi":
        require(native.get("schema_version") == 2 and
                native.get("status") == "passed" and
                "nonce" not in native and "results" not in native and
                isinstance(native.get("transcripts"), dict) and
                set(native["transcripts"]) == set(expected["roles"]) and
                isinstance(native.get("boards"), dict) and
                set(native["boards"]) == set(expected["roles"]) and
                all(set(board) == {"probe_sha256", "msd_root", "uart_port"} and
                    SHA.fullmatch(board.get("probe_sha256", "")) and
                    isinstance(board.get("msd_root"), str) and board["msd_root"] and
                    isinstance(board.get("uart_port"), str) and board["uart_port"]
                    for board in native["boards"].values()) and
                native.get("coverage", {}).get("independent_sessions") == 20 and
                native.get("termination") == {
                    "serial_closed": {
                        role: True for role in expected["roles"]
                    },
                    "all_serial_closed": True,
                } and
                "daplink_uid" not in json.dumps(native, sort_keys=True),
                "legacy multi hash-only identity or cleanup mismatch")
        cycles = native.get("cycles")
        require(isinstance(cycles, list) and len(cycles) == module.CYCLE_COUNT and
                [row.get("cycle") for row in cycles] ==
                list(range(1, module.CYCLE_COUNT + 1)) and
                all(set(row) == {"cycle", "nonce", "results", "cleanup"}
                    for row in cycles),
                "legacy multi cycle denominator mismatch")
        nonces = [row.get("nonce") for row in cycles]
        require(len(set(nonces)) == module.CYCLE_COUNT and
                all(isinstance(nonce, str) and
                    re.fullmatch(r"[0-9a-f]{32}", nonce) is not None
                    for nonce in nonces),
                "legacy multi cycle nonce mismatch")
        parsed_campaign = {}
        for role in expected["roles"]:
            raw = _legacy_transcript(
                native_path, native["transcripts"][role], role
            )
            parsed_campaign[role] = module.parse_role_campaign(
                raw, role, nonces, revision
            )
        module.validate_three_role_campaign(parsed_campaign)
        for index, row in enumerate(cycles):
            require(set(row["results"]) == set(expected["roles"]) and
                    set(row["cleanup"]) == set(expected["roles"]),
                    "legacy multi cycle role denominator mismatch")
            for role in expected["roles"]:
                value = asdict(parsed_campaign[role][index])
                cleanup = {
                    "active_links": value.pop("cleanup_active_links"),
                    "pending_operations": value.pop("cleanup_pending_operations"),
                    "buffers": value.pop("cleanup_buffers"),
                    "status": value.pop("cleanup_status"),
                }
                require(row["results"][role] == value and
                        row["cleanup"][role] == cleanup,
                        f"legacy multi {role} cycle typed result mismatch")
        images = native.get("images")
        require(isinstance(images, dict) and
                set(images) == set(expected["roles"]),
                "legacy image role denominator mismatch")
        for role, image in images.items():
            require(isinstance(image, dict) and
                    isinstance(image.get("flash_sequence"), str) and
                    image["flash_sequence"].startswith("pyocd-sector") and
                    isinstance(image.get("flash_bytes"), str) and
                    image["flash_bytes"].isdecimal() and
                    int(image["flash_bytes"]) > 0 and
                    isinstance(image.get("build_record"), dict),
                    f"legacy {role} program provenance mismatch")
        return
    require(isinstance(native.get("nonce"), str) and
            re.fullmatch(r"[0-9a-f]{32}", native["nonce"]) is not None and
            isinstance(native.get("transcripts"), dict) and
            set(native["transcripts"]) == set(expected["roles"]) and
            isinstance(native.get("results"), dict) and
            set(native["results"]) == set(expected["roles"]),
            "legacy native role denominator mismatch")
    if campaign_id in HASH_ONLY_LEGACY_CAMPAIGNS:
        boards = native.get("boards")
        require(isinstance(boards, dict) and
                set(boards) == set(expected["roles"]) and
                all("daplink_uid" not in board and
                    SHA.fullmatch(board.get("probe_sha256", ""))
                    for board in boards.values()) and
                "daplink_uid" not in json.dumps(native, sort_keys=True),
                "legacy native hash-only board identity mismatch")
    parsed = {}
    for role in expected["roles"]:
        raw = _legacy_transcript(
            native_path, native["transcripts"][role], role
        )
        if parser_kind == "m28_three":
            value = module.parse_role_transcript(
                raw, native["nonce"], test_id, role
            )
        elif parser_kind == "m28_two":
            value = module.parse_role_transcript(raw, native["nonce"], role)
        else:
            value = module.parse_role_transcript(
                raw, native["nonce"], revision, role
            )
        parsed[role] = value
        require(asdict(value) == native["results"][role],
                f"legacy {role} typed result mismatch")
    if test_id is not None:
        require(native.get("test_id") == test_id,
                "legacy three-board test identity mismatch")
    images = native.get("images")
    require(isinstance(images, dict) and
            set(images) == set(expected["roles"]),
            "legacy image role denominator mismatch")
    for role, image in images.items():
        require(isinstance(image, dict) and
                isinstance(image.get("flash_sequence"), str) and
                image["flash_sequence"].startswith("pyocd-sector") and
                isinstance(image.get("flash_bytes"), str) and
                image["flash_bytes"].isdecimal() and
                int(image["flash_bytes"]) > 0 and
                isinstance(image.get("build_record"), dict),
                f"legacy {role} program provenance mismatch")


def _validate_flat_native_raw(native: dict, native_path: Path, expected: dict,
                              revision: str) -> None:
    """! @brief BAP/CS flat JSON의 실제 cycle·raw counter·cleanup 분모를 재검증합니다. """

    require(native.get("source_clean") is True and
            native.get("core_revision") == revision,
            "flat native exact source mismatch")
    if expected["id"] == "m31_bap_duplex":
        from m31_audio_bap_duplex_cycle_run import validate_cycle_records

        cycles = expected["minimum_cycles"]
        require(native.get("status") == "ARDUINO_BAP_DUPLEX_STOP_RELEASE_PASS" and
                native.get("requested_cycles") == cycles and
                native.get("completed_cycles") == cycles and
                isinstance(native.get("cycle_seconds"), list) and
                len(native["cycle_seconds"]) == cycles and
                all(isinstance(value, (int, float)) and 0 < value <= 30
                    for value in native["cycle_seconds"]),
                "BAP raw cycle denominator mismatch")
        cycle_records = native.get("cycle_records")
        require(isinstance(cycle_records, list) and
                [row.get("duration_seconds") for row in cycle_records] ==
                native["cycle_seconds"],
                "BAP raw cycle duration binding mismatch")
        validate_cycle_records(native, cycles)
        client_lines = native.get("client_lines")
        server_lines = native.get("server_lines")
        require(isinstance(client_lines, list) and
                isinstance(server_lines, list) and
                sum("LE Audio duplex client streaming" in line
                    for line in client_lines) >= cycles and
                sum("LE Audio stream stopped" in line
                    for line in client_lines) >= cycles and
                sum("LE Audio peer disconnected" in line
                    for line in client_lines) >= cycles and
                all(not any(marker in line.lower() for marker in
                            ("failed", "fatal", "stack overflow", "*****"))
                    for line in client_lines + server_lines),
                "BAP raw stream/stop/disconnect semantics mismatch")
        require(native.get("cleanup") == {
            "client": {"stop": "PASS", "acl": "PASS", "serial_close": "PASS"},
            "server": {"stop": "PASS", "acl": "PASS", "serial_close": "PASS"},
        } and set(native.get("build_records", {})) == set(expected["roles"]),
                "BAP final cleanup/build denominator mismatch")
        return
    from m31_cs_ras_pair_run import validate_raw_evidence

    require(expected["id"] == "m31_cs_ras" and native.get("status") == "PASS" and
            native.get("procedures") == 100 and
            native.get("stop_restart_cycles") == 20 and
            native.get("disconnect_reconnect_cycles") == 20 and
            native.get("raw_ras") == "PASS" and
            native.get("distance_accuracy") == "BOUNDED_SANITY_PASS" and
            native.get("cleanup_confirmed") is True and
            native.get("mode") == "sector_flash_pair_reset" and
            set(native.get("build_records", {})) == set(expected["roles"]),
            "CS RAS raw denominator or cleanup mismatch")
    validate_raw_evidence(native, 100, 20)
    lines = native.get("initiator_lines")
    reflector_lines = native.get("reflector_lines")
    require(isinstance(lines, list) and isinstance(reflector_lines, list),
            "CS RAS raw line list missing")
    pattern = re.compile(
        r"^CS_RAW counter=(\d+) local=(\d+) peer=(\d+) rtt=(\d+) "
        r"tone=(\d+) valid_rtt=(\d+) distance_m=([0-9.]+)$"
    )
    records = [pattern.fullmatch(line) for line in lines if line.startswith("CS_RAW")]
    require(len(records) >= 100 and all(record is not None for record in records),
            "CS RAS raw procedure record mismatch")
    previous = None
    for record in records[:100]:
        counter, local, peer, rtt, tone, valid = map(
            int, record.groups()[:6]
        )
        require(local == peer and local > 0 and rtt > 0 and tone > 0 and
                0 < valid <= rtt and
                (previous is None or 0 < ((counter - previous) & 0xFFFF) < 0x8000),
                "CS RAS raw measurement boundary mismatch")
        previous = counter
    require(sum("CS procedures stop requested" in line for line in lines) >= 20 and
            sum("CS disconnect requested" in line for line in lines) >= 20 and
            sum("CS reflector disconnected" in line for line in reflector_lines) >= 20 and
            sum(line == "CS quiesce requested role=initiator"
                for line in lines) == 1 and
            sum(line == "CS_QUIESCED role=initiator active_acl=0 "
                       "pending=0 scan=0 cs=0" for line in lines) == 1 and
            sum(line == "CS quiesce requested role=reflector"
                for line in reflector_lines) == 1 and
            sum(line == "CS_QUIESCED role=reflector active_acl=0 "
                       "pending=0 advertising=0 cs=0"
                for line in reflector_lines) == 1,
            "CS RAS stop/disconnect transcript denominator mismatch")


def _validate_diagnostic_build_raw(native: dict, native_path: Path,
                                   revision: str) -> None:
    """! @brief controller/scan-request build의 log·image·config byte와 lock을 검증합니다. """
    from m33_diagnostics import (
        validate_locked_sources, validate_release_build_manifest,
    )

    sdk = Path(str(native.get("sdk_root", ""))).resolve()
    toolchain = Path(str(native.get("toolchain_root", ""))).resolve()
    require(native.get("source_revision") == revision and
            sdk.is_dir() and toolchain.is_dir(),
            "diagnostic build source/toolchain root mismatch")
    validate_release_build_manifest(native, native_path.parent, sdk, toolchain)
    locked = validate_locked_sources(sdk)
    require(locked == {
        "core": revision,
        "ncs": native["ncs_revision"],
        "zephyr": native["zephyr_revision"],
        "board": native["board_revision"],
    }, "diagnostic build final clean lock mismatch")


def _validate_modern_direct_native_raw(native: dict, native_path: Path,
                                       expected: dict) -> None:
    """! @brief modern direct HIL의 typed 원시 분모를 runner oracle로 재생성합니다.

    native attestation의 cycle 목록을 그대로 신뢰하지 않고 각 runner가 실제
    UART parser 결과에서 사용하는 campaign별 builder를 다시 호출합니다.
    원본 transcript byte와 성공 cleanup도 함께 묶어 self-asserted PASS를 막습니다.
    """

    campaign_id = expected["id"]
    require(campaign_id in MODERN_DIRECT_RAW_CAMPAIGNS,
            "modern direct raw validator campaign mismatch")
    _native_transcript(native, native_path)
    cleanup = native.get("cleanup")
    require(isinstance(cleanup, dict) and
            set(cleanup) == set(expected["roles"]) and
            all(isinstance(row, dict) and
                row.get("stop") == "PASS" and
                row.get("serial_close") == "PASS"
                for row in cleanup.values()),
            "modern direct STOP/serial cleanup mismatch")
    if campaign_id == "m31_iso_cis":
        from m31_iso_cis_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("nonces", []),
            SimpleNamespace(**native.get("measurement", {})),
        )
    elif campaign_id == "m31_iso_combined":
        from m31_iso_combined_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("nonces", []),
            SimpleNamespace(**native.get("measurement", {})),
        )
    elif campaign_id == "m31_df_tx":
        from m31_df_beacon_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("nonces", []), native.get("measured", {})
        )
    elif campaign_id == "m32_power":
        from m32_power_path_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("power_reports", {}),
            native.get("path_reports", 0),
            native.get("maximum_event_gap_ms", {}),
        )
    elif campaign_id == "m32_advertising":
        from m32_advertising_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(native.get("results", {}))
    elif campaign_id == "m32_privacy":
        from m32_privacy_run import build_dispatch_cycle_records

        addresses = native.get("local_addresses", {})
        ready = {
            role: (row.get("address"), row.get("type"))
            for role, row in addresses.items()
            if isinstance(row, dict)
        }
        regenerated = build_dispatch_cycle_records(
            native.get("results", {}), ready
        )
    elif campaign_id == "m32_ead":
        from m32_ead_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("results", {}), set(native.get("auth_sequences", []))
        )
    elif campaign_id == "m32_nordic":
        from m32_nordic_extension_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(native.get("results", {}))
    elif campaign_id == "m32_mesh_management":
        from m32_mesh_management_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("results", {}), native.get("capacities", {})
        )
    elif campaign_id == "m32_mesh_update":
        from m32_mesh_update_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("results", {}), native.get("capacities", {})
        )
    else:
        from m33_beacon_run import build_dispatch_cycle_records

        regenerated = build_dispatch_cycle_records(
            native.get("session_results", [])
        )
    require(regenerated == native.get("dispatch_cycle_records") and
            regenerated == native.get(
                "m33_dispatch_attestation", {}
            ).get("cycle_records"),
            "modern direct raw-derived cycle record mismatch")


def _validate_multiphase_direct_native_raw(native: dict, native_path: Path,
                                           expected: dict) -> None:
    """! @brief 순차 재program campaign의 모든 phase image/readback을 검증합니다. """

    campaign_id = expected["id"]
    require(campaign_id in MULTIPHASE_DIRECT_RAW_CAMPAIGNS,
            "multiphase direct campaign mismatch")
    _native_transcript(native, native_path)
    if campaign_id == "m32_standalone_radio":
        from m32_standalone_radio_run import build_dispatch_cycle_records

        phase_source = native.get("protocols", {})
        phase_names = ("radio154", "esb")
        selected_phase = "esb"
    else:
        from m32_coexistence_run import build_dispatch_cycle_records

        phase_source = native.get("scenario_phases", {})
        phase_names = ("ble_154", "ble_esb", "ble_mesh")
        selected_phase = "ble_mesh"
    require(tuple(phase_source) == phase_names,
            "multiphase native phase order/denominator mismatch")
    regenerated = build_dispatch_cycle_records(phase_source)
    require(regenerated == native.get("dispatch_cycle_records") and
            regenerated == native.get(
                "m33_dispatch_attestation", {}
            ).get("cycle_records"),
            "multiphase raw-derived cycle record mismatch")
    phases = native.get("program_phases")
    require(isinstance(phases, dict) and tuple(phases) == phase_names,
            "multiphase program receipt denominator mismatch")
    image_hashes = []
    for phase_name, phase in phases.items():
        require(isinstance(phase, dict) and
                set(phase) == set(expected["roles"]),
                f"{phase_name} program role denominator mismatch")
        for role, row in phase.items():
            require(isinstance(row, dict) and
                    set(row) == {"probe_sha256", "image", "build_record",
                                 "flash", "readback"} and
                    SHA.fullmatch(row.get("probe_sha256", "")),
                    f"{phase_name}/{role} program identity mismatch")
            image = _adjacent_native_file(
                row["image"], native_path.parent,
                f"{phase_name}/{role} image"
            )
            build_record = _adjacent_native_file(
                row["build_record"], native_path.parent,
                f"{phase_name}/{role} build record"
            )
            readback = _adjacent_native_file(
                row["readback"], native_path.parent,
                f"{phase_name}/{role} readback"
            )
            flash = row["flash"]
            require(image.stat().st_size > 0 and
                    build_record.stat().st_size > 0 and
                    readback.stat().st_size > 0 and
                    isinstance(flash, dict) and
                    set(flash) == {"mode", "programmed_bytes", "erase",
                                   "auto_unlock", "mass_erase",
                                   "automatic_recover"} and
                    str(flash["mode"]).startswith("pyocd-sector") and
                    integer(flash["programmed_bytes"], 1) and
                    flash["erase"] == "sector" and
                    flash["auto_unlock"] is False and
                    flash["mass_erase"] is False and
                    flash["automatic_recover"] is False,
                    f"{phase_name}/{role} exact program receipt mismatch")
            image_hashes.append(digest(image))
    require(len(set(image_hashes)) == len(image_hashes),
            "multiphase image provenance was flattened or reused")
    declared = {
        row["role"]: {key: value for key, value in row.items() if key != "role"}
        for row in native["m33_dispatch_attestation"]["hardware"]
    }
    require(declared == phases[selected_phase],
            "multiphase flat attestation differs from selected final phase")


def _replay_ecosystem_transcript(native: dict, native_path: Path,
                                 expected: dict) -> None:
    """! @brief ecosystem 명령·응답의 nonce별 전역 순서를 원본 byte에서 재생합니다. """
    import m33_ecosystem_hil as ecosystem

    transcript_path = native_path.parent / "transcript.log"
    require(transcript_path.is_file() and
            digest(transcript_path) == native.get("transcript_sha256"),
            "ecosystem transcript byte mismatch")
    roles = tuple(expected["roles"])
    transcript_lines = transcript_path.read_text(
        encoding="ascii", errors="strict"
    ).splitlines()
    ecosystem.validate_transcript_evidence(native, transcript_lines)
    entries = []
    for raw_line in transcript_lines:
        role, separator, payload = raw_line.partition("> ")
        if separator and role in roles:
            entries.append({"role": role, "direction": "send",
                            "payload": payload})
            continue
        role, separator, payload = raw_line.partition("< ")
        if separator and role in roles and payload.startswith("M33ECO|"):
            entries.append({
                "role": role, "direction": "receive", "payload": payload,
                "record": ecosystem.parse(payload, role, native["identity"]),
            })

    def indexes(role: str, direction: str, predicate) -> list[int]:
        return [
            index for index, row in enumerate(entries)
            if row["role"] == role and row["direction"] == direction and
            predicate(row)
        ]

    def unique(role: str, direction: str, predicate, label: str) -> int:
        matches = indexes(role, direction, predicate)
        require(len(matches) == 1, f"ecosystem {role} {label} denominator mismatch")
        return matches[0]

    cases = native.get("cases")
    require(isinstance(cases, list) and cases,
            "ecosystem case transcript denominator missing")
    case_nonces = {row.get("nonce") for row in cases}
    require(len(case_nonces) == len(cases),
            "ecosystem case nonce denominator mismatch")
    pass_indexes: dict[tuple[str, str], int] = {}
    stop_indexes = []
    for case_row in cases:
        nonce = case_row["nonce"]
        case = case_row["case"]
        starts = {}
        started = {}
        correct_stops = {}
        for role in roles:
            starts[role] = unique(
                role, "send",
                lambda row, n=nonce, c=case: row["payload"] == f"START {n} {c}",
                f"{nonce} START",
            )
            started[role] = unique(
                role, "receive",
                lambda row, n=nonce: row["record"]["event"] == "STARTED" and
                row["record"]["nonce"] == n,
                f"{nonce} STARTED",
            )
            pass_indexes[(role, nonce)] = unique(
                role, "receive",
                lambda row, n=nonce: row["record"]["event"] == "PASS" and
                row["record"]["nonce"] == n,
                f"{nonce} PASS",
            )
            correct_stop = unique(
                role, "send",
                lambda row, n=nonce: row["payload"] == f"STOP {n}",
                f"{nonce} STOP",
            )
            stopped = unique(
                role, "receive",
                lambda row, n=nonce: row["record"]["event"] == "STOPPED" and
                row["record"]["nonce"] == n and row["record"]["links"] == 0,
                f"{nonce} STOPPED",
            )
            require(starts[role] < started[role] < pass_indexes[(role, nonce)] <
                    correct_stop < stopped,
                    f"ecosystem {role} {nonce} lifecycle order mismatch")
            correct_stops[role] = correct_stop
            stop_indexes.append(stopped)
        if case != "access_denied":
            client_ready = unique(
                "client", "receive",
                lambda row, n=nonce: row["record"]["event"] == "CLIENT_READY" and
                row["record"]["nonce"] == n,
                f"{nonce} CLIENT_READY",
            )
            go = unique(
                "peer", "send", lambda row, n=nonce: row["payload"] == f"GO {n}",
                f"{nonce} GO",
            )
            go_ack = unique(
                "peer", "receive",
                lambda row, n=nonce: row["record"]["event"] == "GO_ACK" and
                row["record"]["nonce"] == n,
                f"{nonce} GO_ACK",
            )
            require(max(started.values()) < client_ready < go < go_ack <
                    min(pass_indexes[(role, nonce)] for role in roles),
                    f"ecosystem {nonce} start/GO/PASS order mismatch")
            for role in roles:
                wrong_stops = indexes(
                    role, "send",
                    lambda row: row["payload"] == "STOP " + "f" * 32,
                )
                rejects = indexes(
                    role, "receive",
                    lambda row, n=nonce: row["record"]["event"] == "REJECT" and
                    row["record"]["nonce"] == n,
                )
                require(any(pass_indexes[(role, nonce)] < wrong_stop < reject <
                            correct_stops[role]
                            for wrong_stop in wrong_stops for reject in rejects),
                        f"ecosystem {role} wrong STOP rejection order mismatch")
        else:
            require(max(started.values()) <
                    min(pass_indexes[(role, nonce)] for role in roles),
                    "ecosystem denied START/PASS order mismatch")

    for role in roles:
        valid_starts = indexes(
            role, "send",
            lambda row: re.fullmatch(
                r"START [0-9a-f]{32} (?:ancs|ams|access_denied|"
                r"ancs_bad|ams_bad)", row["payload"]
            ) is not None,
        )
        extra = [
            index for index in valid_starts
            if entries[index]["payload"].split()[1] not in case_nonces
        ]
        require(len(extra) == 1,
                f"ecosystem {role} wrong-peer START denominator mismatch")
        wrong_start = extra[0]
        wrong_nonce = entries[wrong_start]["payload"].split()[1]
        wrong_started = unique(
            role, "receive",
            lambda row, n=wrong_nonce: row["record"]["event"] == "STARTED" and
            row["record"]["nonce"] == n,
            "wrong-peer STARTED",
        )
        wrong_ready = unique(
            role, "receive",
            lambda row, n=wrong_nonce: row["record"]["event"] == "READY" and
            row["record"]["nonce"] == n and row["record"]["links"] == 0,
            "wrong-peer READY",
        )
        status_candidates = indexes(
            role, "send", lambda row: row["payload"] == "STATUS"
        )
        require(len(status_candidates) == 3,
                f"ecosystem {role} STATUS denominator mismatch")
        wrong_status_candidates = [
            index for index in status_candidates
            if wrong_started < index < wrong_ready
        ]
        require(len(wrong_status_candidates) == 1,
                f"ecosystem {role} wrong-peer STATUS order mismatch")
        wrong_status = wrong_status_candidates[0]
        wrong_stop = unique(
            role, "send",
            lambda row, n=wrong_nonce: row["payload"] == f"STOP {n}",
            "wrong-peer STOP",
        )
        wrong_stopped = unique(
            role, "receive",
            lambda row, n=wrong_nonce: row["record"]["event"] == "STOPPED" and
            row["record"]["nonce"] == n and row["record"]["links"] == 0,
            "wrong-peer STOPPED",
        )
        require(wrong_start < wrong_started < wrong_status < wrong_ready <
                wrong_stop < wrong_stopped < min(
                    pass_indexes[(role, nonce)] for nonce in case_nonces
                ), f"ecosystem {role} wrong-peer order mismatch")
        cleanup = unique(
            role, "send",
            lambda row: row["payload"].startswith("CLEANUP "),
            "CLEANUP",
        )
        cleaned = unique(
            role, "receive",
            lambda row: row["record"]["event"] == "CLEANED",
            "CLEANED",
        )
        require(max(stop_indexes) < cleanup < cleaned,
                f"ecosystem {role} cleanup order mismatch")
        invalid_commands = {
            "START " + "0" * 32 + " ancs", "START invalid ancs", "X" * 120,
        }
        require(all(len(indexes(
                    role, "send", lambda row, command=command:
                    row["payload"] == command
                )) == 1 for command in invalid_commands),
                f"ecosystem {role} malformed command denominator mismatch")
        event_counts = {}
        for entry in entries:
            if entry["role"] == role and entry["direction"] == "receive":
                event = entry["record"]["event"]
                event_counts[event] = event_counts.get(event, 0) + 1
        expected_counts = {
            "READY": 3,
            "REJECT": len(cases) + 2,
            "STARTED": len(cases) + 1,
            "PASS": len(cases),
            "STOPPED": len(cases) + 1,
            "CLEANED": 1,
        }
        if role == "client":
            expected_counts["CLIENT_READY"] = len(cases) - 1
        else:
            expected_counts["GO_ACK"] = len(cases) - 1
        require(event_counts == expected_counts,
                f"ecosystem {role} protocol event denominator mismatch")


def _validate_ecosystem_native_raw(native: dict, native_path: Path,
                                   expected: dict) -> None:
    """! @brief ANCS/AMS 20회·negative·bond cleanup과 준비 fixture byte를 검증합니다. """

    import m33_ecosystem_hil as ecosystem

    negative = native.get("negative")
    require(native.get("apple_interoperability") == "NOT_RUN" and
            native.get("google_interoperability") == "NOT_RUN" and
            isinstance(negative, list) and len(negative) == 1 and
            negative[0].get("wrong_peer_nonce") == "PASS" and
            negative[0].get("malformed_commands") == "PASS" and
            isinstance(negative[0].get("wrong_peer_nonces"), dict) and
            set(negative[0]["wrong_peer_nonces"]) == set(expected["roles"]) and
            all(re.fullmatch(r"[0-9a-f]{32}", value) is not None
                for value in negative[0]["wrong_peer_nonces"].values()),
            "ecosystem external/negative boundary mismatch")
    fixture_path = _adjacent_native_file(
        native.get("fixture"), native_path.parent, "ecosystem fixture"
    )
    preflight_path = _adjacent_native_file(
        native.get("preflight"), native_path.parent, "ecosystem preflight"
    )
    fixture = read_json(fixture_path)
    require(native.get("fixture_sha256") == digest(fixture_path) and
            fixture.get("identity") == native.get("identity") and
            fixture.get("schema_version") == 1 and
            fixture.get("other_radios") == "isolated_verified" and
            fixture.get("test_owned_bond_cleanup") is True and
            fixture.get("preflight_sha256") == digest(preflight_path),
            "ecosystem prepared fixture identity mismatch")
    boards = fixture.get("boards")
    require(isinstance(boards, list) and len(boards) == 2 and
            {row.get("role") for row in boards
             if isinstance(row, dict)} == set(expected["roles"]) and
            len({row.get("probe_sha256") for row in boards}) == 2 and
            all(SHA.fullmatch(row.get("probe_sha256", "")) and
                row.get("readback") == "verified" and
                SHA.fullmatch(row.get("image_sha256", "")) and
                SHA.fullmatch(row.get("build_record_sha256", ""))
                for row in boards),
            "ecosystem fixture role/provenance denominator mismatch")
    transcript_path = native_path.parent / "transcript.log"
    _replay_ecosystem_transcript(native, native_path, expected)
    parsed: dict[str, list[dict]] = {role: [] for role in expected["roles"]}
    for line in transcript_path.read_text(
            encoding="ascii", errors="strict").splitlines():
        role, separator, payload = line.partition("< ")
        if separator and role in parsed and payload.startswith("M33ECO|"):
            parsed[role].append(
                ecosystem.parse(payload, role, native["identity"])
            )
    cases = native.get("cases")
    require(isinstance(cases, list) and
            ecosystem.validate_case_denominators(cases) ==
            native.get("case_denominators"),
            "ecosystem raw case denominator mismatch")
    observed_nonces = set()
    for row in cases:
        case = row.get("case")
        cycle = row.get("cycle")
        nonce = row.get("nonce")
        roles = row.get("roles")
        require(isinstance(nonce, str) and
                re.fullmatch(r"[0-9a-f]{32}", nonce) is not None and
                nonce not in observed_nonces and isinstance(roles, dict) and
                set(roles) == set(expected["roles"]),
                "ecosystem case nonce/role mismatch")
        observed_nonces.add(nonce)
        mode = ("denied" if case == "access_denied" else
                "fresh" if case == "ancs" and cycle == 1 else
                "reconnect")
        for role in expected["roles"]:
            ecosystem.validate_pass(roles[role], case, role, nonce, mode)
            require(roles[role] in parsed[role],
                    f"ecosystem {role} typed result absent from transcript")
    bond_cleanup = native.get("bond_cleanup")
    cleanup = native.get("cleanup")
    require(isinstance(bond_cleanup, list) and len(bond_cleanup) == 2 and
            {row.get("role") for row in bond_cleanup} == set(expected["roles"]) and
            all(row.get("status") == "PASS" and
                row.get("exact_deleted") == 1 and
                row.get("existing_unchanged") is True
                for row in bond_cleanup) and
            isinstance(cleanup, list) and len(cleanup) == 2 and
            {row.get("role") for row in cleanup} == set(expected["roles"]) and
            all(row.get("status") == "PASS" and row.get("stop") == "PASS" and
                row.get("serial_close") == "PASS" for row in cleanup),
            "ecosystem exact bond/serial cleanup mismatch")


def _validate_profile_campaign_native_raw(native_path: Path, family: str,
                                          revision: str) -> None:
    """! @brief Profile aggregate의 raw phase byte를 전용 strict validator로 재검증합니다. """
    from m33_profile_campaign import validate_campaign_evidence
    validate_campaign_evidence(native_path, family, revision)


def _validate_diagnostics_campaign_native_raw(native_path: Path,
                                              revision: str) -> None:
    """! @brief DTM dual prepared fixture와 24개 case를 전용 validator로 재검증합니다. """
    from m33_diagnostics_campaign import validate_campaign
    validate_campaign(native_path, revision)


def _validate_cs_negative_native_raw(native: dict, expected: dict) -> None:
    """! @brief 분리된 CS negative phase의 실제 transcript 분모를 helper로 재도출합니다. """
    from m31_cs_negative_attestation import (
        PHASES, build_insecure_read_records, build_missing_service_records,
        build_stale_key_records, build_wrong_peer_records,
    )
    phase_name = CS_NEGATIVE_CAMPAIGNS[expected["id"]]
    spec = PHASES[phase_name]
    contract = native.get("negative_phase")
    require(isinstance(contract, dict) and
            contract.get("id") == expected["id"] and
            contract.get("roles") == list(expected["roles"]) and
            contract.get("cycles") == expected["minimum_cycles"] and
            contract.get("semantics") == expected["semantics"] and
            REV.fullmatch(contract.get("board_revision", "")),
            "CS negative phase contract mismatch")
    builders = {
        "stale_key": build_stale_key_records,
        "insecure_read": build_insecure_read_records,
        "wrong_peer": build_wrong_peer_records,
        "missing_service": build_missing_service_records,
    }
    rebuilt = builders[phase_name](native, native.get("cleanup", {}))
    require(rebuilt == native.get("dispatch_cycle_records") and
            len(rebuilt) == spec.cycles,
            "CS negative raw cycle denominator mismatch")
    program = native.get("program_phase")
    hardware = native.get("m33_dispatch_attestation", {}).get("hardware")
    require(isinstance(program, dict) and set(program) == set(spec.roles) and
            isinstance(hardware, list) and
            {row.get("role") for row in hardware if isinstance(row, dict)} ==
            set(spec.roles), "CS negative program phase denominator mismatch")
    normalized = {
        row["role"]: {key: value for key, value in row.items() if key != "role"}
        for row in hardware
    }
    require(program == normalized,
            "CS negative program phase differs from attestation")


def _validate_m30_native_raw(native: dict, native_path: Path,
                             expected: dict) -> None:
    """! @brief M30 5종의 raw transcript·phase·heterogeneous 분모를 재검증합니다. """
    from m30_native_attestation import validate_m30_native_evidence

    campaign_id = expected["id"]
    require(campaign_id in M30_NATIVE_CAMPAIGNS,
            "M30 raw validator campaign mismatch")
    denominator = validate_m30_native_evidence(
        campaign_id, native, native_path
    )
    require(denominator.get("campaign_id") == campaign_id and
            denominator.get("total_primary_cycles") ==
            expected["minimum_cycles"],
            "M30 typed primary cycle denominator mismatch")
    attestation = native.get("m33_dispatch_attestation")
    if campaign_id == "m30_dfu":
        require(attestation is None and
                "dispatch_cycle_records" not in native and
                [row.get("name") for row in denominator.get("groups", [])] == [
                    "signed_update", "unsigned_rejection",
                    "wrong_key_rejection", "corrupt_rejection",
                    "truncated_rejection", "downgrade_rejection",
                    "rollback", "secondary_slot_cleanup", "base_restore",
                ], "M30 DFU heterogeneous denominator was flattened")
        return
    require(isinstance(attestation, dict) and
            native.get("dispatch_cycle_records") ==
            attestation.get("cycle_records") and
            len(native.get("dispatch_cycle_records", [])) ==
            expected["minimum_cycles"],
            "M30 native raw/attestation cycle mismatch")


def _validate_campaign_native_raw(native: dict, native_path: Path,
                                  expected: dict, revision: str) -> None:
    """! @brief self-asserted attestation과 별개인 campaign 원시 분모를 재검증합니다. """

    validators = {
        "m31_iso_bis": lambda: _validate_bis_native_raw(native, native_path),
        "m32_mesh": lambda: _validate_mesh_native_raw(native, native_path),
        "m32_mesh_dfu": lambda: _validate_mesh_dfu_native_raw(
            native, native_path, revision
        ),
        "m33_ecosystem_templates": lambda: _validate_template_native_raw(
            native, native_path, revision
        ),
        "m33_ecosystem": lambda: _validate_ecosystem_native_raw(
            native, native_path, expected
        ),
        "m33_profiles_standard": lambda: _validate_profile_campaign_native_raw(
            native_path, "standard", revision
        ),
        "m33_profiles_native": lambda: _validate_profile_campaign_native_raw(
            native_path, "native", revision
        ),
        "m33_diagnostics_dtm": lambda: _validate_diagnostics_campaign_native_raw(
            native_path, revision
        ),
    }
    validator = validators.get(expected["id"])
    if validator is not None:
        validator()
    elif expected["id"] in M30_NATIVE_CAMPAIGNS:
        _validate_m30_native_raw(native, native_path, expected)
    elif expected["id"] in CS_NEGATIVE_CAMPAIGNS:
        _validate_cs_negative_native_raw(native, expected)
    elif expected["id"] in MODERN_DIRECT_RAW_CAMPAIGNS:
        _validate_modern_direct_native_raw(native, native_path, expected)
    elif expected["id"] in MULTIPHASE_DIRECT_RAW_CAMPAIGNS:
        _validate_multiphase_direct_native_raw(native, native_path, expected)
    elif expected["id"] in DERIVED_LEGACY_CAMPAIGNS:
        _validate_legacy_native_raw(native, native_path, expected, revision)
    elif expected["id"] in DERIVED_FLAT_CAMPAIGNS:
        _validate_flat_native_raw(native, native_path, expected, revision)
    elif expected["id"] == "m33_diagnostics_build":
        _validate_diagnostic_build_raw(native, native_path, revision)


def _validate_native_schema(native: dict, native_path: Path,
                            expected: dict, revision: str) -> None:
    """! @brief 기존 runner family의 성공·source·고유 구조를 adapter 전에 fail-closed로 검증합니다. """
    campaign_id = expected["id"]
    family = NATIVE_ADAPTER_REGISTRY[campaign_id]
    expected_status = NATIVE_SUCCESS_STATUS.get(campaign_id, "PASS")
    if family == "legacy_hil":
        require(native.get("status") == "passed" and
                isinstance(native.get("boards"), (dict, int)) and
                isinstance(native.get("results", native.get("cases")), (dict, list)),
                "legacy native evidence did not pass its recorded denominator")
    elif family == "modern_hil":
        require(native.get("status") == expected_status and
                native.get("source_clean") is True and
                isinstance(native.get("boards"), (dict, list)) and
                isinstance(native.get("results", native.get("cycles", native.get("measured"))),
                           (dict, list, int)),
                "modern native evidence did not pass its recorded denominator")
    elif family == "flat_hil":
        require(native.get("status") == expected_status and
                native.get("source_clean") is True,
                "flat native evidence did not pass")
    elif family == "profile_hil":
        require(native.get("schema") == "nucode-m33-profile-campaign-v1" and
                native.get("status") == "PASS" and
                native.get("source_clean") is True and native.get("cycles") == 20 and
                isinstance(native.get("build_identity"), dict) and
                isinstance(native.get("boards"), dict),
                "profile native evidence is not a release PASS")
        require(set(native["build_identity"]) == set(expected["roles"]) and
                set(native["boards"]) == set(expected["roles"]),
                "profile role/build denominator mismatch")
    elif family == "ecosystem_hil":
        require(native.get("schema_version") == 2 and native.get("status") == "PASS" and
                isinstance(native.get("cases"), list) and
                all(isinstance(row, dict) and row.get("status") == "PASS" and
                    row.get("cleanup") == "PASS" for row in native["cases"]),
                "ecosystem native case denominator mismatch")
    elif family == "build_semantic":
        results = native.get("results")
        require(isinstance(results, list) and results and
                all(isinstance(row, dict) and
                    row.get("status") == "PASS" and row.get("exit_code") == 0 and
                    row.get("runtime", "NOT_RUN") == "NOT_RUN" for row in results),
                "build-semantic native result mismatch")
    elif family == "diagnostic_hil":
        from m33_diagnostics_campaign import RF_BOUNDARY
        require(native.get("schema") == "nucode-m33-diagnostics-campaign-v1" and
                native.get("status") == "PASS" and
                native.get("source_clean") is True and native.get("cycles") == 24 and
                len(native.get("cases", [])) == 24 and
                len(native.get("transports", [])) == 2 and
                native.get("rf_boundary") == RF_BOUNDARY,
                "diagnostic native result mismatch")
    else:
        raise ValueError("unknown native adapter family")
    require(_native_revision(native, family) == revision,
            "native evidence source revision mismatch")
    _validate_campaign_native_raw(native, native_path, expected, revision)


def _adjacent_native_file(reference: dict, base: Path, label: str) -> Path:
    """! @brief native attestation이 참조하는 실제 byte를 같은 bundle 내로 한정합니다. """
    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"} and
            isinstance(reference.get("path"), str) and
            Path(reference["path"]).name == reference["path"] and
            SHA.fullmatch(reference.get("sha256", "")), f"{label} reference mismatch")
    path = (base / reference["path"]).absolute()
    require(path.parent.resolve() == base.resolve(),
            f"{label} escapes adjacent evidence directory")
    raw = _read_regular_bytes(path, label)
    require(hashlib.sha256(raw).hexdigest() == reference["sha256"],
            f"{label} byte mismatch")
    return path


def _validate_exact_program_row(row: dict, native_path: Path,
                                expected_role: str) -> dict:
    """! @brief 저장된 image와 live all-range readback byte를 다시 결합합니다. """

    require(isinstance(row, dict) and
            set(row) == {"role", "probe_sha256", "image", "build_record",
                         "flash", "readback"} and
            row["role"] == expected_role and
            SHA.fullmatch(row.get("probe_sha256", "")),
            f"{expected_role} stored exact program identity mismatch")
    image = _adjacent_native_file(
        row["image"], native_path.parent, f"{expected_role} stored image"
    )
    build_record = _adjacent_native_file(
        row["build_record"], native_path.parent,
        f"{expected_role} stored build record"
    )
    readback_path = _adjacent_native_file(
        row["readback"], native_path.parent,
        f"{expected_role} stored readback"
    )
    require(image.stat().st_size > 0 and build_record.stat().st_size > 0,
            f"{expected_role} stored program input is empty")
    ranges = intel_hex_ranges(image)
    expected_ranges = [
        {
            "start": start,
            "length": len(data),
            "expected_sha256": hashlib.sha256(data).hexdigest(),
            "observed_sha256": hashlib.sha256(data).hexdigest(),
            "status": "PASS",
        }
        for start, data in ranges
    ]
    readback = read_json(readback_path)
    allowed_readback_roles = {expected_role}
    if expected_role == "second_peer":
        allowed_readback_roles.add("watcher")
    readback_fields = {
                "schema_version", "kind", "status", "role", "probe_sha256",
                "image_sha256", "backend", "halted", "resumed", "ranges",
                "pre_state", "post_state", "restored",
            }
    require(set(readback) == readback_fields and
            readback["schema_version"] == 1 and
            readback["kind"] == "m33_exact_program_readback" and
            readback["status"] == "PASS" and
            readback["role"] in allowed_readback_roles and
            readback["probe_sha256"] == row["probe_sha256"] and
            readback["image_sha256"] == digest(image) and
            readback["backend"] == "pyocd-live-target" and
            readback["halted"] is True and
            readback["ranges"] == expected_ranges,
            f"{expected_role} stored live all-range readback mismatch")
    ## @brief CPU state 복원은 application STOP/RF cleanup PASS와 독립된 debugger 증거입니다.
    pre_state = readback["pre_state"]
    post_state = readback["post_state"]
    require(readback_state_restored(pre_state, post_state) and
            readback["restored"] is True and
            readback["resumed"] is (pre_state in {"RUNNING", "SLEEPING"}),
            f"{expected_role} readback did not restore the CPU state")
    flash = row["flash"]
    require(isinstance(flash, dict) and
            set(flash) == {"mode", "programmed_bytes", "erase", "auto_unlock",
                           "mass_erase", "automatic_recover"} and
            str(flash["mode"]).startswith("pyocd-sector") and
            integer(flash["programmed_bytes"], 1) and
            flash["erase"] == "sector" and flash["auto_unlock"] is False and
            flash["mass_erase"] is False and
            flash["automatic_recover"] is False,
            f"{expected_role} stored sector program receipt mismatch")
    return {
        "role": expected_role,
        "probe_sha256": row["probe_sha256"],
        "image_sha256": digest(image),
        "build_record_sha256": digest(build_record),
        "readback_sha256": digest(readback_path),
        "program_mode": flash["mode"],
        "programmed_bytes": flash["programmed_bytes"],
        "erase": flash["erase"],
        "auto_unlock": flash["auto_unlock"],
        "mass_erase": flash["mass_erase"],
        "automatic_recover": flash["automatic_recover"],
    }


def _validate_native_attestation(native: dict, native_path: Path, expected: dict,
                                 revision: str, cycles: int,
                                 hardware_override: list[dict] | None = None) -> list[dict]:
    """! @brief 원시 cycle·semantic·image/readback byte로 캠페인 PASS를 재구성합니다. """
    attestation = native.get("m33_dispatch_attestation")
    required = {
        "schema_version", "kind", "campaign_id", "source_revision",
        "source_clean", "semantic_status", "cycle_records", "hardware",
    }
    require(isinstance(attestation, dict) and set(attestation) == required and
            attestation["schema_version"] == 1 and
            attestation["kind"] == NATIVE_ATTESTATION_KIND and
            attestation["campaign_id"] == expected["id"] and
            attestation["source_revision"] == revision and
            attestation["source_clean"] is True,
            "native campaign attestation mismatch")
    records = attestation["cycle_records"]
    semantics = expected["semantics"]
    statuses = _validate_semantic_status(expected, attestation["semantic_status"])
    require(isinstance(records, list) and len(records) == cycles and
            [row.get("cycle") for row in records if isinstance(row, dict)] ==
            list(range(1, cycles + 1)), "native cycle denominator mismatch")
    for row in records:
        require(set(row) == {"cycle", "status", "semantics"} and
                row["status"] == "PASS" and
                row["semantics"] == statuses,
                "native cycle semantic evidence mismatch")
    rows = (attestation["hardware"] if hardware_override is None else
            hardware_override)
    roles = expected["roles"]
    if not roles:
        require(rows == [], "build-semantic native attestation cannot carry hardware")
        return []
    require(isinstance(rows, list) and len(rows) == len(roles) and
            {row.get("role") for row in rows if isinstance(row, dict)} == set(roles),
            "native hardware role denominator mismatch")
    hardware = []
    for row in rows:
        hardware.append(_validate_exact_program_row(
            row, native_path, row.get("role", "")
        ))
    require(len({row["probe_sha256"] for row in hardware}) == len(hardware),
            "native campaign probes must be distinct")
    return hardware


def _adapt_native_evidence(native_path: Path, child_path: Path, expected: dict,
                           revision: str, cycles: int,
                           central_hardware: list[dict] | None = None) -> list[dict]:
    """! @brief 등록 runner의 native JSON을 공통 child schema로 정규화합니다. """
    require(native_path.is_file() and native_path.suffix.lower() == ".json",
            "registered runner native JSON is missing")
    native = read_json(native_path)
    _validate_native_schema(native, native_path, expected, revision)
    if "m33_dispatch_attestation" not in native:
        require(expected["id"] in DERIVED_DISPATCH_CAMPAIGNS and
                (central_hardware is not None or not expected["roles"]),
                "native runner has no verified adapter attestation")
        statuses = {token: "PASS" for token in expected["semantics"]}
        native["m33_dispatch_attestation"] = {
            "schema_version": 1,
            "kind": NATIVE_ATTESTATION_KIND,
            "campaign_id": expected["id"],
            "source_revision": revision,
            "source_clean": True,
            "semantic_status": statuses,
            "cycle_records": [
                {"cycle": cycle, "status": "PASS",
                 "semantics": dict(statuses)}
                for cycle in range(1, cycles + 1)
            ],
            "hardware": central_hardware or [],
        }
    declared_hardware = _validate_native_attestation(
        native, native_path, expected, revision, cycles
    )
    hardware = declared_hardware
    if central_hardware is not None:
        hardware = _validate_native_attestation(
            native, native_path, expected, revision, cycles,
            hardware_override=central_hardware
        )
        require(
            {row["role"]: row for row in hardware} ==
            {row["role"]: row for row in declared_hardware},
            "dispatcher live readback differs from native program attestation",
        )
    child = {
        "schema_version": 1,
        "kind": "m33_campaign_child_result",
        "campaign_id": expected["id"],
        "status": "PASS",
        "source_revision": revision,
        "source_clean": True,
        "cycles": cycles,
        "semantics": expected["semantics"],
        "semantic_status": native["m33_dispatch_attestation"]["semantic_status"],
        "hardware": hardware,
        "native_evidence": {
            "path": native_path.relative_to(child_path.parent).as_posix(),
            "sha256": digest(native_path),
        },
    }
    if expected["verification"] == "build_semantic":
        child["external_interoperability"] = "NOT_RUN"
    _write_new_json(child_path, child)
    return _validate_child_adapter(
        child_path, expected, revision, cycles, native_path
    )


def revalidate_stored_campaign_bundle(child_path: Path, expected: dict,
                                      revision: str, cycles: int) -> list[dict]:
    """! @brief 저장 receipt의 child·native·sidecar byte를 raw oracle로 전부 재검증합니다.

    receipt와 child의 self-hash는 실행 권위가 아닙니다. 이 함수는 content-addressed
    native JSON을 다시 strict parse하고 campaign별 raw parser를 호출한 뒤, image와
    build-record 및 live all-range readback sidecar를 실제 byte에서 재구성합니다.
    """

    child = read_json(child_path)
    hardware = _validate_child_adapter(
        child_path, expected, revision, cycles
    )
    reference = child["native_evidence"]
    native_path = (child_path.parent / reference["path"]).resolve()
    native = read_json(native_path)
    _validate_native_schema(native, native_path, expected, revision)
    attestation = native.get("m33_dispatch_attestation")
    if isinstance(attestation, dict):
        regenerated = _validate_native_attestation(
            native, native_path, expected, revision, cycles
        )
    elif not expected["roles"]:
        regenerated = []
    else:
        rows = []
        by_role = {row["role"]: row for row in hardware}
        dispatcher = native_path.with_name(
            native_path.stem + ".dispatcher.json"
        )
        for role in expected["roles"]:
            flat = by_role[role]
            stem = dispatcher.stem
            row = {
                "role": role,
                "probe_sha256": flat["probe_sha256"],
                "image": {
                    "path": f"{stem}.{role}.image.hex",
                    "sha256": flat["image_sha256"],
                },
                "build_record": {
                    "path": f"{stem}.{role}.build-record",
                    "sha256": flat["build_record_sha256"],
                },
                "flash": {
                    "mode": flat["program_mode"],
                    "programmed_bytes": flat["programmed_bytes"],
                    "erase": flat["erase"],
                    "auto_unlock": flat["auto_unlock"],
                    "mass_erase": flat["mass_erase"],
                    "automatic_recover": flat["automatic_recover"],
                },
                "readback": {
                    "path": f"{stem}.{role}.readback.json",
                    "sha256": flat["readback_sha256"],
                },
            }
            rows.append(_validate_exact_program_row(row, native_path, role))
        regenerated = rows
    require(regenerated == hardware,
            "stored campaign child differs from raw native/program bytes")
    return hardware


def _validate_execution_spec(spec: dict, output: Path,
                             root: Path = ROOT) -> tuple[dict, list[dict]]:
    """! @brief 등록 campaign과 current clean source에 exact 실행 spec을 고정합니다. """
    required = {
        "schema_version", "kind", "field", "id", "source_revision",
        "source_clean", "campaign_plan", "campaigns",
    }
    field = spec.get("field")
    identifier = spec.get("id")
    if field == "families" and identifier == "ecosystem_templates":
        required.add("external_interoperability")
    elif field == "automatic_peers":
        required.add("external_interoperability")
    require(set(spec) == required and spec.get("schema_version") == 1 and
            spec.get("kind") == "m33_campaign_execution_spec" and
            field in CAMPAIGN_REGISTRIES and
            identifier in CAMPAIGN_REGISTRIES[field] and
            REV.fullmatch(spec.get("source_revision", "")) and
            spec.get("source_clean") is True,
            "campaign execution spec schema mismatch")
    revision, clean = _git_identity(root)
    require(clean and revision == spec["source_revision"],
            "campaign execution requires current clean exact source")
    expected_plan = campaign_plan(field, identifier, root)
    require(spec["campaign_plan"] == expected_plan,
            "campaign execution plan or source hash drift")
    rows = spec["campaigns"]
    require(isinstance(rows, list) and len(rows) == len(expected_plan["campaigns"]) and
            [row.get("id") for row in rows if isinstance(row, dict)] ==
            [row["id"] for row in expected_plan["campaigns"]],
            "campaign execution denominator/order mismatch")
    require(not output.exists() and output.suffix.lower() == ".json",
            "new campaign output JSON required")
    try:
        output.resolve().relative_to(root.resolve())
        inside_source = True
    except ValueError:
        inside_source = False
    require(not inside_source,
            "campaign execution output must be outside the source checkout")
    prepared = []
    planned_probe_hashes = {
        board.get("probe_sha256")
        for row in rows if isinstance(row, dict)
        for board in row.get("boards", []) if isinstance(board, dict)
        if SHA.fullmatch(board.get("probe_sha256", ""))
    }
    _reject_raw_probe_identity_bytes(
        json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        "campaign execution spec",
        planned_probe_hashes,
    )
    child_names = set()
    native_names = set()
    receipt_names = set()
    for row, expected in zip(rows, expected_plan["campaigns"]):
        row_required = {
            "id", "verification", "runner", "applications", "roles", "cycles",
            "semantics", "subcommand", "arguments", "timeout_seconds",
            "boards", "native_evidence", "child_evidence", "reuse_receipt",
        }
        require(set(row) == row_required and row["id"] == expected["id"] and
                row["verification"] == expected["verification"] and
                row["runner"] == expected["runner"] and
                row["applications"] == expected["applications"] and
                row["roles"] == expected["roles"] and
                integer(row["cycles"], expected["minimum_cycles"]) and
                row["semantics"] == expected["semantics"] and
                integer(row["timeout_seconds"], MIN_TIMEOUT_SECONDS,
                        campaign_timeout_seconds(expected)),
                "campaign execution row drift")
        runner = root / expected["runner"]["path"]
        require(digest(runner) == expected["runner"]["sha256"],
                "campaign runner source changed")
        reuse = row["reuse_receipt"]
        require(reuse is None or isinstance(reuse, dict),
                "campaign reuse receipt must be null or a content address")
        subcommand = row["subcommand"]
        options, subcommands = _runner_interface(runner, subcommand)
        require((subcommand is None and not subcommands) or
                (isinstance(subcommand, str) and subcommand in subcommands),
                "campaign runner subcommand is not allowed")
        if reuse is None:
            argv, output_arguments = _arguments_to_argv(row["arguments"], options)
        else:
            require(row["arguments"] == [],
                    "reused campaign must not execute runner arguments")
            argv, output_arguments = [], []
        board_plan = _validate_board_plan(row["boards"], expected)
        if reuse is None:
            _validate_argument_board_binding(expected, row["arguments"], board_plan)
            direct_images = _direct_program_images(expected, row["arguments"])
            require(all(path.is_file() for path in direct_images.values()),
                    "direct program image argument is missing")
        native_name = row["native_evidence"]
        require(isinstance(native_name, str) and native_name and
                Path(native_name).suffix.lower() == ".json" and
                native_name not in native_names,
                "campaign native evidence must be a unique JSON")
        native = (output.parent / native_name).resolve()
        try:
            native.relative_to(output.parent.resolve())
            native_in_bundle = True
        except ValueError:
            native_in_bundle = False
        require(native_in_bundle and
                ((reuse is None and not native.exists() and
                  _output_is_bound(output_arguments, native, root)) or
                 (reuse is not None and native.is_file())),
                "campaign native output is existing, missing, or not bound")
        child_name = row["child_evidence"]
        require(isinstance(child_name, str) and Path(child_name).name == child_name and
                child_name.endswith(".json") and child_name not in child_names,
                "campaign child evidence must be a unique adjacent JSON")
        child = output.parent / child_name
        require(((reuse is None and not child.exists()) or
                 (reuse is not None and child.is_file())) and
                child.resolve() != native,
                "campaign child output is existing, missing, or aliases native evidence")
        if reuse is None:
            receipt_name = f"campaign.{expected['id']}.receipt.json"
            receipt = output.parent / receipt_name
            require(not receipt.exists(), "campaign receipt overwrite refused")
        else:
            require(set(reuse) == {"path", "sha256"} and
                    isinstance(reuse.get("path"), str) and
                    Path(reuse["path"]).name == reuse["path"] and
                    SHA.fullmatch(reuse.get("sha256", "")),
                    "campaign reuse content address mismatch")
            receipt_name = reuse["path"]
            receipt = output.parent / receipt_name
            require(receipt.is_file() and digest(receipt) == reuse["sha256"],
                    "campaign reuse receipt byte mismatch")
        require(receipt_name not in receipt_names,
                "campaign receipt may appear only once per execution spec")
        child_names.add(child_name)
        native_names.add(native_name)
        receipt_names.add(receipt_name)
        command = [sys.executable, "-B", str(runner)]
        if subcommand is not None:
            command.append(subcommand)
        command.extend(argv)
        _reject_raw_probe_identity_bytes(
            json.dumps(command, ensure_ascii=False).encode("utf-8"),
            "campaign command",
            set(board_plan.values()),
        )
        prepared.append({
            "expected": expected,
            "row": row,
            "command": command,
            "board_plan": board_plan,
            "native": native,
            "child": child,
            "receipt": receipt,
            "reuse": reuse is not None,
        })
    if "external_interoperability" in spec:
        require(spec["external_interoperability"] == "NOT_RUN",
                "automatic/template execution cannot claim external interoperability")
    return expected_plan, prepared


def _automatic_peer_result(identifier: str, output: Path, revision: str,
                           expected_plan: dict,
                           campaign_results: list[dict]) -> dict:
    """! @brief 같은 실행의 scripted campaign PASS에서 자동 peer 증거를 생성합니다. """

    expected_ids = [row["id"] for row in expected_plan["campaigns"]]
    require([row.get("id") for row in campaign_results
             if isinstance(row, dict)] == expected_ids and
            all(row.get("status") == "PASS" and
                row.get("verification") == "physical_hil" and
                integer(row.get("cycles"), 20)
                for row in campaign_results),
            "automatic peer evidence requires complete scripted campaign PASS")
    evidence_path = output.with_name(
        f"{output.stem}.peer-{identifier}-discovery.json"
    )
    require(not evidence_path.exists(),
            "automatic peer discovery evidence overwrite refused")
    peer_identity = {
        "vendor": "NUCODE",
        "model": f"W06 scripted {identifier} peer",
        "os": "Zephyr",
        "os_version": "NCS 3.4.0",
        "adapter": "NU54DK",
        "app": ",".join(expected_ids),
    }
    evidence = {
        "schema_version": 1,
        "kind": "peer_support_discovery",
        "feature": identifier,
        "peer": peer_identity,
        "status": "PASS",
        "reason": None,
        "reason_code": "observed_pass",
        "support_discovery": "scripted_discovery",
        "source_revision": revision,
        "source_clean": True,
    }
    _write_new_json(evidence_path, evidence)
    result = {
        "feature": identifier,
        "kind": "automatic",
        "status": "PASS",
        "peer_support": "supported",
        "core_support": "supported",
        "peer": peer_identity,
        "verification_owner": "developer",
        "verification_stage": "development",
        "development_blocker": True,
        "release_blocker": True,
        "basis": "scripted_peer",
        "reason_code": "observed_pass",
        "support_discovery": "scripted_discovery",
        "evidence": {
            "path": evidence_path.name,
            "sha256": digest(evidence_path),
        },
        "qualification_status": "NOT_ASSESSED",
    }
    validate_peer(result)
    validate_peer_evidence(result, output.parent, revision)
    return result


def _run_pending_campaign(item: dict, output: Path, readiness: dict,
                          spec: dict, expected_plan: dict,
                          root: Path) -> tuple[list[dict], dict, dict]:
    """! @brief 연속 probe authority 안에서 restore·child·증거 확정을 수행합니다. """

    row = item["row"]
    expected = item["expected"]
    command = item["command"]
    plan = _state_restore_plan(
        expected, row, spec["source_revision"], root
    )
    with _campaign_probe_authority(
            plan, item["native"]) as (child_environment, authority):
        _restore_campaign_state(
            expected, row, item["native"], spec["source_revision"], root,
            plan=plan, authority=authority
        )
        started_ns = time.monotonic_ns()
        process = subprocess.Popen(
            command, cwd=str(root), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, shell=False, env=child_environment
        )
        timed_out = False
        try:
            raw_log, _ = process.communicate(timeout=row["timeout_seconds"])
        except subprocess.TimeoutExpired:
            process.kill()
            raw_log, _ = process.communicate()
            timed_out = True
        finished_ns = max(time.monotonic_ns(), started_ns + 1)
        log_path = output.parent / f"campaign.{expected['id']}.log"
        _reject_raw_probe_identity_bytes(
            raw_log, f"campaign runner log: {expected['id']}",
            set(item["board_plan"].values()),
        )
        _write_new_bytes(log_path, raw_log, "campaign runner log")
        if timed_out:
            raise execution.ExecutionFailure(
                "SAFETY", f"campaign runner timeout: {expected['id']}"
            )
        if process.returncode != 0:
            raise execution.ExecutionFailure(
                "INTERNAL", f"campaign runner failed: {expected['id']}"
            )
        revision, clean = _git_identity(root)
        require(clean and revision == spec["source_revision"] and
                campaign_plan(spec["field"], spec["id"], root) == expected_plan,
                "campaign source changed during execution")
        central_hardware = None
        if readiness[expected["id"]].get("central_direct_readback"):
            central_hardware = _central_program_hardware(
                expected, row, item["native"]
            )
        hardware = _adapt_native_evidence(
            item["native"], item["child"], expected, revision,
            row["cycles"], central_hardware
        )
        semantic_status = read_json(item["child"])["semantic_status"]
        receipt = {
            "schema_version": 1,
            "kind": "actual_runner_receipt",
            "campaign_id": expected["id"],
            "verification": expected["verification"],
            "status": "PASS",
            "source_revision": revision,
            "source_clean": True,
            "runner_sha256": expected["runner"]["sha256"],
            "application_sha256": {
                source["path"]: source["sha256"]
                for source in expected["applications"]
            },
            "roles": expected["roles"],
            "cycles": row["cycles"],
            "semantics": expected["semantics"],
            "semantic_status": semantic_status,
            "child_evidence": {
                "path": item["child"].name,
                "sha256": digest(item["child"]),
            },
            "exit_code": process.returncode,
            "pid": process.pid,
            "started_ns": started_ns,
            "finished_ns": finished_ns,
            "command_sha256": hashlib.sha256(json.dumps(
                command, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")).hexdigest(),
            "hardware": hardware,
        }
        encoded = json.dumps(
            receipt, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        receipt["sha256"] = hashlib.sha256(encoded).hexdigest()
        _write_new_json(item["receipt"], receipt)
    return hardware, receipt, semantic_status


def execute_campaign_spec(spec_path: Path, output: Path,
                          root: Path = ROOT) -> dict:
    """! @brief 등록 runner를 shell 없이 실행하고 새 child evidence를 receipt로 정규화합니다. """
    spec = read_json(spec_path)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    expected_plan, prepared = _validate_execution_spec(spec, output, root)
    pending = [item for item in prepared if not item["reuse"]]
    conflicts = [
        output.parent / f"campaign.{item['expected']['id']}.log"
        for item in pending
        if (output.parent / f"campaign.{item['expected']['id']}.log").exists()
    ]
    if spec["field"] == "automatic_peers":
        peer_path = output.with_name(
            f"{output.stem}.peer-{spec['id']}-discovery.json"
        )
        if peer_path.exists():
            conflicts.append(peer_path)
    require(not conflicts,
            "campaign pending output overwrite refused: " +
            ",".join(path.name for path in conflicts))
    readiness = ({row["id"]: row
                  for row in campaign_dispatch_matrix(root)["campaigns"]}
                 if pending else {})
    blocked = [item["expected"]["id"] for item in pending
               if readiness[item["expected"]["id"]]["status"] !=
               "DISPATCH_READY"]
    require(not blocked,
            "campaign dispatcher is fail-closed: " + ",".join(blocked))
    results = []
    for item in prepared:
        row = item["row"]
        expected = item["expected"]
        if item["reuse"]:
            reference = {"path": item["receipt"].name,
                         "sha256": digest(item["receipt"])}
            _validate_campaign_receipt(
                reference, output.parent, expected, spec["source_revision"],
                False, True
            )
            receipt = read_json(item["receipt"])
            require(receipt["cycles"] == row["cycles"] and
                    receipt["child_evidence"] == {
                        "path": item["child"].name,
                        "sha256": digest(item["child"]),
                    }, "reused campaign denominator/child mismatch")
            hardware = _validate_child_adapter(
                item["child"], expected, spec["source_revision"], row["cycles"],
                item["native"]
            )
        else:
            hardware, receipt, semantic_status = _run_pending_campaign(
                item, output, readiness, spec, expected_plan, root
            )
        execution_board_plan = {
            role: item["board_plan"][role] for role in expected["roles"]
        }
        require({entry["role"]: entry["probe_sha256"] for entry in hardware} ==
                execution_board_plan,
                "campaign child board mapping differs from execution plan")
        if item["reuse"]:
            semantic_status = read_json(item["child"])["semantic_status"]
        results.append({
            "id": expected["id"],
            "status": "PASS",
            "verification": expected["verification"],
            "runner": expected["runner"],
            "applications": expected["applications"],
            "roles": expected["roles"],
            "cycles": row["cycles"],
            "semantics": expected["semantics"],
            "semantic_status": semantic_status,
            "evidence": {
                "path": item["receipt"].name,
                "sha256": digest(item["receipt"]),
            },
        })
    result = {
        "schema_version": 1,
        "evidence_kind": "m33_actual_campaign_result",
        "field": spec["field"],
        "id": spec["id"],
        "status": "PASS",
        "source_revision": spec["source_revision"],
        "source_clean": True,
        "campaign_plan": expected_plan,
        "campaign_results": results,
        "failures": 0,
    }
    if "external_interoperability" in spec:
        result["external_interoperability"] = "NOT_RUN"
    if spec["field"] == "automatic_peers":
        result["peer_result"] = _automatic_peer_result(
            spec["id"], output, spec["source_revision"],
            expected_plan, results
        )
    validate_campaign_evidence(
        result, output, spec["field"], spec["id"], spec["source_revision"],
        allow_physical_audit=True
    )
    _write_new_json(output, result)
    validate_campaign_evidence(
        read_json(output), output, spec["field"], spec["id"],
        spec["source_revision"], allow_physical_audit=True
    )
    return result


def _write_new_json(path: Path, value: dict) -> None:
    """! @brief matrix spec/manifest를 기존 byte 덮어쓰기 없이 기록합니다. """

    execution.write_new_json(path, value)


def _matrix_group_paths(output_root: Path, ordinal: int, field: str,
                        identifier: str, attempt: int) -> tuple[Path, Path]:
    """! @brief 한 group의 append-only attempt spec/result 경로를 반환합니다. """

    require(type(attempt) is int and attempt >= 1,
            "campaign matrix attempt must be positive")
    stem = (
        f"campaign-group.{ordinal:02d}.{field}.{identifier}.attempt-{attempt}"
    )
    attempt_root = output_root / ".campaign-attempts" / stem
    return attempt_root / "spec.json", attempt_root / "result.json"


def _matrix_session(
    output_root: Path,
    groups: list[tuple[str, str]],
    revision: str,
    board_inventory: Path,
    artifact_root: Path,
    sdk_root: Path,
    toolchain: Path,
) -> tuple[Path, dict]:
    """! @brief 재개 전 source·입력·group 분모를 immutable session에 고정합니다. """

    inventory_path = board_inventory.resolve()
    value = {
        "schema_version": 1,
        "kind": "m33_campaign_matrix_session",
        "source_revision": revision,
        "source_clean": True,
        "board_inventory": {
            "path": str(inventory_path),
            "sha256": digest(inventory_path),
        },
        "artifact_root": str(artifact_root.resolve()),
        "sdk_root": str(sdk_root.resolve()),
        "toolchain": str(toolchain.resolve()),
        "group_count": len(groups),
        "groups": [
            {"ordinal": ordinal, "field": field, "id": identifier}
            for ordinal, (field, identifier) in enumerate(groups, start=1)
        ],
    }
    path = output_root / "m33-campaign-matrix.session.json"
    if path.exists():
        require(read_json(path) == value,
                "campaign matrix resume session/input mismatch")
    else:
        _write_new_json(path, value)
    return path, value


def _matrix_attempt_numbers(output_root: Path, ordinal: int, field: str,
                            identifier: str) -> list[int]:
    """! @brief 보존된 group attempt가 1부터 빈틈없이 이어지는지 검사합니다. """

    attempts_root = output_root / ".campaign-attempts"
    if not attempts_root.exists():
        return []
    require(attempts_root.is_dir() and not attempts_root.is_symlink(),
            "campaign matrix attempts root mismatch")
    prefix = f"campaign-group.{ordinal:02d}.{field}.{identifier}.attempt-"
    attempts = []
    for path in attempts_root.iterdir():
        if not path.name.startswith(prefix):
            continue
        suffix = path.name[len(prefix):]
        require(path.is_dir() and not path.is_symlink() and
                re.fullmatch(r"[1-9][0-9]*", suffix) is not None,
                "campaign matrix attempt directory mismatch")
        attempts.append(int(suffix))
    attempts.sort()
    require(attempts == list(range(1, len(attempts) + 1)),
            "campaign matrix attempt sequence has a gap")
    return attempts


def _matrix_reference(path: Path, output_root: Path) -> dict[str, str]:
    """! @brief matrix bundle 내부 상대 경로와 byte hash를 반환합니다. """

    relative = path.resolve().relative_to(output_root.resolve()).as_posix()
    return {"path": relative, "sha256": digest(path)}


def _validate_completed_matrix_group(
    spec_path: Path,
    result_path: Path,
    field: str,
    identifier: str,
    revision: str,
    root: Path = ROOT,
) -> dict:
    """! @brief 완료 group의 original spec과 actual evidence 사슬을 재실행 없이 검증합니다. """

    spec = read_json(spec_path)
    result = read_json(result_path)
    required = {
        "schema_version", "kind", "field", "id", "source_revision",
        "source_clean", "campaign_plan", "campaigns",
    }
    if field == "automatic_peers" or (
            field == "families" and identifier == "ecosystem_templates"):
        required.add("external_interoperability")
    plan = campaign_plan(field, identifier, root)
    require(set(spec) == required and spec["schema_version"] == 1 and
            spec["kind"] == "m33_campaign_execution_spec" and
            spec["field"] == field and spec["id"] == identifier and
            spec["source_revision"] == revision and
            spec["source_clean"] is True and spec["campaign_plan"] == plan,
            "completed matrix execution spec mismatch")
    rows = spec["campaigns"]
    require(isinstance(rows, list) and len(rows) == len(plan["campaigns"]) and
            [row.get("id") for row in rows if isinstance(row, dict)] ==
            [row["id"] for row in plan["campaigns"]],
            "completed matrix spec campaign order mismatch")
    planned_probe_hashes = {
        board.get("probe_sha256")
        for row in rows if isinstance(row, dict)
        for board in row.get("boards", []) if isinstance(board, dict)
        if SHA.fullmatch(board.get("probe_sha256", ""))
    }
    _reject_raw_probe_identity_bytes(
        json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        "completed campaign execution spec",
        planned_probe_hashes,
    )
    validate_campaign_evidence(
        result, result_path, field, identifier, revision,
        allow_physical_audit=True
    )
    result_rows = result["campaign_results"]
    for row, expected, observed in zip(
            rows, plan["campaigns"], result_rows, strict=True):
        row_required = {
            "id", "verification", "runner", "applications", "roles", "cycles",
            "semantics", "subcommand", "arguments", "timeout_seconds",
            "boards", "native_evidence", "child_evidence", "reuse_receipt",
        }
        require(set(row) == row_required and row["id"] == expected["id"] and
                row["verification"] == expected["verification"] and
                row["runner"] == expected["runner"] and
                row["applications"] == expected["applications"] and
                row["roles"] == expected["roles"] and
                integer(row["cycles"], expected["minimum_cycles"]) and
                row["semantics"] == expected["semantics"] and
                integer(row["timeout_seconds"], MIN_TIMEOUT_SECONDS,
                        campaign_timeout_seconds(expected)),
                "completed matrix campaign spec row mismatch")
        board_plan = _validate_board_plan(row["boards"], expected)
        runner = root / expected["runner"]["path"]
        require(runner.is_file() and digest(runner) == expected["runner"]["sha256"],
                "completed matrix runner source changed")
        options, subcommands = _runner_interface(runner, row["subcommand"])
        require((row["subcommand"] is None and not subcommands) or
                (isinstance(row["subcommand"], str) and
                 row["subcommand"] in subcommands),
                "completed matrix runner subcommand mismatch")
        reuse = row["reuse_receipt"]
        if reuse is None:
            _, output_arguments = _arguments_to_argv(row["arguments"], options)
            _validate_argument_board_binding(expected, row["arguments"], board_plan)
            require(all(path.is_file() for path in
                        _direct_program_images(expected, row["arguments"]).values()),
                    "completed matrix direct image missing")
            native = (result_path.parent / row["native_evidence"]).resolve()
            require(native.is_file() and
                    _output_is_bound(output_arguments, native, root),
                    "completed matrix native output binding mismatch")
        else:
            require(row["arguments"] == [] and
                    isinstance(reuse, dict) and
                    set(reuse) == {"path", "sha256"},
                    "completed matrix reuse spec mismatch")
        receipt_path = adjacent_evidence_file(
            observed["evidence"], result_path.parent
        )
        receipt = read_json(receipt_path)
        require((reuse is not None or
                 receipt_path.name == f"campaign.{expected['id']}.receipt.json") and
                (reuse is None or reuse == observed["evidence"]) and
                receipt["child_evidence"]["path"] == row["child_evidence"],
                "completed matrix result/spec receipt mismatch")
        child_path = adjacent_evidence_file(
            receipt["child_evidence"], result_path.parent
        )
        child = read_json(child_path)
        native_path = (result_path.parent / child["native_evidence"]["path"]).resolve()
        require(native_path.is_file() and digest(native_path) ==
                child["native_evidence"]["sha256"] and
                native_path == (result_path.parent /
                                row["native_evidence"]).resolve(),
                "completed matrix native evidence mismatch")
        if reuse is None and expected["id"] in PRE_RUN_STATE_RESTORE:
            restore_path = native_path.with_name(
                f"{native_path.stem}.pre-run-restore.json"
            )
            _validate_state_restore_receipt(
                restore_path, expected, row, revision, root
            )
    return result


def _execute_campaign_matrix(
    board_inventory: Path,
    artifact_root: Path,
    output_root: Path,
    sdk_root: Path,
    toolchain: Path,
    root: Path = ROOT,
) -> dict:
    """! @brief 33+8+8 group을 결정적 순서로 prepare+execute하고 완료 group만 resume합니다. """

    output_root = output_root.resolve()
    require(output_root.is_dir(), "existing matrix output root required")
    try:
        output_root.relative_to(root.resolve())
        inside_source = True
    except ValueError:
        inside_source = False
    require(not inside_source, "matrix output root must be outside source checkout")
    revision, clean = _git_identity(root)
    require(clean, "campaign matrix requires current clean source")
    inventory = read_json(board_inventory.resolve())
    groups = [
        (field, identifier)
        for field, registry in CAMPAIGN_REGISTRIES.items()
        for identifier in registry
    ]
    session_path, _session = _matrix_session(
        output_root, groups, revision, board_inventory, artifact_root,
        sdk_root, toolchain
    )
    manifest_path = output_root / "m33-campaign-matrix.json"
    if manifest_path.exists():
        paths = campaign_matrix_paths(manifest_path, revision)
        manifest = read_json(manifest_path)
        require(manifest.get("schema_version") == 2 and
                manifest.get("session") == {
                    "path": session_path.name,
                    "sha256": digest(session_path),
                }, "campaign matrix manifest/session mismatch")
        for ordinal, ((field, identifier), row) in enumerate(
                zip(groups, manifest["groups"], strict=True), start=1):
            spec_path = (output_root / row["spec"]["path"]).resolve()
            result_path = paths[(field, identifier)]
            expected_spec, expected_result = _matrix_group_paths(
                output_root, ordinal, field, identifier, row["attempt"]
            )
            require(spec_path == expected_spec.resolve() and
                    result_path == expected_result.resolve(),
                    "campaign matrix deterministic attempt path mismatch")
            _validate_completed_matrix_group(
                spec_path, result_path, field, identifier, revision, root
            )
        final_revision, final_clean = _git_identity(root)
        require(final_clean and final_revision == revision,
                "campaign matrix source changed during resume validation")
        return manifest
    rows = []
    completed_paths = {}
    for ordinal, (field, identifier) in enumerate(groups, start=1):
        attempts = _matrix_attempt_numbers(
            output_root, ordinal, field, identifier
        )
        completed = []
        attempt_rows = []
        for attempt in attempts:
            spec_path, result_path = _matrix_group_paths(
                output_root, ordinal, field, identifier, attempt
            )
            if spec_path.is_file() and result_path.is_file():
                # @note result는 완료 때만 생성됩니다. 손상된 완료 증거를 재시도 FAIL로 낮추지 않습니다.
                _validate_completed_matrix_group(
                    spec_path, result_path, field, identifier, revision, root
                )
                completed.append((attempt, spec_path, result_path))
                attempt_rows.append({
                    "attempt": attempt,
                    "status": "PASS",
                    "spec": _matrix_reference(spec_path, output_root),
                    "evidence": _matrix_reference(result_path, output_root),
                })
            else:
                require(not result_path.exists() or spec_path.exists(),
                        "campaign matrix result exists without its spec")
                attempt_row = {"attempt": attempt, "status": "INCOMPLETE"}
                if spec_path.is_file():
                    attempt_row["spec"] = _matrix_reference(
                        spec_path, output_root
                    )
                failure_path = spec_path.parent / "failure.json"
                if failure_path.exists():
                    failure = execution.read_json(failure_path)
                    require(failure.get("source_revision") == revision and
                            failure.get("spec_sha256") == digest(spec_path) and
                            failure.get("status") == "FAIL" and
                            failure.get("category") in execution.CATEGORIES,
                            "campaign matrix failure/source mismatch")
                    execution.validate_references(spec_path.parent, failure["outputs"])
                    require(failure["category"] not in {"SAFETY", "INTEGRITY"},
                            "campaign matrix requires safety/integrity investigation")
                    attempt_row["failure"] = _matrix_reference(failure_path, output_root)
                attempt_rows.append(attempt_row)
        require(len(completed) <= 1,
                "campaign matrix group has multiple completed attempts")
        if completed:
            attempt, spec_path, result_path = completed[0]
            require(attempt == attempts[-1],
                    "campaign matrix has attempts after a completed group")
        else:
            attempt = len(attempts) + 1
            spec_path, result_path = _matrix_group_paths(
                output_root, ordinal, field, identifier, attempt
            )
            spec_path.parent.mkdir(parents=True, exist_ok=False)
            spec = prepare_execution_spec(
                field, identifier, inventory, artifact_root.resolve(),
                spec_path.parent, sdk_root.resolve(), toolchain.resolve(), root
            )
            current_revision, current_clean = _git_identity(root)
            require(current_clean and current_revision == revision,
                    "campaign matrix source changed during preparation")
            _write_new_json(spec_path, spec)
            try:
                execute_campaign_spec(spec_path, result_path, root)
            except BaseException as error:
                if not result_path.exists():
                    outputs = sorted(path for path in spec_path.parent.rglob("*")
                                     if path.is_file() and not path.is_symlink())
                    _write_new_json(spec_path.parent / "failure.json", {
                        **execution.failure_record(error),
                        "source_revision": revision,
                        "spec_sha256": digest(spec_path),
                        "outputs": execution.references(spec_path.parent, outputs),
                    })
                raise
            _validate_completed_matrix_group(
                spec_path, result_path, field, identifier, revision, root
            )
            attempt_rows.append({
                "attempt": attempt,
                "status": "PASS",
                "spec": _matrix_reference(spec_path, output_root),
                "evidence": _matrix_reference(result_path, output_root),
            })
        completed_paths[(field, identifier)] = result_path
        rows.append({
            "ordinal": ordinal,
            "field": field,
            "id": identifier,
            "attempt": attempt,
            "status": "PASS",
            "attempts": attempt_rows,
            "spec": _matrix_reference(spec_path, output_root),
            "evidence": _matrix_reference(result_path, output_root),
        })
    final_revision, final_clean = _git_identity(root)
    require(final_clean and final_revision == revision,
            "campaign matrix source changed during execution")
    manifest = {
        "schema_version": 2,
        "kind": "m33_campaign_matrix_result",
        "status": "PASS",
        "source_revision": revision,
        "source_clean": True,
        "session": {
            "path": session_path.name,
            "sha256": digest(session_path),
        },
        "group_count": len(rows),
        "groups": rows,
    }
    _write_new_json(manifest_path, manifest)
    require(campaign_matrix_paths(manifest_path, revision) == completed_paths,
            "campaign matrix manifest revalidation mismatch")
    return manifest


def execute_campaign_matrix(
    board_inventory: Path, artifact_root: Path, output_root: Path,
    sdk_root: Path, toolchain: Path, root: Path = ROOT,
) -> dict:
    """! @brief 동일 matrix에 두 writer가 접근하지 못하게 한 뒤 순차 재개합니다. """

    require(output_root.is_dir() and not output_root.resolve().is_relative_to(root.resolve()),
            "existing matrix output root outside source required")
    with execution.exclusive(output_root):
        return _execute_campaign_matrix(board_inventory, artifact_root, output_root,
                                        sdk_root, toolchain, root)


def main() -> int:
    """! @brief 실제 campaign 계획·실행·증거와 3보드 soak를 검증합니다. """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("plan", "dispatch-matrix", "prepare-spec", "execute-campaign",
                 "execute-matrix", "validate-soak", "validate-campaign"),
    )
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--field", choices=tuple(CAMPAIGN_REGISTRIES))
    parser.add_argument("--identifier")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--board-inventory", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--sdk-root", type=Path)
    parser.add_argument("--toolchain", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = {
                "soak": hil_contract(),
                "campaigns": {
                    field: {
                        identifier: campaign_plan(field, identifier)
                        for identifier in registry
                    }
                    for field, registry in CAMPAIGN_REGISTRIES.items()
                },
            }
        elif args.command == "dispatch-matrix":
            result = campaign_dispatch_matrix()
        elif args.command == "prepare-spec":
            require(args.field is not None and args.identifier is not None and
                    args.board_inventory is not None and
                    args.artifact_root is not None and
                    args.output_root is not None and args.sdk_root is not None and
                    args.toolchain is not None and args.output is not None,
                    "preparation inputs and output required")
            result = prepare_execution_spec(
                args.field, args.identifier, read_json(args.board_inventory.resolve()),
                args.artifact_root.resolve(), args.output_root.resolve(),
                args.sdk_root.resolve(), args.toolchain.resolve()
            )
        elif args.command == "execute-campaign":
            require(args.spec is not None and args.output is not None,
                    "spec and output required")
            result = execute_campaign_spec(
                args.spec.resolve(), args.output.resolve()
            )
        elif args.command == "execute-matrix":
            require(args.board_inventory is not None and
                    args.artifact_root is not None and
                    args.output_root is not None and args.sdk_root is not None and
                    args.toolchain is not None,
                    "matrix board, artifact, output, SDK, and toolchain inputs required")
            result = execute_campaign_matrix(
                args.board_inventory, args.artifact_root, args.output_root,
                args.sdk_root, args.toolchain
            )
        elif args.command == "validate-soak":
            require(args.evidence is not None and args.revision is not None,
                    "evidence and revision required")
            result = validate_soak(
                args.evidence.resolve(), args.revision, args.development,
                allow_physical_audit=True
            )
        else:
            require(args.evidence is not None and args.revision is not None and
                    args.field is not None and args.identifier is not None,
                    "evidence, revision, field, and identifier required")
            evidence = args.evidence.resolve()
            result = validate_campaign_evidence(
                read_json(evidence), evidence, args.field, args.identifier,
                args.revision, allow_physical_audit=True
            )
            result.update(
                schema_version=1, source_revision=args.revision,
                field=args.field, identifier=args.identifier,
                source_evidence_sha256=digest(evidence)
            )
        if args.output and args.command != "execute-campaign":
            require(not args.output.exists(), "existing evidence is never overwritten")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError,
            subprocess.SubprocessError) as error:
        message = re.sub(
            r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error)
        )
        print(f"M33 evidence rejected: {message[:400]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
