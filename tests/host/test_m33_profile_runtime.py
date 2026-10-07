"""! @brief 표준 서비스와 실제 GATT backend의 runtime 계약을 검사합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest
from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]


class ProfileRuntimeTests(unittest.TestCase):
    def test_production_gatt_services(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        definitions = {
            "BT_OBSERVER": 1, "BT_DEVICE_NAME_MAX": 32,
            "NUCODE_BLE_CORE_EVENT_QUEUE_SIZE": 24, "NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE": 8,
            "BT_USER_PHY_UPDATE": 1, "NUCODE_BLE_GATT_SERVER": 1, "NUCODE_BLE_GATT_CLIENT": 1,
            "NUCODE_BLE_GATT_MAX_SERVICES": 2, "NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE": 8,
            "NUCODE_BLE_GATT_EVENT_QUEUE_SIZE": 24, "BT_SETTINGS": 1, "BT_SMP": 1,
            "BT_GATT_CACHING": 1, "BT_SIGNING": 1, "BT_EATT": 1,
        }
        sources = [
            "libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp",
            "libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp",
            "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp",
            *[str(p.relative_to(ROOT)) for p in (ROOT / "libraries/NUCODE_BLE/src/internal/gap").glob("*.cpp")],
            *[str(p.relative_to(ROOT)) for p in (ROOT / "libraries/NUCODE_BLE/src/internal/gatt").glob("*.cpp")],
            "libraries/NUCODE_BLE_Profiles/src/NUCODE_BLE_ProfileCodec.cpp",
            "libraries/NUCODE_BLE_Profiles/src/NUCODE_BLE_Profiles.cpp",
            "libraries/NUCODE_BLE_Profiles/src/NUCODE_BLE_ObjectStore.cpp",
            "tests/host/m33_profile_runtime_main.cpp",
        ]
        with tempfile.TemporaryDirectory(prefix="nu54-profile-runtime-") as folder:
            binary = Path(folder) / "profile.exe"
            command = [*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread"]
            command += [f"-DCONFIG_{name}={value}" for name, value in definitions.items()]
            for include in ("tests/host/ble_stubs", "third_party/ArduinoCore-API",
                            "libraries/NUCODE_BLE/src", "libraries/NUCODE_BLE_Security/src",
                            "libraries/NUCODE_BLE_Profiles/src"):
                command += ["-I", str(ROOT / include)]
            command += [str(ROOT / source) for source in sources]
            result = subprocess.run(command + ["-o", str(binary)], capture_output=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            for scenario in ("cts", "hts", "csc", "rscs", "ets", "alerts", "bonds", "object_store"):
                with self.subTest(scenario=scenario):
                    result = run_executable([str(binary), scenario], capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
