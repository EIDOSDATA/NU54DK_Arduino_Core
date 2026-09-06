"""! @brief 완료된 단일 Fixture 102의 증거 개수·coverage·원본 journal 일치를 검사합니다. """
from pathlib import Path
import collections
import hashlib
import json
import re

work = Path(__file__).resolve().parent
source = 'a49cc0dbc1ef8bf5f697106d873bdce55f5911df'
evidence = json.loads((work / 'fixture102-attempt1.json').read_text(encoding='utf-8-sig'))
journal = [json.loads(line) for line in (work / 'fixture102-attempt1.json.jsonl').read_text(encoding='utf-8-sig').splitlines()]
assert evidence['status'] == 'passed' and evidence['results'] == journal
assert evidence['core_revision'] == source and evidence['fixture_id'] == 102
assert evidence['swd_frequency_hz'] == 10000000 and evidence['campaign']['completed_cycles'] == 1
assert all(device['flash']['frequency_hz'] == 10000000 for device in evidence['devices'])
data = [row for row in journal if row['id'].startswith('V04-UARTE-DATA/')]
errors = [row for row in journal if row['id'].startswith('V04-UARTE-EXPECTED-ERROR/')]
cleanup = [row for row in journal if row['id'] == 'V04-FIXTURE-CLEANUP']
recovery = [row for row in data if '/recovery-after-' in row['id']]
assert len(data) == 810 and len(errors) == 12 and len(recovery) == 12
assert len(cleanup) == 2 and len(journal) == 826
assert all(row['status'] == 'passed' for row in data + errors)
assert all(row['status'] == 'cleanup' and all(item.get('result') == [0] for item in row['results']) for row in cleanup)
assert len({row['id'] for row in data + errors}) == 822
coverage = collections.Counter('/'.join(row['id'].split('/')[2:4]) for row in data + errors)
assert len(coverage) == 6 and set(coverage.values()) == {137}
directions = collections.Counter(re.search(r'/\((\d+), (\d+), (\d+), (\d+), (\d+), (\d+)\)', row['id']).group(5) for row in data if '/recovery-after-' not in row['id'])
assert dict(directions) == {'1': 792, '2': 6}
result = {'source': source, 'fixture_id': 102, 'status': 'passed', 'swd_frequency_hz': 10000000, 'data_pass': len(data), 'normal_vectors': 792, 'cts_deferred_rx': 6, 'expected_error_pass': len(errors), 'recovery_data_pass': len(recovery), 'functional_pass': 822, 'cleanup_records': 2, 'campaign_records': 2, 'journal_records': len(journal), 'coverage_per_role_instance_pair': dict(sorted(coverage.items())), 'continuous_elapsed_seconds': evidence['campaign']['continuous_elapsed_seconds'], 'journal_matches_final_json': True, 'functional_ids_unique': True, 'sha256': {name: hashlib.sha256((work / name).read_bytes()).hexdigest() for name in ('fixture102-attempt1.json', 'fixture102-attempt1.json.jsonl')}}
with (work / 'results-audit.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
