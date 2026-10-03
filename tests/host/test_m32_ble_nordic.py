#!/usr/bin/env python3
"""! @brief M32-W05 Nordic extension production 경계를 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


REPOSITORY = Path(__file__).resolve().parents[2]


class M32BleNordicTests(unittest.TestCase):
    """! @brief LLPM·QoS·anchor·event·ACL 적용성 시나리오를 실행합니다. """

    def test_nordic_extension_lifecycle_and_negative_boundaries(self) -> None:
        """! @brief production source를 fake SDC와 링크해 세 시나리오를 실행합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m32-w05-") as folder:
            binary = Path(folder) / "m32-w05.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-DNUCODE_HOST_STRONG_DEFAULT_HOOKS=1",
                "-DCONFIG_BT=1",
                "-DCONFIG_BT_CENTRAL=1",
                "-DCONFIG_BT_PERIPHERAL=1",
                "-DCONFIG_BT_MAX_CONN=2",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_BT_USER_PHY_UPDATE=1",
                "-DCONFIG_BT_EXT_ADV=1",
                "-DCONFIG_BT_EXT_ADV_MAX_ADV_SET=1",
                "-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_NUCODE_BLE_NORDIC_EXTENSIONS=1",
                "-DCONFIG_NUCODE_BLE_NORDIC_REPORT_QUEUE_SIZE=4",
                "-DCONFIG_BT_HCI_VS_EVT_USER=1",
                "-DCONFIG_BT_CTLR_SDC_LLPM=1",
                "-DCONFIG_BT_CTLR_SDC_QOS_CONN_EVENT_REPORT=1",
                "-DCONFIG_BT_CTLR_SDC_QOS_CHANNEL_SURVEY=1",
                "-DCONFIG_BT_CTLR_SDC_CONN_ANCHOR_POINT_REPORT=1",
                "-DCONFIG_BT_CTLR_SDC_EVENT_TRIGGER=1",
                "-DCONFIG_BT_CTLR_LE_FLUSHABLE_ACL_DATA=1",
            ]
            for path in ("tests/host/ble_stubs", "libraries/NUCODE_BLE/src"):
                command += ["-I", str(REPOSITORY / path)]
            command += [
                str(REPOSITORY / path)
                for path in (
                    "libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp",
                    "libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapExtendedAdvertising.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapPeriodicAdvertising.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapPawr.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp",
                    "libraries/NUCODE_BLE/src/internal/gap/GapNordic.cpp",
                    "tests/host/m32_ble_nordic_main.cpp",
                )
            ]
            result = subprocess.run(
                command + ["-o", str(binary)], capture_output=True, timeout=60
            )
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
            for scenario in ("llpm", "reports", "negative"):
                with self.subTest(scenario=scenario):
                    result = run_executable(
                        [str(binary), scenario], capture_output=True, timeout=10
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stderr.decode(errors="replace"),
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
