#!/usr/bin/env python3
"""! @brief M32-W04 광고·identity·privacy production 경계를 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


REPOSITORY = Path(__file__).resolve().parents[2]


class M32BleAdvertisingTests(unittest.TestCase):
    """! @brief multi-set·sync·identity·list·EAD 음성 경계를 실행합니다. """

    def test_production_resource_and_security_lifecycle(self) -> None:
        """! @brief production source를 fake controller와 링크해 다섯 시나리오를 실행합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m32-w04-") as folder:
            binary = Path(folder) / "m32-w04.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-DNUCODE_HOST_STRONG_DEFAULT_HOOKS=1",
                "-DCONFIG_BT=1",
                "-DCONFIG_BT_EXT_ADV=1",
                "-DCONFIG_BT_EXT_ADV_MAX_ADV_SET=3",
                "-DCONFIG_BT_ID_MAX=3",
                "-DCONFIG_BT_EXT_ADV_CODING_SELECTION=1",
                "-DCONFIG_BT_FILTER_ACCEPT_LIST=1",
                "-DCONFIG_BT_CTLR_FAL_SIZE=4",
                "-DCONFIG_BT_CTLR_RL_SIZE=4",
                "-DCONFIG_BT_PER_ADV=1",
                "-DCONFIG_BT_PER_ADV_SYNC=1",
                "-DCONFIG_BT_PER_ADV_SYNC_MAX=2",
                "-DCONFIG_BT_CTLR_SYNC_PERIODIC_ADV_LIST_SIZE=2",
                "-DCONFIG_BT_EAD=1",
                "-DCONFIG_BT_OBSERVER=1",
                "-DCONFIG_BT_SCAN_AND_INITIATE_IN_PARALLEL=1",
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
                    "tests/host/m32_ble_advertising_main.cpp",
                )
            ]
            result = subprocess.run(
                command + ["-o", str(binary)], capture_output=True, timeout=60
            )
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
            for scenario in (
                "multiple_sets",
                "parameter_guards",
                "identities_lists",
                "ead_negative",
                "multiple_syncs",
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

    def test_examples_profiles_and_target_contracts_are_complete(self) -> None:
        """! @brief 공개 예제·sidecar·target contract의 W04 분모를 고정합니다. """

        examples = {
            "MultipleAdvertisingSets",
            "MultiplePeriodicSyncs",
            "MultipleBleIdentities",
            "AdvertisingAcceptList",
            "PeriodicAdvertiserList",
            "DirectedAdvertisingPeripheral",
            "DirectedAdvertisingCentral",
            "EncryptedAdvertisingPeripheral",
            "EncryptedAdvertisingCentral",
            "AdvertisingCodingSelection",
            "ScanWhileConnecting",
            "ScalableBleResources",
        }
        for name in examples:
            path = REPOSITORY / "libraries" / "NUCODE_BLE" / "examples" / name
            self.assertTrue((path / f"{name}.ino").is_file(), name)
        for relative in (
            "tests/zephyr/m32_ble_advertising_contract/prj.conf",
            "tests/zephyr/m32_ble_scan_initiate_contract/prj.conf",
        ):
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        extended = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_ble_advertising_contract"
            / "prj.conf"
        ).read_text(encoding="utf-8")
        for setting in (
            "CONFIG_BT_EXT_ADV_MAX_ADV_SET=3",
            "CONFIG_BT_ID_MAX=3",
            "CONFIG_BT_PER_ADV_SYNC_MAX=2",
            "CONFIG_BT_EAD=y",
        ):
            self.assertIn(setting, extended)
        parallel = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_ble_scan_initiate_contract"
            / "prj.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_ID_MAX=1", parallel)
        self.assertIn("CONFIG_BT_SCAN_AND_INITIATE_IN_PARALLEL=y", parallel)

        resource_root = (
            REPOSITORY / "tests" / "zephyr" / "m32_ble_resource_contract"
        )
        expected_profiles = {
            "c1p1.conf": (2, 1, 3, 3, 2),
            "c2p0.conf": (2, 0, 1, 2, 2),
            "c0p2.conf": (2, 2, 2, 2, 1),
        }
        for filename, values in expected_profiles.items():
            config = (resource_root / filename).read_text(encoding="utf-8")
            connections, peripherals, sets, identities, syncs = values
            for setting in (
                f"CONFIG_BT_MAX_CONN={connections}",
                f"CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT={peripherals}",
                f"CONFIG_BT_EXT_ADV_MAX_ADV_SET={sets}",
                f"CONFIG_BT_ID_MAX={identities}",
                f"CONFIG_BT_PER_ADV_SYNC_MAX={syncs}",
            ):
                self.assertIn(setting, config, f"{filename}: {setting}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
