"""! @brief 두 독립된 440 clock/gate net의 전체 LOW/HIGH와 복원을 판정합니다. """
from pathlib import Path
import hashlib
import json

work = Path(__file__).resolve().parent
path = work / 'net-isolation-settled.json'
result = json.loads(path.read_text())
assert result['source'] == (work / 'source.txt').read_text().strip()
assert result['diagnostic_completed'] and result['swd_frequency_hz'] == 10000000
rows = result['results']
assert len(rows) == 25 and result['functional_pass_claimed'] is False
mismatches = []
for row in rows[:24]:
    driver = (row['driver_role'], row['driver_pin'])
    mate = (3 - driver[0], 9 - driver[1])
    for device in row['observed']:
        for pin in (4, 5):
            identity = (device['role'], pin)
            assert device['pin_cnf'][str(pin)] == (1 if identity == driver else 4)
            expected = row['level'] if identity in (driver, mate) else 0
            if device[f'p1_0{pin}'] != expected:
                mismatches.append({'case': row['id'], 'pin': identity, 'expected': expected, 'actual': device[f'p1_0{pin}']})
assert rows[-1]['id'] == 'NET-CLEANUP'
assert all(row['result'] == [0] and row['pins_restored'] == {'4': 12, '5': 2} for row in rows[-1]['results'])
audit = {'source': result['source'], 'observations': 96, 'mismatches': mismatches,
    'wiring_matches_fixture440': not mismatches, 'cleanup_roles_pass': 2,
    'scope': 'static clock/gate separation; no PDM functional PASS',
    'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
with (work / 'net-settled-audit.json').open('x', encoding='utf-8', newline='\n') as output:
    output.write(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
assert not mismatches, mismatches
print('FIXTURE440_INDEPENDENT_CLOCK_GATE_NETS_PASS=96;PINS_RESTORED=4')
