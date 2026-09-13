"""! @brief M29-W06 LE CoC 공개 API·고정 자원·예제 계약을 검증합니다. """

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_L2CAP.h"
SOURCE = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_L2CAP.cpp"
SESSION = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp"
INTERNAL = ROOT / "libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Internal.h"
KCONFIG = ROOT / "zephyr/config/ble.Kconfig"
FEATURE = ROOT / "libraries/NUCODE_BLE/zephyr/ble-nus.conf"
EXAMPLES = ROOT / "libraries/NUCODE_BLE/examples"
TARGET = ROOT / "tests/zephyr/m29_ble_coc_hil/src/main.cpp"
TARGET_CONFIG = ROOT / "tests/zephyr/m29_ble_coc_hil/prj.conf"
TARGET_CASES = ROOT / "tests/zephyr/m29_ble_coc_hil/testcase.yaml"
RUNNER = ROOT / "tests/hil/nu54dk/m29_ble_coc.py"


class M29BleCocTests(unittest.TestCase):
    def test_public_api_uses_opaque_generation_handle(self):
        """! @brief raw Zephyr channel을 숨기고 slot 재사용을 generation으로 구분합니다. """
        header = PUBLIC.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "class BLEL2capChannelHandle final",
            "class L2capCoc final",
            "BLEL2capChannelHandle &channel",
            "BLEL2capEventInfo",
            "BLEConnectionHandle connection",
            "BLEL2capChannelHandleAccess::make",
            "BLEL2capChannelHandleAccess::generation",
        ):
            self.assertIn(token, header + source)
        self.assertNotIn("bt_l2cap_chan", header)

    def test_fixed_resource_limits_are_exact(self):
        """! @brief channel·SDU·RX record·TX buffer 상한과 heap 금지를 고정합니다. """
        header = PUBLIC.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "maximum_channels = 2U",
            "maximum_sdu_length = 512U",
            "receive_records_per_channel = 4U",
            "transmit_buffers = 4U",
            "ReceiveRecord receives[rx_record_count]",
            "NET_BUF_POOL_FIXED_DEFINE(rx_pool, channel_count",
            "NET_BUF_POOL_FIXED_DEFINE(tx_pool, L2capCoc::transmit_buffers",
        ):
            self.assertIn(token, header + source)
        for forbidden in ("new ", "malloc(", "calloc(", "realloc(", "k_malloc("):
            self.assertNotIn(forbidden, source)

    def test_callback_and_buffer_ownership_are_main_thread_bounded(self):
        """! @brief stack callback은 복사·queue만 수행하고 poll이 사용자 callback을 호출합니다. """
        source = SOURCE.read_text(encoding="utf-8")
        callback = source[source.rindex("int channelReceived") : source.rindex("void channelSent")]
        poll = source[source.index("void poll() noexcept") : source.index("void end() noexcept")]
        self.assertIn("::memcpy(receive.data, buffer->data, buffer->len)", callback)
        self.assertIn("receive_records_per_channel", PUBLIC.read_text(encoding="utf-8"))
        self.assertNotIn("callback(", callback)
        self.assertIn("callback(information, callback_context)", poll)
        self.assertIn("net_buf_alloc(&internal::l2cap::tx_pool, K_NO_WAIT)", source)
        self.assertIn("net_buf_unref(buffer)", source)

    def test_credit_backpressure_and_disconnect_reclaim_are_explicit(self):
        """! @brief TX pool 고갈을 busy로 분류하고 disconnect에서 ownership을 회수합니다. """
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "statistics.backpressure",
            "recordError(BLEError::busy, -EAGAIN, true)",
            "pending_transmits",
            "context.transmits_in_use - slot->pending_transmits",
            "bt_l2cap_chan_disconnect",
            "channelReleased",
        ):
            self.assertIn(token, source)

    def test_device_session_and_build_profile_enable_coc(self):
        """! @brief Device poll/end와 Kconfig가 LE CoC lifecycle을 누락하지 않습니다. """
        session = SESSION.read_text(encoding="utf-8")
        internal = INTERNAL.read_text(encoding="utf-8")
        kconfig = KCONFIG.read_text(encoding="utf-8")
        feature = FEATURE.read_text(encoding="utf-8")
        self.assertIn("internal::pollL2cap();", session)
        self.assertIn("internal::l2capEnded();", session)
        self.assertIn("void pollL2cap() noexcept", internal)
        self.assertIn("void l2capEnded() noexcept", internal)
        self.assertIn("config NUCODE_BLE_L2CAP", kconfig)
        for token in (
            "CONFIG_BT_L2CAP_DYNAMIC_CHANNEL=y",
            "CONFIG_BT_L2CAP_TX_MTU=512",
            "CONFIG_BT_L2CAP_TX_BUF_COUNT=4",
            "CONFIG_NUCODE_BLE_L2CAP=y",
            "CONFIG_NUCODE_BLE_L2CAP_EVENT_QUEUE_SIZE=16",
        ):
            self.assertIn(token, feature)

    def test_examples_check_start_send_and_echo_results(self):
        """! @brief server/client 예제가 오류와 peer 수신 성공을 구분해 보고합니다. """
        server = (EXAMPLES / "L2capCocServer/L2capCocServer.ino").read_text(encoding="utf-8")
        client = (EXAMPLES / "L2capCocClient/L2capCocClient.ino").read_text(encoding="utf-8")
        for token in (
            "BLEL2cap.startServer(echoPsm)",
            "BLEL2cap.send(information.channel, information.data, information.length)",
            "BLEDevice.lastError()",
        ):
            self.assertIn(token, server)
        for token in (
            "BLEL2cap.connect(peerConnection, echoPsm, channels[index])",
            "BLEL2cap.availableForWrite() >= channelCount",
            "::memcmp(information.data, payload, sizeof(payload))",
            "pendingEchoes == 0U",
        ):
            self.assertIn(token, client)

    def test_target_protocol_covers_coc_negative_and_recovery(self):
        """! @brief 두 role image와 strict runner가 W06 고정 수치 전체를 포함합니다. """
        target = TARGET.read_text(encoding="utf-8")
        config = TARGET_CONFIG.read_text(encoding="utf-8")
        cases = TARGET_CASES.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        for token in (
            'constexpr char protocol[] = "M29W06|1"',
            "required_iterations = 1000U",
            "required_negative_iterations = 20U",
            "maximum_channels == 2U",
            "maximum_sdu_length == 512U",
            "internal::gatt::serverWrite",
            "stale_handle_accept",
            "backpressure_counter",
        ):
            self.assertIn(token, target)
        for token in (
            "CONFIG_BT_SMP=y",
            "CONFIG_BT_L2CAP_DYNAMIC_CHANNEL=y",
            "CONFIG_BT_L2CAP_TX_MTU=512",
            "CONFIG_BT_L2CAP_TX_BUF_COUNT=4",
            "CONFIG_NUCODE_BLE_L2CAP=y",
        ):
            self.assertIn(token, config)
        self.assertIn("nucode.m29.ble_coc_peripheral", cases)
        self.assertIn("nucode.m29.ble_coc_central", cases)
        for token in (
            'PROTOCOL = "M29W06|1"',
            '"malformed", "offset", "execute", "psm", "credit"',
            '"m29_coc_01_status": "passed"',
            '"m29_neg_01_status": "passed"',
            "validate_source_clean",
        ):
            self.assertIn(token, runner)


if __name__ == "__main__":
    unittest.main()
