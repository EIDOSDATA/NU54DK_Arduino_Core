"""! @brief 실제 Arduino SPI 구현의 driver·transaction 경계를 실행합니다. """
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ['lifecycle', 'route_fail', 'end_retry', 'settings', 'modes', 'thread',
             'buffer', 'driver', 'mask', 'mask_begin_fail', 'mask_end_retry', 'isr']


class SpiFacadeTests(unittest.TestCase):
    def test_production_spi_facade(self):
        compiler = shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r09-') as directory:
            binary = Path(directory) / 'spi.exe'
            command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread']
            for include in ['tests/host/spi_facade_stubs', 'tests/host/route_stubs',
                            'third_party/ArduinoCore-API', 'cores/arduino', 'variants/nu54dk']:
                command.extend(['-I', str(ROOT / include)])
            command.extend(str(ROOT / path) for path in ['tests/host/r09_spi_facade_main.cpp',
                           'cores/arduino/SPI.cpp', 'cores/arduino/internal/spi/SpiZephyrBackend.cpp'])
            command.extend(['-o', str(binary)])
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
