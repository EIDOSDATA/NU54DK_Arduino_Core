"""! @brief 최초 DUT flash 실패 뒤 USB와 SWD 읽기를 한 번만 확인합니다. """
from runtime import *
from datetime import datetime, timezone
from serial.tools import list_ports
from m24_uarte_onboard import matching_port_names
from v04_protocol import ProbeLocks

result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'kind': 'bounded-post-flash-failure-read-only', 'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False, 'fixture_commands_executed': False, 'devices': []}
with ProbeLocks(UIDS):
    for uid, digest, role in zip(UIDS, HASHES, (1, 2)):
        row = {'role': role, 'uid_sha256': digest, 'com_ports': matching_port_names(list_ports.comports(), uid)}
        result['devices'].append(row)
        try:
            session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
            assert session is not None
            with session:
                target = session.target
                cpuid = target.read32(0xE000ED00)
                row.update({'cpuid': hex(cpuid), 'state': target.get_state().name, 'status': 'passed' if cpuid == 0x411FD210 else 'unexpected-cpuid'})
        except Exception as error:
            row.update({'status': 'failed', 'error': type(error).__name__ + ': ' + str(error)})
        print(json.dumps(row), flush=True)
write_new(WORK / 'probe-diagnostic.json', result)
print('PROBE_READ_ONLY_DIAGNOSTIC_COMPLETE', flush=True)
