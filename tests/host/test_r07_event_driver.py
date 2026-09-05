"""! @brief production DPPI·registry와 실제 Host thread를 실행합니다. """
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ['lookup', 'invalid', 'capacity', 'disconnect', 'release', 'isr', 'threads']


class EventDriverTests(unittest.TestCase):
    def test_production_dppi_and_registry(self):
        compiler = shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r07-') as directory:
            binary = Path(directory) / 'event.exe'
            command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections']
            for include in ['tests/host/event_fabric_stubs', 'tests/host/fabric_driver_stubs',
                            'tests/host/serial_driver_stubs', 'tests/host/serial_fabric_stubs', 'cores/arduino']:
                command.extend(['-I', str(ROOT / include)])
            command.extend(str(ROOT / path) for path in ['tests/host/r07_event_driver_main.cpp',
                           'tests/host/event_fabric_stubs/unused_instances.cpp',
                           'cores/arduino/EventFabric.cpp', 'cores/arduino/internal/event/EventFabricRegistry.cpp',
                           'cores/arduino/internal/event/DppiFabric.cpp'])
            command.extend(['-o', str(binary)])
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
