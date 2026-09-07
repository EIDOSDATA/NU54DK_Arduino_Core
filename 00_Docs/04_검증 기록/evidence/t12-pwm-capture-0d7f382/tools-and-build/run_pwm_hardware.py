"""! @brief 현재 사용자 확인을 exact 이미지에 묶어 기존 408 runner를 한 번 실행합니다. """
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
from serial.tools import list_ports

private = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))
keys = ('32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9',
        '4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0')
uids = [private[key].lower() for key in keys]
images = [pair.inspect_image(REPO, Path('C:/pwh04'), role) for role in (1, 2)]
assert all(image['core_revision'] == '054d08fc869cb4089434f02800b5c438c1407be9' for image in images)
available = {hashlib.sha256(p.unique_id.lower().encode('ascii')).hexdigest(): p.unique_id.lower()
             for p in ConnectHelper.get_all_connected_probes(blocking=False)}
assert all(available.get(key) == uid for key, uid in zip(keys, uids))
folder = WORK / 'pwm-hardware-054d08f'
folder.mkdir(exist_ok=True)
enumeration = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'probe_uid_sha256': sorted(available),
               'ports': [{'device': port.device, 'vid': port.vid, 'pid': port.pid,
                          'serial_sha256': hashlib.sha256((port.serial_number or '').lower().encode('ascii')).hexdigest()}
                         for port in list_ports.comports()]}
with (folder / 'enumeration.json').open('x', encoding='utf-8') as stream:
    json.dump(enumeration, stream, ensure_ascii=False, indent=2)
confirmation = fixture.confirmation_template(images, uids, 408)
for key in ('dap_uart_disconnected_both', 'swd_connected_both', 'power_rails_not_joined',
            'equal_io_voltage_confirmed', 'common_ground_confirmed', 'links_match_catalog',
            'pullups_match_catalog', 'extra_outputs_disconnected'):
    confirmation[key] = True
confirmation.update(confirmed_at_unix=time.time(), confirmed_by='eidos: current conversation reply',
                    user_reply='결선 완료.',
                    prompt_scope='USB 분리 후 B P1.14 -> A P1.14 및 GND만 연결, USB 재연결, 양쪽 DAP UART 분리/SWD 연결, 동일 I/O 전압, 전원 레일/다른 신호/외부 풀업 미연결')
fixture.validate_confirmation(confirmation, images, uids, 408)
confirmation_path = folder / 'confirmation.json'
with confirmation_path.open('x', encoding='utf-8') as stream:
    json.dump(confirmation, stream, ensure_ascii=False, indent=2)
print('Exact UID/image/current wiring checks passed; starting one controlled PWM campaign.', flush=True)
try:
    result = runner.main(['--dut', uids[0], '--peer', uids[1], '--build-root', 'C:/pwh04',
        '--pyocd', str(SDK / 'opt/bin/Scripts/pyocd.exe'), '--swd-frequency-hz', '10000000',
        '--fixture', '408', '--pwm-capture', '--execute-fixture',
        '--confirmation', str(confirmation_path), '--evidence', str(folder / 'attempt1.json')])
except Exception as error:
    message = f'{type(error).__name__}: {error}'
    for uid in uids:
        message = message.replace(uid, '[exact UID redacted]')
    print(message, flush=True)
    sys.exit(1)
sys.exit(result)
