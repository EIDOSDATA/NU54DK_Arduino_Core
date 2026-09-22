"""! @brief 실제 GAP/GATT/Stack을 fake Bluetooth와 링크하여 lifecycle을 검증합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable
ROOT = Path(__file__).resolve().parents[2]


class BleGattTests(unittest.TestCase):
    def test_production_gatt_lifecycle(self):
        """! @brief PE-COFF 보안 기본 훅을 보완하고 GATT 구현의 대체를 검증합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r12-gatt-') as folder:
            binary = Path(folder) / 'gatt.exe'
            command = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-DCONFIG_BT_OBSERVER=1',
                       '-DCONFIG_BT_DEVICE_NAME_MAX=32', '-DCONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE=24',
                       '-DCONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE=8', '-DCONFIG_BT_USER_PHY_UPDATE=1',
                       '-DCONFIG_NUCODE_BLE_GATT_MAX_SERVICES=2', '-DCONFIG_NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE=8',
                       '-DCONFIG_NUCODE_BLE_GATT_EVENT_QUEUE_SIZE=24', '-DCONFIG_BT_SETTINGS=1', '-DCONFIG_BT_SMP=1',
                       '-DCONFIG_BT_GATT_CACHING=1', '-DCONFIG_BT_SIGNING=1',
                       '-DCONFIG_BT_EATT=1']
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

                        'libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp',
                        'libraries/NUCODE_BLE/src/internal/gatt/GattDatabase.cpp',
                        'libraries/NUCODE_BLE/src/internal/gatt/GattCache.cpp',
                        'libraries/NUCODE_BLE/src/internal/gatt/GattServer.cpp',
                        'libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp',
                        'tests/host/r12_ble_gatt_main.cpp']]
            result = subprocess.run(command + ['-o', str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in ['registration_failure', 'server_copy', 'server_overflow', 'server_reentrant',
                             'notification', 'indication', 'discovery_failure', 'client_io', 'client_late',
                             'subscription', 'att_failure', 'mixed_server_route',
                             'm29_long_parallel', 'm29_long_write',
                             'm29_descriptor_authorization', 'm29_descriptor_reuse',
                             'm29_cache_restore', 'm29_cache_service_changed',
                             'm29_cache_corrupt', 'm29_cache_no_ccc',
                             'm29_signed_write', 'm29_signed_overflow', 'm29_eatt',
                             'client_reentrant_end']:
                with self.subTest(scenario=scenario):
                    result = run_executable([str(binary), scenario], capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

            capacity_binary = Path(folder) / 'gatt-tx-capacity.exe'
            capacity_result = subprocess.run(
                command + ['-DCONFIG_NUCODE_BLE_GATT_TX_PAYLOAD_SIZE=64',
                           '-o', str(capacity_binary)],
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(
                capacity_result.returncode,
                0,
                capacity_result.stderr.decode(errors='replace'),
            )
            capacity_run = run_executable(
                [str(capacity_binary), 'tx_capacity'], capture_output=True, timeout=10
            )
            self.assertEqual(
                capacity_run.returncode,
                0,
                capacity_run.stderr.decode(errors='replace'),
            )


if __name__ == '__main__':
    unittest.main()
