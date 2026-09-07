"""! @brief 계측 mode의 균등 대비와 숫자 실패 보존·제어 오류 즉시 중단을 검사합니다. """
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_qdec_read_diagnostic as diagnostic
from v04_protocol import ProtocolError


class ReadDiagnosticTests(unittest.TestCase):
    def test_modes_are_balanced_and_order_rotates(self):
        vectors = list(diagnostic.vectors())
        self.assertEqual(len(vectors), 80)
        self.assertEqual(len(set(vectors)), 80)
        self.assertEqual([vectors[index * 4][0] for index in range(4)], [0, 1, 2, 3])
        for mode in range(4):
            self.assertEqual([repeat for value, repeat in vectors if value == mode], list(range(1, 21)))

    def test_count_failure_is_recorded_but_control_failure_stops_comparison(self):
        for control_error in (False, True):
            visited, records, state = [], [], {}
            @contextmanager
            def armed(devices, current, append, label, instance, debounce, *, observation_mode):
                state['mode'] = observation_mode
                visited.append(observation_mode)
                yield

            class Device:
                def command(self, opcode, values):
                    mode = state['mode']
                    if values == (4,):
                        return [mode, int(mode == 3), int(mode >= 2), int(mode >= 1)]
                    self_words = [0] * 20
                    self_words[1:5] = [400, 0, 400, 30]
                    return self_words

            def wave(*args):
                if control_error:
                    raise ProtocolError('injected lease error')

            def observe(device, append, label, *, clear):
                words = [0] * 16
                words[5] = 0 if clear else (399 if state['mode'] == 0 else 400)
                return words

            with patch.object(diagnostic.qdec, 'armed', armed), patch.object(diagnostic.qdec, 'wave', wave), \
                 patch.object(diagnostic.qdec, 'observe', observe), patch('builtins.print'):
                with self.assertRaisesRegex(ProtocolError, 'lease error' if control_error else '20/80'):
                    diagnostic.run([Device(), Device()], lambda _: None, lambda key, row: records.append(row))
            self.assertEqual(len(visited), 1 if control_error else 80)
            if not control_error:
                self.assertEqual(sum(row['status'] == 'failed' for row in records), 20)
                self.assertEqual(records[-1]['comparisons'], 80)
                self.assertFalse(records[-1]['functional_regression'])
                self.assertFalse(any(row['status'] == 'passed' for row in records))


if __name__ == '__main__':
    unittest.main()
