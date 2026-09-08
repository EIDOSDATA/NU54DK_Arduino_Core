"""! @brief 실제 반환·요청 없는 RX 지연, 잘못된 시간과 복구 누락을 거부합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_rx_delay as delay
import v04_t13_run as runner
from v04_protocol import ProtocolError


class RxDelayTests(unittest.TestCase):
    def setUp(self):
        self.test = next(row for row in cases.cases() if row['id'] == 3)

    def vector(self, role, stopped=False):
        return ([1, 21, 1, 2, 100000, 110000, 112010, 10, 12, 14, 12, 0, 0, 1, 1, 26, 26, 28, 1000000, int(stopped)]
                if role == 1 else
                [2, 21, 1, 0, 100000, 0, 0, 10, 0, 0, 12, delay.MASK, 0, 0, 0, 26, 26, 28, 1000000, int(stopped)])

    def test_only_standalone_s_uart_uses_original_tx_rx_with_hardware_flow_removed(self):
        for test in cases.cases():
            for role in (1, 2):
                if test['id'] not in (2, 3, 4, 5):
                    with self.assertRaises(ProtocolError):
                        delay.fixture(test, role)
                    continue
                changed = delay.fixture(test, role)
                for side in ('a', 'b'):
                    self.assertEqual(changed['serial_links'][0][side]['pins'], {
                        key: value for key, value in test['serial_links'][0][side]['pins'].items() if key in ('txd', 'rxd')})
                    self.assertEqual(len(test['serial_links'][0][side]['pins']), 4)
                self.assertEqual(changed['_rx_supply_delay']['hold_us'], 2000)

    def test_actual_return_request_delay_guards_and_later_completion_are_all_required(self):
        for role in (1, 2):
            words = self.vector(role)
            delay.inspect(words, self.test, 1, role)
            mutations = [(0, 0), (1, 20), (2, 0), (3, 1), (15, 10), (16, 0), (18, 128000000), (19, 1)]
            mutations += ([(5, 90000), (6, 110001), (6, 116000), (8, 10), (9, 12),
                           (11, 1), (12, 1), (13, 0), (14, 0), (15, 12), (17, 13)] if role == 1 else
                          [(5, 1), (6, 1), (8, 1), (9, 1), (11, 0), (12, 1), (13, 1), (14, 1), (17, 11)])
            for index, value in mutations:
                broken = words[:]
                broken[index] = value
                with self.subTest(role=role, index=index), self.assertRaises(ProtocolError):
                    delay.inspect(broken, self.test, 1, role)

    def test_both_raws_precede_failure_and_failed_delay_cannot_reacquire_or_pass(self):
        devices = [mock.Mock(), mock.Mock()]
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            device.command.side_effect = lambda opcode, *args, role=role, **kwargs: self.vector(role) if opcode == 162 else [1]
        rows = []
        def group(*args, **kwargs):
            kwargs['during']()
        with mock.patch.object(runner, 'execute_group', side_effect=group) as grouped, \
             mock.patch.object(delay.time, 'sleep'), \
             mock.patch.object(delay, 'inspect', side_effect=ProtocolError('missing actual delay')):
            with self.assertRaises(ProtocolError):
                delay.execute(devices, self.test, 1, mock.Mock(), lambda name, row: rows.append((name, row)), preflight=True)
        self.assertEqual(grouped.call_count, 1)
        self.assertTrue(any(name.endswith('/role1/raw') for name, _ in rows))
        self.assertTrue(any(name.endswith('/role2/raw') for name, _ in rows))
        self.assertFalse(any(row.get('planned_rx_delay_pass') for _, row in rows))
        for device in devices:
            self.assertFalse(any(call.args == (160, (0,)) for call in device.command.call_args_list))

    def test_stop_proof_and_policy_clear_precede_fresh_four_wire_restart(self):
        devices = [mock.Mock(), mock.Mock()]
        finished = False
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            device.command.side_effect = lambda opcode, *args, role=role, **kwargs: self.vector(role, finished) if opcode == 162 else [1]
        def group(*args, **kwargs):
            nonlocal finished
            if kwargs.get('during'):
                kwargs['during']()
                finished = True
            else:
                for device in devices:
                    self.assertEqual(device.command.call_args.args, (160, (0,)))
                self.assertEqual(args[1]['test'], self.test)
        rows = []
        with mock.patch.object(runner, 'execute_group', side_effect=group) as grouped, mock.patch.object(delay.time, 'sleep'):
            delay.execute(devices, self.test, 1, mock.Mock(), lambda name, row: rows.append(row), preflight=True)
        first, last = grouped.call_args_list
        self.assertEqual(first.kwargs['seed'] ^ 0x9E3779B9, last.kwargs['seed'])
        self.assertFalse(rows[-1]['planned_rx_delay_pass'])


if __name__ == '__main__':
    unittest.main()
