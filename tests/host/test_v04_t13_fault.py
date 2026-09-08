"""! @brief T13의 취소/NACK를 정상 완료·가짜 부분량·잘못된 주소와 구분합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
from v04_protocol import ProtocolError
import v04_t13_cases as cases
import v04_t13_fault as fault
import v04_t13_run as runner


class SerialFaultTests(unittest.TestCase):
    def vector(self, mode):
        test_id = 2 if mode in (1, 2) else 7 if mode == 3 else 16
        test = next(row for row in cases.cases() if row['id'] == test_id)
        kind, event, pointers, lane_error = fault.MODES[mode]
        length = test['serial_links'][0]['buffer_bytes']
        amounts = [8, 0] if mode == 1 else [0, 8] if mode == 2 else [0, 0] if mode == 3 else [length, 0 if mode == 5 else length]
        hardware = [0, 0] if mode == 5 else [0, 8] if mode == 2 else [8, 0]
        words = [mode, 1, 0, fault.KINDS[kind], 20, event, *amounts, pointers, 1,
                 0, 0x44 if mode == 5 else 0x42 if mode == 4 else 0,
                 100, 160, 300, 1, *hardware, lane_error, 1000000]
        return test, words

    def test_each_expected_fault_has_distinct_event_and_hardware_amount(self):
        for mode in fault.MODES:
            test, words = self.vector(mode)
            with self.subTest(mode=mode):
                result = fault.inspect(words, test, 1, mode)
                self.assertEqual(result['mode'], mode)
                if mode == 5:
                    self.assertEqual(result['api_tx_length'], 256)
                    self.assertEqual(result['observed_tx_amount'], 0)
                    self.assertIsNone(result['observed_rx_amount'])
                    words[17] = 1024
                    self.assertEqual(fault.inspect(words, test, 1, mode)['rx_amount_raw'], 1024)

    def test_missing_event_bad_guard_wrong_instance_and_pointer_are_rejected(self):
        for mode in fault.MODES:
            test, words = self.vector(mode)
            for index, value in ((1, 0), (2, 1), (4, 21), (5, 0xFFFFFFFF), (8, 0), (9, 0),
                                 (13, 301), (15, 0), (18, 0), (19, 0)):
                broken = words[:]
                broken[index] = value
                with self.subTest(mode=mode, index=index), self.assertRaises(ProtocolError):
                    fault.inspect(broken, test, 1, mode)

    def test_finished_or_empty_cancel_is_not_mid_dma_and_nack_address_is_fixed(self):
        for mode in (1, 2, 3, 4):
            test, words = self.vector(mode)
            length = test['serial_links'][0]['buffer_bytes']
            position = 6 if mode == 1 else 7 if mode == 2 else 16
            for amount in (0, length):
                broken = words[:]
                broken[position] = amount
                with self.subTest(mode=mode, amount=amount), self.assertRaises(ProtocolError):
                    fault.inspect(broken, test, 1, mode)
        test, words = self.vector(5)
        for address in (0x42, 0x6A):
            words[11] = address
            with self.assertRaises(ProtocolError):
                fault.inspect(words, test, 1, 5)

    def test_unsupported_peer_stream_and_mixed_cases_are_rejected(self):
        for test_id, role, mode in ((7, 2, 3), (16, 2, 5), (101, 1, 1), (30, 1, 1), (2, 1, 0)):
            test = next(row for row in cases.cases() if row['id'] == test_id)
            with self.subTest(case=test_id, role=role, mode=mode), self.assertRaises(ProtocolError):
                fault.validate_selection(test, role, mode)

    def test_fault_cleanup_precedes_judgement_and_restart_uses_new_nonce(self):
        test, valid = self.vector(1)
        for corrupt in (False, True):
            raw = valid[:]
            if corrupt:
                raw[8] = 0
            devices = []
            observations = []
            for role in (1, 2):
                device = mock.Mock()
                device.image = {'role': role}
                state = {'stopped': False}
                def command(opcode, *args, current_state=state, **kwargs):
                    if opcode == 107:
                        return [1, 0 if current_state['stopped'] else 1, 65537, 0, 0, 0, 0, 0]
                    if opcode == 110:
                        return raw[:]
                    if opcode == 99:
                        return [2, 0, 0, 0, 0, 0] + [0]*10
                    if opcode == 100:
                        return [0]*20
                    if opcode == 102:
                        current_state['stopped'] = True
                        return [1, 0]
                    if opcode == 51:
                        return [0]*8
                    return [1]
                device.command.side_effect = command
                devices.append(device)
            with (self.subTest(corrupt=corrupt), mock.patch.object(fault.time, 'sleep'),
                  mock.patch.object(runner, 'prepared_uart_pins'),
                  mock.patch.object(runner, 'prepared_bus_pins'),
                  mock.patch.object(runner, 'execute_group') as restart):
                run = lambda: fault.execute(devices, test, 1, 1, mock.Mock(),
                    lambda label, row: observations.append((label, row)), preflight=True)
                if corrupt:
                    with self.assertRaises(ProtocolError):
                        run()
                    restart.assert_not_called()
                else:
                    run()
                    seed = observations[0][1]['seed']
                    self.assertEqual(restart.call_args.kwargs['seed'], seed ^ 0x9E3779B9)
                    self.assertFalse(observations[-1][1]['planned_recovery_pass'])
                for device in devices:
                    self.assertIn(mock.call(102, timeout=2), device.command.call_args_list)
                self.assertTrue(any(label.endswith('/final/role2/fault') for label, _ in observations))


if __name__ == '__main__':
    unittest.main()
