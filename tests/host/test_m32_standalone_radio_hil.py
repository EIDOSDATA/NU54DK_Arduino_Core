#!/usr/bin/env python3
"""! @brief M32-W09 단독 radio HIL protocol과 exact 실행 계약을 검사합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_standalone_radio_run as runner  # noqa: E402


class M32StandaloneRadioHilTests(unittest.TestCase):
    """! @brief 802.15.4·ESB packet 분모와 negative·STOP을 고정합니다. """

    def test_parser_rejects_duplicate_and_invalid_integer(self) -> None:
        """! @brief protocol field 중복과 비정상 decimal을 거부합니다. """
        fields = runner._fields("M32ESB|1|RESULT|requested=2000|acked=1999")
        self.assertEqual(2000, runner._integer(fields, "requested"))
        with self.assertRaisesRegex(runner.StandaloneRadioFailure, "duplicate"):
            runner._fields("M32ESB|1|RESULT|requested=1|requested=2")
        with self.assertRaisesRegex(runner.StandaloneRadioFailure, "invalid integer"):
            runner._integer({"requested": "-1"}, "requested")

    def test_target_sources_fix_packet_negative_and_stop_contract(self) -> None:
        """! @brief 두 target가 20×100 packet·구성/길이 음수·STOP을 포함합니다. """
        for application, negative in (
            ("m32_radio154_hil", "invalid_channel_rejected"),
            ("m32_esb_hil", "invalid_rate_rejected"),
        ):
            source = (
                REPOSITORY / "tests" / "zephyr" / application / "src" / "main.cpp"
            ).read_text(encoding="utf-8")
            for token in (
                "iteration_target = 20U",
                "packets_per_iteration = 100U",
                "invalid_length_rejected",
                negative,
                "|STOP|nonce=",
            ):
                self.assertIn(token, source)

    def test_runner_uses_v2_sector_flash_and_both_test_ids(self) -> None:
        """! @brief 네 역할 모두 CMSIS-DAP v2 sector flash와 DP/AP 대조를 사용합니다. """
        source = (HIL / "m32_standalone_radio_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertIn("flash_image_pyocd", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertNotIn("unlock", source.lower())
        self.assertIn('"M32-154-01:primary"', source)
        self.assertIn('"M32-ESB-01:primary"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
