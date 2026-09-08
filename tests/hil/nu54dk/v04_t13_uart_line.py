"""! @brief 실제 UART parity 오류·1ms break 입력 뒤 STOP과 정상 재시작을 검증합니다. """
import copy
import secrets
import time

from v04_protocol import ProtocolError
import v04_t13_flow as flow
import v04_t13_oracle as oracle

MASK = oracle.MASK


def validate_selection(test, role, mode):
    """! @brief 기존 S의 네 선 UART만 사용하며 별도 GPIO 출력을 추가하지 않습니다. """
    if mode not in ('parity', 'break') or len(test['serial_links']) != 1:
        raise ProtocolError('T13 unsupported UART line fault')
    flow.fixture(test, role)


def seed_for_parity(seed, peer_role):
    """! @brief 첫8비트의 even parity가0인 seed를 골라8N1 stop1과 불일치를 만듭니다. """
    for offset in range(65536):
        candidate = (seed + offset) & MASK
        value = oracle.pattern(oracle.lane_seed(candidate, 0, peer_role), 0)
        if value.bit_count() % 2 == 0:
            return candidate
    raise ProtocolError('T13 cannot select a deterministic parity stimulus')


def inspect(words, test, role, device_role, mode, *, lane=None):
    """! @brief 오류 API 원본과 실제 GPIO 시간·반환을 정상 payload 판정과 분리합니다. """
    validate_selection(test, role, mode)
    target = device_role == role
    endpoint = test['serial_links'][0]['a' if device_role == 1 else 'b']
    policy = (1 if target else 2) if mode == 'parity' else (3 if target else 4)
    if (not isinstance(words, list) or len(words) != 20 or
            any(type(word) is not int or not 0 <= word <= MASK for word in words) or
            words[:4] != [policy, endpoint['instance'], 1, 1] or
            words[15:19] != [3 if policy == 1 else 1,
                flow.physical(endpoint['pins']['txd']), flow.physical(endpoint['pins']['rxd']), 1000000] or
            words[19] != 1):
        raise ProtocolError(f'T13 UART fault identity/configuration/STOP proof missing: {words}')
    measured = {'policy': policy, 'instance': endpoint['instance'], 'normal_soak_pass': False}
    if target:
        mask = words[5]
        # @brief 8N1의 stop1이 parity 자리로, 다음 start0이 8E1의 stop 자리로 들어올 수 있습니다.
        valid_mask = (mask in (2, 6)) if mode == 'parity' else (mask != 0 and mask & ~12 == 0)
        elapsed = (words[10]-words[9]) & MASK
        if (words[4] != 5 or not valid_mask or words[8] != 1 or not 0 < elapsed <= 2000000 or
                words[11:15] != [0, 0, 0, 0] or
                not isinstance(lane, list) or len(lane) != 20 or
                any(type(word) is not int or not 0 <= word <= MASK for word in lane) or
                lane[:3] != [25, mask, 0] or lane[19] != 20):
            raise ProtocolError(f'T13 UART expected error/guard/stop differs: {words}; lane={lane}')
        measured.update(error_mask=mask, arm_to_error_us=elapsed,
            api_transferred_raw=words[6], api_buffer_raw=words[7],
            parity_observed=bool(mask & 2),
            framing_observed=bool(mask & 4), break_flag_observed=bool(mask & 8))
    else:
        if words[4:9] != [MASK, 0, 0, 0, 0] or words[10] != 0:
            raise ProtocolError('T13 UART stimulus metadata contains an unexpected receiver error')
        elapsed = (words[11]-words[9]) & MASK
        if not 0 < elapsed <= 2000000:
            raise ProtocolError('T13 UART stimulus did not start after arming')
        if mode == 'break':
            duration = (words[12]-words[11]) & MASK
            if not 1000 <= duration <= 2000 or words[13:15] != [7, 1]:
                raise ProtocolError('T13 break requires actual HIGH/LOW/HIGH,1ms and GPIO release')
            measured['low_duration_us'] = duration
        elif words[12:15] != [0, 0, 0]:
            raise ProtocolError('T13 parity stimulus unexpectedly used GPIO')
    return measured


