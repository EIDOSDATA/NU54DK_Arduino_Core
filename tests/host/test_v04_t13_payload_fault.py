"""! @brief 첫 payload 오류를 원본으로 재현하며 진단을 정상 통과로 세지 않습니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_oracle as oracle
import v04_t13_run as runner
from v04_protocol import ProtocolError


class PayloadFaultTests(unittest.TestCase):
    def vector(self):
        # @brief seed0의8byte [0,16,32,112,64,176,224,144] 중 offset3의 bit0 오류입니다.
        return [1, 2, 21, 1, 0, 3, 113, 112, 0, 0, 0, 0, 0x20001000, 8, 1, 123,
                0x71201000, 0xE0B04071, 0x70201000, 0xE0B04070]

    def test_first_error_has_reproducible_byte_xor_and_is_never_normal_pass(self):
        result = oracle.serial_data_fault(self.vector())
        self.assertEqual((result['offset'], result['actual'], result['expected'], result['xor']),
                         (3, 113, 112, 1))
        self.assertFalse(result['normal_pass'])
        self.assertEqual(oracle.serial_data_fault([0]*20),
                         {'payload_fault_recorded': False, 'normal_pass': False})

    def test_stale_frame_bad_window_pointer_and_guard_are_rejected(self):
        for index in (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 17, 18, 19):
            broken = self.vector()
            broken[index] ^= {2: 64, 3: 2, 8: 128}.get(index, 1)
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                oracle.serial_data_fault(broken)

    def test_raw_capture_and_analysis_precede_stop(self):
        test = next(row for row in cases.cases() if row['id'] == 8)
        device = mock.Mock()
        device.image = {'role': 1}
        events = []
        def command(opcode, *args, **kwargs):
            events.append(opcode)
            return {99: [8]+[0]*15, 100: [0]*20, 124: self.vector(),
                    107: [1, 0, 0, 0, 0, 0, 0, 0], 102: [1, 0]}[opcode]
        device.command.side_effect = command
        rows = []
        append = lambda name, row: rows.append({'id': name, **row})
        runner.failure_snapshots([device], test, append, 'test')
        runner.stop_pair([device], append, 'cleanup')
        self.assertLess(events.index(124), events.index(102))
        self.assertEqual(next(row for row in rows if row.get('status') == 'diagnostic')['xor'], 1)


if __name__ == '__main__':
    unittest.main()
