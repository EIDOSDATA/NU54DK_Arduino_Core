"""! @brief 두 선 UART의 실제 RX 버퍼 요청 뒤2ms 공급 지연과 정상 복구를 검사합니다. """
import copy
import secrets
import time

from v04_protocol import ProtocolError
import v04_t13_uart_line as uart_line

MASK = 0xFFFFFFFF


def fixture(test, role):
    """! @brief 활성화 전에 양쪽 RTS/CTS를 제외하며 기존 TX/RX만 사용합니다. """
    uart_line.validate_selection(test, role, 'parity')
    if test['id'] not in (2, 3, 4, 5):
        raise ProtocolError('T13 RX delay requires a fixed S UART')
    result = copy.deepcopy(test)
    for side in ('a', 'b'):
        pins = result['serial_links'][0][side]['pins']
        del pins['rts'], pins['cts']
    result['_rx_supply_delay'] = {'role': role, 'hold_us': 2000, 'frame_period_ms': 20}
    return result


def inspect(words, test, role, device_role, *, stopped=False):
    """! @brief 실제 반환·요청·지연·재공급과 다음 완료량을 대조합니다. """
    fixture(test, role)
    delayed = role == device_role
    endpoint = test['serial_links'][0]['a' if device_role == 1 else 'b']
    if (device_role not in (1, 2) or not isinstance(words, list) or len(words) != 20 or
            any(type(word) is not int or not 0 <= word <= MASK for word in words) or
            words[:4] != [1 if delayed else 2, endpoint['instance'], 1, 2 if delayed else 0] or
            words[18:] != [1000000, int(stopped)] or words[15] <= words[7] or words[16] == 0):
        raise ProtocolError('T13 RX delay identity/ARM/progress/STOP proof missing')
    duration = 0
    if delayed:
        duration = (words[6]-words[5]) & MASK
        if (not 2000 <= duration <= 5000 or not 0 < ((words[5]-words[4]) & MASK) <= 200000 or
                words[8] <= words[7] or words[9] <= words[10] or words[11:15] != [0, 0, 1, 1] or
                words[15] <= words[8] or words[17] < words[9]):
            raise ProtocolError('T13 RX buffers were not returned, delayed and replenished as declared')
    elif (words[5:7] != [0, 0] or words[8:10] != [0, 0] or
          words[11:15] != [MASK, 0, 0, 0] or words[17] < words[10]):
        raise ProtocolError('T13 RX delay peer unexpectedly withheld buffers')
    return {'role': device_role, 'delayed': delayed, 'observed_delay_us': duration,
            'rx_frames_after_supply': words[15]-words[8] if delayed else words[15]-words[7],
            'normal_soak_pass': False}


def execute(devices, test, role, continuity, append, *, preflight):
    """! @brief 한 번의 제한 지연 뒤 양쪽 STOP과 원래 네 선 UART의 새 seed 재획득을 요구합니다. """
    import v04_t13_run as runner
    modified = fixture(test, role)
    repeats = 1 if preflight else 100
    for repeat in range(1, repeats+1):
        seed = secrets.randbits(32)
        label = f'T13-S/rx-delay/{test["name"]}/role{role}/repeat{repeat:03}'
        append(label+'/input', {'status': 'input', 'seed': seed, 'test': modified, 'original_test': test})
        for device in devices:
            if device.command(160, (1 if device.image['role'] == role else 2,), timeout=2) != [1]:
                raise ProtocolError('T13 RX delay policy failed before PREPARE')
        observed = {}
        def inject():
            failure = None
            try:
                continuity.check()
                for device in devices:
                    if device.command(161, timeout=2) != [1]:
                        raise ProtocolError('T13 RX delay ARM failed')
                time.sleep(.3)
                continuity.check()
            except BaseException as error:
                failure = error
            finally:
                for device in devices:
                    device_role = device.image['role']
                    try:
                        words = device.command(162, timeout=2)
                        observed[device_role] = words
                        append(label+f'/role{device_role}/raw', {'status': 'observation', 'words': words})
                    except BaseException as error:
                        failure = failure or error
                        append(label+f'/role{device_role}/failure', {'status': 'unproven', 'error': str(error)})
            if failure is not None:
                raise failure
            for device_role, words in observed.items():
                append(label+f'/role{device_role}/delay', {'status': 'expected-delay',
                    **inspect(words, test, role, device_role)})
        runner.execute_group(devices, {'test': modified, 'members': [modified]}, .5, continuity,
            lambda identifier, row: append(label+'/maintained/'+identifier, row),
            preflight=True, seed=seed, during=inject)
        stopped = []
        for device in devices:
            words = device.command(162, timeout=2)
            stopped.append((device.image['role'], words))
            append(label+f'/role{device.image["role"]}/stopped', {'status': 'observation', 'words': words})
        for device_role, words in stopped:
            inspect(words, test, role, device_role, stopped=True)
            before = observed[device_role]
            if words[:15] != before[:15] or any(words[index] < before[index] for index in (15, 16, 17)):
                raise ProtocolError('T13 RX delay evidence changed or reset during STOP')
        for device in devices:
            if device.command(160, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 RX delay policy not cleared')
        restarted = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, .5, continuity,
            lambda identifier, row: append(label+'/reacquired/'+identifier, row),
            preflight=True, seed=restarted)
        append(label+'/result', {'status': 'passed', 'planned_rx_delay_pass': not preflight,
                                'normal_soak_pass': False, 'restart_seed': restarted})
        print(f'T13_RX_DELAY_PROGRESS case={test["name"]} role={role} completed={repeat}/{repeats}', flush=True)