def execute(devices, test, role, mode, continuity, append, *, preflight):
    """! @brief 첫 실패를 보존하고 양쪽 정지가 확인된 경우에만 새 seed로 정상 재획득합니다. """
    import v04_t13_run as runner
    validate_selection(test, role, mode)
    target = next(device for device in devices if device.image['role'] == role)
    peer = next(device for device in devices if device.image['role'] != role)
    marked = copy.deepcopy(test)
    marked['_uart_line_fault'] = mode
    repeats = 1 if preflight else 100
    for repeat in range(1, repeats+1):
        seed = secrets.randbits(32)
        if mode == 'parity':
            seed = seed_for_parity(seed, peer.image['role'])
        label = f'T13-S/uart-line/{test["name"]}/role{role}/{mode}/repeat{repeat:03}'
        append(label+'/input', {'status': 'input', 'seed': seed, 'role': role, 'mode': mode,
            'test': marked, 'peer_first_byte': oracle.pattern(oracle.lane_seed(seed, 0, 3-role), 0)})
        runner.execute_group(devices, {'test': test, 'members': [test]}, .25, continuity,
            lambda identifier, row: append(label+'/baseline/'+identifier, row), preflight=True, seed=seed)
        original_error = None
        raw = {}
        try:
            continuity.check()
            policies = (1, 2) if mode == 'parity' else (3, 4)
            for device, policy in zip((target, peer), policies):
                if (device.command(140, (policy,), timeout=2) != [1] or
                        device.command(106, (1,), timeout=2) != [1] or
                        device.command(112, (0,), timeout=2) != [1]):
                    raise ProtocolError('T13 UART line policy was not accepted before PREPARE')
            for device in reversed(devices):
                if device.command(97, (test['id'], seed, 0x53414645), timeout=3) != [1]:
                    raise ProtocolError('T13 UART line preparation failed')
            runner.prepared_uart_pins(devices, test, append, label+'/prepared')
            for device in devices:
                clock = device.command(107, (0,), timeout=2)
                append(label+f'/clock/role{device.image["role"]}', {'status': 'observation', 'words': clock})
                if len(clock) < 3 or clock[:2] != [1, 1] or clock[2] == 0:
                    raise ProtocolError('T13 UART line precision clock failed')
                armed = device.command(141, timeout=2)
                append(label+f'/arm/role{device.image["role"]}', {'status': 'observation', 'words': armed})
                if armed != [1]:
                    raise ProtocolError('T13 UART line ARM failed before RX START')
            # @brief break는 DUT RX 시작 전에 peer TX GPIO HIGH를 준비합니다.
            if mode == 'break':
                if peer.command(98, timeout=2) != [1] or peer.command(144, timeout=2) != [1]:
                    raise ProtocolError('T13 released peer TX HIGH was not prepared before DUT RX')
            for device in ((target,) if mode == 'break' else (target, peer)):
                if device.command(98, timeout=2) != [1]:
                    raise ProtocolError('T13 UART line START failed')
            if mode == 'break':
                before = target.command(142, timeout=2)
                append(label+'/before-break', {'status': 'observation', 'words': before})
                if len(before) != 20 or before[3] != 0 or before[4] != MASK:
                    raise ProtocolError('T13 DUT error preceded the break pulse')
                if peer.command(143, timeout=2) != [1]:
                    raise ProtocolError('T13 released peer TX could not produce the fixed break pulse')
            deadline = time.monotonic() + 2
            poll = 0
            while True:
                time.sleep(.025)
                continuity.check()
                words = target.command(142, timeout=2)
                append(label+f'/poll{poll}', {'status': 'observation', 'words': words})
                poll += 1
                if (len(words) == 20 and words[3] == 1) or time.monotonic() >= deadline:
                    break
        except BaseException as error:
            original_error = error
            append(label+'/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        finally:
            for device in devices:
                device_role = device.image['role']
                raw[device_role] = {}
                for opcode, args, name in ((99, (), 'engine'), (142, (), 'fault'), (100, (0,), 'lane')):
                    try:
                        words = device.command(opcode, args, timeout=2)
                        raw[device_role][name] = words
                        append(label+f'/final/role{device_role}/{name}', {'status': 'observation', 'words': words})
                        if opcode == 99 and (len(words) != 16 or words[0] != test['id'] or words[5] != 0):
                            original_error = original_error or ProtocolError('T13 UART line case drift/reset/lease expiry')
                            break
                    except BaseException as error:
                        original_error = original_error or error
                        append(label+f'/final/role{device_role}/{name}', {'status': 'unproven', 'error': str(error)})
                        break
            stopped = runner.stop_pair(devices, append, label+'/cleanup')
            pins_idle = runner.idle_pins(devices, append, label+'/pins')
            for device in devices:
                try:
                    words = device.command(142, timeout=2)
                    raw[device.image['role']]['after_stop'] = words
                    append(label+f'/after-stop/role{device.image["role"]}', {'status': 'observation', 'words': words})
                except BaseException as error:
                    original_error = original_error or error
        if original_error is not None:
            raise original_error
        if not stopped or not pins_idle:
            raise ProtocolError('T13 UART line STOP/resource return unproven')
        for device in devices:
            device_role = device.image['role']
            row = raw[device_role]
            if row['after_stop'][:19] != row['fault'][:19]:
                raise ProtocolError('T13 first UART line fault changed during STOP')
            measured = inspect(row['after_stop'], test, role, device_role, mode, lane=row['lane'])
            append(label+f'/observed/role{device_role}', {'status': 'expected-fault-observed', **measured})
            if device is peer and row['lane'][:2] != [0, 0]:
                raise ProtocolError('T13 UART line stimulus peer failed independently')
        for device in devices:
            if device.command(140, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 UART line policy was not cleared before reacquisition')
        restart_seed = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, 1, continuity,
            lambda identifier, row: append(label+'/restart/'+identifier, row), preflight=True, seed=restart_seed)
        append(label+'/result', {'status': 'passed', 'fault_seed': seed, 'restart_seed': restart_seed,
            'planned_uart_line_recovery_pass': not preflight, 'normal_soak_pass': False})
        print(f'T13_UART_LINE_PROGRESS case={test["name"]} role={role} mode={mode} completed={repeat}/{repeats}', flush=True)
