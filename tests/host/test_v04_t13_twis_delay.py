"""! @brief 실제 요청·SCL·지연·STOP 근거 없는 TWIS 통과를 거부합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_twis_delay as delay
import v04_t13_run as runner
from v04_protocol import ProtocolError


class TwisDelayTests(unittest.TestCase):
    def setUp(self):
        self.test = next(row for row in cases.cases() if row['id'] == 17)

    def vector(self, role, stopped=False):
        return ([1, 21, 1, 0]+[0]*8+[delay.MASK, 0, 0, 0, 26, 26, 1000000, int(stopped)]
                if role == 1 else
                [2, 21, 1, 2, 100000, 102010, 1, 1, 0, 0, 0, 50, 0, 0, 1, 1, 26, 26, 1000000, int(stopped)])

    def test_only_original_twim20_21_22_30_with_b_target_is_selected(self):
        for test in cases.cases():
            if test['id'] in (16, 17, 18, 19):
                changed = delay.fixture(test)
                self.assertEqual(changed['serial_links'], test['serial_links'])
                self.assertEqual(changed['_twis_supply_delay']['write_request_hold_us'], 2000)
            else:
                with self.assertRaises(ProtocolError):
                    delay.fixture(test)

    def test_missing_request_low_delay_guard_and_progress_each_fail(self):
        for role in (1, 2):
            words = self.vector(role)
            delay.inspect(words, self.test, role)
            mutations = [(0, 0), (1, 20), (2, 0), (3, 1), (16, 0), (17, 0), (18, 128000000), (19, 1)]
            mutations += ([(4, 1), (12, 0)] if role == 1 else
                          [(5, 100001), (5, 106000), (6, 0), (7, 0), (8, 1), (9, 1),
                           (10, 1), (11, 1), (12, 1), (13, 1), (14, 0), (15, 0)])
            for index, value in mutations:
                broken = words[:]
                broken[index] = value
                with self.subTest(role=role, index=index), self.assertRaises(ProtocolError):
                    delay.inspect(broken, self.test, role)

    def devices(self, finished):
        devices = [mock.Mock(), mock.Mock()]
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            device.command.side_effect = lambda opcode, *args, role=role, **kwargs: self.vector(role, finished()) if opcode == 181 else [1]
        return devices

    def test_both_raws_are_saved_before_failed_observation_and_no_restart(self):
        devices = self.devices(lambda: False)
        rows = []
        def group(*args, **kwargs):
            kwargs['during']()
        with mock.patch.object(runner, 'execute_group', side_effect=group) as grouped, \
             mock.patch.object(delay, 'inspect', side_effect=ProtocolError('missing SCL LOW')):
            with self.assertRaises(ProtocolError):
                delay.execute(devices, self.test, mock.Mock(), lambda name, row: rows.append((name, row)), preflight=True)
        self.assertEqual(grouped.call_count, 1)
        for role in (1, 2):
            self.assertTrue(any(name.endswith(f'/role{role}/raw') for name, _ in rows))
        self.assertFalse(any(row.get('planned_twis_delay_pass') for _, row in rows))

    def test_stop_and_policy_clear_precede_new_seed_reacquisition(self):
        finished = False
        devices = self.devices(lambda: finished)
        def group(*args, **kwargs):
            nonlocal finished
            if kwargs.get('during'):
                kwargs['during']()
                finished = True
            else:
                for device in devices:
                    self.assertEqual(device.command.call_args.args, (180, (0,)))
                self.assertEqual(args[1]['test'], self.test)
        rows = []
        with mock.patch.object(runner, 'execute_group', side_effect=group) as grouped:
            delay.execute(devices, self.test, mock.Mock(), lambda name, row: rows.append(row), preflight=True)
        first, last = grouped.call_args_list
        self.assertEqual(first.kwargs['seed'] ^ 0x9E3779B9, last.kwargs['seed'])
        self.assertFalse(rows[-1]['planned_twis_delay_pass'])


if __name__ == '__main__':
    unittest.main()
