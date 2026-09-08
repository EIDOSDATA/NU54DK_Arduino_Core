"""! @brief 자동 System OFF의 실제 reset·nonce·debug 해제·정리 경계를 검증합니다. """
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_power as power
from v04_protocol import ProtocolError, encode


class PowerTests(unittest.TestCase):
    def test_debug_held_bridge_cannot_substitute_for_normal_mode_or_off(self):
        """! @brief debug 유지 진단에는 정상 mode·reset·retention 성공을 부여하지 않습니다. """
        words = [power.MAGIC, 2, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 2, 0, 0, 0, 800]
        result = power.inspect_debug_bridge(words)
        self.assertFalse(result['normal_mode_proven'])
        self.assertFalse(result['system_off_pass'])
        with self.assertRaises(ProtocolError):
            power.inspect(words, boots=1, mode=0, round_number=0, seed=0)
        for index, value in ((1, 1), (2, 0), (4, 1), (5, 1), (7, 1), (8, 1),
                             (10, 0), (11, 0), (12, 0), (14, 0), (15, 1), (17, 1)):
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


if __name__ == '__main__':
    unittest.main()
