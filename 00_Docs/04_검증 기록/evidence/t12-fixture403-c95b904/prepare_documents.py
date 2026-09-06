"""! @brief 이전 402 입력과 403/404 GPIO 핀맵을 대조합니다. """
from pathlib import Path
import hashlib
import json
import re
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
source = 'c95b9049a62e7c911e4b67104a8f36391ab7e168'
previous = 'ff483a1bbd2a7f275b2c59126ef0e9af09211872'
old = json.loads((repo / '00_Docs/04_검증 기록/evidence/t12-fixture402-ff483a1/target-artifact-index.json').read_text(encoding='utf-8'))
new = json.loads((work / 'target-artifact-index.json').read_text(encoding='utf-8'))
records = []
for left, right in zip(old['targets'], new['targets']):
    assert left['scenario'] == right['scenario']
    equal = {key: left[key] == right[key] for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256', 'memory_bytes')}
    assert all(equal.values()), equal
    records.append({'scenario': right['scenario'], 'equal': equal})
assert len(records) == 2
paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', previous, source], cwd=repo).decode('utf-8').strip('\x00').split('\x00')
assert all(path.endswith('.md') or path.startswith('00_Docs/04_검증 기록/evidence/') for path in paths)
comparison = {'status': 'passed', 'source': source, 'previous_source': previous, 'roles': records, 'intervening_changed_paths': paths, 'documentation_and_evidence_only': True, 'embedded_commit_identities_remain_distinct': True}
(work / 'build-input-comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
catalog_path = repo / 'tests/hil/nu54dk/v04_fixtures.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
pinmap = json.loads((repo / 'tests/hil/nu54dk/nu54dk_connector_pinmap.json').read_text(encoding='utf-8'))['connectors']
current, following = [next(row for row in catalog['fixtures'] if row['id'] == number) for number in (403, 404)]
def normalize(net):
    return re.sub(r'\.(\d+)$', lambda match: '.' + str(int(match.group(1))), net)
for fixture in (current, following):
    for link in fixture['links']:
        for role in ('dut', 'peer'):
            connector, pin, net = link[role]
            assert normalize(pinmap[connector][str(pin)]) == normalize(net)
            assert pinmap[connector][str(pin)] not in ('SWDCLK', 'SWDIO', 'VDD_MOD')
assert [(link['dut'][:2], link['peer'][:2]) for link in following['links']] == [(['P2', 9], ['P4', 12]), (['P2', 30], ['P2', 30])]
record = {'status': 'passed', 'current_fixture': 403, 'next_fixture': 404, 'current': current, 'next': following, 'catalog_revision': catalog['revision'], 'catalog_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(), 'connector_pinmap_matches': True, 'no_next_fixture_executed': True}
(work / 'next-wiring-audit.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('PRIOR_402_INPUT_CONTINUITY_PASS=2; FIXTURE_403_404_PINMAP_PASS')
