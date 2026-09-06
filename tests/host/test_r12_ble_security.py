"""! @brief 실제 GAP/Security/Stack을 fake Bluetooth와 링크하여 lifecycle을 검증합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command
ROOT = Path(__file__).resolve().parents[2]


class BleSecurityTests(unittest.TestCase):
    def test_production_security_lifecycle(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r12-security-') as folder:
            binary = Path(folder) / 'security.exe'
            c_object = Path(folder) / 'hids_backend.o'
            c_compiler = compiler_command('c')
            self.assertIsNotNone(c_compiler)
            c_result = subprocess.run([*c_compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'tests/host/ble_stubs'),
                '-I', str(ROOT / 'libraries/NUCODE_BLE_Security/src'),
                '-c', str(ROOT / 'libraries/NUCODE_BLE_Security/src/internal/NUCODE_BLE_HidsBackend.c'),
                '-o', str(c_object)], capture_output=True, timeout=60)
            self.assertEqual(c_result.returncode, 0, c_result.stderr.decode(errors='replace'))
            command = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-DCONFIG_BT_DEVICE_NAME_MAX=32', '-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24',
                       '-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8', '-DCONFIG_BT_USER_PHY_UPDATE=1',
                       '-DCONFIG_BT_MAX_PAIRED=4', '-DCONFIG_BT_SETTINGS=1', '-DCONFIG_BT_SMP=1']
            for path in ['tests/host/ble_stubs', 'libraries/NUCODE_BLE/src', 'libraries/NUCODE_BLE_Security/src', 'third_party/ArduinoCore-API']:
                command += ['-I', str(ROOT / path)]
            command += [str(ROOT / path) for path in ['libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp',
                        'libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp',
                        'libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp',

                        'libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.cpp',
                        'libraries/NUCODE_BLE_Security/src/internal/security/SecurityPairing.cpp',
                        'libraries/NUCODE_BLE_Security/src/internal/security/SecurityBond.cpp',
                        'libraries/NUCODE_BLE_Security/src/internal/security/SecurityHid.cpp',
                        'libraries/NUCODE_BLE_Security/src/internal/security/SecurityBattery.cpp',
                        'libraries/NUCODE_BLE_Security/src/internal/security/SecurityDeviceInformation.cpp',
                        'tests/host/ble_stubs/hids_mock.cpp',
                        'tests/host/r12_ble_security_main.cpp']]
            result = subprocess.run(command + [str(c_object), '-o', str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in ['pairing_failure', 'pending_timeout', 'pending_duplicate', 'reentrant',
                             'late_callback', 'not_persisted', 'restored_bond', 'erase_failure',
                             'driver_failure', 'queue_overflow', 'profiles', 'hid']:
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
