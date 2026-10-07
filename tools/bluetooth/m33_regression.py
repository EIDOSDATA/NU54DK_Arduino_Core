#!/usr/bin/env python3
"""! @brief M33 회귀·자원·peer 증거를 수집하고 과거 PASS의 부당 승계를 거부합니다.

@note 이 도구의 oracle 시험은 실제 Core 실행이나 실물 HIL을 대체하지 않습니다.
       snapshot은 입력과 계획만 만들며 source 원장·SDK·보드·공개 상태를 변경하지 않습니다.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m33_execution as execution

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r"[0-9a-f]{64}\Z")
REV = re.compile(r"[0-9a-f]{40}\Z")
RESOURCE_GROUPS = ("gap_gatt", "security_dfu", "iso_audio", "df_cs", "mesh",
                   "radio_coexistence", "profiles_companion", "diagnostics")
PEER_GROUPS = ("gatt", "security", "profiles", "beacons", "ancs", "ams", "mesh", "radio")
NEGATIVES = {"stale_handle", "cross_link", "key_identity", "cleanup", "bounded_reconnect", "cancel", "peer_loss"}
FAMILY_IDS = (
    "gap_links", "extended_advertising", "periodic_past", "pawr", "privacy",
    "link_control", "long_read", "reliable_write", "descriptor_authorization",
    "gatt_cache", "coc", "signed_write", "eatt", "pairing_security", "wired_oob",
    "bond_identity", "baseline_profiles", "secure_dfu", "iso", "le_audio",
    "direction_finding", "channel_sounding", "power_path", "timing_features",
    "advertising_identity", "nordic_extensions", "mesh", "radio_coexistence",
    "new_profiles", "beacons", "apple_companion", "ecosystem_templates",
    "diagnostic_templates",
)


def _campaign(runner: str, applications: tuple[str, ...], roles: tuple[str, ...],
              minimum_cycles: int, semantics: tuple[str, ...],
              verification: str = "physical_hil") -> dict:
    """! @brief 실제 기존 runner와 기능 의미를 하나의 불변 campaign으로 묶습니다. """
    return {
        "runner": runner,
        "applications": applications,
        "roles": roles,
        "minimum_cycles": minimum_cycles,
        "semantics": semantics,
        "verification": verification,
    }


## @brief W06은 이 실제 runner 집합만 기능 증거로 수락합니다.
## @note m33_raw_hil의 공통 advertising/scanning image는 의도적으로 포함하지 않습니다.
CAMPAIGNS = {
    "m28_link": _campaign(
        "tests/hil/nu54dk/m28_ble_3board.py", ("tests/zephyr/m28_ble_3board_hil",),
        ("peripheral", "mixed", "central"), 20,
        ("two_live_links", "gatt_sequence_per_link", "bounded_reconnect", "cleanup")),
    "m28_adv_pawr_privacy": _campaign(
        "tests/hil/nu54dk/m28_ble_2board.py", ("tests/zephyr/m28_ble_2board_hil",),
        ("peripheral", "central"), 20,
        ("extended_advertising_payload", "pawr_subevents", "rpa_rotation", "bond_reconnect", "cleanup")),
    "m28_periodic_past": _campaign(
        "tests/hil/nu54dk/m28_ble_3board.py", ("tests/zephyr/m28_ble_3board_hil",),
        ("peripheral", "mixed", "central"), 20,
        ("periodic_reports", "past_transfer", "sync_cleanup")),
    "m28_link_control": _campaign(
        "tests/hil/nu54dk/m28_ble_3board.py", ("tests/zephyr/m28_ble_3board_hil",),
        ("peripheral", "mixed", "central"), 20,
        ("per_link_control_request", "stale_state_rejection", "cross_link_isolation", "cleanup")),
    "m29_long_read": _campaign(
        "tests/hil/nu54dk/m29_ble_long.py", ("tests/zephyr/m29_ble_long_hil",),
        ("peripheral", "central"), 100, ("long_read_512", "mtu_247", "cleanup")),
    "m29_reliable_write": _campaign(
        "tests/hil/nu54dk/m29_ble_long_write.py", ("tests/zephyr/m29_ble_long_write_hil",),
        ("peripheral", "central"), 100, ("reliable_write_512", "cancel", "cleanup")),
    "m29_descriptor": _campaign(
        "tests/hil/nu54dk/m29_ble_descriptor.py", ("tests/zephyr/m29_ble_descriptor_hil",),
        ("peripheral", "central"), 100, ("descriptor_authorization", "read_multiple", "cleanup")),
    "m29_cache": _campaign(
        "tests/hil/nu54dk/m29_ble_cache.py", ("tests/zephyr/m29_ble_cache_hil",),
        ("peripheral", "central"), 20, ("service_changed", "cache_migration", "stale_handle", "cleanup")),
    "m29_coc": _campaign(
        "tests/hil/nu54dk/m29_ble_coc.py", ("tests/zephyr/m29_ble_coc_hil",),
        ("peripheral", "central"), 20, ("two_coc_channels", "negative_recovery", "buffer_cleanup")),
    "m29_signed_eatt": _campaign(
        "tests/hil/nu54dk/m29_ble_signed_eatt.py", ("tests/zephyr/m29_ble_signed_eatt_hil",),
        ("peripheral", "central"), 20, ("signed_write", "replay_rejection", "two_eatt_bearers", "cleanup")),
    "m29_multi": _campaign(
        "tests/hil/nu54dk/m29_ble_multi.py", ("tests/zephyr/m29_ble_multi_hil",),
        ("peripheral", "mixed", "central"), 20,
        ("two_live_links", "gatt_and_coc_traffic", "buffer_cleanup")),
    "m30_pair": _campaign(
        "tests/hil/nu54dk/m30_ble_pair.py", ("tests/zephyr/m30_ble_pair_hil",),
        ("peripheral", "central"), 50, ("five_io_capabilities", "mitm_policy", "key_identity", "cleanup")),
    "m30_oob": _campaign(
        "tests/hil/nu54dk/m30_ble_oob.py", ("tests/zephyr/m30_ble_oob_hil",),
        ("peripheral", "central"), 20, ("wired_oob", "mismatch_rejection", "mitm", "cleanup")),
    "m30_bond": _campaign(
        "tests/hil/nu54dk/m30_ble_bond.py", ("tests/zephyr/m30_ble_bond_hil",),
        ("peripheral", "central"), 20, ("bond_migration", "privacy_rotation", "stale_key", "reboot_restore", "cleanup")),
    "m30_profiles": _campaign(
        "tests/hil/nu54dk/m30_ble_profile.py", ("tests/zephyr/m30_ble_profile_hil",),
        ("peripheral", "central"), 100, ("seven_profiles", "typed_payload", "security", "cleanup")),
    "m30_dfu": _campaign(
        "tests/hil/nu54dk/m30_ble_dfu.py", ("tests/zephyr/m30_ble_dfu_hil",),
        ("peripheral", "central"), 10,
        ("signed_update", "wrong_key_rejection", "rollback", "secondary_slot_cleanup")),
    "m30_multi": _campaign(
        "tests/hil/nu54dk/m30_ble_multi.py", ("tests/zephyr/m30_ble_multi_hil",),
        ("peripheral", "mixed", "central"), 20,
        ("two_secure_links", "cross_link_isolation", "key_identity", "cleanup")),
    "m31_iso_cis": _campaign(
        "tests/hil/nu54dk/m31_iso_cis_run.py", ("tests/zephyr/m31_iso_cis_hil",),
        ("central", "peripheral"), 20, ("cis_sdu", "active_acl_teardown", "bounded_cleanup")),
    "m33_cis_acl_risk": _campaign(
        "tests/hil/nu54dk/m33_cis_acl_risk_run.py",
        ("tests/zephyr/m31_iso_cis_hil",),
        ("central", "peripheral"), 20,
        ("active_cis", "nse_gt_one", "cpu_load", "acl_first_teardown", "cleanup")),
    "m31_iso_bis": _campaign(
        "tests/hil/nu54dk/m31_iso_bis_run.py", ("tests/zephyr/m31_iso_bis_hil",),
        ("source", "receiver"), 20,
        ("bis_sdu", "wrong_broadcast_code", "sync_loss", "bounded_packet_loss", "cleanup")),
    "m31_iso_combined": _campaign(
        "tests/hil/nu54dk/m31_iso_combined_run.py", ("tests/zephyr/m31_iso_combined_hil",),
        ("peer", "combined", "receiver"), 20, ("simultaneous_cis_bis", "buffer_cleanup")),
    "m31_bap_duplex": _campaign(
        "tests/hil/nu54dk/m31_audio_bap_duplex_cycle_run.py",
        ("libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexClient",
         "libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexServer"),
        ("client", "server"), 20, ("bap_unicast_duplex", "codec_qos_state", "cleanup")),
    "m31_df_tx": _campaign(
        "tests/hil/nu54dk/m31_df_beacon_run.py",
        ("libraries/NUCODE_BLE_DirectionFinding/examples/CteBeacon",),
        ("beacon",), 20, ("connectionless_cte_tx", "controller_acceptance", "cleanup")),
    "m31_cs_ras": _campaign(
        "tests/hil/nu54dk/m31_cs_ras_pair_run.py",
        ("libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator",
         "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector"),
        ("initiator", "reflector"), 100,
        ("ras_procedures", "acl_teardown", "peer_loss", "radio_schedule", "cleanup")),
    "m33_cs_acl_radio_risk": _campaign(
        "tests/hil/nu54dk/m33_cs_acl_radio_risk_run.py",
        ("tests/arduino-cli/p2_cs_initiator",
         "tests/arduino-cli/p2_cs_reflector"),
        ("initiator", "reflector"), 20,
        ("active_cs", "scan_overlap", "acl_teardown", "radio_schedule",
         "bounded_reconnect", "cleanup")),
    "m31_cs_negative_stale_key": _campaign(
        "tests/hil/nu54dk/m31_cs_stale_key_run.py",
        ("tests/hil/nu54dk/fixtures/RasStaleKeyInitiator",
         "tests/hil/nu54dk/fixtures/RasStaleKeyReflector"),
        ("initiator", "reflector"), 1,
        ("stale_key", "security_rejection", "no_ras_progress", "cleanup")),
    "m31_cs_negative_insecure_read": _campaign(
        "tests/hil/nu54dk/m31_cs_insecure_read_run.py",
        ("tests/hil/nu54dk/fixtures/RasInsecureRead",
         "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector"),
        ("client", "reflector"), 20,
        ("insecure_read", "same_acl", "security_rejection", "cleanup")),
    "m31_cs_negative_wrong_peer": _campaign(
        "tests/hil/nu54dk/m31_cs_wrong_peer_run.py",
        ("libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator",
         "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector",
         "tests/hil/nu54dk/fixtures/RasWrongPeer"),
        ("initiator", "reflector", "wrong_peer"), 100,
        ("wrong_peer", "service_identity", "ras_procedures", "cleanup")),
    "m31_cs_negative_missing_service": _campaign(
        "tests/hil/nu54dk/m31_cs_missing_service_run.py",
        ("libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator",
         "tests/hil/nu54dk/fixtures/RasMissingService"),
        ("initiator", "missing_service_peer"), 20,
        ("missing_service", "gatt_rejection", "no_ras_progress", "cleanup")),
    "m32_power": _campaign(
        "tests/hil/nu54dk/m32_power_path_run.py", ("tests/zephyr/m32_ble_power_hil",),
        ("central", "peripheral"), 20, ("power_control", "path_loss", "cleanup")),
    "m32_timing": _campaign(
        "tests/hil/nu54dk/m32_timing_feature_run.py", ("tests/zephyr/m32_ble_timing_hil",),
        ("central", "peripheral"), 20,
        ("subrating_ack_boundary", "latency_timeout", "sca", "frame_space", "bounded_reconnect")),
    "m32_advertising": _campaign(
        "tests/hil/nu54dk/m32_advertising_run.py", ("tests/zephyr/m32_ble_advertising_hil",),
        ("advertiser_a", "advertiser_b", "scanner"), 20,
        ("advertising_sets", "identity_isolation", "cleanup")),
    "m32_privacy": _campaign(
        "tests/hil/nu54dk/m32_privacy_run.py", ("tests/zephyr/m32_ble_privacy_hil",),
        ("identity_a", "identity_b", "peer"), 20, ("identity_resolution", "rpa_rotation", "cleanup")),
    "m32_ead": _campaign(
        "tests/hil/nu54dk/m32_ead_run.py", ("tests/zephyr/m32_ble_ead_hil",),
        ("advertiser", "scanner"), 20, ("encrypted_advertising_data", "wrong_key_rejection", "cleanup")),
    "m32_nordic": _campaign(
        "tests/hil/nu54dk/m32_nordic_extension_run.py", ("tests/zephyr/m32_ble_nordic_hil",),
        ("central", "peripheral"), 20, ("nordic_extensions", "event_counter", "cleanup")),
    "m32_mesh": _campaign(
        "tests/hil/nu54dk/m32_mesh_run.py", ("tests/zephyr/m32_mesh_hil",),
        ("provisioner", "node_a", "node_b"), 20,
        ("provision_two_nodes", "mesh_security", "lpn_friend_clear", "rejoin", "cleanup")),
    "m32_mesh_management": _campaign(
        "tests/hil/nu54dk/m32_mesh_management_run.py", ("tests/zephyr/m32_mesh_management_hil",),
        ("client", "server", "target"), 20, ("mesh_management", "target_isolation", "cleanup")),
    "m32_mesh_update": _campaign(
        "tests/hil/nu54dk/m32_mesh_update_run.py", ("tests/zephyr/m32_mesh_update_hil",),
        ("blob_client", "target_a", "target_b"), 20, ("blob_transfer", "target_recovery", "cleanup")),
    "m32_mesh_dfu": _campaign(
        "tests/hil/nu54dk/m32_mesh_dfu_run.py", ("tests/zephyr/m32_mesh_dfu_hil",),
        ("distributor", "target_a", "target_b"), 10,
        ("signed_mesh_dfu", "rollback", "active_watchdog_condition", "cleanup")),
    "m32_standalone_radio": _campaign(
        "tests/hil/nu54dk/m32_standalone_radio_run.py",
        ("tests/zephyr/m32_radio154_hil", "tests/zephyr/m32_esb_hil"),
        ("dut", "peer"), 20, ("ieee802154_packets", "esb_packets", "role_swap", "cleanup")),
    "m32_coexistence": _campaign(
        "tests/hil/nu54dk/m32_coexistence_run.py", ("tests/zephyr/m32_coexistence_hil",),
        ("dut", "radio", "ble"), 20,
        ("ble_mesh", "ble_ieee802154", "ble_esb", "packet_counters", "cleanup")),
    "m33_profiles_standard": _campaign(
        "tests/hil/nu54dk/m33_profile_campaign.py", ("tests/zephyr/m33_profile_hil",),
        ("server", "client", "watcher"), 20,
        ("standard_profiles", "bms_reboot_restore", "scoped_bond_delete", "cleanup")),
    "m33_profiles_native": _campaign(
        "tests/hil/nu54dk/m33_profile_campaign.py", ("tests/zephyr/m33_profile_hil",),
        ("server", "client", "second_peer"), 20,
        ("native_fresh_restore", "native_second_peer", "key_identity", "cleanup")),
    "m33_beacons": _campaign(
        "tests/hil/nu54dk/m33_beacon_run.py", ("tests/zephyr/m33_ble_beacon_hil",),
        ("advertiser", "observer"), 20,
        ("ibeacon", "eddystone", "bthome", "semantic_decode", "cleanup")),
    "m33_ecosystem": _campaign(
        "tools/bluetooth/m33_ecosystem_hil.py", ("tests/zephyr/m33_ecosystem_hil",),
        ("client", "peer"), 20,
        ("ancs", "ams", "access_denied", "malformed_peer", "bonded_reconnect", "cleanup")),
    "m33_ecosystem_templates": _campaign(
        "libraries/NUCODE_BLE_Companion/tools/m33_template_build.py",
        ("libraries/NUCODE_BLE_Companion/templates",), (), 4,
        ("credential_fail_closed", "fast_pair_input", "fast_pair_locator", "enocean_mds_build"),
        "build_semantic"),
    "m33_diagnostics_dtm": _campaign(
        "tools/bluetooth/m33_diagnostics_campaign.py", ("templates/bluetooth/diagnostics/dtm",),
        ("tx", "rx"), 24, ("dtm_tx_rx_role_swap", "packet_count", "negative", "cleanup")),
    "m33_diagnostics_build": _campaign(
        "tools/bluetooth/m33_diagnostics.py",
        ("templates/bluetooth/diagnostics/controller", "templates/bluetooth/diagnostics/scan_request"),
        (), 2, ("hci_transport_build", "exclusive_owner", "external_transport_not_run"),
        "build_semantic"),
}

FAMILY_CAMPAIGNS = {
    "gap_links": ("m28_link",),
    "extended_advertising": ("m28_adv_pawr_privacy",),
    "periodic_past": ("m28_periodic_past",),
    "pawr": ("m28_adv_pawr_privacy",),
    "privacy": ("m28_adv_pawr_privacy",),
    "link_control": ("m28_link_control",),
    "long_read": ("m29_long_read",),
    "reliable_write": ("m29_reliable_write",),
    "descriptor_authorization": ("m29_descriptor",),
    "gatt_cache": ("m29_cache",),
    "coc": ("m29_coc",),
    "signed_write": ("m29_signed_eatt",),
    "eatt": ("m29_signed_eatt",),
    "pairing_security": ("m30_pair",),
    "wired_oob": ("m30_oob",),
    "bond_identity": ("m30_bond",),
    "baseline_profiles": ("m30_profiles",),
    "secure_dfu": ("m30_dfu",),
    "iso": ("m31_iso_cis", "m33_cis_acl_risk", "m31_iso_bis", "m31_iso_combined"),
    "le_audio": ("m31_bap_duplex",),
    "direction_finding": ("m31_df_tx",),
    "channel_sounding": (
        "m31_cs_ras", "m33_cs_acl_radio_risk", "m31_cs_negative_stale_key",
        "m31_cs_negative_insecure_read", "m31_cs_negative_wrong_peer",
        "m31_cs_negative_missing_service",
    ),
    "power_path": ("m32_power",),
    "timing_features": ("m32_timing",),
    "advertising_identity": ("m32_advertising", "m32_privacy", "m32_ead"),
    "nordic_extensions": ("m32_nordic",),
    "mesh": ("m32_mesh", "m32_mesh_management", "m32_mesh_update", "m32_mesh_dfu"),
    "radio_coexistence": ("m32_standalone_radio", "m32_coexistence"),
    "new_profiles": ("m33_profiles_standard", "m33_profiles_native"),
    "beacons": ("m33_beacons",),
    "apple_companion": ("m33_ecosystem",),
    "ecosystem_templates": ("m33_ecosystem_templates",),
    "diagnostic_templates": ("m33_diagnostics_dtm", "m33_diagnostics_build"),
}

RESOURCE_CAMPAIGNS = {
    "gap_gatt": ("m29_multi", "m28_periodic_past", "m29_signed_eatt"),
    "security_dfu": ("m30_multi", "m30_dfu"),
    "iso_audio": ("m31_iso_combined", "m31_bap_duplex", "m33_cis_acl_risk"),
    "df_cs": ("m31_df_tx", "m31_cs_ras", "m33_cs_acl_radio_risk"),
    "mesh": ("m32_mesh", "m32_mesh_update", "m32_mesh_dfu"),
    "radio_coexistence": ("m32_standalone_radio", "m32_coexistence"),
    "profiles_companion": ("m33_profiles_standard", "m33_profiles_native", "m33_ecosystem"),
    "diagnostics": ("m33_diagnostics_dtm", "m33_diagnostics_build"),
}

AUTOMATIC_PEER_CAMPAIGNS = {
    "gatt": ("m29_multi",),
    "security": ("m30_pair", "m30_bond"),
    "profiles": ("m33_profiles_standard", "m33_profiles_native"),
    "beacons": ("m33_beacons",),
    "ancs": ("m33_ecosystem",),
    "ams": ("m33_ecosystem",),
    "mesh": ("m32_mesh", "m32_mesh_management"),
    "radio": ("m32_standalone_radio", "m32_coexistence"),
}

CAMPAIGN_REGISTRIES = {
    "families": FAMILY_CAMPAIGNS,
    "resources": RESOURCE_CAMPAIGNS,
    "automatic_peers": AUTOMATIC_PEER_CAMPAIGNS,
}
FORBIDDEN_GENERIC_APPLICATION = "tests/zephyr/m32_regression_soak_hil/m33_raw_hil"
SDK_RISK_CAMPAIGNS = {
    "DRGN-29228": {
        "campaigns": ("m33_diagnostics_dtm",),
        "condition": "very_noisy_dtm_rx_assert",
        "allowed_status": ("PASS", "CONDITION_NOT_MET"),
    },
    "DRGN-29270": {
        "campaigns": ("m32_timing",),
        "condition": "subrate_latency_timeout_ack_order",
        "allowed_status": ("PASS",),
    },
    "DRGN-29446": {
        "campaigns": ("m33_cis_acl_risk",),
        "condition": "active_cis_acl_termination_under_load",
        "allowed_status": ("PASS",),
    },
    "DRGN-29320": {
        "campaigns": ("m31_iso_bis",),
        "condition": "bis_packet_loss_in_very_noisy_environment",
        "allowed_status": ("PASS", "CONDITION_NOT_MET"),
    },
    "DRGN-29669": {
        "campaigns": ("m33_cs_acl_radio_risk",),
        "condition": "cs_acl_release_with_radio_scheduling",
        "allowed_status": ("PASS",),
    },
    "MESH_LPN_FRIEND_CLEAR": {
        "campaigns": ("m32_mesh",),
        "condition": "ttl_zero_friend_clear_confirm_and_rejoin",
        "allowed_status": ("PASS",),
    },
    "MCUBOOT_ACTIVE_WATCHDOG": {
        "campaigns": ("m32_mesh_dfu",),
        "condition": "watchdog_actively_started_during_update",
        "allowed_status": ("PASS", "CONDITION_NOT_MET"),
    },
}
QUALIFICATION_REFERENCE = (
    "https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54l15/page/comp/"
    "nrf54l15/nrf54l15_ble_qdid_qual_matrix.html"
)
QUALIFICATION_COMPONENTS = {
    "host": "PLANNED_NO_DN",
    "controller": "PLANNED_NO_DN",
    "mesh": "NOT_LISTED_NO_DN",
}
MATRIX_MANIFEST_NAME = "m33-campaign-matrix.json"
## @brief 33개 family는 work package 분모와 별개이며 기존 구현 시험을 다시 실행하는 경로를 명시합니다.
FAMILIES = {
    "gap_links": ("M28", "test_m28_ble_links.py"),
    "extended_advertising": ("M28", "test_m28_ble_extended.py"),
    "periodic_past": ("M28", "test_m28_ble_periodic.py"),
    "pawr": ("M28", "test_m28_ble_pawr.py"),
    "privacy": ("M28", "test_m28_ble_privacy_control.py"),
    "link_control": ("M28", "test_m28_ble_3board_hil.py"),
    "long_read": ("M29", "test_m29_ble_long_read.py"),
    "reliable_write": ("M29", "test_m29_ble_long_write.py"),
    "descriptor_authorization": ("M29", "test_m29_ble_descriptor.py"),
    "gatt_cache": ("M29", "test_m29_ble_cache.py"),
    "coc": ("M29", "test_m29_ble_coc.py"),
    "signed_write": ("M29", "test_m29_ble_signed_eatt.py"),
    "eatt": ("M29", "test_m29_ble_signed_eatt_parser.py"),
    "pairing_security": ("M30", "test_m30_ble_security.py"),
    "wired_oob": ("M30", "test_m30_ble_oob_bond.py"),
    "bond_identity": ("M30", "test_m30_ble_bond_hil.py"),
    "baseline_profiles": ("M30", "test_m30_ble_profile_hil.py"),
    "secure_dfu": ("M30", "test_m30_ble_dfu.py"),
    "iso": ("M31", "test_m31_iso_combined.py"),
    "le_audio": ("M31", "test_m31_audio_lc3.py"),
    "direction_finding": ("M31", "test_m31_df_beacon_config.py"),
    "channel_sounding": ("M31", "test_m31_cs_stale_key.py"),
    "power_path": ("M32", "test_r12_ble_gap.py"),
    "timing_features": ("M32", "test_r12_ble_gap.py"),
    "advertising_identity": ("M32", "test_m32_ble_advertising.py"),
    "nordic_extensions": ("M32", "test_m32_ble_nordic.py"),
    "mesh": ("M32", "test_m32_mesh_management.py"),
    "radio_coexistence": ("M32", "test_m32_coexistence.py"),
    "new_profiles": ("M33-W02", "test_m33_profile_runtime.py"),
    "beacons": ("M33-W02", "test_m33_beacon_codec.py"),
    "apple_companion": ("M33-W03", "test_m33_ecosystem_codec.py"),
    "ecosystem_templates": ("M33-W03", "test_m33_ecosystem_templates.py"),
    "diagnostic_templates": ("M33-W04", "test_m33_diagnostics.py"),
}
COUNT_SYMBOLS = {
    "connections": "CONFIG_BT_MAX_CONN",
    "advertising_sets": "CONFIG_BT_EXT_ADV_MAX_ADV_SET",
    "periodic_syncs": "CONFIG_BT_PER_ADV_SYNC_MAX",
    "iso_channels": "CONFIG_BT_ISO_MAX_CHAN",
    "coc_channels": None,
    "coc_rx_records_per_channel": None,
    "coc_tx_buffers": None,
    "eatt_bearers": "CONFIG_BT_EATT_MAX",
    "cs_connections": "CONFIG_BT_MAX_CONN",
    "mesh_nodes": "CONFIG_BT_MESH_CDB_NODE_COUNT",
    "acl_tx_buffers": "CONFIG_BT_BUF_ACL_TX_COUNT",
    "iso_tx_buffers": "CONFIG_BT_ISO_TX_BUF_COUNT",
    "iso_rx_buffers": "CONFIG_BT_ISO_RX_BUF_COUNT",
}
RESOURCE_MEASUREMENT_SYMBOLS = {
    field: f"m33_w06_measure_{field}" for field in (
        "ram_bytes", "rram_bytes", "minimum_stack_margin_bytes", "allocation_failures",
        "resource_leaks", "pending_links", "outstanding_buffers",
        "sdc_pool_alignment_bytes",
    )
}
RESOURCE_ROLE_CONFIG_SYMBOLS = {
    "resource_a": "CONFIG_NUCODE_M33_RESOURCE_ROLE_A",
    "resource_b": "CONFIG_NUCODE_M33_RESOURCE_ROLE_B",
    "resource_c": "CONFIG_NUCODE_M33_RESOURCE_ROLE_C",
}
EXCLUSIVE_RADIOS = {"dtm", "raw_hci", "ieee802154", "esb"}
HOST_TESTS = sorted({value[1] for value in FAMILIES.values()} |
                    {"test_r12_ble_gatt.py", "test_r12_ble_l2cap.py", "test_r12_ble_security.py",
                     "test_m28_ble_2board_hil.py", "test_m29_ble_multi.py",
                     "test_m29_ble_multi_parser.py", "test_m29_ble_cache_parser.py", "test_m30_ble_multi.py",
                     "test_m31_iso_bis_negative.py", "test_m32_coexistence_hil.py",
                     "test_m32_mesh_dfu_hil.py", "test_m32_mesh_hil.py",
                     "test_m32_radio_attestation.py", "test_m32_standalone_radio_hil.py",
                     "test_m30_native_attestation.py",
                     "test_m31_audio_bap_native_pair_run.py",
                     "test_m31_cs_negative_attestation.py",
                     "test_m31_iso_combined_build_provenance.py",
                     "test_m33_ecosystem_hil.py", "test_m33_modern_direct_attestation.py",
                     "test_m33_flat_build_evidence.py",
                     "test_m33_diagnostics_campaign.py", "test_m33_profile_campaign.py",
                     "test_m33_sdk_risk_hil.py",
                     "test_m33_w06_artifacts.py",
                     "test_m33_w06_pipeline.py",
                     "test_m33_w06_runtime_fixture.py",
                     "test_m33_execution.py",
                     "test_build_matrix_runner.py",
                     "test_m32_regression_soak_hil.py", "test_m33_readiness_contract.py",
                     "test_m33_regression.py"})
## @brief verbose test ID 정렬 목록의 개수와 SHA-256을 source와 독립적으로 고정합니다.
HOST_TEST_EXPECTATIONS = {
    "test_build_matrix_runner.py": (11, "376a2bd3790d7dfa6da74dfe5a08077b475f518e1e3f328394986f4fe14af469"),
    "test_m28_ble_2board_hil.py": (15, "200340053eefa1211b0fb971596f18f1c440cf175c1bba48127338bc932f4ed7"),
    "test_m28_ble_3board_hil.py": (17, "9702191cccf87eaf05d98705b6b70f49e3883d4924bda6f446911f236bca3a8c"),
    "test_m28_ble_extended.py": (2, "b08f318e2c842225295dcbbd253ab9e1e0dd7c43791d7b477d5387b87e1b3f68"),
    "test_m28_ble_links.py": (6, "6de3ca2ef62ba0f1068d8469692ed7726fe23b811eee4300a3711b11284eea05"),
    "test_m28_ble_pawr.py": (2, "b5bc3120e739f2e4538be03b494abd5cb195bb67f13b6a94ba0886ce57095f8e"),
    "test_m28_ble_periodic.py": (2, "cc60df29d91d7621963b65632f752ba8683efbf7035e403c29f160fcaf07f304"),
    "test_m28_ble_privacy_control.py": (2, "9ffedf2e303beae968ce0ecf16f95841dc4502fa1500c92b0a282dc7ba046cf8"),
    "test_m29_ble_cache.py": (10, "7e48465b8553798e0d52872fc106cca7a1186f9a59e3cbfb1fe0b0544c620abf"),
    "test_m29_ble_cache_parser.py": (16, "664cf8749ef33dc0141da0f9c422dd22a9d20fb7c8ef6ec197b5d59d8e0ecda5"),
    "test_m29_ble_coc.py": (7, "8af5cc543dd5dbe77f0dcc922bf7b37f574d078c7d92a370e85a52bb8cf4174f"),
    "test_m29_ble_descriptor.py": (8, "38b60b64ef79eeb0652c5e184d00c0452e58933169c56fbe2c1a7a4b408c7fb9"),
    "test_m29_ble_long_read.py": (8, "0d96e0c38e0be0f49bc8f825f2a7686dccd463ae9b8ea6602b1b39717ff366b3"),
    "test_m29_ble_long_write.py": (6, "969953a7b9bebb2e214db08143f39e2eca80731fc40528b934e991fc17a62720"),
    "test_m29_ble_multi.py": (8, "42ca94eb5de2a9777cbca18fbc76b67e8d73a362f6199f1e42903a3afa0dfc76"),
    "test_m29_ble_multi_parser.py": (17, "70785a96d2b35d27018342b27970cc54b5e1ca40fd1ac9531bd559e06bb04fc7"),
    "test_m29_ble_signed_eatt.py": (17, "541d9145af9f231568cdacf71265782c4954b29074bbe5f8fd14c2debab7eb53"),
    "test_m29_ble_signed_eatt_parser.py": (16, "735312243214d58c246b17ccc179666987a0f0d3e5a5976ed629c177b50f42f3"),
    "test_m30_ble_bond_hil.py": (5, "1206858c4108f47c01e6d524ae92571c47feef3441d6f9fdfdbda84336c79804"),
    "test_m30_ble_dfu.py": (10, "4791099713f061232495c2026a76b993af24fcf50e659ec9154b7cce527219a2"),
    "test_m30_ble_oob_bond.py": (8, "e39f964408267c05d27aced6da8a3e693e49231d0154c789d6d4c35f7006a2c5"),
    "test_m30_ble_profile_hil.py": (6, "d7ee2fc043aa3b6df83605dd3e9b1893bbf3201938ae66304f1fb48a1bf2acb0"),
    "test_m30_ble_multi.py": (8, "ab4d801b87a3feb15db73c0ab98f4972f054550f91f695b837d446f6d9d7720b"),
    "test_m30_ble_security.py": (4, "7ff9b08c4412bff48fb8c85f41a746b6bd19933e6d19c3aa80e5c2365d037bb9"),
    "test_m30_native_attestation.py": (10, "ac412d00668a6f88ed01fdf3f974a0aa08c1790ee374c3c698e4275f7815d4c7"),
    "test_m31_audio_lc3.py": (3, "154edf0d52e77f445997dd4e5bfb3864cd5b757a45c8a2c701d97967fdbc3a87"),
    "test_m31_audio_bap_native_pair_run.py": (1, "583fc0107ed192ed4762c3460e75229a7015f590425c678f30331e494aad7aca"),
    "test_m31_cs_stale_key.py": (6, "d46cc053ce7050b9703eb1c5e581d9e3efa871879b830368dce2c2b20dbaa4c0"),
    "test_m31_cs_negative_attestation.py": (6, "fb6343523a6e10d29faeb47021059e69d00dbffd1bc65d45ffafab8da9853d6c"),
    "test_m31_df_beacon_config.py": (1, "bbe8dc2cf28193e0a22c85a373eecae8ad592e1fd7526eaa357489b50c346102"),
    "test_m31_iso_bis_negative.py": (4, "839b6862827c34cb9d38292f79c63e7e1baaa161d1ae8aa2bc078ae0dfbdc496"),
    "test_m31_iso_combined.py": (4, "52255144829cf6b412aad04bbf1608af740d1826721b4fb78f527d8f13d631a4"),
    "test_m31_iso_combined_build_provenance.py": (5, "61d1003af6e6372ef403aece07315b2dcf8d0caf760eb9ffd63e386edad116f6"),
    "test_m32_ble_advertising.py": (2, "4d2070282b6fb206c9d9a3d1021af70f8e236d9119b68054a89e561610b7ae04"),
    "test_m32_ble_nordic.py": (1, "a522b2993ed2c16ed5df9215115e4f7978eeb7533e3f51b2018392f7b282ccba"),
    "test_m32_coexistence.py": (6, "353e2ad06054049a5cb9ad502bb28299e1fb000ac0874833cbbe6419037705d0"),
    "test_m32_coexistence_hil.py": (6, "af0451d5eee9802420b35765c2305a79515f437def51336aa555232b56140281"),
    "test_m32_mesh_dfu_hil.py": (12, "95cf492beb73e2aadfe227c7ca66407bd7349720faae69c8b0c32170a6c58566"),
    "test_m32_mesh_hil.py": (13, "79b4ff072e4a068fbfdacc973dbbd3b975af1e155a7de700dfb3bb2ed3e408ba"),
    "test_m32_mesh_management.py": (4, "3f1d108e3adebc29fc6264ef9bffc037edc89b12cb1df78619c1fb36f23d5efa"),
    "test_m32_radio_attestation.py": (5, "266b9501383403943fabc9a37c926a0e4d87cb991c600c904192f532cf553d09"),
    "test_m32_regression_soak_hil.py": (8, "ae0f6e6a230456f6acc8dd659429fca59c6d6891e7e0d877c87d191bc00045e1"),
    "test_m32_standalone_radio_hil.py": (3, "aefb754280edb64cb63135c19f83e55e5be916e3df0d9c3bf1e3f163cb768ec0"),
    "test_m33_beacon_codec.py": (1, "17ca5b67be018c6265b62719596e7b5032fc4b20c9fafae3149bd89da176086c"),
    "test_m33_diagnostics.py": (11, "8769c80c9722e21962736cbbd268568929466a4bae98ec994857064d70f132c2"),
    "test_m33_diagnostics_campaign.py": (3, "8d00ae57da9d42424d9e40ae2a9c16d0435b006351a7324ba3e41f66607bdb00"),
    "test_m33_ecosystem_codec.py": (1, "5a773dfd6dc927eadcba6fdb737336cb6a9a29f2a6cea22a00374e889cb46698"),
    "test_m33_ecosystem_hil.py": (8, "4dd38126b1ce70685444a91e6a4fbab4e9b9e008f40d7913055d13e3524e9322"),
    "test_m33_ecosystem_templates.py": (4, "2ac11eed5d998d58dfd99ab1fd79a59de2dabbee31ee254191b1a2326a25e8a7"),
    "test_m33_flat_build_evidence.py": (7, "a961893a3f5929129ac46fb801066a7df758e3b90e97b07305c22460399e8ca8"),
    "test_m33_modern_direct_attestation.py": (5, "f56fb1c93279dc749af8e478bd14b5ca43614b224030467f8070a11520b087f0"),
    "test_m33_profile_runtime.py": (1, "fe0c7a7a50d6cb201f0bf5ff912c8b5bfb1a227c13bc3784b853d35c11d3295c"),
    "test_m33_profile_campaign.py": (4, "5eb631b4f1edc9bf67e251c4bd45b3203beed26765a5b3115587c08a5c833a18"),
    "test_m33_readiness_contract.py": (31, "a0c78cd5b0f2357384456465c1ac21077b55ead8bb8277e8dabb1821cb22c36c"),
    "test_m33_regression.py": (75, "54bbbca5f902fa5e0be74eb6ba891b71664e3d0d89107efd0edfdaa1e098f651"),
    "test_m33_sdk_risk_hil.py": (19, "cc8720169bcf3076bd6f2c9cb73d3f039fd6d92478b052fceadc804eb21d71b9"),
    "test_m33_w06_artifacts.py": (43, "e51b08b2ce8459ffdd56d3d85c2fd065db428ea1c557abd6f94fe1dc97ee784b"),
    "test_m33_w06_pipeline.py": (20, "05d0048220c6bb8d7637441731a200a755f3ee2206f5b7dd9b33b165cfe223a2"),
    "test_m33_w06_runtime_fixture.py": (15, "ed6c8c1aeaab847d4820bf0bd61f7e1535137c464843bdf431d5878d986cc7c7"),
    "test_m33_execution.py": (21, "e4e8f1fe120c1a0d6d3adaa9fe0bdf8aa84750233a1a25519f8c5b823efc0476"),
    "test_r12_ble_gap.py": (1, "b0be325128d4c2af4bf954768dc153d8ee2b9b3f53cf62863267b2c1a13f34bc"),
    "test_r12_ble_gatt.py": (1, "52207f45635a567329e70f79a2bf081ca654099d90e9c118f0027995b962958a"),
    "test_r12_ble_l2cap.py": (1, "4edad75a45b44ccd3c7ae55d94a212dc76549fe31e2baa7fb18121213ed06992"),
    "test_r12_ble_security.py": (1, "b6ea1a516a678597759422545ed361b1aa9d9eacec0c6e422f4293e62d4fd9b0"),
}
if set(FAMILY_IDS) != set(FAMILIES) or len(FAMILY_IDS) != 33:
    raise RuntimeError("independent family ID catalog drift")
if set(FAMILY_CAMPAIGNS) != set(FAMILY_IDS):
    raise RuntimeError("actual family campaign catalog drift")
if set(RESOURCE_CAMPAIGNS) != set(RESOURCE_GROUPS):
    raise RuntimeError("actual resource campaign catalog drift")
if set(AUTOMATIC_PEER_CAMPAIGNS) != set(PEER_GROUPS):
    raise RuntimeError("actual peer campaign catalog drift")
if any(campaign not in CAMPAIGNS for registry in CAMPAIGN_REGISTRIES.values()
       for campaigns in registry.values() for campaign in campaigns):
    raise RuntimeError("unknown actual campaign route")
if any(FORBIDDEN_GENERIC_APPLICATION in definition["applications"]
       for definition in CAMPAIGNS.values()):
    raise RuntimeError("generic raw application cannot be an actual campaign")
if set(HOST_TEST_EXPECTATIONS) != set(HOST_TESTS):
    raise RuntimeError("independent Host test contract drift")
FAMILY_DENOMINATORS = {identifier: 1 for identifier in FAMILY_IDS}
RESOURCE_DENOMINATORS = {identifier: 1 for identifier in RESOURCE_GROUPS}
AUTOMATIC_PEER_DENOMINATORS = {identifier: 20 for identifier in PEER_GROUPS}
RAW_DENOMINATORS = {
    "families": FAMILY_DENOMINATORS,
    "resources": RESOURCE_DENOMINATORS,
    "automatic_peers": AUTOMATIC_PEER_DENOMINATORS,
}
RAW_SCOPES = {
    "families": "current_functional_hil",
    "resources": "current_resource_measurement",
    "automatic_peers": "current_scripted_peer",
}
RAW_EVIDENCE_KINDS = {
    "families": "m33_family_hil_result",
    "resources": "m33_resource_hil_result",
    "automatic_peers": "m33_automatic_peer_hil_result",
}
RAW_PRODUCER_CONTRACTS = {
    "families": {
        "name": "m33-family-physical-hil-v2",
        "route": "tests/hil/nu54dk/m33_regression_run.py",
        "protocol": "NUCODE_M33_W06_FAMILY_V2",
        "roles": ("peripheral", "mixed", "central"),
        "minimum_distinct_images": 3,
    },
    "resources": {
        "name": "m33-resource-physical-hil-v2",
        "route": "tests/hil/nu54dk/m33_regression_run.py",
        "protocol": "NUCODE_M33_W06_RESOURCE_V2",
        "roles": ("resource_a", "resource_b", "resource_c"),
        "minimum_distinct_images": 3,
    },
    "automatic_peers": {
        "name": "m33-automatic-peer-physical-hil-v2",
        "route": "tests/hil/nu54dk/m33_regression_run.py",
        "protocol": "NUCODE_M33_W06_AUTOMATIC_PEER_V2",
        "roles": ("dut", "scripted_peer"),
        "minimum_distinct_images": 2,
    },
}
RAW_TEST_ROUTES = {
    "families": {identifier: f"tests/host/{FAMILIES[identifier][1]}" for identifier in FAMILY_IDS},
    "resources": {identifier: f"M33-RESOURCE-01:{identifier}" for identifier in RESOURCE_GROUPS},
    "automatic_peers": {identifier: f"M33-INTEROP-01:{identifier}" for identifier in PEER_GROUPS},
}
SOURCE_MANIFEST_FIELDS = (
    "core_revision", "board_revision", "ncs_revision", "zephyr_revision",
    "core_source_sha256", "application_source_sha256", "board_source_sha256",
    "firmware_source_sha256", "application_cmake_sha256",
    "application_config_sha256",
)
PEER_REASON_CODES = {
    "PASS": {"observed_pass"},
    "FAIL": {"protocol_failure", "security_failure", "timeout", "state_mismatch"},
    "PEER_UNSUPPORTED": {"peer_service_absent", "peer_platform_unsupported",
                         "peer_vendor_documented_unsupported"},
    "CORE_UNSUPPORTED": {"core_sdk_unsupported", "core_controller_unsupported",
                         "core_board_not_applicable"},
}
SUPPORT_DISCOVERY = {"physical_discovery", "official_peer_documentation",
                     "scripted_discovery", "host_runtime"}


def require(condition: bool, message: str) -> None:
    """! @brief 예상하지 못한 입력은 성공으로 복구하지 않고 거부합니다. """
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    """! @brief 실제 evidence byte의 SHA-256을 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_path_digest(path: Path) -> str:
    """! @brief campaign source 파일 또는 directory tree를 경로와 byte 순서로 hash합니다. """
    require(path.exists(), "campaign source path missing")
    if path.is_file():
        return digest(path)
    require(path.is_dir(), "campaign source path is not a file or directory")
    hasher = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    require(files, "campaign source directory is empty")
    for item in files:
        relative = item.relative_to(path).as_posix().encode("utf-8")
        hasher.update(len(relative).to_bytes(4, "big"))
        hasher.update(relative)
        data = item.read_bytes()
        hasher.update(len(data).to_bytes(8, "big"))
        hasher.update(data)
    return hasher.hexdigest()


