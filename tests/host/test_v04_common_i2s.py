"""! @brief 연속 I2S의 DMA 전체 CRC와 device sample oracle을 교차 검증합니다. """
import copy
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_common_i2s as i2s
from v04_protocol import ProtocolError


class CommonI2sTests(unittest.TestCase):
    def test_continuous_crc_order_padding_and_direction_failures(self):
        self.assertEqual(len(list(i2s.vectors())), 432)
        for width in (8, 16, 24, 32):
            for channels in (0, 1, 2):
                vector = (1, 16000, width, channels, 32, 2)
                packed = 32 // width if width <= 16 else 1
                frame = 2 if channels == 0 else 1
                padding = 3 * frame
                status = [1, 1, 105, 107, 104, 0, 1, padding, 1, 0,
                          104 * 32 * packed - padding, 0, 30, 16000, width, channels, 32, 12, 0, 1]
                rows = []
                for index in range(104):
                    words = i2s.expected_words(i2s.SEED ^ 0x5A5A5A5A, width, 32, index, padding)
                    rows.append([index, round((index + 1) * 32 * packed * 1e6 / (16000 * frame)),
                                 zlib.crc32(struct.pack('<32I', *words)), words[0], words[-1]])
                self.assertEqual(i2s.verify(vector, 1, status, rows)['measured_buffers'], 100)
                for field, value in ((2, 103), (5, 1), (6, 0), (7, 9 * frame), (8, 0),
                                     (10, status[10] - 1), (11, 1), (17, 28), (18, 1)):
                    bad = status.copy()
                    bad[field] = value
                    with self.assertRaises(ProtocolError):
                        i2s.verify(vector, 1, bad, rows)
                for row, field in ((50, 0), (50, 2), (50, 3), (50, 4), (103, 1)):
                    bad = copy.deepcopy(rows)
                    bad[row][field] = 0
                    with self.assertRaises(ProtocolError):
                        i2s.verify(vector, 1, status, bad)

    def test_cpp_sample_oracle_against_python_crc_and_corruption(self):
        source = r'''
#include "i2s_stream_oracle.h"
#include <iostream>
int main()
{
    unsigned seed, width, channels, count;
    while (std::cin >> seed >> width >> channels >> count)
    {
        v04::I2sStreamOracle oracle;
        oracle.reset(seed, width, channels);
        std::uint32_t crc = UINT32_MAX;
        for (unsigned index = 0; index < count; ++index)
        {
            std::uint32_t word;
            std::cin >> word;
            oracle.consume(word);
            crc = v04::i2sCrcWord(crc, word);
        }
        std::cout << oracle.padding << ' ' << oracle.samples << ' '
                  << oracle.mismatches << ' ' << (crc ^ UINT32_MAX) << '\n';
    }
}
'''
        inputs, expected = [], []
        for seed in (i2s.SEED, i2s.SEED ^ 0x5A5A5A5A):
            for width in (8, 16, 24, 32):
                for channels in (0, 1, 2):
                    packed = 32 // width if width <= 16 else 1
                    frame = 2 if channels == 0 else 1
                    self.assertNotEqual(i2s.pattern(seed, 0) & ((1 << width) - 1), 0)
                    words = sum((i2s.expected_words(seed, width, 32, index, 3 * frame) for index in range(5)), [])
                    for corrupt in (False, True):
                        values = words.copy()
                        if corrupt:
                            values[70] ^= 1
                        inputs.append(' '.join(map(str, (seed, width, channels, len(values), *values))))
                        expected.append([3 * frame, len(values) * packed - 3 * frame, int(corrupt),
                                         zlib.crc32(struct.pack('<' + 'I' * len(values), *values))])
        with tempfile.TemporaryDirectory() as directory:
            path, exe = Path(directory) / 'oracle.cpp', Path(directory) / 'oracle.exe'
            path.write_text(source, encoding='utf-8')
            compiled = subprocess.run(compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'tests/zephyr/v04_pair_hil/src'), str(path), '-o', str(exe)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], input='\n'.join(inputs) + '\n',
                                      capture_output=True, text=True, timeout=20)
            self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
            self.assertEqual([list(map(int, line.split())) for line in executed.stdout.splitlines()], expected)
