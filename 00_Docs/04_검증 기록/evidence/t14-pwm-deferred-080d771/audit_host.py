"""! @brief canonical Host 계획·그룹별 종료와 실제 PASS/SKIP 수를 원본 로그에서 대조합니다. """
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

work = Path(__file__).resolve().parent
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
label = sys.argv[1] if len(sys.argv) > 1 else 'host-all'
record = json.loads((work / (label + '.json')).read_text())
raw = (work / (label + '.log')).read_bytes()
text = raw.decode('utf-8').replace('\r\n', '\n')
assert hashlib.sha256(raw).hexdigest() == record['log_sha256']
assert record['source'] == '080d771ae48e83b4621f3160afed67395ead32cd' and not record['dirty']
planned = [p.name for p in sorted((repo / 'tests/host').glob('test_*.py')) if p.name != 'test_m10_packaging.py']
planned += ['test_ac03_storage.py', 'test_m24_uarte_onboard.py', 'test_m24_twim_onboard.py', 'test_m25_onboard.py', 'test_m26_onboard.py']
blocks = re.split(r'^\[M12\] exec: ', text, flags=re.M)[1:]
rows = []
for block in blocks:
    pattern = re.search(r'-p (test_[a-zA-Z0-9_]+\.py)', block).group(1)
    counts = re.findall(r'^Ran (\d+) tests? in ', block, flags=re.M)
    outcome = re.findall(r'^(OK(?: \(skipped=\d+\))?|FAILED[^\n]*)$', block, flags=re.M)
    skips = re.findall(r"^.*\.\.\. skipped (.+)$", block, flags=re.M)
    rows.append({'pattern': pattern, 'reported_tests': int(counts[-1]) if counts else None,
                 'outcome': outcome[-1] if outcome else None, 'skip_reasons': skips})
if record['returncode'] == 0:
    assert 'M12_GATE_PASS=host' in text
    assert [row['pattern'] for row in rows] == planned
    assert all(row['reported_tests'] is not None and row['outcome'].startswith('OK') for row in rows)
    assert not re.search(r'^FAILED|WinError 4551', text, flags=re.M)
tests = sum(row['reported_tests'] or 0 for row in rows)
skip_count = sum(len(row['skip_reasons']) for row in rows)
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
audit = {'source': record['source'], 'canonical_status': 'passed' if record['returncode'] == 0 else 'failed',
    'planned_groups': len(planned), 'executed_groups': len(rows), 'reported_tests': tests,
    'passed_tests': tests - skip_count if record['returncode'] == 0 else None, 'skipped_tests': skip_count,
    'groups': rows, 'log_sha256': record['log_sha256'], 'hardware_access': False,
    'security_policy_changed': False, 'scope': 'Host runner mocks are not physical board executions'}
(work / (label + '-audit.json')).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in audit.items() if k != 'groups'}, ensure_ascii=False))
print(json.dumps([row for row in rows if row['skip_reasons'] or not (row['outcome'] or '').startswith('OK')], ensure_ascii=False))
