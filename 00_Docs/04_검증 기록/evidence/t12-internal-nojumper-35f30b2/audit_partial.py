"""! @brief 첫 실패의 선행 PASS와 실패·미실행 범위를 별도로 고정합니다. """
from pathlib import Path
import hashlib
import json
import sys

work = Path(__file__).parent
sys.path.insert(0, 'C:/Users/eidos/GitHub/NU54DK_Arduino_Core/tests/hil/nu54dk')
import v04_nojumper as hil
data = json.loads((work / 'hardware-attempt1.json').read_text(encoding='utf-8'))
raw = (work / 'hardware-attempt1.json.jsonl').read_bytes()
rows = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
assert data['status'] == 'failed' and len(data['devices']) == 1
assert data['devices'][0]['passed'] == 888 and len(rows) == 889
assert len({row['request'][1] for row in rows}) == 1
for sequence, row in enumerate(rows[:-1], 1):
    assert row['request'][0] == sequence
    assert row['request'][2:] == data['plan'][sequence - 1]
    hil.validate_reply(row['request'], row['reply'])
    if row['request'][2] == 2:
        hil.validate_adc_snapshot(row['request'], row['reply'], bytes.fromhex(row['adc_snapshot_hex']))
failed = rows[-1]
assert failed['request'][2:] == [6, 1000, 0, 100, 0, 1]
assert failed['reply'][2] == 4 and failed['reply'][12:17] == [995, 995, 1, 1, 16]
assert failed['reply'][21] == 0
cleanup = data['devices'][0]['controlled_failure_cleanup']
assert cleanup['state'] == 'HALTED' and cleanup['pwm_enable'] == [0, 0, 0]
assert cleanup['saadc_enable'] == 0 and cleanup['dppi_channels'] == [0, 0, 0, 0]
output = {'source': data['source'], 'status': 'failed-preserved', 'completed_commands': 888,
          'failed_commands': 1, 'not_run_commands_a': 15, 'not_run_commands_b': 904,
          'last_failed_reply': failed, 'controlled_failure_cleanup': cleanup,
          'journal_sha256': hashlib.sha256(raw).hexdigest(),
          'cause': 'New HIL busy-wait minimum ignored the existing V04-EVENT five-percent clock tolerance',
          'not_reclassified_as_pass': True}
(work / 'hardware-partial-audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('FIRST_FAILURE_PRESERVED;A_888_PASS_1_FAIL_15_NOT_RUN;B_904_NOT_RUN')
