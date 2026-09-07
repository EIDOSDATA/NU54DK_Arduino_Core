"""! @brief 사용자 재연결과 읽기 회복 뒤 기존 실패와 분리한 한 번의 새 시험입니다. """
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from check_pc import REPO, WORK, SDK
logging.disable(logging.CRITICAL)
sys.path.insert(0, str(REPO / 'tests/hil/nu54dk'))
import v04_pair as pair
import v04_fixture as fixture
import v04_signal_run as runner
from pyocd.core.helpers import ConnectHelper

folder = WORK / 'pwm-hardware-054d08f'
diagnostic = json.loads((folder / 'diagnostic-after-reconnect.json').read_text(encoding='utf-8'))
assert all(row['swd_read_pass'] and row['pwm_enable'] == [0, 0, 0] and row['p1_14_pin_cnf'] == 2
           for row in diagnostic['boards'])
assert (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(diagnostic['observed_at_utc'])).total_seconds() < 180
images = [pair.inspect_image(REPO, Path('C:/pwh04'), role) for role in (1, 2)]
private = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))
keys = [row['uid_sha256'] for row in diagnostic['boards']]
uids = [private[key].lower() for key in keys]
available = {probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)}
assert set(uids).issubset(available)
confirmation = json.loads((folder / 'confirmation.json').read_text(encoding='utf-8'))
fixture.validate_confirmation(confirmation, images, uids, 408)
confirmation['previous_confirmed_at_unix'] = confirmation['confirmed_at_unix']
confirmation['confirmed_at_unix'] = time.time()
confirmation['reconnection_reply'] = '방금전 분리 후 재 연결했어.'
confirmation['reconnection_scope'] = '기존 P1.14 및 GND 결선과 SWD 스위치를 유지한 두 USB 재연결'
confirmation_path = folder / 'confirmation-after-reconnect.json'
with confirmation_path.open('x', encoding='utf-8') as stream:
    json.dump(confirmation, stream, ensure_ascii=False, indent=2)
fixture.validate_confirmation(confirmation, images, uids, 408)
print('Two exact UID reads recovered; beginning one fresh campaign after user USB reconnect.', flush=True)
try:
    result = runner.main(['--dut', uids[0], '--peer', uids[1], '--build-root', 'C:/pwh04',
        '--pyocd', str(SDK / 'opt/bin/Scripts/pyocd.exe'), '--swd-frequency-hz', '10000000',
        '--fixture', '408', '--pwm-capture', '--execute-fixture',
        '--confirmation', str(confirmation_path), '--evidence', str(folder / 'attempt2.json')])
except Exception as error:
    message = f'{type(error).__name__}: {error}'
    for uid in uids:
        message = message.replace(uid, '[exact UID redacted]')
    print(message, flush=True)
    sys.exit(1)
sys.exit(result)
