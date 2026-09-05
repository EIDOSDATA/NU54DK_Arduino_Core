#!/usr/bin/env python3
"""! @brief M20 범용 GATT public·lifecycle·negative 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import unittest
from ble_source_contracts import gap_source


REPOSITORY = Path(__file__).resolve().parents[2]
LIBRARY = REPOSITORY / "libraries" / "NUCODE_BLE"
HEADER = LIBRARY / "src" / "NUCODE_BLE_GATT.h"
SOURCE = LIBRARY / "src" / "NUCODE_BLE_GATT.cpp"


class M20BleGattContractTests(unittest.TestCase):
    """! @brief schema, cached value, client와 deferred callback 표면을 고정합니다. """

    def test_public_server_and_client_surface_is_complete(self) -> None:
        """! @brief portable UUID·service·characteristic·remote handle API를 검사합니다. """

        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "enum class BLEProperty",
            "enum class BLEPermission",
            "class BLECharacteristic final",
            "class BLEService final",
            "class BLERemoteService final",
            "class BLERemoteCharacteristic final",
            "class GattClient final",
            "BLEClient",
            "addCharacteristic(",
            "setValue(",
            "notificationSubscribed()",
            "indicationSubscribed()",
            "notify()",
            "indicate()",
            "discover(",
            "read()",
            "write(",
            "writeWithoutResponse(",
            "subscribeNotifications()",
            "subscribeIndications()",
            "unsubscribe()",
        ):
            self.assertIn(token, text, token)
        self.assertNotIn("#include <zephyr/", text)
        self.assertNotIn("struct bt_", text)
        self.assertIn("maximum_value_length = 244U", text)
        self.assertIn("BLERemoteService remoteService() const", text)
        self.assertIn("BLERemoteCharacteristic remoteCharacteristic() const", text)
        self.assertIn("image 수명 동안 유효", text)
        self.assertIn("직접 수정하면 안 됩니다", text)

    def test_schema_is_registered_before_stack_and_locked_after_start(self) -> None:
        """! @brief service 등록→bt_enable/settings_load 순서와 late mutation 거부를 고정합니다. """

        gap = gap_source()
        source = SOURCE.read_text(encoding="utf-8")
        begin = gap[gap.index("bool Device::begin(") : gap.index(
            "void Device::poll()", gap.index("bool Device::begin(")
        )]
        self.assertLess(begin.index("prepareGattDatabase()"), begin.index("ensureStack()"))
        self.assertIn("bt_gatt_service_register(&slot.service)", source)
        self.assertIn("if (stackReady()", source)
        self.assertIn("registered_ || internal::stackReady()", source)
        self.assertIn("BLEError::duplicate", source)
        self.assertIn("BLEError::schema_full", source)
        prepare = source[source.index("int prepareGattDatabase()") : source.index(
            "void pollGatt()", source.index("int prepareGattDatabase()")
        )]
        prepare_compact = " ".join(prepare.split())
        self.assertGreaterEqual(prepare.count("for (std::size_t service_index"), 2)
        self.assertLess(
            prepare.index("모든 schema를 먼저 검증"),
            prepare.index("bt_gatt_service_register"),
        )
        self.assertIn("bt_gatt_service_unregister", prepare)
        self.assertIn(
            "*service_slots[rollback].characteristics[index], false",
            prepare_compact,
        )

    def test_server_callbacks_copy_to_fixed_queue_and_use_cached_read(self) -> None:
        """! @brief stack callback에서 Sketch를 호출하지 않고 cached value만 읽습니다. """

        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "K_MSGQ_DEFINE(gatt_event_queue",
            "k_msgq_put(&gatt_event_queue",
            "bt_gatt_attr_read(connection",
            "queueServerEvent(*characteristic, BLECharacteristicEvent::written",
            "BT_GATT_WRITE_FLAG_PREPARE",
            "BT_ATT_ERR_NOT_SUPPORTED",
            "GattAccess::dispatch(*record.characteristic, event)",
            "characteristic_value_lock",
            "copyCachedValue(*characteristic, snapshot",
            "copyCachedValue(*this, snapshot",
        ):
            self.assertIn(token, source, token)
        server_write = source[source.index("ssize_t serverWrite(") : source.index(
            "/** @brief connection별 CCC", source.index("ssize_t serverWrite(")
        )]
        self.assertNotIn("callback_(", server_write)
        for forbidden in ("std::vector", "malloc(", "calloc(", "realloc("):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertNotRegex(source, r"\bnew\s+[A-Za-z_:]")

    def test_thread_context_and_session_tokens_fail_closed(self) -> None:
        """! @brief ISR stack 진입과 disconnect 뒤 stale callback 재사용을 거부합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        for signature in (
            "bool BLECharacteristic::notify()",
            "bool BLECharacteristic::indicate()",
            "bool BLEService::addCharacteristic(",
            "bool GattClient::discover(",
            "bool GattClient::read()",
            "bool GattClient::write(",
            "bool GattClient::writeWithoutResponse(",
            "bool GattClient::subscribeNotifications()",
            "bool GattClient::subscribeIndications()",
            "bool GattClient::unsubscribe()",
        ):
            start = source.index(signature)
            body = source[start : source.index("\n}", start) + 2]
            self.assertIn("internal::requireThreadContext()", body, signature)
        for token in (
            "gatt_session_generation",
            "k_msgq_purge(&gatt_event_queue)",
            "setClientOperationToken(connection)",
            "validClientOperation(connection)",
            "setClientSubscriptionToken(connection)",
            "validClientSubscription(connection)",
            "client_subscription_value",
            "NotificationContext",
            "indication_generations",
        ):
            self.assertIn(token, source, token)
        subscribe = source[source.index("bool startSubscription(") : source.index(
            "} // namespace", source.index("bool startSubscription(")
        )]
        self.assertLess(
            subscribe.index("atomic_set(&client_subscription_value, value)"),
            subscribe.index("bt_gatt_subscribe("),
        )
        hil = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m20_ble_gatt_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("nonce_bytes_length = nonce_length / 2U", hil)
        self.assertIn("memcmp(data, nonce_bytes, nonce_bytes_length)", hil)
        self.assertIn("NUCODE_M20_CENTRAL:NONCE_CHALLENGE:PASS", hil)

    def test_client_disconnect_invalidates_and_discovery_is_bounded(self) -> None:
        """! @brief reconnect 뒤 stale handle·subscription 자동 재사용을 막습니다. """

        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "BT_GATT_SUBSCRIBE_FLAG_VOLATILE",
            "GattAccess::clear(remote_service)",
            "GattAccess::clear(remote_characteristic)",
            "BLEGattClientEvent::handles_invalidated",
            "ClientStage::service_found",
            "ClientStage::characteristic_found",
            "ClientStage::ccc_found",
            "bt_gatt_discover(",
            "bt_gatt_read(",
            "bt_gatt_write(",
            "bt_gatt_write_without_response_cb(",
            "bt_gatt_subscribe(",
            "bt_gatt_unsubscribe(",
            "parameters->value == 0U",
        ):
            self.assertIn(token, source, token)
        subscribe_callback = source[
            source.index("void clientSubscribeCompleted(") : source.index(
                "/** @brief notify/indicate payload", source.index("void clientSubscribeCompleted(")
            )
        ]
        zero_value = subscribe_callback[
            subscribe_callback.index("parameters->value == 0U") :
        ]
        self.assertIn("atomic_set(&client_subscribed, 0)", zero_value)
        self.assertNotIn("BLEGattClientEvent::subscribed", zero_value.split("return;", 1)[0])

    def test_kconfig_examples_and_target_contracts_exist(self) -> None:
        """! @brief resolver config, examples와 M19/M20 분리 target gate를 확인합니다. """

        kconfig = (REPOSITORY / "zephyr" / "Kconfig").read_text(encoding="utf-8")
        feature_conf = (LIBRARY / "zephyr" / "ble-nus.conf").read_text(
            encoding="utf-8"
        )
        for symbol in (
            "config NUCODE_BLE_GATT",
            "config NUCODE_BLE_GATT_MAX_SERVICES",
            "config NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE",
            "config NUCODE_BLE_GATT_EVENT_QUEUE_SIZE",
        ):
            self.assertIn(symbol, kconfig, symbol)
        self.assertIn("CONFIG_BT_GATT_DYNAMIC_DB=y", feature_conf)
        self.assertIn("CONFIG_NUCODE_BLE_GATT=y", feature_conf)
        for name in ("CustomGattPeripheral", "CustomGattCentral"):
            example = LIBRARY / "examples" / name / f"{name}.ino"
            self.assertTrue(example.is_file(), example)
            self.assertFalse((example.parent / "prj.conf").exists())
            self.assertFalse((example.parent / "app.overlay").exists())
        self.assertTrue((REPOSITORY / "tests" / "zephyr" / "m19_ble_gap_contract").is_dir())
        self.assertTrue((REPOSITORY / "tests" / "zephyr" / "m20_ble_gatt_contract").is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
