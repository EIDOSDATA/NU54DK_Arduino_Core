"""! @brief T13의 결선 권한과 실제 완료·peer 데이터 판정에서 거짓 PASS를 거부합니다. """
import copy
import hashlib
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_oracle as oracle
import v04_t13_plan as plan
import v04_t13_session as session
import v04_t13_run as runner
from v04_protocol import ProtocolError


class T13RuntimeTests(unittest.TestCase):
    def test_i2s_firmware_error_is_not_masked_by_lease_rejection(self):
        """! @brief 실제 I2S 오류 뒤 lease 거부가 와도 원인과 raw stream을 먼저 보고합니다. """
        test = next(row for row in cases.cases() if row['id'] == 30)
        device = mock.Mock(image={'role': 1})
        device.command.side_effect = lambda opcode, args=(), timeout=2: (
            [0] if opcode == 103 else [2, 0, 6, 134217] + [0] * 16)
        records = []
        with self.assertRaisesRegex(ProtocolError, 'I2S receive data mismatch'):
            runner.renew_lease(device, test,
                               lambda identifier, row: records.append((identifier, row)), 'sample')
        self.assertEqual(records[0], ('sample/lease-rejected/role1',
                                     {'status': 'observation', 'words': [0]}))
        self.assertEqual(records[1][0], 'sample/lease-rejected/role1/stream2')
        self.assertEqual(records[1][1]['words'][:4], [2, 0, 6, 134217])

    def test_non_i2s_lease_rejection_keeps_generic_error(self):
        """! @brief 다른 peripheral의 lease 거부는 근거 없이 I2S 오류로 바꾸지 않습니다. """
        test = next(row for row in cases.cases() if row['id'] == 20)
        device = mock.Mock(image={'role': 2})
        device.command.return_value = [0]
        records = []
        with self.assertRaisesRegex(ProtocolError, 'T13 lease renewal failed'):
            runner.renew_lease(device, test,
                               lambda identifier, row: records.append((identifier, row)), 'sample')
        self.assertEqual(device.command.call_args_list, [mock.call(103, timeout=2)])
        self.assertEqual(records[0][0], 'sample/lease-rejected/role2')

    def test_handover_starts_target_dma_before_controller_in_both_directions(self):
        """! @brief 역방향 SPI/TWI에서도 Host 지연에 의존하지 않고 target을 먼저 시작합니다. """
        import v04_t13_handover as handover
        devices = [mock.Mock(image={'role': role}) for role in (1, 2)]
        for instance in (0, 20, 21, 22, 30):
            initial, sequence = handover.route(instance)
            for test in [initial, *sequence]:
                kind = test['serial_links'][0]['a']['kind']
                expected = [1, 2] if kind in ('spis', 'twis') else [2, 1]
                with self.subTest(instance=instance, kind=kind):
                    self.assertEqual([device.image['role'] for device in runner.start_order(devices, test)], expected)
                    self.assertEqual([device.image['role'] for device in runner.start_order(devices[::-1], test)], expected)

    def test_unprepared_peer_keeps_cleanup_session_after_other_prepare_failure(self):
        """! @brief 실제 DAP PWM 준비 거부 순서에서 A의 불필요한403과 STOP 손실을 막습니다. """
        test = next(row for row in cases.cases() if row['id'] == 26)
        devices = []
        for role in (1, 2):
            device = mock.Mock()
            device.image = {'role': role}
            device.command.side_effect = lambda opcode, args=(), timeout=2, role=role: (
                ([0] if role == 1 else [26]) + [0]*15 if opcode == 99 else [0]*20)
            devices.append(device)
        records = []
        runner.failure_snapshots(devices, test, lambda name, row: records.append(name), 'test')
        self.assertEqual(devices[0].command.call_args_list,
                         [mock.call(99, timeout=2), mock.call(107, (0,), timeout=2)])
        self.assertIn(mock.call(104, (1,), timeout=2), devices[1].command.call_args_list)
        self.assertIn('test/failure/role2/pwm-pins-page1', records)

    def test_i2s_failure_dma_proves_bit_error_and_neighbour_repetition(self):
        from v04_common_i2s import pattern as i2s_pattern
        for role, padding in ((1, 2), (2, 6)):
            seed = 0x13579246
            receiver_seed = oracle.lane_seed(seed, 0, 3-role)
            completed = 28482
            first = (completed-1)*256-padding
            buffer = [i2s_pattern(receiver_seed, first+index) for index in range(256)]
            buffer[246] ^= 1
            buffer[248] = i2s_pattern(receiver_seed, first+246)
            words = [20, role, oracle.lane_seed(seed, 0, role), receiver_seed, padding,
                     completed*256-padding, 2, first+246, i2s_pattern(receiver_seed, first+246),
                     buffer[246], 2, completed, completed+1, 6, first+246, 1, 1, 1000000, 100, 256]
            report = oracle.i2s_failure(words, buffer, seed, role)
            self.assertEqual(report['mismatches'][0]['xor'], 1)
            self.assertEqual(report['mismatches'][1]['matching_neighbour_offsets'], [-2])
            self.assertFalse(report['normal_pass'])
            for index in (3, 5, 6, 7, 8, 9, 11, 15, 16):
                broken = words[:]
                broken[index] ^= 1
                with self.subTest(role=role, index=index), self.assertRaises(ProtocolError):
                    oracle.i2s_failure(broken, buffer, seed, role)
            with self.assertRaises(ProtocolError):
                oracle.i2s_failure(words, buffer[:-1], seed, role)

    def test_i2s_first_failure_dma_keeps_padding_separate_from_corrupted_samples(self):
        """! @brief 첫 DMA의 정상 시작 zero와 실제 bit 오류를 분리하고 변조된 padding을 거부합니다. """
        from v04_common_i2s import pattern as i2s_pattern
        for role in (1, 2):
            for padding in (0, 2, 6, 16):
                seed = 0x24681357
                peer_seed = oracle.lane_seed(seed, 0, 3-role)
                buffer = [0]*padding + [i2s_pattern(peer_seed, index) for index in range(256-padding)]
                buffer[padding+22] ^= 0x3800
                words = [20, role, oracle.lane_seed(seed, 0, role), peer_seed, padding,
                         256-padding, 1, 22, i2s_pattern(peer_seed, 22), buffer[padding+22],
                         0, 1, 2, 6, 22, 1, 1, 1000000, 100, 256]
                with self.subTest(role=role, padding=padding):
                    report = oracle.i2s_failure(words, buffer, seed, role)
                    self.assertEqual(report['returned_buffer_index'], 0)
                    self.assertEqual(report['mismatches'][0]['index'], 22)
                    self.assertEqual(report['mismatches'][0]['xor'], 0x3800)
                    self.assertEqual(len(report['mismatches']), 1)
                    self.assertFalse(report['normal_pass'])
                    if padding:
                        buffer[padding-1] = 1
                        with self.assertRaises(ProtocolError):
                            oracle.i2s_failure(words, buffer, seed, role)

    def test_pwm_diagnostic_data_route_reuses_one_existing_s_net(self):
        mapping = plan.harness('S')
        self.assertEqual(mapping['P1.07'], 'P1.06')
        self.assertEqual(mapping['P1.14'], 'P1.14')

    def test_pwm_failure_tail_cannot_qualify_normal_soak_or_mixed_topology(self):
        for identifier, preflight in ((26, False), (106, True), (2, True)):
            test = dict(next(row for row in cases.cases() if row['id'] == identifier),
                        _pwm_diagnostic_tail=True)
            with self.subTest(identifier=identifier, preflight=preflight), self.assertRaises(ProtocolError):
                runner.execute_group([], {'test':test, 'members':[test]}, 180, mock.Mock(), mock.Mock(),
                                     preflight=preflight)

    def test_uart_pins_reject_observed_spi_residue_and_wrong_route(self):
        """! @brief SPI21 뒤 실제 관측한 두 보드의 RTS/CTS 잔류와 잘못된 연결을 재현합니다. """
        test = next(row for row in cases.cases() if row['id'] == 101)
        for role, stale_rts in (('a', 37), ('b', 36)):
            endpoint = test['serial_links'][1][role]
            valid = [21, 0, 38, 39, oracle.MASK, oracle.MASK, 0]
            self.assertEqual(oracle.uart_pins(valid, endpoint)['rts'], oracle.MASK)
            with self.assertRaises(ProtocolError):
                oracle.uart_pins([21, 0, 38, 39, stale_rts, 39, 0], endpoint)
            for index, value in ((0, 20), (1, 1), (2, 37), (3, 38), (4, stale_rts), (5, 39), (6, 7)):
                broken = valid[:]
                broken[index] = value
                with self.subTest(role=role, index=index), self.assertRaises(ProtocolError):
                    oracle.uart_pins(broken, endpoint)

    def test_uart_pins_require_configured_hardware_flow_control(self):
        """! @brief 네 선 UART는 실제 RTS/CTS 연결을 유지해야 하며 끊거나 교환하면 실패합니다. """
        endpoint = {'kind': 'uarte', 'instance': 20,
                    'pins': {'txd': 'P1.04', 'rxd': 'P1.05', 'rts': 'P1.06', 'cts': 'P1.07'}}
        valid = [20, 1, 36, 37, 38, 39, 8]
        self.assertEqual(oracle.uart_pins(valid, endpoint)['hwfc'], 1)
        for broken in ([20, 0, 36, 37, 38, 39, 8], [20, 1, 36, 37, 39, 38, 8],
                       [20, 1, 36, 37, oracle.MASK, oracle.MASK, 8]):
            with self.assertRaises(ProtocolError):
                oracle.uart_pins(broken, endpoint)

    def test_pin_failure_preserves_other_uart_and_peer_before_judgement(self):
        """! @brief 첫 UART 핀이 잘못돼도 다른 UART·보드의 raw를 모두 읽은 뒤 판정합니다. """
        test = next(row for row in cases.cases() if row['id'] == 101)
        devices = []
        for role in (1, 2):
            device = mock.Mock()
            device.image = {'role': role}
            device.command.return_value = [0]*7
            devices.append(device)
        observed = []
        with self.assertRaises(ProtocolError):
            runner.prepared_uart_pins(devices, test, lambda label, row: observed.append(label), 'prepared')
        self.assertEqual(observed, ['prepared/role1/lane0/pins', 'prepared/role1/lane1/pins',
                                    'prepared/role1/lane3/pins', 'prepared/role2/lane0/pins',
                                    'prepared/role2/lane1/pins', 'prepared/role2/lane3/pins'])
        for device in devices:
            self.assertEqual(device.command.call_args_list,
                             [mock.call(108, (0,), timeout=2), mock.call(108, (1,), timeout=2),
                              mock.call(108, (3,), timeout=2)])

    def test_stop_requires_clock_release_and_preserves_other_board_cleanup(self):
        """! @brief GPIO 정지 응답만으로 clock 소유권 잔류를 성공 처리하지 않습니다. """
        for held, unreadable in ((0, False), (1, False), (0, True)):
            devices = []
            for role in (1, 2):
                device = mock.Mock()
                device.image = {'role': role}
                def command(opcode, *args, current_role=role, **kwargs):
                    if opcode == 102:
                        return [1, 1]
                    if current_role == 1 and unreadable:
                        raise ProtocolError('clock observation unavailable')
                    return [1, held if current_role == 1 else 0, 0, 0, 0, 0, 0, 0]
                device.command.side_effect = command
                devices.append(device)
            observations = []
            with self.subTest(held=held, unreadable=unreadable):
                result = runner.stop_pair(devices, lambda label, row: observations.append(row), 'stop')
                self.assertEqual(result, held == 0 and not unreadable)
                self.assertEqual(len(observations[0]['outcomes']), 2)
                self.assertTrue(observations[0]['outcomes'][1]['stopped'])

    def test_timing_rejects_impossible_sum_and_maximum(self):
        bins = [2, 1, 1] + [0]*13
        valid = [4, 4, 7, 0] + bins
        self.assertEqual(oracle.timing(valid)['count'], 4)
        for index, value in ((0, 3), (1, 8), (2, 3), (3, 1), (19, 1)):
            broken = valid[:]
            broken[index] = value
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                oracle.timing(broken)
        with self.assertRaises(ProtocolError):
            oracle.timing([1, 4, 3, 0, 0, 0, 1] + [0]*13)
        self.assertEqual(oracle.timing([0]*20)['total_us'], 0)

    def test_stream_oracle_rejects_missing_samples_bad_guards_and_waveform(self):
        test = next(row for row in cases.cases() if row['id'] == 106)
        seed = 71
        adc = [0, 1, 0, 0, 10, 12, 320, 0, 123, 1000, 1200, 1100, 1101, 0, 160, 2, 32, 3, 1, 1]
        pwm = [1, 1, 0, 0, 20, 0, 20, 0, 0, 500, 500, 500, 500, 0, 100, 9600, 10, 0, 1, 1]
        peer_seed = oracle.lane_seed(seed, 0, 2)
        pattern = lambda index: ((peer_seed + 0x9E3779B9*(index+1)) ^ ((index << 16) | (index >> 16))) & oracle.MASK
        audio = [2, 1, 0, 0, 10, 12, 2560, 0, 0, 0, 0, pattern(2302), pattern(2557), 2, 2558, 0, 3, 4, 1, 1]
        for index, words in ((0, adc), (1, pwm), (2, audio)):
            self.assertGreater(oracle.stream(index, words, test, seed, 1)['units'], 0)
            for position, value in ((1, 0), (2, 1), (4, 0), (6, words[6]-1), (18, 0)):
                broken = words[:]
                broken[position] = value
                with self.subTest(index=index, position=position), self.assertRaises(ProtocolError):
                    oracle.stream(index, broken, test, seed, 1)
        for words, position in ((adc, 9), (pwm, 9), (audio, 11)):
            broken = words[:]
            broken[position] = 0
            with self.assertRaises(ProtocolError):
                oracle.stream(words[0], broken, test, seed, 1)
        test_pdm = next(row for row in cases.cases() if row['id'] == 108)
        pdm = [3, 1, 0, 0, 10, 12, 10240, 0, 0, 0, 0, 10, 20, 0, 15000, 16000, 64, 10, 1, 1]
        self.assertEqual(oracle.stream(3, pdm, test_pdm, seed, 1)['rate'], 16000)
        for position, value in ((11, 4097), (14, 4096*1024+1), (16, 151)):
            broken = pdm[:]
            broken[position] = value
            with self.assertRaises(ProtocolError):
                oracle.stream(3, broken, test_pdm, seed, 1)

    def test_fault_snapshot_preserves_other_board_and_stream_before_judgement(self):
        test = next(row for row in cases.cases() if row['id'] == 106)
        devices = []
        for role in (1, 2):
            device = mock.Mock()
            device.image = {'role': role}
            device.command.return_value = [0]*20
            devices.append(device)
        observations = []
        with self.assertRaises(ProtocolError):
            runner.snapshots(devices, test, 1, lambda identifier, row: observations.append(identifier), 'failure')
        self.assertEqual(len(observations), 2*(1+len(test['serial_links'])+3))
        self.assertIn('failure/role2/stream2', observations)

    def test_target_buffer_guards_and_pattern_match_independent_host(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 't13-model.exe'
            compiled = subprocess.run(compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'tests/zephyr/v04_t13_hil/src'),
                str(ROOT / 'tests/host/v04_t13_model_main.cpp'), '-o', str(exe)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            actual = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(actual.returncode, 0, actual.stdout + actual.stderr)
            expected = [oracle.pattern(oracle.lane_seed(0xA7130924, lane, role), position)
                for lane in range(5) for role in (1, 2)
                for position in (0, 1, 1023, 1024, 1000000, 0xFFFFFFFF)]
            self.assertEqual(list(map(int, actual.stdout.split())), expected)

    def test_pair_grouping_keeps_both_roles_without_duplicate_duration(self):
        selected = [row for row in cases.cases() if row['harness'] == 'S' and row['id'] < 100 and runner.serial_only(row)]
        groups = runner.grouped(selected)
        self.assertEqual(len(selected), 22)
        self.assertEqual(len(groups), 13)
        self.assertEqual(sum(len(group['members']) for group in groups), 22)
        for group in groups:
            if len(group['members']) == 2:
                self.assertEqual({member['measured_role'] for member in group['members']}, {'a', 'b'})
                self.assertEqual(group['members'][0]['serial_links'], group['members'][1]['serial_links'])
            self.assertEqual(group['test']['duration_seconds'], 180)

    def test_generated_catalog_preserves_exact_approved_cases(self):
        rows = cases.cases()
        self.assertEqual(len(rows), 37)
        self.assertEqual(sum(row['harness'] == 'S' for row in rows), 36)
        self.assertEqual([row['name'] for row in rows if row['harness'] == 'U'], ['uarte0'])
        self.assertFalse(any('qdec' in row['name'] or row['name'] == 'C07' for row in rows))
        self.assertEqual(sum(row['duration_seconds'] for row in rows if row['harness'] == 'S'), 14220)
        self.assertEqual(cases.generated_tokens(cases.OUTPUT.read_text(encoding='utf-8')),
                         cases.generated_tokens(cases.render()))

    def test_session_rejects_foreign_wiring_and_identity_changes(self):
        uids = ['a' * 32, 'b' * 32]
        images = [{'role': role, 'board_revision': plan.plan()['board_revision'],
                   'core_revision': 'c' * 40} for role in (1, 2)]
        grant = dict(type='v04-t13-s-session', harness='S', catalog_sha256=session.catalog_hash(),
            uid_sha256=[hashlib.sha256(uid.encode()).hexdigest() for uid in uids],
            user_wiring_report='S 연결', user_maintain_reply='실행 중 유지')
        for key in ('maintain_harness_until_end', 'notify_before_usb_wiring_switch_changes',
                    'dap_uart_disconnected_both', 'swd_connected_both', 'equal_io_voltage_confirmed',
                    'power_rails_not_joined', 'common_ground_confirmed', 'links_match_catalog',
                    'external_pullups_disconnected', 'extra_outputs_disconnected'):
            grant[key] = True
        session.validate(grant, images, uids)
        session.validate({**grant, 'confirmed_at_unix': -1, 'expires_at_unix': float('nan')},
                         images, uids)
        for key, value in (('harness', 'C'), ('harness', 'U'),
                           ('links_match_catalog', 1), ('catalog_sha256', '0' * 64),
                           ('user_maintain_reply', '')):
            with self.subTest(key=key, value=value), self.assertRaises(ProtocolError):
                session.validate({**grant, key: value}, images, uids)
        images[1]['core_revision'] = 'd' * 40
        with self.assertRaises(ProtocolError):
            session.validate(grant, images, uids)

    def test_u_session_requires_its_own_current_grant_and_compiled_identity(self):
        """! @brief 기 S 확인을 U 결선·image 권한으로 재사용하지 않습니다. """
        uids = ['a' * 32, 'b' * 32]
        images = [{'role': role, 'board_revision': plan.plan()['board_revision'],
                   'core_revision': 'c' * 40} for role in (1, 2)]
        grant = dict(type='v04-t13-u-session', harness='U', catalog_sha256=session.catalog_hash(),
            uid_sha256=[hashlib.sha256(uid.encode()).hexdigest() for uid in uids],
            user_wiring_report='U 연결', user_maintain_reply='실행 중 유지')
        for key in ('maintain_harness_until_end', 'notify_before_usb_wiring_switch_changes',
                    'dap_uart_disconnected_both', 'swd_connected_both', 'equal_io_voltage_confirmed',
                    'power_rails_not_joined', 'common_ground_confirmed', 'links_match_catalog',
                    'external_pullups_disconnected', 'extra_outputs_disconnected'):
            grant[key] = True
        session.validate(grant, images, uids, harness='U')
        for requested, changed in (('S', {}), ('U', {'type': 'v04-t13-s-session'}),
                                   ('U', {'harness': 'S'})):
            with self.subTest(requested=requested, changed=changed), self.assertRaises(ProtocolError):
                session.validate({**grant, **changed}, images, uids, harness=requested)
        digest = bytes.fromhex(session.catalog_hash())
        identity = [0x54313303] + [int.from_bytes(digest[index:index + 4], 'little')
                                     for index in range(0, 32, 4)] + [0x1FF]
        device = mock.Mock()
        device.command.return_value = identity
        self.assertEqual(session.verify_profile(device, 'U'), 0x1FF)
        identity[0] = 0x54313302
        with self.assertRaises(ProtocolError):
            session.verify_profile(device, 'U')

    def test_u_runner_is_fail_closed_to_fixed_uart00_phases(self):
        """! @brief U는 S 버스·stream·전원·역방향 변형을 실행 전에 거부합니다. """
        for phase in runner.U_PHASES:
            runner.validate_harness_phase('U', phase)
        for phase in ('stream-fault', 'spi-boundary', 'twi-stuck', 'twis-delay',
                      'uart-line-fault', 'handover', 'pwm-recovery'):
            with self.subTest(phase=phase), self.assertRaises(ProtocolError):
                runner.validate_harness_phase('U', phase)
        with self.assertRaises(ProtocolError):
            runner.validate_harness_phase('U', 'preflight', reverse_serial=True)
        runner.validate_harness_phase('S', 'spi-boundary')

    def test_missing_duplicate_and_corrupt_completion_are_rejected(self):
        seed, length, count = 37, 256, 3
        total = length * count
        word = lambda at: int.from_bytes(bytes(oracle.pattern(seed, at + i) for i in range(4)), 'little')
        valid = [count, total, 0, 0x12345678, word(total - length), word(total - 4)]
        actual = oracle.direction(valid, seed, length)
        self.assertEqual(actual['bytes'], total)
        for position in (0, 1, 2, 4, 5):
            broken = valid[:]
            broken[position] ^= 1
            with self.subTest(position=position), self.assertRaises(ProtocolError):
                oracle.direction(broken, seed, length)
        paired = [{'tx': dict(actual), 'rx': dict(actual)}, {'tx': dict(actual), 'rx': dict(actual)}]
        oracle.paired(paired)
        broken = copy.deepcopy(paired)
        broken[1]['rx']['hash'] ^= 1
        with self.assertRaises(ProtocolError):
            oracle.paired(broken)
        empty = {'frames': 0, 'bytes': 0, 'hash': 2166136261}
        with self.assertRaises(ProtocolError):
            oracle.paired([{'tx': empty, 'rx': empty}] * 2)

    def test_device_fault_and_fabricated_time_are_rejected(self):
        words = [2, 1, 1, 0, 1, 0, 40, 2000, 0, 1000, 0, 1000, 0, 123, 0, 0]
        self.assertEqual(oracle.engine(words)['elapsed_ms'], 1000)
        for index, value in ((4, 0), (5, 1), (11, 1001), (7, 999)):
            broken = words[:]
            broken[index] = value
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                oracle.engine(broken)


if __name__ == '__main__':
    unittest.main()
