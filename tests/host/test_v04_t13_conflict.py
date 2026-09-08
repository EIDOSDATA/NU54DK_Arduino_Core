"""! @brief 자원 충돌의 고정 안전 범위·원자적 거부·재획득 판정을 검사합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_plan as plan
import v04_t13_conflict as conflict
import v04_t13_run as runner
from v04_protocol import ProtocolError


class ConflictTests(unittest.TestCase):
    def vector(self, mode, instance=21):
        other = instance if mode == 1 else 22 if instance == 21 else 21
        return [mode, instance, other, 0, 0, 2 if mode == 2 else 8, 0xFFFFFFFF,
                3, 3, 36, 36, 37, 37, 38, 38, 39, 39, 8, 8, 1]

    def test_rejection_result_state_pins_and_guards_must_all_match(self):
        for mode in (1, 2, 3):
            valid = self.vector(mode)
            conflict.inspect(valid, 21, mode)
            for index in range(20):
                broken = valid[:]
                broken[index] ^= 1
                with self.subTest(mode=mode, index=index), self.assertRaises(ProtocolError):
                    conflict.inspect(broken, 21, mode)

    def test_only_approved_p1_uart_is_selected_and_candidate_outputs_face_peer_inputs(self):
        rows = {row['id']: row for row in cases.cases()}
        mapping = plan.harness('S')
        for identifier in (3, 4, 5):
            test = rows[identifier]
            for role in (1, 2):
                for mode in ((1,) if identifier == 5 else (1, 2, 3)):
                    conflict.validate_selection(test, role, mode)
                link = test['serial_links'][0]
                local, peer = (link['a'], link['b']) if role == 1 else (link['b'], link['a'])
                physical = mapping if role == 1 else {value: key for key, value in mapping.items()}
                self.assertEqual(physical[local['pins']['txd']], peer['pins']['rxd'])
                self.assertEqual(physical[local['pins']['rts']], peer['pins']['cts'])
        for identifier in (1, 2, 7, 25, 101):
            with self.assertRaises(ProtocolError):
                conflict.validate_selection(rows[identifier], 1, 1)

    def test_p0_uart30_only_uses_its_own_block_and_bank(self):
        test = next(row for row in cases.cases() if row['id'] == 5)
        self.assertEqual(test['serial_links'][0]['a']['bank'], 'p0_flexible')
        for role in (1, 2):
            conflict.validate_selection(test, role, 1)
            for mode in (2, 3):
                with self.assertRaises(ProtocolError):
                    conflict.validate_selection(test, role, mode)
                with self.assertRaises(ProtocolError):
                    conflict.inspect(self.vector(mode, 30), 30, mode)
        firmware = (ROOT/'tests/zephyr/v04_t13_hil/src/serial.cpp').read_text(encoding='utf-8')
        candidate = firmware[firmware.index('void t13::serialConflict'):firmware.index('void t13::serialBusPins')]
        self.assertIn('static_cast<SerialRouteClass>(lane.endpoint.bank)', candidate)

    def test_only_successful_atomic_rejection_reaches_new_seed_reacquisition(self):
        test = next(row for row in cases.cases() if row['id'] == 3)
        for corrupt in (False, True):
            target = mock.Mock()
            target.image = {'role': 1}
            words = self.vector(1)
            if corrupt:
                words[5] = 0
            target.command.return_value = words
            def run_group(*args, **kwargs):
                if kwargs.get('during'):
                    kwargs['during']()
            rows = []
            with mock.patch.object(runner, 'execute_group', side_effect=run_group) as group:
                run = lambda: conflict.execute([target], test, 1, 1, mock.Mock(),
                    lambda name, row: rows.append((name, row)), preflight=True)
                if corrupt:
                    with self.assertRaises(ProtocolError):
                        run()
                    self.assertEqual(group.call_count, 1)
                    self.assertFalse(any(row['status'] == 'passed' for _, row in rows))
                else:
                    run()
                    self.assertEqual(group.call_count, 2)
                    first, last = group.call_args_list
                    self.assertEqual(first.kwargs['seed'] ^ 0x9E3779B9, last.kwargs['seed'])
                    self.assertFalse(rows[-1][1]['planned_conflict_pass'])


if __name__ == '__main__':
    unittest.main()
