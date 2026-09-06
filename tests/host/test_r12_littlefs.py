"""! @brief 실제 FS/File/mount를 링크하고 fake image의 별도 process 재시작을 검사합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]


class LittleFsPersistenceTests(unittest.TestCase):
    def test_production_littlefs_lifecycle(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r12-littlefs-') as folder:
            folder = Path(folder)
            binary = folder / 'littlefs.exe'
            command = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-I', str(ROOT / 'tests/host/storage_stubs'),
                       '-I', str(ROOT / 'libraries/LittleFS/src'),
                       str(ROOT / 'libraries/LittleFS/src/FS.cpp'),
                       str(ROOT / 'libraries/LittleFS/src/internal/FilePaths.cpp'),
                       str(ROOT / 'libraries/LittleFS/src/internal/FileSlots.cpp'),
                       str(ROOT / 'libraries/LittleFS/src/internal/File.cpp'),
                       str(ROOT / 'libraries/LittleFS/src/LittleFS.cpp'),
                       str(ROOT / 'tests/host/r12_littlefs_main.cpp'), '-o', str(binary)]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            image = folder / 'fake-filesystem.bin'
            for scenario in ['write', 'read', 'mount_failure', 'open_failure', 'io_failure',
                             'busy_mount', 'path_mode', 'read', 'format_retry']:
                with self.subTest(scenario=scenario):
                    before = image.read_bytes() if image.exists() else None
                    result = subprocess.run([str(binary), scenario, str(image)], capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    if scenario not in ['write', 'format_retry']:
                        self.assertEqual(image.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
