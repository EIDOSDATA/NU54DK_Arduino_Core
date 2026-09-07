"""! @brief 저장된 static·clock·net 진단을 예상 독립 신호선과 대조합니다. """
from pathlib import Path
import hashlib
import json

work = Path(__file__).resolve().parent
source = (work / 'source.txt').read_text().strip()
net = json.loads((work / 'net-isolation-probe.json').read_text())
assert net['source'] == source and net['diagnostic_completed'] and not net['functional_pass_claimed']
assert len(net['results']) == 9
results = net['results'][:8]
mismatches = []
for row in results:
    driver = (row['driver_role'], row['driver_pin'])
    mate = (3 - driver[0], 9 - driver[1])
    for device in row['observed']:
        for pin in (4, 5):
            identity = (device['role'], pin)
            expected = row['level'] if identity in (driver, mate) else 0
            actual = device[f'p1_0{pin}']
            assert device['pin_cnf'][str(pin)] == (1 if identity == driver else 4)
            if actual != expected:
                mismatches.append({'id': row['id'], 'pin': identity, 'expected': expected, 'actual': actual})
cleanup = net['results'][-1]
assert cleanup['id'] == 'NET-CLEANUP'
assert all(row['result'] == [0] and row['pins_restored'] == {'4': 12, '5': 2} for row in cleanup['results'])
assert all(device[f'p1_0{pin}'] == row['level'] for row in results for device in row['observed'] for pin in (4, 5))
assert len(mismatches) == 8

static = json.loads((work / 'static-probe.json').read_text())
data_rows = [row for row in static['results'] if row['id'].startswith('STATIC-DATA/')]
assert len(data_rows) == 4 and static['status'] == 'failed'
for row in data_rows:
    configured_initial = (row['generator_setup']['CONFIG1'] >> 20) & 1
    assert row['levels'] == [configured_initial] * 8
    assert row['levels'] != [row['expected']] * 8

post = json.loads((work / 'postflight.json').read_text())
assert post['source'] == source
assert all(value == 0 for device in post['devices'] for value in device['peripheral_enable'].values())
assert all((value & 1) == 0 for device in post['devices'] for value in device['signal_pin_cnf'].values())
report = {'audit_status': 'passed', 'source': source, 'net_diagnostic_executed': True,
    'wiring_matches_fixture440': False, 'expected': 'two independent crossed nets A04-B05 and A05-B04',
    'observed': 'all four clock/gate pins followed every selected driver LOW and HIGH with all non-drivers input pull-down',
    'observations': 32, 'incorrect_net_observations': mismatches,
    'electrical_join_location': 'not localized to board or external jumper; user inspection required',
    'static_data_source_to_receiver_matches': 4,
    'original_static_assertion': 'failed; assumed clock LOW, but prepared output OUTINIT was inverted because clock input read HIGH',
    'pdm_full_sweep_status': 'failed after four mono DMA vectors; first stereo received identical channels',
    'no_further_pdm_after_net_diagnosis': True, 'postflight_roles_pass': 2,
    'last_uploaded_source': source, 'background_hardware_tests_running': False,
    'sha256': {name: hashlib.sha256((work / name).read_bytes()).hexdigest() for name in
        ('net-isolation-probe.json', 'clock-path-probe.json', 'static-probe.json', 'setup-trace.jsonl', 'postflight.json')}}
with (work / 'diagnostic-audit.json').open('x', encoding='utf-8', newline='\n') as output:
    output.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False))
