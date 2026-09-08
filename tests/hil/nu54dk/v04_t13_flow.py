"""! @brief 기존 S의 RTS→CTS 결선으로100ms 정지와 완전한 payload 재개를 검사합니다. """
import copy
import secrets
import time
from v04_protocol import ProtocolError

MASK = 0xFFFFFFFF


def fixture(test, role):
    """! @brief peer만 활성화 전2선 UART·별도 GPIO RTS로 바꾸며 원본에 표시합니다. """
    if (role not in (1, 2) or test['harness'] != 'S' or len(test['serial_links']) != 1 or
            test.get('_reverse_serial') or any(test[key] for key in ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s'))):
        raise ProtocolError('T13 flow requires one fixed S UART')
    link = test['serial_links'][0]
    if (link['rate'] != 1000000 or link['buffer_bytes'] != 1024 or
            any(endpoint['kind'] != 'uarte' or endpoint['instance'] not in (20, 21, 22, 30) or
                set(endpoint['pins']) != {'txd', 'rxd', 'rts', 'cts'} for endpoint in (link['a'], link['b']))):
        raise ProtocolError('T13 unsupported UART flow fixture')
    modified = copy.deepcopy(test)
    peer = modified['serial_links'][0]['b' if role == 1 else 'a']
    modified['_flow_gpio_peer'] = {'role': 3-role, 'rts': peer['pins']['rts'], 'hold_us': 100000}
    del peer['pins']['rts'], peer['pins']['cts']
    return modified


def physical(pin):
    port, bit = pin[1:].split('.')
    return int(port)*32+int(bit)


def inspect(words, test, role, device_role):
    """! @brief 실제 GPIO 시간·TX 대기·resume·고정 PSEL을 독립 대조합니다. """
    endpoint = test['serial_links'][0]['a' if device_role == 1 else 'b']
    observer = device_role == role
    pin = physical(endpoint['pins']['cts' if observer else 'rts'])
    if (not isinstance(words, list) or len(words) != 20 or
            any(type(word) is not int or not 0 <= word <= MASK for word in words) or
            words[:4] != [1 if observer else 2, endpoint['instance'], 3, pin] or
            words[6] != 1000000 or words[11:14] != [1, 1, 0 if observer else 1]):
        raise ProtocolError(f'T13 incomplete CTS interval proof: {words}')
    duration = ((words[5]-words[4]) & MASK)*1000000/words[6]
    if not (90000 <= duration <= 120000 if observer else 100000 <= duration <= 105000):
        raise ProtocolError('T13 actual CTS interval differs from fixed100ms')
    expected_pins = [physical(endpoint['pins'][name]) for name in ('txd', 'rxd')]
    expected_pins += [physical(endpoint['pins'][name]) if observer else MASK for name in ('rts', 'cts')]
    if words[15:19] != expected_pins or bool(words[19] & 1) != observer:
        raise ProtocolError('T13 active flow PSEL/HWFC differs from declared fixture')
    if observer:
        if words[10] != 1 or not 0 <= words[8]-words[7] <= 1 or words[9] <= words[8]:
            raise ProtocolError('T13 TX did not wait for CTS or resume afterward')
    elif words[7:9] != [0, 0] or words[10] != 0 or words[14] != 1:
        raise ProtocolError('T13 peer GPIO interval metadata mismatch')
    return {'physical_pin': pin, 'duration_us': duration, 'observer': observer,
            'waiting_tx_seen': bool(words[10]), 'normal_soak_pass': False}


def execute(devices, test, role, continuity, append, *, preflight):
    import v04_t13_run as runner
    modified = fixture(test, role)
    target = next(device for device in devices if device.image['role'] == role)
    peer = next(device for device in devices if device.image['role'] != role)
    repeats = 1 if preflight else 100
    for repeat in range(1, repeats+1):
        seed = secrets.randbits(32)
        label = f'T13-S/flow/{test["name"]}/role{role}/repeat{repeat:03}'
        append(label+'/input', {'status': 'input', 'seed': seed, 'test': modified,
                               'original_test': test, 'role': role})
        for device, mode in ((target, 1), (peer, 2)):
            if device.command(126, (mode,), timeout=2) != [1]:
                raise ProtocolError('T13 flow policy failed before PREPARE')
        def inject():
            continuity.check()
            for device in (target, peer):
                if device.command(128, timeout=2) != [1]:
                    raise ProtocolError('T13 CTS observation/injection did not start')
            time.sleep(.5)
            continuity.check()
            raw = []
            for device in (target, peer):
                words = device.command(127, timeout=2)
                suffix = label+'/role'+str(device.image['role'])
                append(suffix+'/raw', {'status': 'observation', 'words': words})
                raw.append((device, suffix, words))
            for device, suffix, words in raw:
                append(suffix+'/interval', {'status': 'expected-stall',
                    **inspect(words, test, role, device.image['role'])})
        runner.execute_group(devices, {'test': modified, 'members': [modified]}, .5,
            continuity, lambda identifier, row: append(label+'/maintained/'+identifier, row),
            preflight=True, seed=seed, during=inject)
        for device in devices:
            if device.command(126, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 GPIO flow policy was not released')
        restarted = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, .5,
            continuity, lambda identifier, row: append(label+'/reacquired/'+identifier, row),
            preflight=True, seed=restarted)
        append(label+'/result', {'status': 'passed', 'planned_flow_pass': not preflight,
                                'normal_soak_pass': False, 'restart_seed': restarted})
        print(f'T13_FLOW_PROGRESS case={test["name"]} role={role} completed={repeat}/{repeats}', flush=True)
