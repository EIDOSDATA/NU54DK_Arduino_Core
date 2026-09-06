"""! @brief 독립 LOW/해제/LOW 계획과 실제 raw sample·GPIO·DMA·cleanup을 대조합니다. """
from pathlib import Path
import hashlib
import itertools
import json
import statistics
import struct

work = Path(__file__).resolve().parent
source = (work / 'source.txt').read_text(encoding='ascii').strip()
path = work / 'fixture406-attempt1.json'
result = json.loads(path.read_text(encoding='utf-8'))
journal_path = path.with_suffix('.json.jsonl')
entries = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines()]
assert result['status'] == 'passed' and result['external_wiring_executed'] is True
assert result['fixture_id'] == 406 and result['core_revision'] == source
assert result['fixture_revision'] == 4 and result['swd_frequency_hz'] == 10000000
assert result['results'] == entries and result['campaign']['completed_cycles'] == 1
assert result['campaign']['interrupted_duration_reused'] is False
plan = [(0, count, phase, 0, 0, buffers) for count, buffers, phase in
        itertools.product((32, 256), (1, 2), range(3))]
functional = [row for row in entries if row['id'].startswith('V04-ANALOG-SIGNAL/')]
assert len(functional) == len({row['id'] for row in functional}) == 12
cursor = 0
for vector in plan:
    row, cleanup = entries[cursor:cursor + 2]
    count, buffers, phase = vector[1], vector[5], vector[2]
    assert row['id'] == f'V04-ANALOG-SIGNAL/406/2/{vector}/repeat-1'
    assert row['status'] == 'passed' and row['scope'] == 'input-bias-shared-ain5-manual-saadc'
    assert row['receiver_status'][:7] == [1, 1, 1, 1, 0, count * buffers, count]
    samples = row['samples']
    assert len(samples) == count * buffers
    assert row['minimum'] == min(samples) >= -256
    assert row['maximum'] == max(samples) <= 4095
    assert row['median'] == statistics.median(samples)
    assert row['sha256'] == hashlib.sha256(struct.pack(f'<{len(samples)}h', *samples)).hexdigest()
    assert row['high_samples'] == sum(value > 1024 for value in samples)
    if phase == 1:
        assert row['high_samples'] == len(samples) and row['median'] > 1024
    else:
        assert row['high_samples'] == 0 and max(samples) <= 512
    assert row['phase'] == ['pulldown-before', 'pullup', 'pulldown-after'][phase]
    for key in ('source_readback', 'source_readback_after'):
        assert len(row[key]) == 9
        assert row[key][:7] == [1, phase, 46, 0, int(phase == 1), 0, 1]
        assert row[key][8] & 0xF0F == (0xC if phase == 1 else 0x4)
    assert cleanup['id'] == 'V04-SIGNAL-CLEANUP/repeat-1' and cleanup['status'] == 'cleanup'
    assert cleanup['cleanup_only'] is True
    assert [item['role'] for item in cleanup['results']] == [2, 1]
    assert all(item['result'] == [0] and 'error' not in item for item in cleanup['results'])
    assert cleanup['results'][0]['source_readback'][:7] == [0, 0xFFFFFFFF, 46, 0, 0, 0, 1]
    assert cleanup['results'][0]['source_readback'][8] & 0xF0F == 0
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
groups = []
for offset in range(0, 12, 3):
    group = functional[offset:offset + 3]
    assert group[1]['median'] > max(group[0]['median'], group[2]['median']) + 512
    groups.append({'sample_count': group[0]['receiver_status'][6],
                   'total_samples_per_phase': group[0]['receiver_status'][5],
                   'phase_medians': [r['median'] for r in group],
                   'phase_minima': [r['minimum'] for r in group],
                   'phase_maxima': [r['maximum'] for r in group]})
audit = {'status': 'passed', 'fixture_id': 406, 'source': source, 'attempt': 1,
         'functional_records': 12, 'cleanup_records': 12, 'campaign_records': 2,
         'total_journal_records': len(entries), 'journal_matches_final_json': True,
         'samples_read': sum(len(r['samples']) for r in functional),
         'phase_groups': groups, 'independent_sample_hash_oracle_and_transition_audit': 'passed',
         'source_input_bias_readbacks': 24, 'source_input_release_readbacks': 12,
         'raw_minimum': min(r['minimum'] for r in functional),
         'raw_maximum': max(r['maximum'] for r in functional),
         'continuous_elapsed_seconds': result['campaign']['continuous_elapsed_seconds'],
         'swd_frequency_hz': 10000000,
         'functional_scope': 'AIN5 VBAT_MON shared input INPUT pulldown/pullup/pulldown, single/double SAADC DMA and cleanup',
         'not_measured': ['battery voltage or PMIC register behavior', 'SB4 continuity', 'calibrated ADC precision', 'PWM period/duty', 'Fixture 407/408 and later T12', 'T13 soak/concurrency'],
         'hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, journal_path)}}
(work / 'results-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(audit))
