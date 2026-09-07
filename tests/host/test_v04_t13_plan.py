"""! @brief 미래 결선의 신호 대응·동시 자원·실제 생산 route 허용 여부를 확인합니다. """
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_t13_plan as plan


class T13PlanTests(unittest.TestCase):
    def test_canonical_scope_and_physical_link_directions(self):
        data = json.loads(plan.OUTPUT.read_text(encoding='utf-8'))
        plan.validate(data)
        self.assertFalse(data['physical_executed'])
        self.assertEqual(len(data['topologies']), 8)
        links = [(row['harness'], link) for row in data['topologies'] for link in row['serial_links']]
        links += [(row['harness'], row['serial_link']) for row in data['standalone'] if 'serial_link' in row]
        reverse = {'txd': 'rxd', 'rxd': 'txd', 'rts': 'cts', 'cts': 'rts'}
        for profile, link in links:
            mapping = data['harnesses'][profile]
            for signal, pin in link['a']['pins'].items():
                peer_signal = reverse.get(signal, signal) if link['a']['kind'] == 'uarte' else signal
                self.assertEqual(mapping[pin], link['b']['pins'][peer_signal])
        self.assertNotEqual(data['harnesses']['C']['P2.02'], data['harnesses']['S']['P2.02'])
        self.assertEqual(data['harnesses']['U']['P2.02'], 'P2.00')
        bad = copy.deepcopy(data)
        bad['topologies'][0]['serial_links'][0]['a']['pins']['txd'] = 'P1.10'
        with self.assertRaises(AssertionError):
            plan.validate(bad)

    def test_production_route_validator_accepts_all_planned_serial_endpoints(self):
        data = plan.plan()
        endpoints = [link[role] for row in data['topologies'] for link in row['serial_links'] for role in ('a', 'b')]
        endpoints += [row['serial_link'][role] for row in data['standalone'] if 'serial_link' in row for role in ('a', 'b')]
        kinds = ['uarte', 'spim', 'spis', 'twim', 'twis']
        banks = ['p2_dedicated20', 'p1_flexible', 'p0_flexible']
        profiles = ['connector_fixture', 'dap_uart_bridge', 'dap_uart_disabled', 'pmic_read_only']
        signals = ['invalid', 'txd', 'rxd', 'rts', 'cts', 'sck', 'mosi', 'miso', 'csn', 'dcx', 'sda', 'scl']
        def line(end):
            values = [kinds.index(end['kind']), end['instance'], banks.index(end['bank']), profiles.index(end['profile']), len(end['pins'])]
            for signal, pin in end['pins'].items():
                port, number = pin[1:].split('.')
                values.extend((signals.index(signal), 32 * int(port) + int(number)))
            return ' '.join(map(str, values))
        inputs = [line(end) for end in endpoints]
        # @brief 잘못된 P2 직결 SPI 및 UART의 실제 핀 배치를 생산 validator가 거부해야 합니다.
        for kind, pins in (('spis', dict(sck='P2.01', mosi='P2.02', miso='P2.04', csn='P2.05')),
                           ('uarte', dict(txd='P2.00', rxd='P2.02'))):
            inputs.append(line(plan.endpoint(kind, 0, pins)))
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'routes.exe'
            compiled = subprocess.run(compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-DTEST_UART_STATUS=0', '-DCONFIG_SERIAL=1', '-I', str(ROOT / 'tests/host/serial_fabric_stubs'),
                '-I', str(ROOT / 'cores/arduino'), '-I', str(ROOT / 'variants/nu54dk'),
                str(ROOT / 'variants/nu54dk/serial_fabric_routes.cpp'), str(ROOT / 'tests/host/v04_t13_routes_main.cpp'),
                '-o', str(exe)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], input='\n'.join(inputs) + '\n', capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
            results = list(map(int, executed.stdout.split()))
            self.assertEqual(results, [0] * len(endpoints) + [4, 4])
