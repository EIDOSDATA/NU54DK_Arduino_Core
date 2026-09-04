"""CMake exact revision resolver under different-owner CI simulation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RevisionTests(unittest.TestCase):
    def test_different_owner_is_scoped_and_nonrepository_rejected(self):
        cmake = shutil.which("cmake")
        self.assertIsNotNone(cmake, "Host CMake required")
        with tempfile.TemporaryDirectory(prefix="nu54-revision-") as directory:
            script = Path(directory) / "check.cmake"
            script.write_text(f'include("{ROOT.as_posix()}/tests/zephyr/v04_pair_hil/read_revision.cmake")\n'
                              'nucode_hil_revision("${SOURCE_ROOT}" value)\nmessage("EXACT=${value}")\n', encoding="utf-8")
            environment = {**os.environ, "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}
            expected = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            for root, success in ((ROOT, True), (Path(directory), False)):
                result = subprocess.run([cmake, f"-DSOURCE_ROOT={root.as_posix()}", "-P", str(script)],
                    env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
                if success: self.assertIn("EXACT=" + expected, result.stderr)
                else: self.assertIn("Cannot determine exact HIL source revision", result.stderr)


if __name__ == "__main__": unittest.main()
