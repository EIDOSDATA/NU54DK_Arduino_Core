"""! @brief START 전 idle과 취소 cleanup을 같은 확인 결선에서 검사합니다. """
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
fixture.validate_confirmation(json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8')), images, UIDS, 420)
result = {'source': SOURCE, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'scope': 'fixture420-prepared-idle-and-cancel-before-start',
          'swd_frequency_hz': 10000000, 'flash_executed': False, 'reset_executed': False,
          'start_command_executed': False, 'cases': [], 'devices': []}
devices = []

def output_snapshot(target):
    """! @brief B 송신 두 핀의 OUT latch와 전체 PIN_CNF를 읽습니다. """
    return {'out': target.read32(0x500D8200) & ((1 << 14) | (1 << 10)),
            'pin14': target.read32(0x500D8280 + 4 * 14),
            'pin10': target.read32(0x500D8280 + 4 * 10)}

try:
    with ProbeLocks(UIDS), ExitStack() as stack:
        for uid, digest, image in zip(UIDS, HASHES, images):
            session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
            assert session is not None
            stack.enter_context(session)
            target = session.target
            assert target.read32(0xE000ED00) == 0x411FD210
            pair.verify_identity(bytes(target.read_memory_block8(image['symbols']['v04_identity'], 64)), image['role'], SOURCE)
            raw = bytes(target.read_memory_block8(image['symbols']['v04_response'], SIZE))
            words = struct.unpack('<32I', raw)
            nonce = raw[20:36]
            assert words[4] == 33 and decode(raw, nonce, words[2], image['role'], 33) == (0, [0])
            device = pair.Device(target, image, nonce)
            device.sequence = words[2]
            devices.append(device)
            result['devices'].append({'role': image['role'], 'uid_sha256': digest, 'continued_after_valid_disarm_sequence': words[2]})
        for pwm in (20, 21, 22):
            for qdec in (20, 21):
                case = {'pwm': pwm, 'qdec': qdec, 'cleanup': []}
                case['source_before'] = output_snapshot(devices[1].target)
                result['cases'].append(case)
                try:
                    for device in devices:
                        assert device.command(32, (420, 1, fixture.CONSENT, 2)) == [420, 10000]
                    args = signal.arguments_for('qdec', (pwm, qdec, 100, 2000, 0, 0))
                    assert devices[1].command(34, args) == [0]
                    assert devices[0].command(34, args) == [0]
                    time.sleep(.020)
                    case['controller_status'] = devices[1].command(36)
                    case['receiver_gpio_in'] = devices[0].target.read32(0x500D820C)
                    case['idle_qdec_report'] = devices[0].command(37)
                    case['source_prepared'] = output_snapshot(devices[1].target)
                    assert case['source_prepared'] == {'out': 0, 'pin14': 3, 'pin10': 3}
                    assert case['controller_status'][:5] == [1, 0, 1, 0, 0]
                    assert case['receiver_gpio_in'] & ((1 << 4) | (1 << 6)) == 0
                    assert case['idle_qdec_report'] == [0, 0, 0]
                    case['status'] = 'passed'
                finally:
                    for device in devices:
                        entry = {'role': device.image['role']}
                        try:
                            entry['reply'] = device.command(33)
                        except BaseException as error:
                            entry['error'] = str(error)
                        case['cleanup'].append(entry)
                    assert case['cleanup'] == [{'role': 1, 'reply': [0]}, {'role': 2, 'reply': [0]}]
                    case['source_after'] = output_snapshot(devices[1].target)
                    assert case['source_after'] == case['source_before']
        result['status'] = 'passed'
except BaseException as error:
    result['status'] = 'failed'
    result['error'] = str(error)
    raise
finally:
    result['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    write_new(WORK / 'prepared-cancel.json', result)
    print(json.dumps(result, indent=2), flush=True)
