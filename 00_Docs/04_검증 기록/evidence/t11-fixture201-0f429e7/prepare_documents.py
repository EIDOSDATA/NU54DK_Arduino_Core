"""! @brief 빌드 입력과 다음 결선을 읽기 전용으로 대조하고 stage 감사를 준비합니다. """
from pathlib import Path
import json
import re
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
old_source = '7aece93395f0d74272816894a18c2c5e3f1a2abe'
source = '0f429e7ab9b5b8e24f4ff19e47abe60014975547'
old = json.loads((work.parent / 't11-fixture103/target-artifact-index.json').read_text(encoding='utf-8'))
new = json.loads((work / 'target-artifact-index.json').read_text(encoding='utf-8'))
comparison = {'old_source': old_source, 'new_source': source, 'scope': 'Compiled inputs, config, source membership, memory only; runtime commit identity differs', 'targets': []}
for before, after in zip(old['targets'], new['targets']):
    assert before['scenario'] == after['scenario']
    equal = {key: before[key] == after[key] for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256', 'memory_bytes')}
    assert all(equal.values())
    comparison['targets'].append({'scenario': after['scenario'], 'equal_to_7aece93': equal})
assert len(comparison['targets']) == 2
paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', old_source, source], cwd=repo).decode('utf-8').strip('\x00').split('\x00')
assert all(path.endswith('.md') or path.startswith('00_Docs/04_검증 기록/evidence/') for path in paths)
comparison['intervening_changed_paths'] = paths
comparison['intervening_changes_documentation_and_evidence_only'] = True
(work / 'build-input-comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
catalog = json.loads((repo / 'tests/hil/nu54dk/v04_fixtures.json').read_text(encoding='utf-8'))
pinmap = json.loads((repo / 'tests/hil/nu54dk/nu54dk_connector_pinmap.json').read_text(encoding='utf-8'))['connectors']
current = next(row for row in catalog['fixtures'] if row['id'] == 201)
following = next(row for row in catalog['fixtures'] if row['id'] == 202)
def normalized(net):
    return re.sub(r'\.(\d+)$', lambda match: '.' + str(int(match.group(1))), net)
for fixture in (current, following):
    for link in fixture['links']:
        for role in ('dut', 'peer'):
            connector, pin, net = link[role]
            assert normalized(pinmap[connector][str(pin)]) == normalized(net)
            assert pinmap[connector][str(pin)] not in ('SWDCLK', 'SWDIO', 'VDD_MOD')
old_by_peer = {tuple(row['peer'][:2]): row for row in current['links']}
expected = [(('P4', 20), ('P2', 25), ('P2', 12)), (('P4', 21), ('P2', 26), ('P2', 11)), (('P2', 17), ('P4', 4), ('P2', 10)), (('P2', 19), ('P4', 5), ('P2', 9)), (('P2', 30), ('P2', 30), ('P2', 30))]
for link, (old_pin, new_pin, peer_pin) in zip(following['links'], expected):
    assert tuple(link['dut'][:2]) == new_pin and tuple(link['peer'][:2]) == peer_pin
    assert tuple(old_by_peer[peer_pin]['dut'][:2]) == old_pin
next_record = {'status': 'passed', 'current_fixture': 201, 'next_fixture': 202, 'catalog_revision': catalog['revision'], 'connector_pinmap_matches': True, 'current': current, 'next': following, 'no_next_fixture_executed': True}
(work / 'next-wiring-audit.json').write_text(json.dumps(next_record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
text = (work.parent / 't11-fixture103/stage_audit.py').read_text(encoding='utf-8')
text = text.replace(old_source, source).replace('t11-fixture103-7aece93', 't11-fixture201-0f429e7').replace('69_T11_Fixture_103_current_source_UART_회귀.md', '70_T11_Fixture_201_current_source_SPI_회귀.md')
assert not (work / 'stage_audit.py').exists()
(work / 'stage_audit.py').write_text(text, encoding='utf-8', newline='\n')
print('BUILD_INPUT_COMPARISON_PASS=2; NEXT_FIXTURE_202_PINMAP_PASS; STAGE_SCRIPT_PREPARED')
