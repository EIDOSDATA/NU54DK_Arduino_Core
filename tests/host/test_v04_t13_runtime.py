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

    def test_session_rejects_foreign_wiring_and_time_identity_changes(self):
        uids = ['a' * 32, 'b' * 32]
        images = [{'role': role, 'board_revision': plan.plan()['board_revision'],
                   'core_revision': 'c' * 40} for role in (1, 2)]
        grant = dict(type='v04-t13-s-session', harness='S', catalog_sha256=session.catalog_hash(),
            uid_sha256=[hashlib.sha256(uid.encode()).hexdigest() for uid in uids],
            confirmed_at_unix=1000, expires_at_unix=44200,
            user_wiring_report='S 연결', user_maintain_reply='실행 중 유지')
        for key in ('maintain_harness_until_end', 'notify_before_usb_wiring_switch_changes',
                    'dap_uart_disconnected_both', 'swd_connected_both', 'equal_io_voltage_confirmed',
                    'power_rails_not_joined', 'common_ground_confirmed', 'links_match_catalog',
                    'external_pullups_disconnected', 'extra_outputs_disconnected'):
            grant[key] = True
        session.validate(grant, images, uids, now=2000)
        for key, value in (('harness', 'C'), ('harness', 'U'), ('expires_at_unix', 44201),
                           ('confirmed_at_unix', 2001), ('expires_at_unix', float('nan')),
                           ('links_match_catalog', 1), ('catalog_sha256', '0' * 64),
                           ('user_maintain_reply', '')):
            with self.subTest(key=key, value=value), self.assertRaises(ProtocolError):
                session.validate({**grant, key: value}, images, uids, now=2000)
        with self.assertRaises(ProtocolError):
            session.validate(grant, images, uids, now=44200)
        images[1]['core_revision'] = 'd' * 40
        with self.assertRaises(ProtocolError):
            session.validate(grant, images, uids, now=2000)

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
