#!/usr/bin/env python3
"""Unit contract for the M24 no-extra-wiring UARTE HIL runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("m24_uarte_onboard.py")
SPEC = importlib.util.spec_from_file_location("nu54_m24_uarte_hil", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Port:
    def __init__(self, device: str, serial_number: str | None) -> None:
        self.device = device
        self.serial_number = serial_number


class M24UarteOnboardTests(unittest.TestCase):
    def test_selected_probe_requires_exactly_two_vcom_ports(self) -> None:
        records = [Port("COM7", "ABC"), Port("COM8", "abc"), Port("COM9", "other")]
        self.assertEqual(MODULE.matching_port_names(records, "AbC"), ["COM7", "COM8"])
        with self.assertRaisesRegex(MODULE.UarteHilFailure, "exactly two"):
            MODULE.matching_port_names(records[:1], "ABC")

    def test_response_must_be_exact_unique_and_other_port_silent(self) -> None:
        expected = bytes(range(MODULE.PACKET_SIZE))
        self.assertEqual(
            MODULE.choose_unique_response({"COM7": expected, "COM8": b""}, expected),
            "COM7",
        )
        with self.assertRaisesRegex(MODULE.UarteHilFailure, "exactly one"):
            MODULE.choose_unique_response({"COM7": expected, "COM8": expected}, expected)
        with self.assertRaisesRegex(MODULE.UarteHilFailure, "unexpected bytes"):
            MODULE.choose_unique_response({"COM7": expected, "COM8": b"x"}, expected)

    def test_pyocd_command_is_exact_and_non_destructive(self) -> None:
        command = MODULE.pyocd_command(Path("pyocd.exe"), "probe", Path("image.hex"))
        self.assertEqual(
            command,
            [
                "pyocd.exe",
                "load",
                "--target",
                "nrf54l",
                "--uid",
                "probe",
                "--frequency",
                "1m",
                "image.hex",
            ],
        )
        joined = " ".join(command).casefold()
        self.assertNotIn("recover", joined)
        self.assertNotIn("mass", joined)

    def test_ready_frame_is_fixed_per_instance(self) -> None:
        self.assertEqual(len(MODULE.ready_frame(20)), MODULE.PACKET_SIZE)
        self.assertNotEqual(MODULE.ready_frame(20), MODULE.ready_frame(21))


if __name__ == "__main__":
    unittest.main(verbosity=2)
