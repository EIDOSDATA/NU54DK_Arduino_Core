"""! @brief S/U 결선 checker와 T13의 실제 지속 전송을 exact source·UID로 실행합니다. """
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
import v04_t13_spi_timing as spi_timing
import v04_t13_i2s_edge as i2s_edges
import v04_t13_conflict as conflicts
import v04_t13_flow as flows
import v04_t13_uart_line as uart_lines
import v04_t13_spi_boundary as spi_boundaries
import v04_t13_rx_delay as rx_delays
import v04_t13_twi_stuck as twi_stuck
import v04_t13_twis_delay as twis_delays
import v04_t13_oracle as oracle
import v04_t13_session as session
import v04_wiring as wiring
from v04_fixture_run import unique_fields
from v04_protocol import ProbeLocks, ProtocolError, validate_pair

U_PHASES = ('wiring', 'preflight', 'soak', 'fault-preflight', 'serial-fault',
            'flow-preflight', 'uart-flow')


def validate_harness_phase(harness, phase, *, reverse_serial=False):
    """! @brief U에서 UARTE00 정상·HWFC·취소 외 S 전용 실행을 거부합니다. """
    if harness == 'U' and (phase not in U_PHASES or reverse_serial):
        raise ProtocolError('T13 U permits only fixed UARTE00 normal, flow and cancellation phases')


def wiring_nets(harness):
    """! @brief U는 실제 UARTE00 네 신호만, S는 고정 17신호 전체를 검사합니다. """
    return wiring.UART00_NETS if harness == 'U' else None


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


