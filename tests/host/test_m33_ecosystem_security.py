#!/usr/bin/env python3
"""! @brief AppleClient의 동기·비동기 보안 실패 분류를 실제 source로 검사합니다. """
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CompanionSecurityTests(unittest.TestCase):
    """! @brief disconnect 경합에서도 security 오류가 먼저 보존되는지 검사합니다. """

    def test_immediate_and_asynchronous_security_errors(self):
        """! @brief 공개 callback과 begin 반환값이 모두 security로 일치해야 합니다. """
        compiler = os.environ.get("CXX")
        self.assertTrue(compiler, "CXX must select the explicit MSYS2 compiler")
        with tempfile.TemporaryDirectory(prefix="nu54-companion-security-") as folder:
            binary = Path(folder) / "security.exe"
            command = [
                compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-DCONFIG_BT_GATT_DM=1",
                "-DCONFIG_BT_SMP=1",
                "-I",
                str(ROOT / "tests/host/m33_ecosystem_runtime_stubs"),
                "-I",
                str(ROOT / "libraries/NUCODE_BLE_Companion/src"),
                str(ROOT / "tests/host/m33_ecosystem_security_main.cpp"),
                str(ROOT / "libraries/NUCODE_BLE_Companion/src/NUCODE_BLE_CompanionCodec.cpp"),
                "-o",
                str(binary),
            ]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            result = subprocess.run([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
