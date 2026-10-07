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

try:
    from tools.bluetooth import m33_regression
except ModuleNotFoundError:
    import m33_regression


CORE = Path(__file__).resolve().parents[2]
LOCK_PATH = CORE / "tools/ci/ncs-3.4.0.lock.json"
PARITY_PATH = CORE / "variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json"
TARGET_PATH = CORE / "variants/nu54dk/m33-release-readiness.json"
EXAMPLE_METADATA_PATH = CORE / "libraries/example-metadata.json"
M31_PATH = CORE / "variants/nu54dk/m31-ble-readiness.json"
M32_PATH = CORE / "variants/nu54dk/m32-ble-readiness.json"
CONTRACT_EVIDENCE = (
    "00_Docs/01_아두이노 코어 설계/23_M33_전체_예제_원장과_릴리스_계약.md"
)
W01_EVIDENCE = "00_Docs/04_검증 기록/296_M33_W01_전체_예제_원장과_릴리스_계약.md"
W01_SOURCE_REVISION = "a3585ffbd168d69726a42f785c5e6888f172899f"
W02_EVIDENCE = "00_Docs/04_검증 기록/298_M33_W02_표준_GATT_Beacon_완료.md"
W02_SOURCE_REVISION = "4ebd49521d4a6578beac91ebddbd1bf39d679db4"
W03_EVIDENCE = "00_Docs/04_검증 기록/299_M33_W03_외부_ecosystem과_companion_완료.md"
W03_SOURCE_REVISION = "17182660f8c1c1f4a9f6773b13fcfa453f65e1fc"
W04_EVIDENCE = "00_Docs/04_검증 기록/300_M33_W04_DTM_HCI_진단_template_완료.md"
W04_SOURCE_REVISION = "e3a663d629bcc22fb3222b99c456fda6c8e2c312"
W05_EVIDENCE = "00_Docs/04_검증 기록/301_M33_W05_전체_예제와_설치_경로_완료.md"
W05_SOURCE_REVISION = "5f9b2257e2d9630fc919d9cd6508f918d93207cc"
W05_INSTALLED_EVIDENCE_PATH = CORE / (
    "00_Docs/04_검증 기록/evidence/m33-w05-exact-5f9b2257/"
    "installed-examples.json"
)
LOCK = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
PARITY = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
M31 = json.loads(M31_PATH.read_text(encoding="utf-8"))
M32 = json.loads(M32_PATH.read_text(encoding="utf-8"))
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
QUALIFICATION_OFFICIAL_REFERENCE = (
    "https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54l15/page/comp/"
    "nrf54l15/nrf54l15_ble_qdid_qual_matrix.html"
)
QUALIFICATION_IDENTIFIERS = {
    "host": "PLANNED_NO_DN",
    "controller": "PLANNED_NO_DN",
    "mesh": "NOT_LISTED_NO_DN",
}
SDK_RISK_OWNERS = {
    "DRGN-29228": "M33-DIAG-01",
}
W06_EVIDENCE_ROOT = Path("00_Docs/04_검증 기록/evidence")
W06_COMPLETION_ROOT = Path("00_Docs/04_검증 기록")
W06_COMPLETION_NAME = re.compile(r"[0-9]{3}_M33_W06_[^/\\]*완료\.md\Z")
W06_READINESS_PATH = Path("variants/nu54dk/m33-release-readiness.json")
W06_CLOSURE_DOCUMENTS = {
    Path("00_Docs/TODO_M33.md"),
    Path("00_Docs/TODO_v0.6.0.md"),
    Path("00_Docs/M33_HANDOFF.md"),
    Path("00_Docs/HANDOFF.md"),
    Path("00_Docs/04_검증 기록/README.md"),
    Path("00_Docs/04_검증 기록/303_M33_W06_재실행_최소화와_checkpoint_개선_계획.md"),
    Path("00_Docs/01_아두이노 코어 설계/06_NCS_3.4.0_기능과_예제_지원_매트릭스.md"),
    Path("00_Docs/00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md"),
    Path("00_Docs/00_사전 리서치/04_M33_Bluetooth_qualification_적용성.md"),
}
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
    "M33-W05": ("M33-EXAMPLE-01",),
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
M33_BEACON_EXAMPLES = frozenset({"BeaconAdvertiser", "BeaconObserver"})
M33_PROFILE_EXAMPLES = frozenset({
    "AlertSensor", "BondManagement", "GlucoseSensor", "ObjectClient",
    "ObjectServer", "StandardCollector", "StandardSensor",
})
M33_COMPANION_EXAMPLES = frozenset({"AppleMediaClient", "AppleNotificationClient"})
M33_W05_FABRIC_EXAMPLES = frozenset({
    "AdcContinuousDma", "PwmSequencePlayback", "ResourceConflictDemo",
    "SpiAsyncLoopback", "TwisTargetDoubleBuffer", "UarteAsyncEcho",
})
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


def _sha256_text(path: Path) -> str:
    """! @brief checkout의 CRLF 정책과 무관한 UTF-8 source hash를 계산합니다. """

    normalized = (
        path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    )
    return _sha256_bytes(normalized.encode("utf-8"))


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


