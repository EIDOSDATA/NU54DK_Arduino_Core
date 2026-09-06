"""! @brief TWI 전체 순서와 고유 ID를 독립 계획에 대조합니다. """
from pathlib import Path
import collections
import hashlib
import itertools
import json
import sys

work = Path(__file__).resolve().parent
source = '9a63251ed6f8b9916d8e49d8210414b21c5c7267'
attempt = int(sys.argv[1]) if len(sys.argv) > 1 else 1
assert attempt in (1, 2)
name = f'fixture301-attempt{attempt}.json'
evidence = json.loads((work / name).read_text(encoding='utf-8-sig'))
journal = [json.loads(line) for line in (work / (name + '.jsonl')).read_text(encoding='utf-8-sig').splitlines()]
assert evidence['status'] == 'passed' and evidence['results'] == journal
assert evidence['core_revision'] == source and evidence['fixture_id'] == 301
assert evidence['board_revision'] == 'fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3'
assert evidence['external_wiring_executed'] is True and evidence['swd_frequency_hz'] == 10000000
assert evidence['campaign']['completed_cycles'] == 1
assert all(device['flash']['frequency_hz'] == 10000000 for device in evidence['devices'])
functional = [row for row in journal if row['id'].startswith('V04-TWI-')]
data = [row for row in functional if row['id'].startswith('V04-TWI-DATA/')]
errors = [row for row in functional if row['id'].startswith('V04-TWI-EXPECTED-ERROR/')]
bus = [row for row in functional if row['id'].startswith('V04-TWI-BUS-RECOVERY/')]
recovery = [row for row in data if '/recovery-after-' in row['id']]
cleanup = [row for row in journal if row['id'] == 'V04-FIXTURE-CLEANUP']
assert (len(functional), len(data), len(errors), len(bus), len(recovery), len(cleanup), len(journal)) == (1986, 1968, 12, 6, 18, 2, 1990)
assert all(row['status'] == 'passed' for row in functional)
assert all(row['stuck_result'] != 0 and row['released_result'] == 0 for row in bus)
assert all(row['status'] == 'cleanup' and all(item.get('result') == [0] for item in row['results']) for row in cleanup)
expected = []
for controller, instance_a in itertools.product((1, 2), (20, 21, 22)):
    prefix = f'301/{controller}/{(instance_a, 30)}/'
    for rate, size, direction, address, style in itertools.product((100000, 400000, 1000000), (1, 2, 31, 32, 255, 256), (1, 2, 3), (0x42, 0x43), (0, 1, 2)):
        expected.append('V04-TWI-DATA/' + prefix + str((rate, 0, 0, size, direction, address | (style << 8))))
    for vector, kind, label in (((100000, 0, 0, 32, 1, 0x344), 'EXPECTED-ERROR', 'nack'), ((100000, 0, 0, 256, 3, 0x442), 'EXPECTED-ERROR', 'cancel'), ((100000, 0, 0, 32, 1, 0x542), 'BUS-RECOVERY', 'stuck-sda')):
        expected.append('V04-TWI-' + kind + '/' + prefix + str(vector))
        expected.append('V04-TWI-DATA/' + prefix + str((100000, 0, 0, 32, 3, 0x42)) + '/recovery-after-' + label)
    expected.append('V04-TWI-DATA/' + prefix + str((100000, 0, 0, 32, 3, 0x642)))
actual = [row['id'] for row in functional]
assert len(expected) == len(set(expected)) == len(set(actual)) == 1986
assert actual == expected, 'TWI record order or identity differs from the independent full plan'
coverage = collections.Counter('/'.join(row['id'].split('/')[2:4]) for row in functional)
assert len(coverage) == 6 and set(coverage.values()) == {331}
preserved = []
names = [name, name + '.jsonl']
for previous in range(1, attempt):
    old_name = f'fixture301-attempt{previous}.json'
    old = json.loads((work / old_name).read_text(encoding='utf-8-sig'))
    assert old['status'] == 'failed' and old['results'] == [] and old['external_wiring_executed'] is False
    assert (work / (old_name + '.jsonl')).read_bytes() == b''
    preserved.append(old_name)
    names.extend((old_name, old_name + '.jsonl'))
result = {'source': source, 'fixture_id': 301, 'status': 'passed', 'swd_frequency_hz': 10000000, 'normal_vectors': 1944, 'clock_stretch_data_pass': 6, 'data_pass': 1968, 'expected_error_pass': 12, 'bus_recovery_pass': 6, 'recovery_data_pass': 18, 'functional_pass': 1986, 'cleanup_records': 2, 'campaign_records': 2, 'journal_records': 1990, 'coverage_per_role_instance_pair': dict(sorted(coverage.items())), 'continuous_elapsed_seconds': evidence['campaign']['continuous_elapsed_seconds'], 'journal_matches_final_json': True, 'functional_ids_unique': True, 'independent_plan_ids_match': True, 'independent_plan_order_matches': True, 'successful_attempt': attempt, 'preserved_initial_failures': preserved, 'sha256': {n: hashlib.sha256((work / n).read_bytes()).hexdigest() for n in names}}
with (work / 'results-audit.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result))
