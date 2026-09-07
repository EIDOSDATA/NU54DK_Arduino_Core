"""! @brief 완료된 exact campaign의 두 runtime identity와 출력 해제를 읽기만 확인합니다. """
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys
from check_pc import REPO, WORK
logging.disable(logging.CRITICAL)
sys.path.insert(0, str(REPO / 'tests/hil/nu54dk'))
import v04_pair as pair
from v04_protocol import ProbeLocks
from pyocd.core.helpers import ConnectHelper

folder = WORK / 'pwm-hardware-0d7f382'
result = json.loads((folder / 'attempt1.json').read_text(encoding='utf-8'))
assert result['status'] in ('passed', 'failed')
images = [pair.inspect_image(REPO, Path('C:/pwq04'), role) for role in (1, 2)]
private = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))
uids = [private[device['uid_sha256']].lower() for device in result['devices']]
report = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'core_revision': images[0]['core_revision'], 'swd_frequency_hz': 10000000,
          'cmsis_dap.limit_packets': True, 'explicit_reset_halt_resume_flash': False, 'boards': []}
with ProbeLocks(uids):
    for uid, image in zip(uids, images):
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l',
            frequency=10000000, blocking=False, no_config=True,
            options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False,
                     'cmsis_dap.limit_packets': True})
        if session is None:
            raise RuntimeError('exact probe missing')
        with session:
            target = session.target
            raw = bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64))
            pair.verify_identity(raw, image['role'], image['core_revision'])
            row = {'role': image['role'], 'uid_sha256': hashlib.sha256(uid.encode()).hexdigest(),
                   'identity_raw_hex': raw.hex(), 'cpuid': f'0x{target.read32(0xE000ED00):08x}',
                   'state': target.get_state().name, 'backend_packets': session.probe._link._packet_count,
                   'pwm_enable': [target.read32(base + 0x500) for base in (0x500D2000, 0x500D3000, 0x500D4000)],
                   'dppi20_chen': target.read32(0x500C2500), 'p1_14_pin_cnf': target.read32(0x500D82B8)}
            report['boards'].append(row)
with (folder / 'postflight.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
assert all(row['cpuid'] == '0x411fd210' and row['backend_packets'] == 1 and row['pwm_enable'] == [0, 0, 0]
           and row['dppi20_chen'] == 0 and row['p1_14_pin_cnf'] == 2 for row in report['boards'])
print(json.dumps(report, indent=2))
