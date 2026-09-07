"""! @brief 업로드 timeout 뒤 reset/flash 없이 지정 두 보드의 읽기 응답을 확인합니다. """
from runtime import *
from datetime import datetime, timezone
from v04_protocol import ProbeLocks

evidence = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'swd_frequency_hz': 10000000,
    'flash_executed': False, 'reset_executed': False, 'fixture_commands_executed': False, 'devices': []}
with ProbeLocks(UIDS):
    for role, uid, digest in zip((1, 2), UIDS, HASHES):
        row = {'role': role, 'uid_sha256': digest}
        try:
            session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l',
                frequency=10000000, blocking=False, no_config=True,
                options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
            assert session is not None
            with session:
                row['cpuid'] = hex(session.target.read32(0xE000ED00))
                row['state'] = session.target.get_state().name
                row['passed'] = row['cpuid'] == '0x411fd210'
        except Exception as error:
            row.update(passed=False, error=str(error))
        evidence['devices'].append(row)
write_new(WORK / 'readback-after-timeout3.json', evidence)
assert all(row['passed'] for row in evidence['devices']), evidence['devices']
print('READ_ONLY_CPUID_PASS=2;RETRY_ELIGIBLE')
