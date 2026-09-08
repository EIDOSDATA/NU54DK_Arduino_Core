"""! @brief PWM 미시작 증명 누락·출력 펄스·STOP 실패를 복구 성공으로 오인하지 않게 검사합니다. """
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
from v04_protocol import ProtocolError
import v04_t13_cases as cases
import v04_t13_pwm_recovery as recovery
import v04_t13_run as runner


class PwmRecoveryTests(unittest.TestCase):
    def vector(self, stopped=False):
        stream = [1, int(not stopped), 0, 0, 0, 0, 0, 0] + [0] * 10 + [1, 1]
        return {'proof': [2, 20, 1, 1 if stopped else 2, 0 if stopped else 0x500D2000,
                          int(not stopped), 0, 0, 0, 0, 1, 12345, 1000000],
                'stream1': stream[:], 'stream2': stream[:],
                'pins1': [1, 0, 46] + [0] * 17, 'pins2': [2, 0, 20] + [0] * 17}

    def test_unstarted_state_task_address_no_edges_and_guards_are_required(self):
        for stopped in (False, True):
            self.assertEqual(recovery.inspect_unstarted(self.vector(stopped), 20, stopped=stopped), (12345, 1000000))
        changes = [('proof', index, value) for index, value in
                   ((0, 1), (1, 21), (2, 0), (3, 4), (4, 0), (5, 0), (6, 1), (7, 1), (8, 1), (10, 0), (12, 0))]
        changes += [(f'stream{role}', index, value) for role in (1, 2) for index, value in
                    ((1, 0), (2, 9), (4, 1), (6, 1), (18, 0), (19, 0))]
        changes += [('pins1', 4, 1), ('pins2', 8, 1)]
        for name, index, value in changes:
            broken = self.vector()
            broken[name][index] = value
            with self.subTest(name=name, index=index), self.assertRaises(ProtocolError):
                recovery.inspect_unstarted(broken, 20)
        with self.assertRaises(ProtocolError):
            recovery.inspect_unstarted(self.vector(), 20, stopped=True)

    def test_only_fixed_standalone_normal_wiring_pwm_is_allowed(self):
        for test in cases.cases():
            for mode in (1, 2):
                if test['id'] in (25, 26, 27):
                    recovery.validate_selection(test, mode)
                else:
                    with self.assertRaises(ProtocolError):
                        recovery.validate_selection(test, mode)
        test = copy.deepcopy(next(row for row in cases.cases() if row['id'] == 25))
        test['_pwm_diagnostic_tail'] = 2
        with self.assertRaises(ProtocolError):
            recovery.validate_selection(test, 2)

    def test_failed_unstarted_cleanup_cannot_restart_or_claim_a_completed_repetition(self):
        test = next(row for row in cases.cases() if row['id'] == 25)
        rows = []
        with (mock.patch.object(recovery, 'unstarted', side_effect=ProtocolError('STOP unproven')),
              mock.patch.object(runner, 'execute_group') as restart):
            with self.assertRaises(ProtocolError):
                recovery.execute([], test, 2, mock.Mock(), lambda key, row: rows.append((key, row)), preflight=True)
            restart.assert_not_called()
        self.assertFalse(any(key.endswith('/result') for key, _ in rows))


if __name__ == '__main__':
    unittest.main()
