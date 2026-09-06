"""! @brief 취소 실패 뒤 보존된 image와 실행 identity를 읽기 전용으로 대조합니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import v04_pair as pair
from v04_protocol import ProbeLocks

images = json.loads((WORK / 'exact-images.json').read_text(encoding='utf-8'))
result = {'source': SOURCE, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
          'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False,
          'fixture_commands_executed': False, 'b_cleanup_confirmed': False,
          'purpose': 'read-only snapshot after cancelled prepared PWM; not cleanup PASS', 'devices': []}
with ProbeLocks(UIDS), ExitStack() as stack:
    for uid, digest, image in zip(UIDS, HASHES, images):
        assert image['core_revision'] == SOURCE
        assert pair.sha256_file(Path(image['path'])) == image['sha256']
        assert pair.sha256_file(Path(image['elf'])) == image['elf_sha256']
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
        assert session is not None
        stack.enter_context(session)
        target = session.target
        identity = bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64))
        pair.verify_identity(identity, image['role'], SOURCE)
        cpuid = target.read32(0xE000ED00)
        assert cpuid == 0x411FD210
        result['devices'].append({'role': image['role'], 'uid_sha256': digest, 'identity': identity.hex(),
            'cpuid': hex(cpuid), 'state': target.get_state().name,
            'pin14_cnf': target.read32(0x500D8280 + 4 * 14), 'pin10_cnf': target.read32(0x500D8280 + 4 * 10),
            'gpio_out_mask': target.read32(0x500D8200) & ((1 << 14) | (1 << 10)),
            'pwm20_enable': target.read32(0x500D2500)})
write_new(WORK / 'postflight-stored.json', result)
print('READ_ONLY_FC9F153_IDENTITY_PASS=2;B_CANCEL_STOP_REMAINS_UNPROVEN')
