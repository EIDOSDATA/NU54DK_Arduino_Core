#!/usr/bin/env python3
"""! @brief M32-W04 identity/privacy HIL protocol과 exact 실행 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_privacy_run as runner  # noqa: E402


class M32PrivacyHilTests(unittest.TestCase):
    """! @brief identity/list 재연결 분모와 세 음수 경로를 고정합니다. """

    def test_record_parser_rejects_duplicate_invalid_integer_and_address(self) -> None:
        """! @brief protocol field 중복·decimal·address 형식 오류를 거부합니다. """
        fields = runner._fields("M32PRIV|1|READY|address=AA:BB:CC:DD:EE:FF|type=1")
        self.assertEqual(("AA:BB:CC:DD:EE:FF", 1), runner._address(fields))
        with self.assertRaisesRegex(runner.PrivacyExecutionFailure, "duplicate"):
            runner._fields("M32PRIV|1|RESULT|packets=200|packets=201")
        with self.assertRaisesRegex(runner.PrivacyExecutionFailure, "invalid integer"):
            runner._integer({"packets": "-1"}, "packets")
        with self.assertRaisesRegex(runner.PrivacyExecutionFailure, "invalid READY"):
            runner._address({"address": "bad", "type": "1"})

    def test_hil_source_covers_identity_list_negative_and_bounded_stop(self) -> None:
        """! @brief target가 20×2 재연결·200 packet·세 음수 경로·STOP을 노출합니다. """
        application = REPOSITORY / "tests" / "zephyr" / "m32_ble_privacy_hil"
        source = (application / "src" / "main.cpp").read_text(encoding="utf-8")
        for token in (
            "iteration_target = 20U",
            "packet_target = 200U",
            "wrong_identity_rejected",
            "unauthorized_peer_rejected",
            "active_list_change_rejected",
            "BLEAdvertisingLists.addFilterAccept",
            "filter_connections = true",
            "M32PRIV|1|STOP|nonce=",
        ):
            self.assertIn(token, source)

        sysbuild = (application / "sysbuild.cmake").read_text(encoding="utf-8")
        self.assertIn('M32_PRIV_ROLE}" STREQUAL "peer"', sysbuild)
        self.assertIn("CONFIG_BT_PRIVACY n", sysbuild)
        self.assertIn("CONFIG_BT_RPA_TIMEOUT_DYNAMIC n", sysbuild)
        self.assertIn("CONFIG_BT_SCAN_WITH_IDENTITY y", sysbuild)

    def test_exact_runner_uses_v2_sector_flash_and_register_identity(self) -> None:
        """! @brief 세 역할 모두 CMSIS-DAP v2와 DP/AP identity를 통과해야 합니다. """
        source = (HIL / "m32_privacy_run.py").read_text(encoding="utf-8")
        self.assertIn("collect_register_identity", source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertIn('"M32-PRIV-01:primary"', source)
        self.assertIn("LATENCY_LIMIT_MS = 1000", source)
        self.assertNotIn("--erase chip", source)
        self.assertNotIn("unlock", source.lower())

    def test_native_group_builds_all_roles(self) -> None:
        """! @brief v0.6.0 native 회귀에서 세 역할 image를 함께 빌드합니다. """
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.ble_privacy_hil.identity_a",
            "nucode.m32.ble_privacy_hil.identity_b",
            "nucode.m32.ble_privacy_hil.peer",
        ):
            self.assertIn(suite, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
