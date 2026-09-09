"""! @brief S의 A UART 중계로 B의 정상 debug 해제·System OFF·새 DMA 통신을 검증합니다. """
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import secrets
import struct
import time

import v04_pair as pair
import v04_t13_session as session
import v04_wiring as wiring
from v04_protocol import ProbeLocks, ProtocolError, decode, encode, validate_pair

MAGIC = 0x504F5731
MASK = 0xFFFFFFFF
RESET_PIN, RESET_GPIO, RESET_TIMER = 1, 128, 2048
FAULT_MAGIC = 0x50464531
IDLE_MAGIC = 0x50494431
PINS_MAGIC = 0x50504931
POLL_MAGIC = 0x50504F31
PEER_PIN_RESET_SETTLE_SECONDS = .7


def polling_policy(phase, repeats):
    """! @brief 빠른 polling 비교는 단일 bridge에 한정하며 OFF 반복과 분리합니다. """
    if phase not in ('bridge-debug', 'bridge-fast-poll', 'bridge', 'timer', 'gpio') or repeats not in (1, 100):
        raise ProtocolError('T13 unsupported power phase or repetition count')
    if phase in ('bridge-debug', 'bridge-fast-poll') and repeats != 1:
        raise ProtocolError('T13 bridge diagnostic requires exactly one repetition')
    return 1 if phase == 'bridge-fast-poll' else 0


def connected_probe_uids(connect_helper, peer_debug_detached):
    """! @brief System OFF 대상을 분리한 뒤에는 전체 DAP 열거를 금지합니다. """
    if peer_debug_detached:
        raise ProtocolError('T13 probe enumeration prohibited after peer debug detach')
    return {probe.unique_id.lower() for probe in
            connect_helper.get_all_connected_probes(blocking=False)}


def inspect_polling(words, role, policy):
    """! @brief reset 뒤에도 정확한 polling 정책과 활성 상태를 응답으로 대조합니다. """
    if (role not in (1, 2) or policy not in (0, 1) or not isinstance(words, list) or
            any(type(value) is not int for value in words) or
            words != [POLL_MAGIC, role, policy, policy, 0]):
        raise ProtocolError('T13 power polling policy mismatch')
    return {'polling_policy': policy, 'fast_polling': bool(policy), 'system_off_pass': False}


def fault_region(address, size, symbols):
    """! @brief 진단 symbol이 SRAM 내부이며 기존 mailbox와 겹치지 않는지 확인합니다. """
    if (type(address) is not int or size != 80 or address % 4 or
            not pair.RAM_BEGIN <= address <= pair.RAM_END-80 or any(
                address < start+(64 if name == 'v04_identity' else 128) and start < address+80
                for name, start in symbols.items())):
        raise ProtocolError('T13 power fault symbol outside independent SRAM region')
    return address


def inspect_power_image(repository, build_root, role):
    """! @brief 기존 exact image 검사 뒤 최초 오류용80byte symbol을 읽기 전용으로 추가합니다. """
    from elftools.elf.elffile import ELFFile
    result = pair.inspect_image(repository, build_root, role, family='t13_power_s')
    with result['elf'].open('rb') as stream:
        table = ELFFile(stream).get_section_by_name('.symtab')
        entries = table.get_symbol_by_name('v04_power_fault') if table else []
        if not entries or len(entries) != 1:
            raise ProtocolError('T13 power first-fault symbol missing or ambiguous')
        result['power_fault_address'] = fault_region(int(entries[0]['st_value']),
            int(entries[0]['st_size']), result['symbols'])
        idle = table.get_symbol_by_name('v04_power_idle')
        if not idle or len(idle) != 1:
            raise ProtocolError('T13 power initial idle symbol missing or ambiguous')
        result['power_idle_address'] = fault_region(int(idle[0]['st_value']),
            int(idle[0]['st_size']), result['symbols'])
        if abs(result['power_idle_address']-result['power_fault_address']) < 80:
            raise ProtocolError('T13 power idle and fault snapshots overlap')
        hardware = table.get_symbol_by_name('v04_power_hardware_fault')
        if not hardware or len(hardware) != 1:
            raise ProtocolError('T13 power hardware-fault symbol missing or ambiguous')
        result['power_hardware_fault_address'] = fault_region(int(hardware[0]['st_value']),
            int(hardware[0]['st_size']), result['symbols'])
        if any(abs(result['power_hardware_fault_address']-result[key]) < 80 for key in
               ('power_fault_address', 'power_idle_address')):
            raise ProtocolError('T13 power hardware-fault snapshot overlaps another record')
    return result


