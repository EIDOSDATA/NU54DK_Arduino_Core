"""! @brief 실제 GAP/LE CoC 구현의 고정 자원 수명을 Host에서 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]


class BleL2capTests(unittest.TestCase):
    def test_production_l2cap_lifecycle(self):
        """! @brief generation·RX/TX 상한·backpressure·회수를 실제 소스로 검증합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-r12-l2cap-") as folder:
            binary = Path(folder) / "l2cap.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-DCONFIG_BT_OBSERVER=1",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8",
                "-DCONFIG_BT_USER_PHY_UPDATE=1",
                "-DCONFIG_BT_L2CAP_DYNAMIC_CHANNEL=1",
                "-DCONFIG_NUCODE_BLE_L2CAP=1",
                "-DCONFIG_NUCODE_BLE_L2CAP_EVENT_QUEUE_SIZE=16",
                "-DCONFIG_BT_CONN_TX_USER_DATA_SIZE=8",
            ]
            for path in ["tests/host/ble_stubs", "libraries/NUCODE_BLE/src"]:
                command += ["-I", str(ROOT / path)]
            command += [
                str(ROOT / path)
                for path in [
                    "libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp",
                    "libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapExtendedAdvertising.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapPeriodicAdvertising.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapPawr.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp",
                    "libraries/NUCODE_BLE/src/NUCODE_BLE_L2CAP.cpp",
                    "tests/host/r12_ble_l2cap_main.cpp",
                ]
            ]
            result = subprocess.run(command + ["-o", str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            for scenario in [
                "lifecycle",
                "backpressure",
                "receive_bounds",
                "stale_reuse",
                "server_accept",
                "driver_failures",
                "end",
            ]:
                with self.subTest(scenario=scenario):
                    result = run_executable(
                        [str(binary), scenario], capture_output=True, timeout=10
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stderr.decode(errors="replace")
                    )


if __name__ == "__main__":
    unittest.main()
