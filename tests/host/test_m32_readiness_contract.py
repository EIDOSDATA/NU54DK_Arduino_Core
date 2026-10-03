"""! @brief M32 기능·자원·시험 원장의 fail-closed 규칙을 검사합니다. """

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/bluetooth/m32_contract.py"
SPEC = importlib.util.spec_from_file_location("m32_contract_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M32ReadinessContractTests(unittest.TestCase):
    """! @brief M32 분모·revision·단계·후속시험 경계를 고정합니다. """

    def setUp(self) -> None:
        """! @brief 각 시험에 검증된 새 원장을 제공합니다. """
        self.document = MODULE.contract()

    def test_canonical_denominators_and_fixed_baseline(self) -> None:
        """! @brief W01~W12와 parity·시험 분모 및 고정 SDK를 확인합니다. """
        MODULE.validate(self.document)
        self.assertEqual(self.document["counts"]["work_total"], 12)
        self.assertEqual(self.document["counts"]["m32_parity_samples"], 41)
        self.assertEqual(self.document["counts"]["m32_parity_variants"], 74)
        self.assertEqual(self.document["counts"]["test_family_total"], 24)
        self.assertEqual(
            self.document["baseline"]["development_branch"], "Dev-0.6.0-M32"
        )

    def test_duplicate_capability_and_revision_drift_are_rejected(self) -> None:
        """! @brief 중복 기능과 SDK·board revision 변경을 허용하지 않습니다. """
        duplicate = copy.deepcopy(self.document)
        duplicate["capabilities"].append(copy.deepcopy(duplicate["capabilities"][0]))
        drift = copy.deepcopy(self.document)
        drift["baseline"]["ncs_revision"] = "0" * 40
        for broken in (duplicate, drift):
            with self.subTest(capabilities=len(broken["capabilities"])):
                with self.assertRaises(ValueError):
                    MODULE.validate(broken)

    def test_unknown_status_route_applicability_and_mapping_are_rejected(self) -> None:
        """! @brief unknown enum과 비어 있는 구현 연결을 모두 막습니다. """
        mutations = []
        for key, value in (
            ("target_applicability", "maybe"),
            ("arduino_provision", "magic"),
            ("planned_examples", []),
            ("resource_profile_ids", ["missing_profile"]),
            ("test_ids", ["M32-MISSING-01"]),
        ):
            broken = copy.deepcopy(self.document)
            broken["capabilities"][0][key] = value
            mutations.append(broken)
        bad_stage = copy.deepcopy(self.document)
        bad_stage["capabilities"][0]["stages"]["runtime_capability"]["status"] = "MAYBE"
        mutations.append(bad_stage)
        for broken in mutations:
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_hil_cannot_pass_before_exact_native_build(self) -> None:
        """! @brief HIL PASS가 native build PASS를 대신하지 못하게 합니다. """
        broken = copy.deepcopy(self.document)
        stage = broken["capabilities"][0]["stages"]["functional_hil"]
        stage.update({
            "status": "PASS",
            "revision": MODULE.LOCK["ncs"]["revision"],
            "evidence": MODULE.CONTRACT_EVIDENCE,
        })
        with self.assertRaisesRegex(ValueError, "HIL promoted"):
            MODULE.validate(broken)

    def test_source_or_build_only_capability_cannot_enter_support_catalog(self) -> None:
        """! @brief 기능 HIL 전 후보를 지원 catalog로 승격하지 못하게 합니다. """

        broken = copy.deepcopy(self.document)
        broken["validated_support_candidates"]["capability_ids"] = [
            broken["capabilities"][0]["id"]
        ]
        with self.assertRaisesRegex(ValueError, "support catalog"):
            MODULE.validate(broken)

    def test_not_run_stage_build_and_test_cannot_carry_evidence(self) -> None:
        """! @brief 실행하지 않은 항목에 revision·증거가 남는 승격을 거부합니다. """
        stage = copy.deepcopy(self.document)
        stage["capabilities"][0]["stages"]["runtime_capability"]["revision"] = "1" * 40
        build = copy.deepcopy(self.document)
        build["build_matrix"][0]["source_revision"] = "1" * 40
        test = copy.deepcopy(self.document)
        test["test_families"][0]["cases"][0]["evidence"] = MODULE.CONTRACT_EVIDENCE
        for broken in (stage, build, test):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_resource_caps_and_test_quantitative_rules_are_fixed(self) -> None:
        """! @brief 메모리 상한과 packet·재시험 분모 완화를 막습니다. """
        too_large = copy.deepcopy(self.document)
        too_large["resource_profiles"][0]["measured_ram_bytes"] = (
            too_large["resource_profiles"][0]["maximum_ram_bytes"] + 1
        )
        loss = copy.deepcopy(self.document)
        case = loss["test_families"][0]["cases"][0]
        case["allowed_loss_packets"] = case["packet_denominator"] + 1
        retest = copy.deepcopy(self.document)
        retest["test_families"][0]["cases"][0]["maximum_diagnostic_retests"] = 2
        for broken in (too_large, loss, retest):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_user_follow_up_cannot_hide_development_or_release_gates(self) -> None:
        """! @brief 사용자 후속과 최종 Host 물리 gate의 blocker 의미를 보존합니다. """
        development = copy.deepcopy(self.document)
        development["follow_up_cases"][0]["development_blocker"] = True
        release = copy.deepcopy(self.document)
        release["follow_up_cases"][-1]["release_blocker"] = False
        for broken in (development, release):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_w04_resource_presets_and_fixed_profile_conflict_are_explicit(self) -> None:
        """! @brief ARF 역할 preset과 scan/identity controller 충돌을 고정합니다. """

        builds = {entry["id"]: entry for entry in self.document["build_matrix"]}
        for identifier, profile in (
            ("m32_resource_c1p1_sdc", "ble_c1p1"),
            ("m32_resource_c2p0_sdc", "ble_c2p0"),
            ("m32_resource_c0p2_sdc", "ble_c0p2"),
        ):
            self.assertEqual(builds[identifier]["resource_profile_id"], profile)
        self.assertIn(
            {
                "left": "scan_initiate_parallel",
                "right": "multiple_identities",
                "condition": "same_image",
                "status": "forbidden_by_fixed_controller_requires_id_max_1",
            },
            self.document["profile_conflicts"],
        )

    def test_w05_nordic_build_uses_dedicated_profile(self) -> None:
        """! @brief Nordic 확장 target contract가 전용 자원 profile을 사용합니다. """

        builds = {entry["id"]: entry for entry in self.document["build_matrix"]}
        nordic = builds["m32_nordic_sdc"]
        self.assertEqual(
            nordic["application"], "tests/zephyr/m32_ble_nordic_contract"
        )
        self.assertEqual(nordic["resource_profile_id"], "ble_nordic")


if __name__ == "__main__":
    unittest.main()
