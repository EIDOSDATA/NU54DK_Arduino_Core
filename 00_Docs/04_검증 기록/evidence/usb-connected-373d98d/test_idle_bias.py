"""! @brief 시작 전 두 UART TX 입력의 유휴 bias와 fail-closed 순서를 검증합니다. """
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core\tests\hil\nu54dk')))
import onboard_start

class IdleBiasTests(unittest.TestCase):
    def execute(self, values, reject_write=False):
        events = []
        def write(address, value):
            events.append(('write', address, value))
            if not reject_write:
                values[address] = value
        target = SimpleNamespace(reset_and_halt=lambda: events.append('halt'), get_state=lambda: SimpleNamespace(name='HALTED'), read32=lambda address: 0x411FD210 if address == 0xE000ED00 else values[address], write32=write, flush=lambda: events.append('flush'), resume=lambda: events.append('resume'))
        class Session:
            def __enter__(self):
                self.target = target
                return self
            def __exit__(self, *_):
                events.append('close')
        streams = {name: SimpleNamespace(reset_input_buffer=lambda: events.append('drain'), reset_output_buffer=lambda: None) for name in ('COM5', 'COM6')}
        self.events = events
        with patch.object(onboard_start.time, 'sleep'):
            return onboard_start.reset_halted_start(streams, 'probe', session_factory=lambda **kwargs: Session())

    def test_only_pull_fields_are_set_before_drain_and_resume(self):
        values = {0x5010A080: 0x2, 0x500D8290: 0x10002}
        result = self.execute(values)
        self.assertEqual(values, {0x5010A080: 0xE, 0x500D8290: 0x1000E})
        self.assertEqual(len(result['dap_uart_idle_bias']), 2)
        self.assertLess(self.events.index('flush'), self.events.index('drain'))
        self.assertLess(self.events.index('drain'), self.events.index('resume'))

    def test_output_pin_is_rejected_before_any_write_or_resume(self):
        with self.assertRaisesRegex(RuntimeError, 'input'):
            self.execute({0x5010A080: 0x2, 0x500D8290: 0x3})
        self.assertFalse(any(isinstance(event, tuple) for event in self.events))
        self.assertNotIn('resume', self.events)

    def test_failed_readback_keeps_cpu_halted(self):
        with self.assertRaisesRegex(RuntimeError, 'readback'):
            self.execute({0x5010A080: 0x2, 0x500D8290: 0x2}, reject_write=True)
        self.assertNotIn('resume', self.events)

if __name__ == '__main__':
    unittest.main()
