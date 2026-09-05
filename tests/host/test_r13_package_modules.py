#!/usr/bin/env python3
"""! @brief 패키저의 외부 CWD·격리 import·기존 인자 경계를 검증합니다. """
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "packaging/boards-manager/nu54_package.py"


def load(name: str):
    """! @brief 같은 entrypoint를 독립 Python 소비자 이름으로 읽습니다. """
    spec = importlib.util.spec_from_file_location(name, ENTRY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PackageModuleTests(unittest.TestCase):
    """! @brief 실제 CLI와 import 소비자의 경로 호환성을 검사합니다. """

    def test_isolated_cli_ignores_foreign_package_and_pythonpath(self):
        with tempfile.TemporaryDirectory(prefix="nu54-r13-설치 공백-") as temporary:
            root = Path(temporary)
            fake = root / "nu54_package_impl"
            fake.mkdir()
            (fake / "__init__.py").write_text("raise RuntimeError('FOREIGN_PACKAGE')\n")
            environment = {**os.environ, "PYTHONPATH": str(root)}
            for arguments in [["--help"], ["build", "--help"], ["validate", "--help"],
                              ["index", "--help"], ["validate-index", "--help"]]:
                result = subprocess.run([sys.executable, "-I", str(ENTRY), *arguments],
                                        cwd=root, env=environment, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b"usage: nu54_package.py", result.stdout)
                self.assertNotIn(b"FOREIGN_PACKAGE", result.stderr)

    def test_repository_default_and_multiple_import_identity(self):
        first = load("r13_package_first")
        second = load("r13_package_second")
        parsed = first.build_parser().parse_args(["build", "--output-dir", "unused", "--version", "0.0.90"])
        self.assertEqual(parsed.repo_root, ROOT)
        self.assertEqual(parsed.commit, "HEAD")
        self.assertFalse(parsed.update_index)
        self.assertIsNot(first.implementation, second.implementation)
        self.assertEqual(first.archive_filename("0.0.90"), "nucode-nu54dk-zephyr-0.0.90.zip")
        self.assertIs(first.PackageError, first.implementation.validation.PackageError)
        self.assertIs(first.SourceFile, first.implementation.inputs.SourceFile)

    def test_same_consumer_reload_does_not_reuse_candidate_state(self):
        first = load("r13_package_reloaded")
        original = first.RELEASE_CANDIDATE_VERSIONS
        first.configure_release_candidates(original + ("0.4.0-rc.1",))
        self.assertEqual(first.release_channel("0.4.0-rc.1"), "release-candidate")
        self.assertIn("0.4.0-rc.1", first.build_parser()._subparsers._group_actions[0].choices["build"]._option_string_actions["--version"].choices)
        second = load("r13_package_reloaded")
        self.assertEqual(second.RELEASE_CANDIDATE_VERSIONS, original)
        with self.assertRaises(second.PackageError):
            second.release_channel("0.4.0-rc.1")

    def test_error_marker_and_no_partial_output_for_invalid_version(self):
        module = load("r13_package_errors")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "absent"
            with self.assertRaises(module.PackageError):
                module.build_package(ROOT, output, "0.4.0", "HEAD")
            self.assertFalse(output.exists())
            result = subprocess.run([sys.executable, "-I", str(ENTRY), "build",
                                     "--output-dir", str(output), "--version", "0.0.90",
                                     "--commit", "r13-intentionally-missing-ref"],
                                    cwd=temporary, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertTrue(result.stderr.startswith(b"NU54_PACKAGE_ERROR="), result.stderr)
            self.assertEqual(result.stdout, b"")
            self.assertFalse(output.exists())

    def test_stable_snapshot_includes_moved_package_model(self):
        spec = importlib.util.spec_from_file_location("r13_m18_guard", ROOT / "tools/release/m18_release.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in module.STABLE_SOURCE_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("original\n")
            model = root / "packaging/boards-manager/nu54_package_impl/model.py"
            model.parent.mkdir()
            model.write_text("original stable identity\n")
            before = module.stable_source_snapshot(root)
            model.write_text("changed stable identity\n")
            self.assertNotEqual(before, module.stable_source_snapshot(root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
