"""! @brief M32-W07 Bluetooth Mesh 1.1 관리 공개·자원·예제 계약을 검사합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries/NUCODE_BLE_Mesh_Management"


class M32MeshManagementContractTests(unittest.TestCase):
    """! @brief Mesh 1.1 관리 API가 bounded 공개 경계를 유지하는지 검사합니다. """

    def test_public_header_covers_all_w07_families_without_zephyr_types(self) -> None:
        """! @brief 일곱 기능군의 공개 호출과 유한 결과 구조를 요구합니다. """
        header = (LIBRARY / "src/NUCODE_BLE_Mesh_Management.h").read_text(
            encoding="utf-8"
        )
        required = (
            "startRemoteScan", "stopRemoteScan", "closeRemoteLink", "provisionRemote",
            "getSarTransmitter", "setSarTransmitter", "getSarReceiver", "setSarReceiver",
            "beginOpcodeSequence", "opcodeSequenceTailroom", "sendOpcodeSequence",
            "abortOpcodeSequence", "readLargeComposition", "readModelsMetadata",
            "setPrivateBeacon", "setPrivateGattProxy", "setPrivateNodeIdentity",
            "setOnDemandPrivateProxy", "solicit", "clearSolicitationReplay",
            "setSubnetBridge", "addBridgeEntry", "removeBridgeEntry",
            "app_key_index = 0U",
            "advertising_capacity = 31U", "capacity = 64U", "droppedEvents",
            "remote_device_key_index = 0xFFFDU",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, header)
        self.assertNotIn("struct bt_", header)
        self.assertNotIn("#include <zephyr/", header)

    def test_backend_calls_fixed_sdk_apis_and_uses_bounded_queue(self) -> None:
        """! @brief 공개 호출을 fixed NCS v3.4.0 API와 직접 연결합니다. """
        backend = (LIBRARY / "src/NUCODE_BLE_Mesh_Management.cpp").read_text(
            encoding="utf-8"
        )
        required = (
            "K_MSGQ_DEFINE(management_event_queue", "bt_mesh_rpr_scan_start",
            "bt_mesh_rpr_scan_stop", "bt_mesh_rpr_link_close",
            "bt_mesh_provision_remote", "bt_mesh_sar_cfg_cli_transmitter_set",
            "bt_mesh_sar_cfg_cli_receiver_set", "bt_mesh_op_agg_cli_seq_start",
            "bt_mesh_op_agg_cli_seq_send", "bt_mesh_op_agg_cli_seq_abort",
            "bt_mesh_op_agg_cli_seq_is_started() ? nullptr : &response",
            "bt_mesh_large_comp_data_get", "bt_mesh_models_metadata_get",
            "bt_mesh_priv_beacon_cli_set", "bt_mesh_od_priv_proxy_cli_set",
            "bt_mesh_proxy_solicit", "bt_mesh_sol_pdu_rpl_clear",
            "context.app_idx = target.app_key_index",
            "bt_mesh_brg_cfg_cli_set", "bt_mesh_brg_cfg_cli_table_add",
            "bt_mesh_brg_cfg_cli_table_remove",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, backend)
        self.assertNotIn("new ", backend)
        self.assertNotIn("malloc(", backend)

    def test_management_profile_has_bounded_server_resources(self) -> None:
        """! @brief scan·metadata·SRPL·bridge table 상한과 client/server를 고정합니다. """
        configuration = (LIBRARY / "zephyr/mesh-management.conf").read_text(
            encoding="utf-8"
        )
        for setting in (
            "CONFIG_BT_MESH_RPR_CLI=y", "CONFIG_BT_MESH_RPR_SRV=y",
            "CONFIG_BT_MESH_RPR_SRV_SCANNED_ITEMS_MAX=4",
            "CONFIG_BT_MESH_SAR_CFG_CLI=y", "CONFIG_BT_MESH_SAR_CFG_SRV=y",
            "CONFIG_BT_MESH_OP_AGG_CLI=y", "CONFIG_BT_MESH_OP_AGG_SRV=y",
            "CONFIG_BT_MESH_LARGE_COMP_DATA_CLI=y",
            "CONFIG_BT_MESH_LARGE_COMP_DATA_SRV=y",
            "CONFIG_BT_MESH_MODELS_METADATA_PAGE_LEN=150",
            "CONFIG_BT_MESH_PRIV_BEACON_CLI=y", "CONFIG_BT_MESH_PRIV_BEACON_SRV=y",
            "CONFIG_BT_MESH_OD_PRIV_PROXY_CLI=y", "CONFIG_BT_MESH_OD_PRIV_PROXY_SRV=y",
            "CONFIG_BT_MESH_SOL_PDU_RPL_CLI=y", "CONFIG_BT_MESH_PROXY_SOLICITATION=y",
            "CONFIG_BT_MESH_PROXY_SRPL_SIZE=10",
            "CONFIG_BT_MESH_BRG_CFG_CLI=y", "CONFIG_BT_MESH_BRG_CFG_SRV=y",
            "CONFIG_BT_MESH_BRG_TABLE_ITEMS_MAX=16",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, configuration)

    def test_all_thirteen_management_examples_are_registered(self) -> None:
        """! @brief W07 계획의 13개 예제를 metadata와 정확히 맞춥니다. """
        expected = {
            "MeshRemoteProvisioner", "MeshRemoteProvisioningServer",
            "MeshSarConfigurationClient", "MeshSarConfigurationServer",
            "MeshOpcodeAggregatorClient", "MeshOpcodeAggregatorServer",
            "MeshLargeCompositionDataClient", "MeshLargeCompositionDataServer",
            "MeshPrivateBeaconClient", "MeshPrivateBeaconServer",
            "MeshOnDemandPrivateProxy", "MeshProxySolicitation", "MeshSubnetBridge",
        }
        actual = {path.parent.name for path in (LIBRARY / "examples").glob("*/*.ino")}
        self.assertEqual(actual, expected)
        metadata = json.loads(
            (ROOT / "libraries/example-metadata.json").read_text(encoding="utf-8")
        )
        registered = {
            identity.split("/", 1)[1] for identity in metadata["examples"]
            if identity.startswith("NUCODE_BLE_Mesh_Management/")
        }
        self.assertEqual(registered, expected)


if __name__ == "__main__":
    unittest.main()
