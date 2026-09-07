"""! @brief 공통 두 선의 방향 전환·read/clear·재시작·대각 전이를 검증합니다. """
from contextlib import contextmanager
import itertools
import time

from v04_common_gpio import expect
from v04_fixture import CONSENT
from v04_pair import signed
from v04_protocol import ProtocolError


def vectors():
    """! @brief 두 인스턴스·debounce·양 경계 속도·회전 수를 각 10회 검사합니다. """
    yield from itertools.product((20, 21), (0, 1), (2000, 10000), (1, 100, 1000), range(1, 11))


def observe(device, append, label, *, clear=None):
    """! @brief 실제 hardware read 합산 원본을 먼저 보존합니다. """
    raw = device.command(85) if clear is None else device.command(86, (int(clear),))
    append(label + f'/raw-role{device.image["role"]}', {'status': 'observation', 'words': raw})
    if len(raw) != 16 or raw[9] or raw[10] or raw[12] != 1:
        raise ProtocolError(f'QDEC error/lease mismatch: {raw}')
    expect(raw[11], 3 if device.image['role'] == 2 else 0, 'only B phase pins output')
    return raw


def counts(raw, steps, double_transitions):
    """! @brief signed accumulator와 double-transition 누산기를 각각 판정합니다. """
    expect((signed(raw[5]), raw[6]), (steps, double_transitions), 'QDEC hardware accumulators')
    if raw[8] > 15000 or raw[9]:
        raise ProtocolError('QDEC hardware accumulator drain bound exceeded')


@contextmanager
def armed(devices, current, append, label, instance, debounce, *, observation_mode=None, read_strategy=None):
    """! @brief B가 LOW를 유지한 상태에서 A sampling을 시작·정지한 뒤 B를 입력으로 반환합니다. """
    current(520)
    original = None
    try:
        for device in devices:
            expect(device.command(80, (520, 1, CONSENT, 2)), [520, 10000], 'QDEC arm')
        for device in reversed(devices):
            values = (instance, debounce) if observation_mode is None else (instance, debounce, observation_mode)
            if read_strategy is not None:
                if observation_mode != 3:
                    raise ProtocolError('read strategy diagnostic requires full observation')
                values += (read_strategy,)
            expect(device.command(83, values), [0], 'QDEC prepare')
        time.sleep(.004)
        yield
    except BaseException as error:
        original = error
        append(label + '/failure', {'status': 'failed', 'error': str(error)})
        raise
    finally:
        mismatch = False
        for page in (0, 1, 2, 4, 5, 6, 7, 8):
            try:
                raw = devices[0].command(85, (page,), timeout=2)
                append(label + f'/diagnostic-page{page}', {'status': 'observation', 'words': raw})
                if page == 1:
                    mismatch = any(raw)
            except BaseException as diagnostic_error:
                append(label + f'/diagnostic-page{page}', {'status': 'unavailable', 'error': str(diagnostic_error)})
        if mismatch:
            for offset in range(0, 16, 2):
                try:
                    raw = devices[0].command(85, (3, offset), timeout=2)
                    append(label + f'/read-trace{offset}', {'status': 'observation', 'words': raw})
                except BaseException as diagnostic_error:
                    append(label + f'/read-trace{offset}', {'status': 'unavailable', 'error': str(diagnostic_error)})
        rows = []
        for device in devices:
            try:
                words = device.command(81, timeout=2)
                good = len(words) == 16 and words[1:3] == [0, 0] and words[11:13] == [0, 0] and words[15] == 0
                rows.append({'role': device.image['role'], 'stopped': good, 'words': words})
            except BaseException as error:
                rows.append({'role': device.image['role'], 'stopped': False, 'error': str(error)})
        append(label + '/cleanup', {'status': 'cleanup', 'outcomes': rows})
        if not all(row['stopped'] for row in rows) and original is None:
            raise ProtocolError('QDEC cleanup unproven')


def wave(devices, current, append, label, cycles, interval, direction):
    """! @brief 40초 경계도 lease를 갱신하며 기다리고 실제 발생 step 수를 대조합니다. """
    current(520)
    expected_steps = cycles * (2 if direction == 2 else 4)
    expect(devices[1].command(84, (cycles, interval, direction)), [0], 'finite phase source')
    origin = time.monotonic()
    deadline = origin + expected_steps * interval / 1e6 * 1.5 + 2
    while True:
        current(520)
        for device in devices:
            expect(device.command(82), [0], 'QDEC lease')
        sender = observe(devices[1], append, label + '/progress')
        observe(devices[0], append, label + '/progress')
        if sender[2] == 0:
            break
        if time.monotonic() > deadline:
            raise ProtocolError('QDEC finite source timed out')
        time.sleep(.2)
    expect(sender[3:5], [expected_steps, expected_steps], 'phase source steps')
    time.sleep(.004)
    append(label + '/source-complete', {'status': 'observation', 'steps': expected_steps,
                                      'elapsed_seconds': time.monotonic() - origin})


def run(devices, current, append):
    """! @brief 240조건의 긴 forward/reverse와 짧은 오류·재시작 probe를 구분합니다. """
    for instance, debounce, interval, cycles, repetition in vectors():
        label = f'V04-COMMON-QDEC/{instance}/debounce{debounce}/{interval}us/{cycles}cycles/repeat{repetition}'
        with armed(devices, current, append, label, instance, debounce):
            counts(observe(devices[0], append, label + '/initial', clear=True), 0, 0)
            wave(devices, current, append, label + '/forward', cycles, interval, 0)
            counts(observe(devices[0], append, label + '/forward', clear=False), 4 * cycles, 0)
            ## @brief QDEC를 멈추거나 누산값을 지우지 않고 파형 방향만 바꿉니다.
            wave(devices, current, append, label + '/reverse', cycles, interval, 1)
            counts(observe(devices[0], append, label + '/forward-plus-reverse', clear=True), 0, 0)
            counts(observe(devices[0], append, label + '/read-after-clear', clear=True), 0, 0)
            wave(devices, current, append, label + '/invalid-one-cycle', 1, interval, 2)
            counts(observe(devices[0], append, label + '/invalid', clear=True), 0, 2)
            expect(devices[0].command(87), [0], 'QDEC stop/restart')
            counts(observe(devices[0], append, label + '/restarted-empty', clear=True), 0, 0)
            wave(devices, current, append, label + '/restart-one-cycle', 1, interval, 0)
            counts(observe(devices[0], append, label + '/restart-count', clear=True), 4, 0)
            append(label, {'status': 'passed', 'forward_cycles': cycles, 'reverse_cycles': cycles,
                           'invalid_cycles': 1, 'restart_cycles': 1,
                           'scope': 'running-direction-change-read-clear-double-transition-restart'})
