"""! @brief T13의 고정 serial 오류 주입을 정상 연속 전송과 구분해 판정합니다. """
from __future__ import annotations

import secrets
import time

from v04_protocol import ProtocolError
import v04_t13_oracle as oracle

MODES = {1: ('uarte', 1, 1, 21), 2: ('uarte', 3, 2, 23),
         3: ('spim', 1, 3, 31), 4: ('twim', 10, 3, 50), 5: ('twim', 1, 1, 41)}
KINDS = {'uarte': 1, 'spim': 2, 'twim': 4}


def validate_selection(test, role, mode):
    """! @brief 승인된 단독 serial의 해당 controller·UART만 고정 오류 주입을 선택합니다. """
    if (mode not in MODES or role not in (1, 2) or test['harness'] != 'S' or
            len(test['serial_links']) != 1 or any(test[key] for key in
            ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s')) or
            test['serial_links'][0]['a' if role == 1 else 'b']['kind'] != MODES[mode][0]):
        raise ProtocolError('T13 unsupported serial fault selection')


def inspect(words, test, role, mode):
    """! @brief 실제 취소/NACK·부분 DMA·가드를 요구하며 설정 길이를 전송 성공량으로 세지 않습니다. """
    validate_selection(test, role, mode)
    endpoint = test['serial_links'][0]['a' if role == 1 else 'b']
    length = test['serial_links'][0]['buffer_bytes']
    kind, event, pointers, lane_error = MODES[mode]
    if (len(words) != 20 or any(type(value) is not int or not 0 <= value <= oracle.MASK for value in words)
            or endpoint['kind'] != kind or words[:6] != [mode, 1, 0, KINDS[kind], endpoint['instance'], event]
            or words[8:10] != [pointers, 1] or words[15] == 0 or words[18] != lane_error
            or words[19] == 0 or any(value > length for value in words[6:8]+words[16:17]) or
            (mode != 5 and words[17] > length)):
        raise ProtocolError(f'T13 serial fault event/ownership/guard mismatch: {words}')
    frequency = words[19]
    requested_us = ((words[13]-words[12]) & oracle.MASK) * 1000000 / frequency
    observed_us = ((words[14]-words[12]) & oracle.MASK) * 1000000 / frequency
    if not 0 <= requested_us <= observed_us <= 1000000 or (mode != 5 and requested_us < 50):
        raise ProtocolError('T13 fault timing is missing, reversed or exceeded the bound')
    if mode == 5:
        if words[11] != 0x44 or words[16] != 0 or words[7] != 0:
            raise ProtocolError('T13 NACK did not address the unassigned peer address without data')
    else:
        if mode in (1, 2):
            position = 6 if mode == 1 else 7
            if not 0 < words[position] < length or words[10] != 0 or words[16:18] != words[6:8]:
                raise ProtocolError('T13 UART cancellation did not prove a partial transfer')
        elif not 0 < words[16] < length or words[17] >= length:
            raise ProtocolError('T13 controller cancellation lacks a partial hardware DMA amount')
        if mode == 3 and words[10] != 0:
            raise ProtocolError('T13 SPI cancellation returned an unexpected driver error')
        if mode == 4 and words[11] != 0x42:
            raise ProtocolError('T13 TWI cancellation addressed an unapproved target')
    return {'mode': mode, 'role': role, 'instance': endpoint['instance'], 'event': event,
            'api_tx_length': words[6], 'api_rx_length': words[7],
            'observed_tx_amount': words[16], 'observed_rx_amount': None if mode == 5 else words[17],
            'amount_source': 'uarte_terminal_event' if mode in (1, 2) else 'peripheral_amount_register',
            'rx_amount_raw': words[17], 'rx_requested': mode != 5,
            'request_after_submit_us': requested_us, 'event_after_submit_us': observed_us}


def execute(devices, test, role, mode, continuity, append, *, preflight):
    """! @brief 실패 원본·STOP 뒤 다른 nonce의 정상 송수신을 매회 증명하며 최초 실패에서 끝냅니다. """
    import v04_t13_run as runner
    validate_selection(test, role, mode)
    target = next(device for device in devices if device.image['role'] == role)
    repeats = 1 if preflight else 100
    for repetition in range(1, repeats + 1):
        label = f'T13-S/{"fault-preflight" if preflight else "recovery"}/{test["name"]}/mode{mode}/role{role}/repeat{repetition:03}'
        seed = secrets.randbits(32)
        append(label + '/input', {'status': 'input', 'seed': seed, 'test': test,
                                 'mode': mode, 'role': role, 'repetition': repetition})
        continuity.check()
        original_error = None
        raw_fault = None
        try:
            for device in devices:
                if device.command(106, (1,), timeout=2) != [1]:
                    raise ProtocolError('T13 fault clock policy failed')
                if device.command(112, (int(test.get('_reverse_serial', False)),), timeout=2) != [1]:
                    raise ProtocolError('T13 fault role selection failed')
            for device in reversed(devices):
                if device.command(97, (test['id'], seed, 0x53414645), timeout=3) != [1]:
                    raise ProtocolError('T13 fault preparation failed')
                clock = device.command(107, (0,), timeout=2)
                append(label + f'/clock/role{device.image["role"]}', {'status': 'observation', 'words': clock})
                if clock[:2] != [1, 1] or clock[2] == 0:
                    raise ProtocolError('T13 fault precision clock not held')
            runner.prepared_uart_pins(devices, test, append, label + '/prepared')
            runner.prepared_bus_pins(devices, test, append, label + '/prepared')
            if target.command(109, (mode,), timeout=2) != [1]:
                raise ProtocolError('T13 fixed fault could not be armed')
            for device in reversed(devices):
                if device.command(98, timeout=2) != [1]:
                    raise ProtocolError('T13 fault traffic could not start')
            deadline = time.monotonic() + 2
            poll = 0
            while True:
                time.sleep(.05)
                continuity.check()
                raw_fault = target.command(110, timeout=2)
                append(label + f'/fault{poll}', {'status': 'observation', 'words': raw_fault})
                poll += 1
                if (len(raw_fault) == 20 and raw_fault[1] and raw_fault[5] != oracle.MASK) or time.monotonic() >= deadline:
                    break
        except BaseException as error:
            original_error = error
            append(label + '/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        finally:
            for device in devices:
                for opcode, args, name in ((99, (), 'engine'), (100, (0,), 'lane'), (110, (), 'fault')):
                    try:
                        words = device.command(opcode, args, timeout=2)
                        append(label + f'/final/role{device.image["role"]}/{name}', {'status': 'observation', 'words': words})
                        if opcode == 99 and (len(words) != 16 or words[0] != test['id'] or words[5] != 0):
                            original_error = original_error or ProtocolError('T13 fault reset, case drift or lease expiry')
                        if opcode == 110 and device is target:
                            raw_fault = words
                    except BaseException as error:
                        append(label + f'/final/role{device.image["role"]}/{name}',
                               {'status': 'unproven', 'error': f'{type(error).__name__}: {error}'})
                        original_error = original_error or error
            stopped = runner.stop_pair(devices, append, label + '/cleanup')
            pins_idle = runner.idle_pins(devices, append, label + '/pins')
        if original_error is not None:
            raise original_error
        if not stopped or not pins_idle:
            raise ProtocolError('T13 fault STOP/resource return unproven')
        try:
            measured = inspect(raw_fault, test, role, mode)
        except ProtocolError as error:
            append(label + '/failure', {'status': 'failed', 'error': str(error)})
            raise
        append(label + '/fault-observed', {'status': 'expected-fault-observed', **measured})
        restart_seed = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, 1, continuity,
            lambda identifier, row: append(label + '/restart/' + identifier, row),
            preflight=True, seed=restart_seed)
        append(label + '/result', {'status': 'passed', 'fault_seed': seed, 'restart_seed': restart_seed,
                                  'planned_recovery_pass': not preflight, 'normal_soak_pass': False})
        print(f'T13_RECOVERY_PROGRESS case={test["name"]} mode={mode} role={role} completed={repetition}/{repeats}', flush=True)
