#!/usr/bin/env python3
"""! @brief M14 NU54DK Core-owned 31핀 Variant 계약을 검증합니다. """

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from host_compiler import compiler_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = REPOSITORY_ROOT / "tools" / "variant" / "verify_nu54dk_pinmap.py"
SPEC = importlib.util.spec_from_file_location("nu54_m14_variant", VERIFIER_PATH)
assert SPEC and SPEC.loader
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class M14VariantContractTests(unittest.TestCase):
    ## @brief Zephyr C min/max가 Arduino C macro보다 먼저 확정되도록 include 순서를 고정합니다.
    def test_zephyr_c_header_avoids_min_max_macro_redefinition(self) -> None:
        variant = (
            REPOSITORY_ROOT / "variants" / "nu54dk" / "variant.h"
        ).read_text(encoding="utf-8")
        arduino = (
            REPOSITORY_ROOT / "cores" / "arduino" / "Arduino.h"
        ).read_text(encoding="utf-8")
        self.assertLess(
            variant.index("#include <zephyr/devicetree.h>"),
            variant.index("#include <api/Common.h>"),
        )
        self.assertLess(
            arduino.index("#include <variant.h>"),
            arduino.index("#include <api/ArduinoAPI.h>"),
        )

    def test_core_dts_maps_all_31_pads_with_legacy_alias_compatibility(self) -> None:
        evidence = VERIFIER.verify_pinmap(
            REPOSITORY_ROOT,
            REPOSITORY_ROOT / "board_package" / "NU54DK_Zephyr_DTS",
        )

        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["schema_version"], 2)
        self.assertEqual(evidence["physical_pin_count"], 31)
        self.assertEqual(evidence["mapped_pin_count"], 31)
        self.assertEqual(evidence["digital_pin_id_limit"], 32)
        self.assertEqual(evidence["pin_role_span"], 32)
        self.assertEqual(evidence["digital_capable_default"], 20)
        self.assertEqual(evidence["conditional_gpio_pin_count"], 6)
        self.assertEqual(evidence["analog_input_count"], 8)
        self.assertEqual(
            evidence["legacy_aliases"],
            [{
                "logical_name": "PIN_LED1",
                "logical_id": 4,
                "canonical_name": "PIN_PWM0",
                "canonical_id": 3,
            }],
        )
        self.assertEqual(len(evidence["pins"]), 31)
        self.assertEqual(
            {pin["logical_id"] for pin in evidence["pins"]},
            set(range(32)) - {4},
        )
        physical = {
            (pin["gpio_controller"], pin["gpio_pin"])
            for pin in evidence["pins"]
        }
        self.assertEqual(
            physical,
            {
                *(("gpio0", pin) for pin in range(5)),
                *(("gpio1", pin) for pin in range(15)),
                *(("gpio2", pin) for pin in range(11)),
            },
        )

    def test_route_matrix_and_fail_closed_policies_are_visible_in_evidence(self) -> None:
        evidence = VERIFIER.verify_pinmap(REPOSITORY_ROOT, Path("unused"))
        pins = {
            (pin["gpio_controller"], pin["gpio_pin"]): pin
            for pin in evidence["pins"]
        }
        for pin in range(5):
            self.assertIn("uart30", pins[("gpio0", pin)]["routes"])
        for pin in range(15):
            self.assertIn("i2c22", pins[("gpio1", pin)]["routes"])
            self.assertIn("pwm20", pins[("gpio1", pin)]["routes"])
            self.assertIn("pwm21", pins[("gpio1", pin)]["routes"])
            self.assertIn("pwm22", pins[("gpio1", pin)]["routes"])
        spi_pads = {
            physical for physical, pin in pins.items() if "spi00" in pin["routes"]
        }
        self.assertEqual(spi_pads, {("gpio2", 1), ("gpio2", 2), ("gpio2", 4)})
        for pin in range(11):
            self.assertNotIn("interrupt", pins[("gpio2", pin)]["capabilities"])
        for pin in pins.values():
            if pin["policy"] in {"input-only", "system-reserved"}:
                self.assertNotIn("digital-output", pin["capabilities"])

        a0 = pins[("gpio1", 12)]
        self.assertEqual(a0["policy"], "transferable")
        self.assertEqual(a0["ownership"], "adc")
        self.assertTrue(
            {"digital-input", "digital-output", "interrupt", "open-drain", "analog-input", "pwm-output"}
            <= set(a0["capabilities"])
        )
        self.assertTrue({"adc", "pwm20"} <= set(a0["routes"]))

    def test_verifier_writes_machine_readable_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nu54-m14-variant-") as temporary:
            output = Path(temporary) / "variant-evidence.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(VERIFIER.main(["--output", str(output)]), 0)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["gate"], "m14-nu54dk-variant-contract")
            self.assertEqual(len(evidence["pins"]), evidence["physical_pin_count"])

    def test_duplicate_physical_pad_in_core_dts_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nu54-m14-dts-negative-") as temporary:
            temporary_root = Path(temporary) / "repository"
            self._copy_verifier_inputs(temporary_root)
            dts_path = temporary_root / "dts" / "nucode" / "nu54dk-arduino-pins.dtsi"
            source = dts_path.read_text(encoding="utf-8")
            tampered = source.replace(
                "gpios = <&gpio2 10 GPIO_ACTIVE_HIGH>;",
                "gpios = <&gpio2 9 GPIO_ACTIVE_HIGH>;",
            )
            self.assertNotEqual(source, tampered)
            dts_path.write_text(tampered, encoding="utf-8")
            with self.assertRaisesRegex(VERIFIER.PinMapContractError, "31개 pad 집합"):
                VERIFIER.verify_pinmap(temporary_root, Path("unused"))

    def test_public_constants_compile_without_changing_legacy_values(self) -> None:
        cxx = compiler_command()
        language_probe = subprocess.run(
            [*cxx, "-std=c++17", "-x", "c++", "-fsyntax-only", "-"],
            input="inline constexpr int value = 1;\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if language_probe.returncode != 0:
            self.skipTest("설치된 host compiler가 C++17 inline variable을 지원하지 않습니다.")
        with tempfile.TemporaryDirectory(prefix="nu54-m14-variant-cxx-") as temporary:
            source = Path(temporary) / "variant_contract.cpp"
            source.write_text(
                """
#include <variant.h>
static_assert(LED_BUILTIN == 0U);
static_assert(PIN_BUTTON0 == 1U);
static_assert(PIN_A0 == 2U);
static_assert(PIN_PWM0 == 3U);
static_assert(PIN_LED1 == 4U && PIN_BUTTON3 == 9U);
static_assert(PIN_GPIO0 == 10U && PIN_GPIO1 == 11U);
static_assert(NUM_DIGITAL_PINS == 32U);
static_assert(NUM_DIGITAL_CAPABLE_PINS == 20U);
static_assert(NUM_PIN_ROLES == 32U);
static_assert(NUM_PHYSICAL_PINS == 31U);
static_assert(NUM_ANALOG_INPUTS == 8U);
static_assert(PIN_AIN0 == PIN_P1_04 && PIN_AIN7 == PIN_LED3);
static_assert(A0 == PIN_A0 && A1 == PIN_AIN0 && A7 == PIN_AIN7);
static_assert(canonicalDigitalPin(PIN_LED1) == PIN_PWM0);
static_assert(digitalPinToInterrupt(PIN_A0) == PIN_A0);
static_assert(digitalPinToInterrupt(PIN_PWM0) == PIN_PWM0);
static_assert(digitalPinToInterrupt(PIN_LED1) == PIN_PWM0);
static_assert(digitalPinToInterrupt(LED_BUILTIN) == NOT_AN_INTERRUPT);
static_assert(digitalPinToInterrupt(PIN_GPIO0) == NOT_AN_INTERRUPT);
int main() { return 0; }
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    *cxx,
                    "-std=c++17",
                    "-fsyntax-only",
                    f"-I{REPOSITORY_ROOT / 'variants' / 'nu54dk'}",
                    f"-I{REPOSITORY_ROOT / 'third_party' / 'ArduinoCore-API'}",
                    str(source),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"Variant C++ contract failed:\n{result.stdout}\n{result.stderr}",
            )

    @staticmethod
    def _copy_verifier_inputs(destination: Path) -> None:
        relative_paths = (
            Path("variants/nu54dk/digital_pins.inc"),
            Path("variants/nu54dk/variant.h"),
            Path("variants/nu54dk/variant.cpp"),
            Path("dts/nucode/nu54dk-arduino-pin-metadata.h"),
            Path("dts/nucode/nu54dk-arduino-pins.dtsi"),
        )
        for relative in relative_paths:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY_ROOT / relative, target)



if __name__ == "__main__":
    unittest.main()
