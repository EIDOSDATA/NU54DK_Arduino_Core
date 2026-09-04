#!/usr/bin/env python3
"""Contract tests for M27 private v0.4.0 release preparation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "tools" / "release" / "m27_release.py"
SPEC = importlib.util.spec_from_file_location("nu54_m27_release", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M27ReleaseTests(unittest.TestCase):
    def test_contract_has_every_required_gate_and_remains_hold(self) -> None:
        ledger = MODULE.validate_contract()
        self.assertEqual(
            tuple(gate["id"] for gate in ledger["gates"]), MODULE.REQUIRED_GATE_IDS
        )
        ready, blockers = MODULE.effective_readiness(
            ledger, package_reproducibility_passed=True
        )
        self.assertFalse(ready)
        self.assertNotIn("package_reproducibility", blockers)
        self.assertIn("m24_onboard_hil", blockers)
        self.assertIn("project_owner_approval", blockers)

    def test_candidate_extension_does_not_add_unapproved_stable(self) -> None:
        package = MODULE.load_package_module()
        MODULE.configure_v04_candidate(package)
        self.assertIn(MODULE.VERSION, package.RELEASE_CANDIDATE_VERSIONS)
        self.assertNotIn(MODULE.STABLE_VERSION, package.STABLE_VERSIONS)
        self.assertEqual(package.release_channel(MODULE.VERSION), "release-candidate")
        self.assertEqual(package.release_tag(MODULE.VERSION), "v0.4.0-rc.1")

    def test_historical_package_contract_is_not_modified(self) -> None:
        package = MODULE.load_package_module()
        self.assertEqual(package.RELEASE_CANDIDATE_VERSIONS, MODULE.BASE_RC_VERSIONS)
        self.assertEqual(package.STABLE_VERSIONS, MODULE.BASE_STABLE_VERSIONS)

    def test_cli_exposes_no_publish_or_finalize_command(self) -> None:
        parser = MODULE.build_parser()
        action = next(
            item for item in parser._actions if getattr(item, "choices", None)
        )
        self.assertEqual(set(action.choices), {"contract", "prepare", "validate-plan"})

    def test_plan_rejects_publication_or_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "m27-release-plan.json"
            path.write_text(
                '{"schema_version":1,"milestone":"M27",'
                '"version":"0.4.0-rc.1","stable_version":"0.4.0",'
                '"status":"ready","publication_allowed":true}\n',
                encoding="utf-8",
            )
            with self.assertRaises(MODULE.M27ReleaseFailure):
                MODULE.validate_plan(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
