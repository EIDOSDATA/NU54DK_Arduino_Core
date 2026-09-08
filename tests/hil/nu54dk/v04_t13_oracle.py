"""! @brief 실제 완료 통계를 독립 pattern·시간·peer 방향과 대조합니다. """
from __future__ import annotations

from v04_protocol import ProtocolError

MASK = 0xFFFFFFFF


def i2s_failure(words, buffer, seed, role):
    """! @brief 최초 실패 DMA의 전체256word를 독립 전역 pattern과 대조하며 원인을 단정하지 않습니다. """
    from v04_common_i2s import pattern as i2s_pattern
    if (role not in (1, 2) or len(words) != 20 or len(buffer) != 256 or
            any(type(word) is not int or not 0 <= word <= MASK for word in words + buffer) or
            words[:4] != [20, role, lane_seed(seed, 0, role), lane_seed(seed, 0, 3-role)] or
            words[4] not in range(0, 17, 2) or words[6] == 0 or words[10] >= 3 or
            words[11] == 0 or words[10] != (words[11]-1) % 3 or
            not words[11] <= words[12] <= words[11]+2 or words[13:16] != [6, words[7], 1] or
            words[16] != 1 or words[17] == 0 or words[19] != 256):
        raise ProtocolError('T13 incomplete I2S failure DMA or metadata')
    first_sample = (words[11]-1)*256-words[4]
    if first_sample < 0 or words[5] != words[11]*256-words[4]:
        raise ProtocolError('T13 I2S failure position/count does not identify one returned buffer')
    mismatches = []
    for offset, actual in enumerate(buffer):
        index = first_sample+offset
        expected = i2s_pattern(words[3], index)
        if expected != actual:
            neighbours = [distance for distance in (-4, -2, -1, 1, 2, 4)
                          if index+distance >= 0 and i2s_pattern(words[3], index+distance) == actual]
            mismatches.append({'index':index, 'expected':expected, 'actual':actual,
                               'xor':expected ^ actual, 'matching_neighbour_offsets':neighbours})
    if (len(mismatches) != words[6] or not mismatches or
            [mismatches[0][key] for key in ('index', 'expected', 'actual')] != words[7:10]):
        raise ProtocolError('T13 I2S raw DMA does not reproduce the device first mismatch')
    return {'role':role, 'returned_buffer_index':words[11]-1, 'first_sample':first_sample,
            'mismatches':mismatches, 'normal_pass':False}


def uart_pins(words, endpoint):
    """! @brief 실제 UART PSEL의 사용 핀과 미사용 RTS/CTS 분리를 송신 전에 대조합니다. """
    if (len(words) != 7 or any(type(word) is not int or not 0 <= word <= MASK for word in words) or
            endpoint['kind'] != 'uarte'):
        raise ProtocolError('T13 invalid UART pin snapshot')
    pins = endpoint['pins']
    def raw(signal):
        if signal not in pins:
            return MASK
        port, number = map(int, pins[signal][1:].split('.'))
        return port * 32 + number
    expected = [endpoint['instance'], int('rts' in pins),
                *[raw(signal) for signal in ('txd', 'rxd', 'rts', 'cts')]]
    if words[:6] != expected or words[6] not in (0, 8):
        raise ProtocolError(f'T13 UART pin selection mismatch: actual={words}; expected={expected}')
    return dict(zip(('instance', 'hwfc', 'txd', 'rxd', 'rts', 'cts', 'enable'), words))


def bus_pins(words, endpoint):
    """! @brief SPI/TWI의 실제 PSEL과 SPIM 미사용 DCX를 START 전에 대조합니다. """
    kinds = {'spim': (2, 7), 'spis': (3, 2), 'twim': (4, 6), 'twis': (5, 9)}
    if endpoint['kind'] not in kinds or len(words) != 8 or any(type(word) is not int or not 0 <= word <= MASK for word in words):
        raise ProtocolError('T13 invalid SPI/TWI pin snapshot')
    kind, enable = kinds[endpoint['kind']]
    signals = ('sck', 'mosi', 'miso', 'csn') if kind in (2, 3) else ('sda', 'scl')
    pins = []
    for signal in signals:
        port, number = map(int, endpoint['pins'][signal][1:].split('.'))
        pins.append(port * 32 + number)
    expected = pins + [MASK] * (5-len(pins))
    if words[:2] != [kind, endpoint['instance']] or words[2] not in (0, enable) or words[3:] != expected:
        raise ProtocolError(f'T13 SPI/TWI pin selection mismatch: actual={words}; expected={expected}')
    return {'kind': endpoint['kind'], 'instance': words[1], 'enable': words[2], 'psel': words[3:]}


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


