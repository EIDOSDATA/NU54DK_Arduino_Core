#!/usr/bin/env python3
"""Unit contract for the M25 no-extra-wiring HIL runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


SCRIPT = Path(__file__).with_name("m25_onboard.py")
SPEC = importlib.util.spec_from_file_location("nu54_m25_onboard_hil", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def result_frame(ticks: int = 2000, sample: int = 1234) -> bytes:
    frame = bytearray(MODULE.PACKET_SIZE)
    frame[:4] = b"NU25"
    frame[4:8] = bytes((1, 1, 1, 1))
    frame[8:12] = ticks.to_bytes(4, "little")
    frame[12:14] = sample.to_bytes(2, "little", signed=True)
    frame[14] = 1
    for value in frame[:-1]:
        frame[-1] ^= value
    return bytes(frame)


class M25OnboardTests(unittest.TestCase):
    def test_protocol_frames_are_fixed(self) -> None:
        self.assertEqual(len(MODULE.ready_frame()), MODULE.PACKET_SIZE)
        self.assertEqual(len(MODULE.command_frame()), MODULE.PACKET_SIZE)
        self.assertNotEqual(MODULE.ready_frame(), MODULE.command_frame())

    def test_result_requires_both_physical_checks(self) -> None:
        self.assertEqual(
            MODULE.validate_result_frame(result_frame()),
            {"timer_ticks": 2000, "vdd_raw": 1234, "stream_linked": 1},
        )
        invalid = bytearray(result_frame())
        invalid[6] = 0
        invalid[-1] = 0
        for value in invalid[:-1]:
            invalid[-1] ^= value
        with self.assertRaises(MODULE.M25HilFailure):
            MODULE.validate_result_frame(bytes(invalid))

    def test_probe_requires_exactly_two_vcom_ports(self) -> None:
        ports = [
            SimpleNamespace(device="COM5", serial_number="probe"),
            SimpleNamespace(device="COM6", serial_number="PROBE"),
        ]
        self.assertEqual(
            MODULE.matching_port_names(ports, "Probe"), ["COM5", "COM6"]
        )
        with self.assertRaises(MODULE.M25HilFailure):
            MODULE.matching_port_names(ports[:1], "probe")

    def test_exact_port_rejects_noise(self) -> None:
        expected = MODULE.ready_frame()
        self.assertEqual(
            MODULE.choose_exact_port({"COM5": expected, "COM6": b""}, expected),
            "COM5",
        )
        with self.assertRaises(MODULE.M25HilFailure):
            MODULE.choose_exact_port({"COM5": expected, "COM6": b"x"}, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
