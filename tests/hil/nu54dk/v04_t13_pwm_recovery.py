"""! @brief PWM loop 중간 STOP과 START 없는 준비 취소를 새 정상 capture 복구와 구분합니다. """
from __future__ import annotations

import secrets
import time
from v04_protocol import ProtocolError
import v04_t13_oracle as oracle


def validate_selection(test, mode):
    """! @brief 기존 S P1.14 단독 PWM20/21/22의 두 종료 조건만 허용합니다. """
    if (mode not in (1, 2) or test['id'] not in (25, 26, 27) or test['harness'] != 'S' or
            test['pwm_instance'] not in (20, 21, 22) or test['serial_links'] or
            any(test[key] for key in ('adc_channels', 'pdm_instance', 'i2s')) or
            test.get('_pwm_diagnostic_tail') or test.get('_reverse_serial')):
        raise ProtocolError('T13 unsupported PWM recovery selection')


def inspect_unstarted(observation, instance, *, stopped=False):
    """! @brief 실제 미시작 task 준비·무에지·idle·가드와 정지 후 소유권 반환을 대조합니다. """
    proof = observation['proof']
    expected_state = 1 if stopped else 2
    if (len(proof) != 13 or any(type(value) is not int or not 0 <= value <= oracle.MASK for value in proof) or
            proof[:4] != [2, instance, 1, expected_state] or
            bool(proof[4]) != (not stopped) or proof[5] != int(not stopped) or
            proof[6:9] != [0, 0, 0] or proof[10] != 1 or proof[12] == 0):
        raise ProtocolError(f'T13 PWM unstarted task/state/event mismatch: {proof}')
    for role in (1, 2):
        stream = observation[f'stream{role}']
        if (len(stream) != 20 or stream[:4] != [1, int(not stopped), 0, 0] or
                stream[4] != 0 or stream[6:8] != [0, 0] or stream[18:20] != [1, 1]):
            raise ProtocolError(f'T13 PWM unstarted capture/guard mismatch role={role}: {stream}')
    if not stopped:
        a, b = observation['pins1'], observation['pins2']
        if len(a) != 20 or len(b) != 20 or a[0:3] != [1, 0, 46] or b[:3] != [2, 0, instance] or a[4] != 0 or b[8] != 0:
            raise ProtocolError('T13 PWM unstarted output did not remain idle on both boards')
    return proof[11], proof[12]


def unstarted(devices, test, seed, continuity, append, label):
    """! @brief START task 주소를 읽기만 하고100ms 무출력 관측 뒤 양쪽 STOP을 반드시 시도합니다. """
    import v04_t13_run as runner
    peer = next(device for device in devices if device.image['role'] == 2)
    original_error = None
    def snapshot(suffix):
        result = {'proof': peer.command(122, timeout=2)}
        for device in devices:
            role = device.image['role']
            result[f'stream{role}'] = device.command(104, (1,), timeout=2)
            result[f'pins{role}'] = device.command(119, (0,), timeout=2)
        result['dma_raw'] = peer.command(117, timeout=2)
        append(label + '/' + suffix, {'status': 'observation', **result})
        return result
    try:
        continuity.check()
        for device in devices:
            if device.command(106, (1,), timeout=2) != [1] or device.command(116, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 PWM recovery clock/normal-pin policy failed')
        for device in reversed(devices):
            if device.command(97, (test['id'], seed, 0x53414645), timeout=3) != [1]:
                raise ProtocolError('T13 PWM recovery preparation failed')
        if peer.command(121, timeout=2) != [1]:
            raise ProtocolError('T13 PWM unstarted task preparation rejected')
        for device in reversed(devices):
            if device.command(98, timeout=2) != [1]:
                raise ProtocolError('T13 PWM unstarted capture could not start')
        first = snapshot('begin')
        time.sleep(.1)
        continuity.check()
        last = snapshot('end')
        first_cycle, frequency = inspect_unstarted(first, test['pwm_instance'])
        last_cycle, last_frequency = inspect_unstarted(last, test['pwm_instance'])
        elapsed_us = ((last_cycle - first_cycle) & oracle.MASK) * 1000000 / frequency
        if frequency != last_frequency or not 100000 <= elapsed_us <= 1000000:
            raise ProtocolError('T13 PWM unstarted observation shorter than100ms or invalid clock')
        append(label + '/interval', {'status': 'measurement-complete', 'unstarted_us': elapsed_us})
    except BaseException as error:
        original_error = error
        append(label + '/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        runner.failure_snapshots(devices, test, append, label)
    finally:
        stopped = runner.stop_pair(devices, append, label + '/cleanup')
        idle = runner.idle_pins(devices, append, label + '/pins')
    if original_error is not None:
        raise original_error
    if not stopped or not idle:
        raise ProtocolError('T13 PWM unstarted STOP/resource return unproven')
    inspect_unstarted(snapshot('stopped'), test['pwm_instance'], stopped=True)


def execute(devices, test, mode, continuity, append, *, preflight):
    """! @brief 종료 조건과 새 seed 정상 capture 재시작을 모두 통과한 회만 복구로 셉니다. """
    import v04_t13_run as runner
    validate_selection(test, mode)
    repeats = 1 if preflight else 100
    for repetition in range(1, repeats + 1):
        label = f'T13-S/{"pwm-recovery-preflight" if preflight else "pwm-recovery"}/{test["name"]}/mode{mode}/repeat{repetition:03}'
        seed = secrets.randbits(32)
        append(label + '/input', {'status': 'input', 'mode': mode, 'seed': seed, 'test': test})
        if mode == 2:
            unstarted(devices, test, seed, continuity, append, label + '/unstarted')
        else:
            runner.execute_group(devices, {'test': test, 'members': [test]}, .1, continuity,
                lambda identifier, row: append(label + '/active/' + identifier, row), preflight=True, seed=seed)
        restart_seed = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, 1, continuity,
            lambda identifier, row: append(label + '/restart/' + identifier, row), preflight=True, seed=restart_seed)
        append(label + '/result', {'status': 'passed', 'mode': mode, 'fault_seed': seed,
            'restart_seed': restart_seed, 'planned_pwm_recovery_pass': not preflight, 'normal_soak_pass': False})
        print(f'T13_PWM_RECOVERY_PROGRESS case={test["name"]} mode={mode} completed={repetition}/{repeats}', flush=True)
