"""합성 신호 runner의 vector, oracle, 실행 안전 gate를 검사합니다."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
import v04_signal as signal
import v04_signal_run as runner
from v04_protocol import ProtocolError


class SignalTests(unittest.TestCase):
    def test_vector_counts_and_boundaries(self):
        self.assertEqual(len(list(signal.vectors("analog"))), 48)
        self.assertEqual(len(list(signal.vectors("qdec"))), 48)
        self.assertEqual(len(list(signal.vectors("i2s"))), 96)
        self.assertEqual(len(list(signal.vectors("pdm"))), 96)
        self.assertIn((48000, 32, 0, 256, 2, 0x13579BDF),
                      signal.vectors("i2s"))
        self.assertIn((21, 1024, 75, 1, 1, 2), signal.vectors("pdm"))

    def test_i2s_masks_are_width_and_channel_explicit(self):
        _, stereo16 = signal.i2s_expected(1, 2, 16, 0)
        _, left16 = signal.i2s_expected(1, 2, 16, 1)
        _, stereo32 = signal.i2s_expected(1, 2, 32, 0)
        self.assertEqual(stereo16, 0xFFFFFFFF)
        self.assertEqual(left16, 0xFFFF)
        self.assertEqual(stereo32, 0xFFFFFFFF)

    def test_pdm_runner_requires_channel_and_density_discrimination(self):
        source = (ROOT / "tests/hil/nu54dk/v04_signal.py").read_text(
            encoding="utf-8")
        self.assertIn("PDM stereo channels are not independently distinguishable", source)
        self.assertIn("PDM density ordering mismatch", source)

    def test_pdm_firmware_reports_the_released_dma_length(self):
        source = (ROOT / "cores/arduino/StreamFabric.cpp").read_text(
            encoding="utf-8")
        self.assertIn("samples = slot.bytes / sizeof(std::int16_t)", source)
        self.assertIn("event->buffer_released, samples, 0", source)

    def test_default_cli_is_preflight_and_execution_needs_files(self):
        base = ["--dut", "a" * 32, "--peer", "b" * 32,
                "--build-root", "unused", "--pyocd", "unused",
                "--fixture", "401"]
        self.assertFalse(runner.arguments(base).execute_fixture)
        with self.assertRaises(ProtocolError):
            runner.arguments(base + ["--execute-fixture"])

    def test_signal_campaign_is_bounded(self):
        base = ["--dut", "a" * 32, "--peer", "b" * 32,
                "--build-root", "unused", "--pyocd", "unused",
                "--fixture", "401"]
        self.assertEqual(runner.arguments(base + ["--repetitions", "100"]).repetitions,
                         100)
        with self.assertRaises(ProtocolError):
            runner.arguments(base + ["--duration-seconds", "7201"])

    def test_invalid_vectors_fail_closed(self):
        with self.assertRaises(ProtocolError):
            list(signal.vectors("unknown"))
        with self.assertRaises(ProtocolError):
            signal.arguments_for("analog", tuple(range(9)))


if __name__ == "__main__":
    unittest.main()
