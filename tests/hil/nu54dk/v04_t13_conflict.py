"""! @brief 현재 S UART21/22/30의 block·GPIO·DMA 충돌을 원자적 거부와 복구로 판정합니다. """
import secrets
from v04_protocol import ProtocolError

MASK = 0xFFFFFFFF


def validate_selection(test, role, mode):
    if (role not in (1, 2) or mode not in (1, 2, 3) or test['harness'] != 'S' or
            len(test['serial_links']) != 1 or test.get('_reverse_serial') or
            any(test[key] for key in ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s'))):
        raise ProtocolError('T13 unsupported conflict selection')
    endpoint = test['serial_links'][0]['a' if role == 1 else 'b']
    if endpoint['kind'] != 'uarte' or endpoint['instance'] not in (21, 22, 30) or len(endpoint['pins']) != 4:
        raise ProtocolError('T13 conflict requires the fixed four-wire P1 UART fixture')


def inspect(words, instance, mode):
    """! @brief 거부 전후 기존 UART 상태·PSEL·ENABLE·guard가 같아야 성공입니다. """
    other = instance if mode == 1 else 22 if instance == 21 else 21
    if (not isinstance(words, list) or len(words) != 20 or
            any(type(word) is not int or not 0 <= word <= MASK for word in words) or
            instance not in (21, 22, 30) or mode not in (1, 2, 3) or
            words[:9] != [mode, instance, other, 0, 0, 2 if mode == 2 else 8, MASK, 3, 3] or
            any(words[index] != words[index+1] for index in range(9, 19, 2)) or
            words[17] == 0 or words[19] != 1):
        raise ProtocolError(f'T13 conflict was not atomically rejected: {words}')
    return {'mode': mode, 'instance': instance, 'alternative_instance': other,
            'result': words[5], 'existing_uart_unchanged': True, 'guards_preserved': True}


def execute(devices, test, role, mode, continuity, append, *, preflight):
    """! @brief 매회 기존 payload 유지·STOP·새 seed 정상 재획득을 따로 요구합니다. """
    import v04_t13_run as runner
    validate_selection(test, role, mode)
    target = next(device for device in devices if device.image['role'] == role)
    instance = test['serial_links'][0]['a' if role == 1 else 'b']['instance']
    repeats = 1 if preflight else 100
    for repeat in range(1, repeats+1):
        seed = secrets.randbits(32)
        label = f'T13-S/conflict/{test["name"]}/role{role}/mode{mode}/repeat{repeat:03}'
        append(label+'/input', {'status': 'input', 'seed': seed, 'role': role, 'mode': mode, 'test': test})
        def inject():
            continuity.check()
            words = target.command(125, (mode,), timeout=2)
            append(label+'/raw', {'status': 'observation', 'words': words})
            append(label+'/rejected', {'status': 'expected-rejection', **inspect(words, instance, mode)})
        group = {'test': test, 'members': [test]}
        runner.execute_group(devices, group, .25, continuity,
            lambda identifier, row: append(label+'/maintained/'+identifier, row),
            preflight=True, seed=seed, during=inject)
        restarted = seed ^ 0x9E3779B9
        runner.execute_group(devices, group, .25, continuity,
            lambda identifier, row: append(label+'/reacquired/'+identifier, row),
            preflight=True, seed=restarted)
        append(label+'/result', {'status': 'passed', 'seed': seed, 'restart_seed': restarted,
            'planned_conflict_pass': not preflight, 'normal_soak_pass': False})
        print(f'T13_CONFLICT_PROGRESS instance={instance} role={role} mode={mode} completed={repeat}/{repeats}', flush=True)
