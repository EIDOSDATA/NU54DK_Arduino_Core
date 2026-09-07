"""! @brief SAMPLE IRQ 합산과 자동 REPORT IRQ를 같은400전이로 비교합니다. """
import itertools

import v04_common_qdec as qdec
from v04_common_gpio import expect
from v04_pair import signed
from v04_protocol import ProtocolError


def vectors():
    """! @brief 두 QDEC와 두 IRQ 방법을 각10회 실행합니다. """
    yield from itertools.product((20, 21), range(1, 11), (7, 8))


def verify_irq(strategy, gpio, irq, hardware, pins):
    """! @brief 관측·IRQ·큐 오류를 먼저 검사하고 누산 숫자 차이는 원본으로 반환합니다. """
    if len(gpio) != 20 or gpio[1:4] != [400, 0, 400] or gpio[4] >= 256 or gpio[5] != 0:
        raise ProtocolError('IRQ diagnostic GPIO waveform unproven')
    if len(irq) != 9 or irq[6] or irq[8] or irq[7] >= 256:
        raise ProtocolError('IRQ queue/error/service bound unproven')
    expect(pins[8:13], [16, int(strategy == 8), 5 if strategy == 7 else 6, 0, 1], 'IRQ configuration')
    if strategy == 7:
        if signed(irq[0]) != 400 or irq[1] or irq[2] < 400 or irq[5]:
            raise ProtocolError('SAMPLE IRQ count unproven')
    elif strategy == 8:
        if irq[2] or irq[5] == 0 or hardware[7] != 0:
            raise ProtocolError('automatic REPORT must not mix explicit reads')
    else:
        raise ProtocolError('unsupported IRQ diagnostic strategy')
    return [signed(hardware[5]), hardware[6]]


def run(devices, current, append):
    """! @brief 숫자 실패는 양쪽 STOP 후 계속 비교하며 기능240의 PASS로 세지 않습니다. """
    mismatches = []
    for instance, repetition, strategy in vectors():
        label = f'V04-QDEC-IRQ-DIAGNOSTIC/{instance}/strategy{strategy}/repeat{repetition}'
        with qdec.armed(devices, current, append, label, instance, 0,
                        observation_mode=3, read_strategy=strategy):
            pins = devices[0].command(85, (8,))
            append(label + '/pin-config', {'status': 'observation', 'words': pins})
            expect(pins[0:3], [1, 0, 0], 'QDEC input configuration')
            initial = qdec.observe(devices[0], append, label + '/initial', clear=True)
            expect((signed(initial[5]), initial[6]), (0, 0), 'IRQ initial counts')
            qdec.wave(devices, current, append, label + '/forward', 100, 10000, 0)
            gpio = devices[0].command(85, (0,))
            append(label + '/gpio', {'status': 'observation', 'words': gpio})
            irq = devices[0].command(85, (10,))
            append(label + '/irq', {'status': 'observation', 'words': irq})
            hardware = qdec.observe(devices[0], append, label + '/forward', clear=False)
            actual = verify_irq(strategy, gpio, irq, hardware, pins)
            match = actual == [400, 0]
            append(label + '/comparison', {'status': 'observation' if match else 'failed',
                   'instance': instance, 'strategy': strategy, 'repetition': repetition,
                   'expected': [400, 0], 'actual': actual, 'matches': match,
                   'sample_irq_count': signed(irq[0]), 'report_irq_count': signed(irq[3]),
                   'functional_regression': False})
            if not match:
                mismatches.append({'instance': instance, 'strategy': strategy,
                                   'repetition': repetition, 'actual': actual})
        print(f'QDEC_IRQ_DIAGNOSTIC:instance={instance};strategy={strategy};repeat={repetition};match={int(match)}', flush=True)
    append('V04-QDEC-IRQ-DIAGNOSTIC/summary', {'status': 'observation', 'comparisons': 40,
           'mismatches': mismatches, 'functional_regression': False})
    if mismatches:
        raise ProtocolError(f'QDEC IRQ diagnostic preserved {len(mismatches)}/40 count mismatches')
