"""! @brief 실행이 끝난 SWD 원본의 전체 벡터·통계·DMA 사본·종료 상태를 다시 대조합니다. """
from pathlib import Path
from collections import Counter
import hashlib
import json
import sys

work = Path(__file__).parent
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
sys.path.insert(0, str(repo / 'tests/hil/nu54dk'))
import v04_nojumper as hil

evidence = json.loads((work / 'hardware-attempt1.json').read_text(encoding='utf-8'))
raw = (work / 'hardware-attempt1.json.jsonl').read_bytes()
journal = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
plan = list(hil.time_vectors()) + list(hil.adc_vectors()) + list(hil.timer_vectors()) + list(hil.event_vectors())
plan += list(hil.bridge_vectors())
plan += [(1, instance, flags, 2, 1000, 100) for instance in (20, 21, 22) for flags in (1, 3, 33, 35)]
assert len(plan) == 904 and evidence['plan'] == [list(vector) for vector in plan]
assert evidence['source'] == (work / 'source.txt').read_text().strip()
assert evidence['swd_frequency_hz'] == 10000000
expected_uids = {'32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9',
                 '4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0'}
assert {row['uid_sha256'] for row in evidence['devices']} == expected_uids
assert len(evidence['devices']) == 2 and len(journal) == 1808
summary = []
for device in evidence['devices']:
    uid = device['uid_sha256']
    rows = [row for row in journal if row['uid_sha256'] == uid]
    assert len(rows) == device['passed'] == 904
    assert len({row['request'][1] for row in rows}) == 1 and rows[0]['request'][1] != 0
    for sequence, (row, vector) in enumerate(zip(rows, plan), 1):
        assert row['request'][0] == sequence and row['request'][2:] == list(vector)
        hil.validate_reply(row['request'], row['reply'])
        if vector[0] == 2:
            hil.validate_adc_snapshot(row['request'], row['reply'], bytes.fromhex(row['adc_snapshot_hex']))
    post = device['postflight']
    assert post['ready'] == [hil.MAGIC, 2, 904, 0]
    assert post['pwm_enable'] == [0, 0, 0] and post['dppi_channels'] == [0, 0, 0, 0]
    assert post['saadc_enable'] == 0 and post['p1_14_pin_cnf'] == device['initial_pin'] == 2
    assert 'pending_vector' not in device and 'failure_snapshot' not in device
    adc = [row for row in rows if row['request'][2] == 2]
    timer = [row for row in rows if row['request'][2] == 3]
    events = [row for row in rows if row['request'][2] in (4, 5)]
    summary.append({
        'uid_sha256': uid, 'commands': len(rows),
        'commands_by_operation': dict(sorted(Counter(row['request'][2] for row in rows).items())),
        'adc_configure_sample_stop_cycles': sum(row['reply'][21] for row in adc),
        'adc_samples': sum(row['reply'][16] for row in adc),
        'adc_calibration_completions': sum(row['reply'][23] for row in adc),
        'adc_last_buffer_raw_snapshots': len(adc),
        'adc_extrema_by_request': [{'vector': row['request'][2:], 'extrema': row['reply'][12:16]} for row in adc],
        'timer_compare_capture_cycles': sum(row['reply'][21] for row in timer),
        'timer_reserved_block_rejections': sum(row['reply'][27] for row in timer),
        'timer_max_observed_error_us': max(row['reply'][14] for row in timer),
        'egu_dppi_received_events': sum(row['reply'][12] for row in events if row['request'][2] == 4),
        'ppib_received_events': sum(row['reply'][12] for row in events if row['request'][2] == 5),
        'event_disable_checks': sum(row['reply'][13] for row in events),
        'event_group_lifecycle_checks': sum(row['reply'][22] for row in events),
        'event_group_reservation_rejections': sum(row['reply'][26] for row in events),
        'grtc_time_cycles': sum(row['reply'][21] for row in rows if row['request'][2] == 6),
        'time_observations': [{'vector': row['request'][2:], 'micros_range': row['reply'][12:14],
                               'millis_range': row['reply'][14:16], 'maximum_timer_difference_us': row['reply'][16],
                               'last_millis_micros_timer': row['reply'][24:27],
                               'maximum_millis_difference_us': row['reply'][27], 'kernel_tick_us': row['reply'][28]}
                              for row in rows if row['request'][2] == 6],
        'pwm_regression_cycles': sum(row['reply'][21] for row in rows if row['request'][2] == 1),
        'postflight': post, 'first_record_at': rows[0]['at'], 'last_record_at': rows[-1]['at'],
    })
output = {'source': evidence['source'], 'status': 'passed', 'commands': 1808,
          'swd_hz': 10000000, 'boards': summary, 'journal_sha256': hashlib.sha256(raw).hexdigest(),
          'raw_adc_note': 'SWD snapshots contain the final repetition; every repetition is checked on device',
          'external_waveform_observed': False, 't12_complete': False, 't13_complete': False}
(work / 'hardware-internal-audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(output, ensure_ascii=False))
