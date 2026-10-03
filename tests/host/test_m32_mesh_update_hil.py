#!/usr/bin/env python3
"""! @brief M32-W08 BLOB 세 역할 HIL target 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_mesh_update_run as runner  # noqa: E402
import ble_pair_hil_common as common  # noqa: E402


class M32MeshUpdateHilTests(unittest.TestCase):
    """! @brief BLOB 분모·복구·digest·V2 안전 조건을 고정합니다. """

    def test_capacity_preflight_accounts_for_local_provisioner(self) -> None:
        """! @brief local provisioner를 제외한 두 remote node slot을 요구합니다. """
        fields = {"cdb_node_slots": "3", "cdb_local_slots": "1"}
        capacity = runner._validate_capacity(fields)
        self.assertEqual(2, capacity["cdb_remote_capacity"])
        with self.assertRaisesRegex(runner.MeshUpdateFailure, "capacity mismatch"):
            runner._validate_capacity(
                {"cdb_node_slots": "2", "cdb_local_slots": "1"}
            )

    def test_runner_rejects_target_stack_fault(self) -> None:
        """! @brief UART fault를 장시간 session timeout으로 숨기지 않습니다. """
        with self.assertRaisesRegex(runner.MeshUpdateFailure, "target fault"):
            runner._reject_target_fault("target_a", "Stack overflow")

    def test_role_result_denominators(self) -> None:
        """! @brief client와 target의 정량 결과를 각각 판정합니다. """
        client = {
            "iterations": "10",
            "chunk_size": "128",
            "object_digest": "pass",
            "targets": "2",
            "chunks": "5120",
            "suspend_resume": "pass",
            "wrong_key_rejected": "1",
            "object_size": "32768",
        }
        target = {
            "iterations": "10",
            "chunk_size": "128",
            "object_digest": "pass",
            "chunks": "2560",
            "bad_digest_rejected": "1",
        }
        runner._validate_result("blob_client", client)
        runner._validate_result("target_a", target)
        with self.assertRaisesRegex(runner.MeshUpdateFailure, "chunk/digest"):
            runner._validate_result("target_b", {**target, "chunks": "2559"})

    def test_repeated_identical_result_is_idempotent(self) -> None:
        """! @brief VCOM 재개방 뒤 동일 RESULT는 허용하고 변조는 거부합니다. """
        target = {
            "iterations": "10",
            "chunk_size": "128",
            "object_digest": "pass",
            "chunks": "2560",
            "bad_digest_rejected": "1",
        }
        results: dict[str, dict[str, str]] = {}
        runner._record_result(results, "target_b", target)
        runner._record_result(results, "target_b", dict(target))
        self.assertEqual(target, results["target_b"])
        with self.assertRaisesRegex(runner.MeshUpdateFailure, "repeated RESULT"):
            runner._record_result(
                results, "target_b", {**target, "nonce": "changed"}
            )

    def test_hil_source_covers_blob_transfer_recovery_and_digest(self) -> None:
        """! @brief 세 역할 target가 10회 BLOB·복구·negative를 포함합니다. """
        source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_update_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "object_size = 32768U",
            "recovery_object_size = 8192U",
            "chunk_size = 128U",
            "iteration_target = 10U",
            "provisioning_links_closed < 2U",
            "provisioning_attempt_limit = 6U",
            "configuration_retry_limit = 6U",
            "provisioning_pending = false;",
            "NUCODEMesh.lastDriverError() == -ETIMEDOUT",
            "NUCODEMeshUpdate.sendBlob",
            "NUCODEMeshUpdate.prepareBlobReceive",
            "NUCODEMeshUpdate.suspendBlob",
            "NUCODEMeshUpdate.lastDriverError() == -EBUSY",
            "NUCODEMeshUpdate.resumeBlob",
            "recovery_suspend_after_ms = 10000",
            "server_suspend_settle_ms = 1000",
            "recovery_resume_attempt_limit = 6U",
            "recovery_resume_attempts",
            "recovery_server_timeout_base = 0U",
            "chunk_interval_ms = 100U",
            "transfer_timeout_base = 1U",
            "transfer_ttl = 7U",
            "client_retry_window_ms",
            "10000 * (transfer_timeout_base + 2U) + 100 * transfer_ttl",
            "server_complete_settle_ms =",
            "client_retry_window_ms + 2000",
            "transfer_spacing_ms =",
            "server_complete_settle_ms + 3000",
            "final_result_repeat_ms = 5000",
            "transfer.timeout_base = transfer_timeout_base",
            "transfer.ttl = transfer_ttl",
            "prepareBlobReceive(blob_id, transfer_ttl,",
            "k_uptime_get() < next_receive_ms",
            "next_receive_ms = k_uptime_get() + server_complete_settle_ms",
            "resume_pending",
            "recovery_blob_id = blob_id_base - 1U",
            "driveRecoveryTransfer",
            "transfer.target_count = 1U",
            "transfer.group_address = blob_group_address",
            "transfer.block_size_log = 14U",
            "transfer.block_size_log = 12U",
            "NUCODEMeshUpdate.phase()",
            "NUCODEMeshUpdate.lastDriverError()",
            "NUCODEMeshUpdate.verifyStagedDigest",
            "wrong_key_rejected=1",
            "bad_digest_rejected=1",
            "repeatFinalResult",
            "M32BLOB|1|STOP|nonce=",
        ):
            self.assertIn(token, source)

        backend = (
            REPOSITORY
            / "libraries"
            / "NUCODE_BLE_Mesh_Update"
            / "src"
            / "NUCODE_BLE_Mesh_Update.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "bt_mesh_blob_cli_suspend(&nucode_mesh_blob_client_instance)", backend
        )
        self.assertNotIn("nucode_mesh_blob_client_instance.tx.sending", backend)

    def test_hil_configuration_has_two_remote_node_capacity_and_stack_budget(self) -> None:
        """! @brief 세 보드 topology·stack·signed sysbuild 예산을 고정합니다. """
        application = REPOSITORY / "tests" / "zephyr" / "m32_mesh_update_hil"
        configuration = (application / "prj.conf").read_text(encoding="utf-8")
        for token in (
            "CONFIG_BT_MESH_CDB_NODE_COUNT=3",
            "CONFIG_BT_MESH_LPN_AUTO=n",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4800",
            "CONFIG_BT_RX_STACK_SIZE=8192",
            "CONFIG_BT_MESH_SETTINGS_WORKQ_STACK_SIZE=1700",
            "CONFIG_BT_MESH_ADV_STACK_SIZE=4000",
            "CONFIG_MAIN_STACK_SIZE=8192",
            'CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION="0.0.0+0"',
            'CONFIG_MCUBOOT_EXTRA_IMGTOOL_ARGS="--security-counter 1"',
            "CONFIG_BT_MESH_BLOB_BLOCK_SIZE_MAX=16384",
            "CONFIG_BT_MESH_BLOB_CHUNK_COUNT_MAX=128",
            "CONFIG_BT_MESH_NETWORK_TRANSMIT_COUNT=2",
        ):
            self.assertIn(token, configuration)
        testcase = (application / "testcase.yaml").read_text(encoding="utf-8")
        sysbuild = (application / "sysbuild.conf").read_text(encoding="utf-8")
        bootloader = (application / "sysbuild/mcuboot.conf").read_text(
            encoding="utf-8"
        )
        self.assertEqual(testcase.count("sysbuild: true"), 3)
        self.assertIn("SB_CONFIG_BOOTLOADER_MCUBOOT=y", sysbuild)
        self.assertIn("SB_CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y", sysbuild)
        self.assertIn("CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y", bootloader)
        self.assertIn("CONFIG_MCUBOOT_DOWNGRADE_PREVENTION=y", bootloader)

    def test_native_group_builds_all_roles(self) -> None:
        """! @brief v0.6.0 native 회귀가 client와 두 target을 빌드합니다. """
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.mesh_update_hil.blob_client",
            "nucode.m32.mesh_update_hil.target_a",
            "nucode.m32.mesh_update_hil.target_b",
        ):
            self.assertIn(suite, source)

    def test_runner_is_v2_only_and_partial_scope_is_explicit(self) -> None:
        """! @brief runner가 V2 exact 안전장치와 BLOB traffic 범위만 기록합니다. """
        source = (HIL / "m32_mesh_update_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertIn("cmsis_dap_v1=False", source)
        self.assertIn("reset_target_pyocd", source)
        self.assertIn("clear_nrf54l_rram_pyocd", source)
        self.assertIn("defer_reset=True", source)
        self.assertIn('"zephyr.signed.hex"', source)
        self.assertIn('"mcuboot" / "zephyr" / "zephyr.hex"', source)
        self.assertIn("def _read_protocol_line(", source)
        self.assertNotIn("_line(ports[role]", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertNotIn("prefer_v1=true", source)
        self.assertIn('"M32-BLOB-01:traffic"', source)
        self.assertNotIn('"M32-MDFU-01"', source)
        self.assertIn("clean source commit", source)
        self.assertNotIn("--erase chip", source)

    def test_deferred_flash_halts_without_reset(self) -> None:
        """! @brief sysbuild 두 image를 기록하는 동안 target를 정지 상태로 유지합니다. """

        completed = SimpleNamespace(
            returncode=0, stdout=b"programmed 4096 bytes", stderr=b""
        )
        with patch.object(common.subprocess, "run", return_value=completed) as run:
            result = common.flash_image_pyocd(
                "blob",
                "a" * 32,
                Path("signed.hex"),
                120.0,
                preserve_nrf54l_access=True,
                defer_reset=True,
            )
        self.assertEqual(("pyocd-sector-no-reset", "4096"), result)
        self.assertEqual(1, run.call_count)
        command = run.call_args.args[0]
        self.assertEqual("halt", command[command.index("--connect") + 1])
        self.assertIn("--no-reset", command)

    def test_rram_clear_writes_and_verifies_exact_range(self) -> None:
        """! @brief nRF54L RRAM erase emulation은 0xFF 기록과 전 word 검증을 요구합니다. """

        completed = SimpleNamespace(
            returncode=0,
            stdout=b" ".join([b"ffffffff"] * 64),
            stderr=b"",
        )
        with patch.object(common.subprocess, "run", return_value=completed) as run:
            evidence = common.clear_nrf54l_rram_pyocd(
                "blob", "a" * 32, 0x174000, 0x100, 120.0
            )
        self.assertEqual("nrf54l-rram-fill-verified", evidence["mode"])
        self.assertEqual(64, evidence["verified_words"])
        command = run.call_args.args[0]
        commands = run.call_args.kwargs["input"]
        self.assertEqual("halt", command[command.index("--connect") + 1])
        self.assertIn(b"write32 0x5004b500 1", commands)
        self.assertIn(b"fill 32 0x174000 0x100 0xffffffff", commands)
        self.assertIn(b"read32 0x174000 0x100", commands)

    def test_runner_resets_vcom_reopen_budget_after_progress(self) -> None:
        """! @brief VCOM 재연결 횟수를 무응답 구간별로 제한합니다. """
        source = (HIL / "m32_mesh_update_run.py").read_text(encoding="utf-8")
        for token in (
            "reopen_attempts = {role: 0 for role in ROLES}",
            "reopen_attempts[role] = 0",
            "reopen_attempts[role] < 2",
            "VCOM_REOPEN attempt=",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
