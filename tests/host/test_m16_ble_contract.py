#!/usr/bin/env python3
"""! @brief M16 BLE NUS Stream 공개 API와 callback 안전 계약을 검증합니다. """

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
LIBRARY = REPOSITORY / "libraries" / "NUCODE_BLE"
HEADER = LIBRARY / "src" / "NUCODE_BLE.h"
SOURCE = LIBRARY / "src" / "NUCODE_BLE.cpp"
PROPERTIES = LIBRARY / "library.properties"
FEATURE = LIBRARY / "zephyr" / "feature.yml"
PROFILE_ROOT = REPOSITORY / "variants" / "nu54dk" / "profiles" / "ble"
PERIPHERAL_EXAMPLE = LIBRARY / "examples" / "NUSPeripheral" / "NUSPeripheral.ino"


def function_body(source: str, function_name: str) -> str:
    """! @brief C/C++ source에서 지정 함수의 중괄호 본문을 반환합니다. """

    match = re.search(
        rf"\b{re.escape(function_name)}\s*\([^;{{}}]*\)\s*(?:noexcept\s*)?\{{",
        source,
    )
    if match is None:
        raise AssertionError(f"함수 본문을 찾지 못했습니다: {function_name}")

    opening = source.find("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AssertionError(f"함수 중괄호가 닫히지 않았습니다: {function_name}")


def properties_document(path: Path) -> dict[str, str]:
    """! @brief Arduino library.properties를 key-value 문서로 읽습니다. """

    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise AssertionError(f"잘못된 library.properties 행입니다: {raw_line}")
        result[key.strip()] = value.strip()
    return result


class M16BleNusContractTests(unittest.TestCase):
    """! @brief NUS 전용 Stream API와 고정 자원 callback 전달 계약을 검증합니다. """

    def test_public_nus_stream_surface_is_complete(self) -> None:
        """! @brief peripheral과 central이 공유하는 Arduino Stream 표면을 고정합니다. """

        self.assertTrue(HEADER.is_file(), HEADER)
        text = HEADER.read_text(encoding="utf-8")
        required_tokens = (
            "namespace nucode::ble",
            "enum class Event",
            "enum class Error",
            "class NusSerial final",
            "beginPeripheral(",
            "beginCentral()",
            "startAdvertising()",
            "scanForNus(",
            "poll()",
            "connected()",
            "ready()",
            "disconnect()",
            "end()",
            "available()",
            "read()",
            "peek()",
            "flush()",
            "write(std::uint8_t",
            "write(const std::uint8_t",
            "onEvent(",
            "mtu()",
            "droppedRxBytes()",
            "lastError()",
            "lastDriverError()",
            "BLESerial",
        )
        for token in required_tokens:
            self.assertIn(token, text, token)

        self.assertRegex(text, r"class\s+NusSerial\s+final\s*:\s*public\s+(?:arduino::)?Stream")
        self.assertRegex(text, r"beginPeripheral\s*\(\s*const\s+char\s*\*\s*\w+")
        self.assertRegex(text, r"scanForNus\s*\(\s*const\s+char\s*\*\s*\w+")
        self.assertRegex(
            text,
            r"using\s+EventCallback\s*=\s*void\s*\(\s*\*\s*\)\s*"
            r"\(\s*Event(?:\s+\w+)?\s*,\s*void\s*\*\s*(?:\w+)?\s*\)",
        )
        self.assertRegex(
            text,
            r"extern\s+nucode::ble::NusSerial\s*(?:&\s*)?BLESerial\s*;",
        )
        self.assertNotRegex(text, r"#include\s*[<\"]zephyr/")
        self.assertNotRegex(text, r"#include\s*[<\"]bluetooth/")

    def test_arduino_library_metadata_and_example_contract(self) -> None:
        """! @brief Boards Manager가 NUS library와 양쪽 역할 예제를 찾는지 검증합니다. """

        self.assertTrue(PROPERTIES.is_file(), PROPERTIES)
        document = properties_document(PROPERTIES)
        self.assertEqual(document.get("name"), "NUCODE BLE")
        self.assertEqual(document.get("architectures"), "zephyr")
        self.assertEqual(document.get("includes"), "NUCODE_BLE.h")
        self.assertEqual(document.get("category"), "Communication")

        for name in ("NUSPeripheral", "NUSCentral"):
            directory = LIBRARY / "examples" / name
            self.assertTrue((directory / f"{name}.ino").is_file(), name)
            self.assertFalse((directory / "prj.conf").exists(), name)
            self.assertFalse((directory / "app.overlay").exists(), name)

    def test_peripheral_example_keeps_received_data_free_of_event_logs(self) -> None:
        """! @brief 수신 event 로그가 NUS-Serial 데이터 경로에 섞이지 않도록 고정합니다. """

        source = PERIPHERAL_EXAMPLE.read_text(encoding="utf-8")
        callback = function_body(source, "onBleEvent")
        self.assertNotIn("BLE event:", callback)

        received = re.search(
            r"case\s+nucode::ble::Event::received\s*:\s*"
            r"(?P<body>.*?)(?=\bcase\s+|\bdefault\s*:|$)",
            callback,
            re.DOTALL,
        )
        self.assertIsNotNone(received)
        received_body = received.group("body") if received is not None else ""
        self.assertIn("break;", received_body)
        self.assertNotRegex(received_body, r"\bSerial\s*\.")

        for event_name in (
            "advertising_started",
            "connected",
            "ready",
            "disconnected",
            "error",
        ):
            self.assertIn(f"nucode::ble::Event::{event_name}", callback)

        error = re.search(
            r"case\s+nucode::ble::Event::error\s*:\s*"
            r"(?P<body>.*?)(?=\bcase\s+|\bdefault\s*:|$)",
            callback,
            re.DOTALL,
        )
        self.assertIsNotNone(error)
        error_body = error.group("body") if error is not None else ""
        self.assertIn('Serial.println("BLE error")', error_body)
        self.assertNotIn("lastError", error_body)
        self.assertNotIn("lastDriverError", error_body)

    def test_ble_profile_feature_and_board_menu_are_wired(self) -> None:
        """! @brief ble profile 선택만으로 필요한 NUS feature가 병합되는지 검사합니다. """

        self.assertTrue((PROFILE_ROOT / "profile.json").is_file(), PROFILE_ROOT)
        profile = json.loads(
            (PROFILE_ROOT / "profile.json").read_text(encoding="utf-8")
        )
        self.assertEqual(profile["schema_version"], 1)
        self.assertEqual(profile["id"], "ble")
        self.assertEqual(profile["board"], "nucode:zephyr:nu54dk")
        self.assertEqual(
            profile["zephyr_board"], "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
        )
        self.assertIn("ble", profile["features"])

        feature = json.loads(FEATURE.read_text(encoding="utf-8"))
        self.assertEqual(feature["schema_version"], 1)
        self.assertEqual(feature["id"], "nucode.ble.nus")
        self.assertIn("ble", feature["requires"])
        self.assertEqual(feature["compatible_profiles"], ["ble"])
        self.assertTrue(feature["conf"])

        boards = (REPOSITORY / "boards.txt").read_text(encoding="utf-8")
        self.assertRegex(boards, r"(?m)^nu54dk\.menu\.feature_set\.ble=.+$")
        self.assertIn(
            "nu54dk.menu.feature_set.ble.build.nu54_profile=ble", boards
        )

        builder = (
            REPOSITORY / "tools" / "nu54-builder" / "src" / "nu54_builder_impl" / "common.py"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            builder,
            r'["\']NUCODE_BLE["\']\s*:\s*["\']nucode\.ble\.nus["\']',
        )

    def test_kconfig_and_feature_register_bounded_ble_runtime(self) -> None:
        """! @brief BLE 구현과 고정 queue 크기가 library feature에 명시되는지 검사합니다. """

        kconfig = (REPOSITORY / "zephyr" / "Kconfig").read_text(encoding="utf-8")
        for symbol in (
            "config NUCODE_BLE_NUS",
            "config NUCODE_BLE_RX_BUFFER_SIZE",
            "config NUCODE_BLE_EVENT_QUEUE_SIZE",
        ):
            self.assertIn(symbol, kconfig, symbol)

        feature = json.loads(FEATURE.read_text(encoding="utf-8"))
        self.assertEqual(feature["conf"], ["ble-nus.conf"])
        feature_conf = (LIBRARY / "zephyr" / feature["conf"][0]).read_text(
            encoding="utf-8"
        )
        self.assertIn("CONFIG_NUCODE_BLE_NUS=y", feature_conf)

    def test_bluetooth_callbacks_are_deferred_to_poll_through_fixed_queues(self) -> None:
        """! @brief Bluetooth context에서 Sketch callback 직접 실행과 동적 queue를 차단합니다. """

        self.assertTrue(SOURCE.is_file(), SOURCE)
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "K_MSGQ_DEFINE",
            "k_msgq_put",
            "k_msgq_get",
            "bt_enable",
            "bt_nus_init",
            "bt_nus_client_init",
            "NusSerial::poll",
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

        registrations = re.findall(
            r"\.(received|sent|send_enabled|connected|disconnected)\s*=\s*&?(\w+)",
            source,
        )
        self.assertGreaterEqual(len(registrations), 4, registrations)
        self.assertIn("received", {kind for kind, _ in registrations})
        self.assertIn("connected", {kind for kind, _ in registrations})
        self.assertIn("disconnected", {kind for kind, _ in registrations})
        for kind, callback_name in registrations:
            body = function_body(source, callback_name)
            self.assertNotRegex(
                body,
                r"\b(?:event_callback|user_callback|callback)\s*\(",
                msg=f"{kind} callback이 사용자 callback을 직접 호출합니다: {callback_name}",
            )

        poll_body = function_body(source, "NusSerial::poll")
        self.assertIn("k_msgq_get", poll_body)
        self.assertRegex(
            poll_body, r"\b(?:event_callback|user_callback|callback)\s*\("
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
