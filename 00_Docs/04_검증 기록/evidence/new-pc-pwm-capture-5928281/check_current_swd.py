"""! @brief 새 PC에서 정확한 두 UID의 SWD 읽기 응답만 확인합니다. """
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys

logging.disable(logging.CRITICAL)
WORK = Path(__file__).resolve().parent
REPO = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
sys.path.insert(0, str(REPO / 'tests/hil/nu54dk'))
from v04_protocol import ProbeLocks
from pyocd.core.helpers import ConnectHelper

private = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))
expected = {
    'A': '32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9',
    'B': '4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0',
}
current = {hashlib.sha256(p.unique_id.lower().encode('ascii')).hexdigest(): p.unique_id
           for p in ConnectHelper.get_all_connected_probes(blocking=False)}
assert all(key in current and current[key].lower() == private[key].lower() for key in expected.values())
report = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'method': 'exact UID, locked, attach, CPUID/DHCSR read; no explicit reset/halt/resume/flash',
          'frequency_hz': 10000000, 'auto_unlock': False, 'resume_on_disconnect': False,
          'mass_erase_requested': False, 'external_signal_test': 'NOT RUN', 'boards': []}
with ProbeLocks([current[key] for key in expected.values()]):
    for role, key in expected.items():
        entry = {'role': role, 'uid_sha256': key}
        try:
            session = ConnectHelper.session_with_chosen_probe(
                unique_id=current[key], target_override='nrf54l', frequency=10000000,
                blocking=False, no_config=True,
                options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
            if session is None:
                raise RuntimeError('exact probe not found')
            with session:
                target = session.target
                entry['state_before'] = target.get_state().name
                entry['cpuid'] = f'0x{target.read32(0xE000ED00):08x}'
                entry['dhcsr'] = f'0x{target.read32(0xE000EDF0):08x}'
                entry['state_after'] = target.get_state().name
                entry['pass'] = entry['cpuid'] == '0x411fd210'
        except Exception as error:
            detail = str(error)
            for uid in current.values():
                detail = detail.replace(uid, '[exact UID redacted]').replace(uid.lower(), '[exact UID redacted]')
            entry.update({'pass': False, 'error_type': type(error).__name__, 'error': detail})
        report['boards'].append(entry)
        (WORK / 'current-swd.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(0 if all(board['pass'] for board in report['boards']) else 1)
