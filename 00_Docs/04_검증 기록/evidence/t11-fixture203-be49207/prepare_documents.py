"""! @brief 이전 빌드 입력과 SPI 누적 근거, 다음 TWI 결선의 핀맵을 대조합니다. """
from pathlib import Path
import hashlib
import json
import re
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
old_source = '1349e208073d0fd7d3b020a5e9facf771b371237'
source = 'be4920757fd9faf2ea38721d2aa374246a259f29'
old = json.loads((work.parent / 't11-fixture202/target-artifact-index.json').read_text(encoding='utf-8'))
new = json.loads((work / 'target-artifact-index.json').read_text(encoding='utf-8'))
comparison = {'old_source': old_source, 'new_source': source, 'scope': 'Compiled inputs, config, source membership, memory only; runtime commit identity differs', 'targets': []}
for before, after in zip(old['targets'], new['targets']):
    assert before['scenario'] == after['scenario']
    equal = {key: before[key] == after[key] for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256', 'memory_bytes')}
    assert all(equal.values())
    comparison['targets'].append({'scenario': after['scenario'], 'equal_to_1349e20': equal})
assert len(comparison['targets']) == 2
paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', old_source, source], cwd=repo).decode('utf-8').strip('\x00').split('\x00')
assert all(path.endswith('.md') or path.startswith('00_Docs/04_검증 기록/evidence/') for path in paths)
comparison['intervening_changed_paths'] = paths
comparison['intervening_changes_documentation_and_evidence_only'] = True
(work / 'build-input-comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
catalog_path = repo / 'tests/hil/nu54dk/v04_fixtures.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
pinmap = json.loads((repo / 'tests/hil/nu54dk/nu54dk_connector_pinmap.json').read_text(encoding='utf-8'))['connectors']
current = next(row for row in catalog['fixtures'] if row['id'] == 203)
following = next(row for row in catalog['fixtures'] if row['id'] == 301)

def normalized(net):
    return re.sub(r'\.(\d+)$', lambda match: '.' + str(int(match.group(1))), net)

for fixture in (current, following):
    for link in fixture['links']:
        for role in ('dut', 'peer'):
            connector, pin, net = link[role]
            assert normalized(pinmap[connector][str(pin)]) == normalized(net)
            assert pinmap[connector][str(pin)] not in ('SWDCLK', 'SWDIO', 'VDD_MOD')
assert [(row['signal'], row['dut'][:2], row['peer'][:2]) for row in following['links']] == [('SDA', ['P2', 12], ['P2', 25]), ('SCL', ['P2', 11], ['P2', 26]), ('GND', ['P2', 30], ['P2', 30])]
assert catalog['revision'] == 2 and '내부 pull-up' in following['pullups'][0]
next_record = {'status': 'passed', 'current_fixture': 203, 'next_fixture': 301, 'catalog_revision': catalog['revision'], 'catalog_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(), 'connector_pinmap_matches': True, 'current': current, 'next': following, 'no_next_fixture_executed': True}
(work / 'next-wiring-audit.json').write_text(json.dumps(next_record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('BUILD_INPUT_COMPARISON_PASS=2; NEXT_FIXTURE_301_PINMAP_PASS')
