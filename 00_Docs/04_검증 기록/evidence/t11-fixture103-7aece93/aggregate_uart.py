"""! @brief 세 UART fixture의 exact 원본을 대조해 승인 route 누적 범위를 기록합니다. """
from pathlib import Path
import hashlib
import json
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
expected = {101: ('154324ce7a865522374066ca957ebc98909c7c19', 1644), 102: ('a49cc0dbc1ef8bf5f697106d873bdce55f5911df', 822), 103: ('7aece93395f0d74272816894a18c2c5e3f1a2abe', 2466)}
rows = []
baseline = None
for fixture_id, (source, count) in expected.items():
    directory = work.parent / ('t11-fixture' + str(fixture_id))
    path = directory / 'results-audit.json'
    audit = json.loads(path.read_text(encoding='utf-8'))
    assert audit['source'] == source and audit['status'] == 'passed' and audit['functional_pass'] == count
    assert audit['fixture_id'] == fixture_id and audit['swd_frequency_hz'] == 10000000
    index = json.loads((directory / 'target-artifact-index.json').read_text(encoding='utf-8'))
    signatures = {target['scenario']: {key: target[key] for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256', 'memory_bytes')} for target in index['targets']}
    if baseline is None:
        baseline = signatures
    else:
        assert signatures == baseline
    rows.append({'fixture_id': fixture_id, 'source': source, 'audit_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'data_pass': audit['data_pass'], 'expected_error_pass': audit['expected_error_pass'], 'functional_pass': count, 'cleanup_records': audit['cleanup_records']})
changed = subprocess.run(['git', 'diff', '--name-only', '-z', expected[101][0], expected[103][0]], cwd=repo, check=True, stdout=subprocess.PIPE).stdout.decode('utf-8').split('\x00')
changed = [name for name in changed if name]
assert changed and all(name.startswith('00_Docs/') or name in ('README.md', 'tests/hil/nu54dk/README.md') for name in changed)
totals = {key: sum(row[key] for row in rows) for key in ('data_pass', 'expected_error_pass', 'functional_pass', 'cleanup_records')}
assert totals == {'data_pass': 4860, 'expected_error_pass': 72, 'functional_pass': 4932, 'cleanup_records': 6}
result = {'status': 'passed', 'scope': 'Current-source T11 approved UART routes only; each exact firmware identity remains separate', 'swd_frequency_hz': 10000000, 'fixtures': rows, 'totals': totals, 'compiled_inputs_config_membership_memory_equal': True, 'git_changes_between_fixture_sources': 'documentation-and-evidence-only', 'intervening_changed_files': len(changed), 'single_source_full_hil_claimed': False, 'spi_twi_current_source_executed': False, 'first_fixture103_peer_flash_failure_preserved': True}
path = work / 'uart-route-aggregate.json'
assert not path.exists()
path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(result, ensure_ascii=False))