def read_power_fault(target, image):
    """! @brief cleanup 접속에서 보존된 첫 오류를 읽으며 잘못된 marker·role을 거부합니다. """
    raw = bytes(target.read_memory_block8(image['power_fault_address'], 80))
    if len(raw) != 80:
        raise ProtocolError('T13 power first-fault snapshot truncated')
    words = list(struct.unpack('<20I', raw))
    if words == [0]*20:
        return {'present': False, 'words': words}
    if words[0] != FAULT_MAGIC or words[1] != image['role'] or words[3] > 5:
        raise ProtocolError('T13 power first-fault marker or role mismatch')
    return {'present': True, 'words': words, 'event_type': words[3], 'error_mask': words[4],
            'observed_during_cleanup_only': True}


def read_power_idle(target, image):
    """! @brief 부팅별 pull-up 설정 전후 원본을 읽으며 실제 OFF 성공으로 확대하지 않습니다. """
    raw = bytes(target.read_memory_block8(image['power_idle_address'], 80))
    if len(raw) != 80:
        raise ProtocolError('T13 power initial idle snapshot truncated')
    words = list(struct.unpack('<20I', raw))
    if words == [0]*20:
        return {'present': False, 'words': words}
    if (words[:2] != [IDLE_MAGIC, image['role']] or words[3:6] != [21, 38, 39] or
            words[8] not in (0, 1) or words[9] & 15 != 12 or
            words[10] not in (0, 1) or words[11] not in (0, 1) or words[17:] != [1, 0, 0]):
        raise ProtocolError('T13 power initial idle marker/role/pin/pull mismatch')
    return {'present': True, 'words': words, 'rx_before': words[8], 'rx_after': words[10],
            'internal_rx_pull_up': True, 'system_off_pass': False}


def read_power_hardware_fault(target, image):
    """! @brief 큐 초과와 별도로 보존한 저위 네 비트의 최초 UART 오류를 읽습니다. """
    result = read_power_fault(target, {**image, 'power_fault_address':
                                     image['power_hardware_fault_address']})
    if result['present'] and (result['event_type'] != 5 or not 0 < result['error_mask'] <= 15):
        raise ProtocolError('T13 power hardware-fault record has non-hardware error mask')
    return result


def observe_pins(device, append, label):
    """! @brief 기존 SWD 연결에서 유휴 신호·GPIO·UART 상태를 읽고 성공 판정 없이 보존합니다. """
    words = device.command(134, (1,))
    if (not isinstance(words, list) or len(words) != 20 or words[:2] !=
            [PINS_MAGIC, device.image['role']] or any(type(value) is not int or
            not 0 <= value <= MASK for value in words) or
            any(words[index] not in (0, 1) for index in (11, 12, 13))):
        raise ProtocolError('T13 power live-pin snapshot malformed or wrong role')
    append(label, {'status': 'diagnostic', 'words': words,
        'tx_level': (words[4] >> 6) & 1, 'rx_level': (words[4] >> 7) & 1,
        'system_off_pass': False})
    return words


def prepare_uart_pair(devices, policy, append):
    """! @brief 양쪽 핀 준비 뒤 A의 UART를 켜고 peer reset 전에 실제 수신 준비를 대조합니다. """
    for device in devices:
        if device.command(130, (MAGIC, 1) if policy else (MAGIC,), timeout=2) != [1]:
            raise ProtocolError('T13 power UART/pin preparation failed')
        append(f'polling/role{device.image["role"]}/before-reset', {'status': 'diagnostic',
            **inspect_polling(device.command(134, (2,)), device.image['role'], policy)})
    a = devices[0]
    if a.image['role'] != 1 or a.command(131, timeout=2) != [1]:
        raise ProtocolError('T13 A receive start failed before peer reset')
    words = observe_pins(a, append, 'pins/controller-after-rx-start')
    if words[7:10] != [8, 38, 39] or words[11:17] != [1, 1, 0, 0, 0, 0]:
        raise ProtocolError('T13 A UART enable/RX/pins/idle proof missing before peer reset')


