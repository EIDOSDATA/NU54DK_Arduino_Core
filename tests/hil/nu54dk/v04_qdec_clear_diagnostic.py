"""! @brief 공개 동시 clear·개별 clear·정지 파형 뒤 clear를 구별하는 진단입니다. """
import v04_common_qdec as qdec
from v04_common_gpio import expect
from v04_pair import signed
from v04_protocol import ProtocolError


def vectors(strategies=(0, 1, 2)):
    """! @brief 각 방법을30회 비교하고 시행 순서를 매번 회전합니다. """
    for repetition in range(1, 31):
        for offset in range(len(strategies)):
            yield strategies[(offset + repetition - 1) % len(strategies)], repetition


def run(devices, current, append, *, strategies=(0, 1, 2), prefix="V04-QDEC-CLEAR-DIAGNOSTIC"):
    """! @brief 누산 포화 아래400전이에서 clear 동작의 영향을 분리하며 실패는 보존합니다. """
    mismatches = []
    for strategy, repetition in vectors(strategies):
        label = f'{prefix}/strategy{strategy}/repeat{repetition}'
        with qdec.armed(devices, current, append, label, 20, 0, observation_mode=3, read_strategy=strategy):
            config = devices[0].command(85, (5,))
            append(label + '/strategy', {'status': 'observation', 'words': config})
            bound = 6000000 if strategy == 2 else 15000
            expect(config, [strategy, int(strategy not in (1, 3)), int(strategy != 2), bound, 128], 'clear strategy')
            initial = qdec.observe(devices[0], append, label + '/initial', clear=True)
            expect((signed(initial[5]), initial[6]), (0, 0), 'clear diagnostic initial counts')
            if initial[8] > bound:
                raise ProtocolError('clear diagnostic initial read bound exceeded')
            qdec.wave(devices, current, append, label + '/forward', 100, 10000, 0)
            before = devices[0].command(85, (0,))
            append(label + '/before-final-read', {'status': 'observation', 'words': before})
            if len(before) != 20 or before[1:4] != [400, 0, 400] or before[4] >= 128 or before[5] != 0:
                raise ProtocolError('clear diagnostic source/GPIO waveform unproven')
            samples = devices[0].command(85, (2,))
            append(label + '/samples', {'status': 'observation', 'words': samples})
            if len(samples) != 16 or samples[0:2] != [400, 0] or samples[3] >= 384:
                raise ProtocolError('clear diagnostic independent SAMPLE observation unproven')
            hardware = qdec.observe(devices[0], append, label + '/forward', clear=False)
            if hardware[8] > bound:
                raise ProtocolError('clear diagnostic drain bound exceeded')
            if strategy == 4:
                timing = devices[0].command(85, (6,))
                append(label + '/read-timing', {'status': 'observation', 'words': timing})
                if len(timing) != 3 or not 32 <= timing[0] <= timing[1] <= 64 or timing[2] > 1024:
                    raise ProtocolError('sample-aligned read timing unproven')
            actual = [signed(hardware[5]), hardware[6]]
            match = actual == [400, 0]
            append(label + '/comparison', {'status': 'observation' if match else 'failed',
                   'strategy': strategy, 'repetition': repetition, 'expected': [400, 0], 'actual': actual,
                   'matches': match, 'functional_regression': False})
            if not match:
                mismatches.append({'strategy': strategy, 'repetition': repetition, 'actual': actual})
        print(f'QDEC_CLEAR_DIAGNOSTIC:strategy={strategy};repeat={repetition};match={int(match)}', flush=True)
    append(prefix + '/summary', {'status': 'observation', 'comparisons': 90,
           'mismatches': mismatches, 'functional_regression': False})
    if mismatches:
        raise ProtocolError(f'QDEC clear diagnostic preserved {len(mismatches)}/90 count mismatches')
