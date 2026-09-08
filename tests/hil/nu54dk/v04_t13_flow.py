"""! @brief 기존 S의 RTS→CTS 결선으로100ms 정지와 완전한 payload 재개를 검사합니다. """
import copy
import secrets
import time
from v04_protocol import ProtocolError

MASK = 0xFFFFFFFF


def selected_lane(test):
    """! @brief 단독 UART 또는 계획에 있는 C01/C05의 UART30만 선택합니다. """
    links = test['serial_links']
    if (test['harness'] != 'S' or
            test.get('_reverse_serial') or any(test[key] for key in ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s'))):
        raise ProtocolError('T13 flow requires a fixed S UART topology')
    if len(links) == 1:
        index = 0
    elif ((test['id'], test['name'], len(links)) in ((101, 'C01', 4), (105, 'C05', 5))):
        indices = [index for index, link in enumerate(links) if all(
            link[key]['kind'] == 'uarte' and link[key]['instance'] == 30 for key in ('a', 'b'))]
        if len(indices) != 1:
            raise ProtocolError('T13 concurrent flow needs exactly one UART30')
        index = indices[0]
    else:
        raise ProtocolError('T13 unsupported concurrent flow topology')
    link = links[index]
    if (link['rate'] != 1000000 or link['buffer_bytes'] != 1024 or
            any(endpoint['kind'] != 'uarte' or endpoint['instance'] not in (20, 21, 22, 30) or
                set(endpoint['pins']) != {'txd', 'rxd', 'rts', 'cts'} for endpoint in (link['a'], link['b']))):
        raise ProtocolError('T13 unsupported UART flow fixture')
    return index


def fixture(test, role):
    """! @brief 선택한 peer UART만 활성화 전2선·별도 GPIO RTS로 바꾸며 원본에 표시합니다. """
    if role not in (1, 2):
        raise ProtocolError('T13 flow requires an exact board role')
    index = selected_lane(test)
    modified = copy.deepcopy(test)
    peer = modified['serial_links'][index]['b' if role == 1 else 'a']
    modified['_flow_gpio_peer'] = {'role': 3-role, 'lane': index, 'rts': peer['pins']['rts'], 'hold_us': 100000}
    del peer['pins']['rts'], peer['pins']['cts']
    return modified


def physical(pin):
    port, bit = pin[1:].split('.')
    return int(port)*32+int(bit)


def inspect(words, test, role, device_role):
    """! @brief 실제 GPIO 시간·TX 대기·resume·고정 PSEL을 독립 대조합니다. """
    endpoint = test['serial_links'][selected_lane(test)]['a' if device_role == 1 else 'b']
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


def background_progress(before, after, lane_index):
    """! @brief CTS 대상 외 모든 lane의 양방향 진행을 같은 주입 구간에서 요구합니다. """
    if len(before) != 2 or len(after) != 2:
        raise ProtocolError('T13 concurrent flow requires both board snapshots')
    measured = []
    for role in range(2):
        if len(before[role]) != len(after[role]) or not 0 <= lane_index < len(before[role]):
            raise ProtocolError('T13 concurrent flow lane set drift')
        for index in range(len(before[role])):
            if index == lane_index:
                continue
            delta = {direction: after[role][index][direction]['frames']-before[role][index][direction]['frames']
                     for direction in ('tx', 'rx')}
            if any(value <= 0 for value in delta.values()):
                raise ProtocolError('T13 background serial stalled during CTS injection')
            measured.append({'role': role+1, 'lane': index, 'frames': delta})
    return measured


def background_high(counts, times, interval, test, device_role):
    """! @brief 실제 CTS HIGH 내부 시각에 다른 모든 lane의 TX/RX 완료 증가가 있는지 대조합니다. """
    target = selected_lane(test)
    number = len(test['serial_links'])
    if (number < 2 or device_role not in (1, 2) or
            any(not isinstance(values, list) or len(values) != 20 or
                any(type(value) is not int or not 0 <= value <= MASK for value in values)
                for values in (counts, times, interval)) or
            times[0] != ((1 << number)-1) ^ (1 << target) or
            times[16:] != [number, 1000000, 0, 0]):
        raise ProtocolError('T13 incomplete concurrent CTS HIGH evidence')
    measured = []
    total = (interval[5]-interval[4]) & MASK
    for index in range(5):
        raw = counts[index*4:index*4+4]
        if index == target or index >= number:
            if raw != [0]*4 or any(times[offset+index] for offset in (1, 6, 11)):
                raise ProtocolError('T13 unexpected lane in CTS background evidence')
            continue
        first = (times[1+index]-interval[4]) & MASK
        last = (times[6+index]-interval[4]) & MASK
        endpoint = test['serial_links'][index]['a' if device_role == 1 else 'b']
        if (times[11+index] != endpoint['instance'] or not 0 <= first < last <= total or
                last-first < 80000 or raw[1] <= raw[0] or raw[3] <= raw[2]):
            raise ProtocolError('T13 background lane did not advance within actual CTS HIGH')
        measured.append({'lane': index, 'instance': endpoint['instance'],
            'observed_high_us': last-first, 'tx_frames': raw[1]-raw[0], 'rx_frames': raw[3]-raw[2]})
    return measured


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
            concurrent = len(test['serial_links']) > 1
            before = runner.snapshots(devices, modified, seed, append, label+'/concurrent/before')[1] if concurrent else None
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
                background = [device.command(154, (page,), timeout=2) for page in range(2)] if concurrent else None
                if background:
                    for page, values in enumerate(background):
                        append(suffix+'/background'+str(page), {'status': 'observation', 'words': values})
                raw.append((device, suffix, words, background))
            for device, suffix, words, background in raw:
                append(suffix+'/interval', {'status': 'expected-stall',
                    **inspect(words, test, role, device.image['role'])})
                if background:
                    append(suffix+'/background-high', {'status': 'expected-progress',
                        'lanes': background_high(*background, words, test, device.image['role']),
                        'normal_soak_pass': False})
            if concurrent:
                after = runner.snapshots(devices, modified, seed, append, label+'/concurrent/after')[1]
                append(label+'/concurrent/progress', {'status': 'background-progress',
                    'lanes': background_progress(before, after, selected_lane(test)),
                    'normal_soak_pass': False})
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
