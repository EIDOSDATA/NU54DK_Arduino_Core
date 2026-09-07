"""! @brief PDM 4개 안정화·100개 연속 버퍼를 실제 DMA 통계로 검증합니다. """
import itertools
import sys
import v04_fixture as fixture
import v04_signal as signal
from v04_protocol import ProtocolError


def signed(value, bits=32):
    return value if value < 1 << (bits - 1) else value - (1 << bits)


def received(records, vector):
    """! @brief 전체 반환 순서·길이와 안정화 뒤 채널 부호를 독립 판정합니다. """
    count, stereo = vector[1], vector[3]
    if len(records) != 104:
        raise ProtocolError("PDM continuous completion count mismatch")
    sums = [0, 0]
    for index, row in enumerate(records):
        if len(row) != 8 or row[:3] != [index, index % 4, count]:
            raise ProtocolError("PDM continuous order/slot/length mismatch")
        if any(type(word) is not int or not 0 <= word <= 0xFFFFFFFF for word in row):
            raise ProtocolError("PDM continuous malformed statistics")
        for channel in range(2 if stereo else 1):
            lo = signed(row[5 + channel] & 65535, 16)
            hi = signed(row[5 + channel] >> 16, 16)
            value = signed(row[3 + channel])
            samples = count // (2 if stereo else 1)
            if lo > hi or not lo * samples <= value <= hi * samples:
                raise ProtocolError("PDM continuous invalid sample statistics")
            if index >= 4:
                sums[channel] += value
    means = [value / (100 * count // (2 if stereo else 1)) for value in sums]
    if stereo:
        sign = 1 if ((not vector[4]) != (vector[2] == 75)) else -1
        if not means[0] * sign > 0 or not means[1] * -sign > 0:
            raise ProtocolError(f"PDM continuous stereo polarity mismatch: {means}")
    return {'measured_channel_means': means[:2 if stereo else 1],
            'settle_buffers': 4, 'measured_buffers': 100, 'completed_buffers': 104,
            'samples_per_buffer': count, 'guard_checked_on_device': True,
            'scope': 'continuous-stereo-edge-locked-opposite-levels' if stereo else
                     'continuous-mono-spis-density', 'buffer_statistics': records}


def run_confirmed(devices, images, uids, confirmation, fixture_id, append, repetitions=1):
    """! @brief gate HIGH부터 준비하고 같은 전송을 끊지 않은 채 104개 buffer를 받습니다. """
    selected = fixture.validate_confirmation(confirmation, images, uids, fixture_id)
    if selected['id'] != 440 or type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ProtocolError("invalid continuous PDM campaign")
    vectors = list(itertools.product((20, 21), (256, 1024), (25, 50, 75), (0, 1), (0, 1)))
    for repetition in range(repetitions):
        for controller_role in (1, 2):
            controller, receiver = devices[controller_role - 1], devices[2 - controller_role]
            density_means = {}
            for vector in vectors:
                fixture.validate_confirmation(confirmation, images, uids, fixture_id)
                try:
                    for device in devices:
                        if device.command(32, (440, 1, fixture.CONSENT, controller_role)) != [440, 10000]:
                            raise ProtocolError("continuous PDM arm failed")
                    args = (*vector, 2, 100, 4)
                    for device in (receiver, controller):
                        if device.command(34, args) != [0]:
                            raise ProtocolError("continuous PDM prepare failed")
                        signal.wait_status(device, lambda words: words[2] == 1)
                    if receiver.command(35) != [0]:
                        raise ProtocolError("continuous PDM start failed")
                    status = signal.wait_status(receiver, lambda words: words[3] == 1, timeout=9.0)
                    if status != [1, 1, 1, 1, 0, 104 * vector[1], vector[1], 0]:
                        raise ProtocolError(f"continuous PDM status mismatch: {status}")
                    records = [receiver.command(39, (index,)) for index in range(104)]
                    result = received(records, vector)
                    append(f'V04-PDM-CONTINUOUS/440/{controller_role}/{vector}/repeat-{repetition + 1}',
                           {'receiver_status': status, **result})
                    if not vector[3]:
                        density_means.setdefault((vector[0], vector[1], vector[4]), {})[vector[2]] = result['measured_channel_means'][0]
                finally:
                    original_error = sys.exception()
                    cleanup = []
                    for device in devices:
                        try:
                            cleanup.append({'role': device.image['role'], 'result': device.command(33)})
                        except BaseException as error:
                            cleanup.append({'role': device.image['role'], 'error': str(error)})
                    append('V04-PDM-CONTINUOUS-CLEANUP', {'status': 'cleanup', 'results': cleanup})
                    if any(row.get('result') != [0] for row in cleanup):
                        if original_error is not None:
                            original_error.add_note(f'continuous PDM cleanup unproven: {cleanup}')
                        else:
                            raise ProtocolError(f'continuous PDM cleanup unproven: {cleanup}')
            for key, means in density_means.items():
                if set(means) != {25, 50, 75} or not means[25] < means[50] < means[75]:
                    raise ProtocolError(f'continuous PDM density ordering mismatch {key}: {means}')
                append(f'V04-PDM-CONTINUOUS-DENSITY/{controller_role}/{key}/repeat-{repetition + 1}',
                       {'means': means})
