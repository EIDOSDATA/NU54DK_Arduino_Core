"""! @brief 공통 I2S의 4+100 연속 buffer와 실제 단방향 DMA를 독립 CRC로 판정합니다. """
from contextlib import contextmanager
import itertools
import struct
import time
import zlib

from v04_common_gpio import expect
from v04_fixture import CONSENT
from v04_protocol import ProtocolError

SEED = 0x13579BDF
MASK = 0xFFFFFFFF
RECORDS = 104


def vectors():
    """! @brief master 역할·속도·폭·채널·길이·세 방향의 432조건입니다. """
    yield from itertools.product((1, 2), (16000, 48000), (8, 16, 24, 32), range(3),
                                 (32, 256, 1024), (1, 2, 3))


def pattern(seed, index):
    """! @brief firmware와 별개인 무한 정수 연산으로 32-bit 송신 word를 구성합니다. """
    return ((seed + 0x9E3779B9 * (index + 1)) ^ ((index << 16) | (index >> 16))) & MASK


def expected_words(seed, width, words, index, padding):
    """! @brief 처음의 제한된 zero sample을 제외한 전역 sample 위치를 복원합니다. """
    packed = 32 // width if width <= 16 else 1
    sample_mask = (1 << width) - 1
    result = []
    for word in range(index * words, (index + 1) * words):
        raw = 0
        for lane in range(packed):
            sample = word * packed + lane - padding
            if sample >= 0:
                value = (pattern(seed, sample // packed) >> ((sample % packed) * width)) & sample_mask
                raw |= value << (lane * width)
        result.append(raw)
    return result


def verify(vector, role, status, rows):
    """! @brief 모든 104 buffer의 순번/CRC와 측정 100개의 실제 경과 시간을 확인합니다. """
    master, rate, width, channels, words, direction = vector
    receive = int(bool(direction & (2 if role == 1 else 1)))
    transmit = int(bool(direction & (1 if role == 1 else 2)))
    packed = 32 // width if width <= 16 else 1
    frame = 2 if channels == 0 else 1
    if (len(status) != 20 or status[:2] != [1, 1] or status[2] < RECORDS or
            status[4:7] != [RECORDS, 0, 1] or status[8:10] != [receive, transmit] or
            status[11] or status[13:17] != [rate, width, channels, words] or status[18:20] != [0, 1]):
        raise ProtocolError('I2S incomplete/error/guard/direction/lease')
    expected_direction = (12 if role == master else 0) | ((1 << (4 if role == 1 else 5)) if transmit else 0)
    expect(status[17], expected_direction, 'I2S only configured clocks/data output')
    padding = status[7]
    if padding > 8 * frame or padding % frame or (not receive and padding):
        raise ProtocolError('I2S startup padding exceeds eight aligned frames')
    expect(status[10], RECORDS * words * packed - padding if receive else 0, 'I2S compared sample count')
    expect(len(rows), RECORDS, 'I2S record count')
    peer_seed = SEED ^ (0x5A5A5A5A if role == 1 else 0)
    for index, row in enumerate(rows):
        if len(row) != 5 or row[0] != index or (index and row[1] <= rows[index - 1][1]):
            raise ProtocolError('I2S missing/reordered completion')
        if receive:
            expected = expected_words(peer_seed, width, words, index, padding)
            crc = zlib.crc32(struct.pack('<' + 'I' * words, *expected))
            expect(row[2:], [crc, expected[0], expected[-1]], 'I2S independent raw-buffer CRC/ends')
        else:
            expect(row[2:], [0, 0, 0], 'I2S disabled receive DMA')
    duration = rows[103][1] - rows[4][1]
    expected_us = 99 * words * packed * 1000000 / (rate * frame)
    if abs(duration - expected_us) > expected_us * .05:
        raise ProtocolError(f'I2S measured sample-rate outside 5 percent: {duration}/{expected_us}')
    return {'role': role, 'verified_buffers': RECORDS, 'settling_buffers': 4, 'measured_buffers': 100,
            'padding_samples': padding, 'samples_compared': status[10], 'completion_span_us': duration,
            'max_queue_us': status[12], 'tail_completions_at_observation': status[2] - RECORDS,
            'receive_dma_enabled': bool(receive), 'transmit_dma_enabled': bool(transmit)}


@contextmanager
def armed(devices, current, append, label, vector):
    """! @brief master clock를 먼저 정지하고 slave를 정지하여 출력 충돌을 막습니다. """
    master = vector[0]
    current(530)
    original = None
    try:
        for device in devices:
            expect(device.command(88, (530, 1, CONSENT, master)), [530, 10000], 'I2S arm')
            expect(device.command(90, (*vector[1:], SEED)), [0], 'I2S prepare')
        yield
    except BaseException as error:
        original = error
        append(label + '/failure', {'status': 'failed', 'error': str(error)})
        raise
    finally:
        rows = []
        for device in (devices[master - 1], devices[2 - master]):
            try:
                words = device.command(89, timeout=2)
                good = len(words) == 20 and words[:2] == [0, 0] and words[17] == 0 and words[19] == 0
                rows.append({'role': device.image['role'], 'stopped': good, 'words': words})
            except BaseException as error:
                rows.append({'role': device.image['role'], 'stopped': False, 'error': str(error)})
        append(label + '/cleanup', {'status': 'cleanup', 'outcomes': rows})
        if not all(row['stopped'] for row in rows) and original is None:
            raise ProtocolError('I2S cleanup unproven')


def run(devices, current, append):
    """! @brief 원본 완료 상태를 저장하고 STOP한 다음 독립 CRC를 계산합니다. """
    for vector in vectors():
        label = 'V04-COMMON-I2S/' + '/'.join(map(str, vector))
        master, rate, width, channels, words, direction = vector
        statuses = []
        with armed(devices, current, append, label, vector):
            expect(devices[2 - master].command(91), [0], 'I2S slave start')
            expect(devices[master - 1].command(91), [0], 'I2S master start')
            packed = 32 // width if width <= 16 else 1
            seconds = RECORDS * words * packed / (rate * (2 if channels == 0 else 1))
            deadline = time.monotonic() + seconds * 1.5 + 2
            while True:
                current(530)
                statuses = [device.command(92) for device in devices]
                append(label + '/progress', {'status': 'observation', 'words': statuses})
                if any(len(raw) != 20 or raw[5] or raw[11] or raw[18] for raw in statuses):
                    append(label + '/error-detail', {'status': 'observation',
                                                    'words': [device.command(95) for device in devices]})
                    raise ProtocolError('I2S device error; first mismatch preserved')
                if all(raw[2] >= RECORDS for raw in statuses):
                    break
                if time.monotonic() > deadline:
                    raise ProtocolError('I2S 104 completion deadline exceeded')
                for device in devices:
                    expect(device.command(94), [0], 'I2S lease')
                time.sleep(.2)
        # @brief STOP 뒤에도 보존한 실제 104개 통계만 읽으며 무전송 tail을 측정에 더하지 않습니다.
        results = []
        for role, device in enumerate(devices, 1):
            rows = []
            for offset in range(0, RECORDS, 4):
                raw = device.command(93, (offset, 4))
                expect(len(raw), 20, 'I2S raw statistics packet')
                rows.extend(raw[index:index + 5] for index in range(0, 20, 5))
            append(label + f'/raw-role{role}', {'status': 'observation', 'vector': list(vector),
                                             'words': statuses[role - 1], 'buffers': rows})
            results.append(verify(vector, role, statuses[role - 1], rows))
        append(label, {'status': 'passed', 'results': results,
                       'scope': 'continuous-4-plus-100-buffers-independent-crc-and-null-direction'})
