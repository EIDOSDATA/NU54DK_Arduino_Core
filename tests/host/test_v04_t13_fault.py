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
    def proof(self, words):
        return [4, 1, 0, words[17], 0, 0, 0, 0, 0, 0, 1, 0] + words[12:15] + words[16:18] + [256, 6, 1]

    def inspect(self, words, test, role, mode):
        return fault.inspect(words, test, role, mode, twi_proof=self.proof(words) if mode == 4 else None)

    def test_twi_prior_amount_requires_unstarted_rx_whole_ram_and_same_terminal_event(self):
        test, words = self.vector(4)
        for previous in (0, 256):
            words[17] = previous
            proof = self.proof(words)
            result = fault.inspect(words, test, 1, 4, twi_proof=proof)
            self.assertEqual(result['observed_rx_amount'], 0)
            self.assertEqual(result['rx_amount_raw'], previous)
            with self.assertRaises(ProtocolError):
                fault.inspect(words, test, 1, 4)
            for index in range(20):
                if index == 2:
                    continue
                broken = proof[:]
                broken[index] ^= 1
                with self.subTest(previous=previous, index=index), self.assertRaises(ProtocolError):
                    fault.inspect(words, test, 1, 4, twi_proof=broken)
            broken = proof[:]
            broken[2] = 257
            with self.assertRaises(ProtocolError):
                fault.inspect(words, test, 1, 4, twi_proof=broken)

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

    def test_valid_twi_provenance_reaches_fresh_restart_only_after_pair_cleanup(self):
        test, words = self.vector(4)
        words[17] = 256
        proof = self.proof(words)
        devices = [mock.Mock(), mock.Mock()]
        rows = []
        cleaned = []
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            device.command.side_effect = lambda opcode, *args, **kwargs: {
                107: [1, 1, 65537, 0], 99: [test['id'], 0, 0, 0, 0, 0]+[0]*10,
                100: [0]*20, 110: words[:], 123: proof[:]}.get(opcode, [1])
        def restart(*args, **kwargs):
            self.assertEqual(cleaned, [True])
            self.assertEqual(kwargs['seed'], rows[0][1]['seed'] ^ 0x9E3779B9)
        with (mock.patch.object(fault.time, 'sleep'), mock.patch.object(runner, 'prepared_uart_pins'),
              mock.patch.object(runner, 'prepared_bus_pins'),
              mock.patch.object(runner, 'stop_pair', side_effect=lambda *args: cleaned.append(True) or True),
              mock.patch.object(runner, 'idle_pins', return_value=True),
              mock.patch.object(runner, 'execute_group', side_effect=restart) as restarted):
            fault.execute(devices, test, 1, 4, mock.Mock(), lambda name, row: rows.append((name, row)), preflight=True)
        restarted.assert_called_once()
        measured = next(row for _, row in rows if row['status'] == 'expected-fault-observed')
        self.assertEqual((measured['rx_amount_raw'], measured['observed_rx_amount']), (256, 0))
        self.assertFalse(rows[-1][1]['planned_recovery_pass'])

    def test_rx_cancel_requires_new_receive_activity_before_first_frame_completion(self):
        """! @brief TX 기준·오래된 RX 완료·비활성 수신을 수신 중 취소 성공으로 인정하지 않습니다. """
        test, valid = self.vector(2)
        self.assertEqual(self.inspect(valid, test, 1, 2)['timing_reference'], 'first_rxdrdy_observation')
        proof = [2, 1, 1, 0, 1] + valid[12:15]
        fault.inspect_rx_activity(proof, valid)
        for index in range(8):
            broken = proof[:]
            broken[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                fault.inspect_rx_activity(broken, valid)

    def test_each_expected_fault_has_distinct_event_and_hardware_amount(self):
        for mode in fault.MODES:
            test, words = self.vector(mode)
            with self.subTest(mode=mode):
                result = self.inspect(words, test, 1, mode)
                self.assertEqual(result['mode'], mode)
                if mode == 5:
                    self.assertEqual(result['api_tx_length'], 256)
                    self.assertEqual(result['observed_tx_amount'], 0)
                    self.assertIsNone(result['observed_rx_amount'])
                    words[17] = 1024
                    self.assertEqual(self.inspect(words, test, 1, mode)['rx_amount_raw'], 1024)

    def test_missing_event_bad_guard_wrong_instance_and_pointer_are_rejected(self):
        for mode in fault.MODES:
            test, words = self.vector(mode)
            for index, value in ((1, 0), (2, 1), (4, 21), (5, 0xFFFFFFFF), (8, 0), (9, 0),
                                 (13, 301), (15, 0), (18, 0), (19, 0)):
                broken = words[:]
                broken[index] = value
                with self.subTest(mode=mode, index=index), self.assertRaises(ProtocolError):
                    self.inspect(broken, test, 1, mode)

    def test_finished_or_empty_cancel_is_not_mid_dma_and_nack_address_is_fixed(self):
        for mode in (1, 2, 3, 4):
            test, words = self.vector(mode)
            length = test['serial_links'][0]['buffer_bytes']
            position = 6 if mode == 1 else 7 if mode == 2 else 16
            for amount in (0, length):
                broken = words[:]
                broken[position] = amount
                with self.subTest(mode=mode, amount=amount), self.assertRaises(ProtocolError):
                    self.inspect(broken, test, 1, mode)
        test, words = self.vector(5)
        for address in (0x42, 0x6A):
            words[11] = address
            with self.assertRaises(ProtocolError):
                self.inspect(words, test, 1, 5)

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

    def test_invalid_twi_provenance_is_saved_but_cannot_pass_or_restart(self):
        """! @brief 잘못된 RX 원본은 보존하지만 실제 미시작 증명이 없으므로 통과시키지 않습니다. """
        test, raw = self.vector(4)
        raw[17] = test['serial_links'][0]['buffer_bytes']
        observations = []
        devices = []
        proof = list(range(20))
        for role in (1, 2):
            device = mock.Mock()
            device.image = {'role': role}
            def command(opcode, *args, **kwargs):
                return {107: [1, 1, 65537, 0, 0, 0, 0, 0], 110: raw[:],
                        123: proof[:], 99: [test['id'], 0, 0, 0, 0, 0] + [0]*10,
                        100: [0]*20}.get(opcode, [1])
            device.command.side_effect = command
            devices.append(device)
        with (mock.patch.object(fault.time, 'sleep'),
              mock.patch.object(runner, 'prepared_uart_pins'),
              mock.patch.object(runner, 'prepared_bus_pins'),
              mock.patch.object(runner, 'stop_pair', return_value=True) as stop,
              mock.patch.object(runner, 'idle_pins', return_value=True),
              mock.patch.object(runner, 'execute_group') as restart):
            with self.assertRaises(ProtocolError):
                fault.execute(devices, test, 1, 4, mock.Mock(),
                    lambda name, row: observations.append((name, row)), preflight=True)
            stop.assert_called_once()
            restart.assert_not_called()
        self.assertEqual([row['words'] for name, row in observations
                          if name.endswith('/twi-rx-provenance')], [proof, proof])


if __name__ == '__main__':
    unittest.main()
