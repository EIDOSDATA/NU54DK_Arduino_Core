"""! @brief 실제 타이밍 불일치와 진단을 정식 회귀로 오인하는 경로를 거부합니다. """
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_handover as handover
import v04_t13_run as runner
import v04_t13_spi_timing as timing
from v04_protocol import ProtocolError


class SpiTimingTests(unittest.TestCase):
    def test_one_variable_changes_with_same_gpio_and_uart_twi_rates(self):
        for instance in (20, 21, 22):
            initial, sequence = handover.route(instance)
            for mode in timing.MODES:
                for original in [initial, *sequence]:
                    frozen = copy.deepcopy(original)
                    selected = timing.fixture(original, mode)
                    before, after = original['serial_links'][0], selected['serial_links'][0]
                    self.assertEqual(original, frozen)
                    self.assertEqual(before['a'], after['a'])
                    self.assertEqual(before['b'], after['b'])
                    expected = 4000000 if mode == '4mhz' and before['a']['kind'] in ('spim', 'spis') else before['rate']
                    self.assertEqual(after['rate'], expected)
        for name in ('spim0', 'spim30', 'i2s20', 'C01'):
            original = next(row for row in cases.cases() if row['name'] == name)
            with self.assertRaises(ProtocolError):
                timing.fixture(original, '4mhz')

    def test_actual_register_rate_delay_enable_and_direction_are_required(self):
        original = next(row for row in cases.cases() if row['name'] == 'spim21')
        for mode in timing.MODES:
            test = timing.fixture(original, mode)
            rate = test['serial_links'][0]['rate']
            for role, kind in ((1, 2), (2, 3)):
                endpoint = test['serial_links'][0]['a' if role == 1 else 'b']
                settings = [16000000//rate, 0 if mode == 'rxdelay0' else 1, 255] if kind == 2 else [timing.MASK]*3
                words = [timing.MODES[mode], kind, 21, rate, 0 if kind == 2 else 2, 0,
                         *settings, 0, 0, 0, 0, 0, 0, 0, 1, 128000000, role, 1]
                self.assertTrue(timing.inspect(words, endpoint, rate, mode, role)['diagnostic_only'])
                for index in (0, 1, 2, 3, 4, 5, 6, 7, 8, 18, 19):
                    changed = words[:]
                    changed[index] ^= 1
                    with self.assertRaises(ProtocolError):
                        timing.inspect(changed, endpoint, rate, mode, role)
                if kind == 2:
                    active = words[:]
                    active[4] = 7
                    with self.assertRaises(ProtocolError):
                        timing.inspect(active, endpoint, rate, mode, role)

    def test_both_raw_records_survive_first_configuration_failure(self):
        test = timing.fixture(next(row for row in cases.cases() if row['name'] == 'spim21'), 'baseline')
        devices = [mock.Mock(image={'role': role}) for role in (1, 2)]
        for device in devices:
            device.command.return_value = [0]*20
        rows = []
        with self.assertRaises(ProtocolError):
            timing.observe(devices, test, lambda label, row: rows.append(label), 'prepared')
        self.assertEqual(rows, ['prepared/role1/spi-timing', 'prepared/role2/spi-timing'])

    def test_diagnostic_never_awards_handover100_or_normal_soak(self):
        rows = []
        with mock.patch.object(runner, 'execute_group') as execute:
            handover.execute([], 21, mock.Mock(), lambda label, row: rows.append(row),
                             preflight=True, timing_mode='4mhz')
            self.assertEqual(execute.call_count, 11)
            self.assertTrue(all(call.kwargs['preflight'] for call in execute.call_args_list))
            with self.assertRaises(ProtocolError):
                handover.execute([], 21, mock.Mock(), mock.Mock(), preflight=False, timing_mode='4mhz')
        self.assertFalse(any(row.get('planned_handover_pass') for row in rows))
        self.assertFalse(any(row.get('status') == 'passed' for row in rows))
        test = timing.fixture(next(row for row in cases.cases() if row['name'] == 'spim21'), '4mhz')
        with self.assertRaises(ProtocolError):
            runner.execute_group([], {'test': test}, 180, mock.Mock(), mock.Mock(), preflight=False)


if __name__ == '__main__':
    unittest.main()
