"""! @brief SDK 호출 경계를 주입해 실제 OTS/CGMS adapter와 미설정 fail-closed를 시험합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest
from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]


class ProfileNativeTests(unittest.TestCase):
    def test_native_and_disabled(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-profile-native-") as folder:
            for connections in (0, 1, 2):
                with self.subTest(connections=connections):
                    enabled = connections != 0
                    binary = Path(folder) / f"native-{connections}.exe"
                    command = [*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread"]
                    if enabled:
                        command += ["-DCONFIG_BT_OTS=1", "-DCONFIG_BT_OTS_CLIENT=1",
                                    "-DCONFIG_BT_CGMS=1", "-DCONFIG_BT_OTS_OBJ_MAX_NAME_LEN=32",
                                    f"-DCONFIG_BT_MAX_CONN={connections}"]
                    for include in ("tests/host/m33_profile_native_stubs", "tests/host/ble_stubs",
                                    "libraries/NUCODE_BLE_Profiles/src"):
                        command += ["-I", str(ROOT / include)]
                    command += [str(ROOT / "libraries/NUCODE_BLE_Profiles/src" / name) for name in (
                        "NUCODE_BLE_ProfileCodec.cpp", "NUCODE_BLE_ObjectStore.cpp",
                        "NUCODE_BLE_ObjectTransfer.cpp", "NUCODE_BLE_Glucose.cpp")]
                    command += [str(ROOT / "tests/host/m33_profile_native_main.cpp"), "-o", str(binary)]
                    result = subprocess.run(command, capture_output=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                    if connections == 1:
                        for wrong_size in (16, 120):
                            mismatch = [f"-DCONFIG_BT_OTS_OBJ_MAX_NAME_LEN={wrong_size}" if arg == "-DCONFIG_BT_OTS_OBJ_MAX_NAME_LEN=32" else arg for arg in command]
                            mismatch += ["-fsyntax-only"]
                            rejected = subprocess.run(mismatch, capture_output=True, timeout=90)
                            self.assertNotEqual(rejected.returncode, 0)
                            self.assertIn(b"OTS object name configuration must be exactly 32 bytes", rejected.stderr)
                    for scenario in (("server", "client", "client_retry", "client_bonded_reconnect", "glucose") if connections == 1 else ("disabled",)):
                        result = run_executable([str(binary), scenario], capture_output=True, timeout=15)
                        self.assertEqual(result.returncode, 0, scenario + result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
