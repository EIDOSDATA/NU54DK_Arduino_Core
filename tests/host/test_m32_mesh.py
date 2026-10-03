"""! @brief M32-W06 Bluetooth Mesh 공개·자원·예제 계약을 검사합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries/NUCODE_BLE_Mesh"


class M32MeshContractTests(unittest.TestCase):
    """! @brief Mesh API가 raw Zephyr type 없이 bounded lifecycle을 유지하는지 검사합니다. """

    def test_public_header_has_provisioning_roles_and_standard_models(self) -> None:
        """! @brief W06 공개 기능군과 callback 경계를 전부 요구합니다. """
        header = (LIBRARY / "src/NUCODE_BLE_Mesh.h").read_text(encoding="utf-8")
        required = (
            "enum class Role", "enum class Bearer", "enum class Feature",
            "enableProvisioning", "cancelProvisioning", "provision(", "reset()",
            "friend_node", "low_power_node", "gatt_proxy",
            "configureAppKey", "bindModel", "subscribeModel", "readHealthFaults",
            "configurePublication", "struct Publication",
            "updateKeys", "transitionKeyRefresh", "KeyRefreshTransition",
            "sendOnOff", "sendLevel", "sendLightness",
            "generic_on_off_server", "setLocalOnOff", "localOnOff",
            "requestSensor", "requestTime", "recallScene", "requestSchedule",
            "payload_capacity = 32U", "droppedEvents", "lastDriverError",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, header)
        self.assertNotIn("struct bt_", header)
        self.assertNotIn("#include <zephyr/", header)

    def test_backend_uses_fixed_queue_settings_and_real_mesh_calls(self) -> None:
        """! @brief callback 복사와 PB-ADV/PB-GATT·role API가 실제 stack에 연결됩니다. """
        backend = (LIBRARY / "src/NUCODE_BLE_Mesh.cpp").read_text(encoding="utf-8")
        for token in (
            "K_MSGQ_DEFINE(event_queue", "k_msgq_put", "k_msgq_get",
            "bt_mesh_init", "settings_load", "nucode_ble_note_settings_loaded",
            "SETTINGS_STATIC_HANDLER_DEFINE(nucode_mesh_sseq_compat",
            "SETTINGS_STATIC_HANDLER_DEFINE(nucode_mesh_srpl_compat",
            "bt_mesh_provision_adv",
            "bt_mesh_provision_gatt", "bt_mesh_prov_disable", "bt_mesh_reset",
            "bt_mesh_cdb_clear", "initializeProvisioner(mesh_context.configuration)",
            "clearInactiveProvisionerDatabase", "BT_MESH_CDB_VALID",
            "bt_mesh_cdb_subnet_get(BT_MESH_NET_PRIMARY) == nullptr",
            "bt_mesh_relay_set", "bt_mesh_friend_set", "bt_mesh_lpn_set",
            "bt_mesh_gatt_proxy_set", "bt_mesh_model_send",
            "bt_mesh_cfg_cli_app_key_add", "bt_mesh_cfg_cli_mod_app_bind",
            "bt_mesh_cfg_cli_mod_sub_add", "bt_mesh_health_cli_fault_get",
            "bt_mesh_cfg_cli_mod_pub_set",
            "bt_mesh_app_key_add",
            "bt_mesh_app_key_exists", "BT_MESH_KEY_UNUSED",
            "node_address == mesh_context.configuration.local_address",
            "bt_mesh_model_elem(native_model)",
            "element_address != native_element->rt->addr",
            "bt_mesh_model_find(native_element, model_id)",
            "bindLocalModel(native_model, app_key_index)",
            "sendOnOff(destination, enabled, acknowledged, transaction_id)",
            "bt_mesh_subnet_update", "bt_mesh_app_key_update",
            "bt_mesh_cfg_cli_net_key_update", "bt_mesh_cfg_cli_app_key_update",
            "bt_mesh_cfg_cli_krp_set", "bt_mesh_subnet_kr_phase_set",
        ):
            with self.subTest(token=token):
                self.assertIn(token, backend)
        self.assertNotIn("return handler->h_set", backend)
        self.assertNotIn("new ", backend)
        self.assertNotIn("malloc(", backend)

    def test_feature_configuration_covers_mesh_security_and_resource_bounds(self) -> None:
        """! @brief 설정 저장·segmentation·역할 queue 상한을 고정합니다. """
        configuration = (LIBRARY / "zephyr/mesh-base.conf").read_text(encoding="utf-8")
        for setting in (
            "CONFIG_BT_MESH=y", "CONFIG_BT_MESH_PB_ADV=y",
            "CONFIG_BT_MESH_PB_GATT=y", "CONFIG_BT_MESH_PB_GATT_CLIENT=y",
            "CONFIG_BT_MESH_PROVISIONER=y", "CONFIG_BT_MESH_CDB_NODE_COUNT=3",
            "CONFIG_BT_MESH_CDB_SUBNET_COUNT=1",
            "CONFIG_BT_MESH_CDB_APP_KEY_COUNT=2",
            "CONFIG_BT_MESH_SUBNET_COUNT=1", "CONFIG_BT_MESH_APP_KEY_COUNT=2",
            "CONFIG_BT_MESH_MODEL_KEY_COUNT=2",
            "CONFIG_BT_MESH_CDB_KEY_SYNC=y",
            "CONFIG_BT_MESH_RELAY=y", "CONFIG_BT_MESH_FRIEND=y",
            "CONFIG_BT_MESH_LOW_POWER=y", "CONFIG_BT_MESH_GATT_PROXY=y",
            "CONFIG_BT_MESH_TX_SEG_MAX=16", "CONFIG_BT_MESH_RX_SEG_MAX=16",
            "CONFIG_BT_BUF_ACL_TX_COUNT=8", "CONFIG_BT_BUF_ACL_RX_COUNT_EXTRA=7",
            "CONFIG_BT_SETTINGS=y", "CONFIG_SETTINGS_ZMS=y",
            "CONFIG_NUCODE_BLE_MESH_EVENT_QUEUE_SIZE=16",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, configuration)

    def test_local_secondary_elements_bind_every_composite_model(self) -> None:
        """! @brief local 보조 element의 BLOB·DFU·관리 model 전체를 bind합니다. """
        backend = (LIBRARY / "src/NUCODE_BLE_Mesh.cpp").read_text(encoding="utf-8")
        local_start = backend.index("const struct bt_mesh_elem *native_element")
        remote_start = backend.index("const auto bind =", local_start)
        local_binding = backend[local_start:remote_start]
        for model_id in (
            "BT_MESH_MODEL_ID_BLOB_CLI",
            "BT_MESH_MODEL_ID_BLOB_SRV",
            "BT_MESH_MODEL_ID_DFU_CLI",
            "BT_MESH_MODEL_ID_DFU_SRV",
            "BT_MESH_MODEL_ID_DFD_SRV",
            "BT_MESH_MODEL_ID_SOL_PDU_RPL_CLI",
            "BT_MESH_MODEL_ID_SOL_PDU_RPL_SRV",
        ):
            with self.subTest(model_id=model_id):
                self.assertIn(model_id, local_binding)
        self.assertIn("element_address != native_element->rt->addr", local_binding)

    def test_provisioner_capacity_profile_scales_all_mesh_key_stores(self) -> None:
        """! @brief CDB와 local/model key 한계를 함께 확장하고 node slot 의미를 고정합니다. """
        example = LIBRARY / "examples/MeshProvisioner"
        declaration = json.loads(
            (example / "nucode-build.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            declaration["capacities"],
            {
                "mesh.cdb-node-slots": 33,
                "mesh.cdb-subnets": 4,
                "mesh.cdb-app-keys": 8,
                "mesh.local-subnets": 4,
                "mesh.local-app-keys": 8,
                "mesh.model-app-keys": 4,
            },
        )
        configuration = (example / "prj.conf").read_text(encoding="utf-8")
        for setting in (
            "CONFIG_BT_MESH_CDB_NODE_COUNT=33",
            "CONFIG_BT_MESH_CDB_SUBNET_COUNT=4",
            "CONFIG_BT_MESH_CDB_APP_KEY_COUNT=8",
            "CONFIG_BT_MESH_SUBNET_COUNT=4",
            "CONFIG_BT_MESH_APP_KEY_COUNT=8",
            "CONFIG_BT_MESH_MODEL_KEY_COUNT=4",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, configuration)

    def test_all_twelve_mesh_examples_are_public_and_registered(self) -> None:
        """! @brief W06 계획의 12개 예제를 metadata와 정확히 맞춥니다. """
        expected = {
            "MeshProvisioner", "MeshNode", "MeshHealth", "MeshRelay", "MeshFriend",
            "MeshLowPowerNode", "MeshProxy", "MeshOnOff", "MeshLevel", "MeshLight",
            "MeshSensor", "MeshTimeSceneScheduler",
        }
        actual = {path.parent.name for path in (LIBRARY / "examples").glob("*/*.ino")}
        self.assertEqual(actual, expected)
        metadata = json.loads((ROOT / "libraries/example-metadata.json").read_text(encoding="utf-8"))
        registered = {
            identity.split("/", 1)[1] for identity in metadata["examples"]
            if identity.startswith("NUCODE_BLE_Mesh/")
        }
        self.assertEqual(registered, expected)


if __name__ == "__main__":
    unittest.main()
