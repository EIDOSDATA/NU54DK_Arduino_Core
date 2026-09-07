"""! @brief PDM 준비 순서와 실제 연속 DMA helper의 경계·순서 오류를 검사합니다. """
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_signal as signal
import v04_pdm_continuous as continuous
import v04_signal_run as runner
from v04_protocol import ProtocolError


class PdmContinuousTests(unittest.TestCase):
    def test_receiver_gate_precedes_generator_in_both_roles(self):
        for controller_role in (1, 2):
            calls = []
            class Device:
                def __init__(self, role):
                    self.image = {'role': role}
                def command(self, opcode, args=()):
                    calls.append((self.image['role'], opcode))
                    if opcode == 32:
                        return [440, 10000]
                    if opcode == 34 and self.image['role'] == controller_role:
                        if (3 - controller_role, 34) not in calls:
                            raise ProtocolError('CSn idle HIGH not prepared')
                    return [0]
            devices = [Device(1), Device(2)]
            with patch.object(signal, 'wait_status', return_value=[1, 1, 1, 1, 0, 256, 256, 0]), patch.object(signal, 'read_u16', return_value=[-1000] * 256):
                signal.run_case(devices, {'family': 'pdm', 'id': 440}, controller_role,
                                (20, 256, 25, 0, 0, 1), lambda *args: None)
            self.assertEqual([role for role, op in calls if op == 34], [3 - controller_role, controller_role])
            self.assertEqual(calls[-2:], [(1, 33), (2, 33)])

    def test_continuous_oracle_rejects_truncation_swaps_and_malformed_stats(self):
        def packed(value):
            return (value & 65535) * 65537
        records = [[i, i % 4, 256, 128 * 123, (-128 * 234) & 0xFFFFFFFF,
                    packed(123), packed(-234), 1] for i in range(104)]
        vector = (20, 256, 25, 1, 0)
        self.assertEqual(continuous.received(records, vector)['measured_channel_means'], [123, -234])
        for field, value in ((0, 9), (1, 7), (2, 255), (3, 99999999), (5, packed(-321))):
            bad = [row[:] for row in records]
            bad[5][field] = value
            with self.assertRaises(ProtocolError):
                continuous.received(bad, vector)
        with self.assertRaises(ProtocolError):
            continuous.received(records[:-1], vector)
        with self.assertRaises(ProtocolError):
            continuous.received(records, (20, 256, 25, 1, 1))
        for row in records[:4]:
            row[3], row[4], row[5], row[6] = row[4], row[3], row[6], row[5]
        self.assertEqual(continuous.received(records, vector)['measured_channel_means'], [123, -234])

    def test_continuous_mode_requires_pdm_fixture(self):
        with self.assertRaises(ProtocolError):
            runner.arguments(['--dut', 'a', '--peer', 'b', '--build-root', '.', '--pyocd', '.',
                              '--fixture', '430', '--pdm-continuous'])

    def test_native_rotation_guard_and_ownership(self):
        source = r'''
#include "pdm_continuous.h"
#include <cassert>
int main()
{
    v04::PdmContinuous plan;
    plan.reset(256, true);
    std::int16_t *buffers[4]{};
    for (unsigned i = 0; i < 2; ++i)
    {
        buffers[i] = plan.next();
        assert(buffers[i] != nullptr);
        plan.queued();
    }
    assert(!plan.released(buffers[1], 256));
    assert(!plan.released(buffers[0], 255));
    assert(plan.record(0) == nullptr);
    for (unsigned i = 0; i < 104; ++i)
    {
        auto *next = plan.next();
        assert(next != nullptr);
        buffers[(i + 2) % 4] = next;
        plan.queued();
        auto *current = buffers[i % 4];
        for (unsigned j = 0; j < 256; ++j)
        {
            current[j] = j % 2 == 0 ? 123 : -234;
        }
        assert(plan.released(current, 256));
        assert(!plan.released(current, 256));
        const auto *record = plan.record(i);
        assert(record != nullptr && record[0] == i && record[1] == i % 4);
        assert(record[3] == 15744 && static_cast<std::int32_t>(record[4]) == -29952);
    }
    assert(plan.complete() && plan.guards() && plan.next() == nullptr);
    plan.reset(256, false);
    auto *buffer = plan.next();
    plan.queued();
    buffer[256] = 0;
    assert(!plan.guards() && !plan.released(buffer, 256) && plan.next() == nullptr);
    plan.reset(1024, false);
    for (unsigned i = 0; i < 4; ++i)
    {
        assert(plan.next() != nullptr);
        plan.queued();
    }
    assert(plan.next() == nullptr);
}
'''
        with tempfile.TemporaryDirectory() as folder:
            path, executable = Path(folder) / 'continuous.cpp', Path(folder) / 'continuous.exe'
            path.write_text(source, encoding='utf-8')
            result = subprocess.run(compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'tests/zephyr/v04_pair_hil/src'), str(path), '-o', str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
