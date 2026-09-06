"""! @brief 전체 430 RAM 추적의 queue 성공·시간과 이전 실패 조건을 대조합니다. """
from pathlib import Path
import hashlib
import json

WORK = Path(__file__).resolve().parent
SOURCE = (WORK / 'source.txt').read_text().strip()
audited = json.loads((WORK / 'results-audit.json').read_text())
assert audited['status'] == 'passed'
path = WORK / 'i2s-timings.jsonl'
traces = [json.loads(line) for line in path.read_text().splitlines()]
assert len(traces) == 384
durations = []
same_case = []
for index, trace in enumerate(traces):
    case = audited['counts'][index // 2]
    assert trace['read_index'] == index and trace['receiver_role'] == index % 2 + 1
    rows = trace['entries']
    assert 0 < len(rows) < 32 and all(len(row) == 6 for row in rows)
    assert [row[0] for row in rows] == sorted(row[0] for row in rows)
    assert [row[1] for row in rows].count(100) == 1
    assert len([row for row in rows if row[1] == 101 and row[2] == 1]) == 1
    assert len([row for row in rows if row[1] == 501 and row[2] == 0]) == 1
    assert not any(row[1] == 400 and (row[2] in (3, 4) or row[5] != 0) for row in rows)
    queues = [row for row in rows if row[1] == 300]
    assert [row[2] for row in queues] == ([2, 3] if case['buffers'] == 1 else [1, 2, 3])
    assert all(row[3] == 0 and row[4] > 0 for row in queues)
    durations.extend(row[4] for row in queues)
    if index // 2 == 72:
        assert case['controller_role'] == 1 and case['sample_rate_hz_requested'] == 48000
        assert case['width_bits'] == 24 and case['channels'] == 0
        assert case['words_per_buffer'] == 32 and case['buffers'] == 1
        same_case.append({'role': trace['receiver_role'], 'queue_elapsed_us': [row[4] for row in queues],
            'entries': rows})
old_path = WORK.parent / 't12-fixture430-timing/timing-trace.json'
old = json.loads(old_path.read_text())
before = [row[4] for d in old['devices'] for row in d['entries'] if row[1] == 300]
assert any(row[1] == 400 and row[2] == 3 for d in old['devices'] for row in d['entries'])
assert len(durations) == 960
record = {'status': 'passed', 'source': SOURCE, 'timing_records': len(traces), 'successful_queue_calls': len(durations),
    'queue_elapsed_us': {'min': min(durations), 'max': max(durations), 'mean': sum(durations) / len(durations)},
    'previous_failed_source': old['source'], 'previous_failed_vector_queue_us': before,
    'previous_failed_vector_now_passed': same_case, 'observed_underrun_or_error_events': 0,
    'nominal_32word_24or32bit_stereo_48khz_buffer_us': 1000000 * 32 / 2 / 48000,
    'clock': 'Fixed Zephyr GRTC system cycle counter, configured 1 MHz; not calibrated external sample rate or jitter',
    'capture': 'Passive RAM reads after canonical completed payload reads; no extra mailbox/fixture commands',
    'sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest(),
        'previous-timing-trace.json': hashlib.sha256(old_path.read_bytes()).hexdigest()}}
(WORK / 'timings-audit.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({k: v for k, v in record.items() if k != 'previous_failed_vector_now_passed'}))
