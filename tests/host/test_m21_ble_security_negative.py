#!/usr/bin/env python3
"""! @brief M21 BLE security의 거부·실패·scope 경계를 회귀 검증합니다. """

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
LIBRARY = REPOSITORY / "libraries" / "NUCODE_BLE_Security"
HEADER = (LIBRARY / "src" / "NUCODE_BLE_Security.h").read_text(encoding="utf-8")
SOURCE = (LIBRARY / "src" / "NUCODE_BLE_Security.cpp").read_text(encoding="utf-8")
CONF = (LIBRARY / "zephyr" / "ble-security.conf").read_text(encoding="utf-8")
FEATURE = json.loads((LIBRARY / "zephyr" / "feature.yml").read_text(encoding="utf-8"))
HIL_SOURCE = (
    REPOSITORY / "tests" / "zephyr" / "m21_ble_hil" / "src" / "main.cpp"
).read_text(encoding="utf-8")


class M21BleSecurityNegativeTests(unittest.TestCase):
    """! @brief 암호화·저장·삭제·민감정보 negative 계약을 검증합니다. """

    def test_rejects_security_below_encrypted_and_invalid_timeout(self) -> None:
        """! @brief 무암호화 및 비정상 사용자 응답 timeout을 초기화에서 거부합니다. """

        begin = SOURCE[SOURCE.index("bool SecurityManager::begin") :]
        begin = begin[: begin.index("void SecurityManager::poll")]
        self.assertIn("level < static_cast<unsigned int>(SecurityLevel::encrypted)", begin)
        self.assertIn("config.response_timeout_ms < 1000U", begin)
        self.assertIn("config.response_timeout_ms > 300000U", begin)
        self.assertIn("SecurityIoCapability::keyboard_display", begin)
        self.assertIn("SecurityError::invalid_argument", begin)

    def test_rejects_hid_before_encryption_or_subscription(self) -> None:
        """! @brief L2 미만 link와 CCC 미구독 HID 전송을 PASS로 올리지 않습니다. """

        send = SOURCE[SOURCE.index("bool HidKeyboard::sendReport") :]
        send = send[: send.index("bool HidKeyboard::press")]
        self.assertIn("bt_conn_get_security(connection) < BT_SECURITY_L2", send)
        self.assertIn("SecurityError::invalid_state", send)
        self.assertIn("SecurityError::not_subscribed", send)
        self.assertIn("nucode_ble_hids_send", send)
        backend = (LIBRARY / "src/internal/NUCODE_BLE_HidsBackend.c").read_text(encoding="utf-8")
        self.assertIn("bt_hids_inp_rep_send", backend)
        self.assertIn("bt_hids_boot_kb_inp_rep_send", backend)

    def test_same_boot_bond_is_pending_and_never_false_verified(self) -> None:
        """! @brief pairing 직후에는 persistence pending이며 reboot 복원 전 bonded가 아닙니다. """

        pairing = SOURCE[SOURCE.index("void pairingComplete") :]
        pairing = pairing[: pairing.index("void pairingFailed")]
        self.assertIn("BondState::persistence_pending", pairing)
        self.assertNotIn("BondState::verified", pairing)
        self.assertNotIn("settings_save()", SOURCE)
        self.assertIn("authentication_callbacks.pairing_accept = pairingAccept", SOURCE)
        self.assertIn("markPairingStarted(connection)", SOURCE)
        bonded = SOURCE[SOURCE.index("bool SecurityManager::bonded") :]
        bonded = bonded[: bonded.index("BondState SecurityManager::bondState")]
        self.assertIn("BondState::verified", bonded)

    def test_battery_isr_error_and_hid_usage_range_are_api_specific(self) -> None:
        """! @brief BAS ISR 오류와 HID descriptor 범위 밖 usage를 정확히 거부합니다. """

        battery = SOURCE[SOURCE.index("bool BatteryService::setLevel") :]
        battery = battery[: battery.index("std::uint8_t BatteryService::level")]
        self.assertIn("k_is_in_isr()", battery)
        self.assertIn("battery_error_value", battery)
        self.assertIn("SecurityError::invalid_context", battery)
        press = SOURCE[SOURCE.index("bool HidKeyboard::press") :]
        press = press[: press.index("bool HidKeyboard::releaseAll")]
        self.assertIn("usage > 0x65U", press)
        report_validation = SOURCE[SOURCE.index("bool validKeyboardReport") :]
        report_validation = report_validation[: report_validation.index("bool requireThreadContext")]
        self.assertIn("for (const std::uint8_t usage : report.keys)", report_validation)
        self.assertIn("usage > 0x65U", report_validation)
        send = SOURCE[SOURCE.index("bool HidKeyboard::sendReport") :]
        send = send[: send.index("bool HidKeyboard::press")]
        self.assertIn("validKeyboardReport(report)", send)

    def test_delete_scope_is_ble_bond_only_and_profile_is_ble_only(self) -> None:
        """! @brief erase 범위와 BLE profile 한계를 유지하면서 NUS dependency와 결합합니다. """

        self.assertIn("bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY)", SOURCE)
        self.assertNotRegex(HEADER + SOURCE, r"factory[_A-Z]?reset|mass[_A-Z]?erase")
        self.assertEqual(FEATURE["conflicts"], [])
        self.assertEqual(FEATURE["compatible_profiles"], ["ble"])

    def test_no_fixed_passkey_secret_log_or_unencrypted_hids_config(self) -> None:
        """! @brief 고정 passkey·secret 로그·평문 HIDS 설정을 모두 금지합니다. """

        self.assertNotIn("CONFIG_BT_FIXED_PASSKEY", CONF)
        self.assertIn("CONFIG_BT_HIDS_DEFAULT_PERM_RW_ENCRYPT=y", CONF)
        self.assertNotRegex(SOURCE, r"\b(?:printk|printf|Serial\.(?:print|println))\s*\(")
        self.assertNotIn("record.passkey", HIL_SOURCE)
        self.assertIn("SECURE_GATT:DENIED", HIL_SOURCE)
        self.assertRegex(HIL_SOURCE, r"BT_ATT_ERR_INSUFFICIENT_(?:ENCRYPTION|AUTHENTICATION)")

    def test_hil_requires_full_rf_nonce_before_connect(self) -> None:
        """! @brief 이름만 같은 stale 장치에는 연결하지 않고 128-bit nonce를 요구합니다. """

        self.assertIn("constexpr std::size_t rf_nonce_length = 16U", HIL_SOURCE)
        self.assertIn("constexpr std::uint16_t rf_nonce_binding_bits = 128U", HIL_SOURCE)
        self.assertIn("validRfNonceBinding(result)", HIL_SOURCE)
        self.assertIn("BLEAdvertising.setManufacturerData", HIL_SOURCE)
        scan_callback = HIL_SOURCE[HIL_SOURCE.index("void onScanResult") :]
        scan_callback = scan_callback[: scan_callback.index("#else")]
        self.assertIn("!validRfNonceBinding(result)", scan_callback)
        self.assertNotIn("strcmp(result.name, peer_name)", scan_callback)


if __name__ == "__main__":
    unittest.main(verbosity=2)
