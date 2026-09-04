#!/usr/bin/env python3
"""Unit contract for the M26 no-extra-wiring HIL runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


SCRIPT = Path(__file__).with_name("m26_onboard.py")
SPEC = importlib.util.spec_from_file_location("nu54_m26_onboard_hil", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def armed_frame(temperature: int = 2534) -> bytes:
    frame = bytearray(MODULE.PACKET_SIZE)
    frame[:4] = b"AR26"
    frame[4:9] = bytes((1, 1, 1, 1, 1))
    frame[9:13] = temperature.to_bytes(4, "little", signed=True)
    frame[13:17] = (0).to_bytes(4, "little", signed=True)
    frame[17] = 30
    for value in frame[:-1]:
        frame[-1] ^= value
    return bytes(frame)


def result_frame(temperature: int = 2534) -> bytes:
    frame = bytearray(MODULE.PACKET_SIZE)
    frame[:4] = b"NU26"
    frame[4:8] = bytes((1, 1, 1, 1))
    frame[8:12] = temperature.to_bytes(4, "little", signed=True)
    frame[12:16] = (4).to_bytes(4, "little")
    frame[16:20] = (0xFFFFFFFF).to_bytes(4, "little")
    frame[20:22] = bytes((30, 1))
    for value in frame[:-1]:
        frame[-1] ^= value
    return bytes(frame)


class M26OnboardTests(unittest.TestCase):
    def test_protocol_frames_are_fixed(self) -> None:
        self.assertEqual(len(MODULE.ready_frame()), MODULE.PACKET_SIZE)
        self.assertEqual(len(MODULE.command_frame()), MODULE.PACKET_SIZE)
        self.assertNotEqual(MODULE.ready_frame(), MODULE.command_frame())

    def test_armed_frame_requires_temp_and_wdt30_lifecycle(self) -> None:
        self.assertEqual(
            MODULE.validate_armed_frame(armed_frame()),
            {"temperature_centi_celsius": 2534, "watchdog_instance": 30},
        )
        invalid = bytearray(armed_frame())
        invalid[8] = 0
        invalid[-1] = 0
        for value in invalid[:-1]:
            invalid[-1] ^= value
        with self.assertRaises(MODULE.M26HilFailure):
            MODULE.validate_armed_frame(bytes(invalid))

    def test_result_requires_reset_cause_and_retained_temp(self) -> None:
        self.assertEqual(
            MODULE.validate_result_frame(result_frame()),
            {
                "temperature_centi_celsius": 2534,
                "watchdog_instance": 30,
                "reset_cause": 4,
                "supported_reset_cause": 0xFFFFFFFF,
            },
        )
        invalid = bytearray(result_frame())
        invalid[12:16] = bytes(4)
        invalid[-1] = 0
        for value in invalid[:-1]:
            invalid[-1] ^= value
        with self.assertRaises(MODULE.M26HilFailure):
            MODULE.validate_result_frame(bytes(invalid))

    def test_probe_requires_exactly_two_vcom_ports(self) -> None:
        ports = [
            SimpleNamespace(device="COM5", serial_number="probe"),
            SimpleNamespace(device="COM6", serial_number="PROBE"),
        ]
        self.assertEqual(
            MODULE.matching_port_names(ports, "Probe"), ["COM5", "COM6"]
        )
        with self.assertRaises(MODULE.M26HilFailure):
            MODULE.matching_port_names(ports[:1], "probe")

    def test_exact_frame_rejects_noise(self) -> None:
        expected = MODULE.ready_frame()
        self.assertEqual(
            MODULE.choose_exact_frame({"COM5": expected, "COM6": b""}, expected),
            "COM5",
        )
        with self.assertRaises(MODULE.M26HilFailure):
            MODULE.choose_exact_frame({"COM5": expected, "COM6": b"x"}, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
