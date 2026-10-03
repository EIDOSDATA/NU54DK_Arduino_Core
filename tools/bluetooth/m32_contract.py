#!/usr/bin/env python3
"""! @brief M32 기능·자원·시험 계약 원장을 생성하고 fail-closed 검증합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


CORE = Path(__file__).resolve().parents[2]
LOCK_PATH = CORE / "tools/ci/ncs-3.4.0.lock.json"
PARITY_PATH = CORE / "variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json"
TARGET_PATH = CORE / "variants/nu54dk/m32-ble-readiness.json"
CONTRACT_EVIDENCE = (
    "00_Docs/01_아두이노 코어 설계/22_M32_BLE_Mesh_무선_착수_계약.md"
)
LOCK = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
PARITY = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
WORK_TITLES = (
    "capability_resource_inventory_contract",
    "le_power_control_path_loss",
    "modern_connection_timing_features",
    "advertising_identity_privacy_resources",
    "nordic_link_diagnostics",
    "mesh_foundation_models_security",
    "mesh_1_1_management_privacy_bridging",
    "mesh_blob_dfu_distribution",
    "ieee802154_esb_standalone",
    "supported_radio_coexistence",
    "functional_hil_negative_regression_soak",
    "api_examples_evidence_handoff",
)
STAGES = (
    "source_candidate",
    "nu54dk_native_build",
    "arduino_build",
    "runtime_capability",
    "functional_hil",
    "external_peer_interop",
)
STAGE_STATUSES = {"PASS", "FAIL", "HOLD", "NOT_RUN", "NOT_APPLICABLE", "UNSUPPORTED"}
ROUTES = {"wrapper", "direct", "profile", "template", "testing_profile"}
APPLICABILITY = {"unresolved", "applicable", "not_applicable", "unsupported"}
SUPPORT_PROMOTION_STAGES = (
    "nu54dk_native_build",
    "arduino_build",
    "runtime_capability",
    "functional_hil",
)


def _sha256_json(value: object) -> str:
    """! @brief JSON 값을 정규 직렬화해 원장 범위 hash를 계산합니다. """
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _m32_parity_scope() -> dict:
    """! @brief Master 원장에서 M32가 소유한 sample·variant를 정확히 고정합니다. """
    samples = sorted(
        entry["id"] for entry in PARITY["samples"]
        if str(entry.get("owner_work_id", "")).startswith("M32-")
    )
    variants = sorted(
        entry["id"] for entry in PARITY["variants"]
        if str(entry.get("owner_work_id", "")).startswith("M32-") or
        str(entry.get("follow_up_owner_work_id", "")).startswith("M32-")
    )
    selected = {
        "samples": [
            entry for entry in PARITY["samples"] if entry["id"] in set(samples)
        ],
        "variants": [
            entry for entry in PARITY["variants"] if entry["id"] in set(variants)
        ],
    }
    return {
        "sample_ids": samples,
        "variant_ids": variants,
        "sample_count": len(samples),
        "variant_count": len(variants),
        "selected_rows_sha256": _sha256_json(selected),
    }


def _stage(status: str = "NOT_RUN", revision: str | None = None,
           evidence: str | None = None) -> dict:
    """! @brief 각 검증 단계를 다른 단계와 합치지 않고 기록합니다. """
    return {"status": status, "revision": revision, "evidence": evidence}


def _capability(identifier: str, owner: str, title: str, kconfig: tuple[str, ...],
                api_sources: tuple[str, ...], upstream_samples: tuple[str, ...],
                route: str, examples: tuple[str, ...], profiles: tuple[str, ...],
                test_ids: tuple[str, ...], controller: str = "product_sdc") -> dict:
    """! @brief 기능 source와 제공·자원·시험 경로를 한 행으로 연결합니다. """
    return {
        "id": identifier,
        "owner_work_id": owner,
        "title": title,
        "controller_variant": controller,
        "kconfig": list(kconfig),
        "api_sources": list(api_sources),
        "upstream_samples": list(upstream_samples),
        "arduino_provision": route,
        "planned_examples": list(examples),
        "resource_profile_ids": list(profiles),
        "test_ids": list(test_ids),
        "target_applicability": "unresolved",
        "stages": {
            "source_candidate": _stage(
                "PASS", LOCK["ncs"]["revision"], CONTRACT_EVIDENCE
            ),
            **{stage: _stage() for stage in STAGES if stage != "source_candidate"},
        },
    }


def _capabilities() -> list[dict]:
    """! @brief M32-W01~W10의 기능 source와 후속 구현 경로를 정의합니다. """
    conn = ("zephyr/include/zephyr/bluetooth/conn.h",)
    host = ("zephyr/include/zephyr/bluetooth/bluetooth.h",)
    hci = ("zephyr/include/zephyr/bluetooth/hci_types.h",)
    mesh = ("zephyr/include/zephyr/bluetooth/mesh/access.h",)
    caps = [
        _capability("modern_le_capability", "M32-W01", "확장 LE feature page와 자원 조회",
                    ("CONFIG_BT_LE_EXTENDED_FEAT_SET",), hci, (), "testing_profile",
                    ("ModernLeCapabilities",), ("ble_baseline", "ble_extended"),
                    ("M32-CAP-01",)),
        _capability("le_power_control", "M32-W02", "LE Power Control·Tx Power Report",
                    ("CONFIG_BT_TRANSMIT_POWER_CONTROL",), conn,
                    ("nrf:samples/bluetooth/rssi_power_control/central",
                     "nrf:samples/bluetooth/rssi_power_control/peripheral"), "wrapper",
                    ("LePowerControlCentral", "LePowerControlPeripheral"),
                    ("ble_baseline",), ("M32-PWR-01",)),
        _capability("path_loss_monitoring", "M32-W02", "Path Loss Monitoring",
                    ("CONFIG_BT_PATH_LOSS_MONITORING",), conn,
                    ("nrf:samples/bluetooth/path_loss_monitoring/central",
                     "nrf:samples/bluetooth/path_loss_monitoring/peripheral"), "wrapper",
                    ("PathLossMonitorCentral", "PathLossMonitorPeripheral"),
                    ("ble_baseline",), ("M32-PATH-01",)),
        _capability("connection_subrating", "M32-W03", "Connection Subrating",
                    ("CONFIG_BT_SUBRATING",), conn,
                    ("nrf:samples/bluetooth/subrating",), "wrapper",
                    ("ConnectionSubratingCentral", "ConnectionSubratingPeripheral"),
                    ("ble_baseline",), ("M32-SUB-01",)),
        _capability("sleep_clock_accuracy_update", "M32-W03", "Sleep Clock Accuracy Update",
                    ("CONFIG_BT_SCA_UPDATE",), conn, (), "direct",
                    ("SleepClockAccuracyUpdate",), ("ble_baseline",), ("M32-SCA-01",)),
        _capability("frame_space_update", "M32-W03", "Frame Space Update",
                    ("CONFIG_BT_FRAME_SPACE_UPDATE", "CONFIG_BT_LE_EXTENDED_FEAT_SET"), conn,
                    ("nrf:samples/bluetooth/throughput",), "direct",
                    ("FrameSpaceUpdateCentral", "FrameSpaceUpdatePeripheral"),
                    ("ble_extended",), ("M32-TIME-01",)),
        _capability("shorter_connection_intervals", "M32-W03", "Shorter Connection Intervals",
                    ("CONFIG_BT_SHORTER_CONNECTION_INTERVALS", "CONFIG_BT_SUBRATING"), conn,
                    ("nrf:samples/bluetooth/shorter_conn_intervals",), "profile",
                    ("ShorterConnectionIntervalsCentral", "ShorterConnectionIntervalsPeripheral"),
                    ("ble_extended",), ("M32-TIME-01",)),
        _capability("extended_le_feature_set", "M32-W03", "LL Extended Feature Set",
                    ("CONFIG_BT_LE_EXTENDED_FEAT_SET",), hci, (), "direct",
                    ("ExtendedLeFeaturePages",), ("ble_extended",), ("M32-FEAT-01",)),
        _capability("channel_classification_throughput", "M32-W03",
                    "Channel classification·map·throughput",
                    ("CONFIG_BT_DATA_LEN_UPDATE", "CONFIG_BT_PHY_UPDATE"), conn,
                    ("nrf:samples/bluetooth/throughput",), "profile",
                    ("BleThroughputCentral", "BleThroughputPeripheral", "LeChannelMapControl"),
                    ("ble_extended",), ("M32-FEAT-01",)),
        _capability("multiple_advertising_sets", "M32-W04", "Multiple Advertising Sets",
                    ("CONFIG_BT_EXT_ADV", "CONFIG_BT_EXT_ADV_MAX_ADV_SET=3"), host,
                    ("nrf:samples/bluetooth/multiple_adv_sets",
                     "zephyr:samples/bluetooth/broadcaster_multiple"), "wrapper",
                    ("MultipleAdvertisingSets", "MultiplePeriodicSyncs"),
                    ("ble_extended",), ("M32-ADV-01",)),
        _capability("multiple_identities", "M32-W04", "Multiple local identities",
                    ("CONFIG_BT_ID_MAX=3", "CONFIG_BT_PRIVACY"), host,
                    ("nrf:samples/bluetooth/peripheral_with_multiple_identities",
                     "zephyr:samples/bluetooth/peripheral_identity"), "wrapper",
                    ("MultipleBleIdentities",), ("ble_extended",), ("M32-PRIV-01",)),
        _capability("advertising_lists", "M32-W04", "Accept·resolving·periodic advertiser lists",
                    ("CONFIG_BT_FILTER_ACCEPT_LIST", "CONFIG_BT_PER_ADV_SYNC"), host,
                    ("zephyr:samples/bluetooth/peripheral_accept_list",), "wrapper",
                    ("AdvertisingAcceptList", "PeriodicAdvertiserList"),
                    ("ble_extended",), ("M32-PRIV-01",)),
        _capability("directed_advertising", "M32-W04", "Directed Advertising",
                    ("CONFIG_BT_PERIPHERAL", "CONFIG_BT_PRIVACY"), host,
                    ("zephyr:samples/bluetooth/direct_adv",), "wrapper",
                    ("DirectedAdvertisingPeripheral", "DirectedAdvertisingCentral"),
                    ("ble_extended",), ("M32-PRIV-01",)),
        _capability("encrypted_advertising_data", "M32-W04", "Encrypted Advertising Data",
                    ("CONFIG_BT_EAD",), host,
                    ("zephyr:samples/bluetooth/encrypted_advertising/central",
                     "zephyr:samples/bluetooth/encrypted_advertising/peripheral"), "wrapper",
                    ("EncryptedAdvertisingCentral", "EncryptedAdvertisingPeripheral"),
                    ("ble_extended",), ("M32-EAD-01",)),
        _capability("advertising_coding_selection", "M32-W04", "Advertising Coding Selection",
                    ("CONFIG_BT_CTLR_PHY_CODED", "CONFIG_BT_EXT_ADV_CODING_SELECTION"),
                    host, (), "direct",
                    ("AdvertisingCodingSelection",), ("ble_extended",), ("M32-ADV-01",)),
        _capability("scan_while_initiating", "M32-W04", "Scan while initiating",
                    ("CONFIG_BT_SCAN_AND_INITIATE_IN_PARALLEL", "CONFIG_BT_SCAN_WITH_IDENTITY"), host,
                    ("nrf:samples/bluetooth/scanning_while_connecting",), "profile",
                    ("ScanWhileConnecting",), ("ble_extended",), ("M32-ADV-01",)),
        _capability("scalable_ble_resources", "M32-W04", "ARF-01 BLE role budget",
                    ("CONFIG_BT_MAX_CONN=2",), host, (), "profile",
                    ("ScalableBleResources",),
                    ("ble_c1p1", "ble_c2p0", "ble_c0p2"), ("M32-ADV-01",)),
        _capability("nordic_llpm", "M32-W05", "Nordic LLPM",
                    ("CONFIG_BT_CTLR_SDC_LLPM",),
                    ("nrf/include/bluetooth/hci_vs_sdc.h",),
                    ("nrf:samples/bluetooth/llpm",), "direct", ("NordicLlpmPair",),
                    ("ble_nordic",), ("M32-NORDIC-01",)),
        _capability("nordic_qos_conn_event", "M32-W05", "QoS Connection Event Reports",
                    ("CONFIG_BT_CTLR_SDC_QOS_CONN_EVENT_REPORT",),
                    ("nrf/include/bluetooth/hci_vs_sdc.h",), (), "direct",
                    ("NordicConnectionEventQos",), ("ble_nordic",), ("M32-NORDIC-01",)),
        _capability("nordic_qos_channel_survey", "M32-W05", "QoS Channel Survey",
                    ("CONFIG_BT_CTLR_SDC_QOS_CHANNEL_SURVEY",),
                    ("nrf/include/bluetooth/hci_vs_sdc.h",), (), "direct",
                    ("NordicChannelSurvey",), ("ble_nordic",), ("M32-NORDIC-01",)),
        _capability("connection_time_sync", "M32-W05", "Connection Time Sync",
                    ("CONFIG_BT_CTLR_SDC_CONN_ANCHOR_POINT_REPORT", "CONFIG_BT_HCI_VS_EVT_USER"),
                    ("nrf/include/bluetooth/hci_vs_sdc.h",),
                    ("nrf:samples/bluetooth/conn_time_sync",), "profile",
                    ("ConnectionTimeSyncCentral", "ConnectionTimeSyncPeripheral"),
                    ("ble_nordic",), ("M32-SYNC-01",)),
        _capability("radio_event_trigger", "M32-W05", "Event Trigger",
                    ("CONFIG_BT_CTLR_SDC_EVENT_TRIGGER",),
                    ("nrf/include/bluetooth/hci_vs_sdc.h",),
                    ("nrf:samples/bluetooth/event_trigger",), "direct",
                    ("RadioEventTrigger",), ("ble_nordic",), ("M32-EVENT-01",)),
        _capability("radio_notification", "M32-W05", "Radio Notification callback",
                    ("CONFIG_BT_RADIO_NOTIFICATION_CONN_CB",),
                    ("nrf/include/bluetooth/hci_vs_sdc.h",),
                    ("nrf:samples/bluetooth/radio_notification_cb",), "direct",
                    ("ConnectionRadioNotification",), ("ble_nordic",), ("M32-EVENT-01",)),
        _capability("flushable_acl_data", "M32-W05", "LE Flushable ACL Data",
                    ("CONFIG_BT_CTLR_LE_FLUSHABLE_ACL_DATA",), hci, (), "direct",
                    ("FlushableAclData",), ("ble_nordic",), ("M32-ACL-01",)),
        _capability("mesh_provisioning_configuration_health", "M32-W06",
                    "Mesh provisioning·configuration·health",
                    ("CONFIG_BT_MESH", "CONFIG_BT_MESH_PB_GATT"), mesh,
                    ("zephyr:samples/bluetooth/mesh", "zephyr:samples/bluetooth/mesh_provisioner",
                     "nrf:samples/bluetooth/mesh/chat"), "wrapper",
                    ("MeshProvisioner", "MeshNode", "MeshHealth"),
                    ("mesh_base",), ("M32-MESH-01", "M32-MESHSEC-01")),
        _capability("mesh_relay_friend_lpn_proxy", "M32-W06", "Mesh Relay·Friend·LPN·Proxy",
                    ("CONFIG_BT_MESH_RELAY", "CONFIG_BT_MESH_FRIEND",
                     "CONFIG_BT_MESH_LOW_POWER", "CONFIG_BT_MESH_GATT_PROXY_ENABLED"), mesh,
                    ("zephyr:samples/bluetooth/mesh",), "profile",
                    ("MeshRelay", "MeshFriend", "MeshLowPowerNode", "MeshProxy"),
                    ("mesh_base",), ("M32-MESH-01",)),
        _capability("mesh_standard_models_settings", "M32-W06", "Mesh model·settings·key refresh",
                    ("CONFIG_BT_MESH", "CONFIG_SETTINGS"), mesh,
                    ("nrf:samples/bluetooth/mesh/light", "nrf:samples/bluetooth/mesh/light_switch",
                     "nrf:samples/bluetooth/mesh/light_dimmer",
                     "nrf:samples/bluetooth/mesh/sensor_client",
                     "nrf:samples/bluetooth/mesh/sensor_server"), "profile",
                    ("MeshOnOff", "MeshLevel", "MeshLight", "MeshSensor",
                     "MeshTimeSceneScheduler"), ("mesh_base",),
                    ("M32-MESH-01", "M32-MESHSEC-01")),
        _capability("mesh_remote_provisioning", "M32-W07", "Mesh Remote Provisioning",
                    ("CONFIG_BT_MESH_RPR_CLI", "CONFIG_BT_MESH_RPR_SRV"), mesh, (), "direct",
                    ("MeshRemoteProvisioner", "MeshRemoteProvisioningServer"),
                    ("mesh_management",), ("M32-MESH11-01",)),
        _capability("mesh_sar_configuration", "M32-W07", "Mesh SAR Configuration",
                    ("CONFIG_BT_MESH_SAR_CFG_CLI", "CONFIG_BT_MESH_SAR_CFG_SRV"), mesh, (), "direct",
                    ("MeshSarConfigurationClient", "MeshSarConfigurationServer"),
                    ("mesh_management",), ("M32-MESH11-01",)),
        _capability("mesh_opcodes_aggregator", "M32-W07", "Mesh Opcodes Aggregator",
                    ("CONFIG_BT_MESH_OP_AGG_CLI", "CONFIG_BT_MESH_OP_AGG_SRV"), mesh, (), "direct",
                    ("MeshOpcodeAggregatorClient", "MeshOpcodeAggregatorServer"),
                    ("mesh_management",), ("M32-MESH11-01",)),
        _capability("mesh_large_composition_data", "M32-W07", "Mesh Large Composition Data",
                    ("CONFIG_BT_MESH_LARGE_COMP_DATA_CLI", "CONFIG_BT_MESH_LARGE_COMP_DATA_SRV"),
                    mesh, (), "direct",
                    ("MeshLargeCompositionDataClient", "MeshLargeCompositionDataServer"),
                    ("mesh_management",), ("M32-MESH11-01",)),
        _capability("mesh_private_beacon", "M32-W07", "Mesh Private Beacon",
                    ("CONFIG_BT_MESH_PRIV_BEACONS", "CONFIG_BT_MESH_PRIV_BEACON_CLI",
                     "CONFIG_BT_MESH_PRIV_BEACON_SRV"), mesh, (), "direct",
                    ("MeshPrivateBeaconClient", "MeshPrivateBeaconServer"),
                    ("mesh_management",), ("M32-MESH11-01",)),
        _capability("mesh_private_proxy_solicitation", "M32-W07",
                    "Mesh On-Demand Private Proxy·Solicitation",
                    ("CONFIG_BT_MESH_OD_PRIV_PROXY_CLI", "CONFIG_BT_MESH_OD_PRIV_PROXY_SRV",
                     "CONFIG_BT_MESH_SOLICITATION", "CONFIG_BT_MESH_SOL_PDU_RPL_CLI"), mesh, (),
                    "direct", ("MeshOnDemandPrivateProxy", "MeshProxySolicitation"),
                    ("mesh_management",), ("M32-MESH11-01",)),
        _capability("mesh_subnet_bridging", "M32-W07", "Mesh Subnet Bridging",
                    ("CONFIG_BT_MESH_BRG_CFG_CLI", "CONFIG_BT_MESH_BRG_CFG_SRV"), mesh, (), "direct",
                    ("MeshSubnetBridge",), ("mesh_management",), ("M32-MESH11-01",)),
        _capability("mesh_blob_transfer", "M32-W08", "Mesh BLOB Transfer",
                    ("CONFIG_BT_MESH_BLOB_CLI", "CONFIG_BT_MESH_BLOB_SRV"), mesh,
                    ("nrf:samples/bluetooth/mesh/dfu/distributor",
                     "nrf:samples/bluetooth/mesh/dfu/target"), "direct",
                    ("MeshBlobClient", "MeshBlobServer"), ("mesh_dfu_internal",),
                    ("M32-BLOB-01",)),
        _capability("mesh_dfu_distribution", "M32-W08", "Mesh DFU·Firmware Distribution",
                    ("CONFIG_BT_MESH_DFU_CLI", "CONFIG_BT_MESH_DFU_SRV",
                     "CONFIG_BT_MESH_DFD_SRV"), mesh,
                    ("nrf:samples/bluetooth/mesh/dfu/distributor",
                     "nrf:samples/bluetooth/mesh/dfu/target"), "template",
                    ("MeshDfuTarget", "MeshFirmwareDistributor"),
                    ("mesh_dfu_internal",), ("M32-MDFU-01",)),
        _capability("ieee802154_standalone", "M32-W09", "IEEE 802.15.4 최소 TX/RX",
                    ("CONFIG_IEEE802154",),
                    ("zephyr/include/zephyr/net/ieee802154_radio.h",), (), "testing_profile",
                    ("Radio154Transmitter", "Radio154Receiver"),
                    ("radio_ieee802154",), ("M32-154-01",)),
        _capability("esb_standalone", "M32-W09", "ESB PTX/PRX",
                    ("CONFIG_ESB",), ("nrf/include/esb.h",), (), "testing_profile",
                    ("EsbPtx", "EsbPrx"), ("radio_esb",), ("M32-ESB-01",)),
        _capability("ble_mesh_coexistence", "M32-W10", "BLE와 Mesh 공존",
                    ("CONFIG_BT", "CONFIG_BT_MESH"), mesh,
                    ("nrf:samples/bluetooth/mesh/ble_peripheral_lbs_coex",), "profile",
                    ("BleMeshCoexistence",), ("coexistence_ble_mesh",), ("M32-COEX-01",)),
        _capability("ble_ieee802154_coexistence", "M32-W10", "BLE와 IEEE 802.15.4 공존",
                    ("CONFIG_MPSL", "CONFIG_IEEE802154"), hci,
                    ("nrf:applications/ipc_radio",), "profile",
                    ("Ble154Coexistence",), ("coexistence_ble_154",), ("M32-COEX-01",)),
        _capability("ble_esb_coexistence", "M32-W10", "BLE와 ESB 공존 후보",
                    ("CONFIG_MPSL", "CONFIG_ESB"), ("nrf/include/esb.h",),
                    ("nrf:samples/esb/esb_prx_ble", "nrf:samples/esb/esb_ptx_ble"), "profile",
                    ("BleEsbCoexistence",), ("coexistence_ble_esb",), ("M32-COEX-01",)),
        _capability("radio_coexistence_one_wire", "M32-W10", "외부 1-wire coexistence",
                    ("CONFIG_MPSL_CX",), hci,
                    ("nrf:samples/bluetooth/radio_coex_1wire",), "template",
                    ("RadioCoexistenceOneWire",), ("external_coexistence",), ("M32-COEX-01",)),
    ]
    return caps


def _resource_profiles() -> list[dict]:
    """! @brief 연결·광고·Mesh·radio 자원 상한과 memory guard를 고정합니다. """
    common_memory = {
        "physical_ram_bytes": 262144,
        "application_rram_partition_bytes": 729088,
        "maximum_ram_bytes": 235520,
        "maximum_rram_bytes": 655360,
        "minimum_free_ram_bytes": 26624,
        "minimum_free_rram_bytes": 73728,
    }
    rows = (
        ("ble_baseline", 2, 1, 1, 1, 1, 6, 0, "ble"),
        ("ble_extended", 2, 1, 3, 3, 2, 8, 0, "ble"),
        ("ble_c1p1", 2, 1, 3, 3, 2, 8, 0, "ble"),
        ("ble_c2p0", 2, 0, 1, 2, 2, 8, 0, "ble"),
        ("ble_c0p2", 2, 2, 2, 2, 1, 8, 0, "ble"),
        ("ble_nordic", 2, 1, 1, 1, 1, 8, 0, "ble"),
        ("mesh_base", 2, 1, 1, 1, 0, 8, 2, "mesh"),
        ("mesh_management", 2, 1, 1, 1, 0, 8, 2, "mesh"),
        ("mesh_dfu_internal", 2, 1, 1, 1, 0, 10, 2, "mesh_dfu"),
        ("radio_ieee802154", 0, 0, 0, 0, 0, 0, 0, "ieee802154"),
        ("radio_esb", 0, 0, 0, 0, 0, 0, 0, "esb"),
        ("coexistence_ble_mesh", 2, 1, 1, 1, 0, 8, 2, "coexistence"),
        ("coexistence_ble_154", 1, 1, 1, 1, 0, 6, 0, "coexistence"),
        ("coexistence_ble_esb", 1, 1, 1, 1, 0, 6, 0, "coexistence_candidate"),
        ("external_coexistence", 1, 1, 1, 1, 0, 6, 0, "external_template"),
    )
    return [
        {
            "id": identifier,
            "max_connections": connections,
            "peripheral_connections": peripherals,
            "advertising_sets": advertising_sets,
            "identities": identities,
            "periodic_syncs": syncs,
            "acl_buffers_per_direction": buffers,
            "mesh_remote_nodes": mesh_nodes,
            "radio_mode": mode,
            "measured_ram_bytes": None,
            "measured_rram_bytes": None,
            **common_memory,
        }
        for identifier, connections, peripherals, advertising_sets, identities, syncs,
        buffers, mesh_nodes, mode in rows
    ]


def _case(identifier: str, owner: str, roles: tuple[str, ...], boards: int,
          timeout_s: int, iterations: int, packets: int, allowed_loss: int,
          latency_ms: int, metric: str, negative: tuple[str, ...]) -> dict:
    """! @brief 실행 전 고정해야 할 유한 분모·복구·중단 정책을 만듭니다. """
    return {
        "id": identifier,
        "owner_work_id": owner,
        "roles": list(roles),
        "minimum_boards": boards,
        "timeout_s": timeout_s,
        "iterations": iterations,
        "packet_denominator": packets,
        "allowed_loss_packets": allowed_loss,
        "latency_limit_ms": latency_ms,
        "metric": metric,
        "negative_classes": list(negative),
        "recovery_timeout_s": 30,
        "abort_conditions": [
            "revision_mismatch", "wrong_role_or_image", "unexpected_security_acceptance",
            "payload_corruption", "resource_cleanup_failure",
        ],
        "maximum_diagnostic_retests": 1,
        "verification_owner": "developer",
        "verification_stage": "development",
        "development_blocker": True,
        "release_blocker": True,
        "status": "NOT_RUN",
        "source_revision": None,
        "evidence": None,
    }


def _test_families() -> list[dict]:
    """! @brief M32 예정 test ID를 하위 case와 정량 조건으로 확정합니다. """
    definitions = [
        ("M32-CAP-01", "M32-W01", ("capability_probe",), 1, 60, 1, 13, 0, 5000,
         "controller_feature_and_resource_records", ("missing", "duplicate", "unknown", "revision")),
        ("M32-PWR-01", "M32-W02", ("central", "peripheral"), 2, 180, 20, 40, 0, 5000,
         "tx_power_reports", ("unsupported_peer", "out_of_range", "stale_handle")),
        ("M32-PATH-01", "M32-W02", ("monitor", "peer"), 2, 240, 20, 60, 1, 5000,
         "path_loss_zone_events", ("invalid_threshold", "disabled_report", "peer_loss")),
        ("M32-SUB-01", "M32-W03", ("central", "peripheral"), 2, 240, 20, 40, 0, 5000,
         "subrate_changes", ("rejected_request", "stale_link", "invalid_factor")),
        ("M32-SCA-01", "M32-W03", ("central", "peripheral"), 2, 180, 20, 20, 0, 5000,
         "sca_updates", ("unsupported_peer", "disconnect_pending")),
        ("M32-TIME-01", "M32-W03", ("central", "peripheral"), 2, 240, 20, 2000, 20, 50,
         "frame_space_interval_packets", ("invalid_combination", "controller_reject")),
        ("M32-FEAT-01", "M32-W03", ("central", "peripheral"), 2, 180, 20, 40, 0, 5000,
         "feature_page_and_channel_updates", ("unknown_page", "all_channels_disabled", "cross_link")),
        ("M32-ADV-01", "M32-W04", ("advertiser_a", "advertiser_b", "scanner"), 3, 300, 20, 600, 6, 500,
         "set_sid_scan_records", ("over_capacity", "stale_set", "scan_initiate_conflict")),
        ("M32-PRIV-01", "M32-W04", ("identity_a", "identity_b", "peer"), 3, 300, 20, 200, 0, 1000,
         "identity_list_reconnections", ("wrong_identity", "unauthorized_peer", "active_list_change")),
        ("M32-EAD-01", "M32-W04", ("advertiser", "scanner"), 2, 240, 20, 400, 4, 1000,
         "authenticated_advertisements", ("tamper", "wrong_key", "wrong_iv", "replay")),
        ("M32-NORDIC-01", "M32-W05", ("central", "peripheral"), 2, 300, 20, 200, 2, 1000,
         "vendor_link_reports", ("unsupported_vendor_feature", "overflow", "disabled_callback")),
        ("M32-SYNC-01", "M32-W05", ("time_source", "time_sink"), 2, 300, 20, 1000, 10, 5,
         "timestamp_samples", ("wrap", "stale_sample", "peer_loss")),
        ("M32-EVENT-01", "M32-W05", ("event_source", "observer"), 2, 240, 20, 200, 0, 5,
         "event_and_notification_callbacks", ("cancelled_event", "duplicate_reservation", "late_callback")),
        ("M32-ACL-01", "M32-W05", ("sender", "receiver"), 2, 300, 20, 1000, 10, 1000,
         "flushable_acl_buffers", ("unsupported_peer", "expired_buffer", "post_disconnect_access")),
        ("M32-MESH-01", "M32-W06", ("provisioner", "node_a", "node_b"), 3, 600, 10, 300, 0, 2000,
         "provisioned_model_messages", ("unprovisioned_access", "invalid_opcode", "peer_loss")),
        ("M32-MESHSEC-01", "M32-W06", ("provisioner", "node_a", "node_b"), 3, 600, 10, 200, 0, 2000,
         "secured_mesh_messages", ("wrong_key", "replay", "settings_corruption")),
        ("M32-MESH11-01", "M32-W07", ("client", "server", "target"), 3, 900, 10, 350, 0, 3000,
         "mesh_1_1_management_operations", ("malformed", "out_of_range", "replay", "wrong_subnet")),
        ("M32-BLOB-01", "M32-W08", ("blob_client", "blob_server", "observer"), 3, 10800, 10, 1024, 0, 3000,
         "blob_chunks", ("missing_chunk", "bad_digest", "cancel_resume")),
        ("M32-MDFU-01", "M32-W08", ("distributor", "target_a", "target_b"), 3, 10800, 5, 10, 0, 5000,
         "firmware_distribution_targets", ("wrong_image", "wrong_key", "rollback", "partial_image")),
        ("M32-154-01", "M32-W09", ("transmitter", "receiver"), 2, 300, 20, 2000, 20, 100,
         "ieee802154_packets", ("invalid_channel", "invalid_length", "missing_stop")),
        ("M32-ESB-01", "M32-W09", ("ptx", "prx"), 2, 300, 20, 2000, 20, 100,
         "esb_acknowledged_packets", ("invalid_rate", "invalid_length", "missing_ack", "missing_stop")),
        ("M32-COEX-01", "M32-W10", ("service_a", "service_b", "observer"), 3, 600, 20, 4000, 80, 500,
         "per_protocol_packets", ("double_ownership", "starvation", "restart_failure")),
        ("M32-REG-01", "M32-W11", ("regression_roles",), 3, 1200, 1, 12, 0, 5000,
         "baseline_family_count", ("cross_link", "security_regression", "cleanup")),
        ("M32-SOAK-01", "M32-W11", ("stress_roles",), 3, 1800, 1, 10000, 100, 500,
         "bounded_soak_packets", ("counter_regression", "payload_corruption", "resource_leak")),
    ]
    return [
        {"id": family, "cases": [_case(
            f"{family}:primary", owner, roles, boards, timeout, iterations, packets,
            allowed_loss, latency, metric, negative
        )]}
        for family, owner, roles, boards, timeout, iterations, packets, allowed_loss,
        latency, metric, negative in definitions
    ]


def contract() -> dict:
    """! @brief M32 초기 원장을 생성합니다. """
    scope = _m32_parity_scope()
    capabilities = _capabilities()
    profiles = _resource_profiles()
    families = _test_families()
    document = {
        "schema_version": 1,
        "milestone": "M32",
        "phase": "implementation_in_progress",
        "milestone_status": "not_completed",
        "baseline": {
            "supported_release": "v0.5.0",
            "development_release": "v0.6.0",
            "development_branch": "Dev-0.6.0-M32",
            "target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
            "ncs_revision": LOCK["ncs"]["revision"],
            "zephyr_revision": LOCK["zephyr"]["revision"],
            "board_revision": LOCK["board"]["revision"],
            "toolchain_bundle": LOCK["windows_toolchain"]["bundle_id"],
            "parity_lock_sha256": PARITY["lock_sha256"],
        },
        "parity_scope": scope,
        "work_packages": [
            {"id": f"M32-W{index:02}", "title": title, "status": "not_started",
             "exact_evidence": None}
            for index, title in enumerate(WORK_TITLES, 1)
        ],
        "validated_support_candidates": {
            "publication_status": "not_published",
            "capability_ids": [],
        },
        "capabilities": capabilities,
        "resource_profiles": profiles,
        "profile_conflicts": [
            {"left": "radio_ieee802154", "right": "radio_esb",
             "condition": "same_image", "status": "forbidden"},
            {"left": "mesh_dfu_internal", "right": "radio_esb",
             "condition": "same_image", "status": "forbidden_use_dedicated_profile"},
            {"left": "mesh_dfu_internal", "right": "radio_ieee802154",
             "condition": "same_image", "status": "forbidden_use_dedicated_profile"},
            {"left": "ble_extended", "right": "mesh_management",
             "condition": "combined_maxima", "status": "forbidden_use_dedicated_profile"},
            {"left": "scan_initiate_parallel", "right": "multiple_identities",
             "condition": "same_image",
             "status": "forbidden_by_fixed_controller_requires_id_max_1"},
            {"left": "coexistence_ble_esb", "right": "product_support",
             "condition": "before_standalone_and_coexistence_hil", "status": "candidate_only"},
        ],
        "build_matrix": [
            {"id": "m32_capability_baseline_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_capability",
             "extra_conf_file": "baseline.conf", "resource_profile_id": "ble_baseline",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_capability_extended_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_capability",
             "extra_conf_file": "extended.conf", "resource_profile_id": "ble_extended",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_advertising_extended_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_advertising_contract",
             "extra_conf_file": None, "resource_profile_id": "ble_extended",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_scan_initiate_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_scan_initiate_contract",
             "extra_conf_file": None, "resource_profile_id": "ble_baseline",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_resource_c1p1_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_resource_contract",
             "extra_conf_file": "c1p1.conf", "resource_profile_id": "ble_c1p1",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_resource_c2p0_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_resource_contract",
             "extra_conf_file": "c2p0.conf", "resource_profile_id": "ble_c2p0",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_resource_c0p2_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_resource_contract",
             "extra_conf_file": "c0p2.conf", "resource_profile_id": "ble_c0p2",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_nordic_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_ble_nordic_contract",
             "extra_conf_file": None, "resource_profile_id": "ble_nordic",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_mesh_base_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_mesh_contract",
             "extra_conf_file": None, "resource_profile_id": "mesh_base",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_mesh_management_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_mesh_management_contract",
             "extra_conf_file": None, "resource_profile_id": "mesh_management",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_mesh_dfu_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_mesh_update_contract",
             "extra_conf_file": None, "resource_profile_id": "mesh_dfu_internal",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_radio_ieee802154", "controller_variant": "direct_radio",
             "application": "tests/zephyr/m32_radio154_contract",
             "extra_conf_file": None, "resource_profile_id": "radio_ieee802154",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_radio_esb", "controller_variant": "direct_radio",
             "application": "tests/zephyr/m32_esb_contract",
             "extra_conf_file": None, "resource_profile_id": "radio_esb",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_coexistence_ble_mesh_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_coexistence_contract",
             "extra_conf_file": "ble_mesh.conf", "resource_profile_id": "coexistence_ble_mesh",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_coexistence_ble_154_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_coexistence_contract",
             "extra_conf_file": "ble_154.conf", "resource_profile_id": "coexistence_ble_154",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_coexistence_ble_esb_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_coexistence_contract",
             "extra_conf_file": "ble_esb.conf", "resource_profile_id": "coexistence_ble_esb",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
            {"id": "m32_coexistence_external_one_wire_sdc", "controller_variant": "product_sdc",
             "application": "tests/zephyr/m32_coexistence_contract",
             "extra_conf_file": "external.conf", "resource_profile_id": "external_coexistence",
             "status": "NOT_RUN", "source_revision": None, "evidence": None},
        ],
        "test_families": families,
        "follow_up_cases": [
            {"id": "external_peer_product_interop", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "external_storage_mesh_dfu_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "external_one_wire_coexistence_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "ubuntu_host_physical", "verification_owner": "user",
             "verification_stage": "final_release", "development_blocker": False,
             "release_blocker": True, "status": "NOT_RUN", "evidence": None},
            {"id": "macos_host_physical", "verification_owner": "user",
             "verification_stage": "final_release", "development_blocker": False,
             "release_blocker": True, "status": "NOT_RUN", "evidence": None},
        ],
        "counts": {
            "work_total": 12,
            "work_completed": 0,
            "capability_total": len(capabilities),
            "resource_profile_total": len(profiles),
            "test_family_total": len(families),
            "test_family_passed": 0,
            "test_case_total": sum(len(family["cases"]) for family in families),
            "m32_parity_samples": scope["sample_count"],
            "m32_parity_variants": scope["variant_count"],
        },
    }
    validate(document)
    return document


def _validate_stage(stage: dict, identifier: str) -> None:
    """! @brief PASS·NOT_RUN·UNSUPPORTED의 revision/evidence 승격을 검사합니다. """
    if set(stage) != {"status", "revision", "evidence"} or stage["status"] not in STAGE_STATUSES:
        raise ValueError(f"{identifier}: unknown or missing stage field")
    if stage["status"] == "PASS":
        if (not isinstance(stage["revision"], str) or
                REVISION_PATTERN.fullmatch(stage["revision"]) is None or
                not isinstance(stage["evidence"], str) or
                not (CORE / stage["evidence"]).is_file()):
            raise ValueError(f"{identifier}: PASS without exact revision/evidence")
    elif stage["status"] == "NOT_RUN" and (
        stage["revision"] is not None or stage["evidence"] is not None
    ):
        raise ValueError(f"{identifier}: NOT_RUN has evidence")


def validate(document: dict, sdk_root: Path | None = None) -> None:
    """! @brief 누락·중복·unknown·revision drift·부당 PASS를 거부합니다. """
    if document.get("schema_version") != 1 or document.get("milestone") != "M32":
        raise ValueError("M32 schema identity mismatch")
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
    if baseline.get("development_branch") != "Dev-0.6.0-M32":
        raise ValueError("M32 development branch mismatch")

    scope = _m32_parity_scope()
    if document.get("parity_scope") != scope:
        raise ValueError("M32 parity owner rows drift")
    if scope["sample_count"] != 41 or scope["variant_count"] != 74:
        raise ValueError("M32 parity denominator mismatch")
    if SHA256_PATTERN.fullmatch(scope["selected_rows_sha256"]) is None:
        raise ValueError("M32 parity hash malformed")

    packages = document.get("work_packages", [])
    counts = document.get("counts", {})
    if len(packages) != 12 or [entry.get("id") for entry in packages] != [
        f"M32-W{index:02}" for index in range(1, 13)
    ]:
        raise ValueError("work package denominator or identity mismatch")
    if any(entry.get("status") not in {"not_started", "in_progress", "completed"}
           for entry in packages):
        raise ValueError("work package status unknown")
    for entry in packages:
        if entry["status"] == "completed":
            evidence = entry.get("exact_evidence")
            if not isinstance(evidence, str) or not (CORE / evidence).is_file():
                raise ValueError("completed work without exact evidence")

    profile_ids = [entry.get("id") for entry in document.get("resource_profiles", [])]
    if len(profile_ids) != len(set(profile_ids)) or None in profile_ids:
        raise ValueError("resource profile identity duplicate or missing")
    for profile in document["resource_profiles"]:
        if (profile["maximum_ram_bytes"] > profile["physical_ram_bytes"] or
                profile["maximum_rram_bytes"] > profile["application_rram_partition_bytes"] or
                profile["maximum_ram_bytes"] + profile["minimum_free_ram_bytes"] !=
                profile["physical_ram_bytes"] or
                profile["maximum_rram_bytes"] + profile["minimum_free_rram_bytes"] !=
                profile["application_rram_partition_bytes"]):
            raise ValueError("resource memory guard mismatch")
        if profile["peripheral_connections"] > profile["max_connections"]:
            raise ValueError("peripheral count exceeds connection count")
        for measured, maximum in (("measured_ram_bytes", "maximum_ram_bytes"),
                                  ("measured_rram_bytes", "maximum_rram_bytes")):
            value = profile[measured]
            if value is not None and (not isinstance(value, int) or value > profile[maximum]):
                raise ValueError("measured resource exceeds fixed budget")

    sample_ids = {entry["id"] for entry in PARITY["samples"]}
    capability_ids = []
    used_tests = set()
    for capability in document.get("capabilities", []):
        identifier = capability.get("id")
        capability_ids.append(identifier)
        if capability.get("owner_work_id") not in {f"M32-W{index:02}" for index in range(1, 11)}:
            raise ValueError(f"{identifier}: owner unknown")
        if capability.get("arduino_provision") not in ROUTES:
            raise ValueError(f"{identifier}: route unknown")
        if capability.get("target_applicability") not in APPLICABILITY:
            raise ValueError(f"{identifier}: target applicability unknown")
        if not capability.get("kconfig") or not capability.get("api_sources"):
            raise ValueError(f"{identifier}: Kconfig/API mapping missing")
        if (not capability.get("planned_examples") or not capability.get("resource_profile_ids") or
                not capability.get("test_ids")):
            raise ValueError(f"{identifier}: Arduino/resource/test mapping missing")
        if any(profile not in profile_ids for profile in capability["resource_profile_ids"]):
            raise ValueError(f"{identifier}: resource profile unknown")
        if any(sample not in sample_ids for sample in capability["upstream_samples"]):
            raise ValueError(f"{identifier}: upstream sample unknown")
        used_tests.update(capability["test_ids"])
        if set(capability.get("stages", {})) != set(STAGES):
            raise ValueError(f"{identifier}: independent stage schema missing")
        for stage_name, stage in capability["stages"].items():
            _validate_stage(stage, f"{identifier}/{stage_name}")
        if capability["stages"]["functional_hil"]["status"] == "PASS" and (
            capability["stages"]["nu54dk_native_build"]["status"] != "PASS"
        ):
            raise ValueError(f"{identifier}: HIL promoted before NU54DK build")
        if sdk_root is not None:
            for reference in capability["api_sources"]:
                if not (sdk_root / reference).is_file():
                    raise ValueError(f"{identifier}: SDK source missing: {reference}")
    if len(capability_ids) != len(set(capability_ids)) or None in capability_ids:
        raise ValueError("capability identity duplicate or missing")

    support_candidates = document.get("validated_support_candidates", {})
    eligible_capabilities = sorted(
        capability["id"] for capability in document["capabilities"]
        if capability["target_applicability"] == "applicable" and all(
            capability["stages"][stage]["status"] == "PASS"
            for stage in SUPPORT_PROMOTION_STAGES
        )
    )
    if (
        support_candidates.get("publication_status") != "not_published"
        or support_candidates.get("capability_ids") != eligible_capabilities
    ):
        raise ValueError("source/build-only capability promoted to support catalog")

    family_ids = [entry.get("id") for entry in document.get("test_families", [])]
    if len(family_ids) != 24 or len(family_ids) != len(set(family_ids)):
        raise ValueError("test family denominator or duplicate mismatch")
    if used_tests - set(family_ids):
        raise ValueError("capability references unknown test family")
    for family in document["test_families"]:
        cases = family.get("cases", [])
        if not cases:
            raise ValueError("test family has no case")
        for entry in cases:
            required = {
                "iterations", "timeout_s", "packet_denominator", "allowed_loss_packets",
                "latency_limit_ms", "recovery_timeout_s", "abort_conditions",
                "maximum_diagnostic_retests",
            }
            if not required.issubset(entry) or any(
                not isinstance(entry[key], int) or entry[key] < 0
                for key in required - {"abort_conditions"}
            ):
                raise ValueError("test quantitative contract missing")
            if (entry["iterations"] < 1 or entry["timeout_s"] < 1 or
                    entry["packet_denominator"] < 1 or entry["recovery_timeout_s"] < 1 or
                    entry["maximum_diagnostic_retests"] != 1 or
                    entry["allowed_loss_packets"] > entry["packet_denominator"] or
                    not entry["abort_conditions"]):
                raise ValueError("test quantitative contract invalid")
            if (entry.get("verification_owner") != "developer" or
                    entry.get("verification_stage") != "development" or
                    entry.get("development_blocker") is not True or
                    entry.get("release_blocker") is not True):
                raise ValueError("required implementation hidden as follow-up")
            if entry.get("status") not in {"PASS", "FAIL", "HOLD", "NOT_RUN"}:
                raise ValueError("test status unknown")
            if entry["status"] == "PASS" and (
                not isinstance(entry.get("source_revision"), str) or
                REVISION_PATTERN.fullmatch(entry["source_revision"]) is None or
                not isinstance(entry.get("evidence"), str) or
                not (CORE / entry["evidence"]).is_file()
            ):
                raise ValueError("PASS test without exact source/evidence")
            if entry["status"] == "NOT_RUN" and (
                entry.get("source_revision") is not None or entry.get("evidence") is not None
            ):
                raise ValueError("NOT_RUN test has evidence")

    for entry in document.get("build_matrix", []):
        if entry.get("resource_profile_id") not in profile_ids:
            raise ValueError("build matrix resource profile unknown")
        if entry.get("status") not in {"PASS", "FAIL", "HOLD", "NOT_RUN"}:
            raise ValueError("build matrix status unknown")
        if entry["status"] == "PASS" and (
            not isinstance(entry.get("source_revision"), str) or
            REVISION_PATTERN.fullmatch(entry["source_revision"]) is None or
            not isinstance(entry.get("evidence"), str) or
            not (CORE / entry["evidence"]).is_file()
        ):
            raise ValueError("build PASS without exact source/evidence")
        if entry["status"] == "NOT_RUN" and (
            entry.get("source_revision") is not None or entry.get("evidence") is not None
        ):
            raise ValueError("NOT_RUN build has evidence")

    for entry in document.get("follow_up_cases", []):
        if (entry.get("verification_owner") != "user" or
                entry.get("development_blocker") is not False or
                entry.get("status") not in {"PASS", "FAIL", "HOLD", "NOT_RUN"}):
            raise ValueError("follow-up owner/blocker/status corruption")
        if entry["verification_stage"] == "user_follow_up" and entry["release_blocker"]:
            raise ValueError("user follow-up became release blocker")
        if entry["verification_stage"] == "final_release" and not entry["release_blocker"]:
            raise ValueError("final Host physical gate removed")
        if entry["status"] == "PASS" and not entry.get("evidence"):
            raise ValueError("follow-up PASS without physical evidence")

    expected_counts = {
        "work_total": len(packages),
        "work_completed": sum(entry["status"] == "completed" for entry in packages),
        "capability_total": len(capability_ids),
        "resource_profile_total": len(profile_ids),
        "test_family_total": len(family_ids),
        "test_family_passed": sum(
            all(case["status"] == "PASS" for case in family["cases"])
            for family in document["test_families"]
        ),
        "test_case_total": sum(len(family["cases"]) for family in document["test_families"]),
        "m32_parity_samples": scope["sample_count"],
        "m32_parity_variants": scope["variant_count"],
    }
    if counts != expected_counts:
        raise ValueError("M32 count summary drift")
    if document.get("milestone_status") == "completed" and counts["work_completed"] != 12:
        raise ValueError("M32 completed before 12/12")


def main() -> int:
    """! @brief 초기 생성·현행 검증·고정 SDK source 검증을 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sdk-root", type=Path)
    arguments = parser.parse_args()
    sdk_root = arguments.sdk_root.resolve() if arguments.sdk_root else None
    if arguments.check:
        validate(json.loads(TARGET_PATH.read_text(encoding="utf-8")), sdk_root)
    else:
        TARGET_PATH.write_text(
            json.dumps(contract(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print("M32_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"M32_CONTRACT_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
