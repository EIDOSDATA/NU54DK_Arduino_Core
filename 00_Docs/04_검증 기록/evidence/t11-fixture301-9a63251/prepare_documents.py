"""! @brief 이전 여섯 실기의 빌드 입력과 다음 Fixture 401 핀맵을 대조합니다. """
from pathlib import Path
import hashlib
import json
import re
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
base = repo / '00_Docs/04_검증 기록/evidence'
source = '9a63251ed6f8b9916d8e49d8210414b21c5c7267'
current_index = json.loads((work / 'target-artifact-index.json').read_text(encoding='utf-8'))
records = []
for fixture_id, short in ((101, '154324c'), (102, 'a49cc0d'), (103, '7aece93'), (201, '0f429e7'), (202, '1349e20'), (203, 'be49207')):
    root = base / f't11-fixture{fixture_id}-{short}'
    audit = json.loads((root / 'results-audit.json').read_text(encoding='utf-8'))
    assert audit['status'] == 'passed' and audit['fixture_id'] == fixture_id and audit['source'].startswith(short)
    previous_index = json.loads((root / 'target-artifact-index.json').read_text(encoding='utf-8'))
    comparisons = []
    for old, new in zip(previous_index['targets'], current_index['targets']):
        assert old['scenario'] == new['scenario']
        equal = {key: old[key] == new[key] for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256', 'memory_bytes')}
        assert all(equal.values()), (fixture_id, equal)
        comparisons.append({'scenario': new['scenario'], 'equal_to_current': equal})
    assert len(comparisons) == 2
    records.append({'fixture_id': fixture_id, 'source': audit['source'], 'targets': comparisons})
paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', records[0]['source'], source], cwd=repo).decode('utf-8').strip('\x00').split('\x00')
assert all(path.endswith('.md') or path.startswith('00_Docs/04_검증 기록/evidence/') for path in paths)
comparison = {'status': 'passed', 'new_source': source, 'scope': 'Compiled source bytes, resolved config, membership and memory match across all seven fixtures; embedded commit identities remain separate', 'previous_fixtures': records, 'intervening_changed_paths': paths, 'intervening_changes_documentation_and_evidence_only': True}
(work / 'build-input-comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
catalog_path = repo / 'tests/hil/nu54dk/v04_fixtures.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
pinmap = json.loads((repo / 'tests/hil/nu54dk/nu54dk_connector_pinmap.json').read_text(encoding='utf-8'))['connectors']
current = next(row for row in catalog['fixtures'] if row['id'] == 301)
following = next(row for row in catalog['fixtures'] if row['id'] == 401)
def normalized(net):
    return re.sub(r'\.(\d+)$', lambda m: '.' + str(int(m.group(1))), net)
for fixture in (current, following):
    for link in fixture['links']:
        for role in ('dut', 'peer'):
            connector, pin, net = link[role]
            assert normalized(pinmap[connector][str(pin)]) == normalized(net)
            assert pinmap[connector][str(pin)] not in ('SWDCLK', 'SWDIO', 'VDD_MOD')
assert [(row['dut'][:2], row['peer'][:2]) for row in following['links']] == [(['P2', 12], ['P4', 12]), (['P2', 30], ['P2', 30])]
assert 'controller_role=2' in following['notes']
next_record = {'status': 'passed', 'current_fixture': 301, 'next_fixture': 401, 'catalog_revision': catalog['revision'], 'catalog_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(), 'connector_pinmap_matches': True, 'current': current, 'next': following, 'no_next_fixture_executed': True}
(work / 'next-wiring-audit.json').write_text(json.dumps(next_record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('PRIOR_FIXTURE_INPUT_COMPARISON_PASS=6; ROLE_BUILDS_COMPARED=12; NEXT_FIXTURE_401_PINMAP_PASS')
