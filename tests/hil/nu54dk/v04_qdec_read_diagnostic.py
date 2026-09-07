"""! @brief 같은 image에서 계측 접근 네 종류를 교차 비교하며 기능 PASS로 합산하지 않습니다. """
import v04_common_qdec as qdec
from v04_common_gpio import expect
from v04_pair import signed
from v04_protocol import ProtocolError


def vectors():
    """! @brief 순서 효과를 줄여 각 계측 mode를20회씩 비교합니다. """
    for repetition in range(1, 21):
        for offset in range(4):
            yield (offset + repetition - 1) % 4, repetition


def run(devices, current, append):
    """! @brief count 불일치만 계획한 대비 실험에서 보존·계속하고 제어 오류는 즉시 중단합니다. """
    mismatches = []
    for mode, repetition in vectors():
        label = f'V04-QDEC-READ-DIAGNOSTIC/mode{mode}/repeat{repetition}'
        with qdec.armed(devices, current, append, label, 20, 0, observation_mode=mode):
            configuration = devices[0].command(85, (4,))
            append(label + '/mode', {'status': 'observation', 'words': configuration})
            expect(configuration, [mode, int(mode == 3), int(mode >= 2), int(mode >= 1)], 'read observation mode')
            qdec.counts(qdec.observe(devices[0], append, label + '/initial', clear=True), 0, 0)
            qdec.wave(devices, current, append, label + '/forward', 100, 10000, 0)
            hardware = qdec.observe(devices[0], append, label + '/forward', clear=False)
            pad = devices[0].command(85, (0,))
            append(label + '/gpio', {'status': 'observation', 'words': pad})
            if len(pad) != 20 or pad[1:4] != [400, 0, 400] or pad[4] >= 1000 or pad[5] != 0:
                raise ProtocolError('diagnostic source/GPIO waveform unproven')
            actual = (signed(hardware[5]), hardware[6])
            match = actual == (400, 0)
            append(label + '/comparison', {'status': 'observation' if match else 'failed', 'mode': mode, 'repetition': repetition,
                                          'expected': [400, 0], 'actual': list(actual), 'matches': match,
                                          'functional_regression': False})
            if not match:
                mismatches.append({'mode': mode, 'repetition': repetition, 'actual': list(actual)})
        print(f'QDEC_READ_DIAGNOSTIC:mode={mode};repeat={repetition};match={int(match)}', flush=True)
    append('V04-QDEC-READ-DIAGNOSTIC/summary', {'status': 'observation', 'comparisons': 80,
           'mismatches': mismatches, 'functional_regression': False})
    if mismatches:
        raise ProtocolError(f'QDEC read diagnostic preserved {len(mismatches)}/80 count mismatches')
