"""! @brief 독립 QDEC 계획과 실제 count·방향·cleanup·source를 대조합니다. """
from pathlib import Path
import hashlib
import itertools
import json

WORK = Path(__file__).resolve().parent
SOURCE = (WORK / 'source.txt').read_text().strip()
path = WORK / 'fixture420-attempt1.json'
result = json.loads(path.read_text(encoding='utf-8'))
journal_path = path.with_suffix('.json.jsonl')
entries = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines()]
assert result['status'] == 'passed' and result['external_wiring_executed'] is True
assert result['fixture_id'] == 420 and result['fixture_revision'] == 5 and result['core_revision'] == SOURCE
assert result['swd_frequency_hz'] == 10000000 and result['results'] == entries
assert result['campaign']['completed_cycles'] == 1 and not result['campaign']['interrupted_duration_reused']
plan = list(itertools.product((20, 21, 22), (20, 21), (1, 100), (2000,), (0, 1), (0, 1)))
functional = [row for row in entries if row['id'].startswith('V04-QDEC-SIGNAL/')]
assert len(functional) == len({row['id'] for row in functional}) == 48
counts = []
for index, vector in enumerate(plan):
    row, cleanup = entries[index * 2:index * 2 + 2]
    assert row['id'] == f'V04-QDEC-SIGNAL/420/2/{vector}/repeat-1'
    assert row['status'] == 'passed' and row['scope'] == 'pwm-quadrature-qdec'
    expected = (-1 if vector[4] else 1) * vector[2] * 4
    assert row['accumulated'] == expected and row['double_transitions'] == 0
    counts.append({'pwm': vector[0], 'qdec': vector[1], 'cycles': vector[2],
        'state_interval_us': vector[3], 'reverse': bool(vector[4]), 'debounce': bool(vector[5]),
        'expected': expected, 'actual': row['accumulated']})
    assert cleanup['id'] == 'V04-SIGNAL-CLEANUP/repeat-1' and cleanup['status'] == 'cleanup'
    assert cleanup['cleanup_only'] is True
    assert cleanup['results'] == [{'role': 1, 'result': [0]}, {'role': 2, 'result': [0]}]
assert [row['id'] for row in entries[96:]] == ['V04-CAMPAIGN-PROGRESS', 'V04-CAMPAIGN-COMPLETE']
images = json.loads((WORK / 'exact-images.json').read_text(encoding='utf-8'))
confirmation = json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8'))
assert result['confirmation_sha256'] == hashlib.sha256((WORK / 'confirmation.json').read_bytes()).hexdigest()
for role, device, image in zip((1, 2), result['devices'], images):
    assert device['role'] == image['role'] == role and image['core_revision'] == SOURCE
    assert device['hex_sha256'] == image['sha256'] == confirmation['hex_sha256'][role - 1]
    assert device['elf_sha256'] == image['elf_sha256'] and device['uid_sha256'] == confirmation['uid_sha256'][role - 1]
    assert device['flash']['frequency_hz'] == 10000000
    assert not device['flash']['mass_erase_requested'] and not device['flash']['recover_requested']
audit = {'status': 'passed', 'fixture_id': 420, 'source': SOURCE, 'attempt': 1,
    'functional_records': 48, 'cleanup_records': 48, 'campaign_records': 2,
    'total_journal_records': len(entries), 'journal_matches_final_json': True,
    'independent_plan_order_and_unique_functional_ids': 'passed', 'counts': counts,
    'absolute_accumulated_total': sum(abs(row['actual']) for row in counts),
    'signed_accumulated_total': sum(row['actual'] for row in counts),
    'double_transitions': sum(row['double_transitions'] for row in functional),
    'continuous_elapsed_seconds': result['campaign']['continuous_elapsed_seconds'],
    'swd_frequency_hz': 10000000, 'functional_scope': 'PWM quadrature -> QDEC20/21 counts and direction, debounce off/on, stop between configurations',
    'not_measured': ['real encoder compatibility or bounce filtering effectiveness', 'calibrated period/jitter', 'overflow or invalid-transition injection', 'T13 concurrency/soak'],
    'hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, journal_path)}}
assert audit['absolute_accumulated_total'] == 9696 and audit['signed_accumulated_total'] == 0
(WORK / 'results-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({key: value for key, value in audit.items() if key != 'counts'}))
