#!/usr/bin/env python3
"""! @brief W04 periodic advertising·sync·PAST production source를 Host에서 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


REPOSITORY = Path(__file__).resolve().parents[2]
HEADER_PATH = REPOSITORY / "libraries" / "NUCODE_BLE" / "src" / "NUCODE_BLE_GAP.h"
PROFILE_PATH = REPOSITORY / "libraries" / "NUCODE_BLE" / "zephyr" / "ble-nus.conf"
TARGET_CONFIG_PATH = (
    REPOSITORY / "tests" / "zephyr" / "m28_ble_periodic_contract" / "prj.conf"
)


class M28BlePeriodicTests(unittest.TestCase):
    """! @brief periodic set·sync generation·report·PAST 경계를 검증합니다. """

    def test_periodic_advertising_sync_and_past_lifecycle(self) -> None:
        """! @brief 실제 GAP source를 fake controller와 링크해 네 수명 시나리오를 실행합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m28-w04-") as folder:
            binary = Path(folder) / "m28-w04.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-DNUCODE_HOST_STRONG_DEFAULT_HOOKS=1",
                "-DCONFIG_BT_EXT_ADV=1",
                "-DCONFIG_BT_PER_ADV=1",
                "-DCONFIG_BT_PER_ADV_SYNC=1",
                "-DCONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER=1",
                "-DCONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER=1",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8",
                "-DCONFIG_NUCODE_BLE_PERIODIC_REPORT_QUEUE_SIZE=8",
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
                    "tests/host/m28_ble_periodic_main.cpp",
                )
            ]
            result = subprocess.run(command + ["-o", str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            for scenario in ("advertiser", "sync_report", "past", "end_cleanup"):
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
        """! @brief 공개 API·Kconfig·target·예제의 one-sync 상한을 고정합니다. """

        header = HEADER_PATH.read_text(encoding="utf-8")
        for token in (
            "class BLEPeriodicSyncHandle final",
            "struct BLEPeriodicReport",
            "class PeriodicAdvertising final",
            "bool transferSync(BLEPeriodicSyncHandle sync",
            "bool subscribeTransfers(BLEConnectionHandle connection",
            "extern nucode::ble::PeriodicAdvertising BLEPeriodicAdvertising",
        ):
            self.assertIn(token, header)
        for path in (PROFILE_PATH, TARGET_CONFIG_PATH):
            config = path.read_text(encoding="utf-8")
            for setting in (
                "CONFIG_BT_PER_ADV=y",
                "CONFIG_BT_PER_ADV_SYNC=y",
                "CONFIG_BT_PER_ADV_SYNC_MAX=1",
                "CONFIG_BT_CTLR_SYNC_PERIODIC_ADV_LIST_SIZE=1",
                "CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER=y",
                "CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER=y",
                "CONFIG_NUCODE_BLE_PERIODIC_REPORT_QUEUE_SIZE=8",
            ):
                self.assertIn(setting, config, f"{path}: {setting}")
        for relative_path in (
            "libraries/NUCODE_BLE/examples/PeriodicAdvertiser/PeriodicAdvertiser.ino",
            "libraries/NUCODE_BLE/examples/PeriodicScanner/PeriodicScanner.ino",
            "libraries/NUCODE_BLE/examples/PastSender/PastSender.ino",
            "libraries/NUCODE_BLE/examples/PastReceiver/PastReceiver.ino",
        ):
            example = REPOSITORY / relative_path
            self.assertTrue(example.is_file(), example)
            self.assertIn("BLEDevice.begin(", example.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
