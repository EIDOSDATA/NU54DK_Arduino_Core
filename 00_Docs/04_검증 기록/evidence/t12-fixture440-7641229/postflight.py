"""! @brief reset 없이 exact identity·PDM/SPIS 해제와 440 신호 핀 복원을 확인합니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import v04_pair as pair
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
evidence = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'source': SOURCE,
    'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False,
    'fixture_commands_executed': False,
    'register_definition': 'Fixed SDK nrf54l15_global.h / nrf54l15_types.h; ENABLE offset 0x500',
    'devices': []}
with ProbeLocks(UIDS), ExitStack() as stack:
    for uid, digest, image in zip(UIDS, HASHES, images):
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l',
            frequency=10000000, blocking=False, no_config=True,
            options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
        assert session is not None
        stack.enter_context(session)
        target = session.target
        cpuid = target.read32(0xE000ED00)
        assert cpuid == 0x411FD210
        identity = bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64))
        pair.verify_identity(identity, image['role'], SOURCE)
        pin_cnf = {str(pin): target.read32(0x500D8280 + pin * 4) for pin in (4, 5, 6, 7)}
        enable = {name: target.read32(address) for name, address in
            [('PDM20', 0x500D0500), ('PDM21', 0x500D1500), ('SPIS21', 0x500C7500),
             ('GPIOTE20_CONFIG0', 0x500DA510), ('GPIOTE20_CONFIG1', 0x500DA514),
             ('GPIOTE20_PUBLISH_IN0', 0x500DA180), ('GPIOTE20_SUBSCRIBE_OUT1', 0x500DA084)]}
        enable['DPPI20_CHANNEL0'] = target.read32(0x500C2500) & 1
        evidence['devices'].append({'role': image['role'], 'uid_sha256': digest,
            'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'],
            'runtime_identity_hex': identity.hex(), 'cpuid': hex(cpuid),
            'state': target.get_state().name, 'signal_pin_cnf': pin_cnf,
            'peripheral_enable': enable, 'identity_status': 'passed'})
write_new(WORK / 'postflight.json', evidence)
assert all(v == 0 for d in evidence['devices'] for v in d['peripheral_enable'].values())
startup = json.loads((WORK / 'startup-pins.json').read_text(encoding='utf-8'))
for device, initial in zip(evidence['devices'], startup['devices']):
    assert device['role'] == initial['role']
    for pin, value in device['signal_pin_cnf'].items():
        assert value in (0, 2, initial['pin_cnf'][pin]) and (value & 1) == 0

print('POSTFLIGHT_IDENTITY_PDM_SPIS_GPIOTE_DPPI_OFF_PASS=2;PINS_INPUT_DEFAULT_OR_ORIGINAL=8')
