"""! @brief 430 종료 뒤 reset 없이 source·역할·I2S 해제와 신호 핀을 확인합니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import v04_pair as pair
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
evidence = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'source': SOURCE,
    'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False,
    'fixture_commands_executed': False, 'devices': []}
with ProbeLocks(UIDS), ExitStack() as stack:
    for uid, digest, image in zip(UIDS, HASHES, images):
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
        assert session is not None
        stack.enter_context(session)
        target = session.target
        cpuid = target.read32(0xE000ED00)
        assert cpuid == 0x411FD210
        identity = bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64))
        pair.verify_identity(identity, image['role'], SOURCE)
        pin_cnf = {str(pin): target.read32(0x500D8280 + pin * 4) for pin in (4, 5, 6, 7)}
        i2s_enable = target.read32(0x500DD500)
        evidence['devices'].append({'role': image['role'], 'uid_sha256': digest,
            'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'],
            'runtime_identity_hex': identity.hex(), 'cpuid': hex(cpuid),
            'state': target.get_state().name, 'signal_pin_cnf': pin_cnf,
            'i2s_enable': i2s_enable, 'identity_status': 'passed'})
write_new(WORK / 'postflight.json', evidence)
assert all(device['i2s_enable'] == 0 for device in evidence['devices'])
assert all(value == 2 for device in evidence['devices'] for value in device['signal_pin_cnf'].values())
print('POSTFLIGHT_IDENTITY_AND_I2S_OFF_PASS=2;PINS_DEFAULT=8;NO_FLASH_RESET_OR_FIXTURE_COMMAND')
