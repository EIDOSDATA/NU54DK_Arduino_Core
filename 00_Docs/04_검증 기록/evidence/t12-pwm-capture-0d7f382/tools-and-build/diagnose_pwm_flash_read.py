"""! @brief A flash 원문을 두 USB packet 설정에서 읽기만 하여 불일치와 전송 실패를 구분합니다. """
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from check_pc import REPO, WORK
logging.disable(logging.CRITICAL)
sys.path.insert(0, str(REPO / 'tests/hil/nu54dk'))
import v04_pair as pair
from v04_protocol import ProbeLocks
from pyocd.core.helpers import ConnectHelper
from intelhex import IntelHex

image = pair.inspect_image(REPO, Path('C:/pwh04'), 1)
key = '32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9'
uid = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))[key].lower()
hexfile = IntelHex(str(image['path']))
segments = hexfile.segments()
assert all(0 <= begin < end <= 0x180000 for begin, end in segments)
report = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'uid_sha256': key, 'source': image['core_revision'], 'frequency_hz': 10000000,
          'explicit_flash_reset_halt_resume': False, 'observations': []}
with ProbeLocks([uid]):
    for limited in (False, True):
        row = {'cmsis_dap.limit_packets': limited, 'chunks': 0, 'bytes': 0, 'mismatched_bytes': 0}
        started = time.monotonic()
        digest = hashlib.sha256()
        try:
            session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l',
                frequency=10000000, blocking=False, no_config=True,
                options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False,
                         'cmsis_dap.limit_packets': limited})
            if session is None:
                raise RuntimeError('exact probe missing')
            with session:
                row['state_before'] = session.target.get_state().name
                row['backend_packets'] = session.probe._link._packet_count
                for begin, end in segments:
                    for address in range(begin, end, 4096):
                        if time.monotonic() - started > 90:
                            raise RuntimeError('bounded read duration exceeded')
                        size = min(4096, end - address)
                        actual = bytes(session.target.read_memory_block8(address, size))
                        expected = bytes(hexfile.tobinarray(start=address, size=size))
                        mismatch = [index for index, values in enumerate(zip(actual, expected)) if values[0] != values[1]]
                        row['chunks'] += 1
                        row['bytes'] += size
                        row['mismatched_bytes'] += len(mismatch)
                        if mismatch and 'first_mismatch_address' not in row:
                            row['first_mismatch_address'] = f'0x{address + mismatch[0]:08x}'
                        digest.update(actual)
                row['state_after'] = session.target.get_state().name
                row['read_complete'] = True
        except Exception as error:
            row.update(read_complete=False, error=f'{type(error).__name__}: {error}'.replace(uid, '[exact UID redacted]'))
        row.update(seconds=round(time.monotonic() - started, 3), read_sha256=digest.hexdigest())
        report['observations'].append(row)
        print(json.dumps(row), flush=True)
with (WORK / 'pwm-hardware-054d08f/flash-read-diagnostic.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
