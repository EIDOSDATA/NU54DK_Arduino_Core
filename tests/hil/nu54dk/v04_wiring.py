"""! @brief Fixture 501의 고정 17신호를 단일 LOW와 양쪽 전체 관측으로 대조합니다. """
from __future__ import annotations

from pathlib import Path
import time

import v04_fixture as fixture
from v04_protocol import ProtocolError

CATALOG = Path(__file__).with_name('v04_common_fixture.json')
COUNT = 17
MASK = (1 << COUNT) - 1
NONE = 0xFFFFFFFF


def observed(words, *, low=None, controller=False, armed=True,
             pulse_expirations=0, lease_expirations=0):
    """! @brief 자기 출력 readback뿐 아니라 전체 peer 입력과 설정 원본을 독립 판정합니다. """
    if (len(words) != 8 or any(type(word) is not int or not 0 <= word <= NONE for word in words)
            or (low is not None and (type(low) is not int or not 0 <= low < COUNT))):
        raise ProtocolError('wiring snapshot shape or net invalid')
    expected_levels = MASK if low is None else MASK ^ (1 << low)
    expected_direction = (1 << low) if controller and low is not None else 0
    expected_pulse = low if controller and low is not None else NONE
    expected = [expected_levels, expected_direction, MASK if armed else 0,
                MASK if armed else 0, expected_pulse, pulse_expirations,
                lease_expirations, int(armed)]
    fields = ('levels', 'output_direction', 'pullup', 'owned', 'active_low_net',
              'pulse_expirations', 'lease_expirations', 'armed')
    differences = {name: {'expected': want, 'actual': got}
                   for name, want, got in zip(fields, expected, words)
                   if want != got and (armed or name != 'levels')}
    if differences:
        raise ProtocolError(f'wiring mismatch: {differences}')
    return {'level_mask': words[0], 'low_net': low, 'controller': controller}


def snapshots(devices, append, case_id, **expectation):
    """! @brief 판정 전 raw를 journal에 보존해 첫 실패에서도 관측을 잃지 않습니다. """
    raw = []
    for device in devices:
        row = device.command(51, timeout=2)
        raw.append(row)
        append(case_id + f'/raw-role{device.image["role"]}',
               {'status': 'observation', 'words': row})
    controller_role = expectation.pop('controller_role', None)
    for device, row in zip(devices, raw):
        observed(row, controller=device.image['role'] == controller_role, **expectation)
    return raw


def stop_pair(devices, append, case_id):
    """! @brief 한쪽 실패에도 양쪽 STOP을 시도하고 cleanup 실패를 성공으로 숨기지 않습니다. """
    outcomes = []
    for device in devices:
        try:
            words = device.command(49, timeout=2)
            valid = (len(words) == 8 and words[1:4] == [0, 0, 0] and
                     words[4] == NONE and words[7] == 0)
            outcomes.append({'role': device.image['role'], 'stopped': valid, 'words': words})
        except BaseException as error:
            outcomes.append({'role': device.image['role'], 'stopped': False,
                             'error': f'{type(error).__name__}: {error}'})
    append(case_id, {'status': 'cleanup', 'outcomes': outcomes})
    return all(row['stopped'] for row in outcomes)


def run_confirmed(devices, images, uids, confirmation, append, *, sleep=time.sleep):
    """! @brief 현재 결선 확인 뒤 102개의 LOW/해제 검사와 pulse/lease 만료를 검증합니다. """
    def current():
        """! @brief 기존 실행기는 각 묶음에서 원래 30분 확인 조건을 유지합니다. """
        fixture.validate_confirmation(confirmation, images, uids, 501, catalog_path=CATALOG)
    return run_checks(devices, append, current, sleep=sleep)


def run_checks(devices, append, assert_current, *, sleep=time.sleep):
    """! @brief 호출자가 제공한 현재 실행 조건 검사 뒤 원본 결선 절차를 수행합니다. """
    for controller_role in (1, 2):
        assert_current()
        controller = devices[controller_role - 1]
        label = f'V04-WIRING/501/controller{controller_role}'
        original_error = None
        try:
            for device in devices:
                if device.command(48, (501, 1, fixture.CONSENT, controller_role), timeout=2) != [501, 10000, COUNT]:
                    raise ProtocolError('wiring arm response mismatch')
            sleep(.01)
            snapshots(devices, append, label + '/baseline')
            for repetition in range(3):
                for net in range(COUNT):
                    case_id = label + f'/round{repetition + 1}/net{net + 1}'
                    for device in devices:
                        if device.command(53, timeout=2) != [0]:
                            raise ProtocolError('wiring lease renewal failed')
                    if controller.command(50, (net,), timeout=2) != [net, 500]:
                        raise ProtocolError('wiring LOW response mismatch')
                    sleep(.005)
                    snapshots(devices, append, case_id + '/low', low=net,
                              controller_role=controller_role)
                    if controller.command(52, timeout=2) != [0]:
                        raise ProtocolError('wiring release response mismatch')
                    sleep(.005)
                    snapshots(devices, append, case_id + '/released')
                    append(case_id, {'status': 'passed', 'direction': controller_role,
                                     'net': net + 1, 'repetition': repetition + 1})
        except BaseException as error:
            original_error = error
            raise
        finally:
            if not stop_pair(devices, append, label + '/cleanup') and original_error is None:
                raise ProtocolError('wiring cleanup unproven')

    # @brief 명령 송신을 끊은 구간의 LOW 및 전체 lease 해제를 양쪽에서 각각 관측합니다.
    label = 'V04-WIRING/501/timeout'
    original_error = None
    try:
        assert_current()
        for device in devices:
            role = device.image['role']
            if device.command(48, (501, 1, fixture.CONSENT, role), timeout=2) != [501, 10000, COUNT]:
                raise ProtocolError('timeout test arm failed')
        # @brief 서로 다른 두 net을 순차 구동하며 다음 LOW 전에 이전 pulse가 해제됐는지 읽습니다.
        for device, net in zip(devices, (0, 1)):
            if device.command(50, (net,), timeout=2) != [net, 500]:
                raise ProtocolError('timeout LOW failed')
            sleep(.65)
            raw = device.command(51, timeout=2)
            append(label + f'/pulse-role{device.image["role"]}/raw',
                   {'status': 'observation', 'words': raw})
            observed(raw, pulse_expirations=1)
            append(label + f'/pulse-role{device.image["role"]}', {'status': 'passed'})
        # @brief 마지막 arm보다 충분히 긴 무명령 구간 뒤 소유권/출력/입력 pull 해제를 확인합니다.
        sleep(10.2)
        snapshots(devices, append, label + '/lease', armed=False,
                  pulse_expirations=1, lease_expirations=1)
        append(label + '/lease', {'status': 'passed', 'scope': 'both-firmware-leases-expired'})
    except BaseException as error:
        original_error = error
        raise
    finally:
        if not stop_pair(devices, append, label + '/cleanup') and original_error is None:
            raise ProtocolError('timeout cleanup unproven')
