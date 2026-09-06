"""! @brief 440의 source별 계획 순서·수신 sample·밀도·cleanup을 독립 대조합니다. """
from pathlib import Path
import hashlib
import itertools
import json
import struct
import sys

WORK = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
SOURCE = (WORK / 'source.txt').read_text().strip()
path = WORK / 'fixture440-attempt1.json'
result = json.loads(path.read_text(encoding='utf-8'))
journal_path = path.with_suffix('.json.jsonl')
journal = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines()]
captures_path = WORK / 'pdm-samples.jsonl'
captures = [json.loads(line) for line in captures_path.read_text(encoding='utf-8').splitlines()]
assert result['core_revision'] == SOURCE and result['fixture_id'] == 440
assert result['swd_frequency_hz'] == 10000000 and result['external_wiring_executed']
assert result['results'] == journal
vectors = list(itertools.product((20, 21), (256, 1024), (25, 50, 75), range(2), range(2), (1, 2)))
plan = list(itertools.product((1, 2), vectors))
functional = [row for row in journal if row['id'].startswith('V04-PDM-SIGNAL/')]
cleanups = [row for row in journal if row['id'].startswith('V04-SIGNAL-CLEANUP/')]
density_rows = [row for row in journal if row['id'].startswith('V04-PDM-DENSITY/')]
assert len(plan) == 192 and len(functional) == len({row['id'] for row in functional})
assert len(captures) >= len(functional)
audited = []
mono = {}
for index, row in enumerate(functional):
    controller, vector = plan[index]
    receiver = 3 - controller
    assert row['id'] == f'V04-PDM-SIGNAL/440/{controller}/{vector}/repeat-1'
    assert row['status'] == 'passed'
    count = vector[1] * vector[5]
    assert row['receiver_status'] == [1, 1, 1, 1, 0, count, vector[1], 0]
    capture = captures[index]
    samples = capture['samples']
    assert capture['read_index'] == index and capture['receiver_role'] == receiver
    assert len(samples) == capture['requested_samples'] == count
    assert all(type(value) is int and -32768 <= value <= 32767 for value in samples)
    mean = sum(samples) / count
    assert row['mean'] == mean and row['minimum'] == min(samples) and row['maximum'] == max(samples)
    if vector[3]:
        channels = [sum(samples[ch::2]) / len(samples[ch::2]) for ch in range(2)]
        assert row['channel_means'] == channels and abs(channels[0] - channels[1]) >= 512
        assert row['scope'] == 'pdm-clock-synchronous-gpiote-dppi-stereo'
        sign = 1 if ((not vector[4]) != (vector[2] == 75)) else -1
        assert channels[0] * sign > 512 and channels[1] * -sign > 512
    else:
        assert row['channel_means'] is None and row['scope'] == 'pdm-clock-synchronous-spis-bitstream'
        mono.setdefault((controller, vector[0], vector[1], vector[4], vector[5]), {})[vector[2]] = mean
    audited.append({'controller_role': controller, 'receiver_role': receiver, 'vector': list(vector),
        'samples': count, 'mean': mean, 'channel_means': row['channel_means'],
        'raw_sha256': hashlib.sha256(struct.pack(f'<{count}h', *samples)).hexdigest()})
for row in cleanups:
    assert row['status'] == 'cleanup' and row['cleanup_only']
    assert row['results'] == [{'role': 1, 'result': [0]}, {'role': 2, 'result': [0]}]
for row in density_rows:
    assert row['status'] == 'passed' and row['scope'] == 'pdm-mono-density-order'
    means = {int(key): value for key, value in row['means'].items()}
    assert set(means) == {25, 50, 75} and means[25] < means[50] < means[75]
passed = result['status'] == 'passed'
if passed:
    assert len(functional) == len(captures) == len(cleanups) == 192 and len(density_rows) == 32
    assert len(journal) == 418 and result['campaign']['completed_cycles'] == 1
    assert sum(row['samples'] for row in audited) == 184320
    expected_order = []
    for controller in (1, 2):
        for vector in vectors:
            expected_order += [f'V04-PDM-SIGNAL/440/{controller}/{vector}/repeat-1', 'V04-SIGNAL-CLEANUP/repeat-1']
        for key in itertools.product((20, 21), (256, 1024), range(2), (1, 2)):
            assert mono[(controller, *key)][25] < mono[(controller, *key)][50] < mono[(controller, *key)][75]
            expected_order += [f'V04-PDM-DENSITY/440/{controller}/{key}/repeat-1']
    expected_order += ['V04-CAMPAIGN-PROGRESS', 'V04-CAMPAIGN-COMPLETE']
    assert [row['id'] for row in journal] == expected_order
else:
    assert result['status'] == 'failed' and len(cleanups) == len(functional) + 1
    assert not result['campaign'].get('completed_cycles', 0)
images = json.loads((WORK / 'exact-images.json').read_text(encoding='utf-8'))
confirmation = json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8'))
assert result['confirmation_sha256'] == hashlib.sha256((WORK / 'confirmation.json').read_bytes()).hexdigest()
for role, device, image in zip((1, 2), result['devices'], images):
    assert device['role'] == image['role'] == role and image['core_revision'] == SOURCE
    assert device['hex_sha256'] == image['sha256'] == confirmation['hex_sha256'][role - 1]
    assert device['elf_sha256'] == image['elf_sha256'] and device['uid_sha256'] == confirmation['uid_sha256'][role - 1]
    assert device['flash']['frequency_hz'] == 10000000
    assert not device['flash']['mass_erase_requested'] and not device['flash']['recover_requested']
audit = {'audit_status': 'passed', 'campaign_status': result['status'], 'source': SOURCE,
    'fixture_id': 440, 'functional_pass': len(functional), 'density_pass': len(density_rows),
    'cleanup_pass': len(cleanups), 'raw_captures': len(captures),
    'audited_functional_samples': sum(row['samples'] for row in audited), 'journal_records': len(journal),
    'whole_fixture_pass': passed, 'failed_cases': 0 if passed else 1,
    'unexecuted_vectors': 192 - len(functional) - (0 if passed else 1),
    'error': result.get('error'), 'counts': audited,
    'capture_scope': 'Canonical read_u16 returned samples copied unchanged; startup pin read adds no fixture commands',
    'not_claimed': ['external microphone compatibility or calibrated audio quality',
        '4 settling and 100 measured continuous buffers', 'T13 injected overflow recovery/concurrency/soak', 'T12 whole gate'],
    'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, journal_path, captures_path)}}
(WORK / 'results-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({key: value for key, value in audit.items() if key != 'counts'}, ensure_ascii=False))
