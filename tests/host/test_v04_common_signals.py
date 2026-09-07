"""! @brief 축소 PWM의 누락과 QDEC signed/double-transition 거짓 PASS를 검사합니다. """
import itertools
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
    def test_finite_pwm_raw_sequence_rejects_missing_reordered_and_wrong_duty(self):
        self.assertEqual(len(list(modes.vectors())), 288)
        for idle, repeats, delay, plays in itertools.product((0, 1), (0, 9), (0, 3), (52,)):
            vector = (20, 0, 1000, 0, idle, repeats, delay, plays)
            duties = ([25] * (1 + repeats + delay) + [75] * (1 + repeats + delay)) * plays
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
