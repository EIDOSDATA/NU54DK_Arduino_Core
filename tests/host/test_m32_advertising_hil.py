#!/usr/bin/env python3
"""! @brief M32-W04 multi-set HIL protocol과 exact 실행 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_advertising_run as runner  # noqa: E402


class M32AdvertisingHilTests(unittest.TestCase):
    """! @brief 6-set 분모·음수 경로·보드 안전 조건을 고정합니다. """

    def test_record_parser_rejects_duplicate_and_invalid_integer(self) -> None:
        """! @brief protocol field의 중복과 decimal 외 입력을 거부합니다. """
        fields = runner._fields("M32ADV|1|RESULT|role=scanner|raw=600|unique=120")
        self.assertEqual("scanner", fields["role"])
        self.assertEqual(600, runner._integer(fields, "raw"))
        with self.assertRaisesRegex(runner.AdvertisingExecutionFailure, "duplicate"):
            runner._fields("M32ADV|1|RESULT|raw=600|raw=601")
        with self.assertRaisesRegex(runner.AdvertisingExecutionFailure, "invalid integer"):
            runner._integer({"raw": "-1"}, "raw")

    def test_hil_source_covers_sets_sid_negative_and_bounded_stop(self) -> None:
        """! @brief target가 6 set·120 unique와 세 음수 경로 및 STOP을 노출합니다. """
        source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_ble_advertising_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "iteration_target = 20U",
            "packet_target = 600U",
            "unique_target = 120U",
            "over_capacity_rejected",
            "stale_set_rejected",
            "scan_initiate_conflict_rejected",
            "M32ADV|1|STOP|nonce=",
            "BLEScan.startExtended(false, false, false)",
        ):
            self.assertIn(token, source)

    def test_exact_runner_uses_v2_sector_flash_and_register_identity(self) -> None:
        """! @brief 세 역할 모두 CMSIS-DAP v2와 DP/AP identity를 통과해야 합니다. """
        source = (HIL / "m32_advertising_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertIn('"M32-ADV-01:primary"', source)
        self.assertIn("ALLOWED_LOSS = 6", source)
        self.assertNotIn("--erase chip", source)
        self.assertNotIn("unlock", source.lower())

    def test_native_group_builds_all_roles(self) -> None:
        """! @brief v0.6.0 native 회귀에서 세 역할 image를 함께 빌드합니다. """
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.ble_advertising_hil.advertiser_a",
            "nucode.m32.ble_advertising_hil.advertiser_b",
            "nucode.m32.ble_advertising_hil.scanner",
        ):
            self.assertIn(suite, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
