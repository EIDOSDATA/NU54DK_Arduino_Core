"""! @brief 실패한 준비 취소의 B 자원을 제어 리셋으로 회수하며 파형을 재실행하지 않습니다. """
from runtime import *
from datetime import datetime, timezone
import time
import v04_pair as pair
from v04_protocol import ProbeLocks, MAGIC

image = json.loads((WORK / 'exact-images.json').read_text(encoding='utf-8'))[1]
assert image['role'] == 2 and image['core_revision'] == SOURCE
assert pair.sha256_file(Path(image['path'])) == image['sha256']
result = {'source': SOURCE, 'role': 2, 'uid_sha256': HASHES[1], 'reason': 'prepared PWM cancellation STOP timeout; cleanup only, no test retry',
          'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': True,
          'fixture_commands_executed': False, 'started_at_utc': datetime.now(timezone.utc).isoformat()}
with ProbeLocks(UIDS):
    session = ConnectHelper.session_with_chosen_probe(unique_id=UIDS[1], target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
    assert session is not None
    with session:
        target = session.target
        pair.verify_identity(bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64)), 2, SOURCE)
        assert target.read32(0xE000ED00) == 0x411FD210
        target.reset_and_halt()
        assert target.get_state().name == 'HALTED'
        for address in image['symbols'].values():
            target.write32(address, 0)
        target.flush()
        target.resume()
        deadline = time.monotonic() + 5
        while target.read32(image['symbols']['v04_identity']) != MAGIC:
            assert time.monotonic() < deadline, 'cleanup boot identity timeout'
            time.sleep(.01)
        pair.verify_identity(bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64)), 2, SOURCE)
        result['pwm_enable'] = {str(instance): target.read32(0x500D2500 + (instance - 20) * 0x1000) for instance in (20, 21, 22)}
        result['pin_cnf'] = {str(pin): target.read32(0x500D8280 + pin * 4) for pin in (14, 10)}
        assert all(value == 0 for value in result['pwm_enable'].values())
        assert all(value == 2 for value in result['pin_cnf'].values())
        result['cpu_state'] = target.get_state().name
        result['status'] = 'cleanup-by-controlled-reset-verified'
result['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
write_new(WORK / 'cleanup-reset.json', result)
print('B_CONTROLLED_RESET_CLEANUP_PASS;PWM_DISABLED=3;PINS_DEFAULT=2;NO_FLASH_OR_FIXTURE_COMMAND')
