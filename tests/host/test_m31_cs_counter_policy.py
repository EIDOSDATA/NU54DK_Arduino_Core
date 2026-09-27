"""! @brief M31 CS counter 관찰 정책의 fail-closed 경계를 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tests/hil/nu54dk/m31_cs_ras_pair_run.py"
SPEC = importlib.util.spec_from_file_location("m31_cs_ras_pair_run_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC.loader.exec_module(MODULE)


class M31CsCounterPolicyTests(unittest.TestCase):
    """! @brief 순방향 gap과 무결성 오류를 서로 다른 판정으로 유지합니다. """

    def test_forward_gap_is_observed(self) -> None:
        """! @brief 순방향 누락은 관찰 목록에 남기고 실패시키지 않습니다. """
        gaps = []

        MODULE.record_counter_transition(58, 60, gaps)

        self.assertEqual(gaps, [{"before": 58, "after": 60}])

    def test_duplicate_counter_is_rejected(self) -> None:
        """! @brief 같은 counter의 중복 수신은 오류로 거부합니다. """
        with self.assertRaisesRegex(RuntimeError, "duplicate or backward"):
            MODULE.record_counter_transition(60, 60, [])

    def test_backward_counter_is_rejected(self) -> None:
        """! @brief 역행 counter는 오류로 거부합니다. """
        with self.assertRaisesRegex(RuntimeError, "duplicate or backward"):
            MODULE.record_counter_transition(60, 59, [])

    def test_wraparound_is_forward_progress(self) -> None:
        """! @brief 16-bit wraparound의 연속 증가는 정상 진행으로 처리합니다. """
        gaps = []

        MODULE.record_counter_transition(0xFFFF, 0, gaps)

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