def inspect(words, *, boots, mode, round_number, seed):
    """! @brief debug wake·일반 reset·stale retention을 실제 System OFF 성공과 구분합니다. """
    if (not isinstance(words, list) or len(words) != 20 or
            any(type(value) is not int or not 0 <= value <= MASK for value in words) or
            words[:3] != [MAGIC, 2, 1] or words[4] != 0 or words[5] != boots or
            words[6] != (RESET_PIN if mode == 0 else RESET_TIMER if mode == 1 else RESET_GPIO) or
            words[7:10] != [0, mode, round_number] or words[10:13] != [0, 0, 0] or
            words[16:19] != [int(mode != 0), 1, seed] or words[13] & 0x10000 == 0):
        raise ProtocolError(f'T13 power normal-mode/reset/retention mismatch: {words}')
    return {'boots': boots, 'mode': mode, 'round': round_number, 'seed': seed,
            'reset_cause': words[6], 'debug_requests': words[10:13],
            'dma_release_proven': bool(words[16]), 'xo_stat': words[13], 'uptime_ms': words[19]}


def verify_source(words, source):
    """! @brief B SWD를 다시 열지 않고 중계 응답의 실행 source를 대조합니다. """
    expected = [*struct.unpack('<10I', source.encode('ascii')), MAGIC]
    if words != expected:
        raise ProtocolError('T13 power peer source mismatch after reset')


def inspect_debug_bridge(words):
    """! @brief debug를 유지한 UART 진단을 정상 mode·절전 복구와 구분합니다. """
    if (not isinstance(words, list) or len(words) != 20 or
            any(type(value) is not int or not 0 <= value <= MASK for value in words) or
            words[:3] != [MAGIC, 2, 1] or words[4:6] != [0, 0] or
            words[7:13] != [0, 0, 0, 1, 1, 1] or words[16:19] != [0, 0, 0] or
            words[14] < 1 or words[15] < 2 or words[13] & 0x10000 == 0):
        raise ProtocolError('T13 debug-held UART bridge state mismatch')
    return {'normal_mode_proven': False, 'system_off_pass': False,
            'debug_requests': words[10:13], 'tx_frames': words[14], 'rx_frames': words[15]}


class Relay:
    """! @brief B의 nonce/sequence를 유지하며 A의 두 page mailbox만 사용하는 중계입니다. """
    def __init__(self, controller, nonce, sequence, check, append):
        self.controller, self.nonce, self.sequence = controller, nonce, sequence
        self.check, self.append = check, append
        self.poisoned = False

    def send(self, packet):
        words = struct.unpack('<32I', packet)
        for page in (0, 1):
            if self.controller.command(132, (page, *words[page*16:(page+1)*16]), timeout=2) != [1]:
                raise ProtocolError('T13 relay staging failed')
        if self.controller.command(133, timeout=2) != [1]:
            raise ProtocolError('T13 relay DMA submission failed')

    def receive(self):
        first = self.controller.command(135, (0,), timeout=2)
        if not first:
            return None
        second = self.controller.command(135, (1,), timeout=2)
        if len(first) != 16 or len(second) != 16:
            raise ProtocolError('T13 relay response page truncated')
        return struct.pack('<32I', *(first + second))

    def command(self, opcode, values=(), timeout=2):
        if self.poisoned:
            raise ProtocolError('T13 relay sequence uncertain; automatic retry forbidden')
        self.check()
        self.sequence += 1
        packet = encode(self.nonce, self.sequence, 2, opcode, values)
        try:
            self.send(packet)
            until = time.monotonic() + timeout
            while time.monotonic() < until:
                raw = self.receive()
                if raw is not None:
                    status, result = decode(raw, self.nonce, self.sequence, 2, opcode)
                    self.append(f'relay/seq{self.sequence}', {'status': 'observation',
                        'request_hex': packet.hex(), 'response_hex': raw.hex(), 'words': result,
                        'firmware_status': status})
                    if status != 0:
                        raise ProtocolError(f'T13 relay firmware status {status} opcode {opcode}')
                    return result
                time.sleep(.01)
            raise ProtocolError(f'T13 relay response timeout opcode {opcode}')
        except BaseException:
            self.poisoned = True
            raise

    def silence_probe(self):
        """! @brief 다른 nonce의 명령으로 무응답을 관측하며 정상 B sequence를 소비하지 않습니다. """
        self.check()
        foreign = secrets.token_bytes(16)
        while foreign == self.nonce:
            foreign = secrets.token_bytes(16)
        self.send(encode(foreign, 1, 2, 134, ()))
        started = time.monotonic()
        polls = 0
        while time.monotonic() - started < .3:
            if self.receive() is not None:
                self.poisoned = True
                raise ProtocolError('T13 B replied during the required System OFF silence interval')
            polls += 1
            time.sleep(.02)
        self.append('off/silence', {'status': 'observation', 'duration_seconds': time.monotonic()-started,
                    'polls': polls, 'nonce_sha256': hashlib.sha256(foreign).hexdigest(),
                    'b_swd_accessed': False})


