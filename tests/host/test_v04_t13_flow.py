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
import v04_t13_oracle as oracle
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
        for identifier in (1, 7, 16, 25, 102, 106, 108):
            with self.assertRaises(ProtocolError):
                flow.fixture(tests[identifier], 1)

    def test_concurrent_flow_changes_only_uart30_peer_and_preserves_all_background_links(self):
        tests = {row['id']: row for row in cases.cases()}
        for identifier, index in ((101, 3), (105, 4)):
            for role in (1, 2):
                original = tests[identifier]
                changed = flow.fixture(original, role)
                self.assertEqual(flow.selected_lane(original), index)
                self.assertEqual(changed['_flow_gpio_peer']['lane'], index)
                for lane in range(len(original['serial_links'])):
                    if lane != index:
                        self.assertEqual(changed['serial_links'][lane], original['serial_links'][lane])
                self.assertEqual(set(changed['serial_links'][index]['a' if role == 2 else 'b']['pins']), {'txd', 'rxd'})
                for side in ('a', 'b'):
                    self.assertEqual(len(original['serial_links'][index][side]['pins']), 4)

    def test_concurrent_progress_rejects_one_stalled_background_direction(self):
        import copy
        before = [[{'tx': {'frames': 10}, 'rx': {'frames': 11}} for _ in range(5)] for _ in range(2)]
        after = [[{'tx': {'frames': 14}, 'rx': {'frames': 15}} for _ in range(5)] for _ in range(2)]
        self.assertEqual(len(flow.background_progress(before, after, 4)), 8)
        for role in (0, 1):
            for lane in range(4):
                for direction in ('tx', 'rx'):
                    broken = copy.deepcopy(after)
                    broken[role][lane][direction] = before[role][lane][direction]
                    with self.subTest(role=role, lane=lane, direction=direction), self.assertRaises(ProtocolError):
                        flow.background_progress(before, broken, 4)

    def test_concurrent_progress_must_be_within_actual_high_not_before_or_after(self):
        tests = {row['id']: row for row in cases.cases()}
        for identifier, target in ((101, 3), (105, 4)):
            test = tests[identifier]
            for role in (1, 2):
                counts, times, interval = [0]*20, [0]*20, [0]*20
                interval[4:7] = [1000000, 1100000, 1000000]
                times[16:18] = [target+1, 1000000]
                for lane in range(target):
                    times[0] |= 1 << lane
                    times[1+lane], times[6+lane] = 1000010, 1099990
                    times[11+lane] = test['serial_links'][lane]['a' if role == 1 else 'b']['instance']
                    counts[lane*4:lane*4+4] = [20, 24, 25, 29]
                self.assertEqual(len(flow.background_high(counts, times, interval, test, role)), target)
                for lane in range(target):
                    for offset, value in ((1, 900000), (6, 1100001), (6, 1050000), (11, 99)):
                        broken = times[:]
                        broken[offset+lane] = value
                        with self.subTest(case=identifier, role=role, lane=lane, offset=offset), self.assertRaises(ProtocolError):
                            flow.background_high(counts, broken, interval, test, role)
                    for direction in (0, 2):
                        broken = counts[:]
                        broken[lane*4+direction+1] = broken[lane*4+direction]
                        with self.assertRaises(ProtocolError):
                            flow.background_high(broken, times, interval, test, role)

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

    def pause(self, test, role, seed=123):
        rows = {}
        lane = flow.selected_lane(test)
        for board in (1, 2):
            endpoint = test['serial_links'][lane]['a' if board == 1 else 'b']
            observer = role == board
            raw = self.vector(observer)
            raw[1] = endpoint['instance']
            raw[3] = flow.physical(endpoint['pins']['cts' if observer else 'rts'])
            raw[15:19] = [flow.physical(endpoint['pins'][name]) if observer or name in ('txd', 'rxd')
                          else flow.MASK for name in ('txd', 'rxd', 'rts', 'cts')]
            rows[board] = raw
        return flow.ConfirmedPause(test, role, seed, rows), rows

    def test_pause_is_bound_to_both_proofs_exact_fixture_seed_and_direction(self):
        for test in (row for row in cases.cases() if row['id'] in (2, 3, 4, 5, 101, 105)):
            for role in (1, 2):
                pause, rows = self.pause(test, role)
                fixture = flow.fixture(test, role)
                for board in (1, 2):
                    for lane in range(len(test['serial_links'])):
                        expected = [100, 100]
                        if lane == flow.selected_lane(test):
                            expected[0 if board == role else 1] = 132
                        self.assertEqual(pause.limits(fixture, 123, board, lane), tuple(expected))
                for changed, seed in ((test, 123), (fixture, 124)):
                    with self.assertRaises(ProtocolError):
                        pause.limits(changed, seed, 1, 0)
                with self.assertRaises(ProtocolError):
                    flow.ConfirmedPause(test, role, 123, {1: rows[1]})
                rows[3-role][5] = rows[3-role][4]+1000
                with self.assertRaises(ProtocolError):
                    flow.ConfirmedPause(test, role, 123, rows)

    def test_fault_bound_preserves_payload_checks_and_rejects_other_direction_or_excess_gap(self):
        test = next(row for row in cases.cases() if row['id'] == 3)
        pause, _ = self.pause(test, 1)
        words = [0]*20
        words[19] = 20
        for board, offset in ((1, 5), (2, 11)):
            seed = oracle.lane_seed(123, 0, board)
            edge = lambda at: sum(oracle.pattern(seed, at+i) << (8*i) for i in range(4))
            words[offset:offset+6] = [1, 1024, 0, 7, edge(0), edge(1020)]
        limits = pause.limits(flow.fixture(test, 1), 123, 1, 0)
        words[17:19] = [115, 20]
        with self.assertRaises(ProtocolError):
            oracle.lane(words, 123, 0, 1, 1024)
        oracle.lane(words, 123, 0, 1, 1024, completion_limits_ms=limits)
        for index, value in ((17, 133), (18, 101), (0, 1), (1, 1), (9, words[9] ^ 1)):
            broken = words[:]
            broken[index] = value
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                oracle.lane(broken, 123, 0, 1, 1024, completion_limits_ms=limits)
        with self.assertRaises(ProtocolError):
            runner.snapshots([], test, 123, mock.Mock(), 'test', cts_pause={'limit': 132})


if __name__ == '__main__':
    unittest.main()
