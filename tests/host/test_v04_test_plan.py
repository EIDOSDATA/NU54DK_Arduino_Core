"""Preparation coverage must fail closed without touching physical gate evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("v04_plan", ROOT / "tools/peripheral/verify_v04_test_plan.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class V04TestPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = MODULE.read_json(MODULE.PLAN)

    def test_exact_inventory_and_generated_document(self):
        inventory = MODULE.validate(self.plan)
        self.assertEqual(len(inventory), 75)
        self.assertEqual(len(self.plan["cases"]), 19)
        self.assertEqual(MODULE.render(self.plan, inventory), MODULE.DOCUMENT.read_text(encoding="utf-8"))

    def test_missing_or_duplicate_case_rejected(self):
        for duplicate in (False, True):
            plan = copy.deepcopy(self.plan)
            plan["cases"].pop()
            if duplicate:
                plan["cases"].append(plan["cases"][0])
            with self.assertRaises(MODULE.PlanFailure):
                MODULE.validate(plan)

    def test_instance_omission_rejected(self):
        self.plan["groups"]["uarte"].pop()
        with self.assertRaisesRegex(MODULE.PlanFailure, "inventory"):
            MODULE.validate(self.plan)

    def test_qdec_not_dma(self):
        case = next(c for c in self.plan["cases"] if c["id"] == "V04-DMA-LIFETIME")
        case["groups"].append("qdec")
        with self.assertRaises(MODULE.PlanFailure):
            MODULE.validate(self.plan)

    def test_zero_timeout_and_loss_allowance_rejected(self):
        for key, value in (("command_timeout_seconds", 0), ("unexpected_loss_allowed", 1), ("guard_bytes", True)):
            plan = copy.deepcopy(self.plan)
            plan["limits"][key] = value
            with self.assertRaises(MODULE.PlanFailure):
                MODULE.validate(plan)

    def test_passing_plan_or_result_field_rejected(self):
        for mutate in (lambda p: p.update(status="passed"), lambda p: p["cases"][0].update(result="passed")):
            plan = copy.deepcopy(self.plan)
            mutate(plan)
            with self.assertRaises(MODULE.PlanFailure):
                MODULE.validate(plan)

    def test_empty_criteria_and_bad_reuse_path_rejected(self):
        for key, value in (("oracle", ""), ("modes", []), ("reuse", ["../outside.py"])):
            plan = copy.deepcopy(self.plan)
            plan["cases"][0][key] = value
            with self.assertRaises(MODULE.PlanFailure):
                MODULE.validate(plan)

    def test_unknown_erratum_rejected(self):
        self.plan["cases"][0]["errata"].append(999)
        with self.assertRaisesRegex(MODULE.PlanFailure, "errata"):
            MODULE.validate(self.plan)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(MODULE.PlanFailure, "duplicate JSON"):
            MODULE.unique_object([("id", 1), ("id", 2)])

    def test_inventory_gate_calls_preparation_validator(self):
        gate = (ROOT / "tools/ci/run_m12_gate.py").read_text(encoding="utf-8")
        self.assertIn('"verify_v04_test_plan.py"', gate)


if __name__ == "__main__":
    unittest.main()
