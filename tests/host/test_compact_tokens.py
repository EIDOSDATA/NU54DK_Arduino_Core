"""! @brief 기존 lease 경로와 compact token의 상태·오류·세대를 실제 C++로 대조합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest
from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]


class CompactTokenTests(unittest.TestCase):
    def test_transactions_match_prior_lease_algorithm(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'tokens.exe'
            command = compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-DCONFIG_ZTEST=1', '-DCONFIG_NUCODE_ARDUINO_IO_RESOURCE_SLOTS=8']
            for folder in ('tests/host/route_stubs', 'tests/host/serial_driver_stubs',
                           'tests/host/serial_fabric_stubs', 'cores/arduino'):
                command.extend(['-I', str(ROOT / folder)])
            command.extend([str(ROOT / 'tests/host/compact_tokens_main.cpp'),
                str(ROOT / 'cores/arduino/internal/resource/IoResourceTable.cpp'), '-o', str(binary)])
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            result = subprocess.run([str(binary)], capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
