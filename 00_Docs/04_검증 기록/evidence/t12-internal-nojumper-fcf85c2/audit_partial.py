"""! @brief 두 번째 실행의 A 전체 PASS와 B 양자화 실패를 당시 판정기로 보존합니다. """
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys

work = Path(__file__).parent
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
sys.path.insert(0, str(repo / 'tests/hil/nu54dk'))
source = 'fcf85c2d440b9d389bf08eb42f2f0971a9bdf510'
raw_module = subprocess.check_output(['git', 'show', source + ':tests/hil/nu54dk/v04_nojumper.py'], cwd=repo)
module_path = work / 'original_oracle.py'
module_path.write_bytes(raw_module)
spec = importlib.util.spec_from_file_location('original_fcf85c2_oracle', module_path)
hil = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hil)
data = json.loads((work / 'hardware-attempt1.json').read_text(encoding='utf-8'))
raw = (work / 'hardware-attempt1.json.jsonl').read_bytes()
rows = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
assert data['status'] == 'failed' and data['source'] == source and len(data['devices']) == 2
first, second = data['devices']
assert first['passed'] == 904 and second['passed'] == 0 and len(rows) == 905
a = [row for row in rows if row['uid_sha256'] == first['uid_sha256']]
b = [row for row in rows if row['uid_sha256'] == second['uid_sha256']]
assert len(a) == 904 and len(b) == 1 and len({row['request'][1] for row in a}) == 1
for sequence, row in enumerate(a, 1):
    assert row['request'][0] == sequence and row['request'][2:] == data['plan'][sequence - 1]
    hil.validate_reply(row['request'], row['reply'])
    if row['request'][2] == 2:
        hil.validate_adc_snapshot(row['request'], row['reply'], bytes.fromhex(row['adc_snapshot_hex']))
post = first['postflight']
assert post['ready'] == [hil.MAGIC, 2, 904, 0]
assert post['pwm_enable'] == [0, 0, 0] and post['dppi_channels'] == [0, 0, 0, 0]
assert post['saadc_enable'] == 0 and post['p1_14_pin_cnf'] == 2
failed = b[0]
assert failed['reply'][2] == 4 and failed['reply'][12:17] == [997, 1011, 0, 2, 13]
assert failed['reply'][21] == 66
cleanup = second['controlled_failure_cleanup']
assert cleanup['state'] == 'HALTED' and cleanup['dppi_channels'] == [0, 0, 0, 0]
output = {'source': source, 'status': 'failed-preserved', 'a_commands_passed': 904,
          'b_commands_passed': 0, 'b_failed_commands': 1, 'b_not_run_commands': 903,
          'b_successful_repetitions_in_failed_command': 66,
          'failed_reply': failed, 'a_postflight': post, 'b_controlled_failure_cleanup': cleanup,
          'journal_sha256': hashlib.sha256(raw).hexdigest(),
          'cause': 'Millis integer comparison omitted the distinct observation windows and 32us kernel tick',
          'not_reclassified_as_pass': True}
(work / 'hardware-partial-audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('SECOND_FAILURE_PRESERVED;A_904_PASS;B_0_PASS_1_FAIL_903_NOT_RUN')
