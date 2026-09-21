"""! @brief M29-W02 link별 GATT client와 512-byte long read 계약을 검증합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.h"
INTERNAL = ROOT / "libraries/NUCODE_BLE/src/internal/gatt/GattInternal.h"
CLIENT = ROOT / "libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp"
SESSION = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp"
CONNECTION = ROOT / "libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp"
HOST_SCENARIO = ROOT / "tests/host/r12_ble_gatt_main.cpp"
EXAMPLES = ROOT / "libraries/NUCODE_BLE/examples"


class M29BleLongReadTests(unittest.TestCase):
    """! @brief W02의 공개 API, 고정 자원, callback 수명을 fail-closed로 고정합니다. """

    def test_public_api_keeps_legacy_and_adds_link_detail(self):
        """! @brief 무인자 API와 link 지정 overload·상세 event가 함께 존재해야 합니다. """

        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "maximum_value_length = 512U",
            "struct BLEGattClientEventInfo",
            "BLEConnectionHandle connection",
            "std::uint8_t att_error",
            "BLEGattBearer bearer",
            "discover(BLEConnectionHandle connection",
            "read(BLEConnectionHandle connection)",
            "busy(BLEConnectionHandle connection)",
            "lastAttError(BLEConnectionHandle connection)",
            "onDetailedEvent(BLEGattClientInfoCallback callback",
        ):
            self.assertIn(token, text, token)
        self.assertIn("[[nodiscard]] bool read() noexcept;", text)

    def test_two_contexts_own_all_async_parameters(self):
        """! @brief 두 link가 Zephyr async parameter와 payload를 공유하지 않아야 합니다. """

        text = INTERNAL.read_text(encoding="utf-8")
        for token in (
            "maximum_client_contexts = 2U",
            "using ClientStates = ClientState[maximum_client_contexts]",
            "struct bt_gatt_discover_params discovery_parameters",
            "struct bt_gatt_read_params read_parameters",
            "struct bt_gatt_write_params write_parameters",
            "struct bt_gatt_subscribe_params subscribe_parameters",
            "std::uint8_t read_data[maximum_value_length]",
            "std::uint8_t write_data[maximum_value_length]",
            "BLEConnectionHandle connection_handle",
        ):
            self.assertIn(token, text, token)
        for forbidden in ("std::vector", "malloc(", "calloc(", "realloc("):
            self.assertNotIn(forbidden, text, forbidden)

    def test_long_read_assembles_until_explicit_completion(self):
        """! @brief fragment는 CONTINUE하고 null data 종료에서만 단일 event를 내야 합니다. """

        text = CLIENT.read_text(encoding="utf-8")
        start = text.index("std::uint8_t clientReadCompleted(")
        end = text.index("void clientWriteCompleted(", start)
        callback = text[start:end]
        for token in (
            "state->read_length + length > maximum_value_length",
            "::memcpy(state->read_data + state->read_length, data, length)",
            "return BT_GATT_ITER_CONTINUE",
            "data != nullptr",
            "BLEGattClientEvent::read_complete",
        ):
            self.assertIn(token, callback, token)
        self.assertLess(callback.index("data != nullptr"), callback.index("read_complete"))

    def test_disconnect_is_link_local_and_generation_checked(self):
        """! @brief 한 link 해제가 다른 context queue를 purge하거나 초기화하면 안 됩니다. """

        session = SESSION.read_text(encoding="utf-8")
        start = session.index("void gattDisconnected(")
        end = session.index("void gattEnded(", start)
        disconnect = session[start:end]
        self.assertIn("client.connection_handle == handle", disconnect)
        self.assertIn("clearClientState(*matched)", disconnect)
        self.assertIn("queueInvalidatedEvent(handle)", disconnect)
        self.assertNotIn("k_msgq_purge", disconnect)
        self.assertNotIn("clearClientState(client)", disconnect)
        self.assertEqual(disconnect.count("clearClientState("), 1)

    def test_gap_routes_both_roles_and_host_interleaves_fragments(self):
        """! @brief central/peripheral 모두 GATT에 등록하고 Host가 두 stream을 교차 검증해야 합니다. """

        connection = CONNECTION.read_text(encoding="utf-8")
        self.assertIn("gattConnected(connection, handle)", connection)
        self.assertIn("gattDisconnected(connection, handle)", connection)
        route = connection[connection.index("gattConnected(connection, handle)") - 120 :
                           connection.index("gattConnected(connection, handle)") + 80]
        self.assertNotIn("role == BLELinkRole::central", route)

        scenario = HOST_SCENARIO.read_text(encoding="utf-8")
        for token in (
            '"m29_long_parallel"',
            "first_read != second_read",
            "first.data() + 492",
            "second.data() + 492",
            "detailed_data[0] == first",
            "detailed_data[1] == second",
            "BLEGattClientEvent::handles_invalidated",
            "second.data() + 500, 13",
        ):
            self.assertIn(token, scenario, token)

    def test_public_examples_use_exact_handle_and_full_payload(self):
        """! @brief 사용자 예제가 512 byte와 상세 handle callback을 실제로 사용해야 합니다. """

        peripheral = (EXAMPLES / "LongGattPeripheral" / "LongGattPeripheral.ino").read_text(
            encoding="utf-8"
        )
        central = (EXAMPLES / "LongGattCentral" / "LongGattCentral.ino").read_text(
            encoding="utf-8"
        )
        self.assertIn("uint8_t payload[512]", peripheral)
        self.assertIn("BLEAdvertising.addServiceUuid(serviceUuid)", peripheral)
        for token in (
            "BLEConnectionHandle peer",
            "BLEDevice.onEventInfo(onBleEvent)",
            "BLEClient.onDetailedEvent(onClientEvent)",
            "BLEClient.discover(peer, serviceUuid, valueUuid)",
            "BLEClient.read(peer)",
            "length != 512U",
        ):
            self.assertIn(token, central, token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
