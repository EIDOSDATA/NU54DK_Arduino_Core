#!/usr/bin/env python3
"""! @brief M32-W10 세 보드 공존 HIL 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_coexistence_run as runner  # noqa: E402


class M32CoexistenceHilTests(unittest.TestCase):
    """! @brief 공존 분모·복구·negative·V2 안전 조건을 고정합니다. """

    def test_result_denominators(self) -> None:
        """! @brief DUT와 세 peer 역할의 정량 결과를 판정합니다. """
        dut = {
            "iterations": "20",
            "ble_received": "3980",
            "radio_received": "3990",
            "ble_loss": "20",
            "radio_loss": "10",
            "ble_corrupt": "0",
            "radio_corrupt": "0",
            "ble_restarts": "1",
            "radio_restarts": "1",
            "ble_gap_ms": "499",
            "radio_gap_ms": "500",
            "starvation": "0",
            "double_owner_rejected": "1",
        }
        ble_peer = {
            "iterations": "20",
            "sent": "4000",
            "reconnects": "1",
            "write_failures": "0",
        }
        radio_peer = {
            "iterations": "20",
            "sent": "4000",
            "acknowledged": "3970",
            "failures": "30",
            "restarts": "1",
            "invalid_configuration_rejected": "1",
            "invalid_length_rejected": "1",
            "double_owner_rejected": "1",
        }
        mesh_peer = {
            "iterations": "20",
            "sent": "4000",
            "acknowledged": "4000",
            "restarts": "1",
            "failures": "0",
            "configuration_retries": "3",
            "acknowledgment_retries": "80",
        }
        runner._validate_result("ble_154", "dut", dut)
        runner._validate_result("ble_esb", "radio_peer", radio_peer)
        runner._validate_result("ble_mesh", "ble_peer", ble_peer)
        runner._validate_result("ble_mesh", "mesh_peer", mesh_peer)
        with self.assertRaisesRegex(runner.CoexistenceFailure, "receive denominator"):
            runner._validate_result(
                "ble_154", "dut", {**dut, "radio_received": "3919"}
            )

    def test_hil_source_covers_three_radios_recovery_and_negative(self) -> None:
        """! @brief target가 세 조합·4,000 frame·재시작·negative를 포함합니다. """
        source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_coexistence_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "iteration_target = 20U",
            "packets_per_iteration = 200U",
            "allowed_loss = 80U",
            "service_gap_limit_ms = 500U",
            "esb_send_interval_ms = 10",
            "mesh_configuration_settle_ms = 1500",
            "mesh_acknowledgment_retry_limit = 3U",
            "mesh_acknowledgment_timeout_ms = 300",
            "mesh_ble_payload_delay_ms = 30000",
            "retryMeshConfiguration",
            "configuration_retries=",
            "acknowledgment_retries=",
            "NUCODERadio154.send",
            "NUCODEEsb.send",
            "NUCODEMesh.sendOnOff",
            "BLESerial.disconnect",
            "recordRestart",
            "invalid_configuration_rejected=1",
            "invalid_length_rejected=1",
            "double_owner_rejected=1",
            "M32COEX|1|STOP|nonce=",
        ):
            self.assertIn(token, source)
        self.assertIn("configuration.retransmit_delay_us = 1000U", source)
        self.assertIn("configuration.retransmit_count = 15U", source)
        self.assertIn("next_send_ms = k_uptime_get() + esb_send_interval_ms", source)
        self.assertIn("radio_sequence_valid = false", source)
        self.assertIn("sequence == last_radio_sequence", source)
        self.assertIn(
            "isDuplicateRadioSequence(packet.sequence, packet.duplicate)", source
        )
        stop_session = source[
            source.index("void stopSession()") : source.index("void processCommand()")
        ]
        self.assertLess(
            stop_session.index("cleanup = stopSecondRadio() && cleanup"),
            stop_session.index("BLESerial.end()"),
        )

    def test_native_group_builds_all_nine_images(self) -> None:
        """! @brief v0.6.0 native 회귀가 세 조합의 세 역할을 모두 빌드합니다. """
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for scenario, roles in runner.SCENARIOS.items():
            for role in roles:
                suite = f"nucode.m32.coexistence_hil.{scenario}.{role}"
                self.assertIn(suite, source)

    def test_direct_154_roles_own_temperature_initialization(self) -> None:
        """! @brief direct API 초기화 전 온도 work의 SWI 요청을 금지합니다. """
        application = REPOSITORY / "tests" / "zephyr" / "m32_coexistence_hil"
        for configuration in ("ble_154_dut.conf", "radio154_peer.conf"):
            source = (application / configuration).read_text(encoding="utf-8")
            self.assertIn("CONFIG_NRF_802154_TEMPERATURE_UPDATE=n", source)

    def test_mesh_roles_keep_validated_crypto_stack_margins(self) -> None:
        """! @brief nRF54L provisioning 암호 경로의 adv·workqueue stack을 고정합니다. """
        application = REPOSITORY / "tests" / "zephyr" / "m32_coexistence_hil"
        required = (
            "CONFIG_BT_MESH_CDB_SUBNET_COUNT=1",
            "CONFIG_BT_MESH_SUBNET_COUNT=1",
            "CONFIG_BT_MESH_APP_KEY_COUNT=2",
            "CONFIG_BT_MESH_MODEL_KEY_COUNT=2",
            "CONFIG_BT_MESH_RELAY_ENABLED=n",
            "CONFIG_BT_MESH_FRIEND_ENABLED=n",
            "CONFIG_BT_MESH_GATT_PROXY_ENABLED=n",
            "CONFIG_BT_MESH_TX_SEG_MAX=16",
            "CONFIG_BT_MESH_RX_SEG_MAX=16",
            "CONFIG_BT_MESH_ADV_BUF_COUNT=16",
            "CONFIG_BT_MESH_RX_SEG_MSG_COUNT=2",
            "CONFIG_BT_MESH_TX_SEG_MSG_COUNT=2",
            "CONFIG_BT_RX_STACK_SIZE=5120",
            "CONFIG_BT_MESH_ADV_STACK_SIZE=4000",
            "CONFIG_BT_MESH_SETTINGS_WORKQ_STACK_SIZE=1700",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4800",
            "CONFIG_MAIN_STACK_SIZE=8192",
        )
        for configuration in ("ble_mesh_dut.conf", "mesh_peer.conf"):
            source = (application / configuration).read_text(encoding="utf-8")
            for setting in required:
                with self.subTest(configuration=configuration, setting=setting):
                    self.assertIn(setting, source)

    def test_runner_is_v2_only_and_scope_excludes_external_one_wire(self) -> None:
        """! @brief runner가 V2 exact 안전장치와 내부 radio 범위만 기록합니다. """
        source = (HIL / "m32_coexistence_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertIn("cmsis_dap_v1=False", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertNotIn("prefer_v1=true", source)
        for test_id in (
            '"M32-COEX-01:ble_154"',
            '"M32-COEX-01:ble_esb"',
            '"M32-COEX-01:ble_mesh"',
        ):
            self.assertIn(test_id, source)
        self.assertNotIn("M32-COEX-01:external_one_wire", source)
        self.assertIn("clean source commit", source)
        self.assertNotIn("--erase chip", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
