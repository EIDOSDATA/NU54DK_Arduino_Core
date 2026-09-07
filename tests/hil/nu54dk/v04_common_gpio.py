"""! @brief 공통 net의 GPIO API와 GPIOTE 실제 관측을 독립 기대값과 비교합니다. """
from __future__ import annotations

from contextlib import contextmanager
import itertools
import time

from v04_fixture import CONSENT
from v04_protocol import ProtocolError

NONE = 0xFFFFFFFF


def expect(actual, wanted, label):
    """! @brief 응답을 느슨한 참/거짓 판정 없이 대조합니다. """
    if actual != wanted:
        raise ProtocolError(f'{label}: actual={actual}; expected={wanted}')


def observe(device, append, label):
    """! @brief 실패 판정 전에 장치 원본을 보존합니다. """
    words = device.command(68, timeout=2)
    append(label + f'/raw-role{device.image["role"]}', {'status': 'observation', 'words': words})
    if len(words) != 16 or any(type(value) is not int for value in words):
        raise ProtocolError('GPIO snapshot shape mismatch')
    if words[8] or words[9] or words[11] or words[15] != 1:
        raise ProtocolError(f'GPIO error/leakage/lease mismatch: {words}')
    return words


def level(device, append, label, net, value, output=False, gpio=True):
    """! @brief 실제 pad, Arduino readback, 전체 출력 방향을 함께 판정합니다. """
    words = observe(device, append, label)
    expect(words[0], net, 'selected net')
    if gpio or not output:
        expect(words[1], value, 'physical input')
    # @brief GPIOTE 출력은 입력 buffer가 분리될 수 있으므로 실제 level 판정은 peer 입력이 소유합니다.
    expect(words[2], value if gpio else NONE, 'Arduino input')
    expect(words[3], (1 << net) if output else 0, 'all-net output direction')
    return words


