"""! @brief canonical PASS와 실패 기록을 source별로 합산합니다. """
from pathlib import Path
import json
import re
work = Path(__file__).resolve().parent
def read(name):
    return json.loads((work / name).read_text(encoding='utf-8-sig'))
onboard = {case: read(case + '-373d98d.json') for case in ('uart-a', 'uart-b', 'twim-a', 'twim-b', 'm25-a', 'm25-b', 'm26-a', 'm26-b')}
assert all(value['status'] == 'passed' for value in onboard.values())
ble = {gate: read(gate + '-pair-18a7cbe.json') for gate in ('m19', 'm20', 'm21')}
assert all(value['status'] == 'passed' for value in ble.values())
host = (work / 'host-373d98d-powershell-path.log').read_text(encoding='utf-8-sig')
assert 'M12_GATE_PASS=host' in host and not re.search(r'^FAILED', host, re.M)
total = sum(int(n) for n in re.findall(r'^Ran (\d+) tests? in ', host, re.M))
skipped = sum(int(n) for n in re.findall(r'^OK \(skipped=(\d+)\)', host, re.M))
failures = [read(path.name) for path in sorted(work.glob('*-18a7cbe-failure.json'))]
result = {'onboard_source': '373d98da055b83e86b039448965d630e8d546497', 'onboard_runner_passes': len(onboard), 'onboard_case_passes': 18, 'uart_instance_results': 8, 'pmic_instance_results': 6, 'm25_results': 2, 'm26_results': 2, 'ble_source': '18a7cbec9cceed38d6c866131afdac9e6ffbc4b8', 'ble_pair_gates_passed': list(ble), 'first_attempt_failures_preserved': [{key: value[key] for key in ('case', 'error', 'core_revision')} for value in failures], 'host': {'total': total, 'passed': total-skipped, 'skipped': skipped, 'actual_installed_m13_separate_pass': 11}, 'onboard_measurements': {case: {key: value for key, value in record.items() if key in ('event_ticks', 'timer_ticks', 'vdd_raw', 'temperature_centi_celsius', 'reset_cause', 'reset_prefix_size', 'reset_ready_seconds', 'stream_linked', 'result')} for case, record in onboard.items() if case.startswith(('m25', 'm26'))}, 'external_current_source_T11': 'NOT RUN'}
(work / 'result-summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
