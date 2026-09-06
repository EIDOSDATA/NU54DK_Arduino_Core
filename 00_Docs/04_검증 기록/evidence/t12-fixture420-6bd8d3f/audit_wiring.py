"""! @brief 현재 420과 다음 430의 GPIO·커넥터 대응을 원본 계약과 대조합니다. """
from pathlib import Path
import hashlib
import json

ROOT = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
WORK = Path(__file__).resolve().parent
catalog_path = ROOT / 'tests/hil/nu54dk/v04_fixtures.json'
pinmap_path = ROOT / 'tests/hil/nu54dk/nu54dk_connector_pinmap.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
pinmap = json.loads(pinmap_path.read_text(encoding='utf-8'))['connectors']
selected = [next(row for row in catalog['fixtures'] if row['id'] == value) for value in (420, 430)]
for fixture in selected:
    for link in fixture['links']:
        for role in ('dut', 'peer'):
            connector, pin, net = link[role]
            expected = pinmap[connector][str(pin)]
            if expected.startswith('P') and '.' in expected:
                port, number = expected.split('.')
                expected = f'{port}.{int(number)}'
            assert expected == net
assert selected[0]['family'] == 'qdec' and selected[1]['family'] == 'i2s'
payload = {'status': 'passed', 'current_fixture': 420, 'next_fixture': 430,
    'current': selected[0], 'next': selected[1], 'catalog_revision': catalog['revision'],
    'catalog_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
    'pinmap_sha256': hashlib.sha256(pinmap_path.read_bytes()).hexdigest(),
    'connector_pinmap_matches': True, 'no_next_fixture_executed': True}
(WORK / 'next-wiring-audit.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('WIRING_CONTRACT_PASS=420,430;NEXT_FIXTURE_NOT_EXECUTED')
