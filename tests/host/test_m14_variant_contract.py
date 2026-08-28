#!/usr/bin/env python3
"""! @brief M14 NU54DK Variant와 고정 DTS 단일 원본 계약을 검증합니다. """

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


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = REPOSITORY_ROOT / "tools" / "variant" / "verify_nu54dk_pinmap.py"
SPEC = importlib.util.spec_from_file_location("nu54_m14_variant", VERIFIER_PATH)
assert SPEC and SPEC.loader
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class M14VariantContractTests(unittest.TestCase):
    def test_fixed_board_dts_maps_eight_aliases_and_generates_seven_descriptors(self) -> None:
        board_root = REPOSITORY_ROOT / "board_package" / "NU54DK_Zephyr_DTS"
        evidence = VERIFIER.verify_pinmap(REPOSITORY_ROOT, board_root)

        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["digital_pin_count"], 7)
        self.assertEqual(evidence["mapped_pin_count"], 8)
        self.assertEqual(evidence["digital_pin_id_limit"], 10)
        self.assertEqual(evidence["pin_role_span"], 10)
        self.assertEqual(evidence["reserved_non_digital_ids"], [2, 3, 4])
        self.assertEqual(
            [(pin["logical_name"], pin["logical_id"], pin["dts_alias"])
             for pin in evidence["pins"]],
            [
                ("LED_BUILTIN", 0, "led0"),
                ("PIN_BUTTON0", 1, "sw0"),
                ("PIN_LED2", 5, "led2"),
                ("PIN_LED3", 6, "led3"),
                ("PIN_BUTTON1", 7, "sw1"),
                ("PIN_BUTTON2", 8, "sw2"),
                ("PIN_BUTTON3", 9, "sw3"),
            ],
        )
        self.assertEqual(
            [(pin["logical_name"], pin["logical_id"], pin["dts_alias"], pin["owner"])
             for pin in evidence["reserved_pins"]],
            [("PIN_LED1", 4, "led1", "PIN_PWM0")],
        )
        physical = {
            (pin["gpio_controller"], pin["gpio_pin"])
            for pin in [*evidence["pins"], *evidence["reserved_pins"]]
        }
        self.assertEqual(len(physical), 8)

    def test_verifier_writes_machine_readable_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nu54-m14-variant-") as temporary:
            output = Path(temporary) / "variant-evidence.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(VERIFIER.main(["--output", str(output)]), 0)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["gate"], "m14-nu54dk-variant-contract")
            self.assertEqual(len(evidence["pins"]), evidence["digital_pin_count"])

    def test_duplicate_dts_alias_target_is_rejected(self) -> None:
        source = (
            REPOSITORY_ROOT
            / "board_package"
            / "NU54DK_Zephyr_DTS"
            / "boards"
            / "nucode"
            / "nu54dk"
            / "nu54dk_common.dtsi"
        ).read_text(encoding="utf-8")
        tampered = source.replace("sw3 = &button3;", "sw3 = &button2;")
        self.assertNotEqual(source, tampered)

        with tempfile.TemporaryDirectory(prefix="nu54-m14-dts-negative-") as temporary:
            board_root = Path(temporary)
            common = board_root / "boards" / "nucode" / "nu54dk" / "nu54dk_common.dtsi"
            common.parent.mkdir(parents=True)
            common.write_text(tampered, encoding="utf-8")
            with self.assertRaisesRegex(
                VERIFIER.PinMapContractError,
                "둘 이상의 digital 논리 pin이 같은 GPIO",
            ):
                VERIFIER.verify_pinmap(REPOSITORY_ROOT, board_root)

    def test_public_constants_compile_without_changing_v01_pin_values(self) -> None:
        cxx = self._find_compiler(("g++", "clang++", "c++"))
        language_probe = subprocess.run(
            [cxx, "-std=c++17", "-x", "c++", "-fsyntax-only", "-"],
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
static_assert(NUM_DIGITAL_PINS == 10U);
static_assert(NUM_DIGITAL_CAPABLE_PINS == 7U);
static_assert(NUM_PIN_ROLES == 10U);
static_assert(D0 == LED_BUILTIN && D1 == PIN_BUTTON0);
static_assert(digitalPinToInterrupt(PIN_A0) == NOT_AN_INTERRUPT);
static_assert(digitalPinToInterrupt(PIN_PWM0) == NOT_AN_INTERRUPT);
static_assert(digitalPinToInterrupt(PIN_LED1) == NOT_AN_INTERRUPT);
static_assert(digitalPinToInterrupt(PIN_LED3) == PIN_LED3);
int main() { return 0; }
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    cxx,
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
    def _find_compiler(candidates: tuple[str, ...]) -> str:
        for candidate in candidates:
            compiler = shutil.which(candidate)
            if compiler:
                return compiler
        raise AssertionError("M14 Variant header 계약 시험용 C++ compiler가 없습니다.")


if __name__ == "__main__":
    unittest.main()
