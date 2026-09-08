"""! @brief UART 진단 이력의 부분 게시·wrap·오류와 완료 데이터 해석을 검사합니다. """
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/hil/nu54dk'))
from v04_protocol import ProtocolError
import v04_t13_uart_trace as trace


class UartTraceTests(unittest.TestCase):
    def records(self, count):
        words = [0] * (trace.DEPTH * trace.WORDS)
        for sequence in range(1, count + 1):
            offset = (sequence - 1) % trace.DEPTH * trace.WORDS
            row = [0] * trace.WORDS
            row[:7] = [sequence, (0xFFFFFFF0 + sequence * 8) & 0xFFFFFFFF, 6, 1,
                       0x20004000, 1024, 0x12345678]
            words[offset:offset + trace.WORDS] = row
        return words

    def test_wrapped_history_keeps_chronology_and_callback_payload(self):
        rows = trace.decode(70, self.records(70))
        self.assertEqual([row['sequence'] for row in rows], list(range(7, 71)))
        self.assertTrue(all(row['event_type'] == 1 and row['first_word'] == 0x12345678 for row in rows))
        self.assertTrue(all(not row['physical_pass_added'] for row in rows))

    def test_unpublished_and_stale_records_are_rejected(self):
        for position, value in ((0, 0), (0, 2), (2, 8), (3, 8), (3, 257)):
            words = self.records(1)
            words[position] = value
            with self.subTest(position=position, value=value), self.assertRaises(ProtocolError):
                trace.decode(1, words)
        with self.assertRaises(ProtocolError):
            trace.decode(0, self.records(1))
        with self.assertRaises(ProtocolError):
            trace.decode(1, self.records(1)[:-1])

    def test_error_mask_is_distinct_from_valid_rx_done(self):
        words = self.records(1)
        words[3] = 2 | (14 << 8)
        row = trace.decode(1, words)[0]
        self.assertEqual(row['event_type'], 2)
        self.assertEqual(row['reported_error_mask'], 14)
        self.assertFalse(row['physical_pass_added'])
        self.assertEqual(trace.decode(0, [0] * (trace.DEPTH * trace.WORDS)), [])
