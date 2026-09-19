"""! @brief CSIP Coordinator의 opt-in 2-central GAP 수명주기를 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


ROOT = Path(__file__).resolve().parents[2]


class CsipGapTests(unittest.TestCase):
    """! @brief 기본 역할 분할과 coordinator 전용 역할 분할을 함께 고정합니다. """

    def test_two_central_connections_keep_exact_generations(self) -> None:
        """! @brief 두 outgoing link와 stale callback의 slot 재사용 격리를 실행합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-csip-gap-") as folder:
            binary = Path(folder) / "gap.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-DNUCODE_HOST_STRONG_DEFAULT_HOOKS=1",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8",
                "-DCONFIG_NUCODE_BLE_CENTRAL_CONNECTION_SLOTS=2",
                "-DCONFIG_BT_USER_PHY_UPDATE=1",
                "-DCONFIG_BT_SETTINGS=1",
                "-DCONFIG_BT_SMP=1",
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
                    "tests/host/r12_ble_gap_main.cpp",
                ]
            ]
            result = subprocess.run(
                [*command, "-o", str(binary)], capture_output=True, timeout=60
            )
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
            result = run_executable(
                [str(binary), "two_central"], capture_output=True, timeout=10
            )
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )

    def test_default_partition_remains_one_plus_one(self) -> None:
        """! @brief 기존 profile의 controller·slot 기본값이 바뀌지 않았는지 확인합니다. """

        profile = (ROOT / "libraries/NUCODE_BLE/zephyr/ble-nus.conf").read_text(
            encoding="utf-8"
        )
        kconfig = (ROOT / "zephyr/config/ble.Kconfig").read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1", profile)
        self.assertIn("config NUCODE_BLE_CENTRAL_CONNECTION_SLOTS", kconfig)
        self.assertIn("default 1", kconfig)


if __name__ == "__main__":
    unittest.main(verbosity=2)