def integer(value, minimum=0, maximum=2**31 - 1) -> bool:
    """! @brief bool과 누락된 수치를 실제 측정 정수로 받아들이지 않습니다. """
    return type(value) is int and minimum <= value <= maximum


def read_json(path: Path) -> dict:
    """! @brief 중복 key와 과대 JSON을 fail-closed로 거부합니다. """
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    require(path.is_file() and path.stat().st_size <= 4 * 1024 * 1024, "missing/oversized JSON input")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    require(isinstance(value, dict), "JSON object required")
    return value


def evidence_file(reference: dict, base: Path) -> Path:
    """! @brief 참조 파일의 hash를 확인하며 경로 문자열만으로 증거를 인정하지 않습니다. """
    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"}, "evidence reference fields")
    require(isinstance(reference["path"], str) and reference["path"], "evidence path required")
    require(isinstance(reference["sha256"], str) and SHA.fullmatch(reference["sha256"]), "evidence hash required")
    path = Path(reference["path"])
    path = (base / path).resolve() if not path.is_absolute() else path.resolve()
    require(path.is_file() and digest(path) == reference["sha256"], "evidence file/hash mismatch")
    return path


def adjacent_evidence_file(reference: dict, base: Path) -> Path:
    """! @brief 증거 묶음 밖 파일을 참조하지 못하도록 인접 byte만 허용합니다. """

    require(isinstance(reference, dict) and isinstance(reference.get("path"), str) and
            Path(reference["path"]).name == reference["path"],
            "evidence file must be adjacent")
    return bundle_evidence_file(reference, base)