def _sample_requirements(sample: dict, test_ids: list[str]) -> dict:
    """! @brief sample의 실행 역할·보드·peer 요구와 위임 원본을 명시합니다. """
    owner = sample["owner_work_id"]
    path = sample["upstream_path"]
    if sample["route"] == "excluded":
        return {
            "resolution": "not_applicable_excluded",
            "roles": [],
            "minimum_boards": 0,
            "external_parts": [],
            "peer_policy": "not_applicable",
            "source": PARITY_PATH.relative_to(CORE).as_posix(),
        }
    if owner.startswith("M31-"):
        return {
            "resolution": "delegated_existing_owner",
            "roles": [],
            "minimum_boards": None,
            "external_parts": [],
            "peer_policy": "see_owner_contract",
            "source": M31_PATH.relative_to(CORE).as_posix(),
        }
    if owner.startswith("M32-"):
        return {
            "resolution": "delegated_existing_owner",
            "roles": [],
            "minimum_boards": None,
            "external_parts": [],
            "peer_policy": "see_owner_contract",
            "source": M32_PATH.relative_to(CORE).as_posix(),
        }
    if owner == "M33-W02":
        beacon = "M33-BEACON-01" in test_ids
        return {
            "resolution": "implemented_m33_family",
            "roles": ["advertiser", "observer"] if beacon else ["server", "client"],
            "minimum_boards": 2,
            "external_parts": [],
            "peer_policy": "second_nu54dk",
            "source": TARGET_PATH.relative_to(CORE).as_posix(),
        }
    if owner == "M33-W03":
        return {
            "resolution": "implemented_m33_family",
            "roles": ["device", "scripted_peer"],
            "minimum_boards": 2,
            "external_parts": ["optional_apple_or_google_product"],
            "peer_policy": "automatic_required_product_physical_user_follow_up",
            "source": TARGET_PATH.relative_to(CORE).as_posix(),
        }
    if owner == "M33-W04":
        direct_test_mode = path.endswith("/direct_test_mode")
        return {
            "resolution": "implemented_m33_family",
            "roles": (
                ["transmitter", "receiver"]
                if direct_test_mode else ["controller", "external_host"]
            ),
            "minimum_boards": 2 if direct_test_mode else 1,
            "external_parts": ["optional_rf_tester"] if direct_test_mode else [],
            "peer_policy": "nu54dk_or_external_host_by_transport",
            "source": TARGET_PATH.relative_to(CORE).as_posix(),
        }
    return {
        "resolution": "catalog_decision",
        "roles": ["host_inventory"],
        "minimum_boards": 0,
        "external_parts": [],
        "peer_policy": "none",
        "source": CONTRACT_EVIDENCE,
    }


