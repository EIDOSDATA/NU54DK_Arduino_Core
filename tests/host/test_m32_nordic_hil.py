#!/usr/bin/env python3
"""! @brief M32-W05 Nordic extension HIL protocol과 실행 계약을 검사합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_nordic_extension_run as runner  # noqa: E402


class M32NordicHilTests(unittest.TestCase):
    """! @brief Nordic callback 분모·negative·V2 실행 경계를 고정합니다. """

    def test_parser_rejects_duplicate_and_invalid_integer(self) -> None:
        """! @brief protocol field 중복과 비정상 decimal을 거부합니다. """
        fields = runner._fields("M32NOR|1|RESULT|qos=200|survey=20")
        self.assertEqual(200, runner._integer(fields, "qos"))
        with self.assertRaisesRegex(runner.NordicExtensionFailure, "duplicate"):
            runner._fields("M32NOR|1|RESULT|qos=1|qos=2")
        with self.assertRaisesRegex(runner.NordicExtensionFailure, "invalid integer"):
            runner._integer({"qos": "-1"}, "qos")

    def test_target_fixes_denominators_negatives_and_cleanup(self) -> None:
        """! @brief target에 exact callback 분모·negative·양쪽 STOP 경계를 고정합니다. """
        source = (
            REPOSITORY / "tests/zephyr/m32_ble_nordic_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "qos_target = 200U",
            "survey_target = 20U",
            "anchor_target = 1000U",
            "event_target = 200U",
            "prepare_target = 200U",
            "invalid_llpm_rejected",
            "invalid_survey_rejected",
            "invalid_event_task_rejected",
            "duplicate_reservation_bounded",
            "disabled_callback_quiet",
            "projection_wrap_pass",
            "acl_controller_experimental",
            "|STOP|nonce=",
        ):
            self.assertIn(token, source)

    def test_runner_uses_v2_sector_flash_and_supported_test_ids(self) -> None:
        """! @brief 두 역할에 V2 sector flash를 사용하고 ACL을 PASS로 만들지 않습니다. """
        source = (HIL / "m32_nordic_extension_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertIn("flash_image_pyocd", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertNotIn("unlock", source.lower())
        self.assertIn('"M32-NORDIC-01:primary"', source)
        self.assertIn('"M32-SYNC-01:primary"', source)
        self.assertIn('"M32-EVENT-01:primary"', source)
        self.assertNotIn('"M32-ACL-01:primary"', source)

    def test_ci_build_matrix_contains_both_roles(self) -> None:
        """! @brief Zephyr manifest와 CI build matrix에 두 역할을 고정합니다. """
        testcase = (
            REPOSITORY / "tests/zephyr/m32_ble_nordic_hil/testcase.yaml"
        ).read_text(encoding="utf-8")
        ci = (REPOSITORY / "tools/ci/run_zephyr_build.py").read_text(encoding="utf-8")
        for role in ("central", "peripheral"):
            suite = f"nucode.m32.ble_nordic_hil.{role}"
            self.assertIn(suite, testcase)
            self.assertIn(suite, ci)


if __name__ == "__main__":
    unittest.main(verbosity=2)
