#!/usr/bin/env python3
"""! @brief W03 extended advertising/scanning production source를 Host에서 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


REPOSITORY = Path(__file__).resolve().parents[2]
HEADER_PATH = REPOSITORY / "libraries" / "NUCODE_BLE" / "src" / "NUCODE_BLE_GAP.h"
PROFILE_PATH = REPOSITORY / "libraries" / "NUCODE_BLE" / "zephyr" / "ble-nus.conf"
TARGET_CONFIG_PATH = (
    REPOSITORY / "tests" / "zephyr" / "m28_ble_extended_contract" / "prj.conf"
)


class M28BleExtendedTests(unittest.TestCase):
    """! @brief set generation·255-byte payload·extended metadata 경계를 검증합니다. """

    def test_extended_advertising_and_scanning_lifecycle(self) -> None:
        """! @brief 실제 GAP source를 fake controller와 링크해 네 수명 시나리오를 실행합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m28-w03-") as folder:
            binary = Path(folder) / "m28-w03.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-DNUCODE_HOST_STRONG_DEFAULT_HOOKS=1",
                "-DCONFIG_BT_EXT_ADV=1",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8",
                "-DCONFIG_BT_USER_PHY_UPDATE=1",
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
                    "tests/host/m28_ble_extended_main.cpp",
                )
            ]
            result = subprocess.run(command + ["-o", str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            for scenario in ("set_lifecycle", "invalid_payload", "extended_scan", "end_cleanup"):
                with self.subTest(scenario=scenario):
                    result = run_executable(
                        [str(binary), scenario], capture_output=True, timeout=10
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stderr.decode(errors="replace"),
                    )

    def test_public_profile_target_and_examples_are_bounded(self) -> None:
        """! @brief 공개 API·production Kconfig·target 계약·예제의 고정 상한을 대조합니다. """

        header = HEADER_PATH.read_text(encoding="utf-8")
        for token in (
            "class BLEAdvertisingSetHandle final",
            "maximum_payload_length = 255U",
            "bool startExtended(bool active = true, bool coded = false)",
            "class ExtendedAdvertising final",
            "extern nucode::ble::ExtendedAdvertising BLEExtendedAdvertising",
        ):
            self.assertIn(token, header)
        for path in (
            PROFILE_PATH,
            TARGET_CONFIG_PATH,
        ):
            config = path.read_text(encoding="utf-8")
            for setting in (
                "CONFIG_BT_EXT_ADV=y",
                "CONFIG_BT_EXT_ADV_MAX_ADV_SET=1",
                "CONFIG_BT_CTLR_ADV_DATA_LEN_MAX=255",
            ):
                self.assertIn(setting, config, f"{path}: {setting}")
        for relative_path in (
            "libraries/NUCODE_BLE/examples/ExtendedAdvertising/ExtendedAdvertising.ino",
            "libraries/NUCODE_BLE/examples/ExtendedScanner/ExtendedScanner.ino",
        ):
            example = REPOSITORY / relative_path
            self.assertTrue(example.is_file(), example)
            self.assertIn("BLEDevice.begin(", example.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