def detach_and_pin_reset(device, append):
    """! @brief pyOCD 정상 disconnect 후 CMSIS-DAP nRESET만 사용하며 B DP/AP를 다시 열지 않습니다. """
    connection = device.target.session
    probe = connection.probe
    connection.options['resume_on_disconnect'] = True
    connection.close()
    append('debug/detached', {'status': 'observation', 'resume_on_disconnect': True,
                            'normal_mode_proven': False})
    probe.open()
    try:
        probe.assert_reset(True)
        time.sleep(.02)
        probe.assert_reset(False)
        if probe.is_reset_asserted():
            raise ProtocolError('T13 B nRESET remained asserted')
    finally:
        # @brief 예외에서도 nRESET 해제를 시도하고 SWD connect 없이 probe를 닫습니다.
        probe.assert_reset(False)
        probe.close()
    append('debug/pin-reset', {'status': 'observation', 'pin_only': True, 'hold_ms': 20,
                              'b_dp_ap_access_after_disconnect': False})


def pin_snapshot(target):
    """! @brief 제어 응답 손실 시에도 직접 읽은17개 GPIO와 UART ENABLE을 보존합니다. """
    groups = ((0x5010A000, (0, 1, 2, 3)), (0x500D8200, (4, 5, 6, 7, 10, 14)),
              (0x50050400, (0, 1, 2, 3, 4, 5, 6)))
    return [target.read32(base + 0x80 + pin*4) for base, pins in groups for pin in pins]


