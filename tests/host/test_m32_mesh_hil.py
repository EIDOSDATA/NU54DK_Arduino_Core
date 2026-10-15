#!/usr/bin/env python3
"""! @brief M32-W06 Mesh HIL protocol과 V2 exact 실행 계약을 검증합니다. """

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import time
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_mesh_run as runner  # noqa: E402


class M32MeshHilTests(unittest.TestCase):
    """! @brief 세 역할 분모·negative·보드 안전 조건을 고정합니다. """

    def test_protocol_line_reassembles_serial_timeout_fragments(self) -> None:
        """! @brief timeout 조각을 완성된 개행 protocol 레코드로 재조립합니다. """

        class FragmentedPort:
            """! @brief pyserial readline timeout의 부분 반환을 재현합니다. """

            def __init__(self) -> None:
                self.fragments = [
                    b"M32MESH|1|PROGRESS|role=provisioner|sen",
                    b"t=320|received=160\r\n",
                ]

            def readline(self) -> bytes:
                """! @brief 준비된 UART 조각을 순서대로 반환합니다. """
                if self.fragments:
                    return self.fragments.pop(0)
                return b""

        line = runner._line(FragmentedPort(), time.monotonic() + 1.0)
        self.assertEqual(
            "M32MESH|1|PROGRESS|role=provisioner|sent=320|received=160",
            line,
        )

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

    def test_friend_clear_limit_precedes_the_first_sdk_retry(self) -> None:
        """! @brief 첫 SDK 재시도 직전까지만 Friend Clear 성공으로 판정합니다. """
        fields = {
            "cleanup": "pass",
            "friend_clear": "pass",
            "friend_clear_peer_ack": "pass",
            "friend_clear_ms": str(runner.FRIEND_CLEAR_LIMIT_MS),
        }
        self.assertEqual(
            {"status": "pass", "latency_ms": runner.FRIEND_CLEAR_LIMIT_MS},
            runner._validate_friend_clear("node_b", fields),
        )
        fields["friend_clear_ms"] = str(runner.FRIEND_CLEAR_LIMIT_MS + 1)
        with self.assertRaisesRegex(
            runner.MeshExecutionFailure, "Friend Clear peer-ack boundary"
        ):
            runner._validate_friend_clear("node_b", fields)
        self.assertLess(runner.FRIEND_CLEAR_LIMIT_MS, 1100)

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
        """! @brief 무선 ACK 손실은 같은 TID로 여섯 번까지만 재전송합니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "message_ack_timeout_ms = 2000",
            "message_retry_limit = 6U",
            "message_response_drain_ms = 50",
            "expected_transaction_id",
            "expected_state, true,\n                                      expected_transaction_id",
            'fail("model_ack_timeout", -ETIMEDOUT)',
            "++message_retries;",
        ):
            self.assertIn(token, source)
        self.assertIn("record.payload[0] > 1U", source)
        self.assertIn(
            "record.address != expected_source ||\n"
            "                (record.payload[0] != 0U) != expected_state",
            source,
        )

    def test_lpn_traffic_uses_bounded_friend_polling(self) -> None:
        """! @brief 고밀도 traffic HIL은 자동 poll 사이에 bounded poll을 촉진합니다. """
        configuration = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "prj.conf"
        ).read_text(encoding="utf-8")
        for token in (
            "CONFIG_BT_MESH_LPN_AUTO=n",
            "CONFIG_BT_MESH_LPN_RETRY_TIMEOUT=2",
            "CONFIG_BT_MESH_LPN_POLL_TIMEOUT=100",
            "CONFIG_BT_MESH_LPN_INIT_POLL_TIMEOUT=10",
        ):
            self.assertIn(token, configuration)
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "friend_poll_interval_ms = 250",
            "void driveFriendPoll()",
            "NUCODEMesh.lastDriverError() != -EAGAIN",
            "driveFriendPoll();",
        ):
            self.assertIn(token, source)

    def test_friend_role_stays_active_until_clear_peer_ack(self) -> None:
        """! @brief Friend 역할은 Clear peer ACK 뒤에만 relay와 bearer를 내립니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        arm = source.index("atomic_set(&feature_disable_requested, 1);")
        peer_ack = source.index("atomic_get(&friend_clear_peer_acknowledged) == 0")
        relay_off = source.index("NUCODEMesh.setFeature(Feature::relay, false)")
        friend_off = source.index("NUCODEMesh.setFeature(Feature::friend_node, false)")
        self.assertLess(arm, peer_ack)
        self.assertLess(peer_ack, relay_off)
        self.assertLess(relay_off, friend_off)
        self.assertNotIn("bt_mesh_net_transmit_set", source)

    def test_friend_clear_uses_locked_upstream_sdk_patch(self) -> None:
        """! @brief Friend Clear SDK 결함은 고정된 upstream patch로만 보정합니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_mesh_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        backend = (
            REPOSITORY / "libraries" / "NUCODE_BLE_Mesh" / "src" /
            "NUCODE_BLE_Mesh.cpp"
        ).read_text(encoding="utf-8")
        patch = (
            REPOSITORY / "tools" / "nu54-builder" / "sdk-patches" / "zephyr" /
            "3564414a3b27-friend-clear-confirm.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("error = bt_mesh_lpn_set(enabled);", backend)
        self.assertNotIn("bt_mesh_scan_enable", backend)
        self.assertNotIn("bt_mesh_net_transmit_set", source)
        self.assertIn("friend_clear(frnd);", patch)
        self.assertIn("frnd->pending_cfm = 1U;", patch)
        self.assertIn("!bt_mesh_lpn_clearing()", patch)

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
        self.assertIn("discover_live", source)
        self.assertIn("flash_image_pyocd_sha256", source)
        self.assertIn("reset_and_halt_before_program=True", source)
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
        provisioner = runner._validate_cleared(
            "provisioner",
            {
                "provisioned": "1",
                "settings_reset": "pass",
                "resumed": "0",
                "unprovisioned_rejected": "0",
            },
            1,
        )
        self.assertEqual(1, provisioner["provisioned"])
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
        self.assertIn('fail("clear_lost_local_provisioning")', target)
        self.assertIn('Serial.print(NUCODEMesh.provisioned() ? 1 : 0);', target)
        self.assertIn("CYCLE_TARGET = 20", host)
        self.assertIn('dispatch_attestation(\n                    "m32_mesh"', host)

    def test_development_only_allows_a_bounded_single_cycle_rerun(self) -> None:
        """! @brief 요청된 1회 재검증이 production 20회 분모를 낮추지 않습니다. """

        self.assertEqual(1, runner.validate_cycle_target(1, True))
        self.assertEqual(
            runner.CYCLE_TARGET,
            runner.validate_cycle_target(runner.CYCLE_TARGET, False),
        )
        for invalid in (0, runner.CYCLE_TARGET + 1):
            with self.assertRaises(runner.MeshExecutionFailure):
                runner.validate_cycle_target(invalid, True)
        with self.assertRaisesRegex(
            runner.MeshExecutionFailure, "production Mesh HIL"
        ):
            runner.validate_cycle_target(1, False)

    def test_runner_drains_traffic_before_friend_clear(self) -> None:
        """! @brief 마지막 network retransmit 뒤 Friend Clear를 시작합니다. """
        source = (HIL / "m32_mesh_run.py").read_text(encoding="utf-8")
        drain = "time.sleep(POST_TRAFFIC_DRAIN_SECONDS)"
        cleanup = "cleanup = cleanup_ports(ports, nonce, identity.core, transcript)"
        self.assertIn("POST_TRAFFIC_DRAIN_SECONDS = 1.0", source)
        self.assertLess(source.index(drain), source.index(cleanup))

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
                            "provisioned": int(role == "provisioner"),
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
