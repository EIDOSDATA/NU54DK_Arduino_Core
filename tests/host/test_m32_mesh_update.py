"""! @brief M32-W08 Mesh BLOB·DFU 공개·보안·자원 계약을 검사합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries/NUCODE_BLE_Mesh_Update"


class M32MeshUpdateContractTests(unittest.TestCase):
    """! @brief Mesh update가 bounded inactive-slot과 MCUboot 경계를 유지하는지 검사합니다. """

    def test_public_header_covers_blob_dfu_and_rollback_without_zephyr_types(self) -> None:
        """! @brief BLOB·digest·test boot·confirm 공개 경계를 요구합니다. """
        header = (LIBRARY / "src/NUCODE_BLE_Mesh_Update.h").read_text(
            encoding="utf-8"
        )
        for token in (
            "target_capacity = 4U", "prepareBlobReceive", "sendBlob",
            "suspendBlob", "resumeBlob", "cancelBlob", "clientProgress",
            "serverProgress", "expectImageDigest", "verifyStagedDigest",
            "requestTestUpgrade", "confirmRunningImage", "rebootToApply",
            "FirmwareDistribution", "startDistribution", "cancelDistribution",
            "distributionPhase",
        ):
            with self.subTest(token=token):
                self.assertIn(token, header)
        self.assertNotIn("struct bt_", header)
        self.assertNotIn("#include <zephyr/", header)

    def test_backend_uses_fixed_sdk_blob_dfu_and_mcuboot_apis(self) -> None:
        """! @brief fixed NCS v3.4.0 model과 signed test-upgrade API를 직접 연결합니다. """
        backend = (LIBRARY / "src/NUCODE_BLE_Mesh_Update.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)", backend)
        self.assertTrue(backend.rstrip().endswith("#endif"))
        for token in (
            "bt_mesh_blob_io_flash_init", "bt_mesh_blob_srv_recv",
            "bt_mesh_blob_cli_send", "bt_mesh_blob_cli_suspend",
            "bt_mesh_blob_cli_resume", "bt_mesh_blob_cli_cancel",
            "bt_mesh_app_key_exists",
            "bt_mesh_dfu_metadata_decode", "bt_mesh_dfu_srv_verified",
            "bt_mesh_dfu_srv_rejected", "flash_area_check_int_sha256",
            "boot_read_bank_header", "boot_request_upgrade(BOOT_UPGRADE_TEST)",
            "boot_write_img_confirmed", "BT_MESH_DFD_SRV_INIT",
            "bt_mesh_dfu_slot_reserve", "bt_mesh_dfu_slot_commit",
            "bt_mesh_dfd_srv_receiver_add", "bt_mesh_dfd_srv_start",
            "bt_mesh_dfd_srv_cancel",
        ):
            with self.subTest(token=token):
                self.assertIn(token, backend)
        self.assertNotIn("BOOT_UPGRADE_PERMANENT", backend)
        self.assertNotIn("malloc(", backend)
        self.assertNotIn("new ", backend)

    def test_update_models_are_exposed_to_foundation_binding(self) -> None:
        """! @brief provisioner가 update model AppKey binding을 구성할 수 있어야 합니다. """
        mesh_header = (
            ROOT / "libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh.h"
        ).read_text(encoding="utf-8")
        composition = (
            ROOT / "libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh_Composition.c"
        ).read_text(encoding="utf-8")
        for token in (
            "blob_client",
            "blob_server",
            "mesh_dfu_target",
            "firmware_distributor",
        ):
            self.assertIn(token, mesh_header)
        for token in (
            "return &blob_models[0]",
            "return &blob_models[1]",
            "return &dfu_target_models[1]",
            "return &distributor_models[3]",
        ):
            self.assertIn(token, composition)
        mesh_backend = (
            ROOT / "libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "bind(BT_MESH_MODEL_ID_BLOB_SRV)",
            "bind(BT_MESH_MODEL_ID_DFU_SRV)",
            "bind(BT_MESH_MODEL_ID_BLOB_CLI)",
            "bind(BT_MESH_MODEL_ID_DFU_CLI)",
            "bind(BT_MESH_MODEL_ID_DFD_SRV)",
        ):
            self.assertIn(token, mesh_backend)

    def test_internal_profile_has_bounded_transfer_and_storage_resources(self) -> None:
        """! @brief 내부 slot·chunk·target·slot count 상한을 고정합니다. """
        configuration = (LIBRARY / "zephyr/mesh-update.conf").read_text(
            encoding="utf-8"
        )
        for setting in (
            "CONFIG_BT_MESH_BLOB_SIZE_MAX=720896",
            "CONFIG_BT_MESH_BLOB_BLOCK_SIZE_MAX=4096",
            "CONFIG_BT_MESH_BLOB_CHUNK_COUNT_MAX=32",
            "CONFIG_BT_MESH_RX_BLOB_CHUNK_SIZE=128",
            "CONFIG_BT_MESH_TX_BLOB_CHUNK_SIZE=128",
            "CONFIG_BT_MESH_DFU_SLOT_CNT=1",
            "CONFIG_BT_MESH_DFD_SRV_TARGETS_MAX=4",
            "CONFIG_IMG_ENABLE_IMAGE_CHECK=y",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, configuration)

    def test_all_four_update_examples_are_registered_for_signed_profile(self) -> None:
        """! @brief W08의 네 역할 예제와 signed profile metadata를 맞춥니다. """
        expected = {
            "MeshBlobClient", "MeshBlobServer", "MeshDfuTarget",
            "MeshFirmwareDistributor",
        }
        actual = {path.parent.name for path in (LIBRARY / "examples").glob("*/*.ino")}
        self.assertEqual(actual, expected)
        metadata = json.loads(
            (ROOT / "libraries/example-metadata.json").read_text(encoding="utf-8")
        )
        registered = {
            identity.split("/", 1)[1] for identity, record in metadata["examples"].items()
            if identity.startswith("NUCODE_BLE_Mesh_Update/")
            and record["recommended_profile"] == "secure_ble_dfu"
        }
        self.assertEqual(registered, expected)

    def test_external_flash_path_is_a_disabled_user_template(self) -> None:
        """! @brief 미검증 외부 flash가 기본 경로로 활성화되지 않게 합니다. """
        overlay = (LIBRARY / "extras/mesh-update-external-flash.overlay.template").read_text(
            encoding="utf-8"
        )
        guide = (LIBRARY / "extras/외부_flash_적용_안내.md").read_text(encoding="utf-8")
        self.assertIn('status = "disabled";', overlay)
        self.assertIn("NOT_RUN", guide)
        self.assertIn("MCUboot", guide)


if __name__ == "__main__":
    unittest.main()
