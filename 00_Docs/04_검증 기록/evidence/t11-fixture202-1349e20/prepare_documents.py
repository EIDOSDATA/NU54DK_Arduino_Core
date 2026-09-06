"""! @brief 이전 빌드와 입력을 대조하고 다음 Fixture 203 결선을 확인합니다. """
from pathlib import Path
import json
import re
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
old_source = '0f429e7ab9b5b8e24f4ff19e47abe60014975547'
source = '1349e208073d0fd7d3b020a5e9facf771b371237'
old = json.loads((work.parent / 't11-fixture201/target-artifact-index.json').read_text(encoding='utf-8'))
new = json.loads((work / 'target-artifact-index.json').read_text(encoding='utf-8'))
comparison = {'old_source': old_source, 'new_source': source, 'scope': 'Compiled inputs, config, source membership, memory only; runtime commit identity differs', 'targets': []}
for before, after in zip(old['targets'], new['targets']):
    assert before['scenario'] == after['scenario']
    equal = {key: before[key] == after[key] for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256', 'memory_bytes')}
    assert all(equal.values())
    comparison['targets'].append({'scenario': after['scenario'], 'equal_to_0f429e7': equal})
assert len(comparison['targets']) == 2
paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', old_source, source], cwd=repo).decode('utf-8').strip('\x00').split('\x00')
assert all(path.endswith('.md') or path.startswith('00_Docs/04_검증 기록/evidence/') for path in paths)
comparison['intervening_changed_paths'] = paths
comparison['intervening_changes_documentation_and_evidence_only'] = True
(work / 'build-input-comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
catalog = json.loads((repo / 'tests/hil/nu54dk/v04_fixtures.json').read_text(encoding='utf-8'))
pinmap = json.loads((repo / 'tests/hil/nu54dk/nu54dk_connector_pinmap.json').read_text(encoding='utf-8'))['connectors']
current = next(row for row in catalog['fixtures'] if row['id'] == 202)
following = next(row for row in catalog['fixtures'] if row['id'] == 203)
def normalized(net):
    return re.sub(r'\.(\d+)$', lambda match: '.' + str(int(match.group(1))), net)
for fixture in (current, following):
    for link in fixture['links']:
        for role in ('dut', 'peer'):
            connector, pin, net = link[role]
            assert normalized(pinmap[connector][str(pin)]) == normalized(net)
            assert pinmap[connector][str(pin)] not in ('SWDCLK', 'SWDIO', 'VDD_MOD')
old_by_peer = {tuple(row['peer'][:2]): row for row in current['links']}
expected = [(('P2', 25), ('P2', 12)), (('P2', 26), ('P2', 11)), (('P4', 4), ('P2', 10)), (('P4', 5), ('P2', 9)), (('P2', 30), ('P2', 30))]
for link, (old_pin, new_pin) in zip(following['links'], expected):
    assert tuple(link['dut'][:2]) == tuple(link['peer'][:2]) == new_pin
    assert tuple(old_by_peer[new_pin]['dut'][:2]) == old_pin
next_record = {'status': 'passed', 'current_fixture': 202, 'next_fixture': 203, 'catalog_revision': catalog['revision'], 'connector_pinmap_matches': True, 'current': current, 'next': following, 'no_next_fixture_executed': True}
(work / 'next-wiring-audit.json').write_text(json.dumps(next_record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('BUILD_INPUT_COMPARISON_PASS=2; NEXT_FIXTURE_203_PINMAP_PASS')
