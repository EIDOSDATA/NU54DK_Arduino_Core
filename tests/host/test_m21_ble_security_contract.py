#!/usr/bin/env python3
"""! @brief M21 BLE security·표준 profile의 공개·안전·통합 계약을 검증합니다. """

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
LIBRARY = REPOSITORY / "libraries" / "NUCODE_BLE_Security"
HEADER = LIBRARY / "src" / "NUCODE_BLE_Security.h"
SOURCE = LIBRARY / "src" / "NUCODE_BLE_Security.cpp"
FEATURE = LIBRARY / "zephyr" / "feature.yml"
CONF = LIBRARY / "zephyr" / "ble-security.conf"
EXAMPLE = LIBRARY / "examples" / "SecureKeyboard" / "SecureKeyboard.ino"
COMMON_INTERNAL = (
    REPOSITORY / "libraries" / "NUCODE_BLE" / "src" / "internal" / "NUCODE_BLE_Internal.h"
)
BOARD_CONF = REPOSITORY / "libraries" / "NUCODE_NU54DK" / "zephyr" / "board-system.conf"
COMBINED_CONTRACT = REPOSITORY / "tests" / "zephyr" / "m21_ble_board_contract"
HIL_SOURCE = REPOSITORY / "tests" / "zephyr" / "m21_ble_hil" / "src" / "main.cpp"


