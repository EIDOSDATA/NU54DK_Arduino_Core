#!/usr/bin/env python3
"""! @brief M32-W06 Mesh HIL protocol과 V2 exact 실행 계약을 검증합니다. """

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_mesh_run as runner  # noqa: E402


class M32MeshHilTests(unittest.TestCase):
    """! @brief 세 역할 분모·negative·보드 안전 조건을 고정합니다. """

    def test_record_parser_rejects_duplicate_and_invalid_integer(self) -> None:
        """! @brief protocol field 중복과 decimal 외 입력을 거부합니다. """
        fields = runner._fields(
            "M32MESH|1|RESULT|role=provisioner|acknowledged=500"
        )
        self.assertEqual("provisioner", fields["role"])
        self.assertEqual(500, runner._integer(fields, "acknowledged"))
        with self.assertRaisesRegex(runner.MeshExecutionFailure, "duplicate"):
            runner._fields("M32MESH|1|RESULT|acknowledged=500|acknowledged=501")
        with self.assertRaisesRegex(runner.MeshExecutionFailure, "invalid integer"):
            runner._integer({"acknowledged": "-1"}, "acknowledged")

    def test_capacity_preflight_accounts_for_local_provisioner(self) -> None:
        """! @brief node slot에서 local 한 칸을 제외하고 remote 용량을 판정합니다. """
        fields = {
            "cdb_node_slots": "3",
            "cdb_local_slots": "1",
            "cdb_subnets": "1",
            "cdb_app_keys": "2",
            "local_subnets": "1",
            "local_app_keys": "2",
            "model_app_keys": "2",
        }
        capacity = runner._validate_capacity(fields)
        self.assertEqual(2, capacity["cdb_remote_capacity"])

        fields["cdb_node_slots"] = "2"
        with self.assertRaisesRegex(
            runner.MeshExecutionFailure, "remote node capacity mismatch"
        ):
            runner._validate_capacity(fields)

    def test_hil_source_covers_three_roles_traffic_negative_and_stop(self) -> None:
        """! @brief target가 두 node와 500 message·negative·STOP을 노출합니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "base_message_target = 300U",
            "secured_message_target = 200U",
            "node_a_address = 0x0100U",
            "node_b_address = 0x0200U",
            "unprovisioned_rejected",
            "invalid_destination_rejected",
            "wrong_key_rejected",
            "M32MESH|1|STOP|nonce=",
            "bt_mesh_suspend()",
        ):
            self.assertIn(token, source)

    def test_provisioner_collects_both_beacons_before_opening_the_first_link(self) -> None:
        """! @brief 첫 PB-ADV link가 두 번째 node 발견을 막지 않도록 discovery를 먼저 모읍니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        discovery_gate = "if (!node_a_discovered || !node_b_discovered)"
        self.assertIn(discovery_gate, source)
        self.assertLess(source.index(discovery_gate), source.index("NUCODEMesh.provision("))

    def test_provisioner_retries_after_an_asynchronous_link_close(self) -> None:
        """! @brief PB-ADV 비동기 종료 뒤 pending을 해제하고 bounded backoff를 적용합니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("record.event == Event::provisioning_link_closed", source)
        self.assertIn("provisioning_pending = false;", source)
        self.assertIn("next_provisioning_ms = k_uptime_get() + 1000;", source)
        self.assertIn("NUCODEMesh.lastError() == Error::busy", source)

    def test_configuration_waits_for_both_provisioning_links_to_close(self) -> None:
        """! @brief 구성 전송은 두 PB-ADV link 종료와 bearer 정리 시간을 기다립니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("provisioning_links_closed < 2U", source)
        self.assertIn("configuration_not_before_ms = k_uptime_get() + 1500;", source)
        self.assertNotIn(
            "record.event == Event::node_added)\n        {\n            provisioning_pending = false;",
            source,
        )

    def test_acknowledged_traffic_has_bounded_retransmission(self) -> None:
        """! @brief 무선 ACK 손실은 세 번까지만 재전송하고 중복 응답 시간을 분리합니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "message_ack_timeout_ms = 2000",
            "message_retry_limit = 3U",
            "message_response_drain_ms = 50",
            'fail("model_ack_timeout", -ETIMEDOUT)',
            "++message_retries;",
        ):
            self.assertIn(token, source)

    def test_configuration_status_loss_has_bounded_retry(self) -> None:
        """! @brief 멱등 Configuration 작업은 timeout에만 세 번까지 재시도합니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "configuration_retry_limit = 3U",
            "configuration_retry_delay_ms = 500",
            "error == -ETIMEDOUT",
            "++configuration_retries;",
            "retryConfiguration(\"configure_node_a_app_key\")",
        ):
            self.assertIn(token, source)

    def test_exact_runner_uses_v2_sector_flash_and_register_identity(self) -> None:
        """! @brief 세 역할 모두 CMSIS-DAP v2 DP/AP identity를 통과해야 합니다. """
        source = (HIL / "m32_mesh_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertIn("flash_image_pyocd", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertNotIn("prefer_v1=true", source)
        self.assertIn('"M32-MESH-01:traffic"', source)
        self.assertIn('"M32-MESHSEC-01:traffic"', source)
        self.assertNotIn("--erase chip", source)

    def test_runner_requires_twenty_independent_clean_sessions(self) -> None:
        """! @brief host 회차와 target resume/reset 증거 없이는 20회로 승격하지 않습니다. """

        first = runner._validate_cleared(
            "node_a",
            {
                "provisioned": "0",
                "settings_reset": "pass",
                "resumed": "0",
                "unprovisioned_rejected": "1",
            },
            1,
        )
        later = runner._validate_cleared(
            "node_a",
            {
                "provisioned": "0",
                "settings_reset": "pass",
                "resumed": "1",
                "unprovisioned_rejected": "1",
            },
            2,
        )
        self.assertFalse(first["resumed_from_previous_cleanup"])
        self.assertTrue(later["resumed_from_previous_cleanup"])
        with self.assertRaisesRegex(runner.MeshExecutionFailure, "resume mismatch"):
            runner._validate_cleared(
                "node_a",
                {
                    "provisioned": "0",
                    "settings_reset": "pass",
                    "resumed": "0",
                    "unprovisioned_rejected": "1",
                },
                2,
            )
        target = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        host = (HIL / "m32_mesh_run.py").read_text(encoding="utf-8")
        self.assertLess(target.index("bt_mesh_resume()"), target.index("NUCODEMesh.reset()"))
        self.assertIn("|provisioned=0|settings_reset=pass|resumed=", target)
        self.assertIn("CYCLE_TARGET = 20", host)
        self.assertIn('dispatch_attestation(\n                    "m32_mesh"', host)

    def test_twenty_cycle_raw_validator_rechecks_semantics_and_cleanup(self) -> None:
        """! @brief attestation 전 20회 raw 범위와 역할별 실제 분모를 다시 판정합니다. """

        transcript = []
        records = []
        for cycle in range(1, runner.CYCLE_TARGET + 1):
            nonce = f"{cycle:032x}"
            start = len(transcript) + 1
            results = {
                "provisioner": {
                    "payload_integrity": "pass",
                    "provisioned_nodes": "2",
                    "configured_nodes": "2",
                    "base_messages": "300",
                    "secured_messages": "200",
                    "acknowledged": "500",
                    "invalid_destination_rejected": "1",
                    "wrong_key_rejected": "1",
                    "max_latency_ms": "10",
                },
                "node_a": {
                    "payload_integrity": "pass",
                    "received": "250",
                    "unprovisioned_rejected": "1",
                    "feature": "pass",
                    "friendship": "pass",
                },
                "node_b": {
                    "payload_integrity": "pass",
                    "received": "250",
                    "unprovisioned_rejected": "1",
                    "feature": "pass",
                    "friendship": "pass",
                },
            }
            for role in runner.ROLES:
                for event in ("CLEARED", "BEGIN", "RESULT", "END", "STOPPED"):
                    transcript.append(
                        f"{role}: {runner.PROTOCOL}|{event}|nonce={nonce}|role={role}"
                    )
            transcript.extend(
                (
                    f"node_a: {runner.PROTOCOL}|FRIEND_CLEAR_LOCAL|nonce={nonce}",
                    f"node_b: {runner.PROTOCOL}|FRIEND_CLEAR_PEER|nonce={nonce}",
                )
            )
            end = len(transcript)
            raw = ("\n".join(transcript[start - 1:end]) + "\n").encode("ascii")
            records.append(
                {
                    "cycle": cycle,
                    "nonce": nonce,
                    "status": "PASS",
                    "transcript_line_start": start,
                    "transcript_line_end": end,
                    "transcript_sha256": hashlib.sha256(raw).hexdigest(),
                    "cleared": {
                        role: {
                            "provisioned": 0,
                            "settings_reset": "PASS",
                            "resumed_from_previous_cleanup": cycle > 1,
                            "unprovisioned_access_rejected": (
                                0 if role == "provisioner" else 1
                            ),
                        }
                        for role in runner.ROLES
                    },
                    "results": results,
                    "cleanup": {
                        "status": "PASS",
                        "command_sent": {role: True for role in runner.ROLES},
                        "friend_local_callback": True,
                        "friend_peer_callback": True,
                        "peer_ack_sent": True,
                        "errors": [],
                        "records": {
                            "provisioner": {
                                "status": "not_applicable",
                                "latency_ms": 0,
                            },
                            "node_a": {"status": "pass", "latency_ms": 1},
                            "node_b": {"status": "pass", "latency_ms": 1},
                        },
                    },
                    "semantics": {
                        "provision_two_nodes": "PASS",
                        "mesh_security": "PASS",
                        "lpn_friend_clear": "PASS",
                        "rejoin": "PASS",
                        "cleanup": "PASS",
                    },
                }
            )
        runner.validate_cycle_records(records, transcript)
        records[4]["results"]["provisioner"]["acknowledged"] = "499"
        with self.assertRaisesRegex(runner.MeshExecutionFailure, "denominator"):
            runner.validate_cycle_records(records, transcript)

    def test_native_group_builds_all_roles(self) -> None:
        """! @brief v0.6.0 native 회귀에서 세 역할 image를 함께 빌드합니다. """
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.mesh_hil.provisioner",
            "nucode.m32.mesh_hil.node_a",
            "nucode.m32.mesh_hil.node_b",
        ):
            self.assertIn(suite, source)

    def test_mesh_hil_reserves_runtime_stack_boundaries(self) -> None:
        """! @brief 실제 Mesh provisioning 경로의 스택 경계를 고정합니다. """
        configuration = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "prj.conf"
        ).read_text(encoding="utf-8")
        for option in (
            "CONFIG_BT_MESH_CDB_NODE_COUNT=3",
            "CONFIG_BT_MESH_CDB_SUBNET_COUNT=1",
            "CONFIG_BT_MESH_CDB_APP_KEY_COUNT=2",
            "CONFIG_BT_MESH_SUBNET_COUNT=1",
            "CONFIG_BT_MESH_APP_KEY_COUNT=2",
            "CONFIG_BT_MESH_MODEL_KEY_COUNT=2",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4800",
            "CONFIG_BT_RX_STACK_SIZE=5120",
            "CONFIG_BT_MESH_SETTINGS_WORKQ_STACK_SIZE=1700",
            "CONFIG_BT_MESH_ADV_STACK_SIZE=4000",
            "CONFIG_MAIN_STACK_SIZE=8192",
        ):
            self.assertIn(option, configuration)


if __name__ == "__main__":
    unittest.main(verbosity=2)
