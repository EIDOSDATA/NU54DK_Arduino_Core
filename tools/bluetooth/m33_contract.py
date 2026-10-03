#!/usr/bin/env python3
"""! @brief M33 예제 원장·릴리스 계약을 생성하고 fail-closed로 검증합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


CORE = Path(__file__).resolve().parents[2]
LOCK_PATH = CORE / "tools/ci/ncs-3.4.0.lock.json"
PARITY_PATH = CORE / "variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json"
TARGET_PATH = CORE / "variants/nu54dk/m33-release-readiness.json"
M31_PATH = CORE / "variants/nu54dk/m31-ble-readiness.json"
M32_PATH = CORE / "variants/nu54dk/m32-ble-readiness.json"
CONTRACT_EVIDENCE = (
    "00_Docs/01_아두이노 코어 설계/23_M33_전체_예제_원장과_릴리스_계약.md"
)
LOCK = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
PARITY = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
M31 = json.loads(M31_PATH.read_text(encoding="utf-8"))
M32 = json.loads(M32_PATH.read_text(encoding="utf-8"))
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
SERVICE_DEFINE_PATTERN = re.compile(
    r"^#define\s+(BT_UUID_[A-Z0-9_]+_VAL)\s+(0x18[0-9A-Fa-f]{2})\b"
)
WORK_TITLES = (
    "sample_profile_example_catalog",
    "standard_gatt_and_beacons",
    "external_ecosystem_and_companions",
    "dtm_hci_and_diagnostic_templates",
    "installed_example_quality_and_lifecycle",
    "resource_regression_interoperability_qualification",
    "multi_host_release_candidate",
    "approved_public_release_and_handoff",
)
TEST_FAMILY_IDS = (
    "M33-INV-01",
    "M33-PROFILE-01",
    "M33-BEACON-01",
    "M33-ECOSYSTEM-01",
    "M33-DIAG-01",
    "M33-EXAMPLE-01",
    "M33-REG-01",
    "M33-RESOURCE-01",
    "M33-INTEROP-01",
    "M33-PACKAGE-01",
    "M33-INSTALL-01",
    "M33-RELEASE-01",
)
TEST_OWNER = {
    "M33-INV-01": "M33-W01",
    "M33-PROFILE-01": "M33-W02",
    "M33-BEACON-01": "M33-W02",
    "M33-ECOSYSTEM-01": "M33-W03",
    "M33-DIAG-01": "M33-W04",
    "M33-EXAMPLE-01": "M33-W05",
    "M33-REG-01": "M33-W06",
    "M33-RESOURCE-01": "M33-W06",
    "M33-INTEROP-01": "M33-W06",
    "M33-PACKAGE-01": "M33-W07",
    "M33-INSTALL-01": "M33-W07",
    "M33-RELEASE-01": "M33-W08",
}
OWNER_TEST_IDS = {
    "M31-W02": ("M31-ISO-01",),
    "M31-W03": ("M31-AUDIO-01",),
    "M31-W04": ("M31-DF-01",),
    "M31-W05": ("M31-CS-01",),
    "M32-W01": ("M32-CAP-01",),
    "M32-W02": ("M32-PWR-01", "M32-PATH-01"),
    "M32-W03": ("M32-SUB-01", "M32-SCA-01", "M32-TIME-01", "M32-FEAT-01"),
    "M32-W04": ("M32-ADV-01", "M32-PRIV-01", "M32-EAD-01"),
    "M32-W05": ("M32-NORDIC-01", "M32-SYNC-01", "M32-EVENT-01", "M32-ACL-01"),
    "M32-W06": ("M32-MESH-01", "M32-MESHSEC-01"),
    "M32-W07": ("M32-MESH11-01",),
    "M32-W08": ("M32-BLOB-01", "M32-MDFU-01"),
    "M32-W10": ("M32-COEX-01",),
    "M33-W01": ("M33-INV-01",),
    "M33-W02": ("M33-PROFILE-01", "M33-BEACON-01"),
    "M33-W03": ("M33-ECOSYSTEM-01",),
    "M33-W04": ("M33-DIAG-01",),
}
M31_LIBRARY_OWNERS = {
    "NUCODE_BLE_ISO": "M31-W02",
    "NUCODE_BLE_Audio": "M31-W03",
    "NUCODE_BLE_DirectionFinding": "M31-W04",
    "NUCODE_BLE_ChannelSounding": "M31-W05",
}
M32_LIBRARY_OWNERS = {
    "NUCODE_BLE_Mesh": "M32-W06",
    "NUCODE_BLE_Mesh_Management": "M32-W07",
    "NUCODE_BLE_Mesh_Update": "M32-W08",
    "NUCODE_Radio_IEEE802154": "M32-W09",
    "NUCODE_Radio_ESB": "M32-W09",
    "NUCODE_Radio_Coexistence": "M32-W10",
}
M29_EXAMPLE_PREFIXES = (
    "CustomGatt", "Gatt", "L2cap", "LongGatt", "ReliableWrite", "MixedGattCoc",
)
M28_EXAMPLE_PREFIXES = (
    "GAP", "Extended", "MixedRole", "MultiplePeriodic", "NUS", "Past", "Pawr",
    "Periodic", "PerLink", "Privacy",
)
M33_SERVICE_MACROS = {
    "BT_UUID_ANS_VAL", "BT_UUID_CSC_VAL", "BT_UUID_CGMS_VAL", "BT_UUID_CTS_VAL",
    "BT_UUID_ETS_VAL", "BT_UUID_HTS_VAL", "BT_UUID_BMS_VAL", "BT_UUID_OTS_VAL",
    "BT_UUID_RSCS_VAL",
}
M31_AUDIO_SERVICE_MACROS = {
    "BT_UUID_AICS_VAL", "BT_UUID_VCS_VAL", "BT_UUID_VOCS_VAL", "BT_UUID_CSIS_VAL",
    "BT_UUID_MCS_VAL", "BT_UUID_GMCS_VAL", "BT_UUID_CTES_VAL", "BT_UUID_TBS_VAL",
    "BT_UUID_GTBS_VAL", "BT_UUID_MICS_VAL", "BT_UUID_ASCS_VAL", "BT_UUID_BASS_VAL",
    "BT_UUID_PACS_VAL", "BT_UUID_BASIC_AUDIO_VAL", "BT_UUID_BROADCAST_AUDIO_VAL",
    "BT_UUID_CAS_VAL", "BT_UUID_HAS_VAL", "BT_UUID_TMAS_VAL", "BT_UUID_PBA_VAL",
}
M32_MESH_SERVICE_MACROS = {
    "BT_UUID_MESH_PROV_VAL", "BT_UUID_MESH_PROXY_VAL",
    "BT_UUID_MESH_PROXY_SOLICITATION_VAL",
}
BASELINE_SERVICE_MACROS = {
    "BT_UUID_GAP_VAL", "BT_UUID_GATT_VAL", "BT_UUID_DIS_VAL", "BT_UUID_HRS_VAL",
    "BT_UUID_BAS_VAL", "BT_UUID_HIDS_VAL", "BT_UUID_ESS_VAL",
}
M33_FUNCTIONAL_GROUPS = {
    "M33-W02": (
        "object_transfer", "alert_notification", "current_time",
        "health_thermometer", "cycling_speed_cadence",
        "running_speed_cadence", "continuous_glucose_monitoring",
        "bond_management", "environmental_sensing",
        "ibeacon", "eddystone", "bthome",
    ),
    "M33-W03": (
        "apple_ancs", "apple_ams", "google_fast_pair_input",
        "vendor_ecosystem_templates",
    ),
    "M33-W04": (
        "direct_test_mode", "hci_uart", "hci_3wire", "hci_spi",
        "hci_usb", "hci_ipc",
    ),
}
START_HERE_JOURNEYS = (
    ("board_first_steps", "보드 연결과 첫 실행", (
        "libraries/NUCODE_NU54DK/examples/Blink/Blink.ino",
        "libraries/NUCODE_NU54DK/examples/BoardInfo/BoardInfo.ino",
    )),
    ("serial_and_pins", "통신과 runtime pin 변경", (
        "libraries/NUCODE_NU54DK/examples/Serial1RuntimePins/Serial1RuntimePins.ino",
        "libraries/NUCODE_NU54DK/examples/WireRuntimePins/WireRuntimePins.ino",
        "libraries/NUCODE_NU54DK/examples/SPI00RuntimePins/SPI00RuntimePins.ino",
    )),
    ("persistent_storage", "설정과 파일 저장", (
        "libraries/NUCODE_NU54DK/examples/SettingsStorage/SettingsStorage.ino",
        "libraries/LittleFS/examples/LittleFSPersistence/LittleFSPersistence.ino",
    )),
    ("peripheral_fabric", "주변장치 직접 제어", (
        "libraries/NUCODE_Peripheral_Fabric/examples/FabricCapabilities/FabricCapabilities.ino",
    )),
    ("first_connection", "BLE 연결부터 시작", (
        "libraries/NUCODE_BLE/examples/GAPPeripheral/GAPPeripheral.ino",
        "libraries/NUCODE_BLE/examples/GAPCentral/GAPCentral.ino",
    )),
    ("wireless_serial", "BLE UART로 데이터 교환", (
        "libraries/NUCODE_BLE/examples/NUSPeripheral/NUSPeripheral.ino",
        "libraries/NUCODE_BLE/examples/NUSCentral/NUSCentral.ino",
    )),
    ("secure_sensor_input", "보안 센서와 입력 장치", (
        "libraries/NUCODE_BLE_Security/examples/HeartRate/HeartRate.ino",
        "libraries/NUCODE_BLE_Security/examples/SecureKeyboard/SecureKeyboard.ino",
    )),
    ("multiple_links", "두 link와 L2CAP CoC", (
        "libraries/NUCODE_BLE/examples/MixedRoleLinks/MixedRoleLinks.ino",
        "libraries/NUCODE_BLE/examples/L2capCocClient/L2capCocClient.ino",
        "libraries/NUCODE_BLE/examples/L2capCocServer/L2capCocServer.ino",
    )),
    ("mesh_control", "Mesh 장치 제어", (
        "libraries/NUCODE_BLE_Mesh/examples/MeshOnOff/MeshOnOff.ino",
        "libraries/NUCODE_BLE_Mesh/examples/MeshProvisioner/MeshProvisioner.ino",
    )),
    ("audio_stream", "LE Audio 양방향 stream", (
        "libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexClient/BapUnicastDuplexClient.ino",
        "libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexServer/BapUnicastDuplexServer.ino",
    )),
    ("distance_measurement", "Channel Sounding 거리 측정", (
        "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator/RasInitiator.ino",
        "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector/RasReflector.ino",
    )),
    ("secure_update", "서명된 BLE firmware update", (
        "libraries/NUCODE_BLE_DFU/examples/SecureDfuPeripheral/SecureDfuPeripheral.ino",
    )),
)
START_HERE_PATHS = frozenset(
    path for _, _, sketches in START_HERE_JOURNEYS for path in sketches
)
REQUIRED_EXAMPLE_GUIDANCE = (
    "purpose", "requirements", "configuration", "run_steps",
    "success_output", "common_errors", "next_examples",
)


def _sha256_bytes(payload: bytes) -> str:
    """! @brief byte 열의 SHA-256을 계산합니다. """
    return hashlib.sha256(payload).hexdigest()


def _sha256_json(value: object) -> str:
    """! @brief JSON 값을 정규 직렬화해 범위 hash를 계산합니다. """
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _git_revision(path: Path) -> str:
    """! @brief SDK module checkout의 exact revision을 읽습니다. """
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _parity_scope() -> dict:
    """! @brief Master parity와 M33 소유 범위를 결정적으로 고정합니다. """
    m33_sample_ids = sorted(
        entry["id"] for entry in PARITY["samples"]
        if str(entry.get("owner_work_id", "")).startswith("M33-")
    )
    m33_variant_ids = sorted(
        entry["id"] for entry in PARITY["variants"]
        if str(entry.get("owner_work_id", "")).startswith("M33-")
    )
    selected = {
        "samples": [
            entry for entry in PARITY["samples"] if entry["id"] in set(m33_sample_ids)
        ],
        "variants": [
            entry for entry in PARITY["variants"] if entry["id"] in set(m33_variant_ids)
        ],
    }
    return {
        "master_sample_count": len(PARITY["samples"]),
        "master_variant_count": len(PARITY["variants"]),
        "master_source_only_feature_count": len(PARITY["source_only_features"]),
        "master_rows_sha256": _sha256_json({
            "samples": PARITY["samples"],
            "variants": PARITY["variants"],
            "source_only_features": PARITY["source_only_features"],
        }),
        "m33_sample_ids": m33_sample_ids,
        "m33_variant_ids": m33_variant_ids,
        "m33_sample_count": len(m33_sample_ids),
        "m33_variant_count": len(m33_variant_ids),
        "m33_rows_sha256": _sha256_json(selected),
    }


def _sample_test_ids(sample: dict, variants: list[dict]) -> list[str]:
    """! @brief sample의 기존 또는 M33 예정 시험 ID를 빠짐없이 연결합니다. """
    test_ids = sorted({
        entry["verification_contract"]["local_test_id"]
        for entry in variants
        if entry["verification_contract"].get("local_test_id")
    })
    if test_ids:
        return test_ids
    return list(OWNER_TEST_IDS.get(sample["owner_work_id"], ()))


def _upstream_catalog() -> list[dict]:
    """! @brief 190개 upstream sample을 owner·route·test와 한 행씩 연결합니다. """
    variants_by_parent: dict[str, list[dict]] = {}
    for variant in PARITY["variants"]:
        variants_by_parent.setdefault(variant["parent_sample_id"], []).append(variant)
    rows = []
    for sample in PARITY["samples"]:
        variants = variants_by_parent.get(sample["id"], [])
        if sample["exclusion_reason"]:
            delivery_state = "excluded_with_reason"
        elif sample["owner_work_id"].startswith(("M31-", "M32-")):
            delivery_state = "existing_owner_result"
        elif sample["owner_work_id"] == "M33-W01":
            delivery_state = "catalog_decision_required"
        else:
            delivery_state = "planned_m33_implementation"
        rows.append({
            "id": sample["id"],
            "upstream_module": sample["upstream_module"],
            "upstream_path": sample["upstream_path"],
            "owner_work_id": sample["owner_work_id"],
            "route": sample["route"],
            "delivery_state": delivery_state,
            "exclusion_reason": sample["exclusion_reason"],
            "variant_ids": sorted(entry["id"] for entry in variants),
            "test_ids": _sample_test_ids(sample, variants),
            "target_metadata": {
                "platform_allow_exact": any(
                    entry["target_metadata"]["platform_allow_exact"] is True
                    for entry in variants
                ),
                "platform_exclude_exact": any(
                    entry["target_metadata"]["platform_exclude_exact"] is True
                    for entry in variants
                ),
                "integration_platform_exact": any(
                    entry["target_metadata"]["integration_platform_exact"] is True
                    for entry in variants
                ),
                "build_only_values": sorted({
                    entry["metadata_effective"]["build_only"]
                    for entry in variants
                    if entry["metadata_effective"]["build_only"] is not None
                }),
            },
            "source_sha256": sample["source_sha256"],
        })
    return rows


def _infer_example_owner(library: str, sketch: str, m32_owners: dict[str, str]) -> str:
    """! @brief 설치 예제를 완료 milestone 또는 M33 후속 owner에 귀속합니다. """
    if library in M31_LIBRARY_OWNERS:
        return M31_LIBRARY_OWNERS[library]
    if library in M32_LIBRARY_OWNERS:
        return M32_LIBRARY_OWNERS[library]
    if library == "NUCODE_BLE_EATT" or library == "NUCODE_BLE_LegacySigning":
        return "M29"
    if library == "NUCODE_BLE_Security" or library == "NUCODE_BLE_DFU":
        return "M30"
    if sketch in m32_owners:
        return m32_owners[sketch]
    if sketch.startswith(M29_EXAMPLE_PREFIXES):
        return "M29"
    if sketch.startswith(M28_EXAMPLE_PREFIXES):
        return "M28"
    if not (
        library.startswith("NUCODE_BLE") or library.startswith("NUCODE_Radio")
    ):
        return "v0.5.0-core-baseline"
    return "M28-M30-baseline"


def _recipe_group(library: str, sketch: str) -> str:
    """! @brief 모든 설치 예제를 사용 목적 중심의 한 primary recipe에 배정합니다. """
    if library in {"EEPROM", "LittleFS"} or sketch == "SettingsStorage":
        return "storage"
    if library == "Servo":
        return "servo_motion"
    if library == "SPI" or sketch.startswith("SPI"):
        return "spi"
    if library == "Wire" or sketch.startswith("Wire"):
        return "i2c_wire"
    if library == "NUCODE_Peripheral_Fabric":
        return "peripheral_fabric"
    if library == "NUCODE_NU54DK":
        if sketch.startswith(("Analog", "DynamicPWM", "PWM", "Tone")):
            return "analog_pwm_tone"
        if sketch.startswith(("Blink", "Interrupt")):
            return "gpio_interrupt"
        if sketch.startswith("Serial"):
            return "serial"
        return "board_system_power"
    if library == "NUCODE_Radio_IEEE802154":
        return "radio_802154"
    if library == "NUCODE_Radio_ESB":
        return "radio_esb"
    if library == "NUCODE_Radio_Coexistence":
        return "radio_coexistence"
    if library == "NUCODE_BLE_Audio":
        return "ble_audio"
    if library == "NUCODE_BLE_ISO":
        return "ble_iso"
    if library == "NUCODE_BLE_ChannelSounding":
        return "ble_channel_sounding"
    if library == "NUCODE_BLE_DirectionFinding":
        return "ble_direction_finding"
    if library == "NUCODE_BLE_DFU":
        return "ble_dfu"
    if library == "NUCODE_BLE_Mesh":
        return "ble_mesh_models"
    if library == "NUCODE_BLE_Mesh_Management":
        return "ble_mesh_management"
    if library == "NUCODE_BLE_Mesh_Update":
        return "ble_mesh_update"
    if library in {"NUCODE_BLE_EATT", "NUCODE_BLE_LegacySigning"}:
        return "ble_gatt_extensions"
    if library == "NUCODE_BLE_Security":
        return "ble_security_profiles"
    if library == "NUCODE_BLE":
        if sketch.startswith("NUS"):
            return "ble_uart"
        if any(token in sketch for token in ("Gatt", "ReliableWrite")):
            return "ble_gatt"
        if sketch.startswith("L2cap"):
            return "ble_l2cap"
        if any(token in sketch for token in (
            "Advertising", "Scanner", "Periodic", "Pawr", "Past", "Privacy"
        )):
            return "ble_advertising_scanning"
        if any(token in sketch for token in (
            "Connection", "Power", "PathLoss", "Rssi", "Radio", "Channel",
            "FrameSpace", "Llpm", "SleepClock",
        )):
            return "ble_link_control"
        return "ble_gap_multilink"
    raise ValueError(f"example recipe group missing: {library}/{sketch}")


def _example_catalog() -> list[dict]:
    """! @brief 실제 설치 Arduino Sketch 전체를 기존 readiness와 대조합니다. """
    m31_rows: dict[str, dict] = {}
    for entry in M31["example_roles"]:
        for key in ("actual_sketch", "related_sketches"):
            value = entry.get(key)
            paths = value if isinstance(value, list) else [value]
            for path in paths:
                if path:
                    m31_rows[path.replace("\\", "/")] = entry
    m32_owners = {
        example: capability["owner_work_id"]
        for capability in M32["capabilities"]
        for example in capability["planned_examples"]
        if example != "ModernLeCapabilities"
    }
    m32_capabilities = {
        example: capability
        for capability in M32["capabilities"]
        for example in capability["planned_examples"]
        if example != "ModernLeCapabilities"
    }
    rows = []
    for library_path in sorted((CORE / "libraries").iterdir()):
        if not library_path.is_dir():
            continue
        examples_path = library_path / "examples"
        if not examples_path.is_dir():
            continue
        for sketch_path in sorted(examples_path.rglob("*.ino")):
            relative = sketch_path.relative_to(CORE).as_posix()
            sketch = sketch_path.stem
            m31_entry = m31_rows.get(relative)
            m32_entry = m32_capabilities.get(sketch)
            owner = _infer_example_owner(library_path.name, sketch, m32_owners)
            if m31_entry is not None:
                traceability = "m31_readiness_exact"
                build_status = m31_entry.get("w07_build_status") or m31_entry.get("build_status")
                runtime_status = m31_entry.get("runtime_status", "NOT_RUN")
                evidence = m31_entry.get("w07_build_evidence") or m31_entry.get("evidence")
            elif m32_entry is not None:
                traceability = "m32_readiness_exact"
                build_status = m32_entry["stages"]["arduino_build"]["status"]
                runtime_status = m32_entry["stages"]["functional_hil"]["status"]
                evidence = (
                    m32_entry["stages"]["functional_hil"].get("evidence") or
                    m32_entry["stages"]["arduino_build"].get("evidence")
                )
            else:
                traceability = (
                    "preserved_m28_m30_baseline"
                    if library_path.name.startswith(("NUCODE_BLE", "NUCODE_Radio"))
                    else "preserved_v050_core_baseline"
                )
                build_status = "PRESERVED"
                runtime_status = "PRESERVED"
                evidence = "00_Docs/TODO_v0.5.0.md"
            rows.append({
                "path": relative,
                "library": library_path.name,
                "sketch": sketch,
                "domain": (
                    "bluetooth_radio"
                    if library_path.name.startswith(("NUCODE_BLE", "NUCODE_Radio"))
                    else "core_peripheral"
                ),
                "recipe_group": _recipe_group(library_path.name, sketch),
                "presentation_tier": (
                    "start_here" if relative in START_HERE_PATHS else "reference"
                ),
                "owner_work_id": owner,
                "traceability": traceability,
                "build_status": build_status,
                "runtime_status": runtime_status,
                "evidence": evidence,
                "sha256": _sha256_bytes(sketch_path.read_bytes()),
            })
    return rows


def _deduplication_summary(scope: dict, examples: list[dict]) -> dict:
    """! @brief variant, Sketch와 사용자 기능군의 중복 제거 분모를 고정합니다. """
    hashes: dict[str, list[str]] = {}
    names: dict[str, list[str]] = {}
    for entry in examples:
        hashes.setdefault(entry["sha256"], []).append(entry["path"])
        names.setdefault(entry["sketch"], []).append(entry["path"])
    duplicate_hash_groups = [paths for paths in hashes.values() if len(paths) > 1]
    duplicate_name_groups = [paths for paths in names.values() if len(paths) > 1]
    functional_counts = {
        owner: len(groups) for owner, groups in M33_FUNCTIONAL_GROUPS.items()
    }
    return {
        "variant_to_sample": {
            "master_before": scope["master_variant_count"],
            "master_after": scope["master_sample_count"],
            "m33_before": scope["m33_variant_count"],
            "m33_after": scope["m33_sample_count"],
        },
        "installed_sketch_exact": {
            "before": len(examples),
            "unique_content_after": len(hashes),
            "exact_duplicate_group_count": len(duplicate_hash_groups),
            "files_in_exact_duplicate_groups": sum(
                len(paths) for paths in duplicate_hash_groups
            ),
            "unique_name_after": len(names),
            "duplicate_name_group_count": len(duplicate_name_groups),
            "domain_counts": {
                domain: sum(entry["domain"] == domain for entry in examples)
                for domain in ("core_peripheral", "bluetooth_radio")
            },
        },
        "planned_functional_groups": {
            "by_owner": functional_counts,
            "total": sum(functional_counts.values()),
            "groups": {
                owner: list(groups) for owner, groups in M33_FUNCTIONAL_GROUPS.items()
            },
        },
        "role_distinct_sketches_are_duplicates": False,
    }


def _example_discovery(examples: list[dict]) -> dict:
    """! @brief 전체 예제를 보존하면서 사용자 진입점을 제한한 탐색 모델을 만듭니다. """
    installed_paths = {entry["path"] for entry in examples}
    journeys = [
        {
            "id": identifier,
            "user_intent": intent,
            "tier": "start_here",
            "sketches": list(sketches),
        }
        for identifier, intent, sketches in START_HERE_JOURNEYS
    ]
    featured_paths = {
        path for journey in journeys for path in journey["sketches"]
    }
    recipe_groups = sorted({entry["recipe_group"] for entry in examples})
    return {
        "presentation_tiers": ["start_here", "functional_recipe", "reference"],
        "start_here_journeys": journeys,
        "functional_recipe_groups": recipe_groups,
        "functional_recipe_group_total": len(recipe_groups),
        "m33_planned_functional_group_total": sum(
            len(groups) for groups in M33_FUNCTIONAL_GROUPS.values()
        ),
        "reference_sketch_total": len(examples),
        "featured_sketch_total": len(featured_paths),
        "missing_featured_paths": sorted(featured_paths - installed_paths),
        "guidance_contract": {
            "applies_to": "all_installed_examples",
            "required_fields": list(REQUIRED_EXAMPLE_GUIDANCE),
            "completion_owner": "M33-W05",
            "status": "planned",
        },
        "rules": {
            "root_readme_lists_every_sketch": False,
            "full_catalog_remains_searchable": True,
            "role_distinct_sketches_remain_separate": True,
            "shared_implementation_belongs_in_library_backend": True,
        },
    }


def _service_owner(macro: str) -> tuple[str, str, str]:
    """! @brief 고정 SDK service UUID를 기존 구현·M33 계획·추가 catalog로 나눕니다. """
    if macro in M33_SERVICE_MACROS:
        return "M33-W02", "planned_m33", "표준 GATT profile 구현·예제·HIL 대상"
    if macro in M31_AUDIO_SERVICE_MACROS:
        return "M31-W03", "implemented_existing", "M31 Audio profile 완료 결과 재사용"
    if macro in M32_MESH_SERVICE_MACROS:
        return "M32-W06~W07", "implemented_existing", "M32 Mesh 완료 결과 재사용"
    if macro in BASELINE_SERVICE_MACROS:
        return "M28~M30", "implemented_existing", "기존 GAP/GATT·7개 profile 기준선"
    return "M33-W01", "catalog_only_no_fixed_sample", "고정 SDK UUID 존재; sample/API 적용성 별도 판정"


def _service_catalog(sdk_root: Path) -> tuple[list[dict], dict]:
    """! @brief Zephyr 고정 UUID header의 adopted service 전체를 수집합니다. """
    header = sdk_root / "zephyr/include/zephyr/bluetooth/uuid.h"
    payload = header.read_bytes()
    rows = []
    brief: str | None = None
    for line in payload.decode("utf-8", errors="replace").splitlines():
        brief_match = re.search(r"@brief\s+(.+?)\s+UUID value\s*$", line)
        if brief_match:
            brief = brief_match.group(1).strip()
            continue
        define_match = SERVICE_DEFINE_PATTERN.match(line)
        if define_match:
            macro, value = define_match.groups()
            owner, status, reason = _service_owner(macro)
            rows.append({
                "macro": macro,
                "uuid": value.lower(),
                "name": brief or macro,
                "owner_work_id": owner,
                "delivery_status": status,
                "decision_reason": reason,
                "source": "zephyr/include/zephyr/bluetooth/uuid.h",
            })
            brief = None
    identity = {
        "path": "zephyr/include/zephyr/bluetooth/uuid.h",
        "sha256": _sha256_bytes(payload),
        "zephyr_revision": _git_revision(sdk_root / "zephyr"),
    }
    return rows, identity


def _profile_catalog() -> list[dict]:
    """! @brief adopted profile과 비-SIG ecosystem/beacon의 제공 결정을 구분합니다. """
    definitions = (
        ("gap_gatt", "SIG", "M28~M30", "implemented_existing"),
        ("battery_device_information", "SIG", "M30", "implemented_existing"),
        ("hid_over_gatt", "SIG", "M30", "implemented_existing"),
        ("heart_rate_environmental_sensing", "SIG", "M30", "implemented_existing"),
        ("basic_audio_cap_public_broadcast", "SIG", "M31-W03", "implemented_existing"),
        ("audio_control_media_call", "SIG", "M31-W03", "implemented_existing"),
        ("tmap_gmap_hap", "SIG", "M31-W03", "implemented_existing"),
        ("mesh_and_mesh_1_1", "SIG", "M32-W06~W08", "implemented_existing"),
        ("object_transfer", "SIG", "M33-W02", "planned_m33"),
        ("alert_notification", "SIG", "M33-W02", "planned_m33"),
        ("current_time", "SIG", "M33-W02", "planned_m33"),
        ("health_thermometer", "SIG", "M33-W02", "planned_m33"),
        ("cycling_running_speed_cadence", "SIG", "M33-W02", "planned_m33"),
        ("continuous_glucose_monitoring", "SIG", "M33-W02", "planned_m33"),
        ("bond_management", "SIG", "M33-W02", "planned_m33"),
        ("ibeacon_eddystone_bthome", "non_SIG_formats", "M33-W02", "planned_m33"),
        ("ancs_ams", "Apple", "M33-W03", "planned_m33_external_interop"),
        ("fast_pair_input_locator", "Google", "M33-W03", "planned_m33_external_interop"),
        ("dtm_hci_controller_transports", "diagnostic", "M33-W04", "planned_m33"),
    )
    return [
        {
            "id": identifier,
            "authority": authority,
            "owner_work_id": owner,
            "delivery_status": status,
        }
        for identifier, authority, owner, status in definitions
    ]


def _case(identifier: str, roles: tuple[str, ...], boards: int, timeout_s: int,
          iterations: int, denominator: int, metric: str,
          negative_classes: tuple[str, ...]) -> dict:
    """! @brief 유한 시험 분모와 필수 개발 blocker를 정의합니다. """
    family = identifier.split(":", 1)[0]
    return {
        "id": identifier,
        "owner_work_id": TEST_OWNER[family],
        "roles": list(roles),
        "minimum_boards": boards,
        "timeout_s": timeout_s,
        "iterations": iterations,
        "denominator": denominator,
        "metric": metric,
        "allowed_failures": 0,
        "negative_classes": list(negative_classes),
        "recovery_timeout_s": 30,
        "maximum_diagnostic_retests": 1,
        "verification_owner": "developer",
        "verification_stage": "development",
        "development_blocker": True,
        "release_blocker": True,
        "status": "NOT_RUN",
        "source_revision": None,
        "evidence": None,
    }


def _test_families(scope: dict, service_count: int, example_count: int) -> list[dict]:
    """! @brief M33의 12개 test family와 하위 case 분모를 고정합니다. """
    definitions = {
        "M33-INV-01": (
            _case("M33-INV-01:upstream", ("host",), 0, 120, 1,
                  scope["master_sample_count"] + scope["master_variant_count"],
                  "upstream_sample_and_variant_rows",
                  ("missing", "duplicate", "revision_drift", "owner_missing")),
            _case("M33-INV-01:services", ("host",), 0, 60, 1, service_count,
                  "fixed_sdk_service_uuid_rows",
                  ("duplicate_uuid", "missing_decision", "reasonless_exclusion")),
            _case("M33-INV-01:examples", ("host",), 0, 60, 1, example_count,
                  "installed_ble_radio_sketches",
                  ("missing_path", "duplicate_path", "unassigned_owner")),
            _case("M33-INV-01:promotion", ("host",), 0, 60, 1, 8,
                  "negative_policy_classes",
                  ("source_only_pass", "not_run_pass", "hidden_implementation",
                   "reasonless_exclusion", "follow_up_blocker", "host_gate_removed",
                   "missing_evidence", "unknown_status")),
        ),
        "M33-PROFILE-01": (
            _case("M33-PROFILE-01:gatt_profiles", ("server", "client"), 2, 900, 20, 9,
                  "profile_role_pairs", ("malformed", "unauthorized", "cross_link")),
        ),
        "M33-BEACON-01": (
            _case("M33-BEACON-01:formats", ("advertiser", "observer"), 2, 300, 20, 600,
                  "decoded_advertisements", ("bad_length", "bad_version", "tamper")),
        ),
        "M33-ECOSYSTEM-01": (
            _case("M33-ECOSYSTEM-01:automatic", ("device", "scripted_peer"), 2, 900, 20, 4,
                  "ecosystem_feature_groups", ("missing_credential", "access_denied", "stale_bond")),
        ),
        "M33-DIAG-01": (
            _case("M33-DIAG-01:dtm", ("transmitter", "receiver"), 2, 600, 20, 2000,
                  "dtm_received_packets", ("bad_command", "bad_range", "timeout", "owner_conflict")),
            _case("M33-DIAG-01:hci", ("controller", "external_host"), 1, 300, 20, 5,
                  "transport_classes", ("malformed_frame", "missing_transport", "debug_uart_mix")),
        ),
        "M33-EXAMPLE-01": (
            _case("M33-EXAMPLE-01:catalog", ("build_host",), 0, 1800, 1, example_count,
                  "installed_example_catalog", ("missing_role", "missing_profile", "absolute_path")),
        ),
        "M33-REG-01": (
            _case("M33-REG-01:families", ("regression_roles",), 3, 1800, 1, 33,
                  "regression_families", ("stale_handle", "peer_loss", "cleanup")),
        ),
        "M33-RESOURCE-01": (
            _case("M33-RESOURCE-01:profiles", ("resource_roles",), 3, 1200, 1, 8,
                  "resource_profile_groups", ("over_capacity", "cross_owner", "leak")),
        ),
        "M33-INTEROP-01": (
            _case("M33-INTEROP-01:automatic", ("dut", "scripted_peer"), 2, 1200, 20, 8,
                  "automatic_peer_groups", ("unsupported_peer", "wrong_security", "state_mismatch")),
        ),
        "M33-PACKAGE-01": (
            _case("M33-PACKAGE-01:reproducibility", ("package_host",), 0, 3600, 2, 2,
                  "independent_package_builds", ("hash_mismatch", "missing_file", "version_drift")),
        ),
        "M33-INSTALL-01": (
            _case("M33-INSTALL-01:hosts", ("windows", "ubuntu", "macos"), 1, 7200, 1, 3,
                  "host_support_rows", ("wrong_arch", "permission", "probe_mismatch")),
        ),
        "M33-RELEASE-01": (
            _case("M33-RELEASE-01:public", ("release_host",), 1, 7200, 1, 3,
                  "approval_publish_public_install", ("approval_mismatch", "asset_hash", "catalog_drift")),
        ),
    }
    return [{"id": family, "cases": list(definitions[family])} for family in TEST_FAMILY_IDS]


def contract(sdk_root: Path) -> dict:
    """! @brief 고정 SDK와 현재 저장소에서 M33 초기 release readiness를 생성합니다. """
    scope = _parity_scope()
    upstream = _upstream_catalog()
    examples = _example_catalog()
    services, service_identity = _service_catalog(sdk_root)
    profiles = _profile_catalog()
    families = _test_families(scope, len(services), len(examples))
    deduplication = _deduplication_summary(scope, examples)
    discovery = _example_discovery(examples)
    document = {
        "schema_version": 1,
        "milestone": "M33",
        "phase": "implementation_in_progress",
        "milestone_status": "not_completed",
        "baseline": {
            "supported_release": "v0.5.0",
            "development_release": "v0.6.0",
            "development_branch": "Dev-0.6.0-M33",
            "target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
            "ncs_revision": LOCK["ncs"]["revision"],
            "zephyr_revision": LOCK["zephyr"]["revision"],
            "board_revision": LOCK["board"]["revision"],
            "toolchain_bundle": LOCK["windows_toolchain"]["bundle_id"],
            "parity_lock_sha256": PARITY["lock_sha256"],
        },
        "sdk_policy": {
            "active_version": "3.4.0",
            "next_version": "3.4.1",
            "transition_owner": "v0.7.0 SDK-W01~W06",
            "automatic_upgrade_allowed": False,
            "patch_note_is_failure_cause": False,
        },
        "parity_scope": scope,
        "deduplication_summary": deduplication,
        "example_discovery": discovery,
        "work_packages": [
            {
                "id": f"M33-W{index:02}",
                "title": title,
                "status": "in_progress" if index == 1 else "not_started",
                "exact_evidence": None,
            }
            for index, title in enumerate(WORK_TITLES, 1)
        ],
        "upstream_catalog": upstream,
        "installed_example_catalog": examples,
        "sig_service_source": service_identity,
        "sig_service_catalog": services,
        "profile_delivery_catalog": profiles,
        "test_families": families,
        "release_contract": {
            "publication_status": "not_published",
            "validated_support_ids": [],
            "required_stage_order": [
                "source_candidate", "nu54dk_build", "arduino_build",
                "runtime_or_documented_non_runtime", "negative", "release_review",
            ],
            "source_or_build_only_is_supported": False,
            "not_run_is_pass": False,
            "external_product_interop_required_for_release": False,
            "ubuntu_macos_physical_required_for_host_support": True,
            "owner_approval_required_for_publication": True,
        },
        "follow_up_cases": [
            {"id": "apple_google_product_interop", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "external_audio_sensor_io_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "rf_tester_precision_measurement", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "bluetooth_product_qualification", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "ubuntu_host_physical", "verification_owner": "user",
             "verification_stage": "final_release", "development_blocker": False,
             "release_blocker": True, "status": "NOT_RUN", "evidence": None},
            {"id": "macos_host_physical", "verification_owner": "user",
             "verification_stage": "final_release", "development_blocker": False,
             "release_blocker": True, "status": "NOT_RUN", "evidence": None},
        ],
        "sdk_risk_regressions": [
            {"id": "DRGN-29228", "owner_test_id": "M33-DIAG-01",
             "condition": "very_noisy_dtm_rx_assert", "cause_status": "not_reproduced_not_assumed"},
            {"id": "DRGN-29270", "owner_test_id": "M33-REG-01",
             "condition": "subrate_latency_timeout_ack_order", "cause_status": "conditional_regression"},
            {"id": "DRGN-29446_DRGN-29320", "owner_test_id": "M33-REG-01",
             "condition": "cis_acl_termination_and_bis_noise", "cause_status": "conditional_regression"},
            {"id": "DRGN-29669", "owner_test_id": "M33-REG-01",
             "condition": "cs_acl_release_radio_schedule_assert", "cause_status": "conditional_regression"},
            {"id": "MESH_LPN_MCUboot_WDT", "owner_test_id": "M33-REG-01",
             "condition": "friend_clear_and_active_watchdog_update", "cause_status": "conditional_regression"},
        ],
        "counts": {
            "work_total": 8,
            "work_completed": 0,
            "master_sample_total": scope["master_sample_count"],
            "master_variant_total": scope["master_variant_count"],
            "m33_sample_total": scope["m33_sample_count"],
            "m33_variant_total": scope["m33_variant_count"],
            "installed_example_total": len(examples),
            "installed_ble_radio_example_total": sum(
                entry["domain"] == "bluetooth_radio" for entry in examples
            ),
            "installed_core_peripheral_example_total": sum(
                entry["domain"] == "core_peripheral" for entry in examples
            ),
            "sig_service_total": len(services),
            "profile_catalog_total": len(profiles),
            "test_family_total": len(families),
            "test_case_total": sum(len(family["cases"]) for family in families),
            "test_case_passed": 0,
        },
    }
    validate(document, sdk_root)
    return document


def _validate_case(case: dict, family_id: str) -> None:
    """! @brief 시험 case의 정량·책임·증거 승격 규칙을 검사합니다. """
    if case.get("owner_work_id") != TEST_OWNER[family_id]:
        raise ValueError("test owner mapping drift")
    numeric = (
        "minimum_boards", "timeout_s", "iterations", "denominator",
        "allowed_failures", "recovery_timeout_s", "maximum_diagnostic_retests",
    )
    if any(not isinstance(case.get(name), int) or case[name] < 0 for name in numeric):
        raise ValueError("test quantitative contract missing")
    if (case["timeout_s"] < 1 or case["iterations"] < 1 or case["denominator"] < 1 or
            case["maximum_diagnostic_retests"] != 1 or not case.get("negative_classes")):
        raise ValueError("test quantitative contract invalid")
    if (case.get("verification_owner") != "developer" or
            case.get("verification_stage") != "development" or
            case.get("development_blocker") is not True or
            case.get("release_blocker") is not True):
        raise ValueError("required implementation hidden as follow-up")
    if case.get("status") not in {"PASS", "FAIL", "HOLD", "NOT_RUN"}:
        raise ValueError("test status unknown")
    if case["status"] == "PASS":
        if (not isinstance(case.get("source_revision"), str) or
                REVISION_PATTERN.fullmatch(case["source_revision"]) is None or
                not isinstance(case.get("evidence"), str) or
                not (CORE / case["evidence"]).is_file()):
            raise ValueError("PASS test without exact source/evidence")
    elif case["status"] == "NOT_RUN" and (
        case.get("source_revision") is not None or case.get("evidence") is not None
    ):
        raise ValueError("NOT_RUN test has evidence")


def validate(document: dict, sdk_root: Path | None = None) -> None:
    """! @brief 누락·중복·owner·정책·부당 지원 승격을 거부합니다. """
    if document.get("schema_version") != 1 or document.get("milestone") != "M33":
        raise ValueError("M33 schema identity mismatch")
    baseline = document.get("baseline", {})
    expected_baseline = {
        "ncs_revision": LOCK["ncs"]["revision"],
        "zephyr_revision": LOCK["zephyr"]["revision"],
        "board_revision": LOCK["board"]["revision"],
        "toolchain_bundle": LOCK["windows_toolchain"]["bundle_id"],
        "parity_lock_sha256": PARITY["lock_sha256"],
    }
    if any(baseline.get(key) != value for key, value in expected_baseline.items()):
        raise ValueError("fixed SDK/board/toolchain revision mismatch")
    if baseline.get("development_branch") != "Dev-0.6.0-M33":
        raise ValueError("M33 development branch mismatch")
    policy = document.get("sdk_policy", {})
    if (policy.get("active_version") != "3.4.0" or
            policy.get("automatic_upgrade_allowed") is not False or
            policy.get("patch_note_is_failure_cause") is not False):
        raise ValueError("NCS 3.4.0 policy drift")

    expected_scope = _parity_scope()
    if document.get("parity_scope") != expected_scope:
        raise ValueError("M33 parity owner rows drift")
    if document.get("upstream_catalog") != _upstream_catalog():
        raise ValueError("upstream catalog drift")
    upstream = document["upstream_catalog"]
    upstream_ids = [entry.get("id") for entry in upstream]
    if len(upstream_ids) != len(set(upstream_ids)) or None in upstream_ids:
        raise ValueError("duplicate upstream sample")
    for entry in upstream:
        if not entry.get("owner_work_id") or not entry.get("test_ids"):
            raise ValueError("upstream owner/test mapping missing")
        if entry.get("route") == "excluded" and not entry.get("exclusion_reason"):
            raise ValueError("reasonless exclusion")
        if SHA256_PATTERN.fullmatch(entry.get("source_sha256", "")) is None:
            raise ValueError("upstream source hash malformed")

    if document.get("installed_example_catalog") != _example_catalog():
        raise ValueError("installed example catalog drift")
    examples = document["installed_example_catalog"]
    example_paths = [entry.get("path") for entry in examples]
    if len(example_paths) != len(set(example_paths)) or None in example_paths:
        raise ValueError("duplicate installed example")
    for entry in examples:
        if not entry.get("owner_work_id") or not (CORE / entry["path"]).is_file():
            raise ValueError("installed example owner/path missing")
        if entry.get("domain") not in {"core_peripheral", "bluetooth_radio"}:
            raise ValueError("installed example domain missing")
        if not entry.get("recipe_group"):
            raise ValueError("installed example recipe group missing")
        expected_tier = "start_here" if entry["path"] in START_HERE_PATHS else "reference"
        if entry.get("presentation_tier") != expected_tier:
            raise ValueError("installed example presentation tier drift")
        if SHA256_PATTERN.fullmatch(entry.get("sha256", "")) is None:
            raise ValueError("installed example hash malformed")
    if document.get("deduplication_summary") != _deduplication_summary(
        expected_scope, examples
    ):
        raise ValueError("deduplication summary drift")
    discovery = document.get("example_discovery", {})
    if discovery != _example_discovery(examples):
        raise ValueError("example discovery model drift")
    if discovery.get("missing_featured_paths") != []:
        raise ValueError("featured example path missing")
    journey_ids = [
        entry.get("id") for entry in discovery.get("start_here_journeys", [])
    ]
    if len(journey_ids) != len(set(journey_ids)) or not journey_ids:
        raise ValueError("example journey identity invalid")
    guidance = discovery.get("guidance_contract", {})
    if (guidance.get("applies_to") != "all_installed_examples" or
            guidance.get("required_fields") != list(REQUIRED_EXAMPLE_GUIDANCE) or
            guidance.get("completion_owner") != "M33-W05" or
            guidance.get("status") != "planned"):
        raise ValueError("example guidance contract drift")

    services = document.get("sig_service_catalog", [])
    service_macros = [entry.get("macro") for entry in services]
    service_uuids = [entry.get("uuid") for entry in services]
    if (len(service_macros) != len(set(service_macros)) or
            len(service_uuids) != len(set(service_uuids)) or None in service_macros):
        raise ValueError("duplicate SIG service identity")
    for entry in services:
        if not entry.get("owner_work_id") or not entry.get("decision_reason"):
            raise ValueError("SIG service decision missing")
    service_source = document.get("sig_service_source", {})
    if (SHA256_PATTERN.fullmatch(service_source.get("sha256", "")) is None or
            service_source.get("zephyr_revision") != LOCK["zephyr"]["revision"]):
        raise ValueError("SIG service source identity mismatch")
    if sdk_root is not None:
        for module, expected in (
            ("nrf", LOCK["ncs"]["revision"]),
            ("zephyr", LOCK["zephyr"]["revision"]),
        ):
            if _git_revision(sdk_root / module) != expected:
                raise ValueError(f"{module} revision mismatch")
        expected_services, expected_identity = _service_catalog(sdk_root)
        if services != expected_services or service_source != expected_identity:
            raise ValueError("fixed SDK SIG service catalog drift")

    packages = document.get("work_packages", [])
    if len(packages) != 8 or [entry.get("id") for entry in packages] != [
        f"M33-W{index:02}" for index in range(1, 9)
    ]:
        raise ValueError("M33 work denominator drift")
    if any(entry.get("status") not in {"not_started", "in_progress", "completed"}
           for entry in packages):
        raise ValueError("M33 work status unknown")
    for entry in packages:
        if entry["status"] == "completed" and (
            not isinstance(entry.get("exact_evidence"), str) or
            not (CORE / entry["exact_evidence"]).is_file()
        ):
            raise ValueError("completed work without exact evidence")

    families = document.get("test_families", [])
    if [entry.get("id") for entry in families] != list(TEST_FAMILY_IDS):
        raise ValueError("M33 test family denominator drift")
    for family in families:
        if not family.get("cases"):
            raise ValueError("M33 test family has no case")
        for case in family["cases"]:
            _validate_case(case, family["id"])

    release = document.get("release_contract", {})
    if (release.get("publication_status") != "not_published" or
            release.get("validated_support_ids") != [] or
            release.get("source_or_build_only_is_supported") is not False or
            release.get("not_run_is_pass") is not False or
            release.get("ubuntu_macos_physical_required_for_host_support") is not True or
            release.get("owner_approval_required_for_publication") is not True):
        raise ValueError("unverified support or publication promotion")

    for entry in document.get("follow_up_cases", []):
        if (entry.get("verification_owner") != "user" or
                entry.get("development_blocker") is not False or
                entry.get("status") not in {"PASS", "FAIL", "HOLD", "NOT_RUN"}):
            raise ValueError("follow-up policy corruption")
        if entry["verification_stage"] == "user_follow_up" and entry["release_blocker"]:
            raise ValueError("user follow-up became release blocker")
        if entry["verification_stage"] == "final_release" and not entry["release_blocker"]:
            raise ValueError("final Host gate removed")
        if entry["status"] == "PASS" and not entry.get("evidence"):
            raise ValueError("follow-up PASS without evidence")

    risks = document.get("sdk_risk_regressions", [])
    if not risks or any(
        entry.get("owner_test_id") not in TEST_FAMILY_IDS or
        entry.get("cause_status") not in {
            "not_reproduced_not_assumed", "conditional_regression"
        }
        for entry in risks
    ):
        raise ValueError("SDK risk regression mapping missing")

    counts = document.get("counts", {})
    expected_counts = {
        "work_total": len(packages),
        "work_completed": sum(entry["status"] == "completed" for entry in packages),
        "master_sample_total": expected_scope["master_sample_count"],
        "master_variant_total": expected_scope["master_variant_count"],
        "m33_sample_total": expected_scope["m33_sample_count"],
        "m33_variant_total": expected_scope["m33_variant_count"],
        "installed_example_total": len(examples),
        "installed_ble_radio_example_total": sum(
            entry["domain"] == "bluetooth_radio" for entry in examples
        ),
        "installed_core_peripheral_example_total": sum(
            entry["domain"] == "core_peripheral" for entry in examples
        ),
        "sig_service_total": len(services),
        "profile_catalog_total": len(document.get("profile_delivery_catalog", [])),
        "test_family_total": len(families),
        "test_case_total": sum(len(family["cases"]) for family in families),
        "test_case_passed": sum(
            case["status"] == "PASS" for family in families for case in family["cases"]
        ),
    }
    if counts != expected_counts:
        raise ValueError("M33 count summary drift")
    if document.get("milestone_status") == "completed" and counts["work_completed"] != 8:
        raise ValueError("M33 completed before 8/8")


def main() -> int:
    """! @brief readiness 생성 또는 현행 원장·고정 SDK drift 검사를 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    sdk_root = arguments.sdk_root.resolve()
    if arguments.check:
        validate(json.loads(TARGET_PATH.read_text(encoding="utf-8")), sdk_root)
    else:
        TARGET_PATH.write_text(
            json.dumps(contract(sdk_root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("M33_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"M33_CONTRACT_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
