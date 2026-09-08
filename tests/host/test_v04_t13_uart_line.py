"""! @brief 실제 오류 없는 성공·잘못된 break 핀/시간·STOP 누락을 거부합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_oracle as oracle
import v04_t13_uart_line as line
import v04_t13_run as runner
from v04_protocol import ProtocolError


class UartLineTests(unittest.TestCase):
    def setUp(self):
        self.test = next(row for row in cases.cases() if row['id'] == 3)

    def vector(self, role=1, mode='parity'):
        target = role == 1
        policy = (1 if target else 2) if mode == 'parity' else (3 if target else 4)
        return [policy, 21, 1, 1, 5 if target else line.MASK, 2 if target and mode == 'parity' else 4 if target else 0,
                0, 0, int(target), 1000, 120000 if target else 0, 0 if target else 110000,
                111000 if policy == 4 else 0, 7 if policy == 4 else 0, int(policy == 4),
                3 if policy == 1 else 1, 36, 37, 1000000, 1]

    def lane(self, mode='parity'):
        return [25, 2 if mode == 'parity' else 4, 0] + [0]*16 + [20]

    def test_only_fixed_s_uart_and_deterministic_first_byte_parity(self):
        for test in cases.cases():
            for role in (1, 2):
                if test['id'] in (2, 3, 4, 5):
                    line.validate_selection(test, role, 'break')
                else:
                    with self.assertRaises(ProtocolError):
                        line.validate_selection(test, role, 'break')
        for role in (1, 2):
            for seed in (0, 1, 255, 0xFFFFFFFF, 0x12345678):
                selected = line.seed_for_parity(seed, role)
                self.assertEqual(oracle.pattern(oracle.lane_seed(selected, 0, role), 0).bit_count() % 2, 0)

    def test_missing_error_config_time_guard_or_release_cannot_pass(self):
        for mode in ('parity', 'break'):
            for role in (1, 2):
                valid = self.vector(role, mode)
                line.inspect(valid, self.test, 1, role, mode, lane=self.lane(mode))
                mutations = [(0, 0), (1, 22), (2, 0), (3, 0), (15, 0), (16, 46), (17, 46), (18, 128000000), (19, 0)]
                if role == 1:
                    mutations += [(4, 2), (5, 0), (5, 1), (8, 0), (10, 1000), (10, 3000000), (11, 1)]
                elif mode == 'break':
                    mutations += [(4, 5), (11, 1000), (12, 110999), (12, 120000), (13, 3), (14, 0)]
                else:
                    mutations += [(4, 5), (11, 1000), (13, 7)]
                for index, value in mutations:
                    broken = valid[:]
                    broken[index] = value
                    with self.subTest(mode=mode, role=role, index=index), self.assertRaises(ProtocolError):
                        line.inspect(broken, self.test, 1, role, mode, lane=self.lane(mode))
        wrong_lane = self.lane()
        wrong_lane[0] = 0
        with self.assertRaises(ProtocolError):
            line.inspect(self.vector(), self.test, 1, 1, 'parity', lane=wrong_lane)

    def test_break_reports_framing_and_break_flags_separately(self):
        for mask in (4, 8, 12):
            words, lane = self.vector(mode='break'), self.lane('break')
            words[5] = lane[1] = mask
            measured = line.inspect(words, self.test, 1, 1, 'break', lane=lane)
            self.assertEqual(measured['break_flag_observed'], bool(mask & 8))
            self.assertFalse(measured['normal_soak_pass'])

    def test_contiguous_8n1_stimulus_can_violate_both_parity_and_8e1_stop(self):
        """! @brief 실제 wire bit 위치를 별도로 구성하여8N1/8E1의 두 오류 가능성을 대조합니다. """
        for role in (1, 2):
            for seed in (0, 255, 0xFFFFFFFF):
                selected = line.seed_for_parity(seed, role)
                byte = oracle.pattern(oracle.lane_seed(selected, 0, role), 0)
                wire = [0] + [(byte >> bit) & 1 for bit in range(8)] + [1, 0]
                expected_parity = sum(wire[1:9]) % 2
                mask = (2 if wire[9] != expected_parity else 0) | (4 if wire[10] != 1 else 0)
                self.assertEqual(mask, 6)

    def test_parity_requires_parity_bit_and_rejects_overrun_break_and_unknown_errors(self):
        words, lane = self.vector(), self.lane()
        for mask in (2, 6):
            words[5] = lane[1] = mask
            result = line.inspect(words, self.test, 1, 1, 'parity', lane=lane)
            self.assertTrue(result['parity_observed'])
            self.assertEqual(result['framing_observed'], bool(mask & 4))
            self.assertFalse(result['normal_soak_pass'])
        for mask in (0, 1, 3, 4, 7, 8, 10, 12, 14, 16, 0x80000000):
            words[5] = lane[1] = mask
            with self.subTest(mask=mask), self.assertRaises(ProtocolError):
                line.inspect(words, self.test, 1, 1, 'parity', lane=lane)

    def test_compound_parity_error_still_requires_matching_api_mask_and_stop(self):
        words, lane = self.vector(), self.lane()
        words[5], lane[1] = 6, 2
        with self.assertRaises(ProtocolError):
            line.inspect(words, self.test, 1, 1, 'parity', lane=lane)
        lane[1], words[19] = 6, 0
        with self.assertRaises(ProtocolError):
            line.inspect(words, self.test, 1, 1, 'parity', lane=lane)

    def test_clock_or_arm_rejection_never_starts_rx_and_preserves_cleanup(self):
        for bad_clock in (True, False):
            devices = [mock.Mock(), mock.Mock()]
            calls, rows = [], []
            for role, device in enumerate(devices, 1):
                device.image = {'role': role}
                def command(opcode, *args, role=role, **kwargs):
                    calls.append((role, opcode))
                    if opcode == 107:
                        return [1, 1] if bad_clock else [1, 1, 65537]
                    if opcode == 141:
                        return [0]
                    if opcode == 99:
                        return [3, 1, 0, 0, 1, 0]+[0]*10
                    if opcode == 142:
                        return self.vector(role)
                    return [1]
                device.command.side_effect = command
            with mock.patch.object(runner, 'execute_group') as group, \
                 mock.patch.object(runner, 'prepared_uart_pins'), \
                 mock.patch.object(runner, 'stop_pair', return_value=True) as stop, \
                 mock.patch.object(runner, 'idle_pins', return_value=True) as idle:
                with self.assertRaisesRegex(ProtocolError, 'clock failed' if bad_clock else 'ARM failed'):
                    line.execute(devices, self.test, 1, 'parity', mock.Mock(),
                                 lambda name, row: rows.append((name, row)), preflight=True)
                self.assertFalse(any(opcode in (98, 143, 144) for _, opcode in calls))
                self.assertEqual(group.call_count, 1)
                stop.assert_called_once()
                idle.assert_called_once()
                armed = [row for name, row in rows if '/arm/' in name]
                self.assertEqual(armed, [] if bad_clock else [{'status': 'observation', 'words': [0]}])

    def test_expected_fault_still_requires_cleanup_and_fresh_normal_restart(self):
        devices = [mock.Mock(), mock.Mock()]
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            def command(opcode, *args, role=role, **kwargs):
                if opcode == 142:
                    return self.vector(role)
                if opcode == 99:
                    return [3, 0, 0, 0, int(role != 1), 0] + [0]*10
                if opcode == 100:
                    return self.lane() if role == 1 else [0]*19+[20]
                if opcode == 107:
                    return [1, 1, 1]
                return [1]
            device.command.side_effect = command
        for cleanup_ok in (True, False):
            rows = []
            with mock.patch.object(runner, 'execute_group') as group, \
                 mock.patch.object(runner, 'prepared_uart_pins'), \
                 mock.patch.object(runner, 'stop_pair', return_value=cleanup_ok), \
                 mock.patch.object(runner, 'idle_pins', return_value=True), \
                 mock.patch.object(line.time, 'sleep'):
                if cleanup_ok:
                    line.execute(devices, self.test, 1, 'parity', mock.Mock(), lambda name, row: rows.append(row), preflight=True)
                    self.assertEqual(group.call_count, 2)
                    before, after = group.call_args_list
                    self.assertEqual(before.kwargs['seed'] ^ 0x9E3779B9, after.kwargs['seed'])
                    for device in devices:
                        self.assertEqual(device.command.call_args.args, (140, (0,)))
                    self.assertFalse(rows[-1]['planned_uart_line_recovery_pass'])
                else:
                    with self.assertRaises(ProtocolError):
                        line.execute(devices, self.test, 1, 'parity', mock.Mock(), lambda name, row: rows.append(row), preflight=True)
                    self.assertEqual(group.call_count, 1)
                    self.assertFalse(any(row.get('status') == 'passed' for row in rows))

    def test_break_high_precedes_rx_and_preexisting_error_rejects_pulse(self):
        for earlier_error in (False, True):
            devices = [mock.Mock(), mock.Mock()]
            calls = []
            reads = {1: 0, 2: 0}
            for role, device in enumerate(devices, 1):
                device.image = {'role': role}
                def command(opcode, *args, role=role, **kwargs):
                    calls.append((role, opcode))
                    if opcode == 142:
                        reads[role] += 1
                        words = self.vector(role, 'break')
                        if role == 1 and reads[role] == 1 and not earlier_error:
                            words[3], words[4] = 0, line.MASK
                        return words
                    if opcode == 99:
                        return [3, 0, 0, 0, int(role != 1), 0]+[0]*10
                    if opcode == 100:
                        return self.lane('break') if role == 1 else [0]*19+[20]
                    if opcode == 107:
                        return [1, 1, 1]
                    return [1]
                device.command.side_effect = command
            with mock.patch.object(runner, 'execute_group') as group, \
                 mock.patch.object(runner, 'prepared_uart_pins'), \
                 mock.patch.object(runner, 'stop_pair', return_value=True) as stop, \
                 mock.patch.object(runner, 'idle_pins', return_value=True), \
                 mock.patch.object(line.time, 'sleep'):
                if earlier_error:
                    with self.assertRaises(ProtocolError):
                        line.execute(devices, self.test, 1, 'break', mock.Mock(), mock.Mock(), preflight=True)
                    self.assertNotIn((2, 143), calls)
                    self.assertEqual(group.call_count, 1)
                else:
                    line.execute(devices, self.test, 1, 'break', mock.Mock(), mock.Mock(), preflight=True)
                    for first, later in (((2, 98), (2, 144)), ((2, 144), (1, 98)),
                                         ((1, 98), (1, 142)), ((1, 142), (2, 143))):
                        self.assertLess(calls.index(first), calls.index(later))
                    self.assertEqual(group.call_count, 2)
                stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
