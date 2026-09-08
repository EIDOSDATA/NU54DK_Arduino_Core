"""! @brief 기존 S 결선의 SPI/TWI 역할 전환과 고정 순·역방향100회 경로를 정의합니다. """
from __future__ import annotations

import copy
import secrets
import v04_t13_cases as catalog
import v04_t13_plan as plan
from v04_protocol import ProtocolError


def variant(test, reverse=False):
    """! @brief GPIO 값은 유지하고 SPI 데이터 신호명과 SPI/TWI 역할만 양쪽 함께 바꿉니다. """
    result = copy.deepcopy(test)
    result['_reverse_serial'] = reverse
    if not reverse:
        return result
    if len(result['serial_links']) != 1 or any(result[key] for key in
            ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s')):
        raise ProtocolError('T13 role reversal requires a standalone serial pair')
    link = result['serial_links'][0]
    kinds = (link['a']['kind'], link['b']['kind'])
    if kinds not in (('spim', 'spis'), ('spis', 'spim'), ('twim', 'twis'), ('twis', 'twim')):
        raise ProtocolError('T13 role reversal supports only SPI/TWI')
    opposite = {'spim': 'spis', 'spis': 'spim', 'twim': 'twis', 'twis': 'twim'}
    for role in ('a', 'b'):
        endpoint = link[role]
        endpoint['kind'] = opposite[endpoint['kind']]
        if endpoint['kind'] in ('spim', 'spis'):
            endpoint['pins'] = {({'mosi': 'miso', 'miso': 'mosi'}.get(signal, signal)): pin
                                for signal, pin in endpoint['pins'].items()}
    mapping = plan.harness(result['harness'])
    for signal, pin in link['a']['pins'].items():
        if mapping[pin] != link['b']['pins'][signal]:
            raise ProtocolError('T13 reversed signal does not match the current harness')
    result['name'] += '-reversed'
    return result


def route(instance):
    """! @brief 네 공유 block의 인접 personality 전환을 양방향, serial00은 SPI 두 역할로 고정합니다. """
    if instance not in (0, 20, 21, 22, 30):
        raise ProtocolError('T13 unsupported handover block')
    rows = {row['name']: row for row in catalog.cases() if row['harness'] == 'S' and row['id'] < 100}
    spi = variant(rows[f'spim{instance}'])
    spi_reverse = variant(rows[f'spim{instance}'], True)
    if instance == 0:
        return spi, [spi_reverse, spi]
    uart = variant(rows[f'uarte{instance}'])
    twi = variant(rows[f'twim{instance}'])
    twi_reverse = variant(rows[f'twim{instance}'], True)
    return uart, [spi, spi_reverse, twi, twi_reverse, uart,
                  twi_reverse, twi, spi_reverse, spi, uart]


def execute(devices, instance, continuity, append, *, preflight, timing_mode=None):
    """! @brief reset/flash 없이 매 전환의 STOP·새 PSEL·다른 payload와 다음 peer frame을 증명합니다. """
    import v04_t13_run as runner
    import v04_t13_spi_timing as timing
    if timing_mode is not None and (not preflight or instance not in (20, 21, 22)):
        raise ProtocolError('T13 timing comparison cannot be used as planned handover100')
    initial, sequence = route(instance)
    if timing_mode is not None:
        initial = timing.fixture(initial, timing_mode)
        sequence = [timing.fixture(test, timing_mode) for test in sequence]
    phase = 'spi-timing-diagnostic' if timing_mode else 'handover-preflight' if preflight else 'handover'
    root = f'T13-S/{phase}/serial{instance}'
    first_seed = secrets.randbits(32)
    sequence_index = 0
    def run(test, label):
        nonlocal sequence_index
        seed = (first_seed + sequence_index * 0x9E3779B9) & 0xFFFFFFFF
        sequence_index += 1
        runner.execute_group(devices, {'test': test, 'members': [test]}, .25, continuity,
            lambda identifier, row: append(label + '/' + identifier, row), preflight=True, seed=seed)
    run(initial, root + '/initial')
    previous = initial
    rounds = 1 if preflight else 100
    for repetition in range(1, rounds + 1):
        for step, following in enumerate(sequence, 1):
            label = root + f'/repeat{repetition:03}/step{step:02}'
            append(label + '/input', {'status': 'input', 'from': previous, 'to': following})
            run(following, label + '/transfer')
            append(label + '/result', {'status': 'observation-complete' if timing_mode else 'passed', 'from_name': previous['name'],
                                     'to_name': following['name'], 'planned_handover_pass': not preflight})
            previous = following
        print(f'T13_HANDOVER_PROGRESS block={instance} rounds={repetition}/{rounds} transitions={repetition*len(sequence)}/{rounds*len(sequence)}', flush=True)
