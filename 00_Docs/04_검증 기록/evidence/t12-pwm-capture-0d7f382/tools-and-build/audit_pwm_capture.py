"""! @brief 실행기의 합계를 신뢰하지 않고 raw 시각·논리 ID·cleanup을 독립 재계산합니다. """
import datetime
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import re
from check_pc import WORK

folder = WORK / 'pwm-hardware-0d7f382'
result = json.loads((folder / 'attempt1.json').read_text(encoding='utf-8'))
journal = [json.loads(line) for line in (folder / 'attempt1.json.jsonl').read_text(encoding='utf-8').splitlines()]
assert result['status'] == 'passed' and result['external_wiring_executed']
assert result['swd_frequency_hz'] == 10000000 and result['cmsis_dap_limit_packets']
assert result['results'] == journal
expected = set(itertools.product((20, 21, 22), range(4), (1000, 4000), (0, 25, 50, 75, 100), (0, 1)))
observations = [row for row in journal if row['status'] == 'observation']
functions = [row for row in journal if row['status'] == 'passed' and row['id'].startswith('V04-PWM-CAPTURE/')]
cleanup = [row for row in journal if row['status'] == 'cleanup']
assert len(observations) == len(functions) == len(cleanup) == len(expected) == 240
assert {tuple(row['vector']) for row in functions} == {tuple(row['vector']) for row in observations} == expected
assert len({row['id'] for row in journal}) == len(journal)
assert all(row['results'] == [{'role': 2, 'result': [0, 1, 1]}, {'role': 1, 'result': [0, 1, 1]}] for row in cleanup)
ratios, periods, static_us, edges_total = [], [], [], 0
for index, (raw, checked, stopped) in enumerate(zip(observations, functions, cleanup)):
    vector = tuple(raw['vector'])
    assert tuple(checked['vector']) == vector
    prefix = 'V04-PWM-CAPTURE/408/' + '/'.join(map(str, vector))
    assert raw['id'] == prefix + '/raw/repeat-1'
    assert checked['id'] == prefix + '/repeat-1'
    assert stopped['id'] == prefix + '/cleanup/repeat-1'
    assert journal.index(raw) < journal.index(checked) < journal.index(stopped)
    statuses = raw['statuses']
    assert raw['capture_reply'] == [0]
    assert statuses[0][:4] == [1, 1, 1, 0] and statuses[1][:4] == [1, 1, 0, 0]
    assert statuses[0][-1] == statuses[1][-1] == 1
    assert statuses[1][8] + statuses[1][9] > 0
    top, duty = vector[2:4]
    edges = raw['edges']
    assert statuses[0][4] == len(edges)
    edges_total += len(edges)
    if duty in (0, 100):
        assert not edges and statuses[0][5:7] == [int(duty == 100)] * 2
        assert 100 * top <= statuses[0][7] <= 125 * top
        static_us.append(statuses[0][7])
    else:
        assert len(edges) == 201
        assert all(a[0] < b[0] and a[1] != b[1] and a[1] in (0, 1) and b[1] in (0, 1)
                   for a, b in zip(edges, edges[1:]))
        for offset in range(0, 200, 2):
            a, b, c = edges[offset:offset + 3]
            period = c[0] - a[0]
            high = b[0] - a[0] if a[1] == 1 else c[0] - b[0]
            period_ratio = Fraction(period, top)
            duty_ratio = Fraction(high * 100, period * duty)
            assert Fraction(95, 100) <= period_ratio <= Fraction(105, 100)
            assert Fraction(95, 100) <= duty_ratio <= Fraction(105, 100)
            periods.append(period)
            ratios.append(duty_ratio)
post = json.loads((folder / 'postflight.json').read_text(encoding='utf-8'))
for row, expected_pin_cnf in zip(post['boards'], (0, 2)):
    assert row['cpuid'] == '0x411fd210' and row['state'] == 'SLEEPING'
    assert row['backend_packets'] == 1 and row['pwm_enable'] == [0, 0, 0] and row['dppi20_chen'] == 0
    assert row['p1_14_pin_cnf'] == expected_pin_cnf
    identity = bytes.fromhex(row['identity_raw_hex'])
    assert int.from_bytes(identity[:4], 'little') == 0x344c4948
    assert int.from_bytes(identity[8:12], 'little') == row['role']
    assert identity[16:56].decode('ascii') == result['core_revision']
host = (WORK / 'pwm-usb-host.log').read_text(encoding='utf-8')
groups = [int(value) for value in re.findall(r'Ran (\d+) tests?', host)]
skips = [line for line in host.splitlines() if '... skipped ' in line]
audit = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'source': result['core_revision'], 'physical_status': 'passed within first capture scope',
         'functional_cases': 240, 'cleanup_cases': 240, 'raw_observations': 240,
         'dynamic_cases': len(periods) // 100, 'measured_periods': len(periods), 'raw_edges': edges_total,
         'static_cases': len(static_us), 'static_duration_us_range': [min(static_us), max(static_us)],
         'period_us_range': [min(periods), max(periods)],
         'duty_relative_ratio_range': [str(min(ratios)), str(max(ratios))],
         'campaign_seconds': result['campaign']['continuous_elapsed_seconds'],
         'swd_frequency_hz': 10000000, 'cmsis_dap_limit_packets': True,
         'postflight_pass': True, 'postflight_pin_cnf': [0, 2],
         'postflight_first_oracle_error': 'scratch script incorrectly required reset PIN_CNF=2 on both roles; A GpioteFabric::release explicitly uses GPIO_INPUT, so A=0 is input-connected/no-pull/no-sense; B PWM release=2 input-disconnected. Original failed assertion and raw observation retained; no hardware state changed.',
         'host': {'groups': len(groups), 'tests': sum(groups), 'pass': sum(groups) - len(skips), 'skips': skips},
         'journal_sha256': hashlib.sha256((folder / 'attempt1.json.jsonl').read_bytes()).hexdigest(),
         'flash': [row['flash'] for row in result['devices']],
         'transport_root_cause': 'unresolved; single-packet campaign succeeded, not a universal fix claim',
         't12_complete': False, 't13_complete': False, 'rc_or_release_complete': False}
with (folder / 'audit.json').open('x', encoding='utf-8') as stream:
    json.dump(audit, stream, ensure_ascii=False, indent=2)
print(json.dumps(audit, ensure_ascii=False, indent=2))
