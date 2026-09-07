"""! @brief 두 sequence와 task 시작·triggered hold를 실제 peer TIMER로 판정합니다. """
from contextlib import contextmanager
import itertools
import time

from v04_common_gpio import expect
from v04_fixture import CONSENT
from v04_protocol import ProtocolError
import v04_pwm_capture as steady


def vectors():
    """! @brief 192 유한 sequence와 96 triggered-step 조건을 생성합니다. """
    for instance, slot, top, idle, dppi in itertools.product((20, 21, 22), range(4), (1000, 4000), (0, 1), (0, 1)):
        for repeats, delay, plays in ((0, 0, 52), (9, 3, 4)):
            yield (instance, slot, top, 0, idle, repeats, delay, plays), dppi
        yield (instance, slot, top, 1, idle, 0, 0, 1), dppi


def finite_received(vector, status, edges):
    """! @brief 시작 전 HIGH의 첫 부분 pulse만 제외하고 전체 sequence 순서를 비교합니다. """
    instance, slot, top, triggered, idle, repeats, delay, plays = vector
    if (len(status) != 12 or status[:4] != [1, 1, 1, 0] or status[11] != 1 or
            status[4] != len(edges) or status[5] != idle or not edges):
        raise ProtocolError('finite PWM incomplete/guard/initial idle')
    for index, row in enumerate(edges):
        if len(row) != 2 or row[1] not in (0, 1) or (index and
                (row[0] <= edges[index - 1][0] or row[1] == edges[index - 1][1])):
            raise ProtocolError('finite PWM missing/reordered edge')
    expect(edges[0][1], 1 - idle, 'finite PWM first transition')
    pulses = [(first[0], second[0] - first[0]) for first, second in zip(edges, edges[1:])
              if first[1] == 1 and second[1] == 0]
    expected = ([25] * (1 + repeats + delay) + [75] * (1 + repeats + delay)) * plays
    if idle:
        expected = expected[1:]
    expect(len(pulses), len(expected), 'finite PWM full pulse count')
    for index, ((timestamp, high), duty) in enumerate(zip(pulses, expected)):
        if abs(high * 100 - top * duty) * 100 > top * duty * 5:
            raise ProtocolError(f'finite PWM sequence duty/order at {index}: {high}, expected {duty}%')
        if index and abs(timestamp - pulses[index - 1][0] - top) * 100 > top * 5:
            raise ProtocolError('finite PWM per-cycle period outside 5 percent')
    if len(pulses) < 100:
        raise ProtocolError('finite PWM fewer than 100 complete pulses')
    return {'complete_pulses': len(pulses), 'omitted_initial_partial_pulses': idle,
            'sequence_pairs': plays, 'period_us': top, 'tolerance_percent': 5}


@contextmanager
def armed(devices, current, append, label, vector, dppi):
    """! @brief START 구독 해제→generator STOP→receiver STOP 순서를 firmware에서 증명합니다. """
    current(508)
    original = None
    try:
        for device in devices:
            expect(device.command(40, (508, 1, CONSENT, 2)), [508, 10000], 'PWM modes arm')
            expect(device.command(54, vector), [0], 'PWM modes prepare')
        expect(devices[1].command(55, (dppi,)), [0], 'PWM deferred play')
        idle = devices[0].command(59)
        append(label + '/idle-before-start', {'status': 'observation', 'words': idle})
        expect(idle[0], vector[4], 'peer physical idle before task')
        yield
    except BaseException as error:
        original = error
        append(label + '/failure', {'status': 'failed', 'error': str(error)})
        raise
    finally:
        rows = []
        for device in reversed(devices):
            try:
                rows.append({'role': device.image['role'], 'words': device.command(45)})
            except BaseException as error:
                rows.append({'role': device.image['role'], 'error': str(error)})
        append(label + '/cleanup', {'status': 'cleanup', 'outcomes': rows})
        if any(row.get('words') != [0, 1, 1] for row in rows) and original is None:
            raise ProtocolError('PWM modes cleanup unproven')


def capture(devices, current, append, label, duration, start=False):
    """! @brief 한정 시간 capture가 끝난 뒤 raw edge와 양쪽 event 상태를 저장합니다. """
    current(508)
    for device in devices:
        expect(device.command(58), [0], 'PWM lease')
    expect(devices[0].command(47, (duration,)), [0], 'async PWM capture')
    if start:
        expect(devices[1].command(56), [0], 'PWM CPU/DPPI START')
    deadline = time.monotonic() + duration / 1e6 + 2
    while True:
        current(508)
        status = devices[0].command(46)
        if len(status) != 12 or status[3]:
            raise ProtocolError(f'async PWM capture error {status}')
        if status[2]:
            break
        if time.monotonic() > deadline:
            raise ProtocolError('async PWM capture timed out')
        time.sleep(.03)
    generator = devices[1].command(46)
    modes = [device.command(59) for device in devices]
    edges = []
    for offset in range(0, status[4], 8):
        count = min(8, status[4] - offset)
        raw = devices[0].command(44, (offset, count))
        expect(len(raw), count * 2, 'PWM raw edge packet')
        edges.extend(raw[index:index + 2] for index in range(0, len(raw), 2))
    append(label + '/raw', {'status': 'observation', 'receiver': status, 'generator': generator,
                           'modes': modes, 'edges': edges})
    current(508)
    if generator[3] or generator[11] != 1 or any(row[1] or row[6:8] != [1, 0] for row in modes):
        raise ProtocolError('PWM generator/event-order/guard error')
    return status, generator, modes, edges


def run(devices, current, append):
    """! @brief 유한 자동 STOP과 수동 NEXTSTEP 사이 100주기 유지 결과를 분리합니다. """
    for vector, dppi in vectors():
        label = 'V04-COMMON-PWM-MODES/' + '/'.join(map(str, (*vector, dppi)))
        with armed(devices, current, append, label, vector, dppi):
            if not vector[3]:
                status, generator, modes, edges = capture(devices, current, append, label,
                                                          vector[2] * 104 + 150000, start=True)
                expect(generator[8:11], [vector[7], vector[7], 1], 'finite sequence/playback events')
                result = finite_received(vector, status, edges)
                append(label, {'status': 'passed', 'scope': 'seq0-seq1-repeats-end-delay-task-idle',
                               'dppi_start': bool(dppi), **result})
            else:
                expect(devices[1].command(56), [0], 'triggered PWM START')
                results = []
                for step, duty in enumerate((25, 50, 75)):
                    current(508)
                    if step:
                        expect(devices[1].command(57), [0], 'public PWM NEXTSTEP')
                    time.sleep(vector[2] * 2 / 1e6)
                    status, generator, modes, edges = capture(devices, current, append,
                        label + f'/step{step}', vector[2] * 102)
                    expect(modes[1][2], step, 'public step count')
                    expect(generator[10], 0, 'triggered playback remains active before terminal sample')
                    if len(edges) < 201:
                        raise ProtocolError('triggered PWM fewer than 100 complete periods')
                    measured = status.copy()
                    measured[4] = 201
                    result = steady.received((vector[0], vector[1], vector[2], duty, 1), measured, edges[:201])
                    results.append({'step': step, 'duty': duty, **result})
                append(label, {'status': 'passed', 'scope': 'triggered-step-hold-100-periods-per-level',
                               'dppi_start': bool(dppi), 'results': results})
