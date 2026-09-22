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
                "-DCONFIG_BT_OBSERVER=1",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8",
                "-DCONFIG_NUCODE_BLE_CENTRAL_CONNECTION_SLOTS=2",
                "-DCONFIG_BT_CENTRAL=1",
                "-DCONFIG_BT_MAX_CONN=2",
                "-DCONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=0",
                "-DCONFIG_BT_PERIPHERAL=0",
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

    def test_second_central_routes_server_callback_to_exact_handle(self) -> None:
        """! @brief 같은 central 역할의 두 번째 link도 server event handle을 보존합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-csip-gatt-") as folder:
            binary = Path(folder) / "gatt.exe"
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
                "-DCONFIG_NUCODE_BLE_CENTRAL_CONNECTION_SLOTS=2",
                "-DCONFIG_BT_CENTRAL=1",
                "-DCONFIG_BT_MAX_CONN=2",
                "-DCONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=0",
                "-DCONFIG_BT_PERIPHERAL=0",
                "-DCONFIG_BT_USER_PHY_UPDATE=1",
                "-DCONFIG_NUCODE_BLE_GATT_MAX_SERVICES=2",
                "-DCONFIG_NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE=8",
                "-DCONFIG_NUCODE_BLE_GATT_EVENT_QUEUE_SIZE=24",
                "-DCONFIG_BT_SETTINGS=1",
                "-DCONFIG_BT_SMP=1",
                "-DCONFIG_BT_GATT_CACHING=1",
                "-DCONFIG_BT_SIGNING=1",
                "-DCONFIG_BT_EATT=1",
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
                    "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp",
                    "libraries/NUCODE_BLE/src/internal/gatt/GattDatabase.cpp",
                    "libraries/NUCODE_BLE/src/internal/gatt/GattCache.cpp",
                    "libraries/NUCODE_BLE/src/internal/gatt/GattServer.cpp",
                    "libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp",
                    "tests/host/r12_ble_gatt_main.cpp",
                ]
            ]
            result = subprocess.run(
                [*command, "-o", str(binary)], capture_output=True, timeout=60
            )
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
            result = run_executable(
                [str(binary), "dual_central_server_route"],
                capture_output=True,
                timeout=10,
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

    def test_dual_central_configuration_is_fail_closed(self) -> None:
        """! @brief 두 central slot은 host/controller resource 불일치를 컴파일에서 거부합니다. """

        internal = (ROOT / "libraries/NUCODE_BLE/src/internal/gap/GapInternal.h").read_text(
            encoding="utf-8"
        )
        for token in (
            "CONFIG_BT_MAX_CONN < 2",
            "CONFIG_BT_CENTRAL",
            "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT != 0",
            "Two central slots require a central-only Bluetooth Host",
            "slot.reserved",
        ):
            self.assertIn(
                token,
                internal
                + (
                    ROOT
                    / "libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp"
                ).read_text(encoding="utf-8"),
            )

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-csip-config-") as folder:
            source = Path(folder) / "invalid.cpp"
            source.write_text(
                "#include <internal/gap/GapInternal.h>\n", encoding="utf-8"
            )
            base = [
                *compiler,
                "-std=c++17",
                "-fsyntax-only",
                "-DCONFIG_BT_DEVICE_NAME_MAX=32",
                "-DCONFIG_NUCODE_BLE_CENTRAL_CONNECTION_SLOTS=2",
                "-DCONFIG_BT_CENTRAL=1",
                "-I",
                str(ROOT / "tests/host/ble_stubs"),
                "-I",
                str(ROOT / "libraries/NUCODE_BLE/src"),
                str(source),
            ]
            invalid_allocations = (
                ("-UCONFIG_BT_CENTRAL",),
                ("-DCONFIG_BT_CENTRAL=0",),
                ("-DCONFIG_BT_MAX_CONN=1", "-DCONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=0"),
                ("-DCONFIG_BT_MAX_CONN=2", "-DCONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1"),
            )
            for allocation in invalid_allocations:
                with self.subTest(allocation=allocation):
                    result = subprocess.run(
                        [*base, *allocation], capture_output=True, timeout=30
                    )
                    self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
