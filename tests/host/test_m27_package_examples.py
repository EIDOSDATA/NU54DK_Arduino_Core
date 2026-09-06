#!/usr/bin/env python3
"""Contract tests for the M27 staged-package example runner."""

from __future__ import annotations

import importlib.util
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


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
        self.assertIn("version=package_version", source)

    def test_local_software_package_cannot_be_labeled_rc_evidence(self) -> None:
        """! @brief 기존 RC 기본값과 software preview의 별도 identity를 유지합니다. """
        parser = MODULE.build_parser()
        option = parser._option_string_actions["--package-version"]
        self.assertEqual(option.default, MODULE.VERSION)
        self.assertEqual(set(option.choices), {MODULE.VERSION, "0.0.90"})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli, config, platform = root / "cli", root / "config", root / "platform"
            cli.touch()
            config.touch()
            platform.mkdir()
            lock = MODULE.load_example_lock()
            discovered = {(item["library"], item["example"]): platform / item["library_directory"] / item["example"] for item in lock}
            for version, milestone, evidence_type in [
                ("0.0.90", "R13", "staged-software-package-examples"),
                (MODULE.VERSION, "M27", "staged-candidate-package-examples"),
            ]:
                args = argparse.Namespace(
                    package_version=version, arduino_cli=cli, config=config, platform_root=platform,
                    build_root=root / version, evidence=root / (version + ".json"),
                    lock=MODULE.LOCK_PATH, forbid_root=[], compile_timeout=10, workers=1,
                    ncs_root=root / "ncs", toolchain_root=root / "toolchain", cache_root=root / "cache",
                )
                with mock.patch.object(MODULE.BASE, "run_command", return_value=(0, "{}", 0.0)), \
                     mock.patch.object(MODULE.BASE, "parse_installed_examples", return_value=discovered) as discovery, \
                     mock.patch.object(MODULE.BASE, "validate_build_manifest", return_value={"hex_sha256": "a" * 64}), \
                     mock.patch.object(MODULE.BASE, "cli_identity", return_value={"version": "test"}):
                    evidence = MODULE.run_gate(args)
                self.assertEqual(discovery.call_args.kwargs["version"], version)
                self.assertEqual(evidence["release_version"], version)
                self.assertEqual(evidence["milestone"], milestone)
                self.assertEqual(evidence["evidence_type"], evidence_type)
                self.assertEqual(evidence["compiled_count"], 29)
                self.assertEqual(json.loads(args.evidence.read_text(encoding="utf-8")), evidence)

    def test_runner_parallelizes_independent_build_roots(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ThreadPoolExecutor(max_workers=args.workers)", source)
        self.assertIn("results.sort", source)
        self.assertIn('"milestone": "M27"', source)
        self.assertNotIn("core install", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
