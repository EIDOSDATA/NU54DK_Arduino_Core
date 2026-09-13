"""! @brief M29-W03 link별 long/reliable write와 atomic commit 계약을 검증합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.h"
INTERNAL = ROOT / "libraries/NUCODE_BLE/src/internal/gatt/GattInternal.h"
SERVER = ROOT / "libraries/NUCODE_BLE/src/internal/gatt/GattServer.cpp"
CLIENT = ROOT / "libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp"
SESSION = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp"
CONFIG = ROOT / "libraries/NUCODE_BLE/zephyr/ble-nus.conf"
HOST_SCENARIO = ROOT / "tests/host/r12_ble_gatt_main.cpp"
TARGET = ROOT / "tests/zephyr/m29_ble_long_write_hil/src/main.cpp"
RUNNER = ROOT / "tests/hil/nu54dk/m29_ble_long_write.py"


class M29BleLongWriteTests(unittest.TestCase):
    """! @brief W03 공개 API·고정 자원·원자성·HIL 계약을 fail-closed로 고정합니다. """

    def test_public_api_allows_reliable_write_and_identifies_server_link(self):
        """! @brief response write는 512 byte이고 server callback은 exact link를 제공해야 합니다. """

        text = HEADER.read_text(encoding="utf-8")
        self.assertIn("response가 있는 최대 512 byte long/reliable write", text)
        self.assertIn("write(BLEConnectionHandle connection, const void *data", text)
        event_start = text.index("struct BLECharacteristicEventInfo")
        event_end = text.index("};", event_start)
        self.assertIn("BLEConnectionHandle connection", text[event_start:event_end])

    def test_two_fixed_prepare_transactions_have_no_dynamic_allocation(self):
        """! @brief 두 link마다 transaction 하나를 고정 slot으로 소유해야 합니다. """

        text = INTERNAL.read_text(encoding="utf-8")
        for token in (
            "maximum_prepare_transactions = 2U",
            "struct PrepareTransaction",
            "PrepareTransaction prepare_transactions[maximum_prepare_transactions]",
            "std::uint32_t generation",
            "std::uint16_t length",
        ):
            self.assertIn(token, text, token)
        for forbidden in ("std::vector", "malloc(", "calloc(", "realloc("):
            self.assertNotIn(forbidden, text, forbidden)

    def test_prepare_tracks_fragments_and_execute_commits_once(self):
        """! @brief PREPARE 중 cache를 쓰지 않고 EXECUTE 한 번만 값을 복사해야 합니다. """

        text = SERVER.read_text(encoding="utf-8")
        start = text.index("ssize_t serverWrite(")
        end = text.index("void cccChanged(", start)
        write = text[start:end]
        prepare = write[write.index("BT_GATT_WRITE_FLAG_PREPARE") :]
        execute = prepare[prepare.index("BT_GATT_WRITE_FLAG_EXECUTE") :]
        self.assertIn("offset != transaction->length", prepare)
        self.assertIn("transaction->length = static_cast<std::uint16_t>(offset + length)", prepare)
        self.assertLess(execute.index("::memcpy(GattAccess::value"), execute.index("queueServerEvent"))
        self.assertEqual(execute.count("BLECharacteristicEvent::written"), 2)

    def test_disconnect_and_end_clear_prepare_ownership(self):
        """! @brief stale connection이나 generation이 prepare transaction을 재사용하면 안 됩니다. """

        text = SESSION.read_text(encoding="utf-8")
        self.assertIn("clearServerTransaction(connection)", text)
        self.assertIn("clearServerTransactions()", text)

    def test_client_and_stack_limits_preserve_command_boundary(self):
        """! @brief CoC 512-byte MTU와 ATT command·ACL 한계를 함께 지켜야 합니다. """

        client = CLIENT.read_text(encoding="utf-8")
        config = CONFIG.read_text(encoding="utf-8")
        self.assertIn("length > maximum_value_length", client)
        self.assertIn("validWriteCommandPayload(*state, length)", client)
        self.assertIn("CONFIG_BT_ATT_PREPARE_COUNT=6", config)
        self.assertIn("CONFIG_BT_L2CAP_TX_MTU=512", config)
        self.assertIn("CONFIG_BT_BUF_ACL_TX_SIZE=251", config)

    def test_host_and_target_cover_atomic_negative_and_quantitative_paths(self):
        """! @brief Host 음성 case와 target 100회 고정 protocol이 모두 존재해야 합니다. """

        host = HOST_SCENARIO.read_text(encoding="utf-8")
        target = TARGET.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        for token in (
            '"m29_long_write"',
            "BT_GATT_WRITE_FLAG_PREPARE",
            "BT_GATT_WRITE_FLAG_EXECUTE",
            "BT_ATT_ERR_INVALID_OFFSET",
            "BT_ATT_ERR_INVALID_ATTRIBUTE_LEN",
            "clearServerTransaction",
        ):
            self.assertIn(token, host, token)
        for token in (
            'protocol[] = "M29W03|1"',
            'ready_query[] = "M29W03|1|READY?"',
            "required_iterations = 100U",
            "partial_commit",
            "BLEClient.write(connection_handle, payload, sizeof(payload))",
            "BLEClient.read(connection_handle)",
        ):
            self.assertIn(token, target, token)
        self.assertIn('PROTOCOL = "M29W03|1"', runner)
        self.assertIn('"m29_long_01_status": "passed"', runner)
        self.assertIn('additional_paths=(HIL_DIRECTORY / "m29_ble_long.py",)', runner)


if __name__ == "__main__":
    unittest.main(verbosity=2)
