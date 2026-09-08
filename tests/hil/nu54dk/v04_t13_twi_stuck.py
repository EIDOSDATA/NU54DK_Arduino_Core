"""! @brief 기존 SDA LOW100ms의 bounded recovery 오류와 해제 후 staged 복원을 검사합니다. """
import secrets
import time

from v04_protocol import ProtocolError

MASK = 0xFFFFFFFF
CANCELLED = (-140) & MASK


def validate(test):
    if (test['id'] not in (16, 17, 18, 19) or test['harness'] != 'S' or test.get('_reverse_serial') or
            len(test['serial_links']) != 1 or any(test[key] for key in ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s'))):
        raise ProtocolError('T13 stuck SDA requires one fixed S TWIM/TWIS pair')
    link = test['serial_links'][0]
    instance = 30 if test['id'] == 19 else test['id']+4
    pins = {'sda': 'P0.00', 'scl': 'P0.01'} if instance == 30 else {'sda': 'P1.10', 'scl': 'P1.14'}
    if (link['rate'] != 400000 or link['buffer_bytes'] != 256 or link['a']['kind'] != 'twim' or
            link['b']['kind'] != 'twis' or any(endpoint['instance'] != instance or
                endpoint['pins'] != pins for endpoint in (link['a'], link['b']))):
        raise ProtocolError('T13 stuck SDA must use its existing isolated P1 or P0 route')


def inspect(controller, peer, attempts, test, *, stopped=False):
    """! @brief 실제 LOW·staged/ENABLE·DMA 소유권·GPIO 복원·driver 원인을 모두 대조합니다. """
    validate(test)
    if (not isinstance(attempts, list) or len(attempts) != 2 or
            any(not isinstance(words, list) or len(words) != 20 or
                any(type(word) is not int or not 0 <= word <= MASK for word in words)
                for words in (controller, peer, *attempts))):
        raise ProtocolError('T13 complete stuck SDA raw evidence required')
    instance = test['serial_links'][0]['a']['instance']
    sda, scl = (0, 1) if instance == 30 else (42, 46)
    if (controller[:6] != [1, instance, 1, 2, sda, scl] or peer[:6] != [2, instance, 1, 3, sda, scl] or
            any(words[16:] != [1, 1, 1000000, int(stopped)] for words in (controller, peer)) or
            controller[8:11] != [10, CANCELLED, 0] or controller[13:16] != [0, 0, 3] or
            peer[8:12] != [1, 1, 15, 0 if stopped else 1] or peer[13:16] != [0, 0, 0] or
            (not stopped and peer[12] != 1)):
        raise ProtocolError('T13 SDA LOW/release/result/STOP proof differs from staged recovery')
    hold = (peer[7]-peer[6]) & MASK
    if not 100000 <= hold <= 105000:
        raise ProtocolError('T13 actual SDA LOW duration differs from100ms')
    durations = []
    for index, meta in enumerate(attempts):
        first = 6 if index == 0 else 11
        duration = (controller[first+1]-controller[first]) & MASK
        if (not 0 < duration <= 20000 or meta[:5] != [index, 1, 1, 0, 0] or meta[5:9] != [0]*4 or
                meta[9:17] != [sda, scl, 15, 15, 1, 1, index, index] or
                meta[17:] != [10 if index == 0 else 0, CANCELLED if index == 0 else 0, 1000000]):
            raise ProtocolError('T13 recoverBus did not restore staged GPIO/DMA state within the bound')
        durations.append(duration)
    if not 0 < ((controller[11]-controller[7]) & MASK) <= 2000000:
        raise ProtocolError('T13 released recovery did not follow the failed attempt')
    return {'instance': instance, 'sda_low_us': hold, 'recover_us': durations,
            'first_driver_error': -140, 'released_result': 0, 'normal_soak_pass': False}


def execute(devices, test, continuity, append, *, preflight):
    """! @brief 초기 정상 통신·staged 복구 두 번·STOP·새0x42 통신을 별도로 판정합니다. """
    import v04_t13_run as runner
    validate(test)
    controller = next(device for device in devices if device.image['role'] == 1)
    peer = next(device for device in devices if device.image['role'] == 2)
    repeats = 1 if preflight else 100
    for repeat in range(1, repeats+1):
        seed = secrets.randbits(32)
        label = f'T13-S/twi-stuck/{test["name"]}/repeat{repeat:03}'
        append(label+'/input', {'status': 'input', 'seed': seed, 'test': test, 'sda_low_us': 100000,
                               'controller_state': 'staged; no active DMA', 'peer': 'staged TWIS; separate open-drain SDA'})
        runner.execute_group(devices, {'test': test, 'members': [test]}, .25, continuity,
            lambda name, row: append(label+'/baseline/'+name, row), preflight=True, seed=seed)
        failure = None
        captured = {}
        try:
            continuity.check()
            for device in devices:
                if (device.command(170, (device.image['role'],), timeout=2) != [1] or
                        device.command(106, (1,), timeout=2) != [1] or device.command(112, (0,), timeout=2) != [1]):
                    raise ProtocolError('T13 stuck SDA policy failed before PREPARE')
            for device in (peer, controller):
                if device.command(97, (test['id'], seed, 0x53414645), timeout=3) != [1]:
                    raise ProtocolError('T13 staged recovery PREPARE failed')
            if peer.command(171, timeout=2) != [1] or controller.command(172, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 LOW/first recovery execution failed')
            time.sleep(.13)
            continuity.check()
            released = peer.command(173, (0,), timeout=2)
            append(label+'/released-peer', {'status': 'observation', 'words': released})
            if len(released) != 20 or released[3] != 3 or released[9] != 1:
                raise ProtocolError('T13 SDA did not automatically release before second recovery')
            if controller.command(172, (1,), timeout=2) != [1]:
                raise ProtocolError('T13 released recovery execution failed')
        except BaseException as error:
            failure = error
            append(label+'/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        finally:
            for device in devices:
                role = device.image['role']
                captured[role] = []
                for page in range(3 if role == 1 else 1):
                    try:
                        words = device.command(173, (page,), timeout=2)
                        captured[role].append(words)
                        append(label+f'/role{role}/page{page}', {'status': 'observation', 'words': words})
                    except BaseException as error:
                        failure = failure or error
                        append(label+f'/role{role}/page{page}/failure', {'status': 'unproven', 'error': str(error)})
                try:
                    words = device.command(99, timeout=2)
                    append(label+f'/role{role}/engine', {'status': 'observation', 'words': words})
                    if len(words) != 16 or words[:6] != [test['id'], 1, 0, 0, 1, 0]:
                        raise ProtocolError('T13 staged recovery reset, expiry or unexpected active DMA')
                except BaseException as error:
                    failure = failure or error
            stopped = runner.stop_pair(devices, append, label+'/cleanup')
            idle = runner.idle_pins(devices, append, label+'/pins')
        if failure is not None or not stopped or not idle:
            raise failure or ProtocolError('T13 stuck SDA cleanup unproven')
        measured = inspect(captured[1][0], captured[2][0], captured[1][1:], test)
        after = {}
        for device in devices:
            role = device.image['role']
            after[role] = device.command(173, (0,), timeout=2)
            append(label+f'/role{role}/stopped', {'status': 'observation', 'words': after[role]})
        inspect(after[1], after[2], captured[1][1:], test, stopped=True)
        if after[1][:19] != captured[1][0][:19] or after[2][:11] != captured[2][0][:11]:
            raise ProtocolError('T13 first stuck-SDA recovery evidence changed during STOP')
        append(label+'/observed', {'status': 'expected-error-and-recovery', **measured})
        for device in devices:
            if device.command(170, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 stuck SDA policy not released')
        restarted = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, .5, continuity,
            lambda name, row: append(label+'/restart/'+name, row), preflight=True, seed=restarted)
        append(label+'/result', {'status': 'passed', 'planned_twi_stuck_pass': not preflight,
                                'normal_soak_pass': False, 'restart_seed': restarted})
        print(f'T13_TWI_STUCK_PROGRESS case={test["name"]} completed={repeat}/{repeats}', flush=True)
