"""! @brief flash/reset 없이 종료 CPU와 exact firmware identity를 읽습니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import v04_pair as pair
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
evidence = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'source': SOURCE, 'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False, 'fixture_commands_executed': False, 'devices': []}
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
        pins = (4, 6) if image['role'] == 1 else (14, 10)
        pin_cnf = {str(pin): target.read32(0x500D8280 + pin * 4) for pin in pins}
        pwm_enable = {str(instance): target.read32(0x500D2500 + (instance - 20) * 0x1000) for instance in (20, 21, 22)}
        qdec_enable = {str(instance): target.read32(0x500E0500 + (instance - 20) * 0x1000) for instance in (20, 21)}
        assert all(value == 2 for value in pin_cnf.values())
        assert all(value == 0 for value in (*pwm_enable.values(), *qdec_enable.values()))
        evidence['devices'].append({'role': image['role'], 'uid_sha256': digest, 'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'], 'runtime_identity_hex': identity.hex(), 'cpuid': hex(cpuid), 'state': target.get_state().name, 'status': 'passed', 'signal_pin_cnf': pin_cnf, 'pwm_enable': pwm_enable, 'qdec_enable': qdec_enable})
write_new(WORK / 'postflight.json', evidence)
print('POSTFLIGHT_IDENTITY_PASS=2;NO_FLASH_RESET_OR_FIXTURE_COMMAND', flush=True)
