"""! @brief 실제 장치 없이 PWM raw capture 판정의 거짓 PASS 경계를 검증합니다. """
import copy
from pathlib import Path
import sys
import unittest

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