def execute(args, images, grant, uids, append):
    policy = polling_policy(args.phase, args.repeats)
    from pyocd.core.helpers import ConnectHelper
    devices, relay = [], None
    detached = False
    original_error = None
    cleanup_proven = False
    with ProbeLocks(uids), ExitStack() as stack:
        def available():
            return connected_probe_uids(ConnectHelper, detached)
        if not set(uids).issubset(available()):
            raise ProtocolError('both current exact probes required')
        try:
            for uid, image in zip(uids, images):
                session.validate(grant, images, uids)
                device, flash = pair.boot_exact(stack, ConnectHelper, args.pyocd, uid, image,
                    10000000, cmsis_dap_limit_packets=True, flash_connect_mode='under-reset')
                devices.append(device)
                append(f'flash/role{image["role"]}', {'status': 'observation', 'flash': flash})
                session.verify_profile(device)
                if device.target.read32(image['symbols']['v04_identity'] + 56) != MAGIC:
                    raise ProtocolError('separate power image capability missing')
            continuity = session.Continuity(grant, images, uids, devices, available, pair.verify_identity)
            wiring.run_checks(devices, append, continuity.check)
            prepare_uart_pair(devices, policy, append)
            a, b = devices
            append('debug/before', {'status': 'observation', 'words': b.command(134)})
            observe_pins(a, append, 'pins/controller-before-peer-reset')
            observe_pins(b, append, 'pins/peer-before-reset')
            if args.phase == 'bridge-debug':
                if b.command(131, timeout=2) != [1]:
                    raise ProtocolError('T13 debug-held B receive start failed')
            else:
                if b.command(137, timeout=2) != [1]:
                    raise ProtocolError('T13 explicit expected pin reset could not be armed')
                detached = True
                detach_and_pin_reset(b, append)
                time.sleep(PEER_PIN_RESET_SETTLE_SECONDS)
                observe_pins(a, append, 'pins/controller-after-peer-reset')

            def a_only_check():
                session.validate(grant, images, uids)
                raw = bytes(a.target.read_memory_block8(images[0]['symbols']['v04_identity'], 64))
                pair.verify_identity(raw, 1, images[0]['core_revision'])
                if struct.unpack('<I', raw[56:60])[0] != MAGIC:
                    raise ProtocolError('T13 controller power image changed')

            relay = Relay(a, b.nonce, b.sequence, a_only_check, append)
            verify_source(relay.command(131), images[1]['core_revision'])
            append('polling/role2/relayed', {'status': 'diagnostic',
                **inspect_polling(relay.command(134, (2,)), 2, policy)})
            if args.phase == 'bridge-debug':
                append('debug-held/result', {'status': 'diagnostic',
                    **inspect_debug_bridge(relay.command(134))})
            else:
                inspect(relay.command(134), boots=1, mode=0, round_number=0, seed=0)
                append('debug/result', {'status': 'diagnostic' if policy else 'passed',
                    'normal_mode_proven': True, 'b_swd_accessed_since_detach': False,
                    'fast_polling_diagnostic': bool(policy), 'system_off_pass': False})

            def echo(seed, label):
                challenge = [secrets.randbits(32) for _ in range(20)]
                observed = relay.command(137, challenge)
                expected = [word ^ seed ^ ((0x9E3779B9*(index+1)) & MASK)
                            for index, word in enumerate(challenge)]
                if observed != expected:
                    raise ProtocolError('T13 fresh UART DMA challenge mismatch')
                append(label, {'status': 'passed', 'challenge': challenge, 'response': observed,
                               'seed': seed, 'frame_bytes_each_direction': 128})

            echo(0, 'bridge/fresh-dma')
            mode = {'bridge-debug': 0, 'bridge-fast-poll': 0, 'bridge': 0, 'timer': 1, 'gpio': 2}[args.phase]
            if mode:
                for repeat in range(1, args.repeats+1):
                    a_only_check()
                    seed = secrets.randbits(32)
                    if mode == 2 and a.command(138, (2000,), timeout=2) != [1]:
                        raise ProtocolError('T13 fixed P1.14 open-drain wake schedule failed')
                    started = time.monotonic()
                    if relay.command(136, (mode, repeat, seed)) != [1]:
                        raise ProtocolError('T13 peer refused System OFF')
                    time.sleep(.35)
                    relay.silence_probe()
                    remaining = 3.0 - (time.monotonic()-started)
                    if remaining > 0:
                        time.sleep(remaining)
                    verify_source(relay.command(131), images[1]['core_revision'])
                    words = relay.command(134)
                    result = inspect(words, boots=repeat+1, mode=mode, round_number=repeat, seed=seed)
                    reset_after = time.monotonic() - started - words[19]/1000
                    if not 1.5 <= reset_after <= 3.3:
                        raise ProtocolError(f'T13 reset did not occur in the timed wake window: {reset_after}')
                    echo(seed, f'cycle{repeat:03}/fresh-dma')
                    append(f'cycle{repeat:03}/result', {'status': 'passed', **result,
                        'reset_after_submit_seconds': reset_after, 'b_swd_accessed': False,
                        'planned_100_recovery_pass': args.repeats == 100})
                    print(f'T13_POWER_PROGRESS phase={args.phase} completed={repeat}/{args.repeats}', flush=True)
        except BaseException as error:
            original_error = error
            append('failure', {'status': 'failed', 'error': f'{type(error).__name__}: {error}'})
            if devices and not devices[0].poisoned:
                try:
                    observe_pins(devices[0], append, 'pins/controller-at-failure')
                except BaseException as diagnostic_error:
                    append('pins/controller-at-failure', {'status': 'unproven',
                        'error': str(diagnostic_error)})
        finally:
            for device in reversed(devices):
                try:
                    if device is devices[-1] and (detached or relay is not None):
                        if relay is not None and not relay.poisoned:
                            append('cleanup/b-reply', {'status': 'observation', 'words': relay.command(139)})
                    elif not device.poisoned:
                        append(f'cleanup/role{device.image["role"]}/reply',
                               {'status': 'observation', 'words': device.command(139, timeout=2)})
                except BaseException as error:
                    append('cleanup/reply-failure', {'status': 'unproven', 'error': str(error)})
            # @brief 통신 실패 후에는 고정 lease의 자동 STOP을 기다리고 읽기만으로 자원을 확인합니다.
            time.sleep(10.5 if original_error else .4)
            outcomes = []
            for index, device in enumerate(devices):
                try:
                    if detached and index == 1:
                        connection = ConnectHelper.session_with_chosen_probe(unique_id=uids[1],
                            target_override='nrf54l', frequency=10000000, blocking=False, no_config=True,
                            options={'auto_unlock': False, 'connect_mode': 'attach',
                                     'resume_on_disconnect': False, 'cmsis_dap.limit_packets': True})
                        if connection is None:
                            raise ProtocolError('cleanup probe missing')
                        stack.enter_context(connection)
                        target = connection.target
                        # @brief 실패한 OFF를 debug로 깨울 수 있는 cleanup은 성공 시험에 포함하지 않습니다.
                        time.sleep(.3)
                    else:
                        target = device.target
                    raw_identity = bytes(target.read_memory_block8(device.image['symbols']['v04_identity'], 64))
                    pair.verify_identity(raw_identity, index+1, device.image['core_revision'])
                    for name, reader in (('first-uart-fault', read_power_fault),
                                         ('first-hardware-uart-fault', read_power_hardware_fault),
                                         ('initial-uart-idle', read_power_idle)):
                        try:
                            append(f'cleanup/role{index+1}/{name}',
                                {'status': 'diagnostic', **reader(target, device.image)})
                        except BaseException as error:
                            append(f'cleanup/role{index+1}/{name}',
                                {'status': 'unproven', 'error': str(error)})
                    stamp = struct.unpack('<I', raw_identity[60:64])[0]
                    pins = pin_snapshot(target)
                    stopped = stamp & 0xFFFF000F == 0x53540004 and all(value & 0xD == 0 for value in pins)
                    outcomes.append({'role': index+1, 'stopped': stopped, 'stamp': stamp, 'pin_cnf': pins})
                except BaseException as error:
                    outcomes.append({'role': index+1, 'stopped': False, 'error': str(error)})
            cleanup_proven = len(outcomes) == 2 and all(row['stopped'] for row in outcomes)
            append('cleanup/result', {'status': 'cleanup', 'outcomes': outcomes,
                                     'cleanup_proven': cleanup_proven, 'b_swd_reopened_for_cleanup': detached})
        if original_error is not None:
            raise original_error
        if not cleanup_proven:
            raise ProtocolError('T13 power pair cleanup unproven')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dut', required=True)
    parser.add_argument('--peer', required=True)
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--pyocd', type=Path, required=True)
    parser.add_argument('--session-grant', type=Path, required=True)
    parser.add_argument('--phase', choices=('bridge-debug', 'bridge-fast-poll', 'bridge', 'timer', 'gpio'), required=True)
    parser.add_argument('--repeats', type=int, choices=(1, 100), default=1)
    parser.add_argument('--execute-fixture', action='store_true')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args(argv)
    policy = polling_policy(args.phase, args.repeats)
    uids = validate_pair(args.dut, args.peer)
    images = [inspect_power_image(pair.ROOT, args.build_root, role) for role in (1, 2)]
    grant = json.loads(args.session_grant.read_text(encoding='utf-8'))
    session.validate(grant, images, uids)
    evidence = {'schema_version': 1, 'type': 'v04-t13-s-power', 'phase': args.phase,
        'repeats': args.repeats, 'core_revision': images[0]['core_revision'],
        'board_revision': images[0]['board_revision'], 'swd_frequency_hz': 10000000,
        'scope': 'UART21 DMA quiesce / peer controlled reset and wake; not full T13',
        'diagnostic_only': args.phase in ('bridge-debug', 'bridge-fast-poll'),
        'polling_policy': policy,
        'system_off_requested': args.phase in ('timer', 'gpio'),
        'results': [], 'session_grant_sha256': hashlib.sha256(args.session_grant.read_bytes()).hexdigest(),
        'devices': [{'role': image['role'], 'uid_sha256': hashlib.sha256(uid.encode()).hexdigest(),
                     'image_sha256': image['sha256'], 'elf_sha256': image['elf_sha256']}
                    for uid, image in zip(uids, images)], 'external_wiring_executed': False}
    if not args.execute_fixture:
        print(json.dumps(evidence, indent=2))
        return 0
    if args.evidence is None:
        raise ProtocolError('exclusive evidence path required')
    with pair.evidence_session(args.evidence, evidence) as journal:
        def append(identifier, data):
            row = {'id': identifier, **data}
            evidence['results'].append(row)
            journal.write(json.dumps(row)+'\n')
            journal.flush()
        evidence['external_wiring_executed'] = True
        execute(args, images, grant, uids, append)
    print(f'T13_POWER_PASS phase={args.phase} repeats={args.repeats}; full_T13_completed=0')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
