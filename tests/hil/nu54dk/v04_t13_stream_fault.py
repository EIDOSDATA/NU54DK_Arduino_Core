"""! @brief I2S/PDM 공급 생략의 실제 오류와 STOP 이후 새 데이터 복구를 분리합니다. """
from __future__ import annotations

import secrets
import time

from v04_protocol import ProtocolError
import v04_t13_oracle as oracle


def validate_selection(test, role, mode):
    """! @brief 단독 I2S 양쪽 또는 실제 PDM 수신 역할만 공급 생략을 허용합니다. """
    if (mode not in (1, 2) or role not in (1, 2) or test['harness'] != 'S' or
            test['serial_links'] or test['adc_channels'] or test['pwm_instance'] or
            (mode == 1 and (not test['i2s'] or test['pdm_instance'])) or
            (mode == 2 and (test['i2s'] or test['pdm_instance'] not in (20, 21) or role != 1))):
        raise ProtocolError('T13 unsupported stream starvation selection')


def inspect(words, stream, test, role, mode):
    """! @brief 네 정상 버퍼 이후의 단일 생략·실제 오류·가드를 독립적으로 요구합니다. """
    validate_selection(test, role, mode)
    index, instance, error = (2, 20, 8) if mode == 1 else (3, test['pdm_instance'], 11)
    if (len(words) != 20 or len(stream) != 20 or
            any(type(value) is not int or not 0 <= value <= oracle.MASK for value in words + stream) or
            words[:4] != [mode, index, instance, 1] or words[4] < 4 or words[5] <= words[4] or
            words[7] != 3 or words[10] < words[4] or words[11] < words[5] or
            words[12:14] != [1, 2] or words[14] == 0 or words[15:18] != [0, 0, 0] or
            words[18] != role or words[19] == 0 or
            stream[0] != index or stream[1:4] != [0, error, 3] or stream[18:20] != [1, 1] or
            stream[4:6] != words[10:12]):
        raise ProtocolError(f'T13 stream fault event/order/guard mismatch: {words}; stream={stream}')
    if (mode == 1 and words[8] != 0) or (mode == 2 and words[8] != (-139 & oracle.MASK)):
        raise ProtocolError('T13 stream driver error does not match underrun/overflow')
    elapsed_us = ((words[9] - words[6]) & oracle.MASK) * 1000000 / words[19]
    if not 0 < elapsed_us <= 1000000:
        raise ProtocolError('T13 stream fault did not follow the skipped request within one second')
    return {'mode': mode, 'role': role, 'instance': instance, 'event': words[7],
            'completed_before_skip': words[4], 'completed_at_fault': words[10],
            'event_after_skip_us': elapsed_us, 'driver_error_raw': words[8]}


