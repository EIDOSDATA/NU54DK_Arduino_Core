"""! @brief 실제 Serial lifecycle·resource manager의 STOP 중 교차 호출을 검증합니다. """
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ['progress', 'same_handle', 'same_block', 'timeout', 'request_error', 'driver_error']


class SerialConcurrencyTests(unittest.TestCase):
    def test_production_stop_reservation(self):
        compiler = shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r10-') as directory:
            binary = Path(directory) / 'serial.exe'
            command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-DCONFIG_NUCODE_ARDUINO_IO_RESOURCE_SLOTS=48']
            for include in ['tests/host/serial_driver_stubs', 'tests/host/serial_fabric_stubs',
                            'cores/arduino', 'variants/nu54dk']:
                command.extend(['-I', str(ROOT / include)])
            command.extend(str(ROOT / path) for path in ['tests/host/r10_serial_concurrency_main.cpp',
                           'cores/arduino/SerialFabric.cpp',
                           'cores/arduino/internal/serial/SerialFabricRegistry.cpp',
                           'cores/arduino/internal/serial/SerialFabricLifecycle.cpp',
                           'cores/arduino/internal/io_resource_manager.cpp',
                           'cores/arduino/internal/resource/IoResourceTable.cpp'])
            command.extend(['-o', str(binary)])
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
