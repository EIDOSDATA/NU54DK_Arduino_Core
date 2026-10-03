#!/usr/bin/env python3
"""! @brief M32-W04 EAD HIL protocol과 exact 실행 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_ead_run as runner  # noqa: E402


class M32EadHilTests(unittest.TestCase):
    """! @brief EAD 분모·음수 경로·보드 안전 조건을 고정합니다. """

    def test_record_parser_rejects_duplicate_and_invalid_integer(self) -> None:
        """! @brief protocol field의 중복과 decimal 외 입력을 거부합니다. """
        fields = runner._fields(
            "M32EAD|1|RESULT|role=scanner|raw=400|authenticated=20"
        )
        self.assertEqual("scanner", fields["role"])
        self.assertEqual(400, runner._integer(fields, "raw"))
        with self.assertRaisesRegex(runner.EadExecutionFailure, "duplicate"):
            runner._fields("M32EAD|1|RESULT|raw=400|raw=401")
        with self.assertRaisesRegex(runner.EadExecutionFailure, "invalid integer"):
            runner._integer({"raw": "-1"}, "raw")

    def test_hil_source_covers_positive_negative_and_bounded_stop(self) -> None:
        """! @brief target가 20회 인증과 네 음수 경로 및 STOP을 모두 노출합니다. """
        source = (
            REPOSITORY / "tests" / "zephyr" / "m32_ble_ead_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "iteration_target = 20U",
            "report_target = 400U",
            "replay_rejected",
            "tamper_rejected",
            "wrong_key_rejected",
            "wrong_iv_rejected",
            "M32EAD|1|STOP|nonce=",
            "BLEScan.startExtended(false, false, false)",
        ):
            self.assertIn(token, source)
        self.assertNotIn("if (finished)\n            return;", source)

    def test_exact_runner_uses_v2_sector_flash_and_register_identity(self) -> None:
        """! @brief 두 역할 모두 CMSIS-DAP v2와 DP/AP identity를 통과해야 합니다. """
        source = (HIL / "m32_ead_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertIn('"M32-EAD-01:primary"', source)
        self.assertIn("ALLOWED_LOSS = 4", source)
        self.assertNotIn("--erase chip", source)
        self.assertNotIn("unlock", source.lower())

    def test_native_group_builds_both_roles(self) -> None:
        """! @brief v0.6.0 native 회귀에서 advertiser와 scanner image를 함께 빌드합니다. """
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.ble_ead_hil.advertiser",
            "nucode.m32.ble_ead_hil.scanner",
        ):
            self.assertIn(suite, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
