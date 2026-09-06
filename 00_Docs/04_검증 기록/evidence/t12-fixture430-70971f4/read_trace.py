"""! @brief 정지된 430의 RAM 추적을 새 신호나 reset 없이 읽습니다. """
from runtime import *
from contextlib import ExitStack
from elftools.elf.elffile import ELFFile
import v04_pair as pair
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
result = {'source': SOURCE, 'swd_frequency_hz': 10000000, 'flash_executed': False,
    'reset_executed': False, 'fixture_commands_executed': False,
    'columns': ['since_start_us', 'phase', 'a', 'b', 'c', 'd'],
    'phases': {'100': 'start-enter', '101': 'start-return a=success', '200': 'first-service',
        '300': 'queue-return a=slot b=result c=elapsed_us',
        '400': 'event a=type b=next-slot c=amount d=error',
        '500': 'stop-enter', '501': 'stop-return a=result'},
    'event_types': {'0': 'buffers-needed', '1': 'buffers-complete', '2': 'stopped', '3': 'underrun', '4': 'error'},
    'devices': []}
with ProbeLocks(UIDS), ExitStack() as stack:
    for uid, image in zip(UIDS, images):
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
        stack.enter_context(session)
        target = session.target
        pair.verify_identity(bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64)), image['role'], SOURCE)
        with image['elf'].open('rb') as stream:
            symbols = list(ELFFile(stream).get_section_by_name('.symtab').iter_symbols())
            matches = [s for s in symbols if 'i2s_trace' in s.name and s['st_size'] == 768]
            counters = [s for s in symbols if 'i2s_trace_count' in s.name and s['st_size'] == 4]
            assert len(matches) == len(counters) == 1
            address, counter = int(matches[0]['st_value']), int(counters[0]['st_value'])
            assert 0x20000000 <= address <= 0x20040000 - 768
            assert 0x20000000 <= counter <= 0x20040000 - 4
            count = target.read32(counter)
            assert count <= 32
            data = list(target.read_memory_block32(address, count * 6))
        row = {'role': image['role'], 'count': count, 'entries': [data[n:n+6] for n in range(0, len(data), 6)]}
        result['devices'].append(row)
        print(json.dumps(row))
write_new(WORK / 'timing-trace.json', result)
