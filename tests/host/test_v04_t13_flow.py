"""! @brief CTS 지연의 물리 경로·실제 시간·대기 및 재개 판정을 검사합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_plan as plan
import v04_t13_flow as flow
import v04_t13_run as runner
from v04_protocol import ProtocolError


class FlowTests(unittest.TestCase):
    def test_fixed_existing_rts_cts_mapping_and_peer_only_override(self):
        tests = {row['id']: row for row in cases.cases()}
        for identifier in (2, 3, 4, 5):
            original = tests[identifier]
            for role in (1, 2):
                changed = flow.fixture(original, role)
                a, b = original['serial_links'][0]['a'], original['serial_links'][0]['b']
                self.assertEqual(plan.harness('S')[a['pins']['rts']], b['pins']['cts'])
                self.assertEqual(plan.harness('S')[a['pins']['cts']], b['pins']['rts'])
                target_key, peer_key = ('a', 'b') if role == 1 else ('b', 'a')
                self.assertEqual(changed['serial_links'][0][target_key], original['serial_links'][0][target_key])
                self.assertEqual(set(changed['serial_links'][0][peer_key]['pins']), {'txd', 'rxd'})
                self.assertEqual(len(original['serial_links'][0][peer_key]['pins']), 4)
        for identifier in (1, 7, 16, 25, 101):
            with self.assertRaises(ProtocolError):
                flow.fixture(tests[identifier], 1)

    def vector(self, observer=True):
        return ([1, 21, 3, 39, 1000000, 1100000, 1000000, 10, 10, 14, 1, 1, 1, 0, 12,
                 36, 37, 38, 39, 1] if observer else
                [2, 21, 3, 38, 1000000, 1100000, 1000000, 0, 0, 14, 0, 1, 1, 1, 1,
                 36, 37, flow.MASK, flow.MASK, 0])

    def test_interval_requires_actual_high_low_waiting_tx_resume_and_pin_contract(self):
        test = next(row for row in cases.cases() if row['id'] == 3)
        for observer in (True, False):
            valid = self.vector(observer)
            flow.inspect(valid, test, 1, 1 if observer else 2)
            mutations = [(0, 0), (1, 20), (2, 2), (3, 46), (5, 1001000), (5, 1200000),
                         (6, 128000000), (11, 0), (12, 0), (13, int(observer)), (15, 46), (19, int(not observer))]
            mutations += [(8, 15), (9, 10), (10, 0)] if observer else [(7, 1), (8, 1), (10, 1), (14, 0)]
            for index, value in mutations:
                broken = valid[:]
                broken[index] = value
                with self.subTest(observer=observer, index=index), self.assertRaises(ProtocolError):
                    flow.inspect(broken, test, 1, 1 if observer else 2)

    def test_gpio_policy_is_disabled_before_normal_four_wire_reacquisition(self):
        test = next(row for row in cases.cases() if row['id'] == 3)
        devices = [mock.Mock(), mock.Mock()]
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            device.command.side_effect = lambda opcode, *args, role=role, **kwargs: self.vector(role == 1) if opcode == 127 else [1]
        policy_at_reacquire = []
        def execute_group(*args, **kwargs):
            if kwargs.get('during'):
                kwargs['during']()
            else:
                for device in devices:
                    policy_at_reacquire.append(device.command.call_args.args)
        rows = []
        with mock.patch.object(runner, 'execute_group', side_effect=execute_group) as group, mock.patch.object(flow.time, 'sleep'):
            flow.execute(devices, test, 1, mock.Mock(), lambda label, row: rows.append(row), preflight=True)
        self.assertEqual(policy_at_reacquire, [(126, (0,)), (126, (0,))])
        first, last = group.call_args_list
        self.assertEqual(first.kwargs['seed'] ^ 0x9E3779B9, last.kwargs['seed'])
        self.assertFalse(rows[-1]['planned_flow_pass'])


if __name__ == '__main__':
    unittest.main()
