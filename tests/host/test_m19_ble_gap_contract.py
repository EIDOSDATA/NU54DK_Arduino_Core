#!/usr/bin/env python3
"""! @brief M19 BLE Core/GAP 공개·고정 자원·profile 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
LIBRARY = REPOSITORY / "libraries" / "NUCODE_BLE"
HEADER = LIBRARY / "src" / "NUCODE_BLE_GAP.h"
SOURCE = LIBRARY / "src" / "NUCODE_BLE_GAP.cpp"
STACK = LIBRARY / "src" / "internal" / "NUCODE_BLE_Stack.cpp"
INTERNAL = LIBRARY / "src" / "internal" / "NUCODE_BLE_Internal.h"
BUILDER_PATH = REPOSITORY / "tools" / "nu54-builder" / "src" / "nu54_builder.py"


def load_builder() -> object:
    """! @brief production profile resolver를 직접 import합니다. """

    specification = importlib.util.spec_from_file_location("m19_builder", BUILDER_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"builder를 불러올 수 없습니다: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class M19BleGapContractTests(unittest.TestCase):
    """! @brief M19 API, callback 경계와 profile negative를 고정합니다. """

    def test_public_header_is_arduino_friendly_and_complete(self) -> None:
        """! @brief Zephyr type 없이 목표 GAP 객체와 진단을 노출합니다. """

        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "class BLEUuid final",
            "class BLEAddress final",
            "struct BLEScanResult",
            "class Device final",
            "class Advertising final",
            "class Scan final",
            "class Connection final",
            "BLEDevice",
            "BLEAdvertising",
            "BLEScan",
            "BLEConnection",
            "setConnectable(",
            "addServiceUuid(",
            "setManufacturerData(",
            "setServiceData(",
            "filterName(",
            "filterServiceUuid(",
            "filterAddress(",
            "requestMtu(",
            "requestPhy(",
            "txPower(",
            "requestParameters(",
            "maximumConnections()",
        ):
            self.assertIn(token, text, token)
        self.assertNotIn("#include <zephyr/", text)
        self.assertNotIn("struct bt_", text)
        self.assertIn("maximum_payload_length = 31U", text)
        self.assertIn("maximumConnections()", text)
        self.assertIn("return 1U;", text)

    def test_once_init_and_m21_observer_hooks_are_shared(self) -> None:
        """! @brief NUS/GAP/M21이 bt_enable과 connection callback을 중복 소유하지 않습니다. """

        stack = STACK.read_text(encoding="utf-8")
        internal = INTERNAL.read_text(encoding="utf-8")
        nus = (LIBRARY / "src" / "NUCODE_BLE.cpp").read_text(encoding="utf-8")
        self.assertEqual(stack.count("bt_enable(nullptr)"), 1)
        self.assertIn("internal::ensureStack()", nus)
        self.assertNotIn("atomic_t stack_initialized", nus)
        for token in (
            "securityConnected(struct bt_conn *connection)",
            "securityDisconnected(struct bt_conn *connection)",
            "securityChanged(struct bt_conn *connection, bt_security_t level",
            "settingsReady()",
            "settingsResult()",
        ):
            self.assertIn(token, internal, token)
        self.assertIn("settings_load()", stack)
        self.assertIn("__weak void securityConnected", stack)

    def test_stack_callbacks_only_enqueue_bounded_records(self) -> None:
        """! @brief Bluetooth callback에서 user callback·heap 사용을 금지합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "K_MSGQ_DEFINE(gap_event_queue",
            "K_MSGQ_DEFINE(scan_result_queue",
            "k_msgq_put(&gap_event_queue",
            "k_msgq_put(&scan_result_queue",
            "Device::poll()",
            "result_callback(record.result, scan_context)",
            "record.generation",
            "callback(record.event, event_context)",
        ):
            self.assertIn(token, source, token)
        for forbidden in (
            "std::vector",
            "std::deque",
            "std::list",
            "malloc(",
            "calloc(",
            "realloc(",
        ):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertNotRegex(source, r"\bnew\s+[A-Za-z_:]")
        scan_callback = source[source.index("void scanReceived(") : source.index(
            "/** @brief MTU 교환", source.index("void scanReceived(")
        )]
        self.assertNotIn("result_callback(", scan_callback)
        connection_callback = source[
            source.index("void connectionEstablished(") : source.index(
                "/** @brief disconnect", source.index("void connectionEstablished(")
            )
        ]
        self.assertNotIn("event_callback(", connection_callback)

    def test_nus_callbacks_ignore_generic_gap_links_and_targets_link_bundle(self) -> None:
        """! @brief GAP/GATT link가 미사용 NUS 상태를 오염하지 않도록 bundle parity를 고정합니다. """

        nus = (LIBRARY / "src" / "NUCODE_BLE.cpp").read_text(encoding="utf-8")
        connected = nus[nus.index("void connectionEstablished(") : nus.index(
            "/** @brief disconnect", nus.index("void connectionEstablished(")
        )]
        disconnected = nus[nus.index("void connectionDisconnected(") : nus.index(
            "/** @brief connection object", nus.index("void connectionDisconnected(")
        )]
        for callback in (connected, disconnected):
            self.assertIn("currentRole() == Role::none", callback)
            self.assertLess(
                callback.index("currentRole() == Role::none"),
                callback.index("k_spin_lock(&connection_lock)"),
            )
        for suite in (
            "m19_ble_gap_contract",
            "m19_ble_gap_hil",
            "m20_ble_gatt_contract",
            "m20_ble_gatt_hil",
        ):
            cmake = (
                REPOSITORY / "tests" / "zephyr" / suite / "CMakeLists.txt"
            ).read_text(encoding="utf-8")
            config = (
                REPOSITORY / "tests" / "zephyr" / suite / "prj.conf"
            ).read_text(encoding="utf-8")
            self.assertIn("src/NUCODE_BLE.cpp", cmake, suite)
            self.assertIn("CONFIG_NUCODE_BLE_NUS=y", config, suite)
        stack = STACK.read_text(encoding="utf-8")
        self.assertIn("claimFacade(FacadeOwner owner)", stack)
        self.assertIn("releaseFacade(FacadeOwner owner)", stack)
        self.assertIn("FacadeOwner::nus", nus)
        self.assertIn("FacadeOwner::generic", SOURCE.read_text(encoding="utf-8"))
        end = nus[nus.index("void NusSerial::end()") : nus.index(
            "void NusSerial::onEvent", nus.index("void NusSerial::end()")
        )]
        self.assertIn("wait_for_pending_recycle", end)
        self.assertIn("else if (!wait_for_pending_recycle)", end)
        recycled = nus[nus.index("void connectionRecycled()") : nus.index(
            "BT_CONN_CB_DEFINE", nus.index("void connectionRecycled()")
        )]
        self.assertIn("releaseFacade(", recycled)

    def test_feature_resolver_accepts_ble_and_rejects_standard(self) -> None:
        """! @brief library feature가 ble profile에만 결합되는지 production resolver로 검사합니다. """

        builder = load_builder()
        ble = json.loads(
            (REPOSITORY / "variants" / "nu54dk" / "profiles" / "ble" / "profile.json")
            .read_text(encoding="utf-8")
        )
        standard = json.loads(
            (
                REPOSITORY
                / "variants"
                / "nu54dk"
                / "profiles"
                / "standard"
                / "profile.json"
            ).read_text(encoding="utf-8")
        )
        resolved = builder.resolve_library_features(REPOSITORY, ble, ["NUCODE_BLE"])
        self.assertEqual([entry["id"] for entry in resolved], ["nucode.ble.nus"])
        with self.assertRaisesRegex(builder.AdapterError, "호환되지"):
            builder.resolve_library_features(REPOSITORY, standard, ["NUCODE_BLE"])

    def test_kconfig_and_examples_cover_gap_boundaries(self) -> None:
        """! @brief fixed queue와 사용자 예제가 package source에 포함됐는지 검사합니다. """

        kconfig = (REPOSITORY / "zephyr" / "Kconfig").read_text(encoding="utf-8")
        feature_conf = (LIBRARY / "zephyr" / "ble-nus.conf").read_text(
            encoding="utf-8"
        )
        for symbol in (
            "config NUCODE_BLE_CORE",
            "config NUCODE_BLE_CORE_EVENT_QUEUE_SIZE",
            "config NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE",
        ):
            self.assertIn(symbol, kconfig, symbol)
        for setting in (
            "CONFIG_NUCODE_BLE_CORE=y",
            "CONFIG_BT_MAX_CONN=1",
            "CONFIG_BT_USER_PHY_UPDATE=y",
        ):
            self.assertIn(setting, feature_conf, setting)
        for name in ("GAPPeripheral", "GAPCentral"):
            example = LIBRARY / "examples" / name / f"{name}.ino"
            self.assertTrue(example.is_file(), example)
            self.assertFalse((example.parent / "prj.conf").exists())
            self.assertFalse((example.parent / "app.overlay").exists())

    def test_user_phy_control_disables_zephyr_auto_update(self) -> None:
        """! @brief 공개 PHY 요청과 HIL이 Zephyr 자동 PHY 절차와 경쟁하지 않도록 고정합니다. """

        configurations = {
            "제품 feature": LIBRARY / "zephyr" / "ble-nus.conf",
            "M19 HIL": (
                REPOSITORY
                / "tests"
                / "zephyr"
                / "m19_ble_gap_hil"
                / "prj.conf"
            ),
        }
        for name, path in configurations.items():
            with self.subTest(configuration=name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("CONFIG_BT_USER_PHY_UPDATE=y", text)
                self.assertIn("CONFIG_BT_AUTO_PHY_CENTRAL_NONE=y", text)
                self.assertNotIn("CONFIG_BT_AUTO_PHY_CENTRAL_2M=y", text)

    def test_legacy_tx_power_and_shutdown_generation_are_enforced(self) -> None:
        """! @brief TPC 비활성 target과 end-during-connect 경계를 정적으로 고정합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn(".phy = 0U", source)
        self.assertIn("pending_connection_generation", source)
        self.assertIn("atomic_inc(&device_session_generation)", source)
        end = source[source.index("void Device::end()") : source.index(
            "bool Device::initialized()", source.index("void Device::end()")
        )]
        self.assertLess(
            end.index("atomic_set(&device_initialized, 0)"),
            end.index("bt_conn_disconnect("),
        )
        self.assertIn("pending = pending_connection", end)
        self.assertIn("k_msgq_purge(&gap_event_queue)", end)
        hil = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m19_ble_gap_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("BLEConnection.txPower(tx_power)", hil)
        for step in ("mtu", "phy", "parameters", "tx-power"):
            self.assertIn(f'failLinkRequest("{step}")', hil, step)
        for token in (
            "NUCODE_M19_CENTRAL:LINK_REQUEST:FAIL:step=",
            '":error="',
            '":driver="',
            '":nonce="',
        ):
            self.assertIn(token, hil, token)
        self.assertIn("service_uuid = nucode::ble::BLEUuid(canonical)", hil)
        self.assertIn("nonce_binding_length = 6U", hil)
        self.assertIn("uuid16_field[maximum_ad_field_data]", source)
        self.assertIn("{BT_DATA_UUID16_ALL, uuid16_field, uuid16_length}", source)
        self.assertEqual(source.count("{BT_DATA_UUID16_ALL, uuid16_field"), 1)
        central_disconnect = hil[hil.index("if (disconnect_pending") : hil.index(
            "delay(1);", hil.index("if (disconnect_pending")
        )]
        self.assertIn("#ifdef NUCODE_M19_CENTRAL", hil[:hil.index("if (disconnect_pending")])
        self.assertNotIn("#else", central_disconnect)


if __name__ == "__main__":
    unittest.main(verbosity=2)
