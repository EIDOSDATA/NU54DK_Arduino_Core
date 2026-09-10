#!/usr/bin/env python3
"""! @brief T16 Peripheral Fabric 설치 profile과 공개 진입점 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPOSITORY / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
SPECIFICATION = importlib.util.spec_from_file_location("nu54_builder_t16", BUILDER_PATH)
if SPECIFICATION is None or SPECIFICATION.loader is None:
    raise RuntimeError(f"Builder를 불러올 수 없습니다: {BUILDER_PATH}")
BUILDER = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(BUILDER)

LIBRARY = REPOSITORY / "libraries" / "NUCODE_Peripheral_Fabric"
PROFILE = REPOSITORY / "variants" / "nu54dk" / "profiles" / "fabric"


class T16PeripheralProfileTests(unittest.TestCase):
    """! @brief 수동 Kconfig 편집 없는 Fabric 설치 경로를 검증합니다. """

    def test_board_menu_loads_exact_fabric_profile(self) -> None:
        """! @brief Arduino 보드 메뉴와 builder profile ID가 일치하는지 확인합니다. """

        boards = (REPOSITORY / "boards.txt").read_text(encoding="utf-8")
        self.assertIn(
            "nu54dk.menu.feature_set.fabric=Peripheral Fabric (DAP UART disconnected)",
            boards,
        )
        self.assertIn(
            "nu54dk.menu.feature_set.fabric.build.nu54_profile=fabric", boards
        )
        profile = BUILDER.load_configuration_profile(REPOSITORY, "fabric")
        self.assertEqual(profile["features"], ["gpio", "time", "peripheral_fabric"])
        self.assertEqual(
            profile["requires_hil"],
            [
                "serial_fabric",
                "analog_fabric",
                "event_fabric",
                "stream_fabric",
                "system_fabric",
            ],
        )

    def test_feature_resolver_is_profile_scoped(self) -> None:
        """! @brief Fabric library는 fabric profile에서만 구성 fragment를 병합합니다. """

        fabric = BUILDER.load_configuration_profile(REPOSITORY, "fabric")
        resolved = BUILDER.resolve_library_features(
            REPOSITORY, fabric, ["NUCODE_Peripheral_Fabric"]
        )
        self.assertEqual([item["id"] for item in resolved], ["nucode.peripheral.fabric"])
        standard = BUILDER.load_configuration_profile(REPOSITORY, "standard")
        with self.assertRaisesRegex(BUILDER.AdapterError, "E_FEATURE_PROFILE"):
            BUILDER.resolve_library_features(
                REPOSITORY, standard, ["NUCODE_Peripheral_Fabric"]
            )

    def test_profile_separates_standard_singletons_and_dap_uart(self) -> None:
        """! @brief 직접 IRQ 소유 profile이 singleton과 DAP UART를 함께 켜지 않습니다. """

        configuration = (PROFILE / "prj.conf").read_text(encoding="utf-8")
        for symbol in (
            "SERIAL",
            "SERIAL1",
            "INTERRUPTS",
            "WIRE",
            "SPI",
            "ADC",
            "PWM",
        ):
            self.assertIn(f"CONFIG_NUCODE_ARDUINO_{symbol}=n", configuration)
        self.assertIn("CONFIG_NUCODE_ARDUINO_DAP_UART_GPIO_PINS=y", configuration)
        overlay = (PROFILE / "app.overlay").read_text(encoding="utf-8")
        self.assertIn('/delete-property/ zephyr,console;', overlay)
        self.assertEqual(overlay.count('status = "disabled";'), 3)
        self.assertEqual(overlay.count('status = "okay";'), 3)
        for pin in range(4, 8):
            self.assertIn(f"&arduino_p1_{pin:02d}", overlay)

    def test_feature_enables_verified_families_without_sketch_sidecars(self) -> None:
        """! @brief library 선택만으로 검증된 Fabric family가 활성화되는지 확인합니다. """

        feature = BUILDER.load_library_feature(REPOSITORY, "NUCODE_Peripheral_Fabric")
        self.assertIsNotNone(feature)
        self.assertEqual(feature["compatible_profiles"], ["fabric"])
        self.assertEqual(feature["conf"], ["peripheral-fabric.conf"])
        configuration = (LIBRARY / "zephyr" / "peripheral-fabric.conf").read_text(
            encoding="utf-8"
        )
        for symbol in (
            "SERIAL_FABRIC",
            "ANALOG_FABRIC",
            "EVENT_FABRIC",
            "STREAM_FABRIC",
            "SYSTEM_FABRIC",
        ):
            self.assertIn(f"CONFIG_NUCODE_ARDUINO_{symbol}=y", configuration)
        example = LIBRARY / "examples" / "FabricCapabilities" / "FabricCapabilities.ino"
        self.assertTrue(example.is_file())
        self.assertFalse((example.parent / "prj.conf").exists())
        self.assertFalse((example.parent / "app.overlay").exists())

    def test_public_facade_preserves_qdec_limitation(self) -> None:
        """! @brief QDEC를 지원으로 잘못 승격하지 않고 공개 family factory를 연결합니다. """

        header = (LIBRARY / "src" / "NUCODE_Peripheral_Fabric.h").read_text(
            encoding="utf-8"
        )
        for family in (
            "SerialFabric",
            "AnalogFabric",
            "EventFabric",
            "StreamFabric",
            "SystemFabric",
            "PeripheralInventory",
        ):
            self.assertIn(f"nucode/{family}.h", header)
        self.assertRegex(header, r"Support\s+qdec;")
        self.assertRegex(header, r"Support::unsupported,\s*Support::supported,")

    def test_support_ledger_matches_the_profile_surface(self) -> None:
        """! @brief T16 공개 family와 원장의 노출·HIL 상태가 일치하는지 확인합니다. """

        manifest = json.loads(
            (REPOSITORY / "variants" / "nu54dk" / "peripheral-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        lookup = {item["id"]: item for item in manifest["instances"]}
        serial = [item for item in manifest["instances"] if item["milestone"] == "M24"]
        self.assertEqual(len(serial), 23)
        for item in serial:
            self.assertEqual(item["route"]["state"], "verified", item["id"])
            self.assertEqual(item["states"]["exposure"], "public", item["id"])
            self.assertEqual(item["states"]["hil"], "pass", item["id"])
            self.assertIn("SerialFabric", item["public_api"], item["id"])

        for identifier in ("pdm20", "pdm21", "i2s20"):
            item = lookup[identifier]
            self.assertEqual(item["route"]["state"], "verified", identifier)
            self.assertEqual(item["states"]["exposure"], "public", identifier)
            self.assertIn("StreamFabric", item["public_api"], identifier)
        for identifier in ("qdec20", "qdec21"):
            item = lookup[identifier]
            self.assertEqual(item["states"]["exposure"], "internal", identifier)
            self.assertEqual(item["states"]["hil"], "partial", identifier)

        for identifier in ("temp", "wdt30", "wdt31"):
            item = lookup[identifier]
            self.assertEqual(item["states"]["exposure"], "public", identifier)
            self.assertEqual(item["states"]["hil"], "pass", identifier)
            self.assertIn("SystemFabric", item["public_api"], identifier)

    def test_m27_example_lock_uses_fabric_profile(self) -> None:
        """! @brief 설치 package가 새 예제를 fabric profile로 컴파일하도록 고정합니다. """

        lock = json.loads(
            (REPOSITORY / "tools" / "release" / "m27-package-examples.lock.json").read_text(
                encoding="utf-8"
            )
        )
        records = [
            item
            for item in lock["examples"]
            if item["library_directory"] == "NUCODE_Peripheral_Fabric"
        ]
        self.assertEqual(
            records,
            [
                {
                    "example": "FabricCapabilities",
                    "library": "NUCODE Peripheral Fabric",
                    "library_directory": "NUCODE_Peripheral_Fabric",
                    "profile": "fabric",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
