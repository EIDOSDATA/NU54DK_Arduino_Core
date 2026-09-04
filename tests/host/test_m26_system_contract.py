#!/usr/bin/env python3
"""M26 system-peripheral support-boundary contract tests."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "tools" / "peripheral" / "verify_m26_system_contract.py"
SPEC = importlib.util.spec_from_file_location("nucode_m26_system_contract", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M26SystemContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.strict_json(MODULE.CONTRACT_PATH)

    def test_all_m26_identities_have_a_non_unknown_disposition(self) -> None:
        capabilities = MODULE.validate_contract(self.contract)
        self.assertEqual(len(capabilities), 16)
        self.assertEqual(
            {item["id"] for item in capabilities}, set(MODULE.EXPECTED_DISPOSITIONS)
        )
        self.assertNotIn("unknown", {item["disposition"] for item in capabilities})

    def test_raw_radio_is_exclusive_with_managed_ble(self) -> None:
        self.assertEqual(
            self.contract["raw_radio_policy"],
            "exclusive-with-managed-ble-and-not-public-in-v0.4.0",
        )
        radio = next(item for item in self.contract["capabilities"] if item["id"] == "radio")
        self.assertEqual(radio["disposition"], "partial")
        self.assertIn("배타", radio["coexistence"])

    def test_supported_state_requires_automated_and_physical_pass(self) -> None:
        mutated = copy.deepcopy(self.contract)
        power = next(item for item in mutated["capabilities"] if item["id"] == "power")
        power["physical_gate"] = "not_run"
        with self.assertRaisesRegex(MODULE.ContractFailure, "supported disposition lacks PASS"):
            MODULE.validate_contract(mutated)

    def test_silicon_only_capability_cannot_be_public(self) -> None:
        mutated = copy.deepcopy(self.contract)
        nfct = next(item for item in mutated["capabilities"] if item["id"] == "nfct")
        nfct["surface"] = "public"
        with self.assertRaisesRegex(MODULE.ContractFailure, "silicon/board-only"):
            MODULE.validate_contract(mutated)

    def test_schematic_hash_and_generated_document_are_exact(self) -> None:
        capabilities = MODULE.validate_contract(self.contract)
        expected = MODULE.render_document(self.contract, capabilities)
        self.assertEqual(MODULE.DOCUMENT_PATH.read_text(encoding="utf-8"), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