def bundle_evidence_file(reference: dict, base: Path) -> Path:
    """! @brief content address가 지정 bundle 내부 파일만 가리키는지 확인합니다. """

    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"},
            "evidence reference fields")
    relative = reference["path"]
    require(isinstance(relative, str) and relative and
            not Path(relative).is_absolute() and ":" not in relative and
            "\\" not in relative and
            all(part not in {"", ".", ".."} for part in relative.split("/")),
            "evidence file must remain inside the bundle")
    path = base.absolute() / relative
    require(_content_reference(path, base) == reference,
            "bundle evidence file/hash mismatch")
    return path


def campaign_matrix_paths(path: Path, revision: str) -> dict[tuple[str, str], Path]:
    """! @brief 33+8+8 matrix manifest의 순서·hash·current-S 결합을 검증합니다. """

    manifest_path = path.resolve()
    manifest = read_json(manifest_path)
    common_required = {
        "schema_version", "kind", "status", "source_revision", "source_clean",
        "group_count", "groups",
    }
    schema_version = manifest.get("schema_version")
    required = common_required if schema_version == 1 else \
        common_required | {"session"}
    expected = [
        (field, identifier)
        for field, registry in CAMPAIGN_REGISTRIES.items()
        for identifier in registry
    ]
    require(set(manifest) == required and schema_version in (1, 2) and
            manifest["kind"] == "m33_campaign_matrix_result" and
            manifest["status"] == "PASS" and
            manifest["source_revision"] == revision and
            manifest["source_clean"] is True and
            manifest["group_count"] == len(expected) and
            isinstance(manifest["groups"], list) and
            len(manifest["groups"]) == len(expected),
            "campaign matrix manifest schema/source mismatch")
    if schema_version == 2:
        session_path = adjacent_evidence_file(
            manifest["session"], manifest_path.parent
        )
        session = read_json(session_path)
        board_inventory = session.get("board_inventory")
        inventory_path = Path(board_inventory.get("path", "")) \
            if isinstance(board_inventory, dict) else Path("")
        require(set(session) == {
                    "schema_version", "kind", "source_revision",
                    "source_clean", "board_inventory", "artifact_root",
                    "sdk_root", "toolchain", "group_count", "groups",
                } and
                session.get("schema_version") == 1 and
                session.get("kind") == "m33_campaign_matrix_session" and
                session.get("source_revision") == revision and
                session.get("source_clean") is True and
                isinstance(session.get("board_inventory"), dict) and
                set(session["board_inventory"]) == {"path", "sha256"} and
                isinstance(session["board_inventory"]["path"], str) and
                inventory_path.is_absolute() and
                inventory_path.is_file() and
                digest(inventory_path) ==
                session["board_inventory"]["sha256"] and
                SHA.fullmatch(session["board_inventory"]["sha256"]) is not None and
                all(isinstance(session.get(key), str) and session[key]
                    and Path(session[key]).is_absolute()
                    for key in ("artifact_root", "sdk_root", "toolchain")) and
                session.get("group_count") == len(expected) and
                session.get("groups") == [
                    {"ordinal": ordinal, "field": field, "id": identifier}
                    for ordinal, (field, identifier) in enumerate(
                        expected, start=1
                    )
                ], "campaign matrix session/source mismatch")
    paths = {}
    for ordinal, (row, (field, identifier)) in enumerate(
            zip(manifest["groups"], expected, strict=True), start=1):
        row_required = {"ordinal", "field", "id", "status", "spec",
                        "evidence"}
        if schema_version == 2:
            row_required.update({"attempt", "attempts"})
        require(isinstance(row, dict) and
                set(row) == row_required and
                row["ordinal"] == ordinal and row["field"] == field and
                row["id"] == identifier and row["status"] == "PASS",
                "campaign matrix group order/status mismatch")
        if schema_version == 1:
            spec_path = adjacent_evidence_file(
                row["spec"], manifest_path.parent
            )
            result_path = adjacent_evidence_file(
                row["evidence"], manifest_path.parent
            )
        else:
            require(type(row["attempt"]) is int and row["attempt"] >= 1,
                    "campaign matrix group attempt mismatch")
            require(isinstance(row["attempts"], list) and
                    len(row["attempts"]) == row["attempt"],
                    "campaign matrix attempt denominator mismatch")
            attempt_name = (
                f"campaign-group.{ordinal:02d}.{field}.{identifier}."
                f"attempt-{row['attempt']}"
            )
            expected_spec = f".campaign-attempts/{attempt_name}/spec.json"
            expected_result = f".campaign-attempts/{attempt_name}/result.json"
            require(row["spec"].get("path") == expected_spec and
                    row["evidence"].get("path") == expected_result,
                    "campaign matrix attempt path mismatch")
            spec_path = bundle_evidence_file(
                row["spec"], manifest_path.parent
            )
            result_path = bundle_evidence_file(
                row["evidence"], manifest_path.parent
            )
            for attempt, attempt_row in enumerate(
                    row["attempts"], start=1):
                required_attempt = {"attempt", "status"}
                status = attempt_row.get("status") \
                    if isinstance(attempt_row, dict) else None
                if status == "INCOMPLETE":
                    if "spec" in attempt_row:
                        required_attempt.add("spec")
                    if "failure" in attempt_row:
                        required_attempt.update({"spec", "failure"})
                else:
                    required_attempt.update({"spec", "evidence"})
                require(isinstance(attempt_row, dict) and
                        set(attempt_row) == required_attempt and
                        attempt_row.get("attempt") == attempt and
                        status in {"INCOMPLETE", "FAIL", "PASS"} and
                        (status == "PASS") == (attempt == row["attempt"]),
                        "campaign matrix attempt history mismatch")
                attempt_prefix = (
                    f".campaign-attempts/campaign-group.{ordinal:02d}."
                    f"{field}.{identifier}.attempt-{attempt}/"
                )
                if "spec" in attempt_row:
                    require(attempt_row["spec"].get("path") ==
                            attempt_prefix + "spec.json",
                            "campaign matrix attempt spec path mismatch")
                    bundle_evidence_file(
                        attempt_row["spec"], manifest_path.parent
                    )
                if "evidence" in attempt_row:
                    require(attempt_row["evidence"].get("path") ==
                            attempt_prefix + "result.json",
                            "campaign matrix attempt result path mismatch")
                    bundle_evidence_file(
                        attempt_row["evidence"], manifest_path.parent
                    )
                if "failure" in attempt_row:
                    require(attempt_row["failure"].get("path") ==
                            attempt_prefix + "failure.json",
                            "campaign matrix failure path mismatch")
                    failure_path = bundle_evidence_file(
                        attempt_row["failure"], manifest_path.parent
                    )
                    failure = execution.read_json(failure_path)
                    require(failure.get("source_revision") == revision and
                            failure.get("status") == "FAIL" and
                            failure.get("category") in execution.CATEGORIES and
                            failure.get("spec_sha256") == attempt_row["spec"]["sha256"],
                            "campaign matrix failure evidence mismatch")
                    execution.validate_references(failure_path.parent, failure["outputs"])
            require(row["attempts"][-1]["spec"] == row["spec"] and
                    row["attempts"][-1]["evidence"] == row["evidence"],
                    "campaign matrix final attempt reference mismatch")
        spec = read_json(spec_path)
        result = read_json(result_path)
        require(spec.get("field") == field and spec.get("id") == identifier and
                spec.get("source_revision") == revision and
                result.get("field") == field and result.get("id") == identifier and
                result.get("source_revision") == revision,
                "campaign matrix group identity mismatch")
        paths[(field, identifier)] = result_path
    return paths