def snapshots(devices, test, seed, append, label, *, cts_pause=None):
    """! @brief 모든 raw를 먼저 보존하고 각 방향의 독립 pattern을 확인합니다. """
    if cts_pause is not None and not isinstance(cts_pause, flows.ConfirmedPause):
        raise ProtocolError('T13 completion allowance requires verified CTS evidence')
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
        lanes.append([oracle.lane(words, seed, index, row['role'], test['serial_links'][index]['buffer_bytes'],
                      completion_limits_ms=cts_pause.limits(test, seed, row['role'], index) if cts_pause else (100, 100))
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
            if test.get('_spi_timing_mode'):
                observations += [(183, (0,), 'spi-timing')]
            if test.get('_flow_gpio_peer'):
                observations += [(127, (), 'cts-flow')]
            if test.get('_uart_line_fault'):
                observations += [(142, (), 'uart-line-fault')]
            if test.get('_twis_supply_delay'):
                observations += [(181, (), 'twis-supply-delay')]
            observations += [(104, (index,), f'stream{index}') for index in oracle.stream_indices(test)]
            if test['pwm_instance']:
                observations += [(107, (page,), f'pwm-trace{page}') for page in range(5)]
                observations += [(117, (), 'pwm-registers')]
                observations += [(119, (page,), f'pwm-pins-page{page}') for page in range(2)]
            else:
                observations += [(107, (0,), 'clock')]
            if test['i2s']:
                # @brief 긴 DMA 원본 조회 전에 살아 있는 peer의 핀·DMA·IRQ와 최초 오류 상태를 보존합니다.
                observations += [(118, (page,), f'i2s-failure-page{page}')
                                 for page in (17, 18, 19, *range(17))]
                if test.get('_i2s_edge_diagnostic'):
                    observations += [(186, (page,), f'i2s-edge-page{page}') for page in range(3)]
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


def renew_lease(device, test, append, identifier):
    """! @brief lease 거부 직후 firmware stream 오류를 먼저 보존해 상위 오류 가림을 막습니다. """
    words = device.command(103, timeout=2)
    if words == [1]:
        return
    role = device.image['role']
    append(identifier + f'/lease-rejected/role{role}',
           {'status': 'observation', 'words': words})
    if test['i2s']:
        try:
            stream = device.command(104, (2,), timeout=2)
            append(identifier + f'/lease-rejected/role{role}/stream2',
                   {'status': 'observation', 'words': stream})
        except BaseException as error:
            append(identifier + f'/lease-rejected/role{role}/stream2',
                   {'status': 'unproven', 'error': f'{type(error).__name__}: {error}'})
        else:
            if len(stream) == 20 and stream[:3] == [2, 0, 6]:
                raise ProtocolError('T13 I2S receive data mismatch preceded lease renewal rejection')
    raise ProtocolError('T13 lease renewal failed')


def start_order(devices, test):
    """! @brief 단독 역방향 SPI/TWI는 수신 target의 DMA 준비가 끝난 뒤 controller를 시작합니다. """
    if len(test['serial_links']) == 1:
        link = test['serial_links'][0]
        if (link['a']['kind'], link['b']['kind']) in (('spis', 'spim'), ('twis', 'twim')):
            return sorted(devices, key=lambda device: device.image['role'])
    return sorted(devices, key=lambda device: device.image['role'], reverse=True)


def start_devices(devices, test, append, identifier, *, serial_start_barrier=False):
    """! @brief 고정 CTS 시험에서는 양쪽 RX 준비 응답을 받은 뒤 송신을 허용합니다. """
    barrier_cases = {'S': (2, 3, 4, 5, 6, 7, 8, 9, 10, 101, 105), 'U': (1,)}
    if serial_start_barrier and test['id'] not in barrier_cases.get(test['harness'], ()):
        raise ProtocolError('T13 serial start barrier is restricted to fixed CTS cases')
    ordered = start_order(devices, test)
    if {device.image['role'] for device in ordered} != {1, 2} or len(ordered) != 2:
        raise ProtocolError('T13 start requires both distinct roles')
    append(identifier + '/start-order', {'status': 'observation',
        'roles': [device.image['role'] for device in ordered],
        'serial_start_barrier': serial_start_barrier})
    origin = time.monotonic()
    for device in ordered:
        if device.command(98, (1,) if serial_start_barrier else (), timeout=2) != [1]:
            raise ProtocolError('T13 start failed')
        append(identifier + f'/start-ready/role{device.image["role"]}', {'status': 'observation',
            'host_elapsed_seconds': time.monotonic()-origin, 'transmit_held': serial_start_barrier})
    if serial_start_barrier:
        for device in ordered:
            if device.command(184, timeout=2) != [1]:
                raise ProtocolError('T13 serial transmission release failed')
            append(identifier + f'/start-released/role{device.image["role"]}', {'status': 'observation',
                'host_elapsed_seconds': time.monotonic()-origin, 'both_receivers_prepared': True})


def execute_group(devices, group, duration, continuity, append, *, preflight, seed=None, during=None,
                  serial_start_barrier=False):
    """! @brief 중단 시간을 합산하지 않고 설정을 유지한 한 구간만 판정합니다. """
    test = group['test']
    if test.get('_spi_timing_mode') and not preflight:
        raise ProtocolError('T13 SPI timing diagnostic cannot replace normal soak')
    seed = secrets.randbits(32) if seed is None else seed
    diagnostic_mode = test.get('_pwm_diagnostic_tail', 0)
    if diagnostic_mode not in (0, 1, 2):
        raise ProtocolError('unsupported fixed PWM diagnostic route')
    edge_diagnostic_mode = test.get('_i2s_edge_diagnostic', 0)
    if type(edge_diagnostic_mode) is not int or edge_diagnostic_mode not in (0, 1, 2):
        raise ProtocolError('unsupported fixed I2S edge diagnostic route')
    edge_diagnostic = edge_diagnostic_mode != 0
    diagnostic = bool(diagnostic_mode) or edge_diagnostic
    if diagnostic_mode and (not preflight or test['serial_links'] or not test['pwm_instance'] or
                            test['adc_channels'] or test['pdm_instance'] or test['i2s']):
        raise ProtocolError('PWM failure tail is restricted to standalone diagnostic observation')
    if edge_diagnostic and (not preflight or test['serial_links'] or test['adc_channels'] or
                            test['pwm_instance'] or test['pdm_instance'] or not test['i2s']):
        raise ProtocolError('I2S edge diagnostic is restricted to standalone observation')
    phase = ('pwm-diagnostic' if diagnostic_mode else 'i2s-edge-diagnostic'
             if edge_diagnostic else 'preflight' if preflight else 'soak')
    identifier = f'T13-{test["harness"]}/{phase}/{test["name"]}'
    continuity.check()
    append(identifier + '/input', {'status': 'input', 'test': test, 'seed': seed,
        'measured_members': [member['name'] for member in group['members']],
        'duration_seconds': duration, 'frame_period_ms': 20,
        'serial_start_barrier': serial_start_barrier,
        'service_busy_definition': 'service function wall-cycle duration; not total CPU utilization'})
    original_error = None
    try:
        for device in devices:
            if device.command(182, (spi_timing.MODES.get(test.get('_spi_timing_mode'), 0),), timeout=2) != [1]:
                raise ProtocolError('T13 SPI timing policy selection failed')
            if device.command(106, (1,), timeout=2) != [1]:
                raise ProtocolError('T13 precision clock policy failed')
            if device.command(112, (int(test.get('_reverse_serial', False)),), timeout=2) != [1]:
                raise ProtocolError('T13 role selection failed')
            if device.command(116, (int(diagnostic_mode),), timeout=2) != [1]:
                raise ProtocolError('T13 PWM diagnostic policy failed')
            if device.command(185, (edge_diagnostic_mode,), timeout=2) != [1]:
                raise ProtocolError('T13 I2S edge diagnostic policy failed')
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
        if test.get('_spi_timing_mode'):
            spi_timing.observe(devices, test, append, identifier + '/prepared')
        start_devices(devices, test, append, identifier, serial_start_barrier=serial_start_barrier)
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
        cts_pause = during() if during is not None else None
        start = time.monotonic()
        previous = first_lanes
        previous_engines = first_engines
        tick = 0
        while time.monotonic() - start < duration:
            time.sleep(min(2, max(.1, duration - (time.monotonic() - start))))
            continuity.check()
            for device in devices:
                renew_lease(device, test, append, identifier + f'/sample{tick}')
            engines, lanes = snapshots(devices, test, seed, append, identifier + f'/sample{tick}', cts_pause=cts_pause)
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
        end_engines, end_lanes = snapshots(devices, test, seed, append, identifier + '/end', cts_pause=cts_pause)
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
        _, drained = snapshots(devices, test, seed, append, identifier + '/drained', cts_pause=cts_pause)
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
        append(f'T13-{test["harness"]}/{phase}/{member["name"]}/result',
               {'status': 'observation-complete' if diagnostic or test.get('_spi_timing_mode') else 'passed',
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
    parser.add_argument('--harness', choices=('S', 'U'), default='S')
    parser.add_argument('--phase', choices=('wiring', 'preflight', 'soak', 'fault-preflight', 'serial-fault',
                                          'handover-preflight', 'handover', 'spi-timing-diagnostic',
                                          'stream-fault-preflight', 'stream-fault', 'pwm-diagnostic',
                                          'pwm-recovery-preflight', 'pwm-recovery',
                                          'conflict-preflight', 'resource-conflict',
                                          'flow-preflight', 'uart-flow',
                                          'uart-line-preflight', 'uart-line-fault',
                                          'spi-boundary-preflight', 'spi-boundary',
                                          'rx-delay-preflight', 'rx-delay',
                                          'twi-stuck-preflight', 'twi-stuck',
                                           'twis-delay-preflight', 'twis-delay',
                                           'i2s-edge-diagnostic'), default='wiring')
    parser.add_argument('--cases', nargs='+', type=int, default=[])
    parser.add_argument('--fault-mode', type=int, choices=range(1, 6))
    parser.add_argument('--stream-fault-mode', type=int, choices=(1, 2))
    parser.add_argument('--pwm-recovery-mode', type=int, choices=(1, 2))
    parser.add_argument('--conflict-mode', type=int, choices=(1, 2, 3))
    parser.add_argument('--uart-line-mode', choices=('parity', 'break'))
    parser.add_argument('--spi-boundary-mode', choices=('short', 'unready'))
    parser.add_argument('--pwm-diagnostic-route', choices=('led', 'dap'))
    parser.add_argument('--fault-role', type=int, choices=(1, 2), default=1)
    parser.add_argument('--reverse-serial', action='store_true')
    parser.add_argument('--handover-instance', type=int, choices=(0, 20, 21, 22, 30))
    parser.add_argument('--spi-timing-mode', choices=tuple(spi_timing.MODES))
    parser.add_argument('--execute-fixture', action='store_true')
    parser.add_argument('--cmsis-dap-limit-packets', action='store_true')
    parser.add_argument('--diagnostic-repetitions', type=int, default=1)
    parser.add_argument('--i2s-edge-route', choices=('original', 'swapped'))
    args = parser.parse_args(argv)
    uids = validate_pair(args.dut, args.peer)
    family = f't13_{args.harness.lower()}'
    images = [pair.inspect_image(pair.ROOT, args.build_root.resolve(), role, family=family)
              for role in (1, 2)]
    grant_bytes = args.session_grant.read_bytes()
    grant = json.loads(grant_bytes, object_pairs_hook=unique_fields)
    session.validate(grant, images, uids, harness=args.harness)
    available_cases = {test['id']: test for test in catalog.cases()
                       if test['harness'] == args.harness}
    validate_harness_phase(args.harness, args.phase, reverse_serial=args.reverse_serial)
    is_timing = args.phase == 'spi-timing-diagnostic'
    if is_timing:
        if args.spi_timing_mode is None or args.handover_instance not in (20, 21, 22):
            raise ProtocolError('T13 timing diagnostic requires explicit mode and serial20/21/22')
    elif args.spi_timing_mode is not None:
        raise ProtocolError('T13 SPI timing mode requires diagnostic phase')
    is_handover = args.phase in ('handover-preflight', 'handover', 'spi-timing-diagnostic')
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
        raise ProtocolError(f'explicit supported T13 {args.harness} case set required')
    is_fault = args.phase in ('fault-preflight', 'serial-fault')
    is_stream_fault = args.phase in ('stream-fault-preflight', 'stream-fault')
    is_pwm_recovery = args.phase in ('pwm-recovery-preflight', 'pwm-recovery')
    is_conflict = args.phase in ('conflict-preflight', 'resource-conflict')
    is_flow = args.phase in ('flow-preflight', 'uart-flow')
    is_uart_line = args.phase in ('uart-line-preflight', 'uart-line-fault')
    is_spi_boundary = args.phase in ('spi-boundary-preflight', 'spi-boundary')
    is_rx_delay = args.phase in ('rx-delay-preflight', 'rx-delay')
    is_twi_stuck = args.phase in ('twi-stuck-preflight', 'twi-stuck')
    is_twis_delay = args.phase in ('twis-delay-preflight', 'twis-delay')
    is_i2s_edge = args.phase == 'i2s-edge-diagnostic'
    if is_i2s_edge:
        if args.cases != [30] or not 1 <= args.diagnostic_repetitions <= 1000:
            raise ProtocolError('T13 I2S edge diagnostic requires only case 30')
        edge_mode = 2 if args.i2s_edge_route == 'swapped' else 1
        available_cases[30] = i2s_edges.fixture(available_cases[30], edge_mode)
    elif args.diagnostic_repetitions != 1:
        raise ProtocolError('diagnostic repetitions require the I2S edge diagnostic phase')
    elif args.i2s_edge_route is not None:
        raise ProtocolError('alternate I2S data pins require the edge diagnostic phase')
    if is_twis_delay:
        if args.reverse_serial or args.fault_role != 1:
            raise ProtocolError('T13 TWIS delay needs fixed A controller and B target')
        for identifier in args.cases:
            twis_delays.fixture(available_cases[identifier])
    if is_twi_stuck:
        if not args.cases or args.reverse_serial or args.fault_role != 1:
            raise ProtocolError('T13 stuck SDA needs explicit fixed cases with A controller')
        for identifier in args.cases:
            twi_stuck.validate(available_cases[identifier])
    if is_rx_delay:
        for identifier in args.cases:
            rx_delays.fixture(available_cases[identifier], args.fault_role)
    if is_spi_boundary:
        for identifier in args.cases:
            spi_boundaries.validate_selection(available_cases[identifier], args.spi_boundary_mode)
    elif args.spi_boundary_mode is not None:
        raise ProtocolError('SPI boundary mode requires an explicit SPI boundary phase')
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
    evidence = {'schema_version': 1, 'type': f'v04-t13-{args.harness.lower()}-campaign',
        'status': 'preflight', 'harness': args.harness,
        'phase': args.phase, 'case_ids': args.cases, 'core_revision': images[0]['core_revision'],
        'board_revision': images[0]['board_revision'], 'catalog_sha256': session.catalog_hash(),
        'session_grant_sha256': hashlib.sha256(grant_bytes).hexdigest(), 'swd_frequency_hz': 10000000,
        'external_wiring_executed': False, 'results': [],
        'fault_mode': args.fault_mode, 'fault_role': args.fault_role if is_fault or is_stream_fault or is_conflict or is_flow or is_uart_line or is_rx_delay or is_twi_stuck or is_twis_delay else None,
        'conflict_mode': args.conflict_mode,
        'uart_line_mode': args.uart_line_mode,
        'spi_boundary_mode': args.spi_boundary_mode,
        'stream_fault_mode': args.stream_fault_mode,
        'pwm_recovery_mode': args.pwm_recovery_mode,
        'reverse_serial': args.reverse_serial, 'handover_instance': args.handover_instance,
        'spi_timing_mode': args.spi_timing_mode, 'diagnostic_only': is_timing or is_i2s_edge,
        'diagnostic_repetitions': args.diagnostic_repetitions if is_i2s_edge else None,
        'i2s_edge_route': ('swapped' if edge_mode == 2 else 'original') if is_i2s_edge else None,
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
                session.validate(grant, images, uids, harness=args.harness)
                device, flash = pair.boot_exact(stack, ConnectHelper, args.pyocd, uid, image,
                    10000000, cmsis_dap_limit_packets=args.cmsis_dap_limit_packets)
                devices.append(device)
                evidence['devices'][image['role'] - 1]['flash'] = flash
                capability = 511 if is_pwm_recovery else 255
                if session.verify_profile(device, args.harness) & capability != capability:
                    raise ProtocolError('T13 serial/stream/timing capabilities missing')
            continuity = session.Continuity(grant, images, uids, devices, available,
                                            pair.verify_identity, harness=args.harness)
            evidence['external_wiring_executed'] = True
            evidence['wiring_net_ids'] = [net + 1 for net in
                                          (wiring_nets(args.harness) or range(wiring.COUNT))]
            wiring.run_checks(devices, append, continuity.check,
                              nets=wiring_nets(args.harness))
            print(f'T13_{args.harness}_WIRING_PASS', flush=True)
            if is_handover:
                handover.execute(devices, args.handover_instance, continuity, append,
                                 preflight=args.phase != 'handover', timing_mode=args.spi_timing_mode)
            elif is_i2s_edge:
                i2s_edges.execute(devices, available_cases[30], args.diagnostic_repetitions,
                                  continuity, append)
            elif is_twis_delay:
                for identifier in args.cases:
                    twis_delays.execute(devices, available_cases[identifier], continuity, append,
                        preflight=args.phase == 'twis-delay-preflight')
            elif is_twi_stuck:
                for identifier in args.cases:
                    twi_stuck.execute(devices, available_cases[identifier], continuity, append,
                        preflight=args.phase == 'twi-stuck-preflight')
            elif is_rx_delay:
                for identifier in args.cases:
                    rx_delays.execute(devices, available_cases[identifier], args.fault_role,
                        continuity, append, preflight=args.phase == 'rx-delay-preflight')
            elif is_spi_boundary:
                for identifier in args.cases:
                    spi_boundaries.execute(devices, available_cases[identifier], args.spi_boundary_mode,
                        continuity, append, preflight=args.phase == 'spi-boundary-preflight')
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
                append(f'T13-{args.harness}/final-pins/role{device.image["role"]}',
                       {'status': 'observation', 'words': words})
                if words[1:4] != [0, 0, 0] or words[7] != 0:
                    raise ProtocolError('T13 final pin direction/pull/lease not idle')
    print((f'T13_{args.harness}_DIAGNOSTIC_COMPLETED; no normal-soak qualification'
           if args.phase == 'pwm-diagnostic' or is_timing or is_i2s_edge
           else f'T13_{args.harness}_CAMPAIGN_PASS; phase=' + args.phase), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ProtocolError, OSError, ValueError) as error:
        print(f'T13_FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
