"""! @brief M29-W07-D 2-link GATT·CoC 통합 image와 runner 계약을 검증합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TARGET_ROOT = ROOT / "tests/zephyr/m29_ble_multi_hil"
TARGET = TARGET_ROOT / "src/main.cpp"
TARGET_FRAGMENTS = tuple(
    TARGET_ROOT / "src" / name
    for name in (
        "M29MultiProtocol.inc",
        "M29MultiRadio.inc",
        "M29MultiTraffic.inc",
        "M29MultiEvents.inc",
        "M29MultiCommand.inc",
    )
)
PAYLOAD = TARGET_ROOT / "src/M29MultiPayload.h"
CONFIG = TARGET_ROOT / "prj.conf"
CASES = TARGET_ROOT / "testcase.yaml"
RUNNER = ROOT / "tests/hil/nu54dk/m29_ble_multi.py"
PROTOCOL = ROOT / "tests/hil/nu54dk/m29_ble_multi_protocol.py"
EXAMPLE = ROOT / "libraries/NUCODE_BLE/examples/MixedGattCocLinks/MixedGattCocLinks.ino"
EXAMPLE_PAYLOAD = EXAMPLE.with_name("MixedGattCocPayload.h")


def target_source() -> str:
    """! @brief 분할된 W07-D target source를 논리 순서대로 결합합니다. """

    return "\n".join(
        path.read_text(encoding="utf-8") for path in (TARGET, *TARGET_FRAGMENTS)
    )


class M29BleMultiTests(unittest.TestCase):
    """! @brief 고정 자원·link 격리·protocol·3-role build 계약을 검사합니다. """

    def test_target_uses_two_generation_links_and_bounded_resources(self) -> None:
        target = target_source()
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
        target = target_source()
        for token in (
            'constexpr char protocol[] = "M29W07D|1"',
            'start_prefix[] = "M29W07D|1|START|test=M29-MULTI-01|nonce="',
            "validRfPeer",
            "setManufacturerData(company_id, manufacturer",
            "server_gatt_received",
            "server_coc_received",
            "progress_reported += 100U",
            "client_gatt_completed, nonce_binary",
            "client_coc_received, nonce_binary",
            "hasServer() && (!server_connection.valid() || !server_channel_connected)",
            'fail("cross_link_gatt_client")',
            'fail("cross_link_gatt_server")',
            'fail("cross_link_coc_event")',
            "client_connection != information.connection",
            'Serial.print("|cross_link=0|payload_errors=0|dropped_events=0")',
        ):
            self.assertIn(token, target)
        self.assertNotIn("BLEAdvertising.addServiceUuid(service_uuid)", target)
        self.assertNotIn("BLEScan.filterServiceUuid(service_uuid)", target)

    def test_long_target_is_split_by_responsibility(self) -> None:
        """! @brief 3보드 image가 다시 단일 장문 파일로 합쳐지는 것을 막습니다. """

        main = TARGET.read_text(encoding="utf-8")
        self.assertLessEqual(len(main.splitlines()), 180)
        for fragment in TARGET_FRAGMENTS:
            self.assertTrue(fragment.is_file(), fragment)
            self.assertIn(f'#include "{fragment.name}"', main)
            self.assertLessEqual(len(fragment.read_text(encoding="utf-8").splitlines()), 350)

    def test_mixed_gatt_coc_example_covers_three_roles_and_two_links(self) -> None:
        """! @brief W08 예제가 세 보드 role과 link 지정 API를 실제로 사용하는지 검사합니다. """

        example = EXAMPLE.read_text(encoding="utf-8")
        payload = EXAMPLE_PAYLOAD.read_text(encoding="utf-8")
        for token in (
            "NodeRole::peripheral",
            "NodeRole::mixed",
            "NodeRole::central",
            "BLEConnectionHandle clientConnection",
            "BLEConnectionHandle serverConnection",
            "BLEL2capChannelHandle clientChannel",
            "BLEL2capChannelHandle serverChannel",
            "BLEClient.discover(clientConnection",
            "BLEClient.write(clientConnection",
            "information.connection != clientConnection",
            "information.connection != serverConnection",
            "finishTrafficIfComplete",
        ):
            self.assertIn(token, example)
        self.assertIn("class Payload final", payload)
        self.assertIn("::memcmp(data, expected, length) == 0", payload)

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
            "with ExitStack() as stack:",
            '"m29_multi_01_status": "passed"',
        ):
            self.assertIn(token, runner)
        self.assertLess(
            runner.index("for role in ROLES:\n            if flash_backend"),
            runner.index("with ExitStack() as stack:"),
        )
        for token in (
            'PROTOCOL = "M29W07D|1"',
            "non-ASCII UART noise",
            "actual != expected",
            "mixed.connections != 2",
        ):
            self.assertIn(token, protocol)


if __name__ == "__main__":
    unittest.main()
