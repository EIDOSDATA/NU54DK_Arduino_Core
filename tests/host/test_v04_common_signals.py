"""! @brief 축소 PWM의 누락과 QDEC signed/double-transition 거짓 PASS를 검사합니다. """
import itertools
import gzip
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_pwm_capture as pwm
import v04_common_qdec as qdec
import v04_common_pwm_modes as modes
from v04_protocol import ProtocolError


class CommonSignalsTests(unittest.TestCase):
    def test_qdec_first_mismatch_trace_is_preserved_before_cleanup(self):
        """! @brief 최초 누락의 원본·16개 read ring을 남긴 뒤 양쪽을 정지합니다. """
        calls, records = [], []
        class Device:
            def __init__(self, role):
                self.image = {'role': role}

            def command(self, opcode, values=(), **options):
                calls.append((self.image['role'], opcode, values))
                if opcode == 80:
                    return [520, 10000]
                if opcode == 83:
                    return [0]
                if opcode == 85:
                    if values == (2,):
                        return [400, 0, 16000, 300, 0, 0, 829, 13] * 2
                    return [326] + [0] * 19
                if opcode == 81:
                    return [0] * 16
                raise AssertionError(opcode)
        with self.assertRaisesRegex(ProtocolError, '399'):
            with qdec.armed([Device(1), Device(2)], lambda _: None,
                            lambda key, row: records.append((key, row)), 'fault', 20, 0):
                raise ProtocolError('399 instead of400')
        self.assertEqual([values for role, opcode, values in calls if opcode == 85],
                         [(0,), (1,), (2,), (4,)] + [(3, offset) for offset in range(0, 16, 2)])
        self.assertEqual([(role, opcode) for role, opcode, _ in calls[-2:]], [(1, 81), (2, 81)])
        self.assertEqual(records[0][1]['status'], 'failed')
        self.assertEqual(records[-1][1]['status'], 'cleanup')

    def test_qdec_heartbeat_does_not_extend_expired_common_session(self):
        calls, checks, records = [], [], []
        class Device:
            def __init__(self, role):
                self.image = {'role': role}

            def command(self, opcode, values=(), **options):
                calls.append((self.image['role'], opcode))
                if opcode == 80:
                    return [520, 10000]
                if opcode in (83, 84):
                    return [0]
                if opcode == 81:
                    return [0] * 16
                raise AssertionError('lease renewal or observation after expiry')

        def current(identifier):
            checks.append(identifier)
            if len(checks) == 3:
                raise ProtocolError('common session expired')

        devices = [Device(1), Device(2)]
        with self.assertRaisesRegex(ProtocolError, 'session expired'):
            with qdec.armed(devices, current, lambda key, row: records.append((key, row)), 'expiry', 20, 0):
                qdec.wave(devices, current, lambda *_: None, 'long-wave', 1000, 10000, 0)
        self.assertEqual(checks, [520, 520, 520])
        self.assertEqual(calls[-2:], [(1, 81), (2, 81)])
        self.assertTrue(all(row['stopped'] for row in records[-1][1]['outcomes']))

    def test_qdec_stops_receiver_before_source_and_still_releases_after_stop_failure(self):
        """! @brief 수신기가 활성인 동안 두 phase가 부유하지 않게 하고 실패 시에도 B를 반환합니다. """
        for fail_receiver in (False, True):
            stopped, records = [], []
            class Device:
                def __init__(self, role):
                    self.image = {'role': role}

                def command(self, opcode, values=(), **options):
                    if opcode == 80:
                        return [520, 10000]
                    if opcode == 83:
                        return [0]
                    if opcode == 81:
                        stopped.append(self.image['role'])
                        if self.image['role'] == 1 and fail_receiver:
                            raise ProtocolError('injected receiver stop failure')
                        return [0] * 16
                    raise AssertionError(opcode)

            def execute():
                with qdec.armed([Device(1), Device(2)], lambda _: None,
                                lambda key, row: records.append(row), 'cleanup', 20, 0):
                    pass
            if fail_receiver:
                with self.assertRaisesRegex(ProtocolError, 'cleanup unproven'):
                    execute()
            else:
                execute()
            self.assertEqual(stopped, [1, 2])
            self.assertTrue(records[-1]['outcomes'][1]['stopped'])

        archive = ROOT / '00_Docs/04_검증 기록/evidence/t12-common-additional-0db0689-first/result.json.gz'
        original = json.loads(gzip.decompress(archive.read_bytes()))
        raw = next(row['words'] for row in original['results'] if row['id'] ==
                   'V04-COMMON-QDEC/20/debounce0/2000us/100cycles/repeat9/initial/raw-role1')
        with self.assertRaises(ProtocolError):
            qdec.counts(raw, 0, 0)

    def test_finite_pwm_raw_sequence_rejects_missing_reordered_and_wrong_duty(self):
        self.assertEqual(len(list(modes.vectors())), 288)
        for idle, repeats, delay, plays in itertools.product((0, 1), (0, 9), (0, 3), (52,)):
            vector = (20, 0, 1000, 0, idle, repeats, delay, plays)
            duties = modes.finite_duties(repeats, delay, plays)
            edges = []
            for index, duty in enumerate(duties):
                edges.extend([[100 + index * 1000, 1], [100 + index * 1000 + duty * 10, 0]])
            if idle:
                edges = edges[1:]
            status = [1, 1, 1, 0, len(edges), idle, 0, len(duties) * 1000 + 200000, 0, 0, 0, 1]
            self.assertEqual(modes.finite_received(vector, status, edges)['complete_pulses'], len(duties) - idle)
            damaged = [row.copy() for row in edges]
            damaged[10][0] += 100
            for invalid in (damaged, edges[:-2], edges[:10] + edges[12:], edges[::-1]):
                raw = status.copy()
                raw[4] = len(invalid)
                with self.assertRaises(ProtocolError):
                    modes.finite_received(vector, raw, invalid)

        ## @brief 반복·지연의 교환과 총 길이만 같은 잘못된 frame 배분을 각각 거부합니다.
        vector = (20, 0, 1000, 0, 0, 9, 3, 4)
        wrong_distribution = [25] * 13 + [50] * 10 + modes.finite_duties(9, 3, 4)[23:]
        self.assertEqual(len(wrong_distribution), len(modes.finite_duties(9, 3, 4)))
        for faulty in (modes.finite_duties(3, 9, 4), wrong_distribution):
            wrong = [[value, level] for index, duty in enumerate(faulty)
                     for value, level in ((100 + index * 1000, 1), (100 + index * 1000 + duty * 10, 0))]
            status = [1, 1, 1, 0, len(wrong), 0, 0, len(faulty) * 1000 + 200000, 0, 0, 0, 1]
            with self.assertRaises(ProtocolError):
                modes.finite_received(vector, status, wrong)

    def test_finite_pwm_first_physical_trace_matches_documented_terminal_stop(self):
        """! @brief 최초 172주기 원본과 마지막 반복을 잘못 더한 파형을 구별합니다. """
        archive = ROOT / '00_Docs/04_검증 기록/evidence/t12-common-signals-3334b17-first/result.json.gz'
        original = json.loads(gzip.decompress(archive.read_bytes()))
        self.assertEqual(original['status'], 'failed')
        raw = next(row for row in original['results']
                   if row['id'] == 'V04-COMMON-PWM-MODES/20/0/1000/0/0/9/3/4/0/raw')
        vector = (20, 0, 1000, 0, 0, 9, 3, 4)
        self.assertEqual(modes.finite_received(vector, raw['receiver'], raw['edges'])['complete_pulses'], 172)
        self.assertEqual(len(modes.finite_duties(0, 0, 52)), 208)
        self.assertEqual(len(modes.finite_duties(9, 3, 4)), 172)
        extended = [edge.copy() for edge in raw['edges']]
        for period in range(1, 13):
            extended.extend([[raw['edges'][-2][0] + period * 1000, 1],
                             [raw['edges'][-1][0] + period * 1000, 0]])
        status = raw['receiver'].copy()
        status[4] = len(extended)
        with self.assertRaises(ProtocolError):
            modes.finite_received(vector, status, extended)

    def test_compact_pwm_preserves_each_identity_axis_and_duty_polarity(self):
        full = {row for load in pwm.LOADS for row in pwm.vectors(load)}
        selected = list(pwm.compact_vectors())
        self.assertEqual(len(selected), 675)
        self.assertEqual(len(set(selected)), 675)
        self.assertTrue(set(selected) < full)
        for identity in {(row[0], row[1], row[5]) for row in full}:
            original = [row for row in full if (row[0], row[1], row[5]) == identity]
            reduced = [row for row in selected if (row[0], row[1], row[5]) == identity]
            for axis in range(7):
                self.assertEqual({row[axis] for row in original}, {row[axis] for row in reduced})
            self.assertEqual({(row[3], row[4]) for row in reduced}, set(itertools.product((0, 25, 50, 75, 100), (0, 1))))
            self.assertTrue(all(pwm.valid_vector(row) for row in reduced))

    def test_qdec_boundaries_signed_and_invalid_transition_are_independent(self):
        self.assertEqual(len(list(qdec.vectors())), 240)
        raw = [0] * 16
        raw[5] = (-4000) & 0xFFFFFFFF
        qdec.counts(raw, -4000, 0)
        for field, value in ((5, 4000), (6, 1), (8, 15001), (9, 1)):
            bad = raw.copy()
            bad[field] = value
            with self.assertRaises(ProtocolError):
                qdec.counts(bad, -4000, 0)
        raw[5:7] = [0, 2]
        qdec.counts(raw, 0, 2)
        with self.assertRaises(ProtocolError):
            qdec.counts(raw, 0, 0)


if __name__ == '__main__':
    unittest.main()
