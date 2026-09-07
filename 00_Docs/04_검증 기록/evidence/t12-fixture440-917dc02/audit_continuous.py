"""! @brief 정식 runner와 독립된 연속 PDM 통계·계획·정리 증거 대조입니다. """
from pathlib import Path
import hashlib
import itertools
import json

work = Path(__file__).resolve().parent
path = work / 'fixture440-continuous.json'
result = json.loads(path.read_text())
journal = [json.loads(line) for line in path.with_suffix('.json.jsonl').read_text().splitlines()]
raw = [json.loads(line) for line in (work / 'continuous-statistics.jsonl').read_text().splitlines()]
assert result['results'] == journal and result['core_revision'] == (work / 'source.txt').read_text().strip()
assert result['pdm_continuous'] and result['fixture_id'] == 440 and result['swd_frequency_hz'] == 10000000
functional = [row for row in journal if row['id'].startswith('V04-PDM-CONTINUOUS/440/')]
cleanup = [row for row in journal if row['id'] == 'V04-PDM-CONTINUOUS-CLEANUP']
density = [row for row in journal if row['id'].startswith('V04-PDM-CONTINUOUS-DENSITY/')]
plan = list(itertools.product((1, 2), itertools.product((20, 21), (256, 1024), (25, 50, 75), (0, 1), (0, 1))))
assert len(plan) == 96 and len(raw) >= len(functional) * 104
samples = 0
for index, row in enumerate(functional):
    role, vector = plan[index]
    count = vector[1]
    assert row['id'] == f'V04-PDM-CONTINUOUS/440/{role}/{vector}/repeat-1'
    assert row['status'] == 'passed' and row['guard_checked_on_device']
    assert row['receiver_status'] == [1, 1, 1, 1, 0, count * 104, count, 0]
    assert [row[key] for key in ('settle_buffers', 'measured_buffers', 'completed_buffers')] == [4, 100, 104]
    sums = [0, 0]
    for buffer_index, words in enumerate(row['buffer_statistics']):
        capture = raw[index * 104 + buffer_index]
        assert capture == {'role': 3 - role, 'index': buffer_index, 'words': words}
        assert words[:3] == [buffer_index, buffer_index % 4, count]
        if buffer_index >= 4:
            for channel in range(2 if vector[3] else 1):
                value = words[3 + channel]
                sums[channel] += value if value < 0x80000000 else value - 0x100000000
    means = [s / (count * 100 // (2 if vector[3] else 1)) for s in sums[:2 if vector[3] else 1]]
    assert means == row['measured_channel_means']
    if vector[3]:
        sign = 1 if ((vector[4] == 0) != (vector[2] == 75)) else -1
        assert means[0] * sign > 0 and means[1] * -sign > 0
    samples += count * 104
for row in cleanup:
    assert row['status'] == 'cleanup' and row['results'] == [{'role': 1, 'result': [0]}, {'role': 2, 'result': [0]}]
for row in density:
    means = {int(key): value for key, value in row['means'].items()}
    assert row['status'] == 'passed' and means[25] < means[50] < means[75]
if result['status'] == 'passed':
    assert len(functional) == len(cleanup) == 96 and len(density) == 16 and len(journal) == 210
    assert len(raw) == 9984 and samples == 6389760
    assert result['campaign']['completed_cycles'] == 1
audit = {'audit_status': 'passed', 'campaign_status': result['status'], 'source': result['core_revision'],
    'functional_pass': len(functional), 'cleanup_pass': len(cleanup), 'density_pass': len(density),
    'completed_buffers_audited': len(functional) * 104, 'samples_summarized_on_device': samples,
    'raw_statistic_records': len(raw), 'unexecuted_vectors': 96 - len(functional), 'error': result.get('error'),
    'scope': '104 continuous DMA completions/case; 4 settling excluded from measured statistics; no full PCM export',
    'not_claimed': ['calibrated audio', 'stereo physical 25/50/75 density patterns', 'whole T12', 'T13 soak'],
    'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (path, path.with_suffix('.json.jsonl'), work / 'continuous-statistics.jsonl')}}
(work / 'continuous-audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
print(json.dumps(audit))
