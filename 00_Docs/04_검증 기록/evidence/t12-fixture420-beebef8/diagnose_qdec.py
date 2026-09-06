"""! @brief 동일 결선에서 유한 QDEC 파형과 입력 레지스터를 진단합니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import struct
import time
import v04_pair as pair
import v04_fixture as fixture
import v04_signal as signal
from v04_protocol import ProbeLocks, decode, SIZE

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
confirmation = json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8'))
fixture.validate_confirmation(confirmation, images, UIDS, 420)
result = {'source': SOURCE, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'scope': 'diagnostic-only-same-fixture420-finite-waveform',
          'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False,
          'register_writes': False, 'vector': [20, 20, 100, 10000, 0, 0],
          'devices': [], 'trace': [], 'cleanup': []}
devices = []

def registers(device):
    """! @brief 고정 SDK MDK의 GPIO/QDEC/PWM 레지스터를 읽습니다. """
    target = device.target
    pins = (4, 6) if device.image['role'] == 1 else (14, 10)
    values = {'gpio_in': target.read32(0x500D820C),
              'pin_cnf': {str(pin): target.read32(0x500D8280 + 4 * pin) for pin in pins}}
    base = 0x500E0000 if device.image['role'] == 1 else 0x500D2000
    offsets = (0x200, 0x300, 0x500, 0x508, 0x50C, 0x510, 0x514, 0x520, 0x524, 0x528, 0x544) if device.image['role'] == 1 else (0x500, 0x504, 0x508, 0x50C, 0x510, 0x514, 0x518, 0x560, 0x564)
    values['peripheral'] = {hex(offset): target.read32(base + offset) for offset in offsets}
    return values

try:
    with ProbeLocks(UIDS), ExitStack() as stack:
        try:
            for uid, digest, image in zip(UIDS, HASHES, images):
                session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
                assert session is not None
                stack.enter_context(session)
                target = session.target
                assert target.read32(0xE000ED00) == 0x411FD210
                pair.verify_identity(bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64)), image['role'], SOURCE)
                raw = bytes(target.read_memory_block8(image['symbols']['v04_response'], SIZE))
                words = struct.unpack('<32I', raw)
                assert words[4] == 33
                nonce = raw[20:36]
                assert decode(raw, nonce, words[2], image['role'], 33) == (0, [0])
                device = pair.Device(target, image, nonce)
                device.sequence = words[2]
                devices.append(device)
                result['devices'].append({'role': image['role'], 'uid_sha256': digest, 'continued_after_valid_disarm_sequence': words[2]})
            for device in devices:
                assert device.command(32, (420, 1, fixture.CONSENT, 2)) == [420, 10000]
            args = signal.arguments_for('qdec', result['vector'])
            assert devices[1].command(34, args) == [0]
            assert devices[0].command(34, args) == [0]
            result['ready'] = signal.wait_status(devices[0], lambda words: words[2] == 1)
            result['before'] = [registers(device) for device in devices]
            started = time.monotonic()
            assert devices[1].command(35) == [0]
            result['running'] = [registers(device) for device in devices]
            while time.monotonic() - started < 4.2:
                raw_in = devices[0].target.read32(0x500D820C)
                result['trace'].append([round(time.monotonic() - started, 6), raw_in, ((raw_in >> 4) & 1) | (((raw_in >> 6) & 1) << 1)])
                time.sleep(.001)
            result['complete'] = signal.wait_status(devices[1], lambda words: words[3] == 1)
            result['after'] = [registers(device) for device in devices]
            result['qdec_report'] = devices[0].command(37)
            result['status'] = 'diagnostic-completed'
        finally:
            for device in devices:
                item = {'role': device.image['role']}
                try:
                    item['reply'] = device.command(33)
                except BaseException as error:
                    item['error'] = str(error)
                result['cleanup'].append(item)
except BaseException as error:
    result['status'] = 'failed'
    result['error'] = str(error)
    raise
finally:
    result['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    write_new(WORK / 'qdec-diagnostic1.json', result)
    print(json.dumps({key: value for key, value in result.items() if key != 'trace'}, indent=2), flush=True)
    print('OBSERVED_A_PHASE_STATES=' + str(sorted({entry[2] for entry in result['trace']})))
