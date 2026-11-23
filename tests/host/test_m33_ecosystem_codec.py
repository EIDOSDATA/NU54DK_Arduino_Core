#!/usr/bin/env python3
"""! @brief Apple protocol production codec의 실제 Host 실행을 검증합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest
from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]


class CompanionCodecTests(unittest.TestCase):
    """! @brief 알려진 byte와 모든 ANCS fragment 경계·잘못된 frame을 검사합니다. """

    def test_wire_fragments_and_stale_session(self):
        """! @brief 테스트 대역이 아닌 공개 codec source를 링크해 실행합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-companion-") as folder:
            executable = Path(folder) / "companion.exe"
            source = ROOT / "libraries/NUCODE_BLE_Companion/src"
            result = subprocess.run([
                *compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I", str(source), str(source / "NUCODE_BLE_CompanionCodec.cpp"),
                str(ROOT / "tests/host/m33_ecosystem_codec_main.cpp"), "-o", str(executable)
            ], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            result = run_executable([str(executable)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
