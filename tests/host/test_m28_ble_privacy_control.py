#!/usr/bin/env python3
"""! @brief W06 privacy·RPA와 per-link control production source를 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


REPOSITORY = Path(__file__).resolve().parents[2]
HEADER_PATH = REPOSITORY / "libraries" / "NUCODE_BLE" / "src" / "NUCODE_BLE_GAP.h"
PROFILE_PATH = REPOSITORY / "libraries" / "NUCODE_BLE" / "zephyr" / "ble-nus.conf"
TARGET_CONFIG_PATH = REPOSITORY / "tests" / "zephyr" / "m28_ble_privacy_control_contract" / "prj.conf"


class M28BlePrivacyControlTests(unittest.TestCase):
    """! @brief identity·RPA·DLE·remote-info generation 격리를 검증합니다. """

    def test_privacy_and_per_link_control_lifecycle(self) -> None:
        """! @brief production GAP source를 fake controller와 링크해 다섯 시나리오를 실행합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m28-w06-") as folder:
            binary = Path(folder) / "m28-w06.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-DNUCODE_HOST_STRONG_DEFAULT_HOOKS=1",
                "-DCONFIG_BT_EXT_ADV=1",
                "-DCONFIG_BT_PRIVACY=1",
                "-DCONFIG_BT_RPA_TIMEOUT_DYNAMIC=1",
                "-DCONFIG_BT_RPA_TIMEOUT=900",
                "-DCONFIG_BT_SMP=1",
                "-DCONFIG_BT_REMOTE_INFO=1",
                "-DCONFIG_BT_USER_DATA_LEN_UPDATE=1",
                "-DCONFIG_BT_USER_PHY_UPDATE=1",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8",
                "-DCONFIG_NUCODE_BLE_PERIODIC_REPORT_QUEUE_SIZE=8",
                "-DCONFIG_NUCODE_BLE_PAWR_RESPONSE_QUEUE_SIZE=8",
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
                    "tests/host/m28_ble_privacy_control_main.cpp",
                )
            ]
            result = subprocess.run(command + ["-o", str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            for scenario in (
                "per_link_control",
                "identity_resolution",
                "stale_callback",
                "privacy_rotation",
                "extended_incoming",
            ):
                with self.subTest(scenario=scenario):
                    result = run_executable(
                        [str(binary), scenario], capture_output=True, timeout=10
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stderr.decode(errors="replace"),
                    )

    def test_public_profile_target_and_examples_have_fixed_contract(self) -> None:
        """! @brief 공개 API·Kconfig·target·예제의 W06 경계를 고정합니다. """

        header = HEADER_PATH.read_text(encoding="utf-8")
        for token in (
            "struct BLEConnectionParameters",
            "struct BLEDataLengthInfo",
            "struct BLERemoteInformation",
            "class Privacy final",
            "requestDataLength(BLEConnectionHandle connection",
            "remoteInformation(BLEConnectionHandle connection",
            "extern nucode::ble::Privacy BLEPrivacy",
        ):
            self.assertIn(token, header)
        for path in (PROFILE_PATH, TARGET_CONFIG_PATH):
            config = path.read_text(encoding="utf-8")
            for setting in (
                "CONFIG_BT_PRIVACY=y",
                "CONFIG_BT_RPA_TIMEOUT_DYNAMIC=y",
                "CONFIG_BT_DATA_LEN_UPDATE=y",
                "CONFIG_BT_USER_DATA_LEN_UPDATE=y",
                "CONFIG_BT_AUTO_DATA_LEN_UPDATE=n",
                "CONFIG_BT_REMOTE_INFO=y",
                "CONFIG_BT_REMOTE_VERSION=y",
            ):
                self.assertIn(setting, config, f"{path}: {setting}")
        for relative_path in (
            "libraries/NUCODE_BLE/examples/PrivacyPeripheral/PrivacyPeripheral.ino",
            "libraries/NUCODE_BLE/examples/PerLinkControl/PerLinkControl.ino",
        ):
            example = REPOSITORY / relative_path
            self.assertTrue(example.is_file(), example)
            self.assertIn("BLEDevice.begin(", example.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
