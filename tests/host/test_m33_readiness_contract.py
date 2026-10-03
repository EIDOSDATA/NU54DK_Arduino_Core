"""! @brief M33 전체 원장과 릴리스 정책의 fail-closed 규칙을 검사합니다. """

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/bluetooth/m33_contract.py"
TARGET_PATH = ROOT / "variants/nu54dk/m33-release-readiness.json"
SPEC = importlib.util.spec_from_file_location("m33_contract_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M33ReadinessContractTests(unittest.TestCase):
    """! @brief 원장 분모·owner·승격·후속 실물 gate를 고정합니다. """

    def setUp(self) -> None:
        """! @brief 저장된 현행 readiness를 각 시험에 복제합니다. """
        self.document = json.loads(TARGET_PATH.read_text(encoding="utf-8"))

    def test_canonical_inventory_denominators(self) -> None:
        """! @brief 고정 SDK·M33·예제·service·시험 분모를 확인합니다. """
        MODULE.validate(self.document)
        counts = self.document["counts"]
        self.assertEqual(counts["work_total"], 8)
        self.assertEqual(counts["work_completed"], 2)
        self.assertEqual(counts["master_sample_total"], 190)
        self.assertEqual(counts["master_variant_total"], 474)
        self.assertEqual(counts["m33_sample_total"], 108)
        self.assertEqual(counts["m33_variant_total"], 318)
        self.assertEqual(counts["installed_example_total"], 196)
        self.assertEqual(counts["installed_ble_radio_example_total"], 173)
        self.assertEqual(counts["installed_core_peripheral_example_total"], 23)
        self.assertEqual(counts["sig_service_total"], 69)
        self.assertEqual(counts["test_family_total"], 12)
        self.assertEqual(counts["test_case_total"], 17)
        self.assertEqual(counts["test_case_passed"], 7)

    def test_deduplication_denominators_are_explicit(self) -> None:
        """! @brief 파일 중복 제거와 기능군 통합 분모를 혼동하지 않습니다. """
        summary = self.document["deduplication_summary"]
        self.assertEqual(
            summary["variant_to_sample"],
            {
                "master_before": 474,
                "master_after": 190,
                "m33_before": 318,
                "m33_after": 108,
            },
        )
        sketches = summary["installed_sketch_exact"]
        self.assertEqual(sketches["before"], 196)
        self.assertEqual(sketches["unique_content_after"], 196)
        self.assertEqual(sketches["exact_duplicate_group_count"], 0)
        self.assertEqual(sketches["unique_name_after"], 196)
        self.assertEqual(sketches["duplicate_name_group_count"], 0)
        self.assertEqual(
            sketches["domain_counts"],
            {"core_peripheral": 23, "bluetooth_radio": 173},
        )
        functional = summary["planned_functional_groups"]
        self.assertEqual(
            functional["by_owner"],
            {"M33-W02": 12, "M33-W03": 4, "M33-W04": 6},
        )
        self.assertEqual(functional["total"], 22)
        self.assertFalse(summary["role_distinct_sketches_are_duplicates"])

        broken = copy.deepcopy(self.document)
        broken["deduplication_summary"]["planned_functional_groups"]["total"] = 21
        with self.assertRaisesRegex(ValueError, "deduplication"):
            MODULE.validate(broken)

    def test_example_discovery_keeps_a_small_front_door(self) -> None:
        """! @brief 대표 진입점과 전체 reference 원장을 동시에 보존합니다. """
        discovery = self.document["example_discovery"]
        self.assertEqual(
            discovery["presentation_tiers"],
            ["start_here", "functional_recipe", "reference"],
        )
        self.assertEqual(len(discovery["start_here_journeys"]), 12)
        self.assertGreaterEqual(discovery["functional_recipe_group_total"], 20)
        self.assertEqual(discovery["m33_planned_functional_group_total"], 22)
        self.assertEqual(discovery["reference_sketch_total"], 196)
        self.assertEqual(discovery["missing_featured_paths"], [])
        self.assertEqual(discovery["featured_sketch_total"], 24)
        self.assertEqual(
            discovery["guidance_contract"]["required_fields"],
            [
                "purpose", "requirements", "configuration", "run_steps",
                "success_output", "common_errors", "next_examples",
            ],
        )
        self.assertEqual(
            sum(
                entry["presentation_tier"] == "start_here"
                for entry in self.document["installed_example_catalog"]
            ),
            24,
        )
        self.assertTrue(all(
            entry["recipe_group"]
            for entry in self.document["installed_example_catalog"]
        ))
        self.assertFalse(discovery["rules"]["root_readme_lists_every_sketch"])
        self.assertTrue(discovery["rules"]["full_catalog_remains_searchable"])

        broken = copy.deepcopy(self.document)
        broken["example_discovery"]["start_here_journeys"][0]["sketches"][0] = (
            "libraries/missing/Missing.ino"
        )
        with self.assertRaisesRegex(ValueError, "discovery"):
            MODULE.validate(broken)

    def test_duplicate_missing_owner_and_reasonless_exclusion_are_rejected(self) -> None:
        """! @brief 누락·중복·미배정 owner·이유 없는 제외를 거부합니다. """
        duplicate = copy.deepcopy(self.document)
        duplicate["upstream_catalog"].append(copy.deepcopy(duplicate["upstream_catalog"][0]))
        missing_owner = copy.deepcopy(self.document)
        missing_owner["upstream_catalog"][0]["owner_work_id"] = ""
        excluded = copy.deepcopy(self.document)
        row = next(
            entry for entry in excluded["upstream_catalog"]
            if entry["route"] == "excluded"
        )
        row["exclusion_reason"] = None
        for broken in (duplicate, missing_owner, excluded):
            with self.subTest(rows=len(broken["upstream_catalog"])):
                with self.assertRaises(ValueError):
                    MODULE.validate(broken)

    def test_unverified_support_and_publication_are_rejected(self) -> None:
        """! @brief source/build/NOT_RUN을 지원·공개 상태로 승격하지 않습니다. """
        support = copy.deepcopy(self.document)
        support["release_contract"]["validated_support_ids"] = ["source_only"]
        publication = copy.deepcopy(self.document)
        publication["release_contract"]["publication_status"] = "published"
        not_run = copy.deepcopy(self.document)
        not_run["release_contract"]["not_run_is_pass"] = True
        for broken in (support, publication, not_run):
            with self.assertRaisesRegex(ValueError, "promotion"):
                MODULE.validate(broken)

    def test_required_implementation_cannot_be_hidden_as_user_follow_up(self) -> None:
        """! @brief 필수 구현 case를 사용자 후속으로 바꾸지 못하게 합니다. """
        broken = copy.deepcopy(self.document)
        case = broken["test_families"][0]["cases"][0]
        case.update({
            "verification_owner": "user",
            "verification_stage": "user_follow_up",
            "development_blocker": False,
            "release_blocker": False,
        })
        with self.assertRaisesRegex(ValueError, "hidden"):
            MODULE.validate(broken)

    def test_user_follow_up_and_final_host_gate_are_distinct(self) -> None:
        """! @brief 외부 제품 비차단과 Ubuntu/macOS 최종 gate를 구분합니다. """
        external = copy.deepcopy(self.document)
        external["follow_up_cases"][0]["release_blocker"] = True
        host = copy.deepcopy(self.document)
        host["follow_up_cases"][-1]["release_blocker"] = False
        fake_pass = copy.deepcopy(self.document)
        fake_pass["follow_up_cases"][0]["status"] = "PASS"
        for broken in (external, host, fake_pass):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_not_run_and_pass_evidence_rules_are_enforced(self) -> None:
        """! @brief 미실행 evidence와 exact 근거 없는 PASS를 모두 거부합니다. """
        not_run = copy.deepcopy(self.document)
        not_run["test_families"][3]["cases"][0]["evidence"] = MODULE.CONTRACT_EVIDENCE
        fake_pass = copy.deepcopy(self.document)
        fake_pass["test_families"][3]["cases"][0]["status"] = "PASS"
        for broken in (not_run, fake_pass):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_w01_pass_uses_clean_exact_source_and_evidence(self) -> None:
        """! @brief W01 완료와 네 inventory PASS가 같은 exact 증거를 사용합니다. """
        work = self.document["work_packages"][0]
        self.assertEqual(work["status"], "completed")
        self.assertEqual(work["exact_evidence"], MODULE.W01_EVIDENCE)
        inventory = self.document["test_families"][0]
        self.assertEqual(len(inventory["cases"]), 4)
        self.assertTrue(all(
            case["status"] == "PASS" and
            case["source_revision"] == MODULE.W01_SOURCE_REVISION and
            case["evidence"] == MODULE.W01_EVIDENCE
            for case in inventory["cases"]
        ))

    def test_w02_profile_and_beacon_exact_completion(self) -> None:
        """! @brief W02 profile·Beacon 자동 검사와 HIL 완료를 exact 근거로 고정합니다. """

        work = self.document["work_packages"][1]
        self.assertEqual(work["status"], "completed")
        self.assertEqual(work["exact_evidence"], MODULE.W02_EVIDENCE)
        profile = next(
            entry for entry in self.document["test_families"]
            if entry["id"] == "M33-PROFILE-01"
        )
        beacon = next(
            entry for entry in self.document["test_families"]
            if entry["id"] == "M33-BEACON-01"
        )
        self.assertEqual(len(profile["cases"]), 1)
        self.assertEqual(len(beacon["cases"]), 2)
        self.assertTrue(all(
            case["status"] == "PASS" and
            case["source_revision"] == MODULE.W02_SOURCE_REVISION and
            case["evidence"] == MODULE.W02_EVIDENCE
            for family in (profile, beacon)
            for case in family["cases"]
        ))
        examples = [
            entry for entry in self.document["installed_example_catalog"]
            if entry["owner_work_id"] == "M33-W02"
        ]
        self.assertEqual(len(examples), 9)
        self.assertTrue(all(
            entry["owner_work_id"] == "M33-W02" and
            entry["stages"]["arduino_build"]["status"] == "PASS" and
            entry["stages"]["functional_hil"]["status"] == "PASS" and
            entry["stages"]["external_peer_interop"]["status"] == "NOT_RUN"
            for entry in examples
        ))
        upstream = [
            entry for entry in self.document["upstream_catalog"]
            if entry["owner_work_id"] == "M33-W02" and not entry["exclusion_reason"]
        ]
        self.assertTrue(upstream)
        self.assertTrue(all(
            entry["delivery_state"] == "implemented_m33" and
            entry["execution_requirements"]["resolution"] == "implemented_m33_family"
            for entry in upstream
        ))
        services = [
            entry for entry in self.document["sig_service_catalog"]
            if entry["owner_work_id"] == "M33-W02"
        ]
        profiles = [
            entry for entry in self.document["profile_delivery_catalog"]
            if entry["owner_work_id"] == "M33-W02"
        ]
        self.assertEqual(len(services), 9)
        self.assertEqual(len(profiles), 8)
        self.assertTrue(all(
            entry["delivery_status"] == "implemented_m33"
            for entry in services + profiles
        ))

    def test_example_and_sig_service_drift_are_rejected(self) -> None:
        """! @brief 설치 Sketch·service UUID 원장 수작업 drift를 막습니다. """
        example = copy.deepcopy(self.document)
        example["installed_example_catalog"][0]["owner_work_id"] = ""
        service = copy.deepcopy(self.document)
        service["sig_service_catalog"][0]["decision_reason"] = ""
        for broken in (example, service):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_upstream_requirements_and_example_stages_are_separate(self) -> None:
        """! @brief 역할 요구와 source/build/HIL/peer 상태의 분리를 고정합니다. """
        self.assertTrue(all(
            entry["execution_requirements"]["source"]
            for entry in self.document["upstream_catalog"]
        ))
        self.assertTrue(all(
            entry["arduino_delivery"]["owner_work_id"] == entry["owner_work_id"]
            for entry in self.document["upstream_catalog"]
        ))
        self.assertTrue(all(
            set(entry["stages"]) == {
                "source_candidate", "native_build", "arduino_build",
                "functional_hil", "external_peer_interop",
            }
            for entry in self.document["installed_example_catalog"]
        ))

        requirements = copy.deepcopy(self.document)
        requirements["upstream_catalog"][0]["execution_requirements"]["source"] = ""
        stages = copy.deepcopy(self.document)
        del stages["installed_example_catalog"][0]["stages"]["functional_hil"]
        for broken in (requirements, stages):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_ncs_340_policy_and_conditional_risks_are_preserved(self) -> None:
        """! @brief SDK 자동 전환과 patch note의 원인 단정을 거부합니다. """
        upgrade = copy.deepcopy(self.document)
        upgrade["sdk_policy"]["active_version"] = "3.4.1"
        cause = copy.deepcopy(self.document)
        cause["sdk_policy"]["patch_note_is_failure_cause"] = True
        for broken in (upgrade, cause):
            with self.assertRaisesRegex(ValueError, "3.4.0 policy"):
                MODULE.validate(broken)
        risk_ids = {entry["id"] for entry in self.document["sdk_risk_regressions"]}
        self.assertIn("DRGN-29228", risk_ids)
        self.assertIn("DRGN-29669", risk_ids)


if __name__ == "__main__":
    unittest.main()
