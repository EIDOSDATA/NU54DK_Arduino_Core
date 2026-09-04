#!/usr/bin/env python3
"""Unit contract for the M26 no-extra-wiring HIL runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


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


def result_frame(
    temperature: int = 2534,
    reset_cause: int = MODULE.RESET_WATCHDOG,
    supported_cause: int = 0xFFFFFFFF,
) -> bytes:
    frame = bytearray(MODULE.PACKET_SIZE)
    frame[:4] = b"NU26"
    frame[4:8] = bytes((1, 1, 1, 1))
    frame[8:12] = temperature.to_bytes(4, "little", signed=True)
    frame[12:16] = reset_cause.to_bytes(4, "little")
    frame[16:20] = supported_cause.to_bytes(4, "little")
    frame[20:22] = bytes((30, 1))
    for value in frame[:-1]:
        frame[-1] ^= value
    return bytes(frame)


class M26OnboardTests(unittest.TestCase):
    def test_protocol_frames_are_fixed(self) -> None:
        self.assertEqual(len(MODULE.ready_frame()), MODULE.PACKET_SIZE)
        self.assertEqual(len(MODULE.command_frame()), MODULE.PACKET_SIZE)
        self.assertNotEqual(MODULE.ready_frame(), MODULE.command_frame())
        self.assertEqual(len({MODULE.ready_frame(), MODULE.command_frame(),
                              MODULE.reset_ready_frame(), MODULE.result_request_frame()}), 4)

    def test_reset_epoch_retains_bounded_prefix_and_requires_exact_marker(self) -> None:
        marker = MODULE.reset_ready_frame()
        prefix = bytes.fromhex("fe3ede")
        self.assertEqual(
            MODULE.validate_reset_ready({"COM5": b"", "COM6": prefix + marker}, "COM6"),
            prefix,
        )
        for selected, other in (
            (MODULE.ready_frame(), b""),
            (b"x" * (MODULE.MAX_RESET_PREFIX + 1) + marker, b""),
            (marker + b"x", b""),
            (marker + marker, b""),
            (marker, b"x"),
            (result_frame(), b""),
            (b"", b""),
        ):
            with self.subTest(selected=selected.hex(), other=other.hex()):
                with self.assertRaises(MODULE.M26HilFailure):
                    MODULE.validate_reset_ready({"COM5": other, "COM6": selected}, "COM6")

    def test_reset_epoch_collects_split_marker_without_dropping_prefix(self) -> None:
        class Chunks:
            def __init__(self, chunks):
                self.chunks = list(chunks)

            @property
            def in_waiting(self):
                return len(self.chunks[0]) if self.chunks else 0

            def read(self, size):
                return self.chunks.pop(0)

        marker = MODULE.reset_ready_frame()
        ports = {"COM5": Chunks([]), "COM6": Chunks([b"\xff", marker[:7], marker[7:]])}
        with patch.object(MODULE.time, "sleep"):
            prefix, received = MODULE.collect_reset_ready(ports, "COM6", 1.0)
        self.assertEqual(prefix, b"\xff")
        self.assertEqual(received["COM6"], b"\xff" + marker)

    def test_reset_prefix_is_never_accepted_in_result_phase(self) -> None:
        with self.assertRaises(MODULE.M26HilFailure):
            MODULE.validate_result_frame(b"\xff" + result_frame())

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
                "reset_cause": MODULE.RESET_WATCHDOG,
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

    def test_result_rejects_non_watchdog_and_unsupported_reset_causes(self) -> None:
        # Firmware PASS flags cannot substitute for the actual reset-cause bits.
        for cause, supported in ((4, 0xFFFFFFFF), (16, 4), (20, 16)):
            with self.subTest(cause=cause, supported=supported):
                with self.assertRaises(MODULE.M26HilFailure):
                    MODULE.validate_result_frame(
                        result_frame(reset_cause=cause, supported_cause=supported)
                    )

    def test_observed_watchdog_packets_validate_without_promoting_hil(self) -> None:
        # Diagnostic capture lacked READY; valid packets alone are not a full HIL PASS.
        armed = bytes.fromhex(
            "415232360101010101090b0000000000001e000000000000000000000000000a"
        )
        # The capture contained three inter-frame bytes. Do not silently strip
        # those bytes to promote the diagnostic transcript to a formal HIL PASS.
        result = bytes.fromhex(
            "4e55323601010101090b000010000000b30900001e01000000000000000000a8"
        )
        self.assertEqual(
            MODULE.validate_armed_frame(armed)["temperature_centi_celsius"], 2825
        )
        with self.assertRaises(MODULE.M26HilFailure):
            MODULE.validate_armed_frame(armed + bytes.fromhex("fe3ede"))
        self.assertEqual(
            MODULE.validate_result_frame(result)["reset_cause"], MODULE.RESET_WATCHDOG
        )

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
