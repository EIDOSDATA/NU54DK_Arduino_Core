"""! @brief 실제 장치 없이 PWM raw capture 판정의 거짓 PASS 경계를 검증합니다. """
import copy
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from host_compiler import compiler_command

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hil/nu54dk"))
import v04_pwm_capture as capture
import v04_signal_run as runner
from v04_protocol import ProtocolError


def observation(top=1000, duty=25, first_high=True):
    """! @brief 펌웨어 decoder와 공유하지 않는 독립 시각 표본입니다. """
    edges = []
    high = top * duty // 100
    for index in range(101):
        base = 100 + index * top
        edges.append([base, int(first_high)])
        if index < 100:
            edges.append([base + (high if first_high else top - high), int(not first_high)])
    status = [1, 1, 1, 0, 201, 0, 1, top * 101, 0, 0, 0, 1]
    return status, edges


class PwmCaptureTests(unittest.TestCase):
    def test_explicit_load_sweeps_and_waveform_top_lane(self):
        """! @brief 네 load의 독립 cardinality와 3개 길이·미구현 slot을 검사합니다. """
        for name, load in (('common', 0), ('grouped', 1), ('individual', 2), ('wave-form', 3)):
            values = list(capture.vectors(name))
            self.assertEqual(len(values), 540 if name == 'wave-form' else 720)
            self.assertEqual(len(set(values)), len(values))
            self.assertEqual({row[6] for row in values}, {4, 32, 256})
            self.assertTrue(all(row[5] == load and capture.valid_vector(row) for row in values))
            for vector in values:
                if vector[3] in (0, 100):
                    level = int(vector[3] == 100)
                    status = [1, 1, 1, 0, 0, level, level, vector[2] * 100, 0, 0, 0, 1]
                    capture.received(vector, status, [])
                else:
                    status, edges = observation(vector[2], vector[3])
                    capture.received(vector, status, edges)
        for vector in ((20, 3, 1000, 25, 1, 3, 4), (20, 0, 1000, 25, 1, 4, 4),
                       (20, 0, 1000, 25, 1, 0, 8), (True, 0, 1000, 25, 1)):
            self.assertFalse(capture.valid_vector(vector))

    def test_actual_cpp_decoder_layouts_compile_time(self):
        """! @brief target이 사용하는 helper를 독립 상수 배열의 static_assert로 컴파일합니다. """
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(root / 'tests/zephyr/v04_pair_hil/src'), '-c',
                str(root / 'tests/host/v04_pwm_capture_vector_main.cpp'),
                '-o', str(Path(folder) / 'vector.o')], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_long_sequence_wait_is_bounded_and_preserves_failed_raw(self):
        """! @brief 첫 긴 DMA 완료 대기와 timeout의 raw/STOP 보존을 함께 검사합니다. """
        class Device:
            def __init__(self, role, progresses):
                self.image = {'role': role}
                self.polls = 0
                self.progresses = progresses
            def command(self, opcode, values=(), **kwargs):
                if opcode == 40:
                    return [408, 10000]
                if opcode == 45:
                    return [0, 1, 1]
                if opcode == 46:
                    if self.image['role'] == 1:
                        return [1, 1, 1, 0, 0, 0, 0, 400000, 0, 0, 0, 1]
                    self.polls += 1
                    return [1, 1, 0, 0, 0, 0, 0, 0, int(self.progresses and self.polls >= 3), 0, 0, 1]
                return [0]
        for progresses in (True, False):
            rows = []
            devices = [Device(1, progresses), Device(2, progresses)]
            with patch.object(capture.time, 'sleep'), patch.object(capture.time, 'monotonic',
                    side_effect=[0, 0.01, 0.02, 3]):
                if progresses:
                    capture.run_case(devices, (20, 0, 4000, 0, 1, 0, 256), lambda key, value: rows.append(value))
                    self.assertEqual(devices[1].polls, 3)
                else:
                    with self.assertRaises(ProtocolError):
                        capture.run_case(devices, (20, 0, 4000, 0, 1, 0, 256), lambda key, value: rows.append(value))
            self.assertEqual(rows[0]['status'], 'observation')
            self.assertEqual(rows[-1]['status'], 'cleanup')

    def test_all_slots_tops_duties_and_polarities_are_explicit(self):
        values = list(capture.vectors())
        self.assertEqual(len(values), 240)
        self.assertEqual(len(set(values)), 240)
        for vector in values:
            if vector[3] in (0, 100):
                level = int(vector[3] == 100)
                status = [1, 1, 1, 0, 0, level, level, vector[2] * 100, 0, 0, 0, 1]
                self.assertEqual(capture.received(vector, status, [])['static_level'], level)
            else:
                for first_high in (True, False):
                    status, edges = observation(vector[2], vector[3], first_high)
                    self.assertEqual(capture.received(vector, status, edges)['periods'], 100)

    def test_each_period_and_relative_duty_are_checked(self):
        vector = (20, 0, 1000, 25, 1)
        status, edges = observation()
        for offset in (13, -13, 100, -100):
            bad = copy.deepcopy(edges)
            bad[51][0] += offset
            with self.assertRaises(ProtocolError):
                capture.received(vector, status, bad)
        for offset in (12, -12):
            good = copy.deepcopy(edges)
            good[51][0] += offset
            capture.received(vector, status, good)
        for frequency in (949, 1051):
            other_status, other_edges = observation(frequency)
            with self.assertRaises(ProtocolError):
                capture.received(vector, other_status, other_edges)

    def test_missing_duplicate_reversed_edge_and_wrong_level_fail(self):
        status, edges = observation()
        for mutation in ('drop', 'duplicate', 'reverse', 'level', 'negative', 'bool'):
            bad = copy.deepcopy(edges)
            if mutation == 'drop':
                bad.pop(75)
            elif mutation == 'duplicate':
                bad[75] = bad[74][:]
            elif mutation == 'reverse':
                bad[74], bad[75] = bad[75], bad[74]
            elif mutation == 'level':
                bad[75][1] = bad[74][1]
            elif mutation == 'negative':
                bad[75][0] = -1
            else:
                bad[75][1] = True
            with self.assertRaises(ProtocolError):
                capture.received((20, 0, 1000, 25, 1), status, bad)

    def test_incomplete_fault_guard_and_static_glitch_fail(self):
        status, edges = observation()
        for field, value in ((0, 0), (1, 0), (2, 0), (3, 1), (4, 0), (7, 0), (11, 0)):
            bad = status[:]
            bad[field] = value
            with self.assertRaises(ProtocolError):
                capture.received((20, 0, 1000, 25, 1), bad, edges)
        static = [1, 1, 1, 0, 0, 1, 1, 100000, 0, 0, 0, 1]
        for field, value in ((4, 1), (5, 0), (6, 0), (7, 99999)):
            bad = static[:]
            bad[field] = value
            with self.assertRaises(ProtocolError):
                capture.received((22, 3, 1000, 100, 0), bad, [])

    def test_cli_is_preflight_only_and_requires_408_10mhz(self):
        base = ['--dut', 'a', '--peer', 'b', '--build-root', '.', '--pyocd', 'fake',
                '--fixture', '408', '--pwm-capture', '--swd-frequency-hz', '10000000']
        self.assertFalse(runner.arguments(base).execute_fixture)
        self.assertFalse(runner.arguments(base).cmsis_dap_limit_packets)
        limited = runner.arguments(base + ['--cmsis-dap-limit-packets'])
        self.assertTrue(limited.cmsis_dap_limit_packets)
        self.assertFalse(limited.execute_fixture)
        self.assertEqual(limited.swd_frequency_hz, 10000000)
        self.assertEqual(runner.arguments(base + ['--pwm-load', 'wave-form']).pwm_load, 'wave-form')
        with self.assertRaises(ProtocolError):
            runner.arguments([word for word in base if word != '--pwm-capture'] + ['--pwm-load', 'common'])
        for extra in (['--fixture', '401'], ['--swd-frequency-hz', '1000000'],
                      ['--duration-seconds', '600'], ['--pdm-continuous'], ['--execute-fixture']):
            with self.assertRaises(ProtocolError):
                runner.arguments(base + extra)

    def test_cleanup_stops_generator_first_and_preserves_capture_failure(self):
        calls = []
        class Device:
            def __init__(self, role):
                self.image = {'role': role}
            def command(self, opcode, args=(), **kwargs):
                calls.append((self.image['role'], opcode))
                if opcode == 40:
                    return [408, 10000]
                if opcode == 43:
                    raise ProtocolError('capture timeout')
                return [0, 1, 1] if opcode == 45 else [0]
        with self.assertRaisesRegex(ProtocolError, 'capture timeout'):
            capture.run_case([Device(1), Device(2)], (20, 0, 1000, 25, 1), lambda *args: None)
        self.assertEqual(calls[-2:], [(2, 45), (1, 45)])

    def test_partial_capture_is_journaled_before_failure_and_cleanup(self):
        records = []
        class Device:
            def __init__(self, role):
                self.image = {'role': role}
            def command(self, opcode, args=(), **kwargs):
                if opcode == 40:
                    return [408, 10000]
                if opcode == 43:
                    return [1]
                if opcode == 46:
                    return [1, 1, 0, 1, 1, 0, 1, 125000, 0, 0, 0, 1]
                if opcode == 44:
                    return [123, 1]
                return [0, 1, 1] if opcode == 45 else [0]
        with self.assertRaisesRegex(ProtocolError, 'partial raw preserved'):
            capture.run_case([Device(1), Device(2)], (20, 0, 1000, 25, 1),
                             lambda key, result: records.append((key, result)))
        self.assertEqual([item[1]['status'] for item in records], ['observation', 'cleanup'])
        self.assertEqual(records[0][1]['edges'], [[123, 1]])


if __name__ == '__main__':
    unittest.main()
