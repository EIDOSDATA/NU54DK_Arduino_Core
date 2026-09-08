"""! @brief 공급 생략·오류 순서·STOP 실패를 정상 복구 성공으로 오인하지 않게 검사합니다. """
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
from v04_protocol import ProtocolError
import v04_t13_cases as cases
import v04_t13_stream_fault as fault
import v04_t13_run as runner


class StreamFaultTests(unittest.TestCase):
    def test_pdm_peer_secondary_cs_end_keeps_error_and_rejects_other_faults(self):
        words = [3, 0, 6, 0, 0, 1, 0, 0, 2166136261, 2147483647,
                 2147483648, 0, 0, 0, 1, 0, 0, 0, 1, 1]
        self.assertTrue(fault.inspect_pdm_peer(words)['cs_release_transfer_complete'])
        self.assertFalse(fault.inspect_pdm_peer(words)['normal_stream_pass'])
        for index, value in ((0, 2), (1, 2), (2, 15), (3, 1), (4, 1), (5, 0),
                             (6, 1), (14, 0), (18, 0), (19, 0)):
            broken = words[:]
            broken[index] = value
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                fault.inspect_pdm_peer(broken)
        words[2] = 0
        self.assertFalse(fault.inspect_pdm_peer(words)['cs_release_transfer_complete'])
        words[1] = 1
        self.assertEqual(fault.inspect_pdm_peer(words)['raw_active_before_host_stop'], 1)

    def vector(self, mode, role=1, instance=20):
        test = next(row for row in cases.cases() if
                    (row['i2s'] and not row['serial_links'] if mode == 1 else
                     row['pdm_instance'] == instance and not row['serial_links']))
        index = 2 if mode == 1 else 3
        words = [mode, index, instance, 1, 4, 6, 100, 3, 0 if mode == 1 else (-139 & 0xFFFFFFFF),
                 200, 5, 6, 1, 2, 2, 0, 0, 0, role, 1000000]
        stream = [index, 0, 8 if mode == 1 else 11, 3, 5, 6] + [0]*12 + [1, 1]
        return test, words, stream

    def test_fixed_target_helper_skips_once_and_keeps_first_error(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory)/'stream_fault.exe'
            command = compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT/'tests/zephyr/v04_t13_hil/src'),
                str(ROOT/'tests/host/v04_t13_stream_fault_main.cpp'), '-o', str(exe)]
            built = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stdout+built.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stdout+executed.stderr)

    def test_allowed_stream_roles_require_observed_error_and_finished_stop(self):
        for mode, role, instance in ((1, 1, 20), (1, 2, 20), (2, 1, 20), (2, 1, 21)):
            test, words, stream = self.vector(mode, role, instance)
            with self.subTest(mode=mode, role=role, instance=instance):
                self.assertEqual(fault.inspect(words, stream, test, role, mode)['instance'], instance)
                words[6], words[9] = 0xFFFFFFF0, 84
                self.assertEqual(fault.inspect(words, stream, test, role, mode)['event_after_skip_us'], 100)
        test, words, stream = self.vector(2)
        with self.assertRaises(ProtocolError):
            fault.inspect(words, stream, test, 2, 2)

    def test_missing_skip_bad_guard_prior_fault_wrong_error_and_no_stop_are_rejected(self):
        for mode in (1, 2):
            test, words, stream = self.vector(mode)
            for index, value in ((0, 0), (3, 0), (4, 3), (5, 4), (7, 0xFFFFFFFF), (8, 9),
                                 (9, 100), (10, 3), (12, 0), (13, 4), (14, 0), (16, 1), (19, 0)):
                broken = words[:]
                broken[index] = value
                with self.subTest(mode=mode, index=index), self.assertRaises(ProtocolError):
                    fault.inspect(broken, stream, test, 1, mode)
            for index, value in ((1, 1), (2, 0), (3, 4), (4, 4), (18, 0), (19, 0)):
                broken = stream[:]
                broken[index] = value
                with self.subTest(mode=mode, stream=index), self.assertRaises(ProtocolError):
                    fault.inspect(words, broken, test, 1, mode)

    def test_serial_concurrent_and_unsupported_modes_are_rejected(self):
        for identifier, mode in ((2, 1), (106, 1), (108, 2), (30, 0), (28, 1)):
            test = next(row for row in cases.cases() if row['id'] == identifier)
            with self.subTest(identifier=identifier, mode=mode), self.assertRaises(ProtocolError):
                fault.validate_selection(test, 1, mode)

    def test_cleanup_and_both_peer_raw_precede_judgement_and_nonce_restart(self):
        test, valid, stream = self.vector(1)
        for corrupt, stop_ok in ((False, True), (True, True), (False, False)):
            raw = valid[:]
            if corrupt:
                raw[12] = 0
            devices, observations = [], []
            for role in (1, 2):
                device = mock.Mock()
                device.image = {'role': role}
                def command(opcode, *args, **kwargs):
                    if opcode == 107:
                        return [1, 1, 65537, 0, 0, 0, 0, 0]
                    if opcode == 115:
                        return raw[:]
                    if opcode == 104:
                        return stream[:]
                    if opcode == 99:
                        return [test['id'], 0, 0, 0, 0, 0] + [0]*10
                    return [1]
                device.command.side_effect = command
                devices.append(device)
            with (self.subTest(corrupt=corrupt, stop_ok=stop_ok), mock.patch.object(fault.time, 'sleep'),
                  mock.patch.object(runner, 'stop_pair', return_value=stop_ok) as stop,
                  mock.patch.object(runner, 'idle_pins', return_value=True),
                  mock.patch.object(runner, 'execute_group') as restart):
                run = lambda: fault.execute(devices, test, 1, 1, mock.Mock(),
                    lambda label, row: observations.append((label, row)), preflight=True)
                if corrupt or not stop_ok:
                    with self.assertRaises(ProtocolError):
                        run()
                    restart.assert_not_called()
                else:
                    run()
                    self.assertEqual(restart.call_args.kwargs['seed'], observations[0][1]['seed'] ^ 0x9E3779B9)
                    self.assertFalse(observations[-1][1]['planned_recovery_pass'])
                stop.assert_called_once()
                self.assertTrue(any(label.endswith('/final/role2/stream') for label, _ in observations))


if __name__ == '__main__':
    unittest.main()
