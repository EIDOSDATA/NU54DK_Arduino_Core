"""Host tests for the M24 onboard TWIM HIL protocol."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


MODULE_PATH = Path(__file__).with_name("m24_twim_onboard.py")
SPEC = importlib.util.spec_from_file_location("m24_twim_onboard", MODULE_PATH)
assert SPEC and SPEC.loader
HIL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HIL)


class M24TwimOnboardTests(unittest.TestCase):
    """Lock the no-extra-wiring PMIC protocol and fail-closed parsing."""

    def test_ready_and_command_frames_are_unique(self) -> None:
        self.assertEqual(len({HIL.ready_frame(i) for i in HIL.INSTANCES}), 3)
        self.assertEqual(len({HIL.command_frame(i) for i in HIL.INSTANCES}), 3)
        self.assertTrue(
            all(len(HIL.ready_frame(i)) == HIL.PACKET_SIZE for i in HIL.INSTANCES)
        )

    def test_result_frame_requires_exact_read_only_identity(self) -> None:
        frame = bytearray(HIL.PACKET_SIZE)
        frame[:4] = b"NUTW"
        frame[4:11] = bytes((20, 0, 0x6A, 0x0C, 0x41, 0x41, 1))
        for value in frame[:-1]:
            frame[-1] ^= value
        self.assertEqual(
            HIL.validate_result_frame(bytes(frame), 20),
            {"address": 0x6A, "register": 0x0C, "value": 0x41},
        )
        frame[8] = 0x40
        with self.assertRaises(HIL.TwimHilFailure):
            HIL.validate_result_frame(bytes(frame), 20)

    def test_probe_must_have_exactly_two_ports(self) -> None:
        ports = [
            SimpleNamespace(device="COM5", serial_number="probe"),
            SimpleNamespace(device="COM6", serial_number="probe"),
            SimpleNamespace(device="COM7", serial_number="other"),
        ]
        self.assertEqual(HIL.matching_port_names(ports, "PROBE"), ["COM5", "COM6"])
        with self.assertRaises(HIL.TwimHilFailure):
            HIL.matching_port_names(ports[:1], "probe")

    def test_exact_port_rejects_extra_bytes(self) -> None:
        expected = HIL.ready_frame(21)
        self.assertEqual(
            HIL.choose_exact_port({"COM5": expected, "COM6": b""}, expected),
            "COM5",
        )
        with self.assertRaises(HIL.TwimHilFailure):
            HIL.choose_exact_port({"COM5": expected, "COM6": b"x"}, expected)


if __name__ == "__main__":
    unittest.main()
