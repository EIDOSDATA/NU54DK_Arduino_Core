#!/usr/bin/env python3
"""Contract tests for the M27 staged-package example runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "tools" / "release" / "run_m27_package_examples.py"
SPEC = importlib.util.spec_from_file_location("nu54_m27_package_examples", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M27PackageExampleTests(unittest.TestCase):
    def test_lock_has_exact_version_profiles_and_count(self) -> None:
        records = MODULE.load_example_lock()
        self.assertEqual(len(records), 29)
        self.assertEqual({item["profile"] for item in records}, {"standard", "ble"})
        self.assertEqual(MODULE.VERSION, "0.4.0-rc.1")

    def test_m22_historical_runner_remains_pinned(self) -> None:
        self.assertEqual(MODULE.BASE.VERSION, "0.3.0-rc.3")
        self.assertEqual(MODULE.BASE.EXPECTED_EXAMPLE_COUNT, 29)

    def test_runner_uses_version_explicit_discovery(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("version=VERSION", source)
        self.assertIn('"milestone": "M27"', source)
        self.assertNotIn("core install", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
