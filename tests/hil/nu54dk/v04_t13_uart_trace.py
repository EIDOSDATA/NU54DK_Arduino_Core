"""! @brief 정지한 exact image의 UART 순환 이력을 검증하며 실기 PASS로 판정하지 않습니다. """
from v04_protocol import ProtocolError

DEPTH = 64
WORDS = 24
FIELDS = ('sequence', 'cycle', 'operation', 'argument', 'buffer', 'length', 'first_word',
          'rx_ptr', 'rx_maxcnt', 'rx_amount', 'rx_ready', 'rx_end', 'errorsrc', 'error_event',
          'shorts', 'driver_flags', 'current_buffer', 'next_buffer', 'current_length',
          'next_length', 'enabled', 'configuration', 'ipsr', 'prior_irq_key')


def decode(count, words):
    """! @brief wrap 후 마지막64건만 반환하며 미게시·잘린·잘못된 이력은 거부합니다. """
    if (type(count) is not int or not 0 <= count <= 0xFFFFFFFF or
            not isinstance(words, list) or len(words) != DEPTH * WORDS or
            any(type(word) is not int or not 0 <= word <= 0xFFFFFFFF for word in words)):
        raise ProtocolError('UART trace count or record storage is malformed')
    if count == 0:
        if any(words):
            raise ProtocolError('UART trace was read before publication or after counter wrap')
        return []
    records = []
    for sequence in range(max(1, count - DEPTH + 1), count + 1):
        offset = (sequence - 1) % DEPTH * WORDS
        record = dict(zip(FIELDS, words[offset:offset + WORDS]))
        if record['sequence'] != sequence or record['operation'] not in range(1, 8):
            raise ProtocolError('UART trace contains a torn or stale record')
        if record['operation'] in (6, 7):
            event = record['argument'] & 255
            if event > 7 or (event != 2 and record['argument'] != event):
                raise ProtocolError('UART trace callback type differs from the pinned nrfx ABI')
            record['event_type'] = event
            record['reported_error_mask'] = record['argument'] >> 8 if event == 2 else 0
        record['physical_pass_added'] = False
        records.append(record)
    return records
