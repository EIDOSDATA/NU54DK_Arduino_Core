"""! @brief S 결선 checker와 T13의 실제 지속 전송을 exact source·UID로 실행합니다. """
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

import v04_pair as pair
import v04_t13_cases as catalog
import v04_t13_fault as faults
import v04_t13_stream_fault as stream_faults
import v04_t13_pwm_recovery as pwm_recovery
import v04_t13_handover as handover
import v04_t13_conflict as conflicts
import v04_t13_flow as flows
import v04_t13_uart_line as uart_lines
import v04_t13_oracle as oracle
import v04_t13_session as session
import v04_wiring as wiring
from v04_fixture_run import unique_fields
from v04_protocol import ProbeLocks, ProtocolError, validate_pair


def serial_only(test):
    """! @brief 통신 pair의 중복 측정 시간을 계산할 때 순수 serial 시험을 구분합니다. """
    return bool(test['serial_links']) and not any(test[key] for key in
        ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s'))


def grouped(tests):
    """! @brief 동일 SPI/TWI pair의 양쪽 instance는 한 연속 측정의 별도 관측으로 검증합니다. """
    groups = []
    for test in tests:
        key = json.dumps({name: test[name] for name in ('harness', 'duration_seconds', 'serial_links',
            'adc_channels', 'pwm_instance', 'pwm_duty', 'pdm_instance', 'i2s')}, sort_keys=True)
        existing = next((group for group in groups if group['key'] == key), None)
        if existing is None:
            groups.append({'key': key, 'test': test, 'members': [test]})
        else:
            existing['members'].append(test)
    return groups


def snapshots(devices, test, seed, append, label):
    """! @brief 모든 raw를 먼저 보존하고 각 방향의 독립 pattern을 확인합니다. """
    raw = []
    for device in devices:
        role = device.image['role']
        words = device.command(99, timeout=2)
        append(label + f'/role{role}/engine', {'status': 'observation', 'words': words})
        row = {'role': role, 'engine': words, 'lanes': [], 'streams': {}}
        for index in range(len(test['serial_links'])):
            words = device.command(100, (index,), timeout=2)
            append(label + f'/role{role}/lane{index}', {'status': 'observation', 'words': words})
            row['lanes'].append(words)
        for index in oracle.stream_indices(test):
            words = device.command(104, (index,), timeout=2)
            append(label + f'/role{role}/stream{index}', {'status': 'observation', 'words': words})
            row['streams'][index] = words
        raw.append(row)
    engines, lanes = [], []
    for row in raw:
        state = oracle.engine(row['engine'])
        if row['engine'][0] != test['id'] or row['engine'][1:3] != [1, 1]:
            raise ProtocolError('T13 expected active case changed')
        state['streams'] = {index: oracle.stream(index, words, test, seed, row['role'])
                            for index, words in row['streams'].items()}
        engines.append(state)
        lanes.append([oracle.lane(words, seed, index, row['role'], test['serial_links'][index]['buffer_bytes'])
                      for index, words in enumerate(row['lanes'])])
    return engines, lanes


def prepared_uart_pins(devices, test, append, label):
    """! @brief 양쪽 UART 핀 raw를 먼저 보존하고 START 전 잔류·잘못된 출력을 거부합니다. """
    raw = []
    for device in devices:
        role = device.image['role']
        for index, link in enumerate(test['serial_links']):
            endpoint = link['a' if role == 1 else 'b']
            if endpoint['kind'] == 'uarte':
                words = device.command(108, (index,), timeout=2)
                append(label + f'/role{role}/lane{index}/pins', {'status': 'observation', 'words': words})
                raw.append((words, endpoint))
    for words, endpoint in raw:
        oracle.uart_pins(words, endpoint)


def prepared_bus_pins(devices, test, append, label):
    """! @brief 양쪽 모든 SPI/TWI raw를 보존한 뒤 실제 signal 선택을 대조합니다. """
    raw = []
    for device in devices:
        role = device.image['role']
        for index, link in enumerate(test['serial_links']):
            endpoint = link['a' if role == 1 else 'b']
            if endpoint['kind'] != 'uarte':
                words = device.command(113, (index,), timeout=2)
                append(label + f'/role{role}/lane{index}/bus-pins', {'status': 'observation', 'words': words})
                raw.append((words, endpoint))
    for words, endpoint in raw:
        oracle.bus_pins(words, endpoint)


def timings(devices, test, append, label):
    """! @brief queue·완료 관측·service 지연의 고정 histogram을 raw와 함께 보존합니다. """
    raw = []
    for device in devices:
        selectors = [(0xFFFFFFFF, 0, 'service')]
        selectors += [(index, metric, f'lane{index}/metric{metric}')
                      for index in range(len(test['serial_links'])) for metric in range(3)]
        selectors += [(0x100+index, metric, f'stream{index}/metric{metric}')
                      for index in oracle.stream_indices(test) for metric in range(2)]
        for selector, metric, name in selectors:
            words = device.command(105, (selector, metric), timeout=2)
            identifier = label + f'/role{device.image["role"]}/{name}'
            append(identifier, {'status': 'observation', 'words': words})
            raw.append((identifier, words))
    return {identifier: oracle.timing(words) for identifier, words in raw}


def idle_pins(devices, append, label):
    """! @brief 한쪽 실패 후에도 양쪽 GPIO 반환 상태의 증거를 각각 남깁니다. """
    outcomes = []
    for device in devices:
        try:
            words = device.command(51, timeout=2)
            passed = words[1:4] == [0, 0, 0] and words[7] == 0
            append(label + f'/role{device.image["role"]}',
                   {'status': 'observation', 'words': words, 'idle': passed})
            outcomes.append(passed)
        except BaseException as error:
            append(label + f'/role{device.image["role"]}',
                   {'status': 'unproven', 'error': f'{type(error).__name__}: {error}'})
            outcomes.append(False)
    return all(outcomes)


def stop_pair(devices, append, label):
    """! @brief 한쪽 오류에도 다른 보드 STOP을 시도하며 실패를 별도 보존합니다. """
    outcomes = []
    for device in devices:
        try:
            words = device.command(102, timeout=2)
            clock = device.command(107, (0,), timeout=2)
            outcomes.append({'role': device.image['role'], 'words': words, 'clock': clock,
                             'stopped': words[0] == 1 and clock[1] == 0})
        except BaseException as error:
            outcomes.append({'role': device.image['role'], 'stopped': False,
                             'error': f'{type(error).__name__}: {error}'})
    append(label, {'status': 'cleanup', 'outcomes': outcomes})
    return all(row['stopped'] for row in outcomes)


def failure_snapshots(devices, test, append, identifier):
    """! @brief PREPARE 전 보드에는 보호된 stream 명령을 보내지 않아 STOP 세션을 보존합니다. """
    for device in devices:
        prefix = identifier + f'/failure/role{device.image["role"]}'
        try:
            engine = device.command(99, timeout=2)
            append(prefix + '/engine', {'status': 'observation', 'words': engine})
        except BaseException as error:
            append(prefix + '/engine', {'status': 'unproven', 'error': f'{type(error).__name__}: {error}'})
            continue
        observations = [(107, (0,), 'clock')]
        if engine[0] == test['id']:
            observations = [(100, (index,), f'lane{index}') for index in range(len(test['serial_links']))]
            observations += [(124, (index,), f'lane{index}-first-data-fault') for index in range(len(test['serial_links']))]
            if test.get('_flow_gpio_peer'):
                observations += [(127, (), 'cts-flow')]
            if test.get('_uart_line_fault'):
                observations += [(142, (), 'uart-line-fault')]
            observations += [(104, (index,), f'stream{index}') for index in oracle.stream_indices(test)]
            if test['pwm_instance']:
                observations += [(107, (page,), f'pwm-trace{page}') for page in range(5)]
                observations += [(117, (), 'pwm-registers')]
                observations += [(119, (page,), f'pwm-pins-page{page}') for page in range(2)]
            else:
                observations += [(107, (0,), 'clock')]
            if test['i2s']:
                observations += [(118, (page,), f'i2s-failure-page{page}') for page in range(17)]
        for opcode, arguments, name in observations:
            try:
                words = device.command(opcode, arguments, timeout=2)
                append(prefix + '/' + name, {'status': 'observation', 'words': words})
                if opcode == 124:
                    append(prefix + '/' + name + '/analysis', {'status': 'diagnostic',
                        **oracle.serial_data_fault(words)})
            except BaseException as error:
                append(prefix + '/' + name, {'status': 'unproven', 'error': f'{type(error).__name__}: {error}'})
                break


def execute_group(devices, group, duration, continuity, append, *, preflight, seed=None, during=None):
    """! @brief 중단 시간을 합산하지 않고 설정을 유지한 한 구간만 판정합니다. """
    test = group['test']
    seed = secrets.randbits(32) if seed is None else seed
    diagnostic_mode = test.get('_pwm_diagnostic_tail', 0)
    if diagnostic_mode not in (0, 1, 2):
        raise ProtocolError('unsupported fixed PWM diagnostic route')
    diagnostic = bool(diagnostic_mode)
    if diagnostic and (not preflight or test['serial_links'] or not test['pwm_instance'] or
                       test['adc_channels'] or test['pdm_instance'] or test['i2s']):
        raise ProtocolError('PWM failure tail is restricted to standalone diagnostic observation')
    phase = 'pwm-diagnostic' if diagnostic else 'preflight' if preflight else 'soak'
    identifier = f'T13-S/{phase}/{test["name"]}'
    continuity.check()
    append(identifier + '/input', {'status': 'input', 'test': test, 'seed': seed,
        'measured_members': [member['name'] for member in group['members']],
        'duration_seconds': duration, 'frame_period_ms': 20,
        'service_busy_definition': 'service function wall-cycle duration; not total CPU utilization'})
    original_error = None
    try:
        for device in devices:
            if device.command(106, (1,), timeout=2) != [1]:
                raise ProtocolError('T13 precision clock policy failed')
            if device.command(112, (int(test.get('_reverse_serial', False)),), timeout=2) != [1]:
                raise ProtocolError('T13 role selection failed')
            if device.command(116, (int(diagnostic_mode),), timeout=2) != [1]:
                raise ProtocolError('T13 PWM diagnostic policy failed')
        for device in reversed(devices):
            if device.command(97, (test['id'], seed, 0x53414645), timeout=3) != [1]:
                words = device.command(99, timeout=2)
                append(identifier + '/prepare-failure', {'status': 'observation', 'words': words})
                for index in range(len(test['serial_links'])):
                    append(identifier + f'/prepare-lane{index}', {'status': 'observation',
                        'role': device.image['role'], 'words': device.command(100, (index,), timeout=2)})
                for index in oracle.stream_indices(test):
                    append(identifier + f'/prepare-stream{index}', {'status': 'observation',
                        'role': device.image['role'], 'words': device.command(104, (index,), timeout=2)})
                raise ProtocolError('T13 preparation failed')
        for device in devices:
            words = device.command(99, timeout=2)
            append(identifier + f'/prepared/role{device.image["role"]}/engine',
                   {'status': 'observation', 'words': words})
            for index in range(len(test['serial_links'])):
                append(identifier + f'/prepared/role{device.image["role"]}/lane{index}',
                       {'status': 'observation', 'words': device.command(100, (index,), timeout=2)})
            for index in oracle.stream_indices(test):
                append(identifier + f'/prepared/role{device.image["role"]}/stream{index}',
                       {'status': 'observation', 'words': device.command(104, (index,), timeout=2)})
            if words[0] != test['id'] or words[1:3] != [1, 0] or words[4] != 1:
                raise ProtocolError('T13 case failed before both peers were ready')
        prepared_uart_pins(devices, test, append, identifier + '/prepared')
        prepared_bus_pins(devices, test, append, identifier + '/prepared')
        for device in reversed(devices):
            if device.command(98, timeout=2) != [1]:
                raise ProtocolError('T13 start failed')
        if test['pwm_instance']:
            for device in devices:
                append(identifier + f'/started/role{device.image["role"]}/pwm-registers',
                       {'status': 'observation', 'words': device.command(117, timeout=2)})
                append(identifier + f'/started/role{device.image["role"]}/pwm-pins',
                       {'status': 'observation', 'words': device.command(119, (0,), timeout=2)})
        time.sleep(.3)
        first_engines, first_lanes = snapshots(devices, test, seed, append, identifier + '/begin')
        for device in devices:
            words = device.command(107, (0,), timeout=2)
            append(identifier + f'/clock/role{device.image["role"]}', {'status': 'observation', 'words': words})
            if words[:2] != [1, 1] or words[2] == 0:
                raise ProtocolError('T13 precision clock reference not held')
        for role_lanes in first_lanes:
            if any(min(row['tx']['frames'], row['rx']['frames']) == 0 for row in role_lanes):
                raise ProtocolError('T13 traffic not established before measurement')
        if during is not None:
            during()
        start = time.monotonic()
        previous = first_lanes
        previous_engines = first_engines
        tick = 0
        while time.monotonic() - start < duration:
            time.sleep(min(2, max(.1, duration - (time.monotonic() - start))))
            continuity.check()
            for device in devices:
                if device.command(103, timeout=2) != [1]:
                    raise ProtocolError('T13 lease renewal failed')
            engines, lanes = snapshots(devices, test, seed, append, identifier + f'/sample{tick}')
            for role in range(2):
                for index, current in engines[role]['streams'].items():
                    if current['enabled'] and (index != 3 or role != 1):
                        if current['completed'] <= previous_engines[role]['streams'][index]['completed']:
                            raise ProtocolError('T13 stream stalled or reset')
                for index in range(len(test['serial_links'])):
                    for direction in ('tx', 'rx'):
                        if lanes[role][index][direction]['frames'] <= previous[role][index][direction]['frames']:
                            raise ProtocolError('T13 frame stream stalled or reset')
            previous = lanes
            previous_engines = engines
            tick += 1
            if tick % 15 == 0:
                print(f'T13_PROGRESS case={test["name"]} elapsed={time.monotonic()-start:.1f}s target={duration}s', flush=True)
        measured = time.monotonic() - start
        end_engines, end_lanes = snapshots(devices, test, seed, append, identifier + '/end')
        minimum_frames = int(duration * 1000 / 20 * .9)
        for role in range(2):
            if end_engines[role]['elapsed_ms'] - first_engines[role]['elapsed_ms'] < duration * 1000:
                raise ProtocolError('T13 device continuous duration short')
            for index, last in end_engines[role]['streams'].items():
                if last['units'] - first_engines[role]['streams'][index]['units'] < int(duration * last['rate'] * .9):
                    raise ProtocolError('T13 completed stream throughput below configured rate')
            for index in range(len(test['serial_links'])):
                for direction in ('tx', 'rx'):
                    if end_lanes[role][index][direction]['frames'] - first_lanes[role][index][direction]['frames'] < minimum_frames:
                        raise ProtocolError('T13 completed throughput below fixed frame schedule')
        for device in devices:
            if device.command(101, timeout=2) != [1]:
                raise ProtocolError('T13 quiesce failed')
        time.sleep(.15)
        _, drained = snapshots(devices, test, seed, append, identifier + '/drained')
        for index in range(len(test['serial_links'])):
            oracle.paired([drained[role][index] for role in range(2)])
        distributions = timings(devices, test, append, identifier + '/timing')
        append(identifier + '/measurement', {'status': 'measurement-complete',
            'requested_seconds': duration, 'host_continuous_seconds': measured,
            'first_engines': first_engines, 'last_engines': end_engines,
            'first_lanes': first_lanes, 'last_lanes': end_lanes, 'drained_lanes': drained,
            'timing_distributions': distributions})
    except BaseException as error:
        original_error = error
        append(identifier + '/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        failure_snapshots(devices, test, append, identifier)
    finally:
        stopped = stop_pair(devices, append, identifier + '/cleanup')
        pins_idle = idle_pins(devices, append, identifier + '/pins')
    if original_error is not None:
        raise original_error
    if not stopped or not pins_idle:
        raise ProtocolError('T13 STOP or resource return unproven')
    for member in group['members']:
        append(f'T13-S/{phase}/{member["name"]}/result',
               {'status': 'observation-complete' if diagnostic else 'passed',
                'measurement_id': identifier, 'measured_role': member['measured_role'],
                'requested_seconds': duration, 'planned_soak_pass': not preflight,
                'same_pair_shared_measurement': len(group['members']) > 1})


def main(argv=None):
    """! @brief 명시적 execute가 없으면 image/계획만 검사하고 probe에 접근하지 않습니다. """
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dut', 'peer'):
        parser.add_argument('--' + name, required=True)
    for name in ('build-root', 'pyocd', 'session-grant'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--phase', choices=('wiring', 'preflight', 'soak', 'fault-preflight', 'serial-fault',
                                          'handover-preflight', 'handover',
                                          'stream-fault-preflight', 'stream-fault', 'pwm-diagnostic',
                                          'pwm-recovery-preflight', 'pwm-recovery',
                                          'conflict-preflight', 'resource-conflict',
                                          'flow-preflight', 'uart-flow',
                                          'uart-line-preflight', 'uart-line-fault'), default='wiring')
    parser.add_argument('--cases', nargs='+', type=int, default=[])
    parser.add_argument('--fault-mode', type=int, choices=range(1, 6))
    parser.add_argument('--stream-fault-mode', type=int, choices=(1, 2))
    parser.add_argument('--pwm-recovery-mode', type=int, choices=(1, 2))
    parser.add_argument('--conflict-mode', type=int, choices=(1, 2, 3))
    parser.add_argument('--uart-line-mode', choices=('parity', 'break'))
    parser.add_argument('--pwm-diagnostic-route', choices=('led', 'dap'))
    parser.add_argument('--fault-role', type=int, choices=(1, 2), default=1)
    parser.add_argument('--reverse-serial', action='store_true')
    parser.add_argument('--handover-instance', type=int, choices=(0, 20, 21, 22, 30))
    parser.add_argument('--execute-fixture', action='store_true')
    parser.add_argument('--cmsis-dap-limit-packets', action='store_true')
    args = parser.parse_args(argv)
    uids = validate_pair(args.dut, args.peer)
    images = [pair.inspect_image(pair.ROOT, args.build_root.resolve(), role, family='t13_s') for role in (1, 2)]
    grant_bytes = args.session_grant.read_bytes()
    grant = json.loads(grant_bytes, object_pairs_hook=unique_fields)
    session.validate(grant, images, uids)
    available_cases = {test['id']: test for test in catalog.cases() if test['harness'] == 'S'}
    is_handover = args.phase in ('handover-preflight', 'handover')
    if is_handover:
        if args.cases or args.handover_instance is None or args.fault_mode is not None or args.reverse_serial:
            raise ProtocolError('T13 handover requires only its fixed instance selection')
        initial, sequence = handover.route(args.handover_instance)
        args.cases = sorted({test['id'] for test in [initial, *sequence]})
    elif args.handover_instance is not None:
        raise ProtocolError('handover instance requires a handover phase')
    if args.reverse_serial:
        if args.phase not in ('preflight', 'fault-preflight', 'serial-fault'):
            raise ProtocolError('reversed roles cannot replace the planned normal soak')
        available_cases = {key: handover.variant(value, True) if key in args.cases else value
                           for key, value in available_cases.items()}
    if (len(set(args.cases)) != len(args.cases) or any(identifier not in available_cases for identifier in args.cases)
            or (args.phase == 'wiring' and args.cases) or (args.phase != 'wiring' and not args.cases)):
        raise ProtocolError('explicit supported S case set required')
    is_fault = args.phase in ('fault-preflight', 'serial-fault')
    is_stream_fault = args.phase in ('stream-fault-preflight', 'stream-fault')
    is_pwm_recovery = args.phase in ('pwm-recovery-preflight', 'pwm-recovery')
    is_conflict = args.phase in ('conflict-preflight', 'resource-conflict')
    is_flow = args.phase in ('flow-preflight', 'uart-flow')
    is_uart_line = args.phase in ('uart-line-preflight', 'uart-line-fault')
    if is_uart_line:
        for identifier in args.cases:
            uart_lines.validate_selection(available_cases[identifier], args.fault_role, args.uart_line_mode)
    elif args.uart_line_mode is not None:
        raise ProtocolError('UART line mode requires an explicit UART line phase')
    if is_flow:
        for identifier in args.cases:
            flows.fixture(available_cases[identifier], args.fault_role)
    if is_conflict:
        for identifier in args.cases:
            conflicts.validate_selection(available_cases[identifier], args.fault_role, args.conflict_mode)
    elif args.conflict_mode is not None:
        raise ProtocolError('conflict mode requires an explicit conflict phase')
    if is_pwm_recovery:
        for identifier in args.cases:
            pwm_recovery.validate_selection(available_cases[identifier], args.pwm_recovery_mode)
    elif args.pwm_recovery_mode is not None:
        raise ProtocolError('PWM recovery mode requires an explicit PWM recovery phase')
    if is_fault:
        for identifier in args.cases:
            faults.validate_selection(available_cases[identifier], args.fault_role, args.fault_mode)
    elif args.fault_mode is not None:
        raise ProtocolError('fault mode requires an explicit fault phase')
    if is_stream_fault:
        for identifier in args.cases:
            stream_faults.validate_selection(available_cases[identifier], args.fault_role, args.stream_fault_mode)
    elif args.stream_fault_mode is not None:
        raise ProtocolError('stream fault mode requires an explicit stream fault phase')
    if args.phase == 'pwm-diagnostic':
        if any(identifier not in (25, 26, 27) for identifier in args.cases):
            raise ProtocolError('PWM diagnostic requires only standalone PWM20/21/22')
        available_cases = {key: dict(value, _pwm_diagnostic_tail=2 if args.pwm_diagnostic_route == 'dap' else 1) if key in args.cases else value
                           for key, value in available_cases.items()}
    elif args.pwm_diagnostic_route is not None:
        raise ProtocolError('alternate PWM pins require the diagnostic phase')
    evidence = {'schema_version': 1, 'type': 'v04-t13-s-campaign', 'status': 'preflight',
        'phase': args.phase, 'case_ids': args.cases, 'core_revision': images[0]['core_revision'],
        'board_revision': images[0]['board_revision'], 'catalog_sha256': session.catalog_hash(),
        'session_grant_sha256': hashlib.sha256(grant_bytes).hexdigest(), 'swd_frequency_hz': 10000000,
        'external_wiring_executed': False, 'results': [],
        'fault_mode': args.fault_mode, 'fault_role': args.fault_role if is_fault or is_stream_fault or is_conflict or is_flow or is_uart_line else None,
        'conflict_mode': args.conflict_mode,
        'uart_line_mode': args.uart_line_mode,
        'stream_fault_mode': args.stream_fault_mode,
        'pwm_recovery_mode': args.pwm_recovery_mode,
        'reverse_serial': args.reverse_serial, 'handover_instance': args.handover_instance,
        'devices': [{'role': image['role'], 'uid_sha256': hashlib.sha256(uid.encode()).hexdigest(),
                     'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'],
                     'record_sha256': image['record_sha256']} for uid, image in zip(uids, images)]}
    if not args.execute_fixture:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0
    if args.evidence is None:
        raise ProtocolError('exclusive evidence path required')
    with pair.evidence_session(args.evidence, evidence) as journal:
        def append(identifier, result):
            entry = {'id': identifier, **result}
            evidence['results'].append(entry)
            journal.write(json.dumps(entry, ensure_ascii=False) + '\n')
            journal.flush()
        from pyocd.core.helpers import ConnectHelper
        with ProbeLocks(uids), ExitStack() as stack:
            def available():
                return {probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)}
            if not set(uids).issubset(available()):
                raise ProtocolError('T13 requires both exact probes before flash')
            devices = []
            for uid, image in zip(uids, images):
                session.validate(grant, images, uids)
                device, flash = pair.boot_exact(stack, ConnectHelper, args.pyocd, uid, image,
                    10000000, cmsis_dap_limit_packets=args.cmsis_dap_limit_packets)
                devices.append(device)
                evidence['devices'][image['role'] - 1]['flash'] = flash
                capability = 511 if is_pwm_recovery else 255
                if session.verify_profile(device) & capability != capability:
                    raise ProtocolError('T13 serial/stream/timing capabilities missing')
            continuity = session.Continuity(grant, images, uids, devices, available, pair.verify_identity)
            evidence['external_wiring_executed'] = True
            wiring.run_checks(devices, append, continuity.check)
            print('T13_S_WIRING_PASS', flush=True)
            if is_handover:
                handover.execute(devices, args.handover_instance, continuity, append,
                                 preflight=args.phase == 'handover-preflight')
            elif is_uart_line:
                for identifier in args.cases:
                    uart_lines.execute(devices, available_cases[identifier], args.fault_role,
                        args.uart_line_mode, continuity, append, preflight=args.phase == 'uart-line-preflight')
            elif is_flow:
                for identifier in args.cases:
                    flows.execute(devices, available_cases[identifier], args.fault_role,
                        continuity, append, preflight=args.phase == 'flow-preflight')
            elif is_conflict:
                for identifier in args.cases:
                    conflicts.execute(devices, available_cases[identifier], args.fault_role,
                        args.conflict_mode, continuity, append, preflight=args.phase == 'conflict-preflight')
            elif is_fault:
                for identifier in args.cases:
                    faults.execute(devices, available_cases[identifier], args.fault_role, args.fault_mode,
                                    continuity, append, preflight=args.phase == 'fault-preflight')
            elif is_stream_fault:
                for identifier in args.cases:
                    stream_faults.execute(devices, available_cases[identifier], args.fault_role,
                        args.stream_fault_mode, continuity, append, preflight=args.phase == 'stream-fault-preflight')
            elif is_pwm_recovery:
                for identifier in args.cases:
                    pwm_recovery.execute(devices, available_cases[identifier], args.pwm_recovery_mode,
                        continuity, append, preflight=args.phase == 'pwm-recovery-preflight')
            else:
                for group in grouped([available_cases[identifier] for identifier in args.cases]):
                    execute_group(devices, group, 3 if args.phase == 'preflight' else group['test']['duration_seconds'],
                        continuity, append, preflight=args.phase in ('preflight', 'pwm-diagnostic'))
            continuity.check()
            for device in devices:
                words = device.command(51, timeout=2)
                append(f'T13-S/final-pins/role{device.image["role"]}', {'status': 'observation', 'words': words})
                if words[1:4] != [0, 0, 0] or words[7] != 0:
                    raise ProtocolError('T13 final pin direction/pull/lease not idle')
    print(('T13_S_DIAGNOSTIC_COMPLETED; no normal-soak qualification' if args.phase == 'pwm-diagnostic'
           else 'T13_S_CAMPAIGN_PASS; phase=' + args.phase), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ProtocolError, OSError, ValueError) as error:
        print(f'T13_S_FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
