"""! @brief 자동 System OFF의 실제 reset·nonce·debug 해제·정리 경계를 검증합니다. """
from pathlib import Path
from contextlib import ExitStack
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_power as power
from v04_protocol import ProtocolError, encode


class PowerTests(unittest.TestCase):
    def test_gpio_wake_uses_zephyr_level_detection_path(self):
        """! @brief nRF54L15 GPIO wake가 PIN_CNF 직접 설정으로 퇴행하지 않게 합니다. """
        source = (ROOT/'tests/zephyr/v04_t13_hil/src/power.cpp').read_text(encoding='utf-8')
        self.assertIn('gpio_pin_configure(wake_gpio.port, wake_gpio.pin,', source)
        self.assertIn('gpio_pin_interrupt_configure(wake_gpio.port, wake_gpio.pin,', source)
        self.assertIn('GPIO_INT_LEVEL_LOW', source)
        self.assertNotIn('nrf_gpio_cfg_sense_input(wake_pin', source)

    def test_probe_inventory_is_forbidden_after_peer_debug_detach(self):
        """! @brief B System OFF 중 전체 probe 열거가 DIF wake를 일으키지 않게 합니다. """
        helper = mock.Mock()
        helper.get_all_connected_probes.return_value = [mock.Mock(unique_id='AABB')]
        self.assertEqual(power.connected_probe_uids(helper, False), {'aabb'})
        with self.assertRaisesRegex(ProtocolError, 'prohibited'):
            power.connected_probe_uids(helper, True)
        helper.get_all_connected_probes.assert_called_once_with(blocking=False)
        self.assertEqual(power.PEER_PIN_RESET_SETTLE_SECONDS, .7)
        self.assertEqual(power.POWER_SWD_FREQUENCY_HZ, 1_000_000)

    def test_both_uart_pins_precede_controller_rx_and_no_peer_command_is_sent(self):
        """! @brief 양쪽 준비 후 A RX가 실제 활성화되고 B reset은 호출자에게 남는 순서를 대조합니다. """
        calls = []
        words = [power.PINS_MAGIC, 1, 500, 64, 192, 3, 12, 8, 38, 39,
                 65537, 1, 1, 0, 0, 0, 0, 0, 1, 1]
        devices = [mock.Mock(image={'role': role}) for role in (1, 2)]
        def command(role, opcode, args=(), **kwargs):
            calls.append((role, opcode, args))
            if opcode == 134:
                return [power.POLL_MAGIC, role, 0, 0, 0] if args == (2,) else words
            return [1]
        for role, device in enumerate(devices, 1):
            device.command.side_effect = lambda opcode, args=(), role=role, **kw: command(role, opcode, args, **kw)
        power.prepare_uart_pair(devices, 0, mock.Mock())
        self.assertEqual(calls, [(1,130,(power.MAGIC,)),(1,134,(2,)),
            (2,130,(power.MAGIC,)),(2,134,(2,)),(1,131,()),(1,134,(1,))])

    def test_disabled_controller_or_unexpected_traffic_cannot_proceed_to_peer_reset(self):
        """! @brief ENABLE0·미준비 RX·핀 불일치·기존 오류 또는 트래픽을 reset 전 거부합니다. """
        original = [power.PINS_MAGIC, 1, 500, 64, 192, 3, 12, 8, 38, 39,
                    65537, 1, 1, 0, 0, 0, 0, 0, 1, 1]
        for index, value in ((7,0),(8,39),(9,38),(11,0),(12,0),(13,1),(14,1),(15,1),(16,1)):
            words = original[:]
            words[index] = value
            devices = [mock.Mock(image={'role': role}) for role in (1,2)]
            devices[0].command.side_effect = [[1],[power.POLL_MAGIC,1,0,0,0],[1],words]
            devices[1].command.side_effect = [[1],[power.POLL_MAGIC,2,0,0,0]]
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                power.prepare_uart_pair(devices,0,mock.Mock())

    def test_fast_polling_cannot_select_off_or_a_hundred_repetitions(self):
        """! @brief 비교 정책은 단일 중계만 허용하고 timer/GPIO는 원래 정책을 유지합니다. """
        self.assertEqual(power.polling_policy('bridge-fast-poll', 1), 1)
        for phase in ('bridge', 'timer', 'gpio'):
            for repeats in (1, 100):
                self.assertEqual(power.polling_policy(phase, repeats), 0)
        self.assertEqual(power.polling_policy('timer-gpio', 1), 0)
        for phase, repeats in (('bridge-fast-poll', 100), ('bridge-debug', 100),
                               ('timer-gpio', 100), ('other', 1), ('timer', 2)):
            with self.subTest(phase=phase, repeats=repeats), self.assertRaises(ProtocolError):
                power.polling_policy(phase, repeats)

    def test_polling_policy_must_survive_reset_with_the_same_role_and_no_error(self):
        """! @brief reset으로 사라진 정책·다른 역할·오류 응답을 성공으로 바꾸지 않습니다. """
        for policy in (0, 1):
            words = [power.POLL_MAGIC, 2, policy, policy, 0]
            self.assertFalse(power.inspect_polling(words, 2, policy)['system_off_pass'])
            for index in range(5):
                broken = words[:]
                broken[index] ^= 1
                with self.subTest(policy=policy, index=index), self.assertRaises(ProtocolError):
                    power.inspect_polling(broken, 2, policy)
        for words in (None, [], [power.POLL_MAGIC, 2, 1, True, 0]):
            with self.assertRaises(ProtocolError):
                power.inspect_polling(words, 2, 1)

    def test_live_pins_keep_low_and_separate_observation_from_pass(self):
        """! @brief LOW 상태는 보존하며 손상 응답·다른 역할·잘못된 길이는 거부합니다. """
        device = mock.Mock(image={'role': 1})
        append = mock.Mock()
        words = [power.PINS_MAGIC, 1, 500, 64, 0, 3, 12, 8, 38, 39,
                 65537, 1, 1, 0, 0, 0, 0, 0, 1, 1]
        device.command.return_value = words
        power.observe_pins(device, append, 'pins/test')
        result = append.call_args.args[1]
        self.assertEqual((result['tx_level'], result['rx_level']), (0, 0))
        self.assertFalse(result['system_off_pass'])
        for index, value in ((0, 0), (1, 2), (11, 2), (12, 2), (13, 2), (14, -1)):
            broken = words[:]
            broken[index] = value
            device.command.return_value = broken
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                power.observe_pins(device, append, 'pins/test')
        device.command.return_value = words[:-1]
        with self.assertRaises(ProtocolError):
            power.observe_pins(device, append, 'pins/test')

    def test_hardware_fault_does_not_accept_synthetic_queue_overflow(self):
        """! @brief 합성 큐 초과를 하드웨어 오류로 바꾸지 않으며 실제 저위 비트만 보존합니다. """
        target = mock.Mock()
        image = {'role': 2, 'power_hardware_fault_address': power.pair.RAM_BEGIN+2048}
        words = [power.FAULT_MAGIC, 2, 8, 5, 12]+[0]*15
        target.read_memory_block8.return_value = struct.pack('<20I', *words)
        self.assertEqual(power.read_power_hardware_fault(target, image)['error_mask'], 12)
        for mask in (0, 16, 0x80000000):
            words[4] = mask
            target.read_memory_block8.return_value = struct.pack('<20I', *words)
            with self.subTest(mask=mask), self.assertRaises(ProtocolError):
                power.read_power_hardware_fault(target, image)

    def test_wake_register_snapshot_preserves_off_and_boot_sides(self):
        """! @brief OFF 직전 설정과 cleanup DIF reset을 성공으로 확대하지 않고 보존합니다. """
        target = mock.Mock()
        image = {'role': 2, 'power_wake_address': power.pair.RAM_BEGIN+2560}
        words = [power.WAKE_MAGIC, 2, 1, 7, 12, 65535, 0, 0, 0, 0, 0,
                 1, 3, 4, 1, 8, 1234, 0, 3, 2000000, 1024, 32, 0, 1]
        target.read_memory_block8.return_value = struct.pack('<24I', *words)
        result = power.read_power_wake(target, image)
        self.assertEqual(result['grtc_active_cc_mask'], 8)
        self.assertEqual(result['grtc_counter'], 1234)
        self.assertEqual(result['grtc_active_channel'], 3)
        self.assertEqual(result['grtc_compare_delta'], 2000000)
        self.assertEqual(result['resetreas_after_boot'], 1024)
        self.assertFalse(result['expected_wake'])
        self.assertFalse(result['system_off_pass'])
        for index, value in ((0, 0), (1, 1), (2, 0), (3, 0), (22, 2), (23, 0)):
            broken = words[:]
            broken[index] = value
            target.read_memory_block8.return_value = struct.pack('<24I', *broken)
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                power.read_power_wake(target, image)
        target.read_memory_block8.return_value = bytes(95)
        with self.assertRaises(ProtocolError):
            power.read_power_wake(target, image)

    def test_target_captures_wake_registers_before_poweroff(self):
        """! @brief reset clear·GRTC 준비·snapshot·retention 저장·OFF 순서를 고정합니다. """
        source = (ROOT/'tests/zephyr/v04_t13_hil/src/power.cpp').read_text(encoding='utf-8')
        start = source.index('void enterOff()')
        end = source.index('\n    }\n} // namespace', start)
        body = source[start:end]
        order = [body.index(token) for token in ('hwinfo_clear_reset_cause()',
            'z_nrf_grtc_wakeup_prepare(2000000U)', 'captureWakeRegisters();',
            'if (!save())', 'sys_poweroff();')]
        self.assertEqual(order, sorted(order))
        for token in ('NRF_P1->PIN_CNF[14U]', 'NRF_P1->IN', 'NRF_P1->LATCH',
                      'NRF_P1->DETECTMODE', 'nrf_reset_resetreas_get(NRF_RESET)',
                      'NRF_GRTC->MODE', 'NRF_GRTC->TIMEOUT', 'NRF_GRTC->WAKETIME',
                      'NRF_GRTC->STATUS.LFTIMER', 'GRTC_CC_CCEN_ACTIVE_Msk',
                      'nrf_grtc_sys_counter_get', 'nrf_grtc_sys_counter_cc_get'):
            self.assertIn(token, source)

    def test_debug_held_bridge_cannot_substitute_for_normal_mode_or_off(self):
        """! @brief debug 유지 진단에는 정상 mode·reset·retention 성공을 부여하지 않습니다. """
        words = [power.MAGIC, 2, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 65537, 1, 2, 0, 0, 0, 800]
        result = power.inspect_debug_bridge(words)
        self.assertFalse(result['normal_mode_proven'])
        self.assertFalse(result['system_off_pass'])
        with self.assertRaises(ProtocolError):
            power.inspect(words, boots=1, mode=0, round_number=0, seed=0)
        for index, value in ((1, 1), (2, 0), (4, 1), (5, 1), (7, 1), (8, 1),
                             (10, 0), (11, 0), (12, 0), (13, 0), (14, 0), (15, 1), (17, 1)):
            broken = words[:]
            broken[index] = value
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                power.inspect_debug_bridge(broken)

    def test_idle_snapshot_preserves_low_and_high_without_claiming_off_success(self):
        """! @brief LOW 관측을 숨기지 않으며 잘못된 pull·role·핀과 찢어진 응답을 거부합니다. """
        target = mock.Mock()
        image = {'role': 2, 'power_idle_address': power.pair.RAM_BEGIN+2048}
        words = [power.IDLE_MAGIC, 2, 3, 21, 38, 39, 3, 0, 0, 12, 1, 1, 0, 4096, 30801920, 0, 1, 1, 0, 0]
        for level in (0, 1):
            words[10] = level
            target.read_memory_block8.return_value = struct.pack('<20I', *words)
            result = power.read_power_idle(target, image)
            self.assertEqual(result['rx_after'], level)
            self.assertFalse(result['system_off_pass'])
        for index, value in ((0, 0), (1, 1), (3, 22), (4, 39), (5, 38),
                             (8, 2), (9, 0), (10, 2), (11, 2), (18, 1)):
            broken = words[:]
            broken[index] = value
            target.read_memory_block8.return_value = struct.pack('<20I', *broken)
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                power.read_power_idle(target, image)
        target.read_memory_block8.return_value = bytes(79)
        with self.assertRaises(ProtocolError):
            power.read_power_idle(target, image)

    def test_first_fault_region_cannot_overlap_mailbox_or_leave_sram(self):
        start = power.pair.RAM_BEGIN
        symbols = {'v04_request': start, 'v04_response': start+128, 'v04_identity': start+256}
        self.assertEqual(power.fault_region(start+320, 80, symbols), start+320)
        for address, size in ((start, 80), (start+316, 80), (start+321, 80),
                              (start+320, 64), (power.pair.RAM_END-76, 80), (start-80, 80)):
            with self.subTest(address=address, size=size), self.assertRaises(ProtocolError):
                power.fault_region(address, size, symbols)

    def test_first_fault_read_preserves_mask_and_rejects_torn_or_foreign_record(self):
        target = mock.Mock()
        image = {'role': 2, 'power_fault_address': power.pair.RAM_BEGIN+1024}
        words = [power.FAULT_MAGIC, 2, 250, 5, 4]+[0]*15
        target.read_memory_block8.return_value = struct.pack('<20I', *words)
        self.assertEqual(power.read_power_fault(target, image)['error_mask'], 4)
        target.read_memory_block8.assert_called_once_with(image['power_fault_address'], 80)
        for index, value in ((0, 0), (1, 1), (3, 6)):
            broken = words[:]
            broken[index] = value
            target.read_memory_block8.return_value = struct.pack('<20I', *broken)
            with self.assertRaises(ProtocolError):
                power.read_power_fault(target, image)
        target.read_memory_block8.return_value = bytes(80)
        self.assertFalse(power.read_power_fault(target, image)['present'])

    def words(self, mode):
        return [power.MAGIC, 2, 1, 0, 0, 1 if mode == 0 else 2,
                (1, 2048, 128)[mode], 0, mode, int(mode != 0), 0, 0, 0,
                65537, 3, 4, int(mode != 0), 1, 77 if mode else 0, 900]

    def test_normal_reset_and_each_wake_require_distinct_cause_and_retention(self):
        for mode in (0, 1, 2):
            words = self.words(mode)
            check = lambda raw: power.inspect(raw, boots=words[5], mode=mode,
                round_number=words[9], seed=words[18])
            check(words)
            for index in (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 17, 18):
                broken = words[:]
                broken[index] ^= 1
                with self.subTest(mode=mode, index=index), self.assertRaises(ProtocolError):
                    check(broken)
            for cause in (0, 1 | 32, 32, 128 | 2048):
                broken = words[:]
                broken[6] = cause
                with self.subTest(mode=mode, cause=cause), self.assertRaises(ProtocolError):
                    check(broken)

    def test_foreign_source_and_invalid_raw_types_are_rejected(self):
        source = 'a'*40
        words = [*struct.unpack('<10I', source.encode()), power.MAGIC]
        power.verify_source(words, source)
        for index in range(11):
            broken = words[:]
            broken[index] ^= 1
            with self.assertRaises(ProtocolError):
                power.verify_source(broken, source)
        for raw in (None, self.words(1)[:-1], self.words(1)+[0]):
            with self.assertRaises(ProtocolError):
                power.inspect(raw, boots=2, mode=1, round_number=1, seed=77)

    def test_normal_uart_bridge_requires_running_crystal(self):
        """! @brief debug 해제·reset 원인이 맞아도 XO가 정지한 응답은 거부합니다. """
        for mode in (0, 1, 2):
            words = self.words(mode)
            for clock in (0, 1):
                words[13] = clock
                with self.subTest(mode=mode, clock=clock), self.assertRaises(ProtocolError):
                    power.inspect(words, boots=words[5], mode=mode,
                                  round_number=words[9], seed=words[18])

    def test_relay_validates_full_nonce_sequence_and_never_retries_uncertain_command(self):
        nonce = bytes(range(16))
        for corrupt in (False, True):
            controller = mock.Mock()
            raw = encode(b'x'*16 if corrupt else nonce, 8, 2, 134, [7, 8])
            words = struct.unpack('<32I', raw)
            def command(opcode, args=(), **kwargs):
                if opcode == 135:
                    return list(words[args[0]*16:(args[0]+1)*16])
                return [1]
            controller.command.side_effect = command
            check, append = mock.Mock(), mock.Mock()
            relay = power.Relay(controller, nonce, 7, check, append)
            if corrupt:
                with self.assertRaises(ProtocolError):
                    relay.command(134)
                count = controller.command.call_count
                with self.assertRaises(ProtocolError):
                    relay.command(134)
                self.assertEqual(controller.command.call_count, count)
            else:
                self.assertEqual(relay.command(134), [7, 8])
                self.assertEqual(controller.command.call_args_list[0].args[0], 132)
                self.assertEqual(controller.command.call_args_list[2].args[0], 133)
                self.assertEqual(append.call_args.args[1]['response_hex'], raw.hex())
            check.assert_called_once()

    def test_any_reply_during_off_silence_fails_without_consuming_normal_sequence(self):
        relay = power.Relay(mock.Mock(), bytes(range(16)), 7, mock.Mock(), mock.Mock())
        with mock.patch.object(relay, 'send'), mock.patch.object(relay, 'receive', return_value=b'awake'):
            with self.assertRaises(ProtocolError):
                relay.silence_probe()
        self.assertEqual(relay.sequence, 7)
        self.assertTrue(relay.poisoned)

    def test_debug_session_closes_before_pin_only_reset_and_reset_is_released(self):
        device = mock.Mock()
        device.target.session.options = {}
        probe = mock.Mock(spec=['open', 'close', 'assert_reset', 'is_reset_asserted', 'connect'])
        device.target.session.probe = probe
        probe.is_reset_asserted.return_value = False
        calls = []
        device.target.session.close.side_effect = lambda: calls.append('session-close')
        probe.open.side_effect = lambda: calls.append('probe-open')
        probe.assert_reset.side_effect = lambda level: calls.append(level)
        probe.close.side_effect = lambda: calls.append('probe-close')
        with mock.patch.object(power.time, 'sleep'):
            power.detach_and_pin_reset(device, mock.Mock())
        self.assertEqual(calls, ['session-close', 'probe-open', True, False, False, 'probe-close'])
        probe.connect.assert_not_called()
        self.assertTrue(device.target.session.options['resume_on_disconnect'])

    def test_physical_swd_isolation_precedes_pin_reset(self):
        """! @brief B debug session을 닫은 뒤에만 물리 SWD를 격리하고 nRESET을 실행합니다. """
        device = mock.Mock()
        device.target.session.options = {}
        probe = mock.Mock(spec=['open', 'close', 'assert_reset', 'is_reset_asserted'])
        device.target.session.probe = probe
        probe.is_reset_asserted.return_value = False
        calls = []
        device.target.session.close.side_effect = lambda: calls.append('session-close')
        probe.open.side_effect = lambda: calls.append('probe-open')
        probe.assert_reset.side_effect = lambda level: calls.append(('reset', level))
        probe.close.side_effect = lambda: calls.append('probe-close')
        switch = lambda stage: calls.append(('switch', stage))
        with mock.patch.object(power.time, 'sleep'):
            power.detach_and_pin_reset(device, mock.Mock(), switch)
        self.assertEqual(calls, ['session-close', ('switch', 'isolate'), 'probe-open',
                         ('reset', True), ('reset', False), ('reset', False), 'probe-close'])

    def test_cleanup_attach_retries_only_three_times_and_preserves_second_success(self):
        """! @brief 첫 attach가 OFF를 깨우기만 한 경우 한정 재접속으로 진단 원본을 보존합니다. """
        helper = mock.Mock()
        connection = mock.MagicMock()
        connection.target.read_memory_block8.return_value = bytes(64)
        helper.session_with_chosen_probe.side_effect = [RuntimeError('No ACK'), connection]
        image = {'role': 2, 'core_revision': 'a'*40,
                 'symbols': {'v04_identity': power.pair.RAM_BEGIN}}
        append = mock.Mock()
        with ExitStack() as stack, mock.patch.object(power.time, 'sleep'), \
                mock.patch.object(power.pair, 'verify_identity'):
            target, identity = power.reopen_peer_for_cleanup(
                stack, helper, 'peer', image, append)
        self.assertIs(target, connection.target)
        self.assertEqual(identity, bytes(64))
        self.assertEqual(helper.session_with_chosen_probe.call_count, 2)
        self.assertEqual(append.call_args.args[1]['attempt'], 2)

        helper.reset_mock()
        helper.session_with_chosen_probe.side_effect = RuntimeError('No ACK')
        with ExitStack() as stack, mock.patch.object(power.time, 'sleep'):
            with self.assertRaisesRegex(ProtocolError, 'after 3 attempts'):
                power.reopen_peer_for_cleanup(stack, helper, 'peer', image, append)
        self.assertEqual(helper.session_with_chosen_probe.call_count,
                         power.CLEANUP_ATTACH_ATTEMPTS)


if __name__ == '__main__':
    unittest.main()
