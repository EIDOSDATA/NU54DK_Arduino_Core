#!/usr/bin/env python3
"""M24 serial-fabric route, identity and API contract tests."""

from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "tools" / "peripheral" / "verify_m24_serial_contract.py"
SPEC = importlib.util.spec_from_file_location("nucode_m24_serial_contract", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M24SerialContractTests(unittest.TestCase):
    """Fail-closed route and future API contract semantics."""

    def setUp(self) -> None:
        self.contract = MODULE.strict_json_object(MODULE.CONTRACT_PATH)

    def test_contract_schema_generated_document_and_exact_ncs_pass(self) -> None:
        MODULE.validate_schema_contract(MODULE.strict_json_object(MODULE.SCHEMA_PATH))
        identities = MODULE.validate_contract(self.contract)
        self.assertEqual(len(identities), 23)
        installed = Path("C:/ncs/v3.4.0")
        if installed.is_dir():
            MODULE.validate_ncs_dts(self.contract, installed)
        result = subprocess.run(
            [os.fspath(Path(os.sys.executable)), os.fspath(SCRIPT)],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn(
            "M24_SERIAL_CONTRACT_PASS=blocks:5;identities:23;profiles:23",
            result.stdout,
        )

    def test_block_personality_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.contract)
        lookup = {item["id"]: item for item in mutated["blocks"]}
        lookup["serial21"]["personalities"].remove("twis21")
        with self.assertRaisesRegex(MODULE.ContractFailure, "block identity/personality drifted"):
            MODULE.validate_contract(mutated)

    def test_public_alias_or_singleton_identity_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["stable_surface"]["singletons"][1]["identity"] = "uarte21"
        with self.assertRaisesRegex(MODULE.ContractFailure, "stable singleton identity drifted"):
            MODULE.validate_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        mutated["stable_surface"]["forbidden_aliases"].remove("Serial2")
        with self.assertRaisesRegex(MODULE.ContractFailure, "forbidden alias set drifted"):
            MODULE.validate_contract(mutated)

    def test_dedicated_pin_mapping_and_board_conflict_are_rejected_on_drift(self) -> None:
        mutated = copy.deepcopy(self.contract)
        bank = next(item for item in mutated["pin_banks"] if item["id"] == "p2-dedicated20")
        bank["signal_sets"]["spim"]["sck"] = "P2.6"
        with self.assertRaisesRegex(MODULE.ContractFailure, "dedicated signal mapping drifted"):
            MODULE.validate_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        bank = next(item for item in mutated["pin_banks"] if item["id"] == "p2-dedicated21")
        bank["board_status"] = "approved"
        with self.assertRaisesRegex(MODULE.ContractFailure, "pin bank identity/status drifted"):
            MODULE.validate_contract(mutated)

    def test_every_identity_needs_one_approved_hil_profile(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["approved_profiles"] = [
            item for item in mutated["approved_profiles"] if item["identity"] != "spis30"
        ]
        with self.assertRaisesRegex(MODULE.ContractFailure, "exactly one HIL route profile"):
            MODULE.validate_contract(mutated)

    def test_unsafe_pin_profile_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.contract)
        profile = next(
            item for item in mutated["approved_profiles"] if item["identity"] == "uarte21"
        )
        profile["pins"]["txd"] = "P1.8"
        with self.assertRaisesRegex(MODULE.ContractFailure, "blocked P1 pin"):
            MODULE.validate_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        profile = next(
            item for item in mutated["approved_profiles"] if item["identity"] == "spim30"
        )
        profile["preconditions"] = ["Serial1 is inactive."]
        with self.assertRaisesRegex(MODULE.ContractFailure, "Serial1/DAP isolation"):
            MODULE.validate_contract(mutated)

    def test_local_board_source_checksum_is_fail_closed(self) -> None:
        mutated = copy.deepcopy(self.contract["sources"])
        source = next(item for item in mutated if item["id"] == "board-schematic")
        source["sha256"] = "0" * 64
        with self.assertRaisesRegex(MODULE.ContractFailure, "checksum mismatch"):
            MODULE.validate_sources(mutated)

    def test_contract_only_api_does_not_promote_manifest_support(self) -> None:
        manifest = MODULE.strict_json_object(MODULE.MANIFEST_PATH)
        m24 = {item["id"]: item for item in manifest["instances"] if item["milestone"] == "M24"}
        current = set(MODULE.EXPECTED_SINGLETONS.values())
        self.assertEqual(len(m24), 23)
        for identity, item in m24.items():
            if identity in current:
                continue
            states = item["states"]
            self.assertEqual(states["source"], "absent", identity)
            self.assertEqual(states["exposure"], "none", identity)
            for axis in ("build", "semantic", "hil", "concurrent_hil"):
                self.assertEqual(states[axis], "not_run", f"{identity}.{axis}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