class M21BleSecurityContractTests(unittest.TestCase):
    """! @brief M19/M20 lifecycle와 겹치지 않는 M21 surface를 고정합니다. """

    def test_public_surface_covers_security_profiles_and_hid(self) -> None:
        """! @brief pairing·bond·BAS·DIS·keyboard API가 모두 공개되는지 확인합니다. """

        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "enum class SecurityLevel",
            "enum class BondState",
            "enum class SecurityEvent",
            "bond_persistence_pending",
            "bond_restored_candidate",
            "bond_verified",
            "bond_removal_requested",
            "all_bonds_removal_requested",
            "enum class SecurityError",
            "struct PeerAddress",
            "struct SecurityEventRecord",
            "struct SecurityConfig",
            "class SecurityManager final",
            "requestSecurity()",
            "acceptPairing(",
            "enterPasskey(",
            "confirmPasskey(",
            "cancelPairing()",
            "bondCount()",
            "copyBonds(",
            "eraseBond(",
            "eraseAllBonds()",
            "bondState()",
            "class BatteryService final",
            "class DeviceInformationService final",
            "class HidKeyboard final",
            "BLESecurity",
            "BLEBattery",
            "BLEDeviceInformation",
            "BLEKeyboard",
        ):
            self.assertIn(token, text, token)

        self.assertIn("#include <NUCODE_BLE.h>", text)
        self.assertNotRegex(text, r"#include\s*[<\"]zephyr/")
        self.assertNotRegex(text, r"#include\s*[<\"]bluetooth/")

    def test_backend_reuses_common_stack_and_connection_hooks(self) -> None:
        """! @brief M21이 bt_enable이나 별도 connection callback을 만들지 못하게 합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("bt_enable(", source)
        self.assertNotIn("BT_CONN_CB_DEFINE", source)
        self.assertIn("internal::settingsReady()", source)
        self.assertIn("void securityConnected(struct bt_conn *connection)", source)
        self.assertIn("void securityDisconnected(struct bt_conn *connection)", source)
        self.assertRegex(
            source,
            r"void\s+securityChanged\s*\(\s*struct\s+bt_conn\s*\*\s*connection\s*,\s*"
            r"bt_security_t\s+level\s*,\s*enum\s+bt_security_err\s+error",
        )

        common = COMMON_INTERNAL.read_text(encoding="utf-8")
        for signature in (
            "void securityConnected(struct bt_conn *connection) noexcept;",
            "void securityDisconnected(struct bt_conn *connection) noexcept;",
            "void securityChanged(struct bt_conn *connection, bt_security_t level,",
            "bool settingsReady() noexcept;",
            "int settingsResult() noexcept;",
        ):
            self.assertIn(signature, common, signature)

    def test_library_discovery_phase_excludes_internal_zephyr_backend(self) -> None:
        """! @brief Arduino 탐색 compile에서는 공개 header만 해석하도록 고정합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        public_include = source.index("#include <NUCODE_BLE_Security.h>")
        guard = source.index("#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)")
        internal_include = source.index("#include <internal/NUCODE_BLE_Internal.h>")
        self.assertLess(public_include, guard)
        self.assertLess(guard, internal_include)
        self.assertTrue(source.rstrip().endswith("#endif"))

        backend = (
            LIBRARY / "src" / "internal" / "NUCODE_BLE_HidsBackend.c"
        ).read_text(encoding="utf-8")
        self.assertIn("#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)", backend)
        self.assertTrue(backend.rstrip().endswith("#endif"))

    def test_pairing_callbacks_defer_user_code_and_never_log_secrets(self) -> None:
        """! @brief stack callback에서 Sketch callback·Serial passkey 출력을 금지합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("K_MSGQ_DEFINE(security_event_queue", source)
        self.assertIn("k_msgq_put", source)
        self.assertIn("k_msgq_get", source)
        self.assertIn("SecurityManager::poll", source)
        self.assertNotRegex(source, r"\b(?:Serial|printk|printf)\s*\(")

        for callback in (
            "passkeyDisplay",
            "passkeyEntry",
            "passkeyConfirm",
            "pairingConfirm",
            "pairingComplete",
            "pairingFailed",
        ):
            match = re.search(
                rf"\b{callback}\s*\([^{{;]*\)\s*\{{(?P<body>.*?)\n\}}",
                source,
                re.DOTALL,
            )
            self.assertIsNotNone(match, callback)
            self.assertNotIn("security_event_callback(", match.group("body"))

        example = EXAMPLE.read_text(encoding="utf-8")
        self.assertNotRegex(example, r"Serial\.(?:print|println)\s*\([^\n]*(?:passkey|key material)")
        self.assertNotIn("record.passkey", example)

    def test_bond_is_verified_only_after_reboot_key_restore(self) -> None:
        """! @brief 같은 boot의 메모리 목록을 persistence 성공으로 오판하지 않습니다. """

        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")
        for token in (
            "persistence_pending",
            "restored_candidate",
            "verified",
            "removal_requested",
        ):
            self.assertIn(token, header, token)

        self.assertNotIn("settings_save()", source)
        self.assertNotIn("bondExists", source)
        self.assertIn("captureStartupBonds()", source)
        self.assertIn("isStartupBond(peer)", source)
        self.assertIn("level >= BT_SECURITY_L2", source)
        self.assertIn("BondState::restored_candidate", source)
        self.assertIn("BondState::verified", source)
        self.assertIn("return currentBondState() == BondState::verified", source)
        self.assertIn("bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY)", source)
        self.assertNotIn("bond_deleted,", header)
        self.assertIn("실제 영속 삭제 완료를 뜻하지 않습니다", header)
        self.assertNotIn("factoryReset", HEADER.read_text(encoding="utf-8"))

    def test_feature_enables_smp_settings_bas_dis_and_encrypted_hids(self) -> None:
        """! @brief 별도 feature가 표준 profile dependency를 완전하게 선언하는지 검사합니다. """

        feature = json.loads(FEATURE.read_text(encoding="utf-8"))
        self.assertEqual(feature["id"], "nucode.ble.security")
        self.assertEqual(feature["requires"], ["ble"])
        self.assertEqual(feature["compatible_profiles"], ["ble"])
        self.assertEqual(feature["conf"], ["ble-security.conf"])

        conf = CONF.read_text(encoding="utf-8")
        for symbol in (
            "CONFIG_BT_SMP=y",
            "CONFIG_BT_SMP_APP_PAIRING_ACCEPT=y",
            "CONFIG_BT_SETTINGS=y",
            "CONFIG_BT_SMP_SC_PAIR_ONLY=n",
            "CONFIG_SETTINGS_ZMS=y",
            "CONFIG_BT_BAS=y",
            "CONFIG_BT_DIS=y",
            "CONFIG_BT_DIS_SETTINGS=y",
            "CONFIG_BT_HIDS=y",
            "CONFIG_BT_HIDS_DEFAULT_PERM_RW_ENCRYPT=y",
        ):
            self.assertIn(symbol, conf, symbol)
        self.assertNotIn("CONFIG_BT_FIXED_PASSKEY", conf)

    def test_board_and_security_share_zms_settings_backend(self) -> None:
        """! @brief board/system과 BLE bond 저장소가 단일 ZMS backend를 공유합니다. """

        security_conf = CONF.read_text(encoding="utf-8")
        board_conf = BOARD_CONF.read_text(encoding="utf-8")
        for conf in (security_conf, board_conf):
            self.assertIn("CONFIG_ZMS=y", conf)
            self.assertIn("CONFIG_SETTINGS_ZMS=y", conf)
            self.assertNotIn("CONFIG_NVS=y", conf)
            self.assertNotIn("CONFIG_SETTINGS_NVS=y", conf)

        cmake = (COMBINED_CONTRACT / "CMakeLists.txt").read_text(encoding="utf-8")
        source = (COMBINED_CONTRACT / "src" / "main.cpp").read_text(encoding="utf-8")
        self.assertIn("board-system.conf", cmake)
        self.assertIn("ble-security.conf", cmake)
        self.assertIn("NUCODE_NU54DK.cpp", cmake)
        self.assertIn("#include <NUCODE_NU54DK.h>", source)
        self.assertIn("#include <NUCODE_BLE_Security.h>", source)

    def test_hid_is_protocol_automated_but_os_claim_is_absent(self) -> None:
        """! @brief protocol report와 OS 수동 확인 경계를 혼동하지 않도록 고정합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("keyboard_report_map", source)
        self.assertIn("bt_hids_inp_rep_send", source)
        self.assertIn("bt_hids_boot_kb_inp_rep_send", source)
        self.assertIn("parameters.pm_evt_handler = hidsProtocolModeChanged", source)
        self.assertIn("K_MUTEX_DEFINE(hid_api_mutex)", source)
        self.assertIn("hid_connection_state.connection == connection", source)
        self.assertIn("BT_SECURITY_L2", source)
        example = EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("BLEKeyboard.press", example)
        self.assertIn("BLEKeyboard.releaseAll", example)
        self.assertNotIn("Windows PASS", example)
        self.assertNotIn("smartphone PASS", example)

    def test_hil_initializes_runtime_profiles_after_stack_enable(self) -> None:
        """! @brief HIDS는 stack 전에 등록하고 DIS·BAS runtime 값은 stack 뒤에 설정합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        security_begin = source.index("BLESecurity.begin(security)")
        hids_begin = source.index("BLEKeyboard.begin()")
        device_begin = source.index("BLEDevice.begin(")
        dis_configure = source.index("BLEDeviceInformation.configure(information)")
        battery_level = source.index("BLEBattery.setLevel(expected_battery_read)", dis_configure)

        self.assertLess(security_begin, hids_begin)
        self.assertLess(hids_begin, device_begin)
        self.assertLess(device_begin, dis_configure)
        self.assertLess(dis_configure, battery_level)
        self.assertIn('fail("dis-config")', source)
        self.assertIn('fail("battery-init")', source)
        self.assertNotIn('fail("standard-profile-init")', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
