"""Independent UART oracle and vector/error boundary tests (no hardware)."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hil/nu54dk"))
import v04_uart as uart
from v04_protocol import ProtocolError


class UartTests(unittest.TestCase):
    def test_oracle(self):
        self.assertEqual(uart.payload(0, 8), bytes([0, 37, 75, 110, 150, 187, 221, 0]))
        for seed in (0, 1, 0x12345678, 0xffffffff):
            data = uart.payload(seed, 2048)
            self.assertEqual(len(data), 2048)
            self.assertNotEqual(data, uart.payload(seed ^ 0x5a, 2048))
            self.assertNotEqual(data[:1024], data[1024:])
        for args in ((-1, 1), (0, 0), (0, 2049), (True, 1)):
            with self.assertRaises(ProtocolError): uart.payload(*args)

    def test_vectors(self):
        vectors = list(uart.vectors())
        self.assertEqual(len(vectors), 64)
        self.assertEqual(len(set(vectors)), 64)
        self.assertIn((1000000, 1, 1, 1024, 2), vectors)

    def test_continuous_mode_is_explicit_and_bounded(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "cores/arduino/UarteFabric.cpp").read_text(encoding="utf-8")
        header = (root / "cores/arduino/nucode/SerialFabric.h").read_text(encoding="utf-8")
        self.assertIn("bool continuous_receive{false}", header)
        self.assertIn("!second_valid || first_size < 32U || second_size < 32U", source)
        self.assertIn("NRFX_UARTE_RX_ENABLE_CONT", source)
        self.assertIn("NRF_UARTE_EVENT_RXSTARTED", source)

    def test_dma_state_fail_closed(self):
        uart.check_status([1, 1, 0, 1, 3, 0], 1)
        uart.check_status([2, 1, 0, 3, 3, 3], 2)
        for reply in ([2, 1, 0, 3, 2, 3], [2, 1, 64, 3, 3, 3], [2, 2, 0, 3, 3, 3], [1, 1, 0, 1, 3, 0], []):
            with self.assertRaises(ProtocolError): uart.check_status(reply, 2)

    def test_ambiguous_noisy_and_truncated_response_rejected(self):
        class Port:
            def __init__(self, data): self.data = data
            @property
            def in_waiting(self): return len(self.data)
            def read(self, size):
                data, self.data = self.data[:size], self.data[size:]
                return data
        with patch.object(uart.time, "sleep", return_value=None):
            self.assertEqual(uart.collect({"A": Port(b"abc"), "B": Port(b"")}, b"abc", .001), "A")
            for a, b in ((b"abc", b"abc"), (b"abc", b"noise"), (b"ab", b""), (b"abcd", b"")):
                with self.assertRaises(ProtocolError): uart.collect({"A": Port(a), "B": Port(b)}, b"abc", .001)


if __name__ == "__main__": unittest.main()
