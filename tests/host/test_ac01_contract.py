#!/usr/bin/env python3
"""! @brief AC-01 connector GPIO와 Core API source 계약을 검증합니다. """

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class AC01ContractTests(unittest.TestCase):
    """! @brief hardware 없이 고정할 수 있는 AC-01 계약을 검사합니다. """

    def test_connector_dtsi_uses_only_approved_free_gpio_pair(self) -> None:
        connector = (
            REPOSITORY_ROOT / "dts" / "nucode" / "nu54dk-arduino-connectors.dtsi"
        ).read_text(encoding="utf-8")
        mappings = re.findall(
            r"(?P<label>connector_gpio[01]):.*?gpios\s*=\s*"
            r"<&(?P<controller>gpio\d+)\s+(?P<pin>\d+)\s+GPIO_ACTIVE_HIGH>",
            connector,
            re.DOTALL,
        )
        self.assertEqual(
            mappings,
            [("connector_gpio0", "gpio2", "5"), ("connector_gpio1", "gpio2", "6")],
        )
        self.assertIn("nucode-gpio0 = &connector_gpio0;", connector)
        self.assertIn("nucode-gpio1 = &connector_gpio1;", connector)
        self.assertIn('compatible = "nucode,arduino-connector-gpios";', connector)

        binding = (
            REPOSITORY_ROOT
            / "dts"
            / "bindings"
            / "misc"
            / "nucode,arduino-connector-gpios.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn('compatible: "nucode,arduino-connector-gpios"', binding)
        self.assertRegex(
            binding,
            re.compile(r"child-binding:.*?gpios:.*?type: phandle-array", re.DOTALL),
        )

        pinctrl = (
            REPOSITORY_ROOT
            / "board_package"
            / "NU54DK_Zephyr_DTS"
            / "boards"
            / "nucode"
            / "nu54dk"
            / "nu54dk-pinctrl.dtsi"
        ).read_text(encoding="utf-8")
        peripheral_pins = {
            (int(port), int(pin))
            for port, pin in re.findall(
                r"NRF_PSEL\([^,]+,\s*(\d+),\s*(\d+)\)", pinctrl
            )
        }
        self.assertNotIn((2, 5), peripheral_pins)
        self.assertNotIn((2, 6), peripheral_pins)

    def test_standard_and_ble_profiles_share_one_connector_definition(self) -> None:
        include = "#include <nucode/nu54dk-arduino-connectors.dtsi>"
        for profile in ("standard", "ble"):
            overlay = (
                REPOSITORY_ROOT
                / "variants"
                / "nu54dk"
                / "profiles"
                / profile
                / "app.overlay"
            ).read_text(encoding="utf-8")
            self.assertEqual(overlay.count(include), 1, msg=profile)

    def test_variant_exposes_connector_capability_and_ownership(self) -> None:
        header = (REPOSITORY_ROOT / "variants" / "nu54dk" / "variant.h").read_text(
            encoding="utf-8"
        )
        pin_list = (
            REPOSITORY_ROOT / "variants" / "nu54dk" / "digital_pins.inc"
        ).read_text(encoding="utf-8")
        source = (
            REPOSITORY_ROOT / "variants" / "nu54dk" / "variant.cpp"
        ).read_text(encoding="utf-8")
        self.assertRegex(header, r"#define\s+PIN_GPIO0\s+10U")
        self.assertRegex(header, r"#define\s+PIN_GPIO1\s+11U")
        self.assertIn(
            "NUCODE_NU54DK_DIGITAL_PIN(PIN_GPIO0, nucode_gpio0, connector)",
            pin_list,
        )
        self.assertIn(
            "NUCODE_NU54DK_DIGITAL_PIN(PIN_GPIO1, nucode_gpio1, connector)",
            pin_list,
        )
        self.assertIn("PinCapability::open_drain", source)
        self.assertIn("PinOwnership::connector_gpio", source)
        connector_capabilities = re.search(
            r"constexpr PinCapability connector_capabilities\s*=\s*(.*?);",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(connector_capabilities)
        self.assertNotIn("PinCapability::interrupt", connector_capabilities.group(1))
        self.assertIn("connector_without_gpiote", header)

    def test_safe_interrupt_and_timing_apis_have_real_backends(self) -> None:
        arduino = (REPOSITORY_ROOT / "cores" / "arduino" / "Arduino.h").read_text(
            encoding="utf-8"
        )
        interrupts = (
            REPOSITORY_ROOT / "cores" / "arduino" / "wiring_interrupt.cpp"
        ).read_text(encoding="utf-8")
        pulse_shift = (
            REPOSITORY_ROOT / "cores" / "arduino" / "wiring_pulse_shift.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("void noInterrupts(void);", arduino)
        self.assertIn("void interrupts(void);", arduino)
        self.assertIn("GPIO_INT_LEVEL_LOW", interrupts)
        self.assertIn("GPIO_INT_LEVEL_HIGH", interrupts)
        self.assertIn("callback_mask_depth", interrupts)
        self.assertIn("retriggerAssertedLevel", interrupts)
        self.assertIn("suppress_asserted_level", interrupts)
        self.assertRegex(
            interrupts,
            re.compile(
                r"if \(suppress_asserted_level\).*?GPIO_INT_DISABLE.*?return;",
                re.DOTALL,
            ),
        )
        self.assertNotIn("irq_lock(", interrupts)
        self.assertNotIn("irq_disable(", interrupts)
        self.assertIn('extern "C" unsigned long pulseIn(', pulse_shift)
        self.assertIn('extern "C" unsigned long pulseInLong(', pulse_shift)
        self.assertIn('extern "C" void shiftOut(', pulse_shift)
        self.assertIn('extern "C" std::uint8_t shiftIn(', pulse_shift)
        self.assertIn("k_cycle_get_64()", pulse_shift)


if __name__ == "__main__":
    unittest.main()
