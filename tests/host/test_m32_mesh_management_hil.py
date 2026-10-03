#!/usr/bin/env python3
"""! @brief M32-W07 Mesh 1.1 세 역할 HIL target 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_mesh_management_run as runner  # noqa: E402


class M32MeshManagementHilTests(unittest.TestCase):
    """! @brief Remote Provisioning·일곱 기능군·negative 분모를 고정합니다. """

    def test_runner_parser_rejects_duplicate_and_invalid_integer(self) -> None:
        """! @brief protocol 중복 field와 decimal 외 입력을 거부합니다. """
        fields = runner._fields(
            "M32MESH11|1|RESULT|role=client|operations=350"
        )
        self.assertEqual(350, runner._integer(fields, "operations"))
        with self.assertRaisesRegex(runner.MeshManagementFailure, "duplicate"):
            runner._fields("M32MESH11|1|RESULT|operations=350|operations=351")
        with self.assertRaisesRegex(runner.MeshManagementFailure, "invalid integer"):
            runner._integer({"operations": "x"}, "operations")

    def test_capacity_preflight_accounts_for_local_provisioner(self) -> None:
        """! @brief PB-Remote 두 node와 Subnet Bridge 두 subnet 용량을 고정합니다. """
        fields = {
            "cdb_node_slots": "3",
            "cdb_local_slots": "1",
            "cdb_subnets": "2",
            "cdb_app_keys": "2",
            "local_subnets": "2",
            "local_app_keys": "2",
            "model_app_keys": "2",
        }
        capacity = runner._validate_capacity(fields)
        self.assertEqual(2, capacity["cdb_remote_capacity"])

        fields["cdb_node_slots"] = "2"
        with self.assertRaisesRegex(
            runner.MeshManagementFailure, "remote node capacity mismatch"
        ):
            runner._validate_capacity(fields)

        fields["cdb_node_slots"] = "3"
        fields["local_subnets"] = "1"
        with self.assertRaisesRegex(
            runner.MeshManagementFailure, "local_subnets"
        ):
            runner._validate_capacity(fields)

    def test_runner_rejects_target_stack_fault_without_waiting_for_timeout(self) -> None:
        """! @brief UART stack fault를 900초 session timeout으로 숨기지 않습니다. """
        with self.assertRaisesRegex(
            runner.MeshManagementFailure, "server target fault"
        ):
            runner._reject_target_fault("server", "Stack overflow (context invalid)")
        runner._reject_target_fault("server", "ordinary boot diagnostic")

    def test_hil_source_covers_remote_provisioning_and_management_denominator(self) -> None:
        """! @brief 세 역할 target가 실제 PB-Remote와 350회 관리 경로를 포함합니다. """
        source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_management_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "iteration_target = 10U",
            "operation_target = 350U",
            "startRemoteScan",
            "provisionRemote",
            "driveConfiguration",
            "NUCODEMeshManagement.lastDriverError() != -ETIMEDOUT",
            "Model::solicitation_rpl_configuration",
            "exerciseTarget",
            "readLargeComposition",
            "beginOpcodeSequence",
            "setPrivateBeacon",
            "clearSolicitationReplay",
            "setSubnetBridge",
            "malformed_rejected=1",
            "wrong_subnet_rejected=1",
            "M32MESH11|1|STOP|nonce=",
        ):
            self.assertIn(token, source)

    def test_hil_configuration_enables_seven_feature_groups(self) -> None:
        """! @brief target Kconfig가 W07 일곱 관리 기능군을 모두 활성화합니다. """
        configuration = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_management_hil" / "prj.conf"
        ).read_text(encoding="utf-8")
        for symbol in (
            "CONFIG_BT_MESH_CDB_NODE_COUNT=3",
            "CONFIG_BT_MESH_CDB_SUBNET_COUNT=2",
            "CONFIG_BT_MESH_SUBNET_COUNT=2",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4800",
            "CONFIG_BT_RX_STACK_SIZE=5120",
            "CONFIG_BT_MESH_SETTINGS_WORKQ_STACK_SIZE=1700",
            "CONFIG_BT_MESH_ADV_STACK_SIZE=4000",
            "CONFIG_MAIN_STACK_SIZE=8192",
            "CONFIG_BT_MESH_RPR_CLI=y",
            "CONFIG_BT_MESH_RPR_SRV=y",
            "CONFIG_BT_MESH_SAR_CFG_CLI=y",
            "CONFIG_BT_MESH_OP_AGG_CLI=y",
            "CONFIG_BT_MESH_LARGE_COMP_DATA_CLI=y",
            "CONFIG_BT_MESH_PRIV_BEACON_CLI=y",
            "CONFIG_BT_MESH_SOL_PDU_RPL_CLI=y",
            "CONFIG_BT_MESH_PROXY_SOLICITATION=y",
            "CONFIG_BT_MESH_BRG_CFG_CLI=y",
        ):
            self.assertIn(symbol, configuration)

    def test_native_group_builds_all_roles(self) -> None:
        """! @brief v0.6.0 native 회귀가 client·server·target을 함께 빌드합니다. """
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.mesh_management_hil.client",
            "nucode.m32.mesh_management_hil.server",
            "nucode.m32.mesh_management_hil.target",
        ):
            self.assertIn(suite, source)

    def test_runner_is_v2_only_and_fail_closed(self) -> None:
        """! @brief exact runner가 V2 identity·sector flash·clean source를 강제합니다. """
        source = (HIL / "m32_mesh_management_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertIn("cmsis_dap_v1=False", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertIn('"M32-MESH11-01:management"', source)
        self.assertIn("clean source commit", source)
        self.assertIn("_validate_capacity", source)

    def test_target_waits_for_both_provisioning_links_to_close(self) -> None:
        """! @brief PB-ADV와 PB-Remote 종료 전에 관리 요청을 시작하지 않습니다. """
        source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_management_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("Event::provisioning_link_closed", source)
        self.assertIn("provisioning_links_closed < 2U", source)
        self.assertIn("management_not_before_ms", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
