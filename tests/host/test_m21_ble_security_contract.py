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
HIL_CONF = REPOSITORY / "tests" / "zephyr" / "m21_ble_hil" / "prj.conf"


class M21BleSecurityContractTests(unittest.TestCase):
    """! @brief M19/M20 lifecycle와 겹치지 않는 M21 surface를 고정합니다. """

    def test_public_surface_covers_security_profiles_and_hid(self) -> None:
        """! @brief pairing·bond·BAS·DIS·keyboard API가 모두 공개되는지 확인합니다. """

        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "enum class SecurityLevel",
            "enum class SecurityIoCapability",
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

    def test_auth_callbacks_match_the_configured_io_capability(self) -> None:
        """! @brief 실제 장치 입출력보다 강한 SMP capability를 광고하지 않습니다. """

        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        example = EXAMPLE.read_text(encoding="utf-8")

        for capability in (
            "no_input_output",
            "display_only",
            "keyboard_only",
            "display_yes_no",
            "keyboard_display",
        ):
            self.assertIn(capability, header)

        prepare = source[source.index("void prepareAuthenticationCallbacks") :]
        prepare = prepare[: prepare.index("bool releaseActiveConnection")]
        self.assertIn("SecurityIoCapability capability", prepare)
        self.assertIn("authentication_callbacks.pairing_accept = pairingAccept", prepare)
        self.assertIn("authentication_callbacks.pairing_confirm = pairingConfirm", prepare)
        self.assertIn("case SecurityIoCapability::no_input_output:", prepare)
        self.assertIn("case SecurityIoCapability::display_yes_no:", prepare)
        self.assertIn("case SecurityIoCapability::keyboard_display:", prepare)
        self.assertIn("authentication_callbacks.passkey_display = passkeyDisplay", prepare)
        self.assertIn("authentication_callbacks.passkey_entry = passkeyEntry", prepare)
        self.assertIn("authentication_callbacks.passkey_confirm = passkeyConfirm", prepare)

        no_io = prepare.split("case SecurityIoCapability::no_input_output:", 1)[1]
        no_io = no_io.split("case SecurityIoCapability::display_only:", 1)[0]
        self.assertNotIn("authentication_callbacks.passkey_", no_io)

        display_only = prepare.split(
            "case SecurityIoCapability::display_only:", 1
        )[1]
        display_only = display_only.split(
            "case SecurityIoCapability::keyboard_only:", 1
        )[0]
        self.assertIn("authentication_callbacks.passkey_display", display_only)
        self.assertNotIn("authentication_callbacks.passkey_entry", display_only)
        self.assertNotIn("authentication_callbacks.passkey_confirm", display_only)

        keyboard_only = prepare.split(
            "case SecurityIoCapability::keyboard_only:", 1
        )[1]
        keyboard_only = keyboard_only.split(
            "case SecurityIoCapability::display_yes_no:", 1
        )[0]
        self.assertNotIn("authentication_callbacks.passkey_display", keyboard_only)
        self.assertIn("authentication_callbacks.passkey_entry", keyboard_only)
        self.assertNotIn("authentication_callbacks.passkey_confirm", keyboard_only)

        display_yes_no = prepare.split(
            "case SecurityIoCapability::display_yes_no:", 1
        )[1]
        display_yes_no = display_yes_no.split(
            "case SecurityIoCapability::keyboard_display:", 1
        )[0]
        self.assertIn("authentication_callbacks.passkey_display", display_yes_no)
        self.assertIn("authentication_callbacks.passkey_confirm", display_yes_no)
        self.assertNotIn("authentication_callbacks.passkey_entry", display_yes_no)

        keyboard_display = prepare.split(
            "case SecurityIoCapability::keyboard_display:", 1
        )[1]
        keyboard_display = keyboard_display.split("authentication_info_callbacks = {}", 1)[0]
        self.assertIn("authentication_callbacks.passkey_display", keyboard_display)
        self.assertIn("authentication_callbacks.passkey_entry", keyboard_display)
        self.assertIn("authentication_callbacks.passkey_confirm", keyboard_display)

        self.assertIn(
            "SecurityIoCapability::no_input_output",
            example,
        )
        self.assertNotIn("BLESecurity.confirmPasskey", example)
        self.assertRegex(
            example,
            r"SecurityEvent::pairing_cancelled:[\s\S]*?"
            r"pairing_confirmation_pending = false;",
        )

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

    def test_already_encrypted_restore_is_verified_without_duplicate_event(self) -> None:
        """! @brief connected 시점에 이미 L2인 bond 복원 race를 즉시 검증합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        connected = source[source.index("void securityConnected") :]
        connected = connected[: connected.index("void securityDisconnected")]
        changed = source[source.index("void securityChanged") :]
        changed = changed[: changed.index("\n        }\n\n    }", 1)]

        self.assertIn("const bt_security_t level = bt_conn_get_security(connection)", connected)
        self.assertIn("verifySecureBond(connection, level)", connected)
        self.assertIn("queueSecurityChangedIfNew(connection, level)", connected)
        self.assertIn("verifySecureBond(connection, level)", changed)
        self.assertIn("queueSecurityChangedIfNew(connection, level)", changed)

        deduplicator = source[source.index("void queueSecurityChangedIfNew") :]
        deduplicator = deduplicator[: deduplicator.index("\n    }", 1) + 6]
        deduplicator_compact = " ".join(deduplicator.split())
        self.assertIn("published = atomic_set(", deduplicator_compact)
        self.assertNotIn("atomic_get(&published_level_value)", deduplicator)
        self.assertIn("published != static_cast<atomic_val_t>(level)", deduplicator)

    def test_security_request_synchronizes_an_already_secured_link(self) -> None:
        """! @brief 보안 요청 전·후에 이미 충족된 link를 event와 bond 상태에 동기화합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        synchronizer = source[source.index("bool synchronizeSatisfiedSecurity") :]
        synchronizer = synchronizer[: synchronizer.index("\n    }", 1) + 6]
        request = source[source.index("bool SecurityManager::requestSecurity") :]
        request = request[: request.index("bool SecurityManager::acceptPairing")]

        self.assertIn("bt_conn_get_security(connection)", synchronizer)
        self.assertIn("level < required_level", synchronizer)
        self.assertIn("verifySecureBond(connection, level)", synchronizer)
        self.assertIn("queueSecurityChangedIfNew(connection, level)", synchronizer)
        self.assertGreaterEqual(request.count("synchronizeSatisfiedSecurity("), 2)
        self.assertLess(
            request.index("synchronizeSatisfiedSecurity(connection, required_level)"),
            request.index("bt_conn_set_security(connection, required_level)"),
        )

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
        backend = (LIBRARY / "src/internal/NUCODE_BLE_HidsBackend.c").read_text(encoding="utf-8")
        self.assertIn("bt_hids_inp_rep_send", backend)
        self.assertIn("bt_hids_boot_kb_inp_rep_send", backend)
        self.assertIn("parameters.pm_evt_handler = protocol_mode_changed", backend)
        self.assertIn("nucode_ble_hids_initialize", source)
        self.assertIn("hidsProtocolModeChanged);", source)
        self.assertNotIn("#include <bluetooth/services/hids.h>", source)
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

    def test_hil_clear_stops_only_active_gap_operations(self) -> None:
        """! @brief 초기 CLEAR가 유휴 GAP 객체의 오류 event를 만들지 않도록 고정합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        erase = source[source.index("void eraseBonds") :]
        erase = erase[: erase.index("void executeCommand")]

        self.assertRegex(
            erase,
            r"if\s*\(BLEScan\.running\(\)\)\s*\{\s*"
            r"static_cast<void>\(BLEScan\.stop\(\)\);\s*\}",
        )
        self.assertRegex(
            erase,
            r"if\s*\(BLEConnection\.connected\(\)\)\s*\{\s*"
            r"static_cast<void>\(BLEConnection\.disconnect\(\)\);\s*\}",
        )
        self.assertRegex(
            erase,
            r"if\s*\(BLEAdvertising\.running\(\)\)\s*\{\s*"
            r"static_cast<void>\(BLEAdvertising\.stop\(\)\);\s*\}",
        )

    def test_hil_uses_typed_characteristic_and_auto_ccc_discovery(self) -> None:
        """! @brief 원격 characteristic 값과 CCC를 유효한 Zephyr discovery 방식으로 찾습니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "discover_parameters.type = BT_GATT_DISCOVER_CHARACTERISTIC", source
        )
        self.assertNotIn("BT_GATT_DISCOVER_ATTRIBUTE", source)
        self.assertIn(
            "battery_subscription.ccc_handle = BT_GATT_AUTO_DISCOVER_CCC_HANDLE",
            source,
        )
        self.assertIn(
            "report_subscription.ccc_handle = BT_GATT_AUTO_DISCOVER_CCC_HANDLE",
            source,
        )
        self.assertIn("battery_subscription.disc_params = &battery_ccc_discovery", source)
        self.assertIn("report_subscription.disc_params = &report_ccc_discovery", source)
        self.assertIn("characteristic->properties & BT_GATT_CHRC_NOTIFY", source)

    def test_hil_observes_encrypted_read_denial_before_security_request(self) -> None:
        """! @brief ATT 자동 보안 재시도를 끄고 평문 HIDS read 거부를 직접 검증합니다. """

        conf = HIL_CONF.read_text(encoding="utf-8")
        source = HIL_SOURCE.read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_ATT_RETRY_ON_SEC_ERR=n", conf)
        self.assertIn("BT_ATT_ERR_INSUFFICIENT_ENCRYPTION", source)
        self.assertIn('fail("secure-gatt-not-denied")', source)
        self.assertIn("BLESecurity.requestSecurity()", source)

    def test_hil_continues_when_security_was_satisfied_before_event_poll(self) -> None:
        """! @brief 보안 event와 GAP/read 상태기의 교차 순서에도 profile 검증을 재개합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        helper = source[source.index("void continueCentralProfileIfSecured") :]
        helper = helper[: helper.index("/** @brief 단일 remote read")]
        pre_security = source[source.index("void finishPreSecurityRead") :]
        pre_security = pre_security[: pre_security.index("void reportCentralPhase")]
        gap = source[source.index("void onGapEvent") :]
        gap = gap[: gap.index("void resetPhaseState")]

        self.assertIn("BLESecurity.currentLevel()", helper)
        self.assertIn("SecurityLevel::encrypted", helper)
        self.assertIn("security_request_pending", helper)
        self.assertIn("secured = true", helper)
        self.assertIn("!secured_profile_started && !discovery_active", helper)
        self.assertIn("beginDiscovery(false)", helper)
        self.assertNotIn("continueCentralProfileIfSecured()", pre_security)
        self.assertNotIn("BLESecurity.requestSecurity()", pre_security)
        self.assertIn("security_request_pending = true", pre_security)
        self.assertIn("security_request_due_ms = k_uptime_get()", pre_security)
        drive = source[source.index("void driveCentralProfile") :]
        drive = drive[: drive.index("#endif", 1)]
        self.assertIn("continueCentralProfileIfSecured()", drive)

    def test_hil_defers_non_fresh_security_request_to_main_loop(self) -> None:
        """! @brief 연결 직후 요청을 미루고 이미 진행 중인 SMP는 bounded 간격으로 재확인합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        gap = source[source.index("void onGapEvent") :]
        gap = gap[: gap.index("void resetPhaseState")]
        drive = source[source.index("void driveCentralProfile") :]
        drive = drive[: drive.index("/** @brief 광고 payload")]

        self.assertIn("security_request_delay_ms = 500", source)
        self.assertIn("security_request_retry_ms = 100", source)
        self.assertIn("security_request_timeout_ms = 30000", source)
        self.assertIn("security_request_pending = true", gap)
        self.assertIn("k_uptime_get() + security_request_delay_ms", gap)
        self.assertNotIn("BLESecurity.requestSecurity()", gap)
        self.assertIn("security_request_pending", drive)
        self.assertIn("k_uptime_get() >= security_request_due_ms", drive)
        self.assertIn("BLESecurity.requestSecurity()", drive)
        self.assertLess(
            drive.index("BLESecurity.requestSecurity()"),
            drive.index("continueCentralProfileIfSecured()"),
        )
        self.assertRegex(
            drive,
            r"if\s*\(!BLESecurity\.requestSecurity\(\)\)\s*\{\s*"
            r"[\s\S]*?BLESecurity\.lastError\(\)\s*==\s*"
            r"nucode::ble::SecurityError::busy\)\s*\{\s*"
            r"if\s*\(k_uptime_get\(\)\s*>=\s*security_request_deadline_ms\)"
            r"\s*\{\s*fail\(\"security-timeout\"\);\s*return;\s*\}\s*"
            r"security_request_pending\s*=\s*true;\s*"
            r"security_request_due_ms\s*=\s*"
            r"k_uptime_get\(\)\s*\+\s*security_request_retry_ms;\s*return;\s*\}\s*"
            r"fail\(\"security-request\"\);\s*return;\s*\}\s*return;\s*\}\s*"
            r"continueCentralProfileIfSecured\(\);",
        )

    def test_hil_serializes_all_gatt_transitions_by_main_loop(self) -> None:
        """! @brief discovery·read·subscribe 전이를 one-shot main-loop 작업으로 직렬화합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        starter = source[source.index("bool startPendingGattAction") :]
        starter = starter[: starter.index("void driveCentralProfile")]
        drive = source[source.index("void driveCentralProfile") :]
        drive = drive[: drive.index("/** @brief 광고 payload")]
        advance = source[source.index("void advanceNormalRead") :]
        advance = advance[: advance.index("void finishPreSecurityRead")]
        reset = source[source.index("void resetPhaseState") :]
        reset = reset[: reset.index("void startProtocol")]

        self.assertIn("startPendingGattAction()", drive)
        self.assertIn("pending_gatt_action = CentralGattAction::none", starter)
        for action in (
            "read_pre_security",
            "read_battery",
            "read_manufacturer",
            "read_model",
            "read_serial",
            "read_report_map",
            "subscribe_battery",
            "subscribe_report",
        ):
            self.assertIn(f"CentralGattAction::{action}", starter)
        self.assertNotIn("beginRead(", advance)
        self.assertIn("CentralGattAction::read_manufacturer", advance)
        self.assertIn("CentralGattAction::subscribe_battery", advance)
        self.assertRegex(
            drive,
            r"if\s*\(atomic_cas\(&discovery_complete, 1, 0\)\)"
            r"[\s\S]*?pending_gatt_action = discovery_for_pre_security"
            r"[\s\S]*?return;",
        )
        self.assertIn("CentralGattAction::subscribe_report", drive)
        self.assertIn("pending_gatt_action = CentralGattAction::none", reset)

    def test_hil_repeats_profile_notifications_after_server_ccc_restore(self) -> None:
        """! @brief client 구독 재등록 전 송신 성공 race에도 profile 값을 반복 전달합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        peripheral = source[source.index("void drivePeripheralProfile") :]
        peripheral = peripheral[: peripheral.index("void onSecurityEvent")]
        report = source[source.index("std::uint8_t onReportNotification") :]
        report = report[: report.index("void onBatterySubscribed")]

        first_guard = peripheral[: peripheral.index("if (!key_down_sent)")]
        self.assertNotIn("phase_reported", first_guard)
        self.assertIn("next_profile_send_ms = k_uptime_get() + 500", peripheral)
        self.assertRegex(
            peripheral,
            r"if\s*\(phase_reported\)\s*\{\s*return;\s*\}\s*"
            r"if\s*\(!phaseBondReady\(\)\)",
        )
        self.assertIn("key_down_passed && key_release_passed", report)

    def test_hil_bounds_pre_security_link_recovery_in_main_loop(self) -> None:
        """! @brief 연결 성립 transient만 phase당 세 번까지 callback 밖에서 복구합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        scheduler = source[source.index("void scheduleLinkRetry") :]
        scheduler = scheduler[: scheduler.index("/** @brief nonce")]
        driver = source[source.index("bool driveLinkRetry") :]
        driver = driver[: driver.index("/** @brief 새 pairing")]
        gap = source[source.index("void onGapEvent") :]
        gap = gap[: gap.index("void resetPhaseState")]
        reset = source[source.index("void resetPhaseState") :]
        reset = reset[: reset.index("void startProtocol")]
        loop = source[source.index("void loop()") :]

        self.assertIn("link_retry_delay_ms = 500", source)
        self.assertIn("maximum_link_retries = 3U", source)
        self.assertIn("link_retry_count >= maximum_link_retries", scheduler)
        self.assertIn('fail("link-retry-exhausted")', scheduler)
        self.assertIn("run_mode != RunMode::erased_probe", gap)
        self.assertIn("!connection_was_secured", gap)
        self.assertIn("pairing_event_count == 0U", gap)
        self.assertIn("scheduleLinkRetry()", gap)
        self.assertNotIn("BLEScan.start", gap)
        self.assertNotIn("BLEAdvertising.start", gap)
        self.assertIn("BLEScan.running() || BLEScan.start(true)", driver)
        self.assertIn("BLEAdvertising.running() || BLEAdvertising.start()", driver)
        self.assertIn("link_retry_count = 0U", reset)
        self.assertLess(loop.index("BLEDevice.poll()"), loop.index("BLESecurity.poll()"))
        self.assertLess(
            loop.index("BLESecurity.poll()"),
            loop.index("if (!protocol_started || protocol_failed)"),
        )
        self.assertLess(
            loop.index("if (!protocol_started || protocol_failed)"),
            loop.index("driveLinkRetry()"),
        )
        self.assertLess(loop.index("driveLinkRetry()"), loop.index("driveCentralProfile()"))

    def test_hil_invalidates_stale_gatt_callbacks_on_disconnect_and_reset(self) -> None:
        """! @brief 이전 연결 callback이 새 phase 완료 flag를 오염하지 못하게 세대를 무효화합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        invalidator = source[source.index("void invalidateCentralGattState") :]
        invalidator = invalidator[: invalidator.index("/** @brief 한 원격 characteristic")]
        gap = source[source.index("void onGapEvent") :]
        gap = gap[: gap.index("void resetPhaseState")]
        reset = source[source.index("void resetPhaseState") :]
        reset = reset[: reset.index("void startProtocol")]

        self.assertIn("++gatt_phase_generation", invalidator)
        for completion in (
            "discovery_complete",
            "read_complete",
            "battery_subscription_complete",
            "report_subscription_complete",
        ):
            self.assertIn(f"atomic_set(&{completion}, 0)", invalidator)
        self.assertGreaterEqual(
            source.count("!= gatt_phase_generation"),
            6,
        )
        self.assertIn("invalidateCentralGattState()", gap)
        self.assertIn("invalidateCentralGattState()", reset)

    def test_erased_probe_rejects_every_interactive_pairing_path(self) -> None:
        """! @brief 이전 key 거부 단계에서 Just Works와 passkey 재 pairing을 모두 거부합니다. """

        source = HIL_SOURCE.read_text(encoding="utf-8")
        handler = source[source.index("void onSecurityEvent") :]
        handler = handler[: handler.index("void onGapEvent")]

        self.assertIn("BLESecurity.acceptPairing(false)", handler)
        self.assertIn("BLESecurity.confirmPasskey(false)", handler)
        self.assertIn("BLESecurity.cancelPairing()", handler)
        self.assertGreaterEqual(handler.count("rejectProbePairing("), 3)
        rejector = source[source.index("void rejectProbePairing") :]
        rejector = rejector[: rejector.index("void onSecurityEvent")]
        self.assertIn("old_key_pairing_requested = true", rejector)
        self.assertIn("if (BLEConnection.connected())", rejector)
        self.assertIn("if (!rejected && !disconnect_requested)", rejector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
