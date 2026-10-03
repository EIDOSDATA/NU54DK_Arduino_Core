#!/usr/bin/env python3
"""! @brief M32-W08 signed Mesh DFU HIL 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_mesh_dfu_run as runner  # noqa: E402


class M32MeshDfuHilTests(unittest.TestCase):
    """! @brief 5회·10 target·서명·rollback·V2 안전장치를 고정합니다. """

    def test_capacity_preflight_accounts_for_local_distributor(self) -> None:
        """! @brief local Distributor를 제외한 두 remote Target slot을 요구합니다. """

        capacity = runner.validate_capacity(
            {"cdb_node_slots": "3", "cdb_local_slots": "1"}
        )
        self.assertEqual(2, capacity["cdb_remote_capacity"])
        with self.assertRaisesRegex(runner.MeshDfuFailure, "capacity mismatch"):
            runner.validate_capacity(
                {"cdb_node_slots": "2", "cdb_local_slots": "1"}
            )

    def test_runner_rejects_target_stack_fault(self) -> None:
        """! @brief UART fault를 장시간 timeout으로 숨기지 않습니다. """

        with self.assertRaisesRegex(runner.MeshDfuFailure, "target fault"):
            runner.reject_target_fault("target_a", "Fatal error")

    def test_mcuboot_version_parser(self) -> None:
        """! @brief MCUboot v1 header에서 exact semantic version을 읽습니다. """

        header = bytearray(32)
        struct.pack_into("<I", header, 0, runner.MCUBOOT_MAGIC)
        struct.pack_into("<H", header, 8, 0x800)
        struct.pack_into("<BBHI", header, 20, 2, 3, 4, 5)
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "signed.bin"
            image.write_bytes(header)
            self.assertEqual(runner.parse_mcuboot_version(image), (2, 3, 4, 5))

    def test_final_result_denominators_and_negatives(self) -> None:
        """! @brief 5회·10 target와 세 image negative를 모두 요구합니다. """

        candidate = runner.ImageInput(
            Path("candidate.bin"), 343280, "a" * 64, runner.CANDIDATE_VERSION
        )
        result = {
            "iterations": "5",
            "targets": "10",
            "image_size": str(candidate.size),
            "wrong_key_rejected": "1",
            "wrong_image_rejected": "1",
            "partial_image_rejected": "1",
            "version": "2.0.0+0",
            "signed_sha256": candidate.sha256,
        }
        runner.validate_final_result(result, {"status": "pass"}, candidate)
        with self.assertRaisesRegex(runner.MeshDfuFailure, "targets"):
            runner.validate_final_result({**result, "targets": "9"}, {"status": "pass"}, candidate)

    def test_target_source_covers_signed_distribution_and_rollback(self) -> None:
        """! @brief 세 역할 target가 5회 배포·confirm·rollback 경계를 포함합니다. """

        source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "distribution_iteration_target = 5U",
            "provisioning_links_closed < 2U",
            "provisioning_attempt_limit = 6U",
            "provisioning_pending = false;",
            "NUCODEMesh.lastDriverError() == -ETIMEDOUT",
            "NUCODEMeshUpdate.startDistribution",
            "NUCODEMeshUpdate.confirmRunningImage",
            "bt_mesh_dfu_srv_applied",
            '"wrong_image_accept"',
            '"partial_image_accept"',
            "wrong_key_rejected",
            "M32MDFU|1|APPLY|nonce=",
            "M32MDFU|1|NEXT|nonce=",
            'Serial.print("|RESULT|role=distributor|iterations=5|targets=10',
            "partial_image_size_limit = 4096U",
            "distribution.preserve_composition = false;",
            "BT_MESH_DFU_EFFECT_UNPROV",
            "settings_save_one(role_setting",
        ):
            self.assertIn(token, source)

        candidate = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "src"
            / "candidate.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "boot_write_img_confirmed",
            'settings_load_subtree_direct("m32mdfu"',
            'Serial.print("|BOOT|role=")',
            'Serial.print("|APPLIED|role=")',
            'Serial.print("|STOPPED|role=")',
        ):
            self.assertIn(token, candidate)

        candidate_configuration = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "candidate.conf"
        ).read_text(encoding="utf-8")
        self.assertNotIn("CONFIG_BT=y", candidate_configuration)

    def test_apply_reboots_and_timeout_covers_bounded_mesh_transfer(self) -> None:
        """! @brief Apply 응답 뒤 재부팅과 3시간 유한 실행 상한을 고정합니다. """

        update_source = (
            REPOSITORY
            / "libraries"
            / "NUCODE_BLE_Mesh_Update"
            / "src"
            / "NUCODE_BLE_Mesh_Update.cpp"
        ).read_text(encoding="utf-8")
        target_source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        runner_source = (HIL / "m32_mesh_dfu_run.py").read_text(encoding="utf-8")
        self.assertIn("sys_reboot(SYS_REBOOT_WARM);", update_source)
        self.assertIn("boot_is_img_confirmed()", update_source)
        self.assertIn("BT_MESH_DFU_PHASE_APPLYING", update_source)
        self.assertIn("bt_mesh_dfu_srv_applied", update_source)
        self.assertIn("session_timeout_ms = 10800000", target_source)
        self.assertIn('default=10800.0', runner_source)
        self.assertIn('args.result_timeout <= 10800.0', runner_source)

    def test_hil_configuration_has_two_remote_node_capacity_and_stack_budget(self) -> None:
        """! @brief 세 보드 topology와 Mesh worker stack 예산을 고정합니다. """

        configuration_root = REPOSITORY / "tests" / "zephyr" / "m32_mesh_dfu_hil"
        configuration = (
            (configuration_root / "prj.conf").read_text(encoding="utf-8")
            + (configuration_root / "mesh.conf").read_text(encoding="utf-8")
        )
        for token in (
            "CONFIG_BT_MESH_CDB_NODE_COUNT=3",
            "CONFIG_BT_MESH_LPN_AUTO=n",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4800",
            "CONFIG_BT_MESH_SETTINGS_WORKQ_STACK_SIZE=1700",
            "CONFIG_BT_MESH_ADV_STACK_SIZE=4000",
            "CONFIG_MAIN_STACK_SIZE=8192",
        ):
            self.assertIn(token, configuration)

    def test_runner_is_v2_only_exact_sector_and_clean(self) -> None:
        """! @brief V1·mass erase·recover 없이 exact clean V2 경로만 허용합니다. """

        source = (HIL / "m32_mesh_dfu_run.py").read_text(encoding="utf-8")
        for token in (
            '"cmsis_dap.prefer_v1=false"',
            '"auto_unlock=false"',
            '"--connect",\n        "attach"',
            'cmsis_dap_v1=False',
            "preserve_nrf54l_access=True",
            "defer_reset=True",
            "clear_nrf54l_rram_pyocd",
            "access_preserving_reset",
            '"--sector"',
            '"--erase",\n            "sector"',
            "validate_source_clean",
            '"M32-MDFU-01:primary"',
            '"rollback": "observed"',
            'failure_evidence["failure"]',
            "save_attempt(",
        ):
            self.assertIn(token, source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertNotIn("prefer_v1=true", source)
        self.assertNotIn('"under-reset"', source)
        self.assertNotIn('"--method", "hw"', source)
        self.assertNotIn("software_reset_barrier", source)
        self.assertNotIn("--erase chip", source)
        self.assertNotIn('"recover"', source.casefold())
        self.assertNotIn("--recover", source.casefold())

    def test_native_group_builds_all_four_roles(self) -> None:
        """! @brief native 회귀가 Distributor·두 Target·candidate를 모두 빌드합니다. """

        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.mesh_dfu_hil.distributor",
            "nucode.m32.mesh_dfu_hil.target_a",
            "nucode.m32.mesh_dfu_hil.target_b",
            "nucode.m32.mesh_dfu_hil.candidate",
        ):
            self.assertIn(suite, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
