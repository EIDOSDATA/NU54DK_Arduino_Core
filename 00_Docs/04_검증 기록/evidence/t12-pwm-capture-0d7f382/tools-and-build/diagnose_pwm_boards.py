"""! @brief exact UID attach로 CPU·image와 PWM/DPPI/핀 해제 상태만 읽습니다. """
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
from serial.tools import list_ports

images = [pair.inspect_image(REPO, Path('C:/pwh04'), role) for role in (1, 2)]
private = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))
keys = ('32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9',
        '4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0')
uids = [private[key].lower() for key in keys]
available = {p.unique_id.lower() for p in ConnectHelper.get_all_connected_probes(blocking=False)}
assert set(uids).issubset(available)
report = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'frequency_hz': 10000000, 'method': 'locked exact UID attach/read only',
          'auto_unlock': False, 'explicit_reset_halt_resume_flash': False,
          'ports': [{'device': p.device, 'serial_sha256': hashlib.sha256((p.serial_number or '').lower().encode('ascii')).hexdigest()}
                    for p in list_ports.comports()], 'boards': []}
with ProbeLocks(uids):
    for uid, key, image in zip(uids, keys, images):
        row = {'role': image['role'], 'uid_sha256': key}
        try:
            session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l',
                frequency=10000000, blocking=False, no_config=True,
                options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
            if session is None:
                raise RuntimeError('exact probe missing')
            with session:
                target = session.target
                row['state_before'] = target.get_state().name
                row['cpuid'] = f'0x{target.read32(0xE000ED00):08x}'
                raw = bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64))
                row['identity_raw_hex'] = raw.hex()
                try:
                    pair.verify_identity(raw, image['role'], image['core_revision'])
                    row['current_identity_verified'] = True
                except pair.ProtocolError:
                    row['current_identity_verified'] = False
                row['pwm_enable'] = [target.read32(base + 0x500) for base in (0x500D2000, 0x500D3000, 0x500D4000)]
                row['dppi20_chen'] = target.read32(0x500C2500)
                row['p1_14_pin_cnf'] = target.read32(0x500D82B8)
                row['state_after'] = target.get_state().name
                row['swd_read_pass'] = row['cpuid'] == '0x411fd210'
        except Exception as error:
            message = str(error)
            for value in uids:
                message = message.replace(value, '[exact UID redacted]')
            row.update(swd_read_pass=False, error=f'{type(error).__name__}: {message}')
        report['boards'].append(row)
name = sys.argv[1]
assert Path(name).name == name and name.endswith('.json')
with (WORK / 'pwm-hardware-054d08f' / name).open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(0 if all(row['swd_read_pass'] for row in report['boards']) else 1)