def _upstream_catalog() -> list[dict]:
    """! @brief 190개 upstream sample을 owner·route·test와 한 행씩 연결합니다. """
    variants_by_parent: dict[str, list[dict]] = {}
    for variant in PARITY["variants"]:
        variants_by_parent.setdefault(variant["parent_sample_id"], []).append(variant)
    rows = []
    for sample in PARITY["samples"]:
        variants = variants_by_parent.get(sample["id"], [])
        test_ids = _sample_test_ids(sample, variants)
        if sample["exclusion_reason"]:
            delivery_state = "excluded_with_reason"
        elif sample["owner_work_id"].startswith(("M31-", "M32-")):
            delivery_state = "existing_owner_result"
        elif sample["owner_work_id"] in {"M33-W02", "M33-W03"}:
            delivery_state = "implemented_m33"
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
            "test_ids": test_ids,
            "execution_requirements": _sample_requirements(sample, test_ids),
            "arduino_delivery": {
                "route": sample["route"],
                "state": delivery_state,
                "owner_work_id": sample["owner_work_id"],
                "source": (
                    M31_PATH.relative_to(CORE).as_posix()
                    if sample["owner_work_id"].startswith("M31-")
                    else M32_PATH.relative_to(CORE).as_posix()
                    if sample["owner_work_id"].startswith("M32-")
                    else TARGET_PATH.relative_to(CORE).as_posix()
                ),
            },
            "result_stages": [
                "native_build", "nu54dk_build", "arduino_build", "runtime",
                "negative", "interoperability",
            ],
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
    if library == "NUCODE_BLE" and sketch in M33_BEACON_EXAMPLES:
        return "M33-W02"
    if library == "NUCODE_BLE_Profiles" and sketch in M33_PROFILE_EXAMPLES:
        return "M33-W02"
    if library == "NUCODE_BLE_Companion" and sketch in M33_COMPANION_EXAMPLES:
        return "M33-W03"
    if library == "NUCODE_Peripheral_Fabric" and sketch in M33_W05_FABRIC_EXAMPLES:
        return "M33-W05"
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
    if library in {"NUCODE_BLE_Security", "NUCODE_BLE_Profiles", "NUCODE_BLE_Companion"}:
        return "ble_profiles_and_ecosystems"
    if library == "NUCODE_BLE":
        if sketch in M33_BEACON_EXAMPLES:
            return "ble_beacons"
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
            companion_files = sorted(
                path.relative_to(CORE).as_posix()
                for path in sketch_path.parent.rglob("*")
                if path.is_file() and path != sketch_path
            )
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
            elif owner == "M33-W02" and sketch in M33_BEACON_EXAMPLES | M33_PROFILE_EXAMPLES:
                traceability = "m33_w02_exact"
                build_status = "PASS"
                runtime_status = "PASS"
                evidence = W02_EVIDENCE
            elif owner == "M33-W03" and sketch in M33_COMPANION_EXAMPLES:
                traceability = "m33_w03_exact"
                build_status = "PASS"
                runtime_status = "PASS"
                evidence = W03_EVIDENCE
            elif owner == "M33-W05":
                traceability = "m33_w05_exact"
                build_status = "PASS"
                runtime_status = "NOT_RUN"
                evidence = W05_EVIDENCE
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
                "companion_files": companion_files,
                "stages": {
                    "source_candidate": {
                        "status": "PRESENT",
                        "evidence": relative,
                    },
                    "native_build": {
                        "status": "NOT_APPLICABLE",
                        "evidence": None,
                    },
                    "arduino_build": {
                        "status": build_status,
                        "evidence": evidence if build_status == "PASS" else None,
                    },
                    "functional_hil": {
                        "status": runtime_status,
                        "evidence": evidence if runtime_status == "PASS" else None,
                    },
                    "external_peer_interop": {
                        "status": "NOT_RUN",
                        "evidence": None,
                    },
                },
                "sha256": _sha256_text(sketch_path),
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
    metadata = json.loads(EXAMPLE_METADATA_PATH.read_text(encoding="utf-8"))
    metadata_records = metadata.get("examples", {})
    example_identities = {f"{entry['library']}/{entry['sketch']}" for entry in examples}
    if set(metadata_records) != example_identities:
        raise ValueError("example guidance identity drift")
    role_slot_total = sum(len(metadata_records[identity]["roles"]) for identity in example_identities)
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
            "status": "completed",
        },
        "runtime_role_contract": {
            "example_total": len(examples),
            "documented_role_slot_total": role_slot_total,
            "procedure_status": "documented_not_physical_pass",
            "physical_result_source": "installed_example_catalog.stages.functional_hil",
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
        return "M33-W02", "implemented_m33", "표준 GATT profile 구현·예제·HIL 완료"
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
        ("object_transfer", "SIG", "M33-W02", "implemented_m33"),
        ("alert_notification", "SIG", "M33-W02", "implemented_m33"),
        ("current_time", "SIG", "M33-W02", "implemented_m33"),
        ("health_thermometer", "SIG", "M33-W02", "implemented_m33"),
        ("cycling_running_speed_cadence", "SIG", "M33-W02", "implemented_m33"),
        ("continuous_glucose_monitoring", "SIG", "M33-W02", "implemented_m33"),
        ("bond_management", "SIG", "M33-W02", "implemented_m33"),
        ("ibeacon_eddystone_bthome", "non_SIG_formats", "M33-W02",
         "implemented_m33"),
        ("ancs_ams", "Apple", "M33-W03", "implemented_m33_external_interop_not_run"),
        ("fast_pair_input_locator", "Google", "M33-W03", "implemented_m33_external_interop_not_run"),
        ("dtm_hci_controller_transports", "diagnostic", "M33-W04",
         "implemented_m33_external_runtime_not_run"),
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
    row = {
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
    if family == "M33-INV-01":
        row.update({
            "status": "PASS",
            "source_revision": W01_SOURCE_REVISION,
            "evidence": W01_EVIDENCE,
        })
    if family in {"M33-PROFILE-01", "M33-BEACON-01"}:
        row.update({
            "status": "PASS",
            "source_revision": W02_SOURCE_REVISION,
            "evidence": W02_EVIDENCE,
        })
    if family == "M33-ECOSYSTEM-01":
        row.update({
            "status": "PASS",
            "source_revision": W03_SOURCE_REVISION,
            "evidence": W03_EVIDENCE,
        })
    if family == "M33-DIAG-01":
        row.update({
            "status": "PASS",
            "source_revision": W04_SOURCE_REVISION,
            "evidence": W04_EVIDENCE,
        })
    if family == "M33-EXAMPLE-01":
        row.update({
            "status": "PASS",
            "source_revision": W05_SOURCE_REVISION,
            "evidence": W05_EVIDENCE,
        })
    return row


def _test_families(
    scope: dict, service_count: int, example_count: int, role_slot_count: int
) -> list[dict]:
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
            _case("M33-INV-01:examples", ("host",), 0, 60, 1, 187,
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
            _case("M33-BEACON-01:codec_host", ("host",), 0, 60, 1, 4,
                  "codec_runtime_scenarios",
                  ("bad_length", "bad_version", "wrong_identifier",
                   "reserved_bits", "invalid_range")),
            _case("M33-BEACON-01:formats", ("advertiser", "observer"), 2, 300, 20, 600,
                  "decoded_advertisements", ("bad_length", "bad_version", "tamper")),
        ),
        "M33-ECOSYSTEM-01": (
            _case("M33-ECOSYSTEM-01:fast_pair_input", ("build_host",), 0, 1800, 1, 1,
                  "native_template_build", ("missing_credential", "placeholder", "wrong_use_case")),
            _case("M33-ECOSYSTEM-01:fast_pair_locator", ("build_host",), 0, 1800, 1, 1,
                  "native_template_build", ("missing_credential", "placeholder", "wrong_use_case")),
            _case("M33-ECOSYSTEM-01:ancs", ("client", "scripted_peer"), 2, 900, 2, 4,
                  "fresh_reconnect_and_malformed_sessions", ("access_denied", "stale_nonce", "malformed")),
            _case("M33-ECOSYSTEM-01:ams", ("client", "scripted_peer"), 2, 900, 2, 4,
                  "reconnect_control_and_malformed_sessions", ("access_denied", "stale_nonce", "malformed")),
            _case("M33-ECOSYSTEM-01:access", ("client", "scripted_peer"), 2, 180, 1, 1,
                  "explicit_pairing_rejection", ("remote_rejection", "unexpected_security", "unexpected_data")),
            _case("M33-ECOSYSTEM-01:templates", ("build_host",), 0, 1800, 1, 2,
                  "enocean_and_mds_native_templates", ("credential_injection", "unsupported_board", "automatic_flash")),
            _case("M33-ECOSYSTEM-01:os_ux", ("documentation_host",), 0, 60, 1, 5,
                  "peer_os_support_rows", ("not_run_promoted", "unsupported_promoted", "missing_manual_step")),
        ),
        "M33-DIAG-01": (
            _case("M33-DIAG-01:dtm_twowire", ("transmitter", "receiver"), 2,
                  600, 1, 12, "role_phy_channel_cases",
                  ("bad_command", "bad_range", "timeout", "owner_conflict")),
            _case("M33-DIAG-01:dtm_h4", ("transmitter", "receiver"), 2,
                  600, 1, 12, "role_phy_channel_cases",
                  ("bad_command", "bad_range", "timeout", "owner_conflict")),
            _case("M33-DIAG-01:hci_automatic", ("build_host", "parser_host"), 0,
                  1800, 1, 5, "transport_build_and_parser_classes",
                  ("malformed_frame", "missing_transport", "debug_uart_mix",
                   "owner_conflict", "stale_opcode", "timeout")),
        ),
        "M33-EXAMPLE-01": (
            _case("M33-EXAMPLE-01:catalog", ("build_host",), 0, 1800, 1, example_count,
                  "metadata_and_generated_guidance_rows",
                  ("missing_role", "missing_profile", "missing_guidance", "absolute_path")),
            _case("M33-EXAMPLE-01:discovery", ("build_host",), 0, 600, 1, example_count,
                  "arduino_cli_discovered_examples",
                  ("missing_library", "missing_example", "duplicate_identity")),
            _case("M33-EXAMPLE-01:compile", ("build_host",), 0, 3600, 1, example_count,
                  "clean_installed_example_builds",
                  ("wrong_profile", "missing_sidecar", "source_tree_reference")),
            _case("M33-EXAMPLE-01:negative_profiles", ("build_host",), 0, 1200, 1, 9,
                  "expected_profile_rejections",
                  ("unexpected_compile", "missing_error_marker", "timeout")),
            _case("M33-EXAMPLE-01:runtime_roles", ("documentation_host",), 0, 600, 1,
                  role_slot_count, "documented_runtime_role_slots_not_physical_pass",
                  ("missing_role", "missing_termination", "not_run_promoted")),
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


def _sdk_risk_catalog() -> list[dict]:
    """! @brief 회귀 도구의 SDK 위험 분모를 readiness 원장에 그대로 투영합니다. """
    return [
        {
            "id": identifier,
            "owner_test_id": SDK_RISK_OWNERS.get(identifier, "M33-REG-01"),
            "condition": plan["condition"],
            "cause_status": (
                "not_reproduced_not_assumed" if identifier == "DRGN-29228" else
                "conditional_regression"
            ),
        }
        for identifier, plan in m33_regression.SDK_RISK_CAMPAIGNS.items()
    ]


def _work_status(index: int) -> str:
    """! @brief M33 작업 번호별 현재 진행 상태를 반환합니다. """

    if index <= 5:
        return "completed"
    if index == 6:
        return "in_progress"
    return "not_started"


def contract(sdk_root: Path) -> dict:
    """! @brief 고정 SDK와 현재 저장소에서 M33 초기 release readiness를 생성합니다. """
    scope = _parity_scope()
    upstream = _upstream_catalog()
    examples = _example_catalog()
    services, service_identity = _service_catalog(sdk_root)
    profiles = _profile_catalog()
    discovery = _example_discovery(examples)
    role_slot_count = discovery["runtime_role_contract"][
        "documented_role_slot_total"
    ]
    families = _test_families(scope, len(services), len(examples), role_slot_count)
    deduplication = _deduplication_summary(scope, examples)
    work_packages = [
        {
            "id": f"M33-W{index:02}",
            "title": title,
            "status": _work_status(index),
            "exact_evidence": (
                W01_EVIDENCE if index == 1 else
                W02_EVIDENCE if index == 2 else
                W03_EVIDENCE if index == 3 else
                W04_EVIDENCE if index == 4 else
                W05_EVIDENCE if index == 5 else
                None
            ),
        }
        for index, title in enumerate(WORK_TITLES, 1)
    ]
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
        "work_packages": work_packages,
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
            {"id": "apple_ancs_ams_product_interop", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "google_fast_pair_input_product_interop", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "google_find_hub_locator_product_interop", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "enocean_product_interop", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "memfault_gateway_cloud_interop", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "external_audio_sensor_io_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "hci_uart_external_host_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "hci_async_uart_external_host_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "hci_threewire_external_host_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "hci_lpuart_external_host_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "hci_spi_external_host_physical", "verification_owner": "user",
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
        "sdk_risk_regressions": _sdk_risk_catalog(),
        "counts": {
            "work_total": 8,
            "work_completed": sum(
                entry["status"] == "completed" for entry in work_packages
            ),
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
            "test_case_passed": sum(
                case["status"] == "PASS"
                for family in families for case in family["cases"]
            ),
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


def _read_w05_installed_evidence(path: Path) -> dict:
    """! @brief 중복 key 없이 W05 설치 예제 evidence를 읽습니다. """

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        """! @brief evidence JSON의 중복 key를 즉시 거부합니다. """

        document: dict = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"W05 evidence duplicate JSON key: {key}")
            document[key] = value
        return document

    if not path.is_file():
        raise ValueError("W05 installed example evidence가 없습니다")
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("W05 installed example evidence를 읽지 못했습니다") from error
    if not isinstance(document, dict):
        raise ValueError("W05 installed example evidence root가 object가 아닙니다")
    return document


def _validate_w05_public_values(value: object, location: str = "$") -> None:
    """! @brief 공개 W05 evidence의 절대 경로·UID·secret 노출을 거부합니다. """

    sensitive_keys = {
        "uid", "raw_uid", "device_uid", "hardware_uid", "serial_number",
        "secret", "password", "passwd", "token", "access_token",
        "refresh_token", "api_key", "private_key", "credential", "credentials",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            secret_key = re.search(
                r"(?:^|_)(?:secret|password|passwd|token|api_key|private_key|"
                r"credential)(?:_|$)",
                normalized,
            )
            raw_uid_key = re.search(
                r"(?:^|_)(?:raw_uid|raw_device_uid|device_uid|hardware_uid|uid|"
                r"serial_number)(?:_|$)",
                normalized,
            )
            if (normalized in sensitive_keys or secret_key is not None or
                    raw_uid_key is not None and not normalized.endswith("_sha256")):
                raise ValueError(f"W05 evidence sensitive field: {location}.{key}")
            _validate_w05_public_values(child, f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_w05_public_values(child, f"{location}[{index}]")
        return
    if not isinstance(value, str):
        return
    path_patterns = (
        r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/]",
        r"(?:^|[\s\"'`])\\\\[^\\/\s]+[\\/]",
        r"(?i)(?:^|[\s\"'`])/(?:Users|home|tmp|var/tmp|private|Volumes|mnt|opt)/",
    )
    secret_patterns = (
        r"(?i)-----BEGIN [^-]*PRIVATE KEY-----",
        r"(?i)\b(?:password|passwd|secret|token|api[_ -]?key)\s*[:=]\s*\S+",
        r"(?i)\bauthorization\s*[:=]\s*(?:bearer\s+)?\S+",
        r"(?i)\b(?:raw[_ -]?uid|device[_ -]?uid|hardware[_ -]?uid|uid)"
        r"\s*[:=]\s*[0-9a-f-]{8,}",
    )
    if any(re.search(pattern, value) is not None for pattern in path_patterns):
        raise ValueError(f"W05 evidence absolute path exposure: {location}")
    if any(re.search(pattern, value) is not None for pattern in secret_patterns):
        raise ValueError(f"W05 evidence credential or raw UID exposure: {location}")


def _validate_w05_installed_evidence(path: Path) -> dict:
    """! @brief W05 204/204·negative 9/9 evidence를 fail-closed로 검증합니다. """

    document = _read_w05_installed_evidence(path)
    _validate_w05_public_values(document)
    if (document.get("schema_version") != 1 or
            document.get("work_id") != "M33-W05" or
            document.get("test_id") != "M33-EXAMPLE-01" or
            document.get("status") != "PASS" or
            not isinstance(document.get("finished_utc"), str) or
            not document["finished_utc"].strip() or
            not isinstance(document.get("summary"), dict)):
        raise ValueError("W05 evidence top-level completion mismatch")

    revision_fields = (
        "source_revision", "installed_source_revision",
        "source_revision_after", "installed_revision_after",
    )
    if any(document.get(field) != W05_SOURCE_REVISION for field in revision_fields):
        raise ValueError("W05 evidence exact revision mismatch")
    if (document.get("source_clean_before") is not True or
            document.get("source_clean_after") is not True or
            document.get("installed_clean_after") is not True or
            document.get("installed_tree_unchanged") is not True):
        raise ValueError("W05 evidence clean or immutable tree mismatch")

    if document.get("denominators") != {
        "catalog": 204,
        "discovered": 204,
        "compiled": 204,
        "negative_profiles": 9,
    }:
        raise ValueError("W05 evidence denominator mismatch")
    isolation = document.get("isolation", {})
    if (not isinstance(isolation, dict) or
            isolation.get("source_install_separate") is not True or
            isolation.get("fresh_build_root") is not True):
        raise ValueError("W05 evidence isolation mismatch")

    libraries = document.get("libraries")
    if not isinstance(libraries, list) or len(libraries) != 24:
        raise ValueError("W05 evidence library denominator mismatch")
    library_directories: set[str] = set()
    library_names: set[str] = set()
    library_examples = 0
    for row in libraries:
        if not isinstance(row, dict):
            raise ValueError("W05 evidence library row mismatch")
        directory = row.get("directory")
        name = row.get("name")
        count = row.get("example_count")
        if (not isinstance(directory, str) or not directory or
                not isinstance(name, str) or not name or
                not isinstance(count, int) or isinstance(count, bool) or count < 0 or
                directory in library_directories or name in library_names):
            raise ValueError("W05 evidence library identity mismatch")
        library_directories.add(directory)
        library_names.add(name)
        library_examples += count
    if library_examples != 204:
        raise ValueError("W05 evidence library example sum mismatch")

    profile_counts = document.get("profile_counts")
    if (not isinstance(profile_counts, dict) or not profile_counts or
            any(not isinstance(profile, str) or not profile or
                not isinstance(count, int) or isinstance(count, bool) or count < 0
                for profile, count in profile_counts.items()) or
            sum(profile_counts.values()) != 204):
        raise ValueError("W05 evidence profile sum mismatch")

    builds = document.get("builds")
    if not isinstance(builds, list) or len(builds) != 204:
        raise ValueError("W05 evidence build denominator mismatch")
    builds_by_identity: dict[str, dict] = {}
    for row in builds:
        if not isinstance(row, dict):
            raise ValueError("W05 evidence build row mismatch")
        identity = row.get("identity")
        exit_code = row.get("exit_code")
        if (not isinstance(identity, str) or not identity or
                identity in builds_by_identity or row.get("status") != "PASS" or
                row.get("timed_out") is not False or
                not isinstance(exit_code, int) or isinstance(exit_code, bool) or
                exit_code != 0):
            raise ValueError("W05 evidence final build mismatch")
        builds_by_identity[identity] = row

    negatives = document.get("negative_profiles")
    if not isinstance(negatives, list) or len(negatives) != 9:
        raise ValueError("W05 evidence negative denominator mismatch")
    negative_ids: set[str] = set()
    negative_identities: set[str] = set()
    for row in negatives:
        if not isinstance(row, dict):
            raise ValueError("W05 evidence negative row mismatch")
        identifier = row.get("id")
        identity = row.get("identity")
        exit_code = row.get("exit_code")
        if (not isinstance(identifier, str) or not identifier or
                not isinstance(identity, str) or not identity or
                identifier in negative_ids or identity in negative_identities or
                row.get("status") != "PASS" or row.get("timed_out") is not False or
                not isinstance(exit_code, int) or isinstance(exit_code, bool) or
                exit_code == 0 or
                not isinstance(row.get("unexpected_artifact_count"), int) or
                isinstance(row.get("unexpected_artifact_count"), bool) or
                row.get("unexpected_artifact_count") != 0):
            raise ValueError("W05 evidence negative result mismatch")
        negative_ids.add(identifier)
        negative_identities.add(identity)

    retest_policy = document.get("diagnostic_retest_policy")
    if (not isinstance(retest_policy, dict) or
            not isinstance(retest_policy.get("maximum_per_failed_build"), int) or
            isinstance(retest_policy.get("maximum_per_failed_build"), bool) or
            retest_policy.get("maximum_per_failed_build") != 1 or
            retest_policy.get("fresh_build_directory") is not True or
            retest_policy.get("serial") is not True or
            retest_policy.get("initial_failure_is_preserved") is not True):
        raise ValueError("W05 evidence diagnostic retest policy mismatch")
    retests = document.get("diagnostic_retests")
    if not isinstance(retests, list):
        raise ValueError("W05 evidence diagnostic retest rows missing")
    retested_identities: set[str] = set()
    for row in retests:
        if not isinstance(row, dict):
            raise ValueError("W05 evidence diagnostic retest row mismatch")
        identity = row.get("identity")
        initial = row.get("initial")
        retry = row.get("retry")
        if (not isinstance(identity, str) or identity in retested_identities or
                row.get("reason") != "initial_compile_failure" or
                row.get("attempt") != 2 or not isinstance(initial, dict) or
                initial.get("identity") != identity or initial.get("status") != "FAIL" or
                not isinstance(retry, dict) or retry.get("identity") != identity or
                retry != builds_by_identity.get(identity)):
            raise ValueError("W05 evidence diagnostic retest mismatch")
        retested_identities.add(identity)

    summary = document["summary"]
    expected_summary = {
        "catalog": 204,
        "discovered": 204,
        "compiled_pass": 204,
        "compiled_fail": 0,
        "initial_compile_fail": len(retests),
        "diagnostic_retest_pass": len(retests),
        "diagnostic_retest_fail": 0,
        "negative_pass": 9,
        "negative_fail": 0,
    }
    if any(not isinstance(summary.get(key), int) or
           isinstance(summary.get(key), bool) or summary.get(key) != value
           for key, value in expected_summary.items()):
        raise ValueError("W05 evidence summary mismatch")
    return document


def _validate_w05_completion(package: dict, cases: list[dict]) -> None:
    """! @brief W05 완료와 다섯 PASS를 설치 evidence payload에 결합합니다. """

    package_completed = package.get("status") == "completed"
    any_pass = any(case.get("status") == "PASS" for case in cases)
    if not package_completed and not any_pass:
        return
    if (not package_completed or package.get("exact_evidence") != W05_EVIDENCE or
            len(cases) != 5 or any(case.get("status") != "PASS" for case in cases) or
            any(case.get("source_revision") != W05_SOURCE_REVISION or
                case.get("evidence") != W05_EVIDENCE for case in cases)):
        raise ValueError("W05 completion and exact PASS evidence must be atomic")
    _validate_w05_installed_evidence(W05_INSTALLED_EVIDENCE_PATH)


def _validate_w06_qualification(closure: dict) -> None:
    """! @brief NCS 3.4.0 component 근거를 제품 자격으로 승격하지 못하게 고정합니다. """
    rows = closure.get("qualification", [])
    if (not isinstance(rows, list) or len(rows) != len(QUALIFICATION_IDENTIFIERS) or
            {row.get("component") for row in rows if isinstance(row, dict)} !=
            set(QUALIFICATION_IDENTIFIERS)):
        raise ValueError("W06 qualification denominator mismatch")
    required = {
        "component", "applicability", "component_status", "component_version",
        "design_identifier", "product_status", "example_status_implied",
        "official_reference", "remaining_product_procedure",
    }
    for row in rows:
        component = row["component"]
        if (set(row) != required or row.get("applicability") != "applicable" or
                row.get("component_status") != "EVIDENCE_RECORDED" or
                row.get("component_version") != "NCS 3.4.0 LTS" or
                row.get("design_identifier") != QUALIFICATION_IDENTIFIERS[component] or
                row.get("product_status") != "NOT_ASSESSED" or
                row.get("example_status_implied") is not False or
                row.get("official_reference") != QUALIFICATION_OFFICIAL_REFERENCE or
                not isinstance(row.get("remaining_product_procedure"), str) or
                not row["remaining_product_procedure"]):
            raise ValueError("W06 qualification evidence mismatch")


def _git_text(repository: Path, *arguments: str) -> str:
    """! @brief closure bridge 검증용 Git 출력을 실패 시 승격해 반환합니다. """

    try:
        return subprocess.check_output(
            [
                "git", "-C", str(repository),
                "-c", "core.quotepath=false",
                *arguments,
            ],
            text=True,
            encoding="utf-8",
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("W06 closure Git identity를 확인하지 못했습니다") from error


def _git_blob_sha256(repository: Path, revision: str, path: Path) -> str:
    """! @brief source commit S의 tracked file byte를 checkout 변경 없이 hash합니다. """

    try:
        payload = subprocess.check_output(
            [
                "git", "-C", str(repository),
                "show", f"{revision}:{path.as_posix()}",
            ],
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("W06 source commit input byte를 읽지 못했습니다") from error
    return hashlib.sha256(payload).hexdigest()


def _w06_allowed_closure_path(path: Path, evidence_directory: Path) -> bool:
    """! @brief source 다음 commit에 허용하는 W06 기록 경로만 판정합니다. """

    if path == W06_READINESS_PATH or path in W06_CLOSURE_DOCUMENTS:
        return True
    if _w06_completion_document(path):
        return True
    try:
        path.relative_to(evidence_directory)
        return True
    except ValueError:
        return False


def _w06_completion_document(path: Path) -> bool:
    """! @brief 역사 인계와 번호가 달라도 W06 완료 문서 이름만 허용합니다. """

    return (path.parent == W06_COMPLETION_ROOT and
            W06_COMPLETION_NAME.fullmatch(path.name) is not None)


def _validate_w06_commit_bridge(
    source_revision: str,
    closure_revision: str,
    evidence: Path,
    repository: Path = CORE,
) -> list[Path]:
    """! @brief exact source S 바로 다음의 기록 전용 단일 commit C를 검증합니다. """

    if (REVISION_PATTERN.fullmatch(source_revision) is None or
            REVISION_PATTERN.fullmatch(closure_revision) is None or
            source_revision == closure_revision):
        raise ValueError("W06 source/closure revision bridge가 잘못됐습니다")
    if _git_text(repository, "rev-parse", "HEAD") != closure_revision:
        raise ValueError("W06 closure revision이 current HEAD가 아닙니다")
    if _git_text(
            repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("W06 closure는 clean working tree에서만 유효합니다")
    parent_row = _git_text(
        repository, "rev-list", "--parents", "-n", "1", closure_revision
    ).split()
    if parent_row != [closure_revision, source_revision]:
        raise ValueError(
            "W06 closure는 exact source의 단일 non-merge child여야 합니다"
        )

    try:
        evidence_relative = evidence.resolve().relative_to(repository.resolve())
    except ValueError as error:
        raise ValueError("W06 closure evidence가 저장소 밖에 있습니다") from error
    evidence_relative = Path(evidence_relative.as_posix())
    evidence_directory = evidence_relative.parent
    try:
        evidence_directory.relative_to(W06_EVIDENCE_ROOT)
    except ValueError as error:
        raise ValueError("W06 closure evidence directory가 허용 범위 밖입니다") from error
    if not evidence_directory.name.startswith("m33-w06-"):
        raise ValueError("W06 closure evidence directory 이름이 고정 prefix와 다릅니다")

    changed: list[Path] = []
    rows = _git_text(
        repository,
        "diff",
        "--name-status",
        "--no-renames",
        source_revision,
        closure_revision,
        "--",
    ).splitlines()
    for row in rows:
        pieces = row.split("\t")
        if len(pieces) != 2 or pieces[0] not in {"A", "M"}:
            raise ValueError("W06 closure commit의 path 상태가 허용되지 않습니다")
        path = Path(pieces[1].replace("\\", "/"))
        if not _w06_allowed_closure_path(path, evidence_directory):
            raise ValueError("W06 closure commit이 구현 또는 allowlist 밖을 변경했습니다")
        changed.append(path)
    if (not changed or evidence_relative not in changed or
            W06_READINESS_PATH not in changed or
            not any(_w06_completion_document(path) for path in changed)):
        raise ValueError("W06 closure commit의 필수 evidence/완료/readiness 기록이 없습니다")
    return changed


def _validate_w06_closure(package: dict, cases: list[dict]) -> None:
    """! @brief W06 완료와 세 PASS를 현재 clean source의 strict closure에 결합합니다. """
    package_completed = package.get("status") == "completed"
    any_pass = any(case.get("status") == "PASS" for case in cases)
    if not package_completed and not any_pass:
        return
    if (not package_completed or len(cases) != 3 or
            any(case.get("status") != "PASS" for case in cases)):
        raise ValueError("W06 completion and PASS must be atomic")
    evidence = package.get("exact_evidence")
    if not isinstance(evidence, str) or not evidence:
        raise ValueError("W06 completed without closure evidence")
    relative = Path(evidence)
    if relative.is_absolute():
        raise ValueError("W06 closure evidence must be repository-relative")
    closure_path = (CORE / relative).resolve()
    try:
        closure_path.relative_to(CORE.resolve())
    except ValueError as error:
        raise ValueError("W06 closure evidence escaped repository") from error
    if not closure_path.is_file():
        raise ValueError("W06 closure evidence missing")
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    closure_base = closure_path.parent
    if closure.get("kind") == m33_regression.EXTERNAL_CLOSURE_KIND:
        closure, closure_base = m33_regression.resolve_external_closure(
            closure_path, repository=CORE
        )
    revision = closure.get("source_revision")
    if (REVISION_PATTERN.fullmatch(revision or "") is None or
            closure.get("source_clean") is not True or
            any(case.get("source_revision") != revision or
                case.get("evidence") != evidence for case in cases)):
        raise ValueError("W06 PASS is not bound to closure source/evidence")
    _validate_w06_qualification(closure)
    current = m33_regression.snapshot(CORE)
    closure_revision = current.get("source_revision", "")
    if current.get("source_clean") is not True:
        raise ValueError("W06 closure commit working tree is dirty")
    _validate_w06_commit_bridge(
        revision, closure_revision, closure_path, CORE
    )
    source_context = dict(current)
    source_context["source_revision"] = revision
    inputs = current.get("inputs")
    if (not isinstance(inputs, dict) or "M33" not in inputs or
            not isinstance(inputs["M33"], dict) or
            inputs["M33"].get("path") != W06_READINESS_PATH.as_posix()):
        raise ValueError("W06 closure source input snapshot이 없습니다")
    source_context["inputs"] = {
        key: dict(value) for key, value in inputs.items()
    }
    source_context["inputs"]["M33"]["sha256"] = _git_blob_sha256(
        CORE, revision, W06_READINESS_PATH
    )
    audit = m33_regression.validate_closure(
        closure, closure_base, source_context
    )
    if (audit.get("status") != "AUDIT_ONLY" or
            audit.get("actual_run") != "NOT_VERIFIED" or
            audit.get("source_revision") != revision or
            audit.get("product_qualification") != "NOT_ASSESSED"):
        raise ValueError("W06 strict closure audit result mismatch")


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
        requirements = entry.get("execution_requirements", {})
        if (requirements.get("resolution") not in {
                "not_applicable_excluded", "delegated_existing_owner",
                "implemented_m33_family", "planned_m33_family", "catalog_decision",
            } or not isinstance(requirements.get("roles"), list) or
                not isinstance(requirements.get("external_parts"), list) or
                not isinstance(requirements.get("peer_policy"), str) or
                not isinstance(requirements.get("source"), str)):
            raise ValueError("upstream execution requirements missing")
        delivery = entry.get("arduino_delivery", {})
        if (delivery.get("route") != entry["route"] or
                delivery.get("owner_work_id") != entry["owner_work_id"] or
                not isinstance(delivery.get("source"), str)):
            raise ValueError("upstream Arduino delivery mapping missing")
        if entry.get("result_stages") != [
            "native_build", "nu54dk_build", "arduino_build", "runtime",
            "negative", "interoperability",
        ]:
            raise ValueError("upstream result stage mapping missing")

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
        if any(not (CORE / path).is_file() for path in entry.get("companion_files", [])):
            raise ValueError("installed example companion path missing")
        stages = entry.get("stages", {})
        if set(stages) != {
            "source_candidate", "native_build", "arduino_build",
            "functional_hil", "external_peer_interop",
        }:
            raise ValueError("installed example stage separation missing")
        if (stages["source_candidate"].get("status") != "PRESENT" or
                stages["source_candidate"].get("evidence") != entry["path"] or
                stages["external_peer_interop"].get("status") != "NOT_RUN"):
            raise ValueError("installed example stage promotion invalid")
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
            guidance.get("status") != "completed"):
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
    w05_cases = next(
        family["cases"] for family in families
        if family["id"] == "M33-EXAMPLE-01"
    )
    w06_cases = [
        case
        for family in families
        if TEST_OWNER[family["id"]] == "M33-W06"
        for case in family["cases"]
    ]

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
    if risks != _sdk_risk_catalog():
        raise ValueError("SDK risk regression catalog drift")

    _validate_w05_completion(packages[4], w05_cases)
    _validate_w06_closure(packages[5], w06_cases)

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
