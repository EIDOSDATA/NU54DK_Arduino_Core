"""! @brief production EEPROM과 독립 Python codec oracle로 영속 byte를 검사합니다. """
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]


class EepromPersistenceTests(unittest.TestCase):
    def test_production_eeprom_record_and_restart(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r12-eeprom-') as folder:
            folder = Path(folder)
            binary = folder / 'eeprom.exe'
            command = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-I', str(ROOT / 'tests/host/storage_stubs'),
                       '-I', str(ROOT / 'libraries/EEPROM/src'),
                       str(ROOT / 'libraries/EEPROM/src/EEPROM.cpp'),
                       str(ROOT / 'libraries/EEPROM/src/internal/EEPROMRecord.cpp'),
                       str(ROOT / 'libraries/EEPROM/src/internal/EEPROMSettings.cpp'),
                       str(ROOT / 'tests/host/r12_eeprom_main.cpp'), '-o', str(binary)]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

            def run(scenario, path):
                result = subprocess.run([str(binary), scenario, str(path)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

            def record(payload):
                return struct.pack('<IHHI', 0x45503534, 1, len(payload), zlib.crc32(payload)) + payload

            payload = bytes(range(0xA0, 0xA8))
            path = folder / 'persist.bin'
            run('write', path)
            self.assertEqual(path.read_bytes(), record(payload))
            run('read', path)
            run('resize', path)
            self.assertEqual(path.read_bytes(), record(payload + b'\xff' * 8))
            run('read', path)
            for scenario in ['init_failure', 'load_failure', 'short_load', 'save_failure', 'bounds']:
                with self.subTest(scenario=scenario):
                    path.write_bytes(record(payload))
                    run(scenario, path)
                    if scenario == 'save_failure':
                        self.assertEqual(path.read_bytes(), record(b'\x55' + payload[1:]))
            valid = record(payload)
            corrupted = [b'', valid[:12], valid[:-1], valid + b'\0', b'\0' * 1037]
            for offset in [0, 4, 6, 8, 12]:
                altered = bytearray(valid)
                altered[offset] ^= 0x7F
                corrupted.append(bytes(altered))
            for index, bad_record in enumerate(corrupted):
                with self.subTest(corruption=index):
                    path.write_bytes(bad_record)
                    run('corrupt', path)
                    self.assertEqual(path.read_bytes(), record(b'\xff' * 8))


if __name__ == '__main__':
    unittest.main()
