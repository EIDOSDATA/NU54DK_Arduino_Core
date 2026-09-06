"""! @brief 독립 48개 계획과 실제 JSON/journal, cleanup, exact identity를 대조합니다. """
from pathlib import Path
import hashlib
import itertools
import json
import re

work = Path(__file__).resolve().parent
source = 'e080bbc8f07a0ad751d83dacdb259d395b69be5b'
path = work / 'fixture404-attempt1.json'
result = json.loads(path.read_text(encoding='utf-8'))
journal_path = path.with_suffix('.json.jsonl')
entries = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines()]
assert result['status'] == 'passed' and result['external_wiring_executed'] is True
assert result['fixture_id'] == 404 and result['core_revision'] == source
assert result['swd_frequency_hz'] == 10000000 and result['results'] == entries
assert result['campaign']['completed_cycles'] == 1
assert result['campaign']['interrupted_duration_reused'] is False
plan = list(itertools.product((20, 21, 22), (32, 256), (1021,), (512,), range(4), (1, 2)))
functional = [row for row in entries if row['id'].startswith('V04-ANALOG-SIGNAL/')]
assert len(functional) == 48 and len({row['id'] for row in functional}) == 48
cursor = 0
for vector in plan:
    row, cleanup = entries[cursor:cursor + 2]
    assert row['id'] == f'V04-ANALOG-SIGNAL/404/2/{vector}/repeat-1'
    assert row['status'] == 'passed' and row['scope'] == 'pwm-manual-saadc'
    status = row['receiver_status']
    assert len(status) == 8 and status[:5] == [1, 1, 1, 1, 0]
    assert status[5] == vector[1] * vector[5] and status[6] == vector[1]
    assert -32768 <= row['minimum'] <= row['maximum'] <= 32767 and row['maximum'] > 256
    assert re.fullmatch('[0-9a-f]{64}', row['sha256'])
    assert cleanup['id'] == 'V04-SIGNAL-CLEANUP/repeat-1' and cleanup['status'] == 'cleanup'
    assert cleanup['cleanup_only'] is True
    assert cleanup['results'] == [{'role': 1, 'result': [0]}, {'role': 2, 'result': [0]}]
    cursor += 2
assert [row['id'] for row in entries[cursor:]] == ['V04-CAMPAIGN-PROGRESS', 'V04-CAMPAIGN-COMPLETE']
images = json.loads((work / 'exact-images.json').read_text(encoding='utf-8'))
confirmation = json.loads((work / 'confirmation.json').read_text(encoding='utf-8'))
assert result['confirmation_sha256'] == hashlib.sha256((work / 'confirmation.json').read_bytes()).hexdigest()
for role, device, image in zip((1, 2), result['devices'], images):
    assert device['role'] == image['role'] == role and image['core_revision'] == source
    assert device['hex_sha256'] == image['sha256'] == confirmation['hex_sha256'][role - 1]
    assert device['elf_sha256'] == image['elf_sha256']
    assert device['uid_sha256'] == confirmation['uid_sha256'][role - 1]
    assert device['flash']['frequency_hz'] == 10000000
    assert device['flash']['mass_erase_requested'] is False
    assert device['flash']['recover_requested'] is False
audit = {
    'status': 'passed', 'fixture_id': 404, 'source': source, 'attempt': 1,
    'independent_plan_order_and_unique_functional_ids': 'passed',
    'functional_records': 48, 'cleanup_records': 48, 'campaign_records': 2,
    'total_journal_records': len(entries), 'journal_matches_final_json': True,
    'samples_read': sum(row['receiver_status'][5] for row in functional),
    'raw_minimum': min(row['minimum'] for row in functional),
    'raw_maximum': max(row['maximum'] for row in functional),
    'vectors_observing_low_below_256': sum(row['minimum'] < 256 for row in functional),
    'vectors_observing_high_above_256': sum(row['maximum'] > 256 for row in functional),
    'continuous_elapsed_seconds': result['campaign']['continuous_elapsed_seconds'],
    'swd_frequency_hz': 10000000, 'controller_roles': [2], 'receiver_roles': [1],
    'functional_scope': 'PWM output channel routing, manual SAADC sample count, single/double DMA completion, observed HIGH and cleanup',
    'not_measured': ['calibrated voltage or ADC precision', 'PWM period/duty capture or jitter', 'T12 remaining fixtures', 'T13 concurrency/soak'],
    'hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, journal_path)},
}
(work / 'results-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(audit))