def timing(words):
    """! @brief histogram 합·구간별 가능 합계·최대값과 64-bit 합계를 독립 대조합니다. """
    if len(words) != 20 or any(type(v) is not int or not 0 <= v <= MASK for v in words):
        raise ProtocolError('T13 invalid timing snapshot')
    count, maximum, low, high, *bins = words
    total = low | high << 32
    lower = sum(amount * (0 if index == 0 else (1 << (index-1)) + 1) for index, amount in enumerate(bins))
    upper = sum(amount * ((1 << index) if index < 15 else MASK) for index, amount in enumerate(bins))
    bucket = min(15, max(0, (max(1, maximum)-1).bit_length()))
    if (sum(bins) != count or total < maximum or not lower <= total <= min(upper, maximum*count) or
            (count == 0 and (maximum or total)) or (count and not bins[bucket]) or
            any(bins[bucket+1:])):
        raise ProtocolError('T13 fabricated or inconsistent timing distribution')
    return {'count': count, 'maximum_us': maximum, 'total_us': total, 'bins': bins}


def stream_indices(test):
    return [index for index, key in enumerate(('adc_channels', 'pwm_instance', 'i2s', 'pdm_instance')) if test[key]]


def stream(index, words, test, seed, role):
    """! @brief 실제 ADC sample·PWM 모든 에지·I2S 전역 위치·PDM DMA 진행을 대조합니다. """
    if len(words) != 20 or any(type(v) is not int or not 0 <= v <= MASK for v in words):
        raise ProtocolError('T13 invalid stream snapshot')
    enabled = index != 0 or role == 1
    if words[0] != index or words[2:4] != [0, 0] or words[18] != 1 or words[19] != int(enabled) or words[1] != int(enabled):
        raise ProtocolError(f'T13 stream failed or inactive: index={index}, role={role}, words={words}')
    completed, queued = words[4:6]
    units = words[6] | words[7] << 32
    result = {'completed': completed, 'units': units, 'enabled': enabled, 'rate': 0}
    if not enabled:
        if completed or queued or units:
            raise ProtocolError('T13 disabled peer ADC has fabricated measurements')
        return result
    if index == 1:
        if completed == 0:
            raise ProtocolError('T13 PWM has no observed progress')
        if role == 1:
            high, low = test['pwm_duty']*10, 1000-test['pwm_duty']*10
            if (units != completed or not high-8 <= words[9] <= words[10] <= high+8 or
                    not low-8 <= words[11] <= words[12] <= low+8 or
                    abs((words[15]-words[14]) - (completed-1)*500) > completed*8+1000):
                raise ProtocolError('T13 PWM edge count or timing differs from configured waveform')
            result['rate'] = 2000
        return result
    if index == 3 and role == 2:
        if queued != 1 or words[14] == 0:
            raise ProtocolError('T13 PDM synthetic source was not armed')
        return result
    length = (32, 0, 256, 1024)[index]
    slots = (2, 0, 3, 4)[index]
    if completed == 0 or units != completed * length or not completed <= queued <= completed + slots:
        raise ProtocolError('T13 stream completion, DMA count or slot ownership mismatch')
    signed = lambda value: value-(1 << 32) if value & (1 << 31) else value
    if index == 0:
        if (not 500 <= words[9] <= words[10] < 4095 or not 500 <= words[11] < 4095 or
                not 500 <= words[12] < 4095 or words[15] != test['adc_channels'] or words[16] > 150):
            raise ProtocolError('T13 ADC range, channel or completion gap mismatch')
        result['rate'] = 500*test['adc_channels']
    elif index == 2:
        padding, samples, errors = words[13:16]
        peer_seed = lane_seed(seed, 0, 3-role)
        pattern_word = lambda at: ((peer_seed + 0x9E3779B9*(at+1)) ^ (((at << 16) & MASK) | (at >> 16))) & MASK
        if (padding > 16 or padding % 2 or samples+padding != units or errors or
                words[11] != pattern_word(samples-256) or words[12] != pattern_word(samples-1) or words[16] > 20):
            raise ProtocolError('T13 independent I2S stream pattern or continuity mismatch')
        result['rate'] = 96000
    elif index == 3:
        if (completed >= 4 and (abs(signed(words[11])) > 4096 or abs(signed(words[12])) > 4096 or
                abs(signed(words[14])) > 4096*1024)) or words[15] != 16000 or words[16] > 150:
            raise ProtocolError('T13 PDM density or completion gap mismatch')
        result['rate'] = 16000
    return result
