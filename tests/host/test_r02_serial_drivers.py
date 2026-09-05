"""! @brief production Serial adapter와 수명주기를 fake nrfx 및 실제 thread로 검증합니다. """
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SerialDriverTests(unittest.TestCase):
    def test_production_sync_and_lifetime(self):
        compiler = shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r02-') as temporary:
            for personality in ('SPIM', 'TWIM'):
                binary = Path(temporary) / (personality + '.exe')
                command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                           '-DTEST_' + personality, '-I', str(ROOT/'tests/host/serial_driver_stubs'),
                           '-I', str(ROOT/'tests/host/serial_fabric_stubs'), '-I', str(ROOT/'cores/arduino'),
                           '-I', str(ROOT/'variants/nu54dk'), str(ROOT/'cores/arduino/SerialFabric.cpp'),
                           str(ROOT/'tests/host/r02_serial_driver_main.cpp'), '-o', str(binary)]
                result = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                for scenario in ('stale', 'consumer', 'overflow', 'deadline', 'stop_failure', 'submit_deactivate',
                                 'reservation', 'errors', 'generation_wrap', 'late_stop', 'wait_deactivate', 'other_thread'):
                    with self.subTest(personality=personality, scenario=scenario):
                        result = subprocess.run([str(binary), scenario], capture_output=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
