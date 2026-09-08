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


def inspect(words, *, boots, mode, round_number, seed):
    """! @brief debug wake·일반 reset·stale retention을 실제 System OFF 성공과 구분합니다. """
    if (not isinstance(words, list) or len(words) != 20 or
            any(type(value) is not int or not 0 <= value <= MASK for value in words) or
            words[:3] != [MAGIC, 2, 1] or words[4] != 0 or words[5] != boots or
            words[6] != (RESET_PIN if mode == 0 else RESET_TIMER if mode == 1 else RESET_GPIO) or
            words[7:10] != [0, mode, round_number] or words[10:13] != [0, 0, 0] or
            words[16:19] != [int(mode != 0), 1, seed]):
        raise ProtocolError(f'T13 power normal-mode/reset/retention mismatch: {words}')
    return {'boots': boots, 'mode': mode, 'round': round_number, 'seed': seed,
            'reset_cause': words[6], 'debug_requests': words[10:13],
            'dma_release_proven': bool(words[16]), 'uptime_ms': words[19]}


def verify_source(words, source):
    """! @brief B SWD를 다시 열지 않고 중계 응답의 실행 source를 대조합니다. """
    expected = [*struct.unpack('<10I', source.encode('ascii')), MAGIC]
    if words != expected:
        raise ProtocolError('T13 power peer source mismatch after reset')


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
    from pyocd.core.helpers import ConnectHelper
    devices, relay = [], None
    detached = False
    original_error = None
    cleanup_proven = False
    with ProbeLocks(uids), ExitStack() as stack:
        def available():
            return {probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)}
        if not set(uids).issubset(available()):
            raise ProtocolError('both current exact probes required')
        try:
            for uid, image in zip(uids, images):
                session.validate(grant, images, uids)
                device, flash = pair.boot_exact(stack, ConnectHelper, args.pyocd, uid, image,
                    10000000, cmsis_dap_limit_packets=True)
                devices.append(device)
                append(f'flash/role{image["role"]}', {'status': 'observation', 'flash': flash})
                session.verify_profile(device)
                if device.target.read32(image['symbols']['v04_identity'] + 56) != MAGIC:
                    raise ProtocolError('separate power image capability missing')
            continuity = session.Continuity(grant, images, uids, devices, available, pair.verify_identity)
            wiring.run_checks(devices, append, continuity.check)
            for device in devices:
                if device.command(130, (MAGIC,), timeout=2) != [1]:
                    raise ProtocolError('T13 power UART/pin preparation failed')
            a, b = devices
            append('debug/before', {'status': 'observation', 'words': b.command(134)})
            if b.command(137, timeout=2) != [1]:
                raise ProtocolError('T13 explicit expected pin reset could not be armed')
            detached = True
            detach_and_pin_reset(b, append)
            time.sleep(.3)

            def a_only_check():
                session.validate(grant, images, uids)
                if not set(uids).issubset(available()):
                    raise ProtocolError('T13 exact USB probe disconnected')
                raw = bytes(a.target.read_memory_block8(images[0]['symbols']['v04_identity'], 64))
                pair.verify_identity(raw, 1, images[0]['core_revision'])
                if struct.unpack('<I', raw[56:60])[0] != MAGIC:
                    raise ProtocolError('T13 controller power image changed')

            if a.command(131, timeout=2) != [1]:
                raise ProtocolError('T13 A receive start failed')
            relay = Relay(a, b.nonce, b.sequence, a_only_check, append)
            verify_source(relay.command(131), images[1]['core_revision'])
            inspect(relay.command(134), boots=1, mode=0, round_number=0, seed=0)
            append('debug/result', {'status': 'passed', 'normal_mode_proven': True,
                                   'b_swd_accessed_since_detach': False})

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
            mode = {'bridge': 0, 'timer': 1, 'gpio': 2}[args.phase]
            if mode:
                for repeat in range(1, args.repeats+1):
                    a_only_check()
                    if grant['expires_at_unix'] - time.time() < 20:
                        raise ProtocolError('T13 insufficient current session time for another wake cycle')
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
        finally:
            for device in reversed(devices):
                try:
                    if detached and device is devices[-1]:
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
                    try:
                        append(f'cleanup/role{index+1}/first-uart-fault',
                            {'status': 'diagnostic', **read_power_fault(target, device.image)})
                    except BaseException as error:
                        append(f'cleanup/role{index+1}/first-uart-fault',
                            {'status': 'unproven', 'error': str(error)})
                    stamp = struct.unpack('<I', raw_identity[60:64])[0]
                    pins = pin_snapshot(target)
                    stopped = stamp & 0xFFFF0007 == 0x53540004 and all(value & 0xD == 0 for value in pins)
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
    parser.add_argument('--phase', choices=('bridge', 'timer', 'gpio'), required=True)
    parser.add_argument('--repeats', type=int, choices=(1, 100), default=1)
    parser.add_argument('--execute-fixture', action='store_true')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args(argv)
    uids = validate_pair(args.dut, args.peer)
    images = [inspect_power_image(pair.ROOT, args.build_root, role) for role in (1, 2)]
    grant = json.loads(args.session_grant.read_text(encoding='utf-8'))
    session.validate(grant, images, uids)
    evidence = {'schema_version': 1, 'type': 'v04-t13-s-power', 'phase': args.phase,
        'repeats': args.repeats, 'core_revision': images[0]['core_revision'],
        'board_revision': images[0]['board_revision'], 'swd_frequency_hz': 10000000,
        'scope': 'UART21 DMA quiesce / peer controlled reset and wake; not full T13',
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
