"""! @brief 실제 완료 통계를 독립 pattern·시간·peer 방향과 대조합니다. """
from __future__ import annotations

from v04_protocol import ProtocolError

MASK = 0xFFFFFFFF


def pattern(seed, index):
    """! @brief 송신/RX 메모리를 입력으로 사용하지 않는 전역 byte 기대값입니다. """
    index &= MASK
    mixed = (seed + index * 0x9E3779B9) & MASK
    return ((mixed ^ (mixed >> 13) ^ (index >> 8)) >> 7) & 255


def lane_seed(seed, lane, role):
    return (seed ^ (0x13579BDF * (lane + 1)) ^ (role * 0x5A5A5A5A)) & MASK


def direction(words, seed, length):
    """! @brief 길이 합계·최종 frame 양끝을 Host 기대값과 대조합니다. """
    completed, low, high, digest, first, last = words
    count = low | high << 32
    if count != completed * length:
        raise ProtocolError('T13 completion count/length mismatch')
    if completed:
        offset = count - length
        expected = lambda at: sum(pattern(seed, at + index) << (8 * index) for index in range(4))
        if first != expected(offset) or last != expected(count - 4):
            raise ProtocolError('T13 independent frame endpoints mismatch')
    elif count or digest != 2166136261 or first or last:
        raise ProtocolError('T13 empty stream has fabricated data')
    return {'frames': completed, 'bytes': count, 'hash': digest}


def lane(words, seed, lane_index, role, length):
    """! @brief 오류·가드 실패·누락·과도한 frame 정지를 성공으로 수용하지 않습니다. """
    if (len(words) != 20 or any(type(word) is not int or not 0 <= word <= MASK for word in words) or
            words[0] != 0 or words[1] != 0 or words[2] not in (0, 1) or words[19] != 20):
        raise ProtocolError(f'T13 serial failure or invalid snapshot: {words}')
    if max(words[17:19]) > 100:
        raise ProtocolError('T13 frame completion gap exceeded 100ms')
    return {'tx': direction(words[5:11], lane_seed(seed, lane_index, role), length),
            'rx': direction(words[11:17], lane_seed(seed, lane_index, 3 - role), length),
            'max_queue_us': words[3], 'max_tx_gap_ms': words[17], 'max_rx_gap_ms': words[18]}


def paired(rows):
    """! @brief quiesce·drain 후 두 방향의 실제 완료 길이·hash가 같아야 합니다. """
    if len(rows) != 2:
        raise ProtocolError('T13 requires both physical roles')
    for first, second in ((0, 1), (1, 0)):
        if rows[first]['tx'] != rows[second]['rx'] or rows[first]['tx']['frames'] == 0:
            raise ProtocolError('T13 peer TX/RX count or payload hash mismatch')


def engine(words):
    """! @brief device uptime·실제 연속 시간과 실패/lease 만료를 검사합니다. """
    if len(words) != 16 or words[4] != 1 or words[5] != 0:
        raise ProtocolError(f'T13 engine unhealthy or lease expired: {words}')
    fields = [words[index] | words[index + 1] << 32 for index in (7, 9, 11, 13)]
    if fields[0] < fields[1] or fields[2] > fields[0] - fields[1]:
        raise ProtocolError('T13 elapsed counter is inconsistent')
    return dict(zip(('uptime_ms', 'start_ms', 'elapsed_ms', 'service_busy_us'), fields))
