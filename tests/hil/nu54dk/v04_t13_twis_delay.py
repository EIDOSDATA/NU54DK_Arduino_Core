"""! @brief 실제 TWIS write 요청 뒤2ms 버퍼 공급 지연과 양방향 복구를 검사합니다. """
import copy
import secrets

from v04_protocol import ProtocolError
import v04_t13_twi_stuck as stuck

MASK = 0xFFFFFFFF


def fixture(test):
    """! @brief 기존 S의 A controller·B target 및 고정400kHz 경로만 허용합니다. """
    stuck.validate(test)
    result = copy.deepcopy(test)
    result['_twis_supply_delay'] = {'role': 2, 'write_request_hold_us': 2000}
    return result


def inspect(words, test, role, *, stopped=False):
    """! @brief 실제 요청·LOW 관측·지연·공급·가드·양방향 완료를 모두 요구합니다. """
    fixture(test)
    endpoint = test['serial_links'][0]['a' if role == 1 else 'b']
    if (role not in (1, 2) or not isinstance(words, list) or len(words) != 20 or
            any(type(word) is not int or not 0 <= word <= MASK for word in words) or
            words[:4] != [role, endpoint['instance'], 1, 0 if role == 1 else 2] or
            words[16] == 0 or words[17] == 0 or words[18:] != [1000000, int(stopped)]):
        raise ProtocolError('T13 TWIS delay identity/progress/STOP proof missing')
    duration = 0
    if role == 2:
        duration = (words[5]-words[4]) & MASK
        if (not 2000 <= duration <= 5000 or words[6:11] != [1, 1, 0, 0, 0] or
                words[11] < 2 or words[12:16] != [0, 0, 1, 1]):
            raise ProtocolError('T13 TWIS actual write request, sampled SCL LOW or delayed supply missing')
    elif words[4:16] != [0]*8 + [MASK, 0, 0, 0]:
        raise ProtocolError('T13 TWIS delay controller unexpectedly withheld buffers')
    return {'role': role, 'observed_delay_us': duration, 'scl_low_samples': words[11],
            'rx_frames': words[16], 'tx_frames': words[17], 'normal_soak_pass': False}


def execute(devices, test, continuity, append, *, preflight):
    """! @brief 한 번의 실제 지연 뒤 STOP과 새 seed의 정상 재획득까지 묶어 대조합니다. """
    import v04_t13_run as runner
    modified = fixture(test)
    repeats = 1 if preflight else 100
    for repeat in range(1, repeats+1):
        seed = secrets.randbits(32)
        label = f'T13-S/twis-delay/{test["name"]}/repeat{repeat:03}'
        append(label+'/input', {'status': 'input', 'seed': seed, 'test': modified})
        for device in devices:
            if device.command(180, (device.image['role'],), timeout=2) != [1]:
                raise ProtocolError('T13 TWIS delay policy failed before PREPARE')
        observed = {}
        def observe():
            failure = None
            for device in devices:
                role = device.image['role']
                try:
                    words = device.command(181, timeout=2)
                    observed[role] = words
                    append(label+f'/role{role}/raw', {'status': 'observation', 'words': words})
                except BaseException as error:
                    failure = failure or error
                    append(label+f'/role{role}/failure', {'status': 'unproven', 'error': str(error)})
            if failure is not None:
                raise failure
            for role, words in observed.items():
                append(label+f'/role{role}/delay', {'status': 'expected-delay', **inspect(words, test, role)})
        runner.execute_group(devices, {'test': modified, 'members': [modified]}, .5, continuity,
            lambda identifier, row: append(label+'/maintained/'+identifier, row),
            preflight=True, seed=seed, during=observe)
        stopped = []
        for device in devices:
            role = device.image['role']
            words = device.command(181, timeout=2)
            stopped.append((role, words))
            append(label+f'/role{role}/stopped', {'status': 'observation', 'words': words})
        for role, words in stopped:
            inspect(words, test, role, stopped=True)
            before = observed[role]
            if words[:16] != before[:16] or any(words[index] < before[index] for index in (16, 17)):
                raise ProtocolError('T13 TWIS delay evidence changed during STOP')
        for device in devices:
            if device.command(180, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 TWIS delay policy not cleared')
        restarted = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, .5, continuity,
            lambda identifier, row: append(label+'/reacquired/'+identifier, row),
            preflight=True, seed=restarted)
        append(label+'/result', {'status': 'passed', 'planned_twis_delay_pass': not preflight,
                                'normal_soak_pass': False, 'restart_seed': restarted})
        print(f'T13_TWIS_DELAY_PROGRESS case={test["name"]} completed={repeat}/{repeats}', flush=True)
