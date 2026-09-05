"""! @brief 실제 GAP/GATT/Stack을 fake Bluetooth와 링크하여 lifecycle을 검증합니다. """
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[2]


class BleGattTests(unittest.TestCase):
    def test_production_gatt_lifecycle(self):
        compiler = shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r12-gatt-') as folder:
            binary = Path(folder) / 'gatt.exe'
            command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-DCONFIG_BT_DEVICE_NAME_MAX=32', '-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24',
                       '-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8', '-DCONFIG_BT_USER_PHY_UPDATE=1',
                       '-DCONFIG_NUCODE_BLE_GATT_MAX_SERVICES=2', '-DCONFIG_NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE=8',
                       '-DCONFIG_NUCODE_BLE_GATT_EVENT_QUEUE_SIZE=24', '-DCONFIG_BT_SETTINGS=1', '-DCONFIG_BT_SMP=1']
            for path in ['tests/host/ble_stubs', 'libraries/NUCODE_BLE/src']:
                command += ['-I', str(ROOT / path)]
            command += [str(ROOT / path) for path in ['libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp',
                        'libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp',

                        'libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp',
                        'libraries/NUCODE_BLE/src/internal/gatt/GattDatabase.cpp',
                        'libraries/NUCODE_BLE/src/internal/gatt/GattServer.cpp',
                        'libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp',
                        'tests/host/r12_ble_gatt_main.cpp']]
            result = subprocess.run(command + ['-o', str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in ['registration_failure', 'server_copy', 'server_overflow', 'server_reentrant',
                             'notification', 'indication', 'discovery_failure', 'client_io', 'client_late',
                             'subscription', 'att_failure']:
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
