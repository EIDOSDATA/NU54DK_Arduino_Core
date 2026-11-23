"""! @brief 실제 표준 GATT codec의 wire 형식과 음성 경계를 Host에서 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]


class ProfileCodecTests(unittest.TestCase):
    """! @brief packet·달력·signed 값·길이·link 격리 runtime 시험입니다. """

    def test_production_codec(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-profile-") as folder:
            binary = Path(folder) / "profiles.exe"
            result = subprocess.run(
                [*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                 "-I", str(ROOT / "libraries/NUCODE_BLE_Profiles/src"),
                 str(ROOT / "libraries/NUCODE_BLE_Profiles/src/NUCODE_BLE_ProfileCodec.cpp"),
                 str(ROOT / "tests/host/m33_profile_codec_main.cpp"), "-o", str(binary)],
                capture_output=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            result = run_executable([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
