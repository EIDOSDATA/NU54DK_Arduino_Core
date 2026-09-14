"""! @brief M29-W07-D 2-link GATT·CoC 통합 image와 runner 계약을 검증합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TARGET_ROOT = ROOT / "tests/zephyr/m29_ble_multi_hil"
TARGET = TARGET_ROOT / "src/main.cpp"
PAYLOAD = TARGET_ROOT / "src/M29MultiPayload.h"
CONFIG = TARGET_ROOT / "prj.conf"
CASES = TARGET_ROOT / "testcase.yaml"
RUNNER = ROOT / "tests/hil/nu54dk/m29_ble_multi.py"
PROTOCOL = ROOT / "tests/hil/nu54dk/m29_ble_multi_protocol.py"


class M29BleMultiTests(unittest.TestCase):
    """! @brief 고정 자원·link 격리·protocol·3-role build 계약을 검사합니다. """

    def test_target_uses_two_generation_links_and_bounded_resources(self) -> None:
        target = TARGET.read_text(encoding="utf-8")
        config = CONFIG.read_text(encoding="utf-8")
        for token in (
            "CONFIG_BT_MAX_CONN == 2",
            "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1",
            "BLEConnectionHandle client_connection",
            "BLEConnectionHandle server_connection",
            "BLEL2capChannelHandle client_channel",
            "BLEL2capChannelHandle server_channel",
            "cross_link_events",
            "required_operations = 1000U",
        ):
            self.assertIn(token, target)
        for token in (
            "CONFIG_BT_MAX_CONN=2",
            "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1",
            "CONFIG_BT_L2CAP_TX_MTU=512",
            "CONFIG_BT_L2CAP_TX_BUF_COUNT=4",
            "CONFIG_NUCODE_BLE_L2CAP_EVENT_QUEUE_SIZE=24",
        ):
            self.assertIn(token, config)

    def test_payload_codec_binds_link_transport_sequence_and_nonce(self) -> None:
        payload = PAYLOAD.read_text(encoding="utf-8")
        for token in (
            "class MultiPayload final",
            "nonce_binary_length = 16U",
            "gatt_kind = 0x47U",
            "coc_kind = 0x4cU",
            "std::uint8_t marker",
            "std::uint32_t sequence",
            "::memcmp(data, expected, payload_length)",
        ):
            self.assertIn(token, payload)

    def test_target_protocol_is_fixed_and_receiver_validated(self) -> None:
        target = TARGET.read_text(encoding="utf-8")
        for token in (
            'constexpr char protocol[] = "M29W07D|1"',
            'start_prefix[] = "M29W07D|1|START|test=M29-MULTI-01|nonce="',
            "validRfPeer",
            "setManufacturerData(company_id, manufacturer",
            "server_gatt_received",
            "server_coc_received",
            'fail("cross_link_gatt_client")',
            'fail("cross_link_gatt_server")',
            'fail("cross_link_coc_event")',
            'Serial.print("|cross_link=0|payload_errors=0|dropped_events=0")',
        ):
            self.assertIn(token, target)
        self.assertNotIn("BLEAdvertising.addServiceUuid(service_uuid)", target)
        self.assertNotIn("BLEScan.filterServiceUuid(service_uuid)", target)

    def test_three_role_build_matrix_is_explicit(self) -> None:
        cases = CASES.read_text(encoding="utf-8")
        for role in ("peripheral", "mixed", "central"):
            self.assertIn(f"nucode.m29.ble_multi_{role}", cases)
            self.assertIn(f"M29_MULTI_ROLE={role}", cases)

    def test_runner_and_strict_parser_are_split(self) -> None:
        self.assertTrue(RUNNER.is_file())
        runner = RUNNER.read_text(encoding="utf-8")
        protocol = PROTOCOL.read_text(encoding="utf-8")
        for token in (
            "validate_source_clean",
            "validate_build_record",
            "validate_three_role_session",
            "ThreadPoolExecutor(max_workers=3)",
            '"m29_multi_01_status": "passed"',
        ):
            self.assertIn(token, runner)
        for token in (
            'PROTOCOL = "M29W07D|1"',
            "non-ASCII UART noise",
            "actual != expected",
            "mixed.connections != 2",
        ):
            self.assertIn(token, protocol)


if __name__ == "__main__":
    unittest.main()
