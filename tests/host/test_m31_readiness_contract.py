"""! @brief M31 분모와 외장·Host 후속 gate의 부당 승격을 검사합니다. """

from __future__ import annotations

import copy
import importlib.util
import json
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

    def test_related_public_example_must_exist(self) -> None:
        """! @brief 완료된 역할에 기록한 추가 Arduino 예제의 실재를 검사합니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        client = next(role for role in doc["example_roles"] if role["id"] == "W03-02:client")
        client["related_sketches"] = ["libraries/NUCODE_BLE_Audio/examples/Missing/Missing.ino"]
        with self.assertRaisesRegex(ValueError, "related Arduino sketch path invalid"):
            MODULE.validate(doc)

    def test_w02_wire_hil_cannot_close_thin_public_examples(self) -> None:
        """! @brief 무선 시험 PASS만으로 데이터 경로가 없는 ISO 예제를 완료 처리하지 않습니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        package = next(item for item in doc["work_packages"] if item["id"] == "M31-W02")
        package["status"] = "completed"
        package["public_example_status"] = "rework_required"
        doc["counts"]["work_completed"] = sum(
            item["status"] == "completed" for item in doc["work_packages"]
        )
        with self.assertRaisesRegex(ValueError, "W02 public ISO example flow incomplete"):
            MODULE.validate(doc)

    def test_w04_completion_requires_product_support_boundary(self) -> None:
        """! @brief W04 완료 뒤 제품 SDC IQ RX를 임의 PASS로 승격하지 않습니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        raw_iq = next(entry for entry in doc["capabilities"] if entry["id"] == "raw_iq_rx")
        raw_iq["target_applicability"] = "product_sdc_raw_iq_rx"
        with self.assertRaisesRegex(ValueError, "W04 product SDC unsupported boundary mismatch"):
            MODULE.validate(doc)

    def test_w04_completion_requires_both_public_tx_examples(self) -> None:
        """! @brief W04 완료에는 CTE beacon과 연결 응답 예제의 실기 PASS가 모두 필요합니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        responder = next(entry for entry in doc["example_roles"]
                         if entry["id"] == "cte_peripheral")
        responder["runtime_status"] = "FAIL"
        with self.assertRaisesRegex(ValueError, "W04 public TX example incomplete"):
            MODULE.validate(doc)

    def test_w05_completion_requires_stale_key_negative(self) -> None:
        """! @brief W05 완료 뒤 one-sided stale-key 수용 0 근거를 제거할 수 없습니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        package = next(item for item in doc["work_packages"] if item["id"] == "M31-W05")
        audit_path = ROOT / package["exact_evidence"]
        original = json.loads(audit_path.read_text(encoding="utf-8"))
        changed = copy.deepcopy(original)
        changed["negative"]["one_sided_stale_key"]["authenticated_ras_accepts"] = 1
        package["exact_evidence"] = "00_Docs/04_검증 기록/evidence/m31-w05-close-20260925/test-invalid-audit.json"
        invalid = ROOT / package["exact_evidence"]
        try:
            invalid.write_text(
                json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "W05 security negative evidence incomplete"
            ):
                MODULE.validate(doc)
        finally:
            invalid.unlink(missing_ok=True)

    def test_w05_completion_requires_public_ras_pair(self) -> None:
        """! @brief W05 완료에는 두 공개 RAS 역할의 build/runtime PASS가 모두 필요합니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        reflector = next(entry for entry in doc["example_roles"]
                         if entry["id"] == "cs_reflector")
        reflector["runtime_status"] = "FAIL"
        with self.assertRaisesRegex(ValueError, "W05 public RAS example incomplete"):
            MODULE.validate(doc)

    def test_w06_completion_requires_zero_resource_leaks(self) -> None:
        """! @brief W06 완료 뒤 자원 누수 0 판정을 제거할 수 없습니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        package = next(item for item in doc["work_packages"] if item["id"] == "M31-W06")
        audit_path = ROOT / package["exact_evidence"]
        original = json.loads(audit_path.read_text(encoding="utf-8"))
        changed = copy.deepcopy(original)
        changed["resource_lifecycle"]["resource_leaks"] = 1
        package["exact_evidence"] = (
            "00_Docs/04_검증 기록/evidence/m31-w06-close-20260926/"
            "test-invalid-resource-audit.json"
        )
        invalid = ROOT / package["exact_evidence"]
        try:
            invalid.write_text(
                json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "W06 resource lifecycle evidence incomplete"):
                MODULE.validate(doc)
        finally:
            invalid.unlink(missing_ok=True)

    def test_w06_completion_requires_all_m19_m30_families(self) -> None:
        """! @brief M19~M30 회귀 분모 12를 축소한 W06 완료를 거부합니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        package = next(item for item in doc["work_packages"] if item["id"] == "M31-W06")
        audit_path = ROOT / package["exact_evidence"]
        original = json.loads(audit_path.read_text(encoding="utf-8"))
        changed = copy.deepcopy(original)
        changed["m19_m30_regression"]["families"] = 11
        package["exact_evidence"] = (
            "00_Docs/04_검증 기록/evidence/m31-w06-close-20260926/"
            "test-invalid-regression-audit.json"
        )
        invalid = ROOT / package["exact_evidence"]
        try:
            invalid.write_text(
                json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "W06 M19-M30 regression evidence incomplete"):
                MODULE.validate(doc)
        finally:
            invalid.unlink(missing_ok=True)

    def test_w07_completion_requires_full_role_denominator(self) -> None:
        """! @brief 적용·외장·미지원 역할의 고정 분모 축소를 거부합니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        package = next(item for item in doc["work_packages"] if item["id"] == "M31-W07")
        package["applicable_role_passed"] = 38
        with self.assertRaisesRegex(ValueError, "W07 role denominator incomplete"):
            MODULE.validate(doc)

    def test_w07_completion_requires_safe_final_hil(self) -> None:
        """! @brief 자동 unlock·recover 없는 최종 3보드 HIL 경계를 유지합니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        package = next(item for item in doc["work_packages"] if item["id"] == "M31-W07")
        audit_path = ROOT / package["exact_evidence"]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        hil_path = audit_path.parent / audit["three_board_hil"]["evidence"]
        hil = json.loads(hil_path.read_text(encoding="utf-8"))
        changed = copy.deepcopy(hil)
        changed["safety"]["functional_flash_auto_unlock"] = True
        invalid = audit_path.parent / "test-invalid-w07-hil.json"
        original = audit["three_board_hil"]["evidence"]
        try:
            invalid.write_text(
                json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            audit["three_board_hil"]["evidence"] = invalid.name
            invalid_audit = audit_path.parent / "test-invalid-w07-audit.json"
            invalid_audit.write_text(
                json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            package["exact_evidence"] = str(invalid_audit.relative_to(ROOT))
            with self.assertRaisesRegex(
                ValueError, "W07 three-board HIL manifest incomplete"
            ):
                MODULE.validate(doc)
        finally:
            audit["three_board_hil"]["evidence"] = original
            invalid.unlink(missing_ok=True)
            (audit_path.parent / "test-invalid-w07-audit.json").unlink(missing_ok=True)

    def test_w07_forward_counter_gap_remains_observe_only(self) -> None:
        """! @brief 관찰된 순방향 gap을 완료 차단 조건으로 되돌리지 않습니다. """
        readiness = ROOT / "variants/nu54dk/m31-ble-readiness.json"
        doc = json.loads(readiness.read_text(encoding="utf-8"))
        package = next(item for item in doc["work_packages"] if item["id"] == "M31-W07")
        audit_path = ROOT / package["exact_evidence"]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        hil = json.loads(
            (audit_path.parent / audit["three_board_hil"]["evidence"]).read_text(
                encoding="utf-8"
            )
        )
        channel_sounding = hil["families"]["channel_sounding"]
        self.assertEqual(channel_sounding["counter_gap_policy"], "observe_only")
        self.assertEqual(channel_sounding["counter_gaps"], [{"before": 58, "after": 60}])
        MODULE.validate(doc)


if __name__ == "__main__":
    unittest.main()
