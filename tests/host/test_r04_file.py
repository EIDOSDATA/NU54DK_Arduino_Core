"""! @brief production File을 실제 thread mutex와 Zephyr FS fake로 검증합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]


class FileLifetimeTests(unittest.TestCase):
    def test_production_file(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r04-') as folder:
            binary = Path(folder) / 'file.exe'
            command = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-I', str(ROOT / 'tests/host/storage_stubs'),
                       '-I', str(ROOT / 'libraries/LittleFS/src'),
                       str(ROOT / 'tests/host/r04_file_main.cpp'), '-o', str(binary)]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in ['value', 'mutex', 'threads', 'stale', 'saturation', 'close_error', 'isr', 'last_threads']:
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
