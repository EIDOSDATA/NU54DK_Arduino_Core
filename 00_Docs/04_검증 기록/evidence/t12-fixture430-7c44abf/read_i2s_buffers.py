"""! @brief 종료된 첫 I2S 시험의 RAM buffer를 reset·새 신호 없이 읽어 배치를 진단합니다. """
from runtime import *
from contextlib import ExitStack
from elftools.elf.elffile import ELFFile
import v04_pair as pair
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
result = {'source': SOURCE, 'flash_executed': False, 'reset_executed': False, 'fixture_commands_executed': False,
    'swd_frequency_hz': 10000000, 'devices': []}
with ProbeLocks(UIDS), ExitStack() as stack:
    for uid, image in zip(UIDS, images):
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
        stack.enter_context(session)
        target = session.target
        pair.verify_identity(bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64)), image['role'], SOURCE)
        row = {'role': image['role'], 'buffers': {}}
        with image['elf'].open('rb') as stream:
            symbols = list(ELFFile(stream).get_section_by_name('.symtab').iter_symbols())
            for name in ('i2s_rx', 'i2s_tx'):
                candidates = [symbol for symbol in symbols if name in symbol.name and symbol['st_size'] == 16384]
                assert len(candidates) == 1
                address = int(candidates[0]['st_value'])
                assert 0x20000000 <= address <= 0x20040000 - 16384
                row['buffers'][name] = {'address': address,
                    'slot0': list(target.read_memory_block32(address, 40)),
                    'tail': list(target.read_memory_block32(address + 8192, 16))}
        result['devices'].append(row)
write_new(WORK / 'i2s-buffer-diagnostic.json', result)
for row in result['devices']:
    print(json.dumps({'role': row['role'], 'rx0': [hex(value) for value in row['buffers']['i2s_rx']['slot0'][:8]],
        'tx0': [hex(value) for value in row['buffers']['i2s_tx']['slot0'][:8]],
        'rx_tail': [hex(value) for value in row['buffers']['i2s_rx']['tail'][:4]]}))