def execute(devices, test, role, mode, continuity, append, *, preflight):
    """! @brief 최초 실패 원본과 양쪽 STOP을 보존하고 정상 재시작까지 한 복구 회로 셉니다. """
    import v04_t13_run as runner
    validate_selection(test, role, mode)
    target = next(device for device in devices if device.image['role'] == role)
    index = 2 if mode == 1 else 3
    repeats = 1 if preflight else 100
    for repetition in range(1, repeats + 1):
        label = f'T13-S/{"stream-fault-preflight" if preflight else "stream-recovery"}/{test["name"]}/role{role}/repeat{repetition:03}'
        seed = secrets.randbits(32)
        append(label + '/input', {'status': 'input', 'seed': seed, 'test': test,
                                 'mode': mode, 'role': role, 'repetition': repetition})
        continuity.check()
        original_error = None
        raw_fault = raw_stream = raw_peer_stream = None
        unexpected_i2s_data = False
        peer_tail = None
        try:
            for device in devices:
                if device.command(106, (1,), timeout=2) != [1] or device.command(112, (0,), timeout=2) != [1]:
                    raise ProtocolError('T13 stream fault clock/role policy failed')
            for device in reversed(devices):
                if device.command(97, (test['id'], seed, 0x53414645), timeout=3) != [1]:
                    raise ProtocolError('T13 stream fault preparation failed')
                clock = device.command(107, (0,), timeout=2)
                append(label + f'/clock/role{device.image["role"]}', {'status': 'observation', 'words': clock})
                if clock[:2] != [1, 1] or clock[2] == 0:
                    raise ProtocolError('T13 stream fault precision clock not held')
            if target.command(114, (mode,), timeout=2) != [1]:
                raise ProtocolError('T13 stream starvation could not be armed')
            for device in reversed(devices):
                if device.command(98, timeout=2) != [1]:
                    raise ProtocolError('T13 stream fault traffic could not start')
            deadline = time.monotonic() + 2
            poll = 0
            while True:
                time.sleep(.05)
                continuity.check()
                raw_fault = target.command(115, timeout=2)
                append(label + f'/fault{poll}', {'status': 'observation', 'words': raw_fault})
                poll += 1
                if (len(raw_fault) == 20 and raw_fault[3] and raw_fault[7] != oracle.MASK) or time.monotonic() >= deadline:
                    break
        except BaseException as error:
            original_error = error
            append(label + '/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        finally:
            for device in devices:
                for opcode, args, name in ((99, (), 'engine'), (104, (index,), 'stream'), (115, (), 'fault')):
                    try:
                        words = device.command(opcode, args, timeout=2)
                        append(label + f'/final/role{device.image["role"]}/{name}', {'status': 'observation', 'words': words})
                        if mode == 1 and opcode == 104 and len(words) == 20 and words[2] == 6:
                            unexpected_i2s_data = True
                        if opcode == 99 and (len(words) != 16 or words[0] != test['id'] or words[5] != 0):
                            original_error = original_error or ProtocolError('T13 stream fault reset, case drift or lease expiry')
                            # @brief PREPARE 전 stream 조회를 생략하고 양쪽 STOP 경로를 보존합니다.
                            break
                        if device is target:
                            if opcode == 115:
                                raw_fault = words
                            elif opcode == 104:
                                raw_stream = words
                        elif opcode == 104:
                            raw_peer_stream = words
                    except BaseException as error:
                        append(label + f'/final/role{device.image["role"]}/{name}',
                               {'status': 'unproven', 'error': f'{type(error).__name__}: {error}'})
                        original_error = original_error or error
                        break
            if unexpected_i2s_data:
                captured = {}
                def capture(identifier, row):
                    append(identifier, row)
                    captured[identifier] = row
                runner.failure_snapshots(devices, test, capture, label + '/unexpected-data')
                try:
                    inspect(raw_fault, raw_stream, test, role, mode)
                    prefix = label + '/unexpected-data/failure/role1/i2s-failure-page'
                    metadata = captured.get(prefix+'0', {}).get('words', [])
                    buffer = [word for page in range(1, 17)
                              for word in captured.get(prefix+str(page), {}).get('words', [])]
                    peer_tail = inspect_i2s_peer_tail(raw_fault, raw_peer_stream, metadata, buffer, seed, role)
                    append(label + '/secondary-peer-output-loss', {'status': 'diagnostic', **peer_tail})
                except (ProtocolError, TypeError, IndexError) as error:
                    original_error = original_error or ProtocolError(
                        'T13 unexpected I2S receive data error before recovery: '+str(error))
            stopped = runner.stop_pair(devices, append, label + '/cleanup')
            pins_idle = runner.idle_pins(devices, append, label + '/pins')
        if original_error is not None:
            raise original_error
        if not stopped or not pins_idle:
            raise ProtocolError('T13 stream fault STOP/resource return unproven')
        try:
            measured = inspect(raw_fault, raw_stream, test, role, mode)
            if peer_tail is not None:
                measured['peer_output_loss'] = peer_tail
            if mode == 2:
                measured['peer'] = inspect_pdm_peer(raw_peer_stream)
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
        print(f'T13_STREAM_RECOVERY_PROGRESS case={test["name"]} role={role} completed={repetition}/{repeats}', flush=True)


def inspect_i2s_peer_tail(fault, peer, metadata, buffer, seed, role):
    """! @brief 검증된 B underrun의 마지막 word 또는 nrfx 버퍼 재사용 첫 word 절단·zero 꼬리만 구분합니다. """
    from v04_common_i2s import pattern as i2s_pattern
    if (role != 2 or len(fault) != 20 or len(peer) != 20 or len(metadata) != 20 or
            peer[:3] != [2, 0, 6] or peer[18:20] != [1, 1] or
            metadata[11] != peer[4] or metadata[12] != peer[5] or
            metadata[7] != peer[3] or metadata[6] != peer[15] or
            metadata[4] != peer[13] or metadata[5] != peer[14]):
        raise ProtocolError('T13 I2S peer output-loss metadata mismatch')
    report = oracle.i2s_failure(metadata, buffer, seed, 1)
    boundary = fault[5]*256
    first = report['mismatches'][0]
    if first['index'] not in (boundary-1, boundary):
        raise ProtocolError('T13 I2S peer error precedes the last submitted TX word')
    offset = first['index']-report['first_sample']
    repeated = first['index'] == boundary
    before_stop = i2s_pattern(metadata[3], boundary-256) if repeated else first['expected']
    if (first['actual'] not in [(before_stop & (oracle.MASK << bits)) & oracle.MASK
                                for bits in range(1, 33)] or
            any(value != 0 for value in buffer[offset+1:])):
        raise ProtocolError('T13 I2S peer tail is not one truncated word followed by zeros')
    return {'normal_stream_pass': False, 'target_queued_words': boundary,
            'first_affected_sample': first['index'], 'affected_words': len(report['mismatches']),
            'last_submitted_word_truncated': first['index'] == boundary-1,
            'last_tx_buffer_reuse_truncated': repeated,
            'raw_error_preserved': 6}


def inspect_pdm_peer(words):
    """! @brief PDM 정지의 CS 해제 관측과 다른 peer 오류·가드 손상을 구분합니다. """
    if (not isinstance(words, list) or len(words) != 20 or
            any(type(value) is not int or not 0 <= value <= oracle.MASK for value in words) or
            words[0] != 3 or words[1] not in (0, 1) or words[2:4] not in ([0, 0], [6, 0]) or
            words[4:8] != [0, 1, 0, 0] or words[14] != 1 or words[18:20] != [1, 1]):
        raise ProtocolError(f'T13 PDM peer stop event/guard mismatch: {words}')
    return {'raw_active_before_host_stop': words[1], 'raw_error': words[2], 'raw_detail': words[3],
            'cs_release_transfer_complete': words[2] == 6,
            'normal_stream_pass': False}
