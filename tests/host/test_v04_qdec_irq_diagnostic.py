"""! @brief IRQ 숫자 실패와 이벤트 누락·큐 오류·혼합 읽기를 구별합니다. """
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/hil/nu54dk'))
from v04_protocol import ProtocolError
import v04_qdec_irq_diagnostic as diagnostic


class QdecIrqDiagnosticTests(unittest.TestCase):
    def test_vectors_cover_both_instances_and_irq_modes(self):
        rows = list(diagnostic.vectors())
        self.assertEqual(len(set(rows)), 40)
        for instance in (20, 21):
            for strategy in (7, 8):
                self.assertEqual(sum(i == instance and s == strategy for i, _, s in rows), 10)

    def test_sample_irq_does_not_repair_accumulator_mismatch(self):
        gpio = [0, 400, 0, 400, 100] + [0] * 15
        irq = [400, 0, 16000, 0, 0, 0, 0, 110, 0]
        hardware = [0] * 16
        hardware[5], hardware[7] = 399, 30000
        pins = [0] * 8 + [16, 0, 5, 0, 1]
        self.assertEqual(diagnostic.verify_irq(7, gpio, irq, hardware, pins), [399, 0])
        for index, value in ((0, 399), (1, 1), (6, 1), (7, 256), (8, 1)):
            bad = irq.copy()
            bad[index] = value
            with self.assertRaises(ProtocolError):
                diagnostic.verify_irq(7, gpio, bad, hardware, pins)

    def test_report_irq_rejects_explicit_reads_and_wrong_hardware_mode(self):
        gpio = [0, 400, 0, 400, 100] + [0] * 15
        irq = [0, 0, 0, 400, 0, 1600, 0, 110, 0]
        hardware = [0] * 16
        hardware[5] = 400
        pins = [0] * 8 + [16, 1, 6, 0, 1]
        self.assertEqual(diagnostic.verify_irq(8, gpio, irq, hardware, pins), [400, 0])
        hardware[7] = 1
        with self.assertRaises(ProtocolError):
            diagnostic.verify_irq(8, gpio, irq, hardware, pins)
        hardware[7] = 0
        pins[9] = 0
        with self.assertRaises(ProtocolError):
            diagnostic.verify_irq(8, gpio, irq, hardware, pins)


if __name__ == '__main__':
    unittest.main()