def intel_hex_ranges(path: Path) -> list[tuple[int, bytes]]:
    """! @brief 실제 Intel HEX의 checksum·중복·주소를 검증하고 연속 byte 범위를 반환합니다. """
    memory, base_address, ended = {}, 0, False
    try:
        lines = path.read_bytes().decode("ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("image must be an ASCII Intel HEX file") from error
    for line in lines:
        require(not ended and line.startswith(":"), "invalid Intel HEX record ordering")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as error:
            raise ValueError("invalid Intel HEX encoding") from error
        require(len(record) >= 5 and len(record) == record[0] + 5 and sum(record) & 0xff == 0,
                "invalid Intel HEX checksum/length")
        count, address, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
        data = record[4:-1]
        if kind == 0:
            start = base_address + address
            require(count > 0 and 0 <= start < start + count <= 0x16c000,
                    "Intel HEX data outside application range")
            for offset, value in enumerate(data):
                require(start + offset not in memory, "overlapping Intel HEX data")
                memory[start + offset] = value
        elif kind == 1:
            require(count == 0 and address == 0, "invalid Intel HEX EOF")
            ended = True
        elif kind == 2:
            require(count == 2 and address == 0, "invalid Intel HEX segment address")
            base_address = int.from_bytes(data, "big") << 4
        elif kind == 4:
            require(count == 2 and address == 0, "invalid Intel HEX linear address")
            base_address = int.from_bytes(data, "big") << 16
        elif kind in (3, 5):
            require(count == 4 and address == 0, "invalid Intel HEX start address")
        else:
            require(False, "unsupported Intel HEX record")
    require(ended and memory and all(index in memory for index in range(8)),
            "Intel HEX EOF/vector missing")
    ranges: list[tuple[int, bytearray]] = []
    for address in sorted(memory):
        if not ranges or address != ranges[-1][0] + len(ranges[-1][1]):
            ranges.append((address, bytearray()))
        ranges[-1][1].append(memory[address])
    return [(start, bytes(data)) for start, data in ranges]


def validate_source_manifest(manifest: dict, revision: str, lock: dict) -> None:
    """! @brief full revision과 실제 build 입력 hash로 source manifest를 재계산합니다. """
    require(isinstance(manifest, dict) and
            set(manifest) == {*SOURCE_MANIFEST_FIELDS, "sha256"},
            "source manifest fields")
    expected_revisions = {
        "core_revision": revision,
        "board_revision": lock["board"]["revision"],
        "ncs_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
    }
    for key, expected in expected_revisions.items():
        require(REV.fullmatch(manifest.get(key, "")) and manifest[key] == expected,
                "source manifest full revision mismatch")
    for key in SOURCE_MANIFEST_FIELDS[4:]:
        require(SHA.fullmatch(manifest.get(key, "")), "source manifest hash missing")
    encoded = "\n".join(f"{key}={manifest[key]}" for key in SOURCE_MANIFEST_FIELDS)
    require(manifest["sha256"] == hashlib.sha256(encoded.encode("ascii")).hexdigest(),
            "source manifest digest mismatch")


def validate_image_evidence(image: dict, base: Path, revision: str, lock: dict,
                            expected_role: str | None = None,
                            physical: bool = True) -> dict:
    """! @brief image·원본 build·live readback·안전 flash 기록을 실제 byte와 결합합니다. """
    required = {"role", "file", "build_record", "readback", "flash_record", "build",
                "source_manifest", "load_ranges"}
    require(isinstance(image, dict) and set(image) == required, "image evidence fields")
    role = image["role"]
    require(isinstance(role, str) and role and (expected_role is None or role == expected_role),
            "image role mismatch")
    image_path = adjacent_evidence_file(image["file"], base)
    ranges = intel_hex_ranges(image_path)
    expected_load_ranges = [
        {"start": start, "length": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for start, data in ranges
    ]
    require(image["load_ranges"] == expected_load_ranges, "image load-range manifest mismatch")
    programmed_bytes = sum(len(data) for _, data in ranges)
    programmed_sectors = {
        sector
        for start, data in ranges
        for sector in range(start // 4096, (start + len(data) - 1) // 4096 + 1)
    }
    sector_programmed_bytes = len(programmed_sectors) * 4096
    if physical:
        vector = dict((start + offset, value) for start, data in ranges
                      for offset, value in enumerate(data))
        initial_sp = int.from_bytes(bytes(vector[index] for index in range(4)), "little")
        reset_vector = int.from_bytes(bytes(vector[index] for index in range(4, 8)), "little")
        require(programmed_bytes >= 65536 and 0x20000000 <= initial_sp < 0x30000000 and
                reset_vector & 1 == 1 and 0 < (reset_vector & ~1) < 0x16c000,
                "physical firmware image size/vector is implausible")
    manifest = image["source_manifest"]
    validate_source_manifest(manifest, revision, lock)
    if physical:
        embedded_values = [manifest[key].encode("ascii") for key in SOURCE_MANIFEST_FIELDS]
        embedded_values.append(manifest["sha256"].encode("ascii"))
        require(all(any(value in data for _, data in ranges) for value in embedded_values),
                "full source manifest is not embedded in physical image")
    build_record_path = adjacent_evidence_file(image["build_record"], base)
    require(build_record_path.stat().st_size <= 1024 * 1024, "oversized build record")
    try:
        build_record_bytes = build_record_path.read_bytes()
        build_record_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("build record must be UTF-8 text") from error
    build = image["build"]
    require(isinstance(build, dict), "image build object required")
    for key, expected in (("core_revision", revision), ("board_revision", lock["board"]["revision"]),
                          ("ncs_revision", lock["ncs"]["revision"]),
                          ("zephyr_revision", lock["zephyr"]["revision"])):
        actual = build.get(key, "")
        require(actual == expected and REV.fullmatch(actual) and
                actual.encode("ascii") in build_record_bytes,
                "original build record revision mismatch")
    for key in SOURCE_MANIFEST_FIELDS[4:]:
        require(SHA.fullmatch(build.get(key, "")), "image build source proof missing")
        require(build[key].encode("ascii") in build_record_bytes,
                "build source proof absent from original record")
        require(manifest[key] == build[key],
                "source manifest is not bound to original build source proof")
    require(build.get("source_manifest_sha256") == manifest["sha256"] and
            manifest["sha256"].encode("ascii") in build_record_bytes,
            "full source manifest absent from original build record")
    require(SHA.fullmatch(build.get("record_sha256", "")), "build record hash missing")
    require(build["record_sha256"] == digest(build_record_path), "build record byte mismatch")

    readback_path = adjacent_evidence_file(image["readback"], base)
    readback = read_json(readback_path)
    require(set(readback) == {"schema_version", "status", "role", "source_revision",
                              "source_manifest_sha256", "probe_sha256", "backend", "halted",
                              "resumed", "image_sha256", "ranges"}, "readback evidence fields")
    require(readback["schema_version"] == 2 and readback["status"] == "PASS" and
            readback["role"] == role and readback["source_revision"] == revision and
            readback["source_manifest_sha256"] == manifest["sha256"] and
            SHA.fullmatch(readback["probe_sha256"]) and
            readback["backend"] == "pyocd-live-target" and
            readback["halted"] is True and readback["resumed"] is True and
            readback["image_sha256"] == image["file"]["sha256"],
            "live readback identity mismatch")
    expected_ranges = [{"start": start, "length": len(data), "expected_sha256": hashlib.sha256(data).hexdigest(),
                        "observed_sha256": hashlib.sha256(data).hexdigest(), "status": "PASS"}
                       for start, data in ranges]
    require(readback["ranges"] == expected_ranges, "target readback does not match exact image ranges")

    flash_path = adjacent_evidence_file(image["flash_record"], base)
    flash = read_json(flash_path)
    required_flash = {"schema_version", "status", "role", "source_revision", "probe_sha256",
                      "cmsis_dap", "mode", "erase", "auto_unlock", "automatic_recover",
                      "mass_erase", "source_manifest_sha256", "image_sha256",
                      "programmed_bytes", "readback_sha256"}
    require(set(flash) == required_flash and flash["schema_version"] == 2 and flash["status"] == "PASS",
            "flash evidence fields/status")
    require(flash["role"] == role and flash["source_revision"] == revision and
            flash["probe_sha256"] == readback["probe_sha256"] and
            flash["source_manifest_sha256"] == manifest["sha256"] and
            flash["cmsis_dap"] == "v2-only",
            "flash role/revision/probe mismatch")
    require(flash["mode"] == "pyocd-sector-sw-reset" and flash["erase"] == "sector" and
            flash["auto_unlock"] is False and flash["automatic_recover"] is False and
            flash["mass_erase"] is False, "unsafe flash operation")
    expected_programmed_bytes = sector_programmed_bytes if physical else programmed_bytes
    require(flash["image_sha256"] == image["file"]["sha256"] and
            flash["readback_sha256"] == image["readback"]["sha256"] and
            flash["programmed_bytes"] == expected_programmed_bytes,
            "flash image/readback/load-range binding mismatch")
    return {"role": role, "image_sha256": image["file"]["sha256"],
            "readback_sha256": image["readback"]["sha256"],
            "probe_sha256": flash["probe_sha256"], "ranges": expected_ranges,
            "source_manifest_sha256": manifest["sha256"]}


def campaign_plan(field: str, identifier: str, root: Path = ROOT) -> dict:
    """! @brief 실제 runner와 source tree hash를 포함한 현재 campaign 계획을 반환합니다. """
    require(field in CAMPAIGN_REGISTRIES and
            identifier in CAMPAIGN_REGISTRIES[field], "unknown actual campaign plan")
    rows = []
    for campaign_id in CAMPAIGN_REGISTRIES[field][identifier]:
        definition = CAMPAIGNS[campaign_id]
        runner_path = root / definition["runner"]
        require(runner_path.is_file(), f"actual campaign runner missing: {campaign_id}")
        applications = []
        for relative in definition["applications"]:
            require(relative != FORBIDDEN_GENERIC_APPLICATION,
                    "generic raw application is forbidden")
            source_path = root / relative
            require(source_path.exists(), f"actual campaign application missing: {campaign_id}")
            applications.append({"path": relative,
                                 "sha256": source_path_digest(source_path)})
        rows.append({
            "id": campaign_id,
            "verification": definition["verification"],
            "runner": {"path": definition["runner"],
                       "sha256": digest(runner_path)},
            "applications": applications,
            "roles": list(definition["roles"]),
            "minimum_cycles": definition["minimum_cycles"],
            "semantics": list(definition["semantics"]),
        })
    return {"field": field, "id": identifier, "campaigns": rows}


def snapshot(root: Path = ROOT) -> dict:
    """! @brief 기존 원장 수치를 역사 기준선으로 보존하며 현재 회귀 결과는 NOT_RUN으로 둡니다. """
    lock = read_json(root / "tools/ci/ncs-3.4.0.lock.json")
    inputs, documents = {}, {}
    for milestone in range(28, 34):
        suffix = "release" if milestone == 33 else "ble"
        path = root / f"variants/nu54dk/m{milestone}-{suffix}-readiness.json"
        documents[milestone] = read_json(path)
        inputs[f"M{milestone}"] = {"path": path.relative_to(root).as_posix(), "sha256": digest(path)}
        baseline = documents[milestone]["baseline"]
        for field, section in (("ncs_revision", "ncs"), ("zephyr_revision", "zephyr"), ("board_revision", "board")):
            require(baseline.get(field) == lock[section]["revision"], f"M{milestone} {field} drift")
    current = documents[33]
    cases = {case["id"]: case for family in current["test_families"] for case in family["cases"]}
    for name, expected, iterations, boards in (
            ("M33-REG-01:families", 33, 1, 3),
            ("M33-RESOURCE-01:profiles", 8, 1, 3),
            ("M33-INTEROP-01:automatic", 8, 20, 2)):
        require(cases[name]["denominator"] == expected and
                cases[name]["iterations"] == iterations and
                cases[name]["minimum_boards"] == boards and
                cases[name]["allowed_failures"] == 0,
                "shared denominator/iteration/board contract changed")
    packages = {row["id"]: row for row in current["work_packages"]}
    blockers = [key for key in ("M33-W02", "M33-W03", "M33-W04", "M33-W05")
                if packages.get(key, {}).get("status") != "completed"]
    for identifier, (_, filename) in FAMILIES.items():
        require((root / "tests/host" / filename).is_file(), f"missing family Host route: {identifier}")
        campaign_plan("families", identifier, root)
    for field, identifiers in (("resources", RESOURCE_GROUPS),
                               ("automatic_peers", PEER_GROUPS)):
        for identifier in identifiers:
            campaign_plan(field, identifier, root)
    resource_path = root / "00_Docs/04_검증 기록/evidence/m31-w06-close-20260926/resource-manifest.json"
    historical_resource = read_json(resource_path)
    return {
        "schema_version": 1, "scope": "M33-W06-preparation", "status": "NOT_RUN",
        "source_revision": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
        "source_clean": not subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True).strip(),
        "inputs": inputs, "lock_sha256": digest(root / "tools/ci/ncs-3.4.0.lock.json"),
        "prerequisite_blockers": blockers,
        "historical_only": {
            "m28": documents[28]["public_contract"], "m29": documents[29]["resource_contract"],
            "m30": documents[30]["resource_contract"], "m31": historical_resource,
            "m31_source": {"path": resource_path.relative_to(root).as_posix(), "sha256": digest(resource_path)},
            "m32_profiles": documents[32]["resource_profiles"], "m32_conflicts": documents[32]["profile_conflicts"],
        },
        "families": [{"id": key, "owner": owner, "host_test": filename,
                      "host_status": "NOT_RUN", "current_hil_status": "NOT_RUN",
                      "campaigns": list(FAMILY_CAMPAIGNS[key])}
                     for key, (owner, filename) in FAMILIES.items()],
        "resource_groups": [{"id": key, "campaigns": list(RESOURCE_CAMPAIGNS[key])}
                            for key in RESOURCE_GROUPS],
        "automatic_peer_groups": [
            {"id": key, "campaigns": list(AUTOMATIC_PEER_CAMPAIGNS[key])}
            for key in PEER_GROUPS
        ],
        "negative_classes": sorted(NEGATIVES),
        "sdk_risk_regressions": current["sdk_risk_regressions"],
        "sdk_risk_plan": SDK_RISK_CAMPAIGNS,
        "risk_policy": "conditional test coverage, never an inferred failure cause; NCS 3.4.0 unchanged",
        "hil_contract": hil_contract(), "external_interoperability": "NOT_RUN",
        "qualification": "NOT_ASSESSED", "physical_os_validation": "RC_USER_GATE",
        "peer_matrix_template": peer_matrix(),
    }


def hil_contract() -> dict:
    """! @brief 새 image에 모든 기능을 강제로 결합하지 않는 세 보드 유한 시험 계약입니다. """
    return {"roles": ["peripheral", "mixed", "central"], "boards": 3,
            "image_application": "tests/zephyr/m32_regression_soak_hil",
            "explicit_parent_execution_runner": "tests/hil/nu54dk/m32_regression_soak_run.py",
            "duration_seconds": 1800, "timeout_seconds": 2100,
            "packets_per_link": 10000, "allowed_loss_packets": 100,
            "required_observed_loss_packets": 0, "maximum_gap_ms": 500,
            "cleanup_timeout_ms": 30000, "maximum_diagnostic_retests": 1,
            "required_zero": ["corrupt", "duplicate", "unexpected_disconnect", "recovery_failures", "drops"],
            "preflight": ["actual three probe hashes and VCOM mapping", "exact build/image readback",
                          "other radio isolation", "exclusive probe locks",
                          "finite autonomous cleanup and FINAL"],
            "automatic_flash": False, "automatic_unlock": False, "automatic_recover": False,
            "termination": "autonomous_finite_cleanup_final", "stop_token": False,
            "scope": "current-revision representative GATT soak; not all-feature simultaneous support",
            "status": "NOT_RUN"}


def peer_matrix() -> list[dict]:
    """! @brief OS 이름만으로 service 지원을 추정하지 않는 기능별 후속 matrix입니다. """
    rows = []
    for feature in PEER_GROUPS:
        for operating_system in ("Android", "iOS", "Windows", "Ubuntu", "macOS"):
            rows.append({"feature": feature, "kind": "external_product", "status": "NOT_RUN",
                         "peer_support": "unknown", "core_support": "unknown",
                         "peer": {"vendor": None, "model": None, "os": operating_system,
                                  "os_version": None, "adapter": None, "app": None},
                         "verification_owner": "user", "verification_stage": "user_follow_up",
                         "development_blocker": False, "release_blocker": False,
                         "support_discovery": "not_run", "reason_code": "not_run",
                         "evidence": None, "qualification_status": "NOT_ASSESSED"})
    for operating_system in ("Windows", "Ubuntu", "macOS"):
        rows.append({"feature": "package_usb_serial_debug_lifecycle", "kind": "physical_os", "status": "NOT_RUN",
                     "peer_support": "unknown", "core_support": "unknown",
                     "peer": {"vendor": None, "model": None, "os": operating_system,
                              "os_version": None, "adapter": None, "app": None},
                     "verification_owner": "user", "verification_stage": "final_release",
                     "development_blocker": False, "release_blocker": True,
                     "support_discovery": "not_run", "reason_code": "not_run",
                     "evidence": None, "qualification_status": "NOT_ASSESSED"})
    return rows


def read_config(path: Path) -> dict:
    """! @brief 실제 build .config의 설정값만 읽고 없는 symbol을 임의 활성화하지 않습니다. """
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"(CONFIG_[A-Z0-9_]+)=(.*)", line)
        if match:
            require(match[1] not in result, "duplicate Kconfig assignment")
            raw = match[2]
            result[match[1]] = int(raw, 0) if re.fullmatch(r"(?:[0-9]+|0x[0-9a-fA-F]+)", raw) else raw
    require(result, "empty Kconfig evidence")
    return result


def elf_allocated_memory(path: Path) -> dict:
    """! @brief ELF alloc section을 읽어 RRAM/RAM 사용량과 주소 범위를 계산합니다. """
    data = path.read_bytes()
    require(64 <= len(data) <= 64 * 1024 * 1024 and data[:4] == b"\x7fELF",
            "resource ELF input missing or invalid")
    elf_class, encoding = data[4], data[5]
    require(elf_class in (1, 2) and encoding == 1, "resource ELF class/encoding unsupported")
    if elf_class == 1:
        require(len(data) >= 52, "truncated ELF32 header")
        section_offset = struct.unpack_from("<I", data, 32)[0]
        entry_size, count = struct.unpack_from("<HH", data, 46)
        flag_offset, address_offset, size_offset, width = 8, 12, 20, 4
    else:
        section_offset = struct.unpack_from("<Q", data, 40)[0]
        entry_size, count = struct.unpack_from("<HH", data, 58)
        flag_offset, address_offset, size_offset, width = 8, 16, 32, 8
    minimum = 40 if elf_class == 1 else 64
    require(entry_size >= minimum and count > 0 and
            section_offset + entry_size * count <= len(data), "invalid ELF section table")
    ranges = {"rram": [], "ram": []}
    for index in range(count):
        offset = section_offset + entry_size * index
        flags = int.from_bytes(data[offset + flag_offset:offset + flag_offset + width], "little")
        address = int.from_bytes(data[offset + address_offset:offset + address_offset + width], "little")
        size = int.from_bytes(data[offset + size_offset:offset + size_offset + width], "little")
        if flags & 2 == 0 or size == 0:
            continue
        end = address + size
        if 0 <= address < end <= 0x20000000:
            ranges["rram"].append((address, end))
        elif 0x20000000 <= address < end <= 0x40000000:
            ranges["ram"].append((address, end))
        else:
            require(False, "ELF alloc section outside RRAM/RAM")
    result = {}
    for kind in ("rram", "ram"):
        ordered = sorted(ranges[kind])
        require(ordered, f"ELF {kind} alloc section missing")
        merged = []
        for start, end in ordered:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        result[f"{kind}_bytes"] = sum(end - start for start, end in merged)
        result[f"{kind}_ranges"] = [{"start": start, "length": end - start}
                                           for start, end in merged]
    return result


def elf_load_segments(path: Path) -> list[dict]:
    """! @brief ELF PT_LOAD의 file byte와 load address를 원본에서 읽습니다. """
    data = path.read_bytes()
    require(64 <= len(data) <= 64 * 1024 * 1024 and data[:4] == b"\x7fELF" and
            data[5] == 1, "resource ELF load input invalid")
    elf_class = data[4]
    if elf_class == 1:
        header_size, program_offset = 52, struct.unpack_from("<I", data, 28)[0]
        entry_size, count = struct.unpack_from("<HH", data, 42)
        minimum = 32
    else:
        require(elf_class == 2, "resource ELF load class unsupported")
        header_size, program_offset = 64, struct.unpack_from("<Q", data, 32)[0]
        entry_size, count = struct.unpack_from("<HH", data, 54)
        minimum = 56
    require(len(data) >= header_size and entry_size >= minimum and count > 0 and
            program_offset + entry_size * count <= len(data), "ELF program table invalid")
    result = []
    for index in range(count):
        offset = program_offset + entry_size * index
        if struct.unpack_from("<I", data, offset)[0] != 1:
            continue
        if elf_class == 1:
            file_offset, address, file_size, memory_size = struct.unpack_from(
                "<IIII", data, offset + 4
            )
        else:
            file_offset, address = struct.unpack_from("<QQ", data, offset + 8)
            file_size, memory_size = struct.unpack_from("<QQ", data, offset + 32)
        require(file_size > 0 and memory_size >= file_size and
                file_offset + file_size <= len(data), "ELF PT_LOAD range invalid")
        result.append({"start": address, "data": data[file_offset:file_offset + file_size]})
    require(result, "ELF PT_LOAD missing")
    return result


def elf_symbols(path: Path, expected: dict[str, int]) -> dict[str, dict]:
    """! @brief ELF symbol table에서 debugger 측정 symbol의 주소·크기를 읽습니다. """
    data = path.read_bytes()
    elf_class = data[4]
    if elf_class == 1:
        section_offset = struct.unpack_from("<I", data, 32)[0]
        entry_size, count = struct.unpack_from("<HH", data, 46)
        minimum = 40
    else:
        require(elf_class == 2, "resource ELF symbol class unsupported")
        section_offset = struct.unpack_from("<Q", data, 40)[0]
        entry_size, count = struct.unpack_from("<HH", data, 58)
        minimum = 64
    require(entry_size >= minimum and count > 0 and
            section_offset + entry_size * count <= len(data), "ELF symbol section table invalid")

    def section(index: int) -> tuple[int, int, int, int, int]:
        require(0 <= index < count, "ELF linked string table index invalid")
        offset = section_offset + entry_size * index
        if elf_class == 1:
            kind = struct.unpack_from("<I", data, offset + 4)[0]
            body_offset, size, link, element_size = struct.unpack_from("<IIII", data, offset + 16)
            element_size = struct.unpack_from("<I", data, offset + 36)[0]
        else:
            kind = struct.unpack_from("<I", data, offset + 4)[0]
            body_offset, size = struct.unpack_from("<QQ", data, offset + 24)
            link = struct.unpack_from("<I", data, offset + 40)[0]
            element_size = struct.unpack_from("<Q", data, offset + 56)[0]
        require(kind == 8 or body_offset + size <= len(data),
                "ELF section body outside file")
        return kind, body_offset, size, link, element_size

    found = {}
    for index in range(count):
        kind, body_offset, size, link, symbol_size = section(index)
        if kind not in (2, 11):
            continue
        string_kind, string_offset, string_size, _, _ = section(link)
        require(string_kind == 3 and symbol_size >= (16 if elf_class == 1 else 24) and
                size % symbol_size == 0, "ELF symbol/string table invalid")
        strings = data[string_offset:string_offset + string_size]
        for item in range(size // symbol_size):
            offset = body_offset + item * symbol_size
            name_offset = struct.unpack_from("<I", data, offset)[0]
            if name_offset >= len(strings):
                continue
            end = strings.find(b"\0", name_offset)
            require(end >= 0, "ELF symbol name unterminated")
            name = strings[name_offset:end].decode("utf-8", errors="strict")
            if name not in expected:
                continue
            if elf_class == 1:
                address, item_size = struct.unpack_from("<II", data, offset + 4)
            else:
                address, item_size = struct.unpack_from("<QQ", data, offset + 8)
            require(name not in found, "duplicate resource measurement symbol")
            found[name] = {"address": address, "size": item_size}
    require(set(found) == set(expected), "resource measurement ELF symbols missing")
    for name, address in expected.items():
        require(found[name] == {"address": address, "size": 4},
                "resource measurement symbol address/size mismatch")
    return found


def validate_elf_hex_binding(elf_path: Path, image_path: Path) -> None:
    """! @brief ELF PT_LOAD file byte와 Intel HEX load byte가 완전히 일치하는지 확인합니다. """
    elf_bytes = {}
    for segment in elf_load_segments(elf_path):
        for index, value in enumerate(segment["data"]):
            address = segment["start"] + index
            require(address not in elf_bytes, "overlapping ELF PT_LOAD bytes")
            elf_bytes[address] = value
    image_bytes = {}
    for start, data in intel_hex_ranges(image_path):
        for index, value in enumerate(data):
            address = start + index
            require(address not in image_bytes, "overlapping Intel HEX bytes")
            image_bytes[address] = value
    require(set(image_bytes) <= set(elf_bytes) and
            all(elf_bytes[address] == value for address, value in image_bytes.items()) and
            {address for address, value in elf_bytes.items() if value != 0} <= set(image_bytes),
            "ELF PT_LOAD and Intel HEX bytes differ")


def linker_memory_regions(path: Path) -> dict:
    """! @brief linker map의 Memory Configuration 원본에서 RRAM/RAM 영역을 읽습니다. """
    require(path.is_file() and path.stat().st_size <= 64 * 1024 * 1024,
            "resource map input missing or oversized")
    regions = {}
    pattern = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s+"
                         r"(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)(?:\s|$)")
    inside = False
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if line.strip() == "Memory Configuration":
            require(not inside and not regions, "duplicate linker Memory Configuration")
            inside = True
            continue
        if inside and line.strip().startswith("Linker script and memory map"):
            break
        if not inside:
            continue
        match = pattern.match(line)
        if match is not None:
            name = match.group(1).upper()
            require(name not in regions, "duplicate linker memory region")
            regions[name] = {"start": int(match.group(2), 16),
                             "length": int(match.group(3), 16)}
    require(inside, "linker map Memory Configuration missing")
    rram = next((value for name, value in regions.items()
                 if "FLASH" in name or "RRAM" in name), None)
    ram = next((value for name, value in regions.items()
                if ("RAM" in name and "RRAM" not in name) or "SRAM" in name), None)
    require(rram is not None and ram is not None and rram["length"] > 0 and ram["length"] > 0,
            "linker map RRAM/RAM regions missing")
    return {"rram": rram, "ram": ram}


def _range_inside(region: dict, allocated: dict) -> bool:
    """! @brief alloc 범위가 linker memory region을 벗어나지 않는지 확인합니다. """
    start = allocated["start"]
    end = start + allocated["length"]
    return region["start"] <= start <= end <= region["start"] + region["length"]


def validate_resource(record: dict, base: Path, revision: str | None = None,
                      execution_results: dict | None = None,
                      boards: dict | None = None,
                      images: dict | None = None) -> None:
    """! @brief .config·ELF/map·debugger·UART의 독립 원본을 교차 검증합니다. """
    context = (execution_results, boards, images)
    require(all(value is None for value in context) or all(value is not None for value in context),
            "resource runtime cross-binding context incomplete")
    require(record.get("group") in RESOURCE_GROUPS, "unknown resource group")
    config = read_config(adjacent_evidence_file(record["config"], base))
    requested = record.get("requested")
    require(isinstance(requested, dict) and set(requested) == set(COUNT_SYMBOLS), "resource request field set")
    for resource, symbol in COUNT_SYMBOLS.items():
        value = requested[resource]
        require(integer(value, 0, 64), "invalid requested count")
        if resource.startswith("coc_"):
            ## @brief 공개 L2capCoc 상한은 Kconfig 수가 아닌 production header의 고정 2/4/4입니다.
            limit = {"coc_channels": 2, "coc_rx_records_per_channel": 4, "coc_tx_buffers": 4}[resource] if config.get("CONFIG_NUCODE_BLE_L2CAP") == "y" else 0
        elif resource == "cs_connections" and config.get("CONFIG_BT_CHANNEL_SOUNDING") != "y":
            limit = 0
        else:
            limit = config.get(symbol, 0)
        require(integer(limit, 0, 64) and value <= limit, f"resource exceeds configured {resource}")
    require(requested["connections"] <= 2 and requested["advertising_sets"] <= 3 and
            requested["periodic_syncs"] <= 2, "published role budget exceeded")
    modes = record.get("radio_owners")
    require(isinstance(modes, list) and modes and len(modes) == len(set(modes)), "radio owner list")
    require(set(modes) <= {"ble", "mesh", "iso", "audio", "df", "cs", *EXCLUSIVE_RADIOS}, "unknown radio owner")
    allowed = {"gap_gatt": {"ble"}, "security_dfu": {"ble"}, "iso_audio": {"iso", "audio"},
               "df_cs": {"df", "cs"}, "mesh": {"mesh"}, "radio_coexistence": {"ble", "mesh", "ieee802154", "esb"},
               "profiles_companion": {"ble"}, "diagnostics": {"dtm", "raw_hci"}}
    require(set(modes) <= allowed[record["group"]], "resource group/owner mismatch")
    owner_symbols = {"ble": "CONFIG_BT", "mesh": "CONFIG_BT_MESH", "iso": "CONFIG_BT_ISO",
                     "audio": "CONFIG_BT_AUDIO", "df": "CONFIG_BT_DF", "cs": "CONFIG_BT_CHANNEL_SOUNDING",
                     "ieee802154": "CONFIG_IEEE802154", "esb": "CONFIG_ESB"}
    for owner in modes:
        if owner in owner_symbols:
            require(config.get(owner_symbols[owner]) == "y", "radio owner absent in actual configuration")
    if set(modes) & {"dtm", "raw_hci"}:
        require(len(modes) == 1, "diagnostic ownership conflict")
        require(config.get("CONFIG_BT_HCI_RAW") == "y" and config.get("CONFIG_BT_HCI_HOST") != "y",
                "normal BLE Host owns diagnostic controller")
        if modes == ["dtm"]:
            require(config.get("CONFIG_BT_CTLR_DTM_HCI") == "y", "fixed SDK DTM controller feature absent")
    require(not {"ieee802154", "esb"} <= set(modes), "two standalone radios conflict")
    if len(modes) > 1:
        require(set(modes) == {"iso", "audio"} or record.get("dedicated_coexistence") in
                ("coexistence_ble_mesh", "coexistence_ble_154", "coexistence_ble_esb"),
                "unverified combined maximum or independent-image combination")
        expected = {"coexistence_ble_mesh": {"ble", "mesh"}, "coexistence_ble_154": {"ble", "ieee802154"},
                    "coexistence_ble_esb": {"ble", "esb"}}
        if record.get("dedicated_coexistence"):
            require(set(modes) == expected[record["dedicated_coexistence"]], "coexistence owner mismatch")
    measured = record.get("measured", {})
    require(integer(measured.get("ram_bytes"), 1, 235520) and integer(measured.get("rram_bytes"), 1, 655360),
            "RAM/RRAM measurement missing or over published limit")
    require(integer(measured.get("minimum_stack_margin_bytes"), 1), "runtime stack margin not observed")
    for field in ("allocation_failures", "resource_leaks", "pending_links", "outstanding_buffers"):
        require(type(measured.get(field)) is int and measured[field] == 0, "resource cleanup failed")
    if config.get("CONFIG_BT_LL_SOFTDEVICE") == "y":
        require(type(measured.get("sdc_pool_alignment_bytes")) is int and measured["sdc_pool_alignment_bytes"] == 8,
                "SDC pool alignment must be eight bytes")
    else:
        require("sdc_pool_alignment_bytes" in measured and measured["sdc_pool_alignment_bytes"] is None,
                "non-SDC image alignment must be explicitly not applicable")
    require(all(integer(config.get(symbol), 1) for symbol in
                ("CONFIG_MAIN_STACK_SIZE", "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE", "CONFIG_BT_RX_STACK_SIZE"))
            if "ble" in modes or "iso" in modes or "mesh" in modes else True, "thread budget absent")
    role_measurements = record.get("role_measurements")
    expected_roles = set(RAW_PRODUCER_CONTRACTS["resources"]["roles"])
    require(isinstance(role_measurements, dict) and set(role_measurements) == expected_roles,
            "resource role measurement denominator")
    measurement_path = adjacent_evidence_file(record["measurement_evidence"], base)
    measurement = read_json(measurement_path)
    require(set(measurement) == {"schema_version", "kind", "group", "source_revision",
                                 "source_clean", "config_sha256", "roles"},
            "resource measurement fields")
    require(measurement["schema_version"] == 2 and
            measurement["kind"] == "resource_measurement_sources" and
            measurement["group"] == record["group"] and measurement["source_clean"] is True and
            measurement["config_sha256"] == record["config"]["sha256"] and
            isinstance(measurement["roles"], dict) and
            set(measurement["roles"]) == expected_roles,
            "resource measurement source mismatch")
    if revision is not None:
        require(measurement["source_revision"] == revision, "resource measurement revision mismatch")
    measurement_fields = {"ram_bytes", "rram_bytes", "minimum_stack_margin_bytes",
                          "allocation_failures", "resource_leaks", "pending_links",
                          "outstanding_buffers", "sdc_pool_alignment_bytes"}
    measurement_addresses = record.get("measurement_addresses")
    require(isinstance(measurement_addresses, dict) and
            set(measurement_addresses) == expected_roles,
            "resource debugger address role denominator")
    artifact_paths = {kind: set() for kind in ("config", "elf", "map")}
    artifact_hashes = {kind: set() for kind in ("config", "elf", "map")}
    for role in sorted(expected_roles):
        role_measured = role_measurements[role]
        require(isinstance(role_measured, dict) and set(role_measured) == measurement_fields,
                "resource role measurement fields")
        require(integer(role_measured["ram_bytes"], 1, 235520) and
                integer(role_measured["rram_bytes"], 1, 655360) and
                integer(role_measured["minimum_stack_margin_bytes"], 1),
                "resource role memory/stack measurement invalid")
        require(all(type(role_measured[field]) is int and role_measured[field] == 0
                    for field in ("allocation_failures", "resource_leaks", "pending_links",
                                  "outstanding_buffers")),
                "resource role cleanup measurement failed")
        if config.get("CONFIG_BT_LL_SOFTDEVICE") == "y":
            require(role_measured["sdc_pool_alignment_bytes"] == 8,
                    "resource role SDC alignment mismatch")
        else:
            require(role_measured["sdc_pool_alignment_bytes"] is None,
                    "resource role non-SDC alignment mismatch")
        entry = measurement["roles"][role]
        require(isinstance(entry, dict) and
                set(entry) == {"measured", "config", "elf", "map", "debugger"} and
                entry["measured"] == role_measured, "resource artifact role mismatch")
        role_config_path = adjacent_evidence_file(entry["config"], base)
        elf_path = adjacent_evidence_file(entry["elf"], base)
        map_path = adjacent_evidence_file(entry["map"], base)
        debugger_path = adjacent_evidence_file(entry["debugger"], base)
        for kind, path in (("config", role_config_path), ("elf", elf_path),
                           ("map", map_path)):
            artifact_paths[kind].add(path)
            artifact_hashes[kind].add(entry[kind]["sha256"])
        role_config = read_config(role_config_path)
        marker = RESOURCE_ROLE_CONFIG_SYMBOLS[role]
        require(role_config.pop(marker, None) == "y" and
                not set(role_config) & set(RESOURCE_ROLE_CONFIG_SYMBOLS.values()) and
                role_config == config,
                "resource role build configuration/marker differs from profile config")
        allocated = elf_allocated_memory(elf_path)
        require(allocated["ram_bytes"] == role_measured["ram_bytes"] and
                allocated["rram_bytes"] == role_measured["rram_bytes"],
                "ELF resource allocation differs from measured values")
        regions = linker_memory_regions(map_path)
        require(all(_range_inside(regions["rram"], item) for item in allocated["rram_ranges"]) and
                all(_range_inside(regions["ram"], item) for item in allocated["ram_ranges"]),
                "ELF allocation exceeds linker map memory region")
        addresses = measurement_addresses[role]
        require(isinstance(addresses, dict) and set(addresses) == measurement_fields and
                all(integer(value, 0x20000000, 0x3ffffffc) and value % 4 == 0
                    for value in addresses.values()) and
                len(set(addresses.values())) == len(addresses) and
                all(any(item["start"] <= value < item["start"] + item["length"]
                        for item in allocated["ram_ranges"])
                    for value in addresses.values()),
                "resource debugger address is not bound to ELF RAM")
        elf_symbols(elf_path, {
            RESOURCE_MEASUREMENT_SYMBOLS[field]: addresses[field]
            for field in measurement_fields
        })
        if images is not None:
            validate_elf_hex_binding(
                elf_path, adjacent_evidence_file(images[role]["file"], base)
            )
        debugger = read_json(debugger_path)
        debugger_fields = {"schema_version", "kind", "role", "source_revision", "source_clean",
                           "probe_sha256", "image_sha256", "backend", "halted", "resumed",
                           "addresses", "measured"}
        require(set(debugger) == debugger_fields and debugger["schema_version"] == 1 and
                debugger["kind"] == "pyocd-read-only-resource-snapshot" and
                debugger["role"] == role and debugger["source_clean"] is True and
                debugger["backend"] == "pyocd-live-target" and debugger["halted"] is True and
                debugger["resumed"] is True and debugger["addresses"] == addresses and
                debugger["measured"] == role_measured,
                "debugger resource snapshot mismatch")
        if revision is not None:
            require(debugger["source_revision"] == revision,
                    "debugger resource revision mismatch")
        if boards is not None and images is not None and execution_results is not None:
            require(debugger["probe_sha256"] == boards[role]["probe_sha256"] and
                    debugger["image_sha256"] == images[role]["file"]["sha256"] and
                    execution_results[role].get("measured") == role_measured,
                    "resource probe/image/UART cross-binding mismatch")
    require(all(len(artifact_paths[kind]) == len(expected_roles) and
                len(artifact_hashes[kind]) == len(expected_roles)
                for kind in artifact_paths),
            "resource roles must use distinct config/ELF/map paths and hashes")
    expected_measured = {
        "ram_bytes": max(value["ram_bytes"] for value in role_measurements.values()),
        "rram_bytes": max(value["rram_bytes"] for value in role_measurements.values()),
        "minimum_stack_margin_bytes": min(value["minimum_stack_margin_bytes"]
                                          for value in role_measurements.values()),
        "allocation_failures": sum(value["allocation_failures"]
                                   for value in role_measurements.values()),
        "resource_leaks": sum(value["resource_leaks"] for value in role_measurements.values()),
        "pending_links": sum(value["pending_links"] for value in role_measurements.values()),
        "outstanding_buffers": sum(value["outstanding_buffers"]
                                   for value in role_measurements.values()),
        "sdc_pool_alignment_bytes": next(iter(role_measurements.values()))[
            "sdc_pool_alignment_bytes"],
    }
    require(all(value["sdc_pool_alignment_bytes"] ==
                expected_measured["sdc_pool_alignment_bytes"]
                for value in role_measurements.values()) and measured == expected_measured,
            "aggregate resource measurement mismatch")


@dataclass(frozen=True)
class Binding:
    """! @brief 비밀 key 대신 peer/key hash와 generation으로 oracle link를 식별합니다. """
    slot: int
    generation: int
    peer_sha256: str
    key_sha256: str


class SessionOracle:
    """! @brief Host negative 입력 검증용 모델이며 production backend 실행을 주장하지 않습니다. """
    def __init__(self):
        self.links, self.pending, self.generations, self.retired_operations, self.loss = {}, {}, {}, set(), {}

    def connect(self, binding: Binding, now_ms: int) -> None:
        """! @brief role slot·generation·identity와 유한 재연결 창을 확인합니다. """
        require(integer(binding.slot, 0, 1) and integer(binding.generation, 1), "invalid handle")
        require(SHA.fullmatch(binding.peer_sha256) and SHA.fullmatch(binding.key_sha256), "hashed identity required")
        require(binding.slot not in self.links and binding.generation > self.generations.get(binding.slot, 0), "stale handle")
        require(integer(now_ms), "invalid timestamp")
        if binding.slot in self.loss:
            peer, key, lost_at, attempts = self.loss[binding.slot]
            require(binding.peer_sha256 == peer and binding.key_sha256 == key, "key/peer identity mismatch")
            require(now_ms >= lost_at and now_ms - lost_at <= 30000 and attempts <= 3, "reconnect bound")
        self.links[binding.slot] = binding
        self.generations[binding.slot] = binding.generation
        self.loss.pop(binding.slot, None)

    def require_binding(self, binding: Binding) -> None:
        """! @brief slot만 같거나 peer/key가 다른 callback을 새 link로 전달하지 않습니다. """
        require(self.links.get(binding.slot) == binding, "stale/cross-link/key identity")

    def request(self, binding: Binding, operation: str, now_ms: int) -> None:
        """! @brief link당 하나의 유한 operation만 소유합니다. """
        self.require_binding(binding)
        require(isinstance(operation, str) and re.fullmatch(r"[a-z0-9_-]{1,32}", operation), "invalid operation ID")
        require(binding.slot not in self.pending and operation not in self.retired_operations, "busy or retired operation")
        require(integer(now_ms), "invalid timestamp")
        self.pending[binding.slot] = (binding, operation, now_ms)

    def complete(self, binding: Binding, operation: str, now_ms: int) -> None:
        """! @brief 취소·peer loss 뒤 callback과 5초를 넘긴 operation을 거부합니다. """
        self.require_binding(binding)
        pending = self.pending.get(binding.slot)
        require(pending is not None and pending[:2] == (binding, operation), "stale/cross-operation callback")
        require(integer(now_ms) and 0 <= now_ms - pending[2] <= 5000, "operation timeout")
        self.retired_operations.add(operation)
        del self.pending[binding.slot]

    def cancel(self, binding: Binding) -> None:
        """! @brief 취소한 operation token은 새 요청에 다시 사용하지 않습니다. """
        self.require_binding(binding)
        pending = self.pending.pop(binding.slot, None)
        require(pending is not None, "nothing to cancel")
        self.retired_operations.add(pending[1])

    def peer_loss(self, binding: Binding, now_ms: int) -> None:
        """! @brief peer loss는 pending을 취소하고 generation link를 즉시 무효화합니다. """
        self.require_binding(binding)
        require(integer(now_ms), "invalid timestamp")
        if binding.slot in self.pending:
            self.cancel(binding)
        del self.links[binding.slot]
        self.loss[binding.slot] = (binding.peer_sha256, binding.key_sha256, now_ms, 0)

    def reconnect_attempt(self, slot: int, now_ms: int) -> None:
        """! @brief 원인 진단 없는 무한 재연결 대신 최대 3회·30초만 허용합니다. """
        require(slot in self.loss and integer(now_ms), "no lost peer")
        peer, key, lost, count = self.loss[slot]
        require(0 <= now_ms - lost <= 30000 and count < 3, "reconnect bound")
        self.loss[slot] = (peer, key, lost, count + 1)

    def cleanup(self, started_ms: int, finished_ms: int, outstanding_buffers: int) -> None:
        """! @brief link·operation·buffer와 30초 정리 한도를 모두 확인합니다. """
        require(integer(started_ms) and integer(finished_ms) and 0 <= finished_ms - started_ms <= 30000,
                "cleanup timeout")
        require(not self.links and not self.pending and type(outstanding_buffers) is int and outstanding_buffers == 0,
                "cleanup leak")
        self.loss.clear()


def validate_peer(row: dict) -> None:
    """! @brief 자동 peer·제품 interop·OS support·qualification을 서로 승격하지 않습니다. """
    kind = row.get("kind")
    require(kind in ("automatic", "external_product", "physical_os"), "unknown peer kind")
    require(row.get("status") in ("PASS", "FAIL", "NOT_RUN", "PEER_UNSUPPORTED", "CORE_UNSUPPORTED"), "peer status")
    require(row.get("peer_support") in ("supported", "unsupported", "unknown") and
            row.get("core_support") in ("supported", "unsupported", "unknown"), "support classification")
    policy = {"automatic": ("developer", "development", True, True),
              "external_product": ("user", "user_follow_up", False, False),
              "physical_os": ("user", "final_release", False, True)}[kind]
    require(tuple(row.get(key) for key in ("verification_owner", "verification_stage", "development_blocker", "release_blocker")) == policy,
            "verification responsibility/blocker policy mismatch")
    require(type(row["development_blocker"]) is bool and type(row["release_blocker"]) is bool, "boolean policy required")
    require(isinstance(row.get("feature"), str) and row["feature"] and isinstance(row.get("peer"), dict), "feature-specific peer required")
    require(set(row["peer"]) == {"vendor", "model", "os", "os_version", "adapter", "app"}, "peer identity fields")
    require(all(value is None or isinstance(value, str) for value in row["peer"].values()), "peer identity field type")
    if row["status"] == "PASS":
        require(row["peer_support"] == row["core_support"] == "supported", "unknown support cannot pass")
        require(all(isinstance(row["peer"][key], str) and row["peer"][key] for key in ("vendor", "model", "os", "os_version")), "observed peer identity required")
        expected_basis = "scripted_peer" if kind == "automatic" else "physical_peer"
        require(row.get("basis") == expected_basis and isinstance(row.get("evidence"), dict), "wrong interop proof basis")
        require(row.get("reason_code") == "observed_pass" and row.get("support_discovery") in SUPPORT_DISCOVERY,
                "PASS discovery/reason classification required")
    elif row["status"] in ("PEER_UNSUPPORTED", "CORE_UNSUPPORTED"):
        key = "peer_support" if row["status"] == "PEER_UNSUPPORTED" else "core_support"
        require(row[key] == "unsupported" and isinstance(row.get("reason"), str) and row["reason"] and
                row.get("reason_code") in PEER_REASON_CODES[row["status"]] and
                row.get("support_discovery") in SUPPORT_DISCOVERY and isinstance(row.get("evidence"), dict),
                "unsupported evidence/discovery/reason required")
    elif row["status"] == "FAIL":
        require(isinstance(row.get("reason"), str) and row["reason"] and
                row.get("reason_code") in PEER_REASON_CODES["FAIL"] and
                row.get("support_discovery") in SUPPORT_DISCOVERY and isinstance(row.get("evidence"), dict),
                "failure evidence/discovery/reason required")
    else:
        require(row.get("evidence") is None and row.get("reason_code") == "not_run" and
                row.get("support_discovery") == "not_run" and
                row["peer_support"] == row["core_support"] == "unknown" and
                row.get("basis") is None and row.get("reason") is None,
                "NOT_RUN must remain unevidenced and explicit")
    require(row.get("qualification_status") == "NOT_ASSESSED", "interop is not product qualification")


def validate_peer_evidence(row: dict, base: Path, revision: str | None = None) -> None:
    """! @brief peer 상태를 hash된 구조화 discovery 원본과 대조합니다. """
    require(row["status"] != "NOT_RUN", "NOT_RUN must not have peer evidence")
    path = adjacent_evidence_file(row["evidence"], base)
    evidence = read_json(path)
    required = {"schema_version", "kind", "feature", "peer", "status", "reason",
                "reason_code",
                "support_discovery", "source_revision", "source_clean"}
    require(set(evidence) == required and evidence["schema_version"] == 1 and
            evidence["kind"] == "peer_support_discovery", "peer evidence fields")
    require(evidence["feature"] == row["feature"] and evidence["peer"] == row["peer"] and
            evidence["status"] == row["status"] and evidence["reason"] == row.get("reason") and
            evidence["reason_code"] == row["reason_code"] and
            evidence["support_discovery"] == row["support_discovery"] and
            evidence["source_clean"] is True, "peer evidence content mismatch")
    if revision is not None:
        require(evidence["source_revision"] == revision, "peer evidence revision mismatch")


def _campaign_semantic_status(expected: dict, value: dict[str, str]) -> bool:
    """! @brief 조건 미충족을 허용된 DFU watchdog 항목에만 한정합니다. """

    if not isinstance(value, dict) or set(value) != set(expected["semantics"]) or \
            any(status not in ("PASS", "NOT_APPLICABLE")
                for status in value.values()):
        return False
    not_applicable = {
        token for token, status in value.items() if status == "NOT_APPLICABLE"
    }
    return not not_applicable or (
        expected["id"] == "m32_mesh_dfu" and
        not_applicable == {"active_watchdog_condition"}
    )


def _validate_campaign_receipt(reference: dict, base: Path, expected: dict,
                               revision: str, allow_fixture: bool,
                               allow_physical_audit: bool) -> bool:
    """! @brief 실제 child runner receipt를 exact runner·source·board identity에 결합합니다. """
    path = adjacent_evidence_file(reference, base)
    receipt = read_json(path)
    required = {
        "schema_version", "kind", "campaign_id", "verification", "status",
        "source_revision", "source_clean", "runner_sha256", "application_sha256",
        "roles", "cycles", "semantics", "semantic_status", "child_evidence",
        "exit_code", "pid",
        "started_ns", "finished_ns", "command_sha256", "hardware", "sha256",
    }
    require(isinstance(receipt, dict) and set(receipt) == required and
            receipt["schema_version"] == 1 and
            receipt["kind"] in ("actual_runner_receipt", "schema_fixture"),
            "campaign receipt schema mismatch")
    fixture = receipt["kind"] == "schema_fixture"
    if fixture:
        require(allow_fixture, "campaign schema fixture cannot satisfy physical closure")
    else:
        require(allow_physical_audit,
                "stored campaign evidence is audit-only and cannot create an actual run")
    require(receipt["campaign_id"] == expected["id"] and
            receipt["verification"] == expected["verification"] and
            receipt["status"] == "PASS" and
            receipt["source_revision"] == revision and
            receipt["source_clean"] is True and
            receipt["runner_sha256"] == expected["runner"]["sha256"] and
            receipt["application_sha256"] == {
                row["path"]: row["sha256"] for row in expected["applications"]
            } and receipt["roles"] == expected["roles"] and
            integer(receipt["cycles"], expected["minimum_cycles"]) and
            receipt["semantics"] == expected["semantics"] and
            _campaign_semantic_status(expected, receipt["semantic_status"]) and
            receipt["exit_code"] == 0 and integer(receipt["pid"], 1) and
            type(receipt["started_ns"]) is int and receipt["started_ns"] > 0 and
            type(receipt["finished_ns"]) is int and
            receipt["finished_ns"] > receipt["started_ns"] and
            SHA.fullmatch(receipt["command_sha256"] or ""),
            "campaign receipt identity/result mismatch")
    child_path = adjacent_evidence_file(receipt["child_evidence"], path.parent)
    require(child_path.resolve() != path.resolve() and
            0 < child_path.stat().st_size <= 16 * 1024 * 1024,
            "campaign child evidence missing or self-referential")
    child_raw = child_path.read_bytes()
    require(revision.encode("ascii") in child_raw,
            "campaign child evidence is not bound to the full source revision")
    hardware = receipt["hardware"]
    require(isinstance(hardware, list), "campaign hardware rows")
    if expected["verification"] == "physical_hil":
        expected_roles = set(expected["roles"])
        require(len(hardware) == len(expected_roles) and
                {row.get("role") for row in hardware if isinstance(row, dict)} == expected_roles,
                "campaign hardware role denominator")
        for row in hardware:
            require(set(row) == {"role", "probe_sha256", "image_sha256",
                                 "build_record_sha256", "readback_sha256",
                                 "program_mode", "programmed_bytes", "erase",
                                 "auto_unlock", "mass_erase", "automatic_recover"} and
                    all(SHA.fullmatch(row.get(key, "")) for key in
                        ("probe_sha256", "image_sha256", "build_record_sha256",
                         "readback_sha256")) and
                    str(row["program_mode"]).startswith("pyocd-sector") and
                    integer(row["programmed_bytes"], 1) and
                    row["erase"] == "sector" and row["auto_unlock"] is False and
                    row["mass_erase"] is False and
                    row["automatic_recover"] is False,
                    "campaign hardware identity fields")
        require(len({row["probe_sha256"] for row in hardware}) == len(hardware),
                "campaign probes must be distinct")
    else:
        require(expected["verification"] == "build_semantic" and
                expected["roles"] == [] and hardware == [],
                "build-only campaign cannot carry physical PASS")
    if not fixture:
        hil_path = str(ROOT / "tests/hil/nu54dk")
        if hil_path not in sys.path:
            sys.path.insert(0, hil_path)
        from m33_regression_run import revalidate_stored_campaign_bundle

        regenerated = revalidate_stored_campaign_bundle(
            child_path, expected, revision, receipt["cycles"]
        )
        require(regenerated == hardware,
                "campaign receipt hardware differs from stored child/native bytes")
    unsigned = {key: value for key, value in receipt.items() if key != "sha256"}
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(receipt["sha256"] == hashlib.sha256(encoded).hexdigest(),
            "campaign receipt digest mismatch")
    return not fixture


def validate_campaign_evidence(raw: dict, raw_path: Path, field: str,
                               identifier: str, revision: str,
                               allow_fixture: bool = False,
                               allow_physical_audit: bool = False) -> dict:
    """! @brief generic radio가 아닌 등록된 실제 campaign 결과만 W06 분모로 검증합니다. """
    require(field in CAMPAIGN_REGISTRIES and
            identifier in CAMPAIGN_REGISTRIES[field], "unknown campaign evidence route")
    common = {"schema_version", "evidence_kind", "field", "id", "status",
              "source_revision", "source_clean", "campaign_plan", "campaign_results",
              "failures"}
    required = set(common)
    allowed = set(common)
    if field == "families" and identifier == "ecosystem_templates":
        required.add("external_interoperability")
        allowed.add("external_interoperability")
    elif field == "automatic_peers":
        required.update({"peer_result", "external_interoperability"})
        allowed.update({"peer_result", "external_interoperability"})
    require(isinstance(raw, dict) and set(raw) == required and
            raw.get("schema_version") == 1 and
            raw.get("evidence_kind") == "m33_actual_campaign_result" and
            raw.get("field") == field and raw.get("id") == identifier and
            raw.get("status") == "PASS" and raw.get("source_revision") == revision and
            raw.get("source_clean") is True and raw.get("failures") == 0,
            "actual campaign evidence schema/result mismatch")
    expected_plan = campaign_plan(field, identifier)
    require(raw["campaign_plan"] == expected_plan,
            "actual campaign plan or source hash drift")
    rows = raw["campaign_results"]
    expected_rows = {row["id"]: row for row in expected_plan["campaigns"]}
    require(isinstance(rows, list) and len(rows) == len(expected_rows) and
            {row.get("id") for row in rows if isinstance(row, dict)} == set(expected_rows),
            "actual campaign denominator missing or duplicated")
    physical = False
    for row in rows:
        expected = expected_rows[row["id"]]
        require(set(row) == {"id", "status", "verification", "runner",
                             "applications", "roles", "cycles", "semantics",
                             "semantic_status", "evidence"} and
                row["status"] == "PASS" and
                row["verification"] == expected["verification"] and
                row["runner"] == expected["runner"] and
                row["applications"] == expected["applications"] and
                row["roles"] == expected["roles"] and
                integer(row["cycles"], expected["minimum_cycles"]) and
                row["semantics"] == expected["semantics"] and
                _campaign_semantic_status(expected, row["semantic_status"]),
                "actual campaign result does not match registry")
        physical = _validate_campaign_receipt(
            row["evidence"], raw_path.parent, expected, revision, allow_fixture,
            allow_physical_audit
        ) or physical
    if field == "families" and identifier == "ecosystem_templates":
        require(raw["external_interoperability"] == "NOT_RUN",
                "template build cannot certify product interoperability")
    if field == "automatic_peers":
        require(raw["external_interoperability"] == "NOT_RUN",
                "scripted peer cannot certify external interoperability")
        validate_peer(raw["peer_result"])
        require(raw["peer_result"]["kind"] == "automatic" and
                raw["peer_result"]["feature"] == identifier and
                raw["peer_result"]["status"] == "PASS",
                "automatic peer result incomplete")
        validate_peer_evidence(raw["peer_result"], raw_path.parent, revision)
    return {"status": "AUDIT_ONLY" if physical else "SCHEMA_VALID",
            "actual_run": "NOT_VERIFIED", "field": field, "id": identifier,
            "campaigns": len(rows)}


def validate_producer(producer: dict, field: str, identifier: str,
                      allow_fixture: bool, allow_physical_audit: bool) -> bool:
    """! @brief generic raw protocol은 parser fixture로만 허용하고 실제 PASS 승격을 거부합니다. """
    required = {"schema_version", "kind", "name", "route", "route_sha256",
                "test_route", "protocol"}
    require(isinstance(producer, dict) and set(producer) == required and
            producer["schema_version"] == 1, "producer fields")
    contract = RAW_PRODUCER_CONTRACTS[field]
    require(producer["name"] == contract["name"] and
            producer["route"] == contract["route"] and
            producer["test_route"] == RAW_TEST_ROUTES[field][identifier] and
            producer["protocol"] == contract["protocol"], "producer route drift")
    route = ROOT / contract["route"]
    require(route.is_file() and producer["route_sha256"] == digest(route),
            "producer source hash mismatch")
    require(producer["kind"] in ("physical_hil", "schema_fixture"), "producer kind")
    if producer["kind"] == "schema_fixture":
        require(allow_fixture, "schema fixture cannot satisfy physical closure")
        return False
    _ = allow_physical_audit
    raise ValueError("generic raw physical evidence is retired; use registered actual campaigns")


def validate_raw_execution_receipt(receipt: dict, raw: dict,
                                   boards: dict, images: dict,
                                   transcripts: dict, nonce: str) -> None:
    """! @brief flash·readback·UART가 한 live session에서 생성됐는지 receipt로 결합합니다. """
    required = {"schema_version", "kind", "producer_sha256", "scope", "id",
                "nonce_sha256", "active_started_ns", "active_finished_ns", "roles", "sha256"}
    require(isinstance(receipt, dict) and set(receipt) == required and
            receipt["schema_version"] == 1 and
            receipt["kind"] == "pyocd-sector-uart-live-session-v1",
            "raw execution receipt schema mismatch")
    unsigned = {key: value for key, value in receipt.items() if key != "sha256"}
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(receipt["sha256"] == hashlib.sha256(encoded).hexdigest() and
            receipt["producer_sha256"] == raw["producer"]["route_sha256"] and
            receipt["scope"] == raw["scope"] and receipt["id"] == raw["id"] and
            receipt["nonce_sha256"] == hashlib.sha256(nonce.encode("ascii")).hexdigest() and
            type(receipt["active_started_ns"]) is int and
            type(receipt["active_finished_ns"]) is int and
            receipt["active_finished_ns"] > receipt["active_started_ns"] and
            set(receipt["roles"]) == set(boards), "raw execution receipt identity mismatch")
    for role, board in boards.items():
        row = receipt["roles"][role]
        image = images[role]
        require(set(row) == {"probe_sha256", "image_sha256", "readback_sha256",
                             "flash_record_sha256", "transcript_sha256"} and
                row["probe_sha256"] == board["probe_sha256"] and
                row["image_sha256"] == image["file"]["sha256"] and
                row["readback_sha256"] == image["readback"]["sha256"] and
                row["flash_record_sha256"] == image["flash_record"]["sha256"] and
                row["transcript_sha256"] == transcripts[role]["sha256"],
                "raw execution receipt role binding mismatch")


def validate_execution_transcript(reference: dict, base: Path, raw: dict,
                                  protocol: str, role: str, board: dict,
                                  image: dict, target_manifest: dict) -> tuple[dict, str]:
    """! @brief 실제 UART READY·반복·cleanup·FINAL의 strict 수치와 nonce를 파싱합니다. """
    path = adjacent_evidence_file(reference, base)
    require(path.stat().st_size <= 1024 * 1024, "oversized UART transcript")
    try:
        lines = path.read_bytes().decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("UART transcript must be ASCII") from error
    nonce_pattern = re.compile(r"[0-9a-f]{32}\Z")
    require(lines, "empty UART transcript")
    ready_pattern = re.compile(
        rf"{re.escape(protocol)}:READY:id={re.escape(raw['id'])}:role={re.escape(role)}:"
        rf"revision={raw['source_revision']}:"
        rf"source_manifest_sha256={image['source_manifest']['sha256']}:"
        rf"target_manifest_sha256={target_manifest['sha256']}"
    )
    ready = ready_pattern.fullmatch(lines[0])
    require(ready is not None, "UART READY identity mismatch")
    cursor = 1
    for iteration in range(1, raw["denominator"] + 1):
        prefix = (
            f"{protocol}:ITERATION:PASS:id={raw['id']}:role={role}:iteration={iteration}:"
            f"completed={iteration}:failures=0:nonce="
        )
        require(cursor < len(lines) and lines[cursor].startswith(prefix),
                "UART iteration denominator/result mismatch")
        observed_nonce = lines[cursor][len(prefix):]
        if iteration == 1:
            require(nonce_pattern.fullmatch(observed_nonce) is not None and
                    observed_nonce != "0" * 32, "UART session nonce mismatch")
            nonce = observed_nonce
        else:
            require(observed_nonce == nonce, "UART iteration nonce mismatch")
        cursor += 1
    measured = None
    if raw["evidence_kind"] == RAW_EVIDENCE_KINDS["resources"]:
        measured = raw["role_measurements"][role]
        alignment = measured["sdc_pool_alignment_bytes"]
        alignment_text = "na" if alignment is None else str(alignment)
        expected = (
            f"{protocol}:MEASUREMENT:PASS:id={raw['id']}:role={role}:"
            f"ram_bytes={measured['ram_bytes']}:rram_bytes={measured['rram_bytes']}:"
            f"minimum_stack_margin_bytes={measured['minimum_stack_margin_bytes']}:"
            f"allocation_failures={measured['allocation_failures']}:"
            f"resource_leaks={measured['resource_leaks']}:pending_links={measured['pending_links']}:"
            f"outstanding_buffers={measured['outstanding_buffers']}:"
            f"sdc_pool_alignment_bytes={alignment_text}:nonce={nonce}"
        )
        require(cursor < len(lines) and lines[cursor] == expected,
                "UART resource measurement mismatch")
        cursor += 1
    cleanup_pattern = re.compile(
        rf"{re.escape(protocol)}:CLEANUP:PASS:id={re.escape(raw['id'])}:role={re.escape(role)}:"
        rf"elapsed_ms=([0-9]+):active_links=0:pending_links=0:outstanding_buffers=0:"
        rf"initialized=0:nonce={nonce}"
    )
    require(cursor < len(lines), "UART cleanup missing")
    cleanup = cleanup_pattern.fullmatch(lines[cursor])
    require(cleanup is not None and integer(int(cleanup.group(1)), 0, 30000),
            "UART cleanup incomplete")
    cleanup_ms = int(cleanup.group(1))
    cursor += 1
    final = (
        f"{protocol}:FINAL:PASS:id={raw['id']}:role={role}:"
        f"completed={raw['denominator']}:failures=0:"
        f"target_manifest_sha256={target_manifest['sha256']}:nonce={nonce}"
    )
    require(cursor < len(lines) and lines[cursor] == final and cursor + 1 == len(lines),
            "UART FINAL missing or trailing protocol data")
    result = {"role": role, "completed": raw["denominator"], "failures": 0,
              "cleanup_ms": cleanup_ms, "cleanup": "pass"}
    if measured is not None:
        result["measured"] = measured
    return result, nonce


def validate_target_manifest(manifest: dict, field: str, identifier: str,
                             role: str, revision: str, source_manifest_sha256: str,
                             scope: str, measurement_addresses: dict | None = None) -> None:
    """! @brief scope/test/role 계약을 compile-time target identity로 고정합니다. """
    required = {"schema_version", "scope", "id", "test_route", "protocol", "role",
                "source_revision", "source_manifest_sha256", "sha256"}
    if field == "resources":
        required.add("measurement_addresses_sha256")
    contract = RAW_PRODUCER_CONTRACTS[field]
    require(isinstance(manifest, dict) and set(manifest) == required and
            manifest["schema_version"] == 1 and manifest["scope"] == scope and
            manifest["id"] == identifier and
            manifest["test_route"] == RAW_TEST_ROUTES[field][identifier] and
            manifest["protocol"] == contract["protocol"] and manifest["role"] == role and
            manifest["source_revision"] == revision and
            manifest["source_manifest_sha256"] == source_manifest_sha256,
            "target manifest identity mismatch")
    if field == "resources":
        require(isinstance(measurement_addresses, dict) and
                manifest["measurement_addresses_sha256"] == hashlib.sha256(
                    json.dumps(measurement_addresses, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
                ).hexdigest(), "target resource debugger address binding mismatch")
    unsigned = {key: value for key, value in manifest.items() if key != "sha256"}
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(manifest["sha256"] == hashlib.sha256(encoded).hexdigest(),
            "target manifest digest mismatch")


def validate_raw_evidence(raw: dict, raw_path: Path, field: str, identifier: str,
                          revision: str, lock: dict,
                          allow_fixture: bool = False,
                          allow_physical_audit: bool = False) -> dict:
    """! @brief scope별 고정 분모·원본 protocol·image/readback를 함께 검증합니다. """
    require(field in RAW_DENOMINATORS and identifier in RAW_DENOMINATORS[field], "unknown raw evidence route")
    expected_scope = RAW_SCOPES[field]
    if field == "families" and identifier == "ecosystem_templates":
        expected_scope = "current_template_automatic_checks"
        require(raw.get("external_interoperability") == "NOT_RUN", "template build cannot certify ecosystem")
    common_fields = {"schema_version", "evidence_kind", "producer", "id", "status", "source_revision",
                     "source_clean", "scope", "denominator", "completed", "failures",
                     "boards", "images", "target_manifests", "transcripts", "results",
                     "execution_receipt"}
    required_fields = set(common_fields)
    allowed_fields = set(common_fields)
    if field == "families" and identifier == "ecosystem_templates":
        required_fields.add("external_interoperability")
        allowed_fields.add("external_interoperability")
    elif field == "resources":
        required_fields.update({"group", "config", "requested", "radio_owners", "measured",
                                "role_measurements", "measurement_addresses",
                                "measurement_evidence"})
        allowed_fields.update(required_fields | {"dedicated_coexistence"})
    elif field == "automatic_peers":
        required_fields.add("peer_result")
        allowed_fields.add("peer_result")
    require(isinstance(raw, dict) and required_fields <= set(raw) <= allowed_fields and
            raw.get("schema_version") == 2 and
            raw.get("evidence_kind") == RAW_EVIDENCE_KINDS[field],
            "raw scope schema mismatch")
    expected = RAW_DENOMINATORS[field][identifier]
    require(raw.get("status") == "PASS" and raw.get("id") == identifier and
            raw.get("source_revision") == revision and raw.get("source_clean") is True,
            "raw result identity/revision/clean mismatch")
    require(raw.get("scope") == expected_scope, "raw evidence scope mismatch")
    require(raw.get("denominator") == expected and raw.get("completed") == expected and
            type(raw.get("failures")) is int and raw["failures"] == 0,
            "raw fixed denominator incomplete")
    physical = validate_producer(raw["producer"], field, identifier, allow_fixture,
                                 allow_physical_audit)
    contract = RAW_PRODUCER_CONTRACTS[field]
    expected_roles = set(contract["roles"])
    boards = raw.get("boards")
    require(isinstance(boards, list) and len(boards) == len(expected_roles) and
            {board.get("role") for board in boards if isinstance(board, dict)} == expected_roles,
            "raw board-role denominator mismatch")
    board_map = {}
    for board in boards:
        require(set(board) == {"role", "probe_sha256", "registers", "image_sha256"} and
                SHA.fullmatch(board.get("probe_sha256", "")) and
                isinstance(board.get("registers"), dict) and board["registers"] and
                SHA.fullmatch(board.get("image_sha256", "")), "raw live board identity fields")
        board_map[board["role"]] = board
    require(len({board["probe_sha256"] for board in boards}) == len(expected_roles),
            "raw distinct probe denominator")
    images = raw.get("images")
    require(isinstance(images, list) and len(images) == len(expected_roles),
            "bound image-role denominator")
    roles = [image.get("role") for image in images if isinstance(image, dict)]
    require(set(roles) == expected_roles and len(roles) == len(set(roles)),
            "image roles missing/duplicate")
    require(len({image.get("file", {}).get("path") for image in images}) ==
            len(expected_roles), "raw roles must use distinct image paths")
    validated_images = {}
    target_manifests = raw.get("target_manifests")
    require(isinstance(target_manifests, dict) and set(target_manifests) == expected_roles,
            "target manifest role denominator")
    for image in images:
        validated = validate_image_evidence(image, raw_path.parent, revision, lock,
                                            image["role"], physical)
        board = board_map[image["role"]]
        require(validated["probe_sha256"] == board["probe_sha256"] and
                validated["image_sha256"] == board["image_sha256"],
                "raw board/image/live-readback binding mismatch")
        target_manifest = target_manifests[image["role"]]
        measurement_addresses = (raw["measurement_addresses"][image["role"]]
                                 if field == "resources" else None)
        validate_target_manifest(target_manifest, field, identifier, image["role"], revision,
                                 image["source_manifest"]["sha256"], raw["scope"],
                                 measurement_addresses)
        if physical:
            image_path = adjacent_evidence_file(image["file"], raw_path.parent)
            ranges = intel_hex_ranges(image_path)
            embedded = [str(target_manifest[key]).encode("utf-8")
                        for key in target_manifest if key != "schema_version"]
            require(all(any(value in data for _, data in ranges) for value in embedded),
                    "target manifest is not embedded in physical image")
        validated_images[image["role"]] = validated
    require(len({image["image_sha256"] for image in validated_images.values()}) >=
            contract["minimum_distinct_images"], "raw distinct image denominator")
    transcripts = raw.get("transcripts")
    require(isinstance(transcripts, dict) and set(transcripts) == expected_roles,
            "raw UART transcript role denominator")
    results, nonces = {}, set()
    for role in contract["roles"]:
        result, nonce = validate_execution_transcript(
            transcripts[role], raw_path.parent, raw, contract["protocol"], role,
            board_map[role], next(image for image in images if image["role"] == role),
            target_manifests[role],
        )
        results[role] = result
        nonces.add(nonce)
    require(len(nonces) == 1 and raw["results"] == results,
            "raw UART session/result mismatch")
    if physical:
        receipt = raw["execution_receipt"]
        nonce = next(iter(nonces))
        image_map = {image["role"]: image for image in images}
        validate_raw_execution_receipt(receipt, raw, board_map, image_map,
                                       transcripts, nonce)
    else:
        require(raw["execution_receipt"] is None,
                "schema fixture cannot carry a physical execution receipt")
    if field == "resources":
        require(raw.get("group") == identifier, "resource group mismatch")
        validate_resource(raw, raw_path.parent, revision, results, board_map,
                          {image["role"]: image for image in images})
    if field == "automatic_peers":
        validate_peer(raw["peer_result"])
        require(raw["peer_result"]["kind"] == "automatic" and
                raw["peer_result"]["status"] == "PASS" and
                raw["peer_result"]["feature"] == identifier, "automatic peer incomplete")
        validate_peer_evidence(raw["peer_result"], raw_path.parent, revision)
    return {"status": "AUDIT_ONLY" if physical else "SCHEMA_VALID",
            "actual_run": "NOT_VERIFIED", "scope": raw["scope"], "id": identifier}


def _content_reference(path: Path, base: Path) -> dict[str, str]:
    """! @brief bundle 내부 파일을 상대 경로와 SHA-256으로 고정합니다. """


    absolute, bundle = path.absolute(), base.absolute()
    try:
        relative = absolute.relative_to(bundle).as_posix()
    except ValueError as error:
        raise ValueError("campaign evidence must remain inside the bundle") from error
    require(all(part not in {"", ".", ".."} for part in relative.split("/")),
            "campaign evidence path must remain inside the bundle")
    execution.regular(bundle, directory=True)
    row = execution.references(bundle, [absolute])[0]
    return {"path": row["path"], "sha256": row["sha256"]}


def campaign_observation_keys(campaign_id: str) -> list[tuple[str, str, str]]:
    """! @brief 동일 campaign의 독립 group 실행을 생략하지 않는 고정 분모입니다. """

    return [
        (campaign_id, field, identifier)
        for field, registry in CAMPAIGN_REGISTRIES.items()
        for identifier, campaigns in registry.items()
        if campaign_id in campaigns
    ]


def _observation_keys(rows: list[dict]) -> list[tuple[str, str, str]]:
    """! @brief malformed 행을 필터로 버리지 않고 실행 식별자 전체를 검사합니다. """

    require(isinstance(rows, list) and all(
        isinstance(row, dict) and isinstance(row.get("group"), dict)
        for row in rows
    ), "SDK risk campaign execution denominator/schema mismatch")
    return [(row.get("campaign_id"), row["group"].get("field"),
             row["group"].get("id")) for row in rows]


def collect_campaign_observations(
    campaign_evidence: dict[tuple[str, str], Path],
    revision: str,
    bundle: Path,
) -> dict[str, list[dict]]:
    """! @brief group 결과에서 receipt·child·native raw 증거 사슬을 다시 수집합니다. """

    expected_groups = [
        (field, identifier)
        for field, registry in CAMPAIGN_REGISTRIES.items()
        for identifier in registry
    ]
    require(set(campaign_evidence) == set(expected_groups),
            "campaign observation group denominator mismatch")
    observations = {}
    for field, identifier in expected_groups:
        group_path = campaign_evidence[(field, identifier)].absolute()
        group_reference = _content_reference(group_path, bundle)
        raw = read_json(group_path)
        validate_campaign_evidence(
            raw, group_path, field, identifier, revision,
            allow_physical_audit=True
        )
        for result in raw["campaign_results"]:
            receipt_path = adjacent_evidence_file(
                result["evidence"], group_path.parent
            )
            receipt = read_json(receipt_path)
            child_path = adjacent_evidence_file(
                receipt["child_evidence"], receipt_path.parent
            )
            child = read_json(child_path)
            native_path = bundle_evidence_file(
                child["native_evidence"], child_path.parent
            )
            observation = {
                "campaign_id": result["id"],
                "semantic_status": result["semantic_status"],
                "group": {
                    "field": field,
                    "id": identifier,
                    "evidence": group_reference,
                },
                "receipt": _content_reference(receipt_path, bundle),
                "child_evidence": _content_reference(child_path, bundle),
                "native_evidence": _content_reference(native_path, bundle),
                "native": read_json(native_path),
            }
            observations.setdefault(result["id"], []).append(observation)
    require(set(observations) == set(CAMPAIGNS),
            "campaign observation denominator mismatch")
    return observations


def _risk_observation_public(observation: dict) -> dict:
    """! @brief raw JSON 본문을 제외한 content-addressed 위험 근거만 직렬화합니다. """

    return {
        key: observation[key]
        for key in (
            "campaign_id", "semantic_status", "group", "receipt",
            "child_evidence", "native_evidence",
        )
    }


def _risk_condition_observed(risk_id: str, observation: dict) -> bool:
    """! @brief campaign semantic과 native raw 조건을 함께 사용해 위험 조건을 재도출합니다. """

    semantic = observation["semantic_status"]
    native = observation["native"]
    if risk_id == "DRGN-29228":
        boundary = native.get("rf_boundary", {})
        risk = boundary.get("sdk_risk", {}) if isinstance(boundary, dict) else {}
        require(risk.get("id") == risk_id and
                risk.get("status") == "CONDITION_NOT_MET" and
                boundary.get("controlled_noisy_rf") == "NOT_RUN",
                "DRGN-29228 raw RF boundary mismatch")
        return False
    if risk_id == "DRGN-29270":
        raw = native.get("sdk_risk_regression", {}).get(risk_id, {})
        return (
            semantic.get("subrating_ack_boundary") == "PASS" and
            semantic.get("latency_timeout") == "PASS" and
            raw.get("issue") == risk_id and
            integer(raw.get("acknowledged_transitions"), 1) and
            integer(raw.get("increased_latency_timeout_acknowledgements"), 1) and
            integer(raw.get("boundary_payloads"), 1)
        )
    if risk_id == "DRGN-29446":
        required = {"active_cis", "nse_gt_one", "cpu_load",
                    "acl_first_teardown", "cleanup"}
        return (
            all(semantic.get(token) == "PASS" for token in required) and
            native.get("test_id") == "M33-REG-01:DRGN-29446" and
            native.get("scope") ==
            "active_cis_nse_gt_one_cpu_load_acl_first_teardown" and
            isinstance(native.get("cycles"), list) and
            len(native["cycles"]) >= CAMPAIGNS["m33_cis_acl_risk"]["minimum_cycles"]
        )
    if risk_id == "DRGN-29320":
        raw = native.get("sdk_risk_regression", {}).get(risk_id, {})
        require(raw.get("issue") == risk_id and
                raw.get("bounded_baseline") == "PASS" and
                raw.get("not_run_is_pass") is False,
                "DRGN-29320 raw baseline mismatch")
        if raw.get("controlled_noisy_rf") == "NOT_RUN":
            require(raw.get("overall_status") == "NOT_RUN",
                    "DRGN-29320 unobserved noisy condition mismatch")
            return False
        return (semantic.get("bounded_packet_loss") == "PASS" and
                raw.get("controlled_noisy_rf") == "PASS" and
                raw.get("overall_status") == "PASS")
    if risk_id == "DRGN-29669":
        required = {"active_cs", "scan_overlap", "acl_teardown",
                    "radio_schedule", "bounded_reconnect", "cleanup"}
        return (
            all(semantic.get(token) == "PASS" for token in required) and
            native.get("test_id") == "M33-REG-01:DRGN-29669" and
            native.get("scope") ==
            "active_cs_scan_overlap_acl_teardown_and_recovery" and
            native.get("not_run_is_pass") is False and
            isinstance(native.get("cycles"), list) and
            len(native["cycles"]) >=
            CAMPAIGNS["m33_cs_acl_radio_risk"]["minimum_cycles"]
        )
    if risk_id == "MESH_LPN_FRIEND_CLEAR":
        raw = native.get("sdk_risk_regression", {}).get(
            "mesh_lpn_friend_clear", {}
        )
        roles = raw.get("roles", {})
        return (
            semantic.get("lpn_friend_clear") == "PASS" and
            raw.get("status") == "PASS" and
            raw.get("condition") ==
            "ttl_zero_friend_clear_confirm_before_first_retry" and
            isinstance(roles, dict) and
            set(roles) == {"provisioner", "node_a", "node_b"} and
            roles["provisioner"] == {"status": "not_applicable", "latency_ms": 0} and
            all(roles[role].get("status") == "pass" and
                integer(roles[role].get("latency_ms"), 0, 1000)
                for role in ("node_a", "node_b"))
        )
    require(risk_id == "MCUBOOT_ACTIVE_WATCHDOG",
            "unknown SDK risk condition")
    raw = native.get("sdk_risk_regression", {}).get(
        "mcuboot_active_watchdog", {}
    )
    if raw.get("status") == "NOT_APPLICABLE":
        require(semantic.get("active_watchdog_condition") == "NOT_APPLICABLE" and
                raw.get("not_run_is_pass") is False,
                "MCUboot watchdog condition mismatch")
        return False
    return (semantic.get("active_watchdog_condition") == "PASS" and
            raw.get("status") == "PASS" and
            raw.get("condition") == "active_watchdog_erase_swap_hash" and
            raw.get("not_run_is_pass") is False)


def derive_sdk_risk_documents(observations: dict[str, list[dict]],
                              revision: str) -> dict[str, dict]:
    """! @brief 검증된 raw campaign 증거에서만 일곱 위험 JSON을 결정적으로 만듭니다. """

    documents = {}
    for risk_id, plan in SDK_RISK_CAMPAIGNS.items():
        risk_observations = []
        for campaign_id in plan["campaigns"]:
            executions = observations.get(campaign_id)
            require(_observation_keys(executions) == campaign_observation_keys(campaign_id),
                    "SDK risk campaign execution denominator mismatch")
            risk_observations.extend(executions)
        # @note 첫 미관측 결과 뒤의 malformed raw도 검사하므로 all(generator)를 쓰지 않습니다.
        conditions = [_risk_condition_observed(risk_id, item)
                      for item in risk_observations]
        observed = all(conditions)
        if observed:
            status = "PASS"
            cause_status = "conditional_regression"
        else:
            require("CONDITION_NOT_MET" in plan["allowed_status"],
                    f"fixed PASS SDK risk condition was not proven: {risk_id}")
            status = "CONDITION_NOT_MET"
            cause_status = "not_reproduced_not_assumed"
        documents[risk_id] = {
            "schema_version": 2,
            "kind": "m33_sdk_risk_result",
            "id": risk_id,
            "status": status,
            "condition": plan["condition"],
            "condition_observed": observed,
            "cause_status": cause_status,
            "campaigns": list(plan["campaigns"]),
            "campaign_evidence": [
                _risk_observation_public(item) for item in risk_observations
            ],
            "source_revision": revision,
            "source_clean": True,
        }
    return documents


def validate_sdk_risks(rows: list[dict], base: Path, revision: str,
                       completed_campaigns: set[str],
                       observations: dict[str, list[dict]] | None = None) -> None:
    """! @brief 고정 SDK 위험을 실제 campaign과 연결하고 미충족 조건을 PASS로 승격하지 않습니다. """

    expected_documents = (derive_sdk_risk_documents(observations, revision)
                          if observations is not None else None)
    require(isinstance(rows, list) and len(rows) == len(SDK_RISK_CAMPAIGNS) and
            {row.get("id") for row in rows if isinstance(row, dict)} ==
            set(SDK_RISK_CAMPAIGNS), "SDK risk denominator missing or duplicated")
    for row in rows:
        plan = SDK_RISK_CAMPAIGNS[row["id"]]
        required = {"id", "status", "condition", "condition_observed",
                    "cause_status", "campaigns", "evidence"}
        require(set(row) == required and row["status"] in plan["allowed_status"] and
                row["condition"] == plan["condition"] and
                row["campaigns"] == list(plan["campaigns"]) and
                set(row["campaigns"]) <= completed_campaigns and
                row["cause_status"] in ("not_reproduced_not_assumed",
                                         "conditional_regression"),
                "SDK risk result identity/status mismatch")
        if row["status"] == "PASS":
            require(row["condition_observed"] is True,
                    "SDK risk PASS requires the recorded condition")
        else:
            require(row["status"] == "CONDITION_NOT_MET" and
                    row["condition_observed"] is False,
                    "unobserved SDK risk condition cannot pass")
        evidence_path = adjacent_evidence_file(row["evidence"], base)
        evidence = read_json(evidence_path)
        require(set(evidence) == {"schema_version", "kind", "id", "status",
                                  "condition", "condition_observed", "cause_status",
                                  "campaigns", "campaign_evidence",
                                  "source_revision", "source_clean"} and
                evidence["schema_version"] == 2 and
                evidence["kind"] == "m33_sdk_risk_result" and
                evidence["id"] == row["id"] and
                evidence["status"] == row["status"] and
                evidence["condition"] == row["condition"] and
                evidence["condition_observed"] == row["condition_observed"] and
                evidence["cause_status"] == row["cause_status"] and
                evidence["campaigns"] == row["campaigns"] and
                evidence["source_revision"] == revision and
                evidence["source_clean"] is True,
                "SDK risk evidence mismatch")
        require(_observation_keys(evidence["campaign_evidence"]) ==
                [key for campaign_id in plan["campaigns"]
                 for key in campaign_observation_keys(campaign_id)],
                "SDK risk campaign source denominator mismatch")
        for source in evidence["campaign_evidence"]:
            require(isinstance(source, dict) and set(source) == {
                "campaign_id", "semantic_status", "group", "receipt",
                "child_evidence", "native_evidence",
            }, "SDK risk campaign source schema mismatch")
            group = source["group"]
            require(isinstance(group, dict) and
                    set(group) == {"field", "id", "evidence"},
                    "SDK risk group source mismatch")
            for reference in (
                    group["evidence"], source["receipt"],
                    source["child_evidence"], source["native_evidence"]):
                bundle_evidence_file(reference, base)
        if expected_documents is not None:
            require(evidence == expected_documents[row["id"]],
                    "SDK risk evidence was not derived from campaign raw evidence")


def validate_qualification(row: dict) -> None:
    """! @brief Host/controller/Mesh component 근거와 별도 제품 자격을 구분합니다. """
    require(row.get("component") in ("host", "controller", "mesh"), "qualification component")
    require(row.get("applicability") in ("applicable", "not_applicable", "unresolved"), "qualification applicability")
    require(row.get("component_status") in ("NOT_ASSESSED", "EVIDENCE_RECORDED"), "component qualification status")
    require(row.get("product_status") == "NOT_ASSESSED" and row.get("example_status_implied") is False,
            "component qualification cannot certify product or example")
    if row["component_status"] == "EVIDENCE_RECORDED":
        require(all(isinstance(row.get(key), str) and row[key] for key in
                    ("component_version", "design_identifier", "official_reference", "remaining_product_procedure")),
                "component evidence and remaining product procedure required")
        expected_identifier = {
            "host": "PLANNED_NO_DN",
            "controller": "PLANNED_NO_DN",
            "mesh": "NOT_LISTED_NO_DN",
        }[row["component"]]
        require(row["applicability"] == "applicable" and
                row["component_version"] == "NCS 3.4.0 LTS" and
                row["design_identifier"] == expected_identifier,
                "fixed NCS qualification evidence status mismatch")
        require(row["official_reference"].startswith("https://"), "official qualification reference required")


def validate_closure(document: dict, base: Path, current: dict) -> dict:
    """! @brief 저장 증거의 integrity만 재검사하고 actual-run PASS로 승격하지 않습니다. """
    require(document.get("schema_version") == 1 and document.get("source_revision") == current["source_revision"], "closure source mismatch")
    require(document.get("source_clean") is True and current.get("source_clean") is True, "exact closure requires clean source")
    require(not current["prerequisite_blockers"], "W02-W05 prerequisite catalog incomplete")
    require(document.get("inputs") == current["inputs"], "catalog snapshot drift")
    require(document.get("lock_sha256") == current["lock_sha256"], "fixed SDK lock drift")
    require(set(document.get("negative_classes", [])) == NEGATIVES, "negative class denominator")
    host_path = evidence_file(document["host_regression"], base)
    host = read_json(host_path)
    require(host.get("status") == "PASS" and host.get("scope") == "Host-regression-only" and
            host.get("source_revision") == current["source_revision"] and host.get("source_clean") is True,
            "current clean Host regression required")
    expected_tests = set(HOST_TESTS)
    require(len(host.get("records", [])) == len(expected_tests) and
            {row.get("test") for row in host["records"]} == expected_tests, "Host test routes missing/duplicate")
    for row in host["records"]:
        require(type(row.get("exit_code")) is int and row["exit_code"] == 0, "Host test did not pass")
        require(integer(row.get("pid"), 1) and integer(row.get("started_ns"), 1) and
                integer(row.get("finished_ns"), row["started_ns"] + 1) and
                SHA.fullmatch(row.get("raw_sha256", "")),
                "Host process audit fields missing")
        expected_count, expected_ids_sha256 = HOST_TEST_EXPECTATIONS[row["test"]]
        require(row.get("tests_run") == expected_count and row.get("skipped") == 0 and
                row.get("test_ids_sha256") == expected_ids_sha256 and
                isinstance(row.get("test_ids"), list),
                "Host verbose test ID contract mismatch")
        test_path = ROOT / "tests" / "host" / row["test"]
        require(test_path.is_file() and row.get("test_sha256") == digest(test_path),
                "Host test source hash mismatch")
        require(row.get("command") == host_command(row["test"]) and
                row.get("command_sha256") == host_command_sha256(row["command"]),
                "Host command mismatch")
        log_path = evidence_file({"path": row["test"] + ".log",
                                  "sha256": row["log_sha256"]}, host_path.parent)
        parsed = parse_unittest_log(log_path.read_bytes())
        require(parsed["exit_code"] == row["exit_code"] and
                parsed["tests_run"] == row["tests_run"] and
                parsed["skipped"] == row["skipped"] and
                parsed["test_ids"] == row["test_ids"] and
                parsed["test_ids_sha256"] == row["test_ids_sha256"] and
                hashlib.sha256(log_path.read_bytes()).hexdigest() == row["raw_sha256"] and
                host_log_matches_contract(row["test"], parsed),
                "Host manifest differs from raw unittest log")
    sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
    from m33_regression_run import validate_soak
    validate_soak(evidence_file(document["soak"], base), current["source_revision"],
                  allow_physical_audit=True)
    completed_campaigns = set()
    campaign_paths = {}
    for field, required in (("families", set(FAMILIES)), ("resources", set(RESOURCE_GROUPS)), ("automatic_peers", set(PEER_GROUPS))):
        rows = document.get(field)
        require(isinstance(rows, list) and len(rows) == len(required) and {r.get("id") for r in rows} == required,
                f"missing/duplicate {field} denominator")
        for row in rows:
            require(row.get("status") == "PASS" and row.get("source_revision") == current["source_revision"], f"{field} current PASS required")
            raw_path = bundle_evidence_file(row["evidence"], base)
            campaign_paths[(field, row["id"])] = raw_path
            raw = read_json(raw_path)
            validate_campaign_evidence(
                raw, raw_path, field, row["id"], current["source_revision"],
                allow_physical_audit=True
            )
            completed_campaigns.update(
                campaign["id"] for campaign in raw["campaign_results"]
            )
    observations = collect_campaign_observations(
        campaign_paths, current["source_revision"], base
    )
    validate_sdk_risks(document.get("sdk_risk_results", []), base,
                       current["source_revision"], completed_campaigns,
                       observations)
    external = document.get("external_peers", [])
    expected_external = {(row["kind"], row["feature"], row["peer"]["os"]) for row in peer_matrix()}
    require(len(external) == len(expected_external) and
            {(row.get("kind"), row.get("feature"), row.get("peer", {}).get("os")) for row in external} == expected_external,
            "external follow-up/physical OS matrix incomplete")
    for row in external:
        validate_peer(row)
        require(row["kind"] != "automatic", "external peer kind mismatch")
        if row["status"] != "NOT_RUN":
            validate_peer_evidence(row, base, current["source_revision"])
    qualification = document.get("qualification", [])
    require(len(qualification) == 3 and {row.get("component") for row in qualification} == {"host", "controller", "mesh"}, "qualification denominator")
    qualification_path = adjacent_evidence_file(
        document.get("qualification_evidence"), base
    )
    require(
        qualification == _qualification_rows(
            qualification_path, base / ".closure-validation.json",
            current["source_revision"],
        ),
        "qualification source evidence mismatch",
    )
    for row in qualification:
        validate_qualification(row)
        require(row["component_status"] == "EVIDENCE_RECORDED" and
                row["applicability"] != "unresolved",
                "qualification applicability investigation is incomplete")
    return {"status": "AUDIT_ONLY", "actual_run": "NOT_VERIFIED",
            "scope": "stored-evidence-integrity-only", "source_revision": current["source_revision"],
            "families": 33, "resource_groups": 8, "automatic_peer_groups": 8, "product_qualification": "NOT_ASSESSED"}


def _closure_reference(path: Path, output: Path, label: str) -> dict[str, str]:
    """! @brief closure와 같은 directory의 기존 파일만 content address로 결합합니다. """

    absolute = path.absolute()
    require(absolute.is_file() and absolute.parent == output.parent.absolute(),
            f"{label} evidence must be adjacent")
    return _content_reference(absolute, output.parent)


def _qualification_rows(path: Path, output: Path,
                        revision: str) -> list[dict]:
    """! @brief 별도 조사 evidence의 세 component 행을 제품 자격 승격 없이 읽습니다. """

    _closure_reference(path, output, "qualification")
    evidence = read_json(path.resolve())
    require(set(evidence) == {"schema_version", "kind", "source_revision",
                              "source_clean", "qualification"} and
            evidence["schema_version"] == 1 and
            evidence["kind"] == "m33_qualification_results" and
            evidence["source_revision"] == revision and
            evidence["source_clean"] is True and
            isinstance(evidence["qualification"], list) and
            len(evidence["qualification"]) == 3,
            "qualification evidence schema mismatch")
    rows = evidence["qualification"]
    require({row.get("component") for row in rows if isinstance(row, dict)} ==
            {"host", "controller", "mesh"}, "qualification denominator")
    for row in rows:
        validate_qualification(row)
        require(row["component_status"] == "EVIDENCE_RECORDED" and
                row["product_status"] == "NOT_ASSESSED" and
                row["example_status_implied"] is False,
                "qualification evidence cannot certify a product")
    return rows


def _write_new_json(path: Path, value: dict) -> None:
    """! @brief 공통 원자 확정으로 최종 sidecar의 부분 write와 덮어쓰기를 거부합니다. """


    execution.write_new_json(path, value)


def produce_sdk_risks(matrix_manifest: Path, output: Path,
                      root: Path = ROOT) -> dict:
    """! @brief 49개 actual group의 raw evidence에서 일곱 SDK 위험 증거를 생성합니다. """

    output = output.resolve()
    require(output.is_dir(), "existing SDK risk output bundle required")
    current = snapshot(root)
    revision = current["source_revision"]
    require(current["source_clean"] is True and
            not current["prerequisite_blockers"],
            "SDK risk production requires current clean exact source")
    manifest_path = matrix_manifest.resolve()
    require(manifest_path.parent == output,
            "campaign matrix manifest must be inside the output bundle")
    campaign_paths = campaign_matrix_paths(manifest_path, revision)
    observations = collect_campaign_observations(campaign_paths, revision, output)
    documents = derive_sdk_risk_documents(observations, revision)
    destinations = {
        risk_id: output / f"risk.{risk_id}.json"
        for risk_id in SDK_RISK_CAMPAIGNS
    }
    existing = [path.name for path in destinations.values() if path.exists()]
    require(not existing,
            "SDK risk output overwrite refused: " + ",".join(existing))
    for risk_id, path in destinations.items():
        _write_new_json(path, documents[risk_id])
    rows = [{
        key: documents[risk_id][key]
        for key in (
            "id", "status", "condition", "condition_observed",
            "cause_status", "campaigns",
        )
    } | {"evidence": {"path": path.name, "sha256": digest(path)}}
            for risk_id, path in destinations.items()]
    validate_sdk_risks(
        rows, output, revision, set(CAMPAIGNS), observations
    )
    return {
        "status": "EVIDENCE_RECORDED",
        "scope": "m33-w06-sdk-risk-production",
        "source_revision": revision,
        "risks": rows,
    }


def produce_qualification(output: Path, root: Path = ROOT) -> dict:
    """! @brief 고정 NCS 3.4.0 component 조사만 기록하고 제품 자격은 승격하지 않습니다. """

    output = output.resolve()
    require(output.suffix.lower() == ".json" and not output.exists() and
            output.parent.is_dir(),
            "new qualification JSON in an existing bundle required")
    current = snapshot(root)
    require(current["source_clean"] is True and
            not current["prerequisite_blockers"],
            "qualification production requires current clean exact source")
    procedure = (
        "제품 소유자가 출시 시점 DN 표와 실제 component 변경 범위를 확인하고 "
        "Qualification Workspace의 시험·서류·수수료 절차를 완료해야 함"
    )
    rows = [{
        "component": component,
        "applicability": "applicable",
        "component_status": "EVIDENCE_RECORDED",
        "product_status": "NOT_ASSESSED",
        "example_status_implied": False,
        "component_version": "NCS 3.4.0 LTS",
        "design_identifier": identifier,
        "official_reference": QUALIFICATION_REFERENCE,
        "remaining_product_procedure": procedure,
    } for component, identifier in QUALIFICATION_COMPONENTS.items()]
    for row in rows:
        validate_qualification(row)
    document = {
        "schema_version": 1,
        "kind": "m33_qualification_results",
        "source_revision": current["source_revision"],
        "source_clean": True,
        "qualification": rows,
    }
    _write_new_json(output, document)
    require(_qualification_rows(
        output, output.with_name(".qualification-validation.json"),
        current["source_revision"]
    ) == rows, "qualification producer revalidation mismatch")
    return document


def assemble_closure(
    output: Path,
    host_regression: Path,
    soak: Path,
    campaign_evidence: dict[tuple[str, str], Path],
    sdk_risk_evidence: dict[str, Path],
    qualification_evidence: Path,
    root: Path = ROOT,
) -> dict:
    """! @brief 기존 actual evidence 참조만 조립하고 strict closure를 즉시 재검증합니다. """

    output = output.resolve()
    require(output.suffix.lower() == ".json" and not output.exists() and
            output.parent.is_dir(), "new closure JSON in an existing bundle required")
    current = snapshot(root)
    revision = current["source_revision"]
    require(current["source_clean"] is True and not current["prerequisite_blockers"],
            "closure assembly requires current clean exact source")
    expected_campaigns = {
        (field, identifier)
        for field, registry in CAMPAIGN_REGISTRIES.items()
        for identifier in registry
    }
    require(set(campaign_evidence) == expected_campaigns,
            "closure campaign evidence denominator mismatch")
    require(set(sdk_risk_evidence) == set(SDK_RISK_CAMPAIGNS),
            "closure SDK risk evidence denominator mismatch")
    groups = {field: [] for field in CAMPAIGN_REGISTRIES}
    for field, registry in CAMPAIGN_REGISTRIES.items():
        for identifier in registry:
            path = campaign_evidence[(field, identifier)].absolute()
            reference = _content_reference(path, output.parent)
            raw = read_json(path)
            require(raw.get("status") == "PASS" and
                    raw.get("source_revision") == revision and
                    raw.get("source_clean") is True,
                    f"{field}:{identifier} current actual PASS required")
            validate_campaign_evidence(
                raw, path, field, identifier, revision,
                allow_physical_audit=True
            )
            groups[field].append({
                "id": identifier,
                "status": raw["status"],
                "source_revision": revision,
                "evidence": reference,
            })
    risks = []
    for risk_id in SDK_RISK_CAMPAIGNS:
        path = sdk_risk_evidence[risk_id].resolve()
        reference = _closure_reference(path, output, f"SDK risk {risk_id}")
        evidence = read_json(path)
        require(set(evidence) == {"schema_version", "kind", "id", "status",
                                  "condition", "condition_observed", "cause_status",
                                  "campaigns", "campaign_evidence",
                                  "source_revision", "source_clean"} and
                evidence.get("schema_version") == 2 and
                evidence.get("kind") == "m33_sdk_risk_result" and
                evidence.get("id") == risk_id and
                evidence.get("source_revision") == revision and
                evidence.get("source_clean") is True,
                f"SDK risk source evidence mismatch: {risk_id}")
        risks.append({
            key: evidence[key] for key in (
                "id", "status", "condition", "condition_observed",
                "cause_status", "campaigns"
            )
        } | {"evidence": reference})
    qualification_reference = _closure_reference(
        qualification_evidence, output, "qualification"
    )
    document = {
        "schema_version": 1,
        "source_revision": revision,
        "source_clean": True,
        "inputs": current["inputs"],
        "lock_sha256": current["lock_sha256"],
        "negative_classes": sorted(NEGATIVES),
        "host_regression": _closure_reference(
            host_regression, output, "Host regression"
        ),
        "soak": _closure_reference(soak, output, "soak"),
        "families": groups["families"],
        "resources": groups["resources"],
        "automatic_peers": groups["automatic_peers"],
        "sdk_risk_results": risks,
        "external_peers": peer_matrix(),
        "qualification_evidence": qualification_reference,
        "qualification": _qualification_rows(
            qualification_evidence, output, revision
        ),
    }
    audit = validate_closure(document, output.parent, current)
    require(audit == {
        "status": "AUDIT_ONLY",
        "actual_run": "NOT_VERIFIED",
        "scope": "stored-evidence-integrity-only",
        "source_revision": revision,
        "families": 33,
        "resource_groups": 8,
        "automatic_peer_groups": 8,
        "product_qualification": "NOT_ASSESSED",
    }, "closure audit result mismatch")
    _write_new_json(output, document)
    return document


EXTERNAL_CLOSURE_KIND = "m33_w06_external_closure"
EXTERNAL_CLOSURE_ENV = "NUCODE_M33_W06_EVIDENCE_ROOT"


def _external_bundle(root: Path, repository: Path) -> Path:
    """! @brief 비공개 원본은 저장소 밖의 실제 절대 경로만 허용합니다. """

    require(root.is_absolute(), "external bundle must use an absolute path")
    for parent in (root, *root.parents):
        execution.regular(parent, directory=True)
    root = root.resolve()
    require(not root.is_relative_to(repository.resolve()) and
            not repository.resolve().is_relative_to(root),
            "private evidence bundle must be outside repository")
    return root


def _bundle_files(root: Path) -> list[Path]:
    """! @brief 모든 원본을 열거하며 directory link와 특수 파일도 거부합니다. """

    execution.regular(root, directory=True)
    paths = []
    pending = [root]
    while pending:
        for path in pending.pop().iterdir():
            execution.regular(path, directory=path.is_dir())
            if path.is_dir():
                pending.append(path)
            else:
                paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def export_closure(manifest: Path, output: Path, root: Path = ROOT) -> dict:
    """! @brief strict 원본 검증 후 byte 없이 공개 hash index만 외부에 만듭니다. """

    base = _external_bundle(manifest.parent, root)
    execution.regular(manifest)
    output = Path(os.path.abspath(output))
    require(not output.is_relative_to(base) and
            not output.is_relative_to(root.resolve()) and not output.exists(),
            "closure export needs a new directory outside bundle/repository")
    current = snapshot(root)
    closure = execution.read_json(manifest)
    audit = validate_closure(closure, base, current)
    require(audit.get("status") == "AUDIT_ONLY" and
            audit.get("actual_run") == "NOT_VERIFIED" and
            audit.get("source_revision") == current["source_revision"],
            "closure export requires strict stored-evidence audit")
    rows = execution.references(base, _bundle_files(base))
    # @note 공개 파일명에는 임의 문자열이나 절대 경로를 넣지 않습니다.
    require(all(re.fullmatch(r"[A-Za-z0-9_./-]+", row["path"])
                for row in rows), "public bundle index contains unsafe path text")
    index = {"schema_version": 1, "kind": "m33_w06_private_bundle_index",
             "source_revision": current["source_revision"], "files": rows}
    execution.write_new_json(output / "bundle-files.json", index)
    reference = {
        "schema_version": 1, "kind": EXTERNAL_CLOSURE_KIND,
        "source_revision": current["source_revision"], "source_clean": True,
        "status": "EVIDENCE_REFERENCED", "publication": "hash-index-only",
        "closure": execution.references(base, [manifest])[0],
        "bundle_manifest": execution.references(
            output, [output / "bundle-files.json"])[0],
    }
    execution.write_new_bytes(output / ".gitattributes", b"* -text\n")
    execution.write_new_json(output / "closure-reference.json", reference)
    return reference


def resolve_external_closure(reference_path: Path, bundle: Path | None = None,
                             repository: Path = ROOT) -> tuple[dict, Path]:
    """! @brief 공개 참조만으로 PASS하지 않고 지정한 원본 전체 byte를 검사합니다. """

    for parent in reference_path.absolute().parents:
        execution.regular(parent, directory=True)
    reference = execution.read_json(reference_path)
    require(set(reference) == {"schema_version", "kind", "source_revision",
                              "source_clean", "status", "publication", "closure",
                              "bundle_manifest"} and
            reference["schema_version"] == 1 and
            reference["kind"] == EXTERNAL_CLOSURE_KIND and
            reference["status"] == "EVIDENCE_REFERENCED" and
            reference["publication"] == "hash-index-only" and
            reference["source_clean"] is True and
            REV.fullmatch(reference["source_revision"] or ""),
            "external closure reference schema mismatch")
    supplied = bundle if bundle is not None else os.environ.get(EXTERNAL_CLOSURE_ENV)
    require(bool(supplied), "external closure raw bundle is required: " +
            EXTERNAL_CLOSURE_ENV)
    base = _external_bundle(Path(supplied), repository)
    execution.validate_references(reference_path.parent, [reference["bundle_manifest"]])
    require(reference["bundle_manifest"]["path"] == "bundle-files.json",
            "public bundle index name mismatch")
    index = execution.read_json(reference_path.parent / "bundle-files.json")
    require(set(index) == {"schema_version", "kind", "source_revision", "files"} and
            index["schema_version"] == 1 and
            index["kind"] == "m33_w06_private_bundle_index" and
            index["source_revision"] == reference["source_revision"],
            "external closure index schema/source mismatch")
    execution.validate_references(base, index["files"])
    require([path.relative_to(base).as_posix() for path in _bundle_files(base)] ==
            [row["path"] for row in index["files"]],
            "external closure bundle file set drift")
    execution.validate_references(base, [reference["closure"]])
    require(reference["closure"] in index["files"],
            "closure is absent from private bundle index")
    closure_path = base / reference["closure"]["path"]
    require(closure_path.parent == base, "external closure must be at bundle root")
    closure = execution.read_json(closure_path)
    require(closure.get("source_revision") == reference["source_revision"] and
            closure.get("source_clean") is True, "external closure source mismatch")
    return closure, base


def _named_paths(values: list[str], campaign: bool) -> dict:
    """! @brief 중복 없는 `field:id=path` 또는 `id=path` CLI 값을 해석합니다. """

    result = {}
    for value in values:
        key_text, separator, path_text = value.partition("=")
        require(separator == "=" and key_text and path_text,
                "named evidence must use key=path")
        if campaign:
            field, field_separator, identifier = key_text.partition(":")
            require(field_separator == ":" and field and identifier,
                    "campaign evidence must use field:id=path")
            key = (field, identifier)
        else:
            key = key_text
        require(key not in result, "duplicate named evidence")
        result[key] = Path(path_text)
    return result


def host_command(filename: str) -> list[str]:
    """! @brief Host regression의 허용된 exact unittest 명령을 반환합니다. """
    return [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/host",
            "-p", filename, "-v"]


def host_command_sha256(command: list[str]) -> str:
    """! @brief 실행 명령의 순서와 인자를 canonical JSON hash로 고정합니다. """
    return hashlib.sha256(json.dumps(command, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _invalid_unittest_log() -> dict:
    """! @brief 파싱 실패를 실행 성공이나 일부 test 목록으로 복구하지 않습니다. """
    return {"exit_code": 1, "tests_run": 0, "skipped": 0,
            "test_ids": [], "test_ids_sha256": hashlib.sha256(b"").hexdigest()}


def parse_unittest_log(raw: bytes) -> dict:
    """! @brief unittest raw log의 verbose ID·최종 OK·실행 수를 독립 재계산합니다. """
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    summary = re.search(
        r"(?m)^-{70}\nRan ([0-9]+) tests? in [0-9.]+s\n\n"
        r"OK(?: \(skipped=([0-9]+)\))?\n?\Z",
        text,
    )
    if summary is None or len(re.findall(r"(?m)^Ran [0-9]+ tests? in ", text)) != 1 or \
            re.search(r"(?m)^(?:FAILED|ERROR)(?:\s|\(|$)", text):
        return _invalid_unittest_log()
    identifiers = []
    for name, qualified in re.findall(
            r"(?m)^([A-Za-z_][A-Za-z0-9_]*) \(([^)\r\n]+)\)", text):
        parts = qualified.split(".")
        if len(parts) < 2 or parts[-1] != name:
            return _invalid_unittest_log()
        identifiers.append(".".join(parts[-2:]))
    identifiers.sort()
    tests_run = int(summary.group(1))
    if tests_run != len(identifiers) or len(identifiers) != len(set(identifiers)):
        return _invalid_unittest_log()
    skipped = int(summary.group(2) or 0)
    identifier_sha256 = hashlib.sha256("\n".join(identifiers).encode("utf-8")).hexdigest()
    return {"exit_code": 0, "tests_run": tests_run, "skipped": skipped,
            "test_ids": identifiers, "test_ids_sha256": identifier_sha256}


def host_log_matches_contract(filename: str, parsed: dict) -> bool:
    """! @brief verbose test ID 전체 목록의 고정 count/hash 계약을 확인합니다. """
    expected = HOST_TEST_EXPECTATIONS.get(filename)
    return expected is not None and parsed.get("exit_code") == 0 and \
        parsed.get("skipped") == 0 and \
        (parsed.get("tests_run"), parsed.get("test_ids_sha256")) == expected


_HOST_PROCESS_AUTHORITY = object()


@dataclass(frozen=True)
class _HostProcessRuntime:
    """! @brief subprocess 실행 동안만 생성하는 비직렬화 receipt입니다. """
    authority: object
    test: str
    pid: int
    started_ns: int
    finished_ns: int
    exit_code: int
    raw_sha256: str


def _validate_host_runtime(records: list[dict], runtimes: list[_HostProcessRuntime]) -> None:
    """! @brief 저장 manifest가 방금 spawn한 프로세스 receipt와 일치하는지 검증합니다. """
    require(len(records) == len(runtimes), "Host same-process receipt denominator")
    for row, runtime in zip(records, runtimes):
        require(runtime.authority is _HOST_PROCESS_AUTHORITY and
                row["test"] == runtime.test and row["pid"] == runtime.pid and
                row["started_ns"] == runtime.started_ns and
                row["finished_ns"] == runtime.finished_ns and
                row["exit_code"] == runtime.exit_code and
                row["raw_sha256"] == runtime.raw_sha256,
                "Host same-process receipt mismatch")


def run_host(output: Path, root: Path = ROOT) -> dict:
    """! @brief subprocess를 직접 spawn하고 동일 프로세스 receipt를 검증합니다. """
    output = output.resolve()
    require(not output.exists() or output.is_dir(),
            "Host output must be a directory")
    planned = [output / "result.json"] + [
        output / (filename + ".log") for filename in HOST_TESTS
    ]
    conflicts = [path.name for path in planned if path.exists()]
    require(not conflicts,
            "Host evidence overwrite refused: " + ",".join(conflicts))
    initial_revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    initial_clean = not subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True).strip()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    runtimes = []
    for filename in HOST_TESTS:
        require((root / "tests/host" / filename).is_file(), "missing Host regression route")
        command = host_command(filename)
        started_ns = time.monotonic_ns()
        try:
            process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            try:
                stdout, stderr = process.communicate(timeout=240)
                raw, result = stdout + stderr, process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raw, result = stdout + stderr, 124
        except OSError:
            raise
        finished_ns = time.monotonic_ns()
        log = output / (filename + ".log")
        with log.open("xb") as stream:
            stream.write(raw)
        parsed = parse_unittest_log(raw)
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        records.append({"test": filename, "test_sha256": digest(root / "tests" / "host" / filename),
                        "pid": process.pid, "started_ns": started_ns,
                        "finished_ns": finished_ns, "raw_sha256": raw_sha256,
                        "exit_code": result, "tests_run": parsed["tests_run"],
                        "skipped": parsed["skipped"], "test_ids": parsed["test_ids"],
                        "test_ids_sha256": parsed["test_ids_sha256"], "command": command,
                        "command_sha256": host_command_sha256(command),
                        "log_sha256": digest(log)})
        runtimes.append(_HostProcessRuntime(
            _HOST_PROCESS_AUTHORITY, filename, process.pid, started_ns, finished_ns,
            result, raw_sha256,
        ))
    _validate_host_runtime(records, runtimes)
    final_revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    status_command = ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"]
    try:
        relative_output = output.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative_output = None
    if relative_output:
        status_command.extend(["--", ".", f":(exclude){relative_output}",
                               f":(exclude){relative_output}/**"])
    final_clean = not subprocess.check_output(status_command, text=True).strip()
    result = {"schema_version": 1, "status": "PASS" if all(
              row["exit_code"] == 0 and host_log_matches_contract(row["test"], row)
              for row in records)
              and initial_revision == final_revision and initial_clean and final_clean else "FAIL",
              "source_revision": final_revision,
              "source_clean": initial_clean and final_clean,
              "scope": "Host-regression-only", "functional_hil": "NOT_RUN", "records": records}
    _write_new_json(output / "result.json", result)
    return result


def main() -> int:
    """! @brief 읽기·검사·Host 실행만 제공하며 flash·공개·원장 수정을 하지 않습니다. """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("snapshot", "validate", "host", "risks",
                            "qualification", "assemble", "export-closure")
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--host-regression", type=Path)
    parser.add_argument("--soak", type=Path)
    parser.add_argument("--campaign-evidence", action="append", default=[])
    parser.add_argument("--campaign-matrix", type=Path)
    parser.add_argument("--sdk-risk-evidence", action="append", default=[])
    parser.add_argument("--qualification-evidence", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "host":
            require(args.output is not None, "Host output directory required")
            result = run_host(args.output)
        elif args.command == "risks":
            require(args.output is not None and args.campaign_matrix is not None,
                    "SDK risk output bundle and campaign matrix required")
            result = produce_sdk_risks(args.campaign_matrix, args.output)
        elif args.command == "qualification":
            require(args.output is not None,
                    "qualification JSON output required")
            result = produce_qualification(args.output)
        elif args.command == "export-closure":
            require(args.manifest is not None and args.output is not None,
                    "closure manifest and public export directory required")
            result = export_closure(args.manifest, args.output)
        elif args.command == "assemble":
            require(args.output is not None and
                    args.host_regression is not None and args.soak is not None and
                    args.qualification_evidence is not None,
                    "closure assembly inputs and output required")
            require(not (args.campaign_evidence and args.campaign_matrix is not None),
                    "use either named campaign evidence or one campaign matrix")
            campaign_evidence = _named_paths(args.campaign_evidence, True)
            if args.campaign_matrix is not None:
                current = snapshot()
                campaign_evidence = campaign_matrix_paths(
                    args.campaign_matrix, current["source_revision"]
                )
            result = assemble_closure(
                args.output,
                args.host_regression,
                args.soak,
                campaign_evidence,
                _named_paths(args.sdk_risk_evidence, False),
                args.qualification_evidence,
            )
        else:
            current = snapshot()
            if args.command == "validate":
                require(args.manifest is not None, "closure manifest required")
                result = validate_closure(read_json(args.manifest), args.manifest.resolve().parent, current)
            else:
                result = current
            if args.output:
                require(not args.output.exists(), "existing evidence is never overwritten")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result_status = result.get("status", "ASSEMBLED")
        result_scope = result.get("scope", "m33-w06-closure")
        print(json.dumps({"status": result_status, "scope": result_scope,
                          "output": str(args.output) if args.output else None}))
        return int(result_status == "FAIL")
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"M33 regression rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
