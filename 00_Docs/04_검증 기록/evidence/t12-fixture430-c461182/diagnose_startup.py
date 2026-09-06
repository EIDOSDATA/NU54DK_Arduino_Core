"""! @brief 430 시작 padding을 width/channel별로 관측하며 기능 PASS로 합산하지 않습니다. """
from runtime import *
from contextlib import ExitStack
from elftools.elf.elffile import ELFFile
import struct
import v04_pair as pair
import v04_fixture as fixture
import v04_signal as signal
from v04_protocol import ProbeLocks, decode, SIZE

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
fixture.validate_confirmation(json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8')), images, UIDS, 430)
result = {'source': SOURCE, 'scope': 'startup-padding-diagnostic-only', 'functional_pass_claimed': False,
    'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False, 'cases': []}
devices = []
addresses = []
try:
    with ProbeLocks(UIDS), ExitStack() as stack:
        for uid, image in zip(UIDS, images):
            session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
            stack.enter_context(session)
            target = session.target
            pair.verify_identity(bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64)), image['role'], SOURCE)
            raw = bytes(target.read_memory_block8(image['symbols']['v04_response'], SIZE))
            words = struct.unpack('<32I', raw)
            nonce = raw[20:36]
            assert decode(raw, nonce, words[2], image['role'], 33) == (0, [0])
            device = pair.Device(target, image, nonce)
            device.sequence = words[2]
            devices.append(device)
            with image['elf'].open('rb') as stream:
                symbols = list(ELFFile(stream).get_section_by_name('.symtab').iter_symbols())
                matches = [sym for sym in symbols if 'i2s_rx' in sym.name and sym['st_size'] == 12288]
                assert len(matches) == 1
                addresses.append(int(matches[0]['st_value']))
        for controller in (1, 2):
            for width in (8, 16, 24, 32):
                for channels in (0, 1, 2):
                    vector = (16000, width, channels, 32, 1, 0x13579BDF)
                    row = {'controller': controller, 'vector': vector, 'receivers': [], 'cleanup': []}
                    result['cases'].append(row)
                    try:
                        for device in devices:
                            assert device.command(32, (430, 1, fixture.CONSENT, controller)) == [430, 10000]
                        for role in (controller, 3 - controller):
                            assert devices[role - 1].command(34, signal.arguments_for('i2s', vector)) == [0]
                        for role in (3 - controller, controller):
                            assert devices[role - 1].command(35) == [0]
                        for device, address in zip(devices, addresses):
                            status = signal.wait_status(device, lambda values: values[3] == 1)
                            raw_words = signal.read_u32(device, 32)
                            tail = list(device.target.read_memory_block32(address + 8192, 8))
                            received = raw_words + tail
                            seed = vector[5] ^ (0x5A5A5A5A if device.image['role'] == 1 else 0)
                            mask = 0xFFFFFF if width == 24 else 0xFFFFFFFF
                            expected = [signal.pattern(seed, index) & mask for index in range(32)]
                            offsets = [offset for offset in range(5) if [value & mask for value in received[offset:offset + 32]] == expected]
                            row['receivers'].append({'role': device.image['role'], 'status': status,
                                'raw_words': raw_words, 'tail': tail, 'diagnostic_matching_word_offsets': offsets})
                    finally:
                        for device in devices:
                            row['cleanup'].append({'role': device.image['role'], 'reply': device.command(33)})
                        assert all(item['reply'] == [0] for item in row['cleanup'])
                    print(json.dumps({'controller': controller, 'width': width, 'channels': channels,
                        'offsets': [item['diagnostic_matching_word_offsets'] for item in row['receivers']]}), flush=True)
        result['status'] = 'diagnostic-completed'
except BaseException as error:
    result['status'] = 'diagnostic-failed'
    result['error'] = str(error)
    raise
finally:
    write_new(WORK / 'startup-diagnostic.json', result)
