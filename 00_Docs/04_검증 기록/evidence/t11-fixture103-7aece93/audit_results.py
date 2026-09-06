"""! @brief 완료된 단일 Fixture 103의 증거 개수·coverage·원본 journal 일치를 검사합니다. """
from pathlib import Path
import collections
import hashlib
import json
import re

work = Path(__file__).resolve().parent
source = '7aece93395f0d74272816894a18c2c5e3f1a2abe'
evidence = json.loads((work / 'fixture103-attempt2.json').read_text(encoding='utf-8-sig'))
journal = [json.loads(line) for line in (work / 'fixture103-attempt2.json.jsonl').read_text(encoding='utf-8-sig').splitlines()]
assert evidence['status'] == 'passed' and evidence['results'] == journal
assert evidence['core_revision'] == source and evidence['fixture_id'] == 103
assert evidence['swd_frequency_hz'] == 10000000 and evidence['campaign']['completed_cycles'] == 1
first = json.loads((work / 'fixture103-attempt1.json').read_text(encoding='utf-8-sig'))
assert first['status'] == 'failed' and first['external_wiring_executed'] is False and first['results'] == []
diagnostic = json.loads((work / 'probe-diagnostic.json').read_text(encoding='utf-8'))
assert diagnostic['swd_frequency_hz'] == 10000000 and len(diagnostic['devices']) == 2
assert all(row['status'] == 'passed' and row['cpuid'] == '0x411fd210' for row in diagnostic['devices'])
assert all(device['flash']['frequency_hz'] == 10000000 for device in evidence['devices'])
data = [row for row in journal if row['id'].startswith('V04-UARTE-DATA/')]
errors = [row for row in journal if row['id'].startswith('V04-UARTE-EXPECTED-ERROR/')]
cleanup = [row for row in journal if row['id'] == 'V04-FIXTURE-CLEANUP']
recovery = [row for row in data if '/recovery-after-' in row['id']]
assert len(data) == 2430 and len(errors) == 36 and len(recovery) == 36
assert len(cleanup) == 2 and len(journal) == 2470
assert all(row['status'] == 'passed' for row in data + errors)
assert all(row['status'] == 'cleanup' and all(item.get('result') == [0] for item in row['results']) for row in cleanup)
assert len({row['id'] for row in data + errors}) == 2466
coverage = collections.Counter('/'.join(row['id'].split('/')[2:4]) for row in data + errors)
assert len(coverage) == 18 and set(coverage.values()) == {137}
directions = collections.Counter(re.search(r'/\((\d+), (\d+), (\d+), (\d+), (\d+), (\d+)\)', row['id']).group(5) for row in data if '/recovery-after-' not in row['id'])
assert dict(directions) == {'1': 2376, '2': 18}
result = {'source': source, 'fixture_id': 103, 'status': 'passed', 'swd_frequency_hz': 10000000, 'data_pass': len(data), 'normal_vectors': 2376, 'cts_deferred_rx': 18, 'expected_error_pass': len(errors), 'recovery_data_pass': len(recovery), 'functional_pass': 2466, 'cleanup_records': 2, 'campaign_records': 2, 'journal_records': len(journal), 'coverage_per_role_instance_pair': dict(sorted(coverage.items())), 'continuous_elapsed_seconds': evidence['campaign']['continuous_elapsed_seconds'], 'journal_matches_final_json': True, 'functional_ids_unique': True, 'sha256': {name: hashlib.sha256((work / name).read_bytes()).hexdigest() for name in ('fixture103-attempt2.json', 'fixture103-attempt2.json.jsonl')}}
result.update({'first_attempt_flash_failure_preserved': True, 'first_attempt_functional_results': 0, 'additional_attempts': 1, 'probe_failure_root_cause': 'unresolved'})
with (work / 'results-audit.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
