#!/usr/bin/env python3
"""! @brief M15 board/system 공개·구성·안전 계약을 host에서 정적으로 검증합니다. """

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
LIBRARY = REPOSITORY / "libraries" / "NUCODE_NU54DK"
HEADER = LIBRARY / "src" / "NUCODE_NU54DK.h"
SOURCE = LIBRARY / "src" / "NUCODE_NU54DK.cpp"
FEATURE = LIBRARY / "zephyr" / "feature.yml"


class M15BoardSystemContractTests(unittest.TestCase):
    """! @brief API 누락, 자동 전원 동작과 위험한 PMIC raw 접근을 차단합니다. """

    def test_public_surface_contains_board_system_contract(self) -> None:
        """! @brief M15 승인 API와 안정 오류 타입이 단일 전역 객체에 노출되는지 검사합니다. """

        text = HEADER.read_text(encoding="utf-8")
        required = (
            "enum class Error",
            "enum class ResetCause",
            "struct ResetReport",
            "enum class WakeButton",
            "class BoardSystem final",
            "boardModel()",
            "boardTarget()",
            "deviceId(",
            "resetReport(",
            "uptimeMilliseconds()",
            "watchdogBegin(",
            "watchdogFeed()",
            "watchdogStop()",
            "hardwareCounterTicks()",
            "hardwareCounterFrequency()",
            "alarmAfterMicroseconds(",
            "storageBegin()",
            "storagePut(",
            "storageGet(",
            "storageRemove(",
            "enterSystemOffOnButton(",
            "enterSystemOffAfter(",
            "extern nucode::nu54dk::BoardSystem &NU54DK;",
        )
        for token in required:
            self.assertIn(token, text, token)
        self.assertIn("성공하면 System OFF에 들어가 반환하지 않습니다", text)
        self.assertNotIn("prepareButtonWake(", text)
        self.assertNotIn("prepareTimedWake(", text)
        self.assertNotIn("enterSystemOff()", text)

    def test_pmic_writes_require_explicit_ram_only_authorization(self) -> None:
        """! @brief PMIC write가 공개 raw register 없이 매 boot 명시 승인을 요구하는지 검사합니다. """

        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("PmicWriteAuthorization", header)
        self.assertIn("complete_or_disabled", header)
        self.assertNotRegex(header, r"(?m)^\s*complete,")
        self.assertIn("acknowledge_unverified_battery_hardware = 0x4E553534UL", header)
        self.assertIn("pmicAuthorizeWrites", header)
        self.assertIn("pmicRevokeWrites", header)
        self.assertIn("pmicRequestShutdown", header)
        self.assertIn("pmicRequestShipMode", header)
        self.assertNotIn("pmicArmShutdownOnInputRemoval", header)
        self.assertNotIn("pmicArmShipModeOnInputRemoval", header)
        self.assertNotIn("pmicEnterShutdown", header)
        self.assertNotIn("pmicEnterShipMode", header)
        self.assertIn("이미 없으면 즉시 진입할 수 있습니다", header)
        self.assertIn("성공 경로가 반환된다고 보장하지 않습니다", header)
        self.assertNotIn("pmicRaw", header)
        self.assertNotIn("pmicReadRegister(", header)
        self.assertNotIn("pmicWriteRegister(", header)
        self.assertIn("atomic_t pmic_writes_authorized = ATOMIC_INIT(0)", source)
        mutation_body = source.split("Error mutatePmicRegister(", 1)[1].split(
            "\n\t}\n\n\tconst char *BoardSystem::boardModel", 1
        )[0]
        self.assertLess(
            mutation_body.index("atomic_get(&pmic_writes_authorized)"),
            mutation_body.index("pmicUpdateRegister"),
        )
        self.assertEqual(source.count("return mutatePmicRegister"), 8)
        self.assertIn("return false;", header.split("hasBatteryTemperatureProtection", 1)[1])
        self.assertIn(
            "status.charge_voltage_mv = (decoded_voltage > 4650U) ? 4650U : decoded_voltage;",
            source,
        )
        shutdown_body = source.split(
            "Error BoardSystem::pmicRequestShutdown()", 1
        )[1].split("Error BoardSystem::pmicRequestShipMode()", 1)[0]
        ship_body = source.split(
            "Error BoardSystem::pmicRequestShipMode()", 1
        )[1]
        self.assertIn("PmicRegister::ship_reset, 0x60U, 0x20U, true, false", shutdown_body)
        self.assertIn("PmicRegister::ship_reset, 0x60U, 0x40U, true, false", ship_body)

    def test_pmic_begin_is_read_only_and_driver_node_stays_disabled(self) -> None:
        """! @brief begin 경로의 register write와 PMIC DTS 자동 활성화를 차단합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        begin_body = source.split("Error BoardSystem::pmicBegin()", 1)[1].split(
            "Error BoardSystem::pmicReadStatus", 1
        )[0]
        self.assertIn("pmicReadRegister", begin_body)
        self.assertNotIn("pmicWriteRegister", begin_body)

        overlay = (LIBRARY / "zephyr" / "board-system.overlay").read_text(
            encoding="utf-8"
        )
        self.assertIn("&wdt31", overlay)
        self.assertNotIn("bq25186", overlay.lower())
        self.assertNotRegex(overlay, r"(?is)charger.*status\s*=\s*\"okay\"")

    def test_feature_merges_exact_board_system_fragments(self) -> None:
        """! @brief Arduino library 선택이 Wire와 고정 conf·overlay를 자동 병합하는지 검사합니다. """

        document = json.loads(FEATURE.read_text(encoding="utf-8"))
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["id"], "nucode.board")
        self.assertIn("wire", document["requires"])
        self.assertEqual(document["conf"], ["board-system.conf"])
        self.assertEqual(document["overlays"], ["board-system.overlay"])
        self.assertEqual(document["compatible_profiles"], ["standard"])

        configuration = (LIBRARY / "zephyr" / "board-system.conf").read_text(
            encoding="utf-8"
        )
        for symbol in (
            "CONFIG_HWINFO=y",
            "CONFIG_WATCHDOG=y",
            "CONFIG_POWEROFF=y",
            "CONFIG_PM_DEVICE=y",
            "CONFIG_FLASH=y",
            "CONFIG_ZMS=y",
            "CONFIG_SETTINGS=y",
            "CONFIG_SETTINGS_ZMS=y",
            "CONFIG_SETTINGS_ZMS_LOAD_SUBTREE_PATH=y",
        ):
            self.assertIn(symbol, configuration, symbol)
        self.assertNotIn("CONFIG_SETTINGS_ZMS_FORCE_MOUNT=y", configuration)

    def test_storage_namespace_and_bounds_are_fixed(self) -> None:
        """! @brief Sketch가 설정 저장소 전체나 무제한 값을 소유하지 못하게 합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('constexpr char settings_prefix[] = "nucode/"', source)
        self.assertIn("maximum_settings_key_length = 48U", source)
        self.assertIn("maximum_settings_value_length = 256U", source)
        self.assertIn("makeSettingsPath", source)
        self.assertNotIn("SETTINGS_ZMS_FORCE_MOUNT", source)

    def test_alarm_callback_is_deferred_out_of_grtc_isr(self) -> None:
        """! @brief GRTC ISR에서 사용자 callback을 직접 실행하지 않도록 검사합니다. """

        source = SOURCE.read_text(encoding="utf-8")
        isr_body = source.split("void alarmInterruptHandler(", 1)[1].split(
            "/** @brief 완료된 channel", 1
        )[0]
        self.assertIn("k_work_submit", isr_body)
        self.assertNotIn("callback(", isr_body)
        work_body = source.rsplit("void alarmWorkHandler(", 1)[1].split(
            "/** @brief 선택된 WakeButton", 1
        )[0]
        self.assertIn("callback(expiration, context)", work_body)

    def test_public_examples_exist_without_zephyr_sidecars(self) -> None:
        """! @brief 사용자가 prj.conf나 overlay를 편집하지 않아도 예제를 열 수 있는지 검사합니다. """

        examples = (
            "BoardInfo",
            "CounterAlarm",
            "SettingsStorage",
            "SystemOffWake",
            "WatchdogBasic",
        )
        for name in examples:
            directory = LIBRARY / "examples" / name
            self.assertTrue((directory / f"{name}.ino").is_file(), name)
            self.assertFalse((directory / "prj.conf").exists(), name)
            self.assertFalse((directory / "app.overlay").exists(), name)

        system_off = (
            LIBRARY / "examples" / "SystemOffWake" / "SystemOffWake.ino"
        ).read_text(encoding="utf-8")
        self.assertIn('strcmp(command, "BUTTON")', system_off)
        self.assertIn('strcmp(command, "TIMER")', system_off)
        setup_body = system_off.split("void setup()", 1)[1].split("void loop()", 1)[0]
        self.assertNotIn("enterSystemOffOnButton", setup_body)
        self.assertNotIn("enterSystemOffAfter", setup_body)
        self.assertIn("NU54DK.enterSystemOffOnButton(WakeButton::sw0)", system_off)
        self.assertIn("NU54DK.enterSystemOffAfter(2000000ULL)", system_off)
        self.assertNotIn("prepareButtonWake", system_off)
        self.assertNotIn("prepareTimedWake", system_off)

    def test_m15_system_off_hil_is_command_gated_and_manual(self) -> None:
        """! @brief 결합 HIL이 SWD 격리 뒤 timed와 button ARM을 순서대로 요구합니다. """

        target = (
            REPOSITORY / "tests" / "zephyr" / "m15_wake" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        runner = (
            REPOSITORY / "tests" / "hil" / "nu54dk" / "m15_system_off.py"
        ).read_text(encoding="utf-8")
        testcase = (
            REPOSITORY / "tests" / "zephyr" / "m15_wake" / "testcase.yaml"
        ).read_text(encoding="utf-8")
        timed_body = target.split("void armTimedWake()", 1)[1].split(
            "void armButtonWake", 1
        )[0]
        button_body = target.split("void armButtonWake", 1)[1].split(
            "void continueAfterTimedWake", 1
        )[0]
        self.assertLess(
            timed_body.index("waitForCommand"),
            timed_body.index("NU54DK.enterSystemOffAfter"),
        )
        self.assertLess(
            button_body.index("waitForCommand"),
            button_body.index("NU54DK.enterSystemOffOnButton"),
        )
        self.assertIn("NU54DK.enterSystemOffAfter(timed_wake_delay_us)", target)
        self.assertIn("NU54DK.enterSystemOffOnButton(WakeButton::sw0)", target)
        self.assertNotIn("prepareButtonWake", target)
        self.assertIn("NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=TIMED", target)
        self.assertIn("NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=TIMED", target)
        self.assertIn("NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=BUTTON", target)
        self.assertIn("report.cause != expected", target)
        self.assertIn('serial_port.write(f"ARM_TIMED:{nonce}\\n"', runner)
        self.assertIn('serial_port.write(f"ARM_BUTTON:{nonce}\\n"', runner)
        self.assertIn("--acknowledge-interface-switch", runner)
        self.assertIn("--acknowledge-button-wake", runner)
        self.assertIn("DISABLE_SWD_ONLY", runner)
        self.assertIn("SW0_RELEASED", runner)
        self.assertIn("RESET_DEBUG", runner)
        self.assertRegex(runner, r'parser\.add_argument\(\s*"--board-id",\s*required=True')
        self.assertIn("MINIMUM_BUTTON_PROMPT_MS = 2000", runner)
        self.assertIn("build_only: true", testcase)
        self.assertNotIn("harness:", testcase)


if __name__ == "__main__":
    unittest.main(verbosity=2)
