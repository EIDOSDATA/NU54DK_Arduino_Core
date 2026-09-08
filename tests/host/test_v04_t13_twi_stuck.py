"""! @brief SDA의 실제 LOW와 복구 원인·복원·종료 없는 가짜 성공을 거부합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_twi_stuck as stuck
import v04_t13_run as runner
from v04_protocol import ProtocolError


class TwiStuckTests(unittest.TestCase):
    def setUp(self):
        self.test = next(row for row in cases.cases() if row['id'] == 16)

    def raw(self, role, stopped=False):
        return ([1, 20, 1, 2, 42, 46, 1000, 1090, 10, stuck.CANCELLED, 0,
                 140000, 140030, 0, 0, 3, 1, 1, 1000000, int(stopped)] if role == 1 else
                [2, 20, 1, 3, 42, 46, 500, 100510, 1, 1, 15, int(not stopped), 1,
                 0, 0, 0, 1, 1, 1000000, int(stopped)])

    def attempts(self):
        return [[index, 1, 1, 0, 0, 0, 0, 0, 0, 42, 46, 15, 15, 1, 1, index, index,
                 10 if index == 0 else 0, stuck.CANCELLED if index == 0 else 0, 1000000]
                for index in (0, 1)]

    def test_scope_is_only_isolated_fixed_twi_with_a_controller(self):
        for test in cases.cases():
            if test['id'] in (16, 17, 18, 19):
                stuck.validate(test)
            else:
                with self.assertRaises(ProtocolError):
                    stuck.validate(test)
        with self.assertRaises(ProtocolError):
            stuck.validate(dict(self.test, _reverse_serial=True))
        p0 = next(row for row in cases.cases() if row['id'] == 19)
        a, b, attempts = self.raw(1), self.raw(2), self.attempts()
        for raw in (a, b):
            raw[1], raw[4], raw[5] = 30, 0, 1
        for meta in attempts:
            meta[9:11] = [0, 1]
        stuck.inspect(a, b, attempts, p0)

    def test_low_duration_actual_errno_and_gpio_dma_restore_are_required(self):
        import copy
        valid = [self.raw(1), self.raw(2), *self.attempts()]
        stuck.inspect(*valid[:2], valid[2:], self.test)
        mutations = {
            0: [(0, 0), (2, 0), (3, 1), (4, 34), (7, 1000), (7, 30000), (8, 0), (9, 0),
                (10, 3), (13, 10), (14, stuck.CANCELLED), (15, 0), (16, 0), (17, 3), (18, 0), (19, 1)],
            1: [(3, 2), (7, 510), (7, 107000), (8, 0), (9, 0), (10, 7), (11, 0), (12, 0),
                (13, 6), (16, 0), (17, 0), (18, 0), (19, 1)],
            2: [(1, 3), (2, 0), (3, 6), (4, 6), (5, 3), (6, 3), (7, 3), (8, 3),
                (11, 7), (12, 7), (13, 0), (14, 0), (15, 1), (16, 1), (17, 0), (18, 0)],
            3: [(1, 3), (2, 3), (3, 6), (4, 6), (11, 0), (12, 0), (13, 0), (14, 0),
                (15, 0), (16, 0), (17, 10), (18, stuck.CANCELLED)]}
        for array, changes in mutations.items():
            for index, value in changes:
                broken = copy.deepcopy(valid)
                broken[array][index] = value
                with self.subTest(array=array, index=index), self.assertRaises(ProtocolError):
                    stuck.inspect(*broken[:2], broken[2:], self.test)

    def devices(self, state):
        devices = [mock.Mock(), mock.Mock()]
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            def command(opcode, args=(), role=role, **kwargs):
                if opcode == 173:
                    return self.raw(role, state['stopped']) if args[0] == 0 else self.attempts()[args[0]-1]
                if opcode == 99:
                    return [16, 1, 0, 0, 1, 0]+[0]*10
                return [1]
            device.command.side_effect = command
        return devices

    def test_failed_expected_recovery_preserves_all_pages_and_cleanup_before_judging(self):
        state = {'stopped': False}
        devices = self.devices(state)
        rows = []
        with mock.patch.object(runner, 'execute_group') as grouped, \
             mock.patch.object(runner, 'stop_pair', return_value=True) as stopped, \
             mock.patch.object(runner, 'idle_pins', return_value=True), \
             mock.patch.object(stuck.time, 'sleep'), \
             mock.patch.object(stuck, 'inspect', side_effect=ProtocolError('wrong original errno')):
            with self.assertRaises(ProtocolError):
                stuck.execute(devices, self.test, mock.Mock(), lambda name, row: rows.append((name, row)), preflight=True)
        self.assertEqual(grouped.call_count, 1)
        stopped.assert_called_once()
        for suffix in ('/role1/page0', '/role1/page1', '/role1/page2', '/role2/page0'):
            self.assertTrue(any(name.endswith(suffix) for name, _ in rows))

    def test_stopped_evidence_and_policy_clear_precede_new_normal_seed(self):
        state = {'stopped': False}
        devices = self.devices(state)
        def stop(*args, **kwargs):
            state['stopped'] = True
            return True
        rows = []
        with mock.patch.object(runner, 'execute_group') as grouped, \
             mock.patch.object(runner, 'stop_pair', side_effect=stop), \
             mock.patch.object(runner, 'idle_pins', return_value=True), mock.patch.object(stuck.time, 'sleep'):
            stuck.execute(devices, self.test, mock.Mock(), lambda name, row: rows.append(row), preflight=True)
        first, last = grouped.call_args_list
        self.assertEqual(first.kwargs['seed'] ^ 0x9E3779B9, last.kwargs['seed'])
        for device in devices:
            self.assertEqual(device.command.call_args.args, (170, (0,)))
        self.assertFalse(rows[-1]['planned_twi_stuck_pass'])


if __name__ == '__main__':
    unittest.main()
