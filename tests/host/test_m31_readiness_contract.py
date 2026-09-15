"""! @brief M31 분모와 외장·Host 후속 gate의 부당 승격을 검사합니다. """

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/bluetooth/m31_contract.py"
SPEC = importlib.util.spec_from_file_location("m31_contract_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M31ReadinessTests(unittest.TestCase):
    """! @brief 작업 8·family 10·Audio 11과 미실행 후속 범위를 검사합니다. """

    def test_initial_denominators_and_statuses_are_not_pass(self) -> None:
        """! @brief 계획 문서에서 새 실기 PASS를 만들지 않습니다. """
        doc = MODULE.contract()
        self.assertEqual(doc["counts"]["work_total"], 8)
        self.assertEqual(doc["counts"]["test_family_total"], 10)
        self.assertEqual(doc["counts"]["audio_group_total"], 11)
        self.assertEqual(doc["counts"]["work_completed"], 0)
        self.assertTrue(all(entry["status"] == "NOT_RUN" for family in doc["test_families"]
                            for entry in family["cases"]))

    def test_audio_pass_requires_functional_case(self) -> None:
        """! @brief Audio group만 PASS로 바꾸는 입력을 거부합니다. """
        doc = MODULE.contract()
        doc["audio_groups"][0]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "audio group PASS"):
            MODULE.validate(doc)

    def test_external_physical_not_run_cannot_become_blocker_or_fake_pass(self) -> None:
        """! @brief 외장 I/O 실물의 비차단 상태와 증거 경계를 유지합니다. """
        doc = MODULE.contract()
        doc["follow_up_cases"][0]["release_blocker"] = True
        with self.assertRaisesRegex(ValueError, "follow-up release blocker"):
            MODULE.validate(doc)
        doc = MODULE.contract()
        doc["follow_up_cases"][0]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "PASS without physical"):
            MODULE.validate(doc)

    def test_final_ubuntu_gate_cannot_be_removed(self) -> None:
        """! @brief 사용자 최종 실물 Host gate를 문서 변경으로 면제하지 않습니다. """
        doc = MODULE.contract()
        doc["follow_up_cases"][2]["release_blocker"] = False
        with self.assertRaisesRegex(ValueError, "final Host physical gate"):
            MODULE.validate(doc)

    def test_completed_work_count_requires_exact_denominator(self) -> None:
        """! @brief 작업 상태와 분자를 함께 갱신해야 완료로 인정합니다. """
        doc = MODULE.contract()
        doc["work_packages"][0]["status"] = "completed"
        with self.assertRaisesRegex(ValueError, "work denominator"):
            MODULE.validate(doc)


if __name__ == "__main__":
    unittest.main()