@contextmanager
def armed(devices, controller, current, append, label):
    """! @brief 양쪽 STOP을 독립 시도하고 cleanup 오류도 원본과 함께 유지합니다. """
    current(502)
    original = None
    try:
        for device in devices:
            expect(device.command(64, (502, 1, CONSENT, controller), timeout=2), [502, 10000], 'arm')
        yield
    except BaseException as error:
        original = error
        append(label + '/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        raise
    finally:
        results = []
        for device in (devices[controller - 1], devices[2 - controller]):
            try:
                words = device.command(65, timeout=2)
                good = len(words) == 16 and words[0] == NONE and words[3] == 0 and words[13:] == [0, 0, 0]
                results.append({'role': device.image['role'], 'stopped': good, 'words': words})
            except BaseException as error:
                results.append({'role': device.image['role'], 'stopped': False, 'error': str(error)})
        append(label + '/cleanup', {'status': 'cleanup', 'outcomes': results})
        if not all(row['stopped'] for row in results) and original is None:
            raise ProtocolError('common GPIO cleanup unproven')


def gpio_case(devices, controller, net, repetition, current, append):
    """! @brief 양방향 input/pull/output/open-drain을 공개 GPIO API로 검사합니다. """
    label = f'V04-COMMON-GPIO/role{controller}/net{net}/repeat{repetition}'
    dut, peer = devices[controller - 1], devices[2 - controller]
    with armed(devices, controller, current, append, label):
        expect(peer.command(66, (net, 0)), [0], 'peer input')
        for mode, value in ((2, 0), (1, 1)):
            expect(dut.command(66, (net, mode)), [0], 'input pull')
            time.sleep(.005)
            level(dut, append, label + f'/pull{mode}', net, value)
            level(peer, append, label + f'/pull{mode}', net, value)
        expect(dut.command(66, (net, 3)), [0], 'GPIO output')
        for value in (0, 1, 0):
            expect(dut.command(67, (value,)), [0], 'digitalWrite')
            level(dut, append, label + f'/output{value}', net, value, True)
            level(peer, append, label + f'/output{value}', net, value)
        expect(peer.command(66, (net, 1)), [0], 'open-drain peer pullup')
        expect(dut.command(66, (net, 4)), [0], 'open-drain output')
        for value in (0, 1, 0):
            expect(dut.command(67, (value,)), [0], 'open-drain write')
            words = level(dut, append, label + f'/open-drain{value}', net, value, True)
            expect((words[4] >> 8) & 7, 6, 'S0D1 physical drive mode')
            level(peer, append, label + f'/open-drain{value}', net, value)
        append(label, {'status': 'passed', 'scope': 'public-gpio-api-peer-levels-pulls-open-drain'})


def channel_vectors():
    """! @brief 가용 8/4채널을 각 port의 승인 net에 순환 대응합니다. """
    for instance, channels, nets in ((20, 8, tuple(range(6))), (30, 4, tuple(range(6, 10)))):
        for channel in range(channels):
            yield instance, channel, nets[channel % len(nets)], channels


def task_case(devices, controller, vector, polarity, repetition, current, append):
    """! @brief GPIOTE OUT/SET/CLR task의 실제 외부 level과 비대상 핀 방향을 검사합니다. """
    instance, channel, net, channels = vector
    label = f'V04-COMMON-GPIOTE-TASK/{instance}/{channel}/role{controller}/pol{polarity}/repeat{repetition}'
    dut, peer = devices[controller - 1], devices[2 - controller]
    with armed(devices, controller, current, append, label):
        expect(peer.command(66, (net, 0)), [0], 'peer input')
        expect(dut.command(70, (net, channel, polarity, 1)), [0, channels], 'GPIOTE output')
        for task, value in ((2, 0), (1, 1), (0, 1 if polarity == 0 else 0), (2, 0), (0, 0 if polarity == 1 else 1)):
            expect(dut.command(71, (task,)), [0], 'GPIOTE task')
            level(dut, append, label + f'/task{task}', net, value, True, False)
            level(peer, append, label + f'/task{task}', net, value)
        append(label, {'status': 'passed'})


def edge_case(devices, controller, vector, polarity, hz, repetition, current, append):
    """! @brief 유한 1000 에지의 발생·수신 원본과 rising/falling/toggle count를 대조합니다. """
    instance, channel, net, channels = vector
    label = f'V04-COMMON-GPIOTE-EDGE/{instance}/{channel}/role{controller}/pol{polarity}/{hz}Hz/repeat{repetition}'
    generator, receiver = devices[controller - 1], devices[2 - controller]
    with armed(devices, controller, current, append, label):
        expect(generator.command(70, (net, channel, 2, 1)), [0, channels], 'generator')
        expect(receiver.command(70, (net, channel, polarity, 0)), [0, channels], 'receiver')
        level(receiver, append, label + '/initial', net, 0, gpio=False)
        started = time.monotonic()
        expect(generator.command(72, (hz, 1000)), [0], 'finite start')
        deadline = started + 1000 / hz * 1.5 + 2
        while True:
            for device in devices:
                expect(device.command(69, timeout=2), [0], 'lease renewal')
            raw = observe(generator, append, label + '/progress')
            if raw[7] == 0:
                break
            if time.monotonic() > deadline:
                raise ProtocolError('finite GPIOTE source did not finish')
            time.sleep(.5)
        time.sleep(.02)
        sent = level(generator, append, label + '/final', net, 0, True, False)
        received = level(receiver, append, label + '/final', net, 0, False, False)
        expect(sent[6], 1000, 'source task count')
        expect(received[5], 1000 if polarity == 2 else 500, 'GPIOTE event count')
        expect(sent[5], 0, 'source event leakage')
        expect(received[6], 0, 'receiver output leakage')
        append(label, {'status': 'passed', 'emitted_edges': sent[6], 'received_events': received[5],
                       'elapsed_seconds': time.monotonic() - started,
                       'max_poll_gap_us': [sent[10], received[10]],
                       'scope': 'functional-event-count-not-precision-timing'})


def run(devices, current, append, *, section='all'):
    """! @brief 고정 시험 순서이며 실패 뒤 다음 case를 실행하지 않습니다. """
    if section in ('all', 'gpio'):
        for controller in (1, 2):
            label = f'V04-COMMON-GPIO/negative/role{controller}'
            with armed(devices, controller, current, append, label):
                for subcase, error in ((0, 2), (1, 4), (2, 4)):
                    words = devices[controller - 1].command(73, (subcase,))
                    append(label + f'/subcase{subcase}/raw', {'status': 'observation', 'words': words})
                    expect(words, [error, 0, 0], 'atomic invalid-pin/channel/port rejection')
                append(label, {'status': 'passed'})
        for controller, net, repetition in itertools.product((1, 2), range(17), range(1, 11)):
            gpio_case(devices, controller, net, repetition, current, append)
    if section in ('all', 'task'):
        for controller, vector, polarity, repetition in itertools.product((1, 2), tuple(channel_vectors()), range(3), range(1, 11)):
            task_case(devices, controller, vector, polarity, repetition, current, append)
    if section in ('all', 'edge'):
        for controller, vector, polarity, hz, repetition in itertools.product((1, 2), tuple(channel_vectors()), range(3), (100, 1000), range(1, 11)):
            edge_case(devices, controller, vector, polarity, hz, repetition, current, append)
