"""! @brief 누산 clear 대비의 균등 조건·실패 보존·독립 관측 중단을 검사합니다. """
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_qdec_clear_diagnostic as diagnostic
from v04_protocol import ProtocolError


class ClearDiagnosticTests(unittest.TestCase):
    def test_balanced_rotating_methods(self):
        vectors = list(diagnostic.vectors())
        self.assertEqual(len(set(vectors)), 90)
        self.assertEqual([vectors[index * 3][0] for index in range(3)], [0, 1, 2])
        for strategy in range(3):
            self.assertEqual([repeat for value, repeat in vectors if value == strategy], list(range(1, 31)))

    def test_mismatch_retained_and_sample_or_control_error_stops(self):
        for failure in ('count', 'sample', 'control'):
            visited, stopped, records, state = [], [], [], {}

            @contextmanager
            def armed(devices, current, append, label, instance, debounce, *, observation_mode, read_strategy):
                self.assertEqual(observation_mode, 3)
                state['strategy'] = read_strategy
                visited.append(read_strategy)
                try:
                    yield
                finally:
                    stopped.append(read_strategy)

            class Device:
                def command(self, opcode, values):
                    strategy = state['strategy']
                    if values == (5,):
                        return [strategy, int(strategy != 1), int(strategy != 2), 6000000 if strategy == 2 else 15000, 128]
                    if values == (2,):
                        words = [0] * 16
                        words[0:4] = [400, 0, 16000, 512 if failure == 'sample' else 343]
                        return words
                    words = [0] * 20
                    words[1:5] = [400, 0, 400, 100]
                    return words

            def wave(*args):
                if failure == 'control':
                    raise ProtocolError('injected lease error')

            def observe(device, append, label, *, clear):
                words = [0] * 16
                if not clear:
                    words[5] = 399 if state['strategy'] == 0 else 400
                    words[8] = 4200000 if state['strategy'] == 2 else 500
                return words

            with patch.object(diagnostic.qdec, 'armed', armed), patch.object(diagnostic.qdec, 'wave', wave), \
                 patch.object(diagnostic.qdec, 'observe', observe), patch('builtins.print'):
                pattern = {'count': '30/90', 'sample': 'SAMPLE observation', 'control': 'lease error'}[failure]
                with self.assertRaisesRegex(ProtocolError, pattern):
                    diagnostic.run([Device(), Device()], lambda _: None, lambda key, row: records.append(row))
            self.assertEqual(visited, stopped)
            self.assertEqual(len(visited), 90 if failure == 'count' else 1)
            if failure == 'count':
                self.assertEqual(sum(row['status'] == 'failed' for row in records), 30)
                self.assertFalse(any(row['status'] == 'passed' for row in records))
                self.assertFalse(records[-1]['functional_regression'])


if __name__ == '__main__':
    unittest.main()
