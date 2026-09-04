#!/usr/bin/env python3
"""Host tests for the private M27 staged-candidate runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "release" / "m27_staged_candidate.py"
SPEC = importlib.util.spec_from_file_location("m27_staged_candidate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M27StagedCandidateTests(unittest.TestCase):
    def test_archive_members_require_exact_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("../escape.txt", "forbidden")
            with self.assertRaises(MODULE.StagedCandidateFailure):
                MODULE.validate_zip_members(archive)

    def test_stage_archive_places_payload_at_arduino_platform_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "candidate.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr(f"{MODULE.ARCHIVE_ROOT}/platform.txt", "name=NU54\n")
            workspace = root / "stage"
            platform = MODULE.stage_archive(archive, workspace)
            self.assertEqual(
                platform,
                workspace
                / "data"
                / "packages"
                / "nucode"
                / "hardware"
                / "zephyr"
                / MODULE.VERSION,
            )
            self.assertEqual((platform / "platform.txt").read_text(), "name=NU54\n")

    def test_runner_has_no_publication_command(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("core install", source)
        self.assertNotIn("release create", source)
        self.assertNotIn("git tag", source)
        self.assertIn('"--workers"', source)


if __name__ == "__main__":
    unittest.main()
