"""! @brief SPI 전체 계획 ID와 독립 기대 수량을 실제 journal에 대조합니다. """
from pathlib import Path
import collections
import hashlib
import itertools
import json

work = Path(__file__).resolve().parent
source = 'be4920757fd9faf2ea38721d2aa374246a259f29'
initial = json.loads((work / 'fixture203-attempt1.json').read_text(encoding='utf-8-sig'))
assert initial['status'] == 'failed' and initial['external_wiring_executed'] is False and initial['results'] == []
assert (work / 'fixture203-attempt1.json.jsonl').read_bytes() == b''
assert 'pair_dut' in initial['error'] and 'Timeout reading from probe' in initial['error']
evidence = json.loads((work / 'fixture203-attempt2.json').read_text(encoding='utf-8-sig'))
journal = [json.loads(line) for line in (work / 'fixture203-attempt2.json.jsonl').read_text(encoding='utf-8-sig').splitlines()]
assert evidence['status'] == 'passed' and evidence['results'] == journal
assert evidence['core_revision'] == source and evidence['fixture_id'] == 203
assert evidence['board_revision'] == 'fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3'
assert evidence['external_wiring_executed'] is True
assert evidence['swd_frequency_hz'] == 10000000 and evidence['campaign']['completed_cycles'] == 1
assert all(device['flash']['frequency_hz'] == 10000000 for device in evidence['devices'])
data = [row for row in journal if row['id'].startswith('V04-SPI-DATA/')]
errors = [row for row in journal if row['id'].startswith('V04-SPI-EXPECTED-ERROR/')]
cleanup = [row for row in journal if row['id'] == 'V04-FIXTURE-CLEANUP']
recovery = [row for row in data if '/recovery-after-' in row['id']]
concurrent = [row for row in data if '/spim00-twim22-concurrent' in row['id']]
assert len(data) == 27234 and len(errors) == 18 and len(recovery) == 18 and not concurrent
assert len(cleanup) == 2 and len(journal) == 27256
assert all(row['status'] == 'passed' for row in data + errors)
assert all(row['status'] == 'cleanup' and all(item.get('result') == [0] for item in row['results']) for row in cleanup)
expected = set()
for controller, instance_a, instance_b in itertools.product((1, 2), (20, 21, 22), (20, 21, 22)):
    prefix = f'203/{controller}/{(instance_a, instance_b)}/'
    for vector in itertools.product((2000000, 4000000, 8000000), range(4), range(2), (1, 2, 31, 32, 255, 256, 1024), (1, 2, 3), (0, 1, 2)):
        expected.add('V04-SPI-DATA/' + prefix + str(vector))
    expected.add('V04-SPI-EXPECTED-ERROR/' + prefix + str((2000000, 0, 0, 1024, 3, 3)))
    expected.add('V04-SPI-DATA/' + prefix + str((2000000, 0, 0, 32, 3, 0)) + '/recovery-after-cancel')
actual = {row['id'] for row in data + errors}
assert len(expected) == len(actual) == len(data + errors) == 27252
assert actual == expected, {'missing': sorted(expected - actual)[:3], 'extra': sorted(actual - expected)[:3]}
coverage = collections.Counter('/'.join(row['id'].split('/')[2:4]) for row in data + errors)
assert len(coverage) == 18 and collections.Counter(coverage.values()) == {1514: 18}
result = {'source': source, 'fixture_id': 203, 'status': 'passed', 'swd_frequency_hz': 10000000, 'data_pass': len(data), 'normal_vectors': 27216, 'expected_error_pass': len(errors), 'recovery_data_pass': len(recovery), 'spim00_twim22_concurrent_pass': 0, 'functional_pass': 27252, 'cleanup_records': 2, 'campaign_records': 2, 'journal_records': len(journal), 'coverage_per_role_instance_pair': dict(sorted(coverage.items())), 'continuous_elapsed_seconds': evidence['campaign']['continuous_elapsed_seconds'], 'journal_matches_final_json': True, 'functional_ids_unique': True, 'independent_plan_ids_match': True, 'successful_attempt': 2, 'initial_flash_failure_preserved': True, 'initial_functional_results': 0, 'sha256': {name: hashlib.sha256((work / name).read_bytes()).hexdigest() for name in ('fixture203-attempt1.json', 'fixture203-attempt1.json.jsonl', 'fixture203-attempt2.json', 'fixture203-attempt2.json.jsonl')}}
with (work / 'results-audit.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
