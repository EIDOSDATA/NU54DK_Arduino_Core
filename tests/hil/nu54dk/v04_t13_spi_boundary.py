"""! @brief 짧은 SPIS DMA·미준비 transaction을 전체 RAM과 실제 event로 구분합니다. """
import secrets
import time

from v04_protocol import ProtocolError
import v04_t13_oracle as oracle
from v04_t13_flow import physical

MASK = oracle.MASK


def validate_selection(test, mode):
    if (mode not in ('short', 'unready') or test['harness'] != 'S' or test.get('_reverse_serial') or
            len(test['serial_links']) != 1 or any(test[key] for key in
                ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s'))):
        raise ProtocolError('T13 unsupported SPI boundary case')
    link = test['serial_links'][0]
    if (link['rate'] != 8000000 or link['buffer_bytes'] != 1024 or
            link['a']['kind'] != 'spim' or link['b']['kind'] != 'spis' or
            test['name'] != 'spim'+str(link['a']['instance']) or
            any(endpoint['instance'] not in (0, 20, 21, 22, 30) or
                set(endpoint['pins']) != {'sck', 'mosi', 'miso', 'csn'} for endpoint in (link['a'], link['b']))):
        raise ProtocolError('T13 SPI boundary requires a fixed8MHz1024byte S pair')


def inspect(raw, before, after, baseline, tx, rx, test, role, mode, seed, lane):
    """! @brief ORC/DEF를 정상 frame으로 인정하지 않고 실제 길이·경계·CS·다음 복구를 분리합니다. """
    validate_selection(test, mode)
    endpoint = test['serial_links'][0]['a' if role == 1 else 'b']
    policy = (1 if role == 1 else 2) if mode == 'short' else (3 if role == 1 else 4)
    terminal = policy != 4
    arrays = (raw, before, after, baseline, lane)
    if (role not in (1, 2) or any(not isinstance(words, list) or len(words) != 20 or
            any(type(word) is not int or not 0 <= word <= MASK for word in words) for words in arrays) or
            raw[:5] != [policy, endpoint['instance'], 1, 1 if terminal else 2, int(terminal)] or
            raw[9:11] != [1, 1] or raw[18:20] != [1000000, 1] or
            baseline[4:] != [1024]+[0]*15 or not all(baseline[2:4]) or
            lane[:3] != ([82, 0, 0] if terminal else [0, 0, 1]) or lane[19] != 20):
        raise ProtocolError(f'T13 SPI boundary event/STOP/guard proof missing: {raw}; lane={lane}')
    for meta in (before, after):
        pins = [physical(endpoint['pins'][name]) for name in ('sck', 'mosi', 'miso', 'csn')]
        if (meta[:3] != [policy, 2 if role == 1 else 3, endpoint['instance']] or
                meta[3] not in ((0, 7) if role == 1 else (2,)) or meta[4] != 255 or
                meta[10:14] != pins or meta[17] != 1 or meta[19] != 1000000):
            raise ProtocolError('T13 SPI boundary hardware configuration changed')
    if after[16] != 1:
        raise ProtocolError('T13 SPI CS was not HIGH after the measured transaction')
    if raw[13:15] != after[14:16]:
        raise ProtocolError('T13 SPI terminal register snapshots disagree')
    if terminal:
        amount = 1024 if role == 1 else 512
        if (raw[5:9] != [0, amount, amount, 3] or raw[11:13] != [amount, amount] or
                not 0 < ((raw[15]-raw[16]) & MASK) <= 2000000 or
                after[6:10] != [amount, amount, baseline[2], baseline[3]]):
            raise ProtocolError('T13 SPI terminal amount/pointer differs from the actual DMA')
        if role == 1:
            if not 0 < ((raw[17]-raw[16]) & MASK) <= ((raw[15]-raw[16]) & MASK):
                raise ProtocolError('T13 SPI controller submission/event order mismatch')
        elif raw[17] != 0 or after[14:16] != [3, 1]:
            raise ProtocolError('T13 short SPIS needs OVERREAD/OVERFLOW and CPU semaphore return')
    else:
        if (raw[5:9] != [MASK, 0, 0, 0] or raw[11:13] != baseline[:2] or
                raw[15] or raw[17] or before[15] != 1 or after[15] != 1 or
                after[5] != 255 or before[6:16] != after[6:16]):
            raise ProtocolError('T13 unready SPIS did not keep its initial DMA/semaphore state')
    if not isinstance(tx, bytes) or not isinstance(rx, bytes) or len(tx) != 1024 or len(rx) != 1024:
        raise ProtocolError('T13 complete1024byte TX/RX memory evidence required')
    expected_tx = bytes(oracle.pattern(oracle.lane_seed(seed, 0, role), index) for index in range(1024))
    expected_peer = bytes(oracle.pattern(oracle.lane_seed(seed, 0, 3-role), index) for index in range(1024))
    if tx != expected_tx:
        raise ProtocolError('T13 source TX RAM changed')
    expected_rx = (expected_peer[:512]+b'\xff'*512 if role == 1 else expected_peer[:512]+b'\xcc'*512) if mode == 'short' else bytes([255 if role == 1 else 204])*1024
    if rx != expected_rx:
        mismatch = next(index for index in range(1024) if rx[index] != expected_rx[index])
        raise ProtocolError(f'T13 SPI boundary full RAM mismatch at byte{mismatch}')
    return {'role': role, 'mode': mode, 'instance': endpoint['instance'],
        'api_tx_length': raw[6], 'api_rx_length': raw[7], 'hardware_tx_amount_raw': raw[11],
        'hardware_rx_amount_raw': raw[12], 'rx_amount_is_previous': not terminal,
        'status_raw': raw[13], 'ram_bytes_compared': 2048, 'normal_soak_pass': False}


def execute(devices, test, mode, continuity, append, *, preflight):
    """! @brief 한 번의 비정상 CS frame과 STOP 후 새 정상 payload를 독립적으로 판정합니다. """
    import v04_t13_run as runner
    validate_selection(test, mode)
    controller = next(device for device in devices if device.image['role'] == 1)
    peer = next(device for device in devices if device.image['role'] == 2)
    repeats = 1 if preflight else 100
    for repeat in range(1, repeats+1):
        seed = secrets.randbits(32)
        label = f'T13-S/spi-boundary/{test["name"]}/{mode}/repeat{repeat:03}'
        append(label+'/input', {'status': 'input', 'test': test, 'seed': seed, 'mode': mode})
        runner.execute_group(devices, {'test': test, 'members': [test]}, .25, continuity,
            lambda name, row: append(label+'/baseline/'+name, row), preflight=True, seed=seed)
        original_error = None
        observed = {}
        try:
            continuity.check()
            for device in devices:
                role = device.image['role']
                policy = role if mode == 'short' else role+2
                if (device.command(150, (policy,), timeout=2) != [1] or
                        device.command(106, (1,), timeout=2) != [1] or device.command(112, (0,), timeout=2) != [1]):
                    raise ProtocolError('T13 SPI boundary policy failed before PREPARE')
            for device in (peer, controller):
                if device.command(97, (test['id'], seed, 0x53414645), timeout=3) != [1]:
                    raise ProtocolError('T13 SPI boundary PREPARE failed')
            runner.prepared_bus_pins(devices, test, append, label+'/prepared')
            for device in devices:
                clock = device.command(107, (0,), timeout=2)
                append(label+f'/clock/role{device.image["role"]}', {'status': 'observation', 'words': clock})
                if clock[:2] != [1, 1] or clock[2] == 0 or device.command(151, timeout=2) != [1]:
                    raise ProtocolError('T13 SPI boundary clock or ARM failed')
            for device in (peer, controller):
                if device.command(98, timeout=2) != [1]:
                    raise ProtocolError('T13 SPI boundary START failed')
            deadline = time.monotonic()+2
            poll = 0
            while True:
                time.sleep(.025)
                continuity.check()
                words = controller.command(152, (0,), timeout=2)
                append(label+f'/poll{poll}', {'status': 'observation', 'words': words})
                poll += 1
                if (len(words) == 20 and words[4] == 1) or time.monotonic() >= deadline:
                    break
        except BaseException as error:
            original_error = error
            append(label+'/failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
        finally:
            for device in devices:
                role = device.image['role']
                observed[role] = {}
                try:
                    engine = device.command(99, timeout=2)
                    append(label+f'/final/role{role}/engine', {'status': 'observation', 'words': engine})
                    if len(engine) != 16 or engine[0] != test['id'] or engine[5] != 0:
                        raise ProtocolError('T13 SPI boundary reset/case drift/lease expiry')
                    observed[role]['lane'] = device.command(100, (0,), timeout=2)
                    append(label+f'/final/role{role}/lane', {'status': 'observation', 'words': observed[role]['lane']})
                except BaseException as error:
                    original_error = original_error or error
                    append(label+f'/final/role{role}/failure', {'status': 'unproven', 'error': str(error)})
            stopped = runner.stop_pair(devices, append, label+'/cleanup')
            pins_idle = runner.idle_pins(devices, append, label+'/pins')
        if not stopped or not pins_idle:
            raise original_error or ProtocolError('T13 SPI boundary STOP/resource return unproven')
        for device in devices:
            role = device.image['role']
            try:
                for page in range(4):
                    words = device.command(152, (page,), timeout=2)
                    observed[role][page] = words
                    append(label+f'/stopped/role{role}/meta{page}', {'status': 'observation', 'words': words})
                for direction, name in ((0, 'tx'), (1, 'rx')):
                    data = bytearray()
                    for page in range(16):
                        continuity.check()
                        words = device.command(153, (direction, page), timeout=2)
                        append(label+f'/stopped/role{role}/{name}{page}', {'status': 'observation', 'words': words})
                        if len(words) != 16 or any(type(word) is not int or not 0 <= word <= MASK for word in words):
                            raise ProtocolError('T13 incomplete SPI memory page')
                        data.extend(b''.join(word.to_bytes(4, 'little') for word in words))
                    observed[role][name] = bytes(data)
            except BaseException as error:
                original_error = original_error or error
                append(label+f'/stopped/role{role}/failure', {'status': 'unproven', 'error': str(error)})
        if original_error is not None:
            raise original_error
        for role, row in observed.items():
            measured = inspect(*(row[page] for page in range(4)), row['tx'], row['rx'], test, role, mode, seed, row['lane'])
            append(label+f'/observed/role{role}', {'status': 'expected-boundary-observed', **measured})
        for device in devices:
            if device.command(150, (0,), timeout=2) != [1]:
                raise ProtocolError('T13 SPI boundary policy not cleared')
        restart_seed = seed ^ 0x9E3779B9
        runner.execute_group(devices, {'test': test, 'members': [test]}, 1, continuity,
            lambda name, row: append(label+'/restart/'+name, row), preflight=True, seed=restart_seed)
        append(label+'/result', {'status': 'passed', 'fault_seed': seed, 'restart_seed': restart_seed,
            'planned_spi_boundary_pass': not preflight, 'normal_soak_pass': False})
        print(f'T13_SPI_BOUNDARY_PROGRESS case={test["name"]} mode={mode} completed={repeat}/{repeats}', flush=True)
