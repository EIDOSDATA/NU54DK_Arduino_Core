"""! @brief 독립 translation unit의 실제 Analog/Stream data 경계를 검증합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]


class FabricDataTests(unittest.TestCase):
    def test_production_data_and_restarts(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r11-') as folder:
            binary = Path(folder) / 'data.exe'
            args = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-DCONFIG_SERIAL=0', '-DTEST_UART_STATUS=0']
            for directory in ['tests/host/fabric_driver_stubs', 'tests/host/serial_driver_stubs',
                              'tests/host/serial_fabric_stubs', 'cores/arduino']:
                args.extend(['-I', str(ROOT / directory)])
            sources = ['cores/arduino/AnalogFabric.cpp', 'cores/arduino/StreamFabric.cpp',
                       'cores/arduino/internal/analog/SaadcFabric.cpp',
                       'cores/arduino/internal/analog/PwmSequenceFabric.cpp',
                       'cores/arduino/internal/stream/PdmFabric.cpp',
                       'cores/arduino/internal/stream/I2sFabric.cpp',
                       'cores/arduino/internal/stream/QdecFabric.cpp',
                       'tests/host/r11_fabric_data_main.cpp']
            result = subprocess.run(args + [str(ROOT / p) for p in sources] + ['-o', str(binary)],
                                    capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertIn(b'R11_DATA_PASS=5;RESTARTS=10;FRAMES=1000', result.stdout)


if __name__ == '__main__':
    unittest.main()
