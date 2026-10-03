"""! @brief 실제 GAP/Stack을 fake Bluetooth와 링크하여 lifecycle을 검증합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable
ROOT = Path(__file__).resolve().parents[2]


class BleGapTests(unittest.TestCase):
    def test_production_gap_lifecycle(self):
        """! @brief PE-COFF 기본 훅을 강하게 링크하고 GAP 수명주기를 검증합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r12-gap-') as folder:
            binary = Path(folder) / 'gap.exe'
            command = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-DNUCODE_HOST_STRONG_DEFAULT_HOOKS=1',
                       '-DCONFIG_BT_CONN=1',
                       '-DCONFIG_BT_OBSERVER=1',
                       '-DCONFIG_BT_DEVICE_NAME_MAX=32', '-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24',
                       '-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8', '-DCONFIG_BT_USER_PHY_UPDATE=1',
                       '-DCONFIG_BT_SETTINGS=1', '-DCONFIG_BT_SMP=1',
                       '-DCONFIG_BT_TRANSMIT_POWER_CONTROL=1',
                       '-DCONFIG_BT_PATH_LOSS_MONITORING=1',
                       '-DCONFIG_BT_CTLR_CONN_RSSI=1',
                       '-DCONFIG_BT_SUBRATING=1', '-DCONFIG_BT_CENTRAL=1',
                       '-DCONFIG_BT_SHORTER_CONNECTION_INTERVALS=1',
                       '-DCONFIG_BT_LE_EXTENDED_FEAT_SET=1',
                       '-DCONFIG_BT_FRAME_SPACE_UPDATE=1', '-DCONFIG_BT_SCA_UPDATE=1']
            for path in ['tests/host/ble_stubs', 'libraries/NUCODE_BLE/src']:
                command += ['-I', str(ROOT / path)]
            command += [str(ROOT / path) for path in ['libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp',
                        'libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapExtendedAdvertising.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapPeriodicAdvertising.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapPawr.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp',

                        'tests/host/r12_ble_gap_main.cpp']]
            result = subprocess.run(command + ['-o', str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in ['lifecycle', 'late_callback', 'reconnect', 'recycled', 'queue_overflow',
                             'reentrant', 'pending_end', 'scan_copy', 'driver_failure',
                             'settings_failure', 'settings_preloaded', 'advertising',
                             'multi_link', 'generation',
                             'end_two_links', 'role_callback_guard', 'power_control',
                             'timing_features']:
                with self.subTest(scenario=scenario):
                    result = run_executable([str(binary), scenario], capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
