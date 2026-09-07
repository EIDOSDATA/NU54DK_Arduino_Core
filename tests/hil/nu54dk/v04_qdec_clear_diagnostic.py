"""! @brief 공개 동시 clear·개별 clear·정지 파형 뒤 clear를 구별하는 진단입니다. """
import v04_common_qdec as qdec
from v04_common_gpio import expect
from v04_pair import signed
from v04_protocol import ProtocolError


def verify_observation(gpio, samples, polling):
    """! @brief 고정256us 샘플의 직접 poll·처리 시간 상한으로 누락을 배제합니다. """
    if len(gpio) != 20 or gpio[1:4] != [400, 0, 400] or gpio[4] >= 256 or gpio[5] != 0:
        raise ProtocolError('clear diagnostic source/GPIO waveform unproven')
    if len(samples) != 16 or samples[0:2] != [400, 0]:
        raise ProtocolError('clear diagnostic independent SAMPLE observation unproven')
    if len(polling) != 3 or polling[2] < samples[2] or polling[2] == 0:
        raise ProtocolError('SAMPLE polling evidence incomplete')
    ## @brief 1MHz 시각 양자화 여유2us를 포함해 다음 샘플 전 처리·누락 시 최소 event 간격을 검사합니다.
    window = polling[0] + polling[1] + 2
    if window >= 256 or samples[3] + window >= 512:
        raise ProtocolError('SAMPLE polling/processing bound exceeded')


def verify_protection(words):
    """! @brief 낮은 IRQ 우선순위와128us 미만 read 보호·정상 mask 복원을 확인합니다. """
    if len(words) != 5 or words[0:2] != [7, 1] or not 0 < words[2] < 128 or words[3:] != [0, 0]:
        raise ProtocolError('protected read duration or IRQ state unproven')


def vectors(strategies=(0, 1, 2)):
    """! @brief 각 방법을30회 비교하고 시행 순서를 매번 회전합니다. """
    for repetition in range(1, 31):
        for offset in range(len(strategies)):
            yield strategies[(offset + repetition - 1) % len(strategies)], repetition


def run(devices, current, append, *, strategies=(0, 1, 2), prefix="V04-QDEC-CLEAR-DIAGNOSTIC"):
    """! @brief 누산 포화 아래400전이에서 clear 동작의 영향을 분리하며 실패는 보존합니다. """
    mismatches = []
    comparison_count = 30 * len(strategies)
    for strategy, repetition in vectors(strategies):
        label = f'{prefix}/strategy{strategy}/repeat{repetition}'
        with qdec.armed(devices, current, append, label, 20, 0, observation_mode=3, read_strategy=strategy):
            config = devices[0].command(85, (5,))
            append(label + '/strategy', {'status': 'observation', 'words': config})
            bound = 6000000 if strategy == 2 else 15000
            expect(config, [strategy, int(strategy not in (1, 3, 5)), int(strategy != 2), bound, 128], 'clear strategy')
            if strategy in (5, 6):
                for role, device in enumerate(devices, 1):
                    pins = device.command(85, (8,))
                    append(label + f'/pin-config-role{role}', {'status': 'observation', 'words': pins})
                    if len(pins) != 13 or pins[0:3] != [role, 0 if role == 1 else 3, 0 if role == 1 else 3]:
                        raise ProtocolError('QDEC input/output electrical configuration mismatch')
                    if role == 1 and pins[8:13] != [16, 0, 4, 0, 1]:
                        raise ProtocolError('QDEC actual LEDPRE/shortcut/interrupt/debounce/enable mismatch')
            initial = qdec.observe(devices[0], append, label + '/initial', clear=True)
            expect((signed(initial[5]), initial[6]), (0, 0), 'clear diagnostic initial counts')
            if initial[8] > bound:
                raise ProtocolError('clear diagnostic initial read bound exceeded')
            qdec.wave(devices, current, append, label + '/forward', 100, 10000, 0)
            before = devices[0].command(85, (0,))
            append(label + '/before-final-read', {'status': 'observation', 'words': before})
            samples = devices[0].command(85, (2,))
            append(label + '/samples', {'status': 'observation', 'words': samples})
            polling = devices[0].command(85, (9,))
            append(label + '/sample-polling', {'status': 'observation', 'words': polling})
            verify_observation(before, samples, polling)
            hardware = qdec.observe(devices[0], append, label + '/forward', clear=False)
            if hardware[8] > bound:
                raise ProtocolError('clear diagnostic drain bound exceeded')
            if strategy == 4:
                timing = devices[0].command(85, (6,))
                append(label + '/read-timing', {'status': 'observation', 'words': timing})
                if len(timing) != 3 or not 32 <= timing[0] <= timing[1] <= 64 or timing[2] > 1024:
                    raise ProtocolError('sample-aligned read timing unproven')
            if strategy in (5, 6):
                late = devices[0].command(85, (7,))
                append(label + '/late-read', {'status': 'observation', 'words': late})
                if len(late) != 14 or not 5 <= late[3] < 128:
                    raise ProtocolError('delayed register observation timing unproven')
            if strategy == 9:
                protected = devices[0].command(85, (11,))
                append(label + '/protected-read', {'status': 'observation', 'words': protected})
                verify_protection(protected)
            actual = [signed(hardware[5]), hardware[6]]
            match = actual == [400, 0]
            append(label + '/comparison', {'status': 'observation' if match else 'failed',
                   'strategy': strategy, 'repetition': repetition, 'expected': [400, 0], 'actual': actual,
                   'matches': match, 'functional_regression': False})
            if not match:
                mismatches.append({'strategy': strategy, 'repetition': repetition, 'actual': actual})
        print(f'QDEC_CLEAR_DIAGNOSTIC:strategy={strategy};repeat={repetition};match={int(match)}', flush=True)
    append(prefix + '/summary', {'status': 'observation', 'comparisons': comparison_count,
           'mismatches': mismatches, 'functional_regression': False})
    if mismatches:
        raise ProtocolError(f'QDEC clear diagnostic preserved {len(mismatches)}/{comparison_count} count mismatches')
