"""! @brief 기존 S net의 역할 전환·실제 PSEL·고정 양방향 전환 수를 검사합니다. """
from collections import Counter
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_handover as handover
import v04_t13_oracle as oracle
import v04_t13_plan as plan
import v04_t13_run as runner
from v04_protocol import ProtocolError


class HandoverTests(unittest.TestCase):
    def test_reversed_endpoints_preserve_each_wire_and_one_spi_output(self):
        selected = [row for row in cases.cases() if 6 <= row['id'] <= 23]
        for original in selected:
            reverse = handover.variant(original, True)
            mapping = plan.harness('S')
            for role in ('a', 'b'):
                self.assertEqual(set(original['serial_links'][0][role]['pins'].values()),
                                 set(reverse['serial_links'][0][role]['pins'].values()))
            link = reverse['serial_links'][0]
            for signal, pin in link['a']['pins'].items():
                self.assertEqual(mapping[pin], link['b']['pins'][signal])
                if link['a']['kind'] in ('spim', 'spis'):
                    outputs = lambda end: {'sck', 'mosi', 'csn'} if end['kind'] == 'spim' else {'miso'}
                    self.assertEqual(int(signal in outputs(link['a'])) + int(signal in outputs(link['b'])), 1)
        for identifier in (1, 2, 24, 101, 106):
            test = next(row for row in cases.cases() if row['id'] == identifier)
            with self.assertRaises(ProtocolError):
                handover.variant(test, True)

    def test_target_transform_and_production_routes_match_host(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory)/'handover.exe'
            command = compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-DTEST_UART_STATUS=0', '-DCONFIG_SERIAL=1', '-I', str(ROOT/'tests/host/serial_fabric_stubs'),
                '-I', str(ROOT/'cores/arduino'), '-I', str(ROOT/'variants/nu54dk'),
                '-I', str(ROOT/'tests/zephyr/v04_t13_hil/src'),
                str(ROOT/'variants/nu54dk/serial_fabric_routes.cpp'),
                str(ROOT/'tests/host/v04_t13_handover_main.cpp'), '-o', str(exe)]
            built = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stdout+built.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stdout+executed.stderr)
        originals = {row['id']: row for row in cases.cases()}
        checked = 0
        kinds = {'spim': 2, 'spis': 3, 'twim': 4, 'twis': 5}
        for line in executed.stdout.splitlines():
            label, *values = line.split()
            values = list(map(int, values))
            if label == 'CASE':
                self.assertEqual(values[1], int(6 <= values[0] <= 23))
                continue
            identifier, role, kind, result, *pins = values
            endpoint = handover.variant(originals[identifier], True)['serial_links'][0]['a' if role == 0 else 'b']
            expected = {cases.SIGNALS.index(signal): 32*int(pin[1])+int(pin[3:]) for signal, pin in endpoint['pins'].items()}
            self.assertEqual(kind, kinds[endpoint['kind']])
            self.assertEqual(result, 0)
            self.assertEqual(dict(zip(pins[::2], pins[1::2])), expected)
            checked += 1
        self.assertEqual(checked, 36)

    def test_actual_bus_pins_reject_wrong_role_data_pin_and_unused_dcx(self):
        for identifier in (6, 7, 16):
            test = next(row for row in cases.cases() if row['id'] == identifier)
            for reverse in (False, True):
                for role in ('a', 'b'):
                    endpoint = handover.variant(test, reverse)['serial_links'][0][role]
                    kind = {'spim': 2, 'spis': 3, 'twim': 4, 'twis': 5}[endpoint['kind']]
                    signals = ('sck', 'mosi', 'miso', 'csn') if kind in (2, 3) else ('sda', 'scl')
                    pins = [32*int(endpoint['pins'][signal][1])+int(endpoint['pins'][signal][3:]) for signal in signals]
                    words = [kind, endpoint['instance'], 0, *pins, *([oracle.MASK]*(5-len(pins)))]
                    self.assertEqual(oracle.bus_pins(words, endpoint)['kind'], endpoint['kind'])
                    for index in (0, 1, 3, 4, 7):
                        broken = words[:]
                        broken[index] ^= 1
                        with self.assertRaises(ProtocolError):
                            oracle.bus_pins(broken, endpoint)

    def test_round_trip_routes_cover_both_directions_and_serial00_has_no_uart(self):
        for instance in (0, 20, 21, 22, 30):
            initial, sequence = handover.route(instance)
            path = [initial, *sequence]
            edges = Counter((first['name'], second['name']) for first, second in zip(path, path[1:]))
            self.assertEqual(len(sequence), 2 if instance == 0 else 10)
            self.assertEqual(initial['name'], sequence[-1]['name'])
            for (first, second), count in edges.items():
                self.assertEqual(count, 1)
                self.assertEqual(edges[second, first], 1)
            if instance == 0:
                self.assertTrue(all('uart' not in row['name'] for row in path))

    def test_bus_pin_failure_keeps_every_lane_and_peer_raw_before_judgement(self):
        test = next(row for row in cases.cases() if row['id'] == 104)
        devices = []
        for role in (1, 2):
            device = mock.Mock()
            device.image = {'role': role}
            device.command.return_value = [0]*8
            devices.append(device)
        records = []
        with self.assertRaises(ProtocolError):
            runner.prepared_bus_pins(devices, test, lambda label, row: records.append(label), 'prepared')
        self.assertEqual(records, [f'prepared/role{role}/lane{lane}/bus-pins'
                                  for role in (1, 2) for lane in range(3)])

    def test_preflight_is_one_round_with_distinct_seeds_and_no_handover_pass(self):
        records = []
        with mock.patch.object(runner, 'execute_group') as run:
            handover.execute([], 0, mock.Mock(), lambda label, row: records.append((label, row)), preflight=True)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len({call.kwargs['seed'] for call in run.call_args_list}), 3)
        results = [row for label, row in records if label.endswith('/result')]
        self.assertEqual(len(results), 2)
        self.assertFalse(any(row['planned_handover_pass'] for row in results))


if __name__ == '__main__':
    unittest.main()
