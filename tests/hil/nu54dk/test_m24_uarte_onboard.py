#!/usr/bin/env python3
"""Unit contract for the M24 no-extra-wiring UARTE HIL runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


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
                "--no-config",
                "--no-reset",
                "-O",
                "resume_on_disconnect=false",
                "-O",
                "auto_unlock=false",
                "--erase",
                "sector",
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

    def test_all_onboard_flash_runners_disable_automatic_mass_erase(self) -> None:
        for name in ("m24_uarte_onboard", "m24_twim_onboard", "m25_onboard", "m26_onboard"):
            with self.subTest(runner=name):
                specification = importlib.util.spec_from_file_location(
                    f"test_safe_{name}", SCRIPT.with_name(f"{name}.py")
                )
                assert specification and specification.loader
                module = importlib.util.module_from_spec(specification)
                specification.loader.exec_module(module)
                with patch.object(
                    module.subprocess, "run",
                    return_value=SimpleNamespace(returncode=0, stdout=b"flash passed"),
                ) as command:
                    module.flash_image(Path("pyocd.exe"), "exact-uid", Path("image.hex"), 120)
                arguments = command.call_args.args[0]
                self.assertEqual(arguments[arguments.index("--uid") + 1], "exact-uid")
                self.assertEqual(arguments[arguments.index("--erase") + 1], "sector")
                self.assertIn("auto_unlock=false", arguments)
                self.assertIn("--no-config", arguments)
                self.assertIn("--no-reset", arguments)
                self.assertIn("resume_on_disconnect=false", arguments)
                self.assertNotIn("chip", arguments)

    def test_controlled_start_orders_halt_drain_and_resume(self) -> None:
        import onboard_start
        events = []
        target = SimpleNamespace(
            reset_and_halt=lambda: events.append("halt"),
            get_state=lambda: SimpleNamespace(name="HALTED"),
            read32=lambda address: 0x411FD210,
            resume=lambda: events.append("resume"),
        )

        class Session:
            def __enter__(self):
                self.target = target
                return self

            def __exit__(self, *args):
                events.append("close")

        ports = {name: SimpleNamespace(
            reset_input_buffer=lambda: events.append("drain-in"),
            reset_output_buffer=lambda: events.append("drain-out"),
        ) for name in ("COM5", "COM6")}
        with patch.object(onboard_start.time, "sleep"):
            factory = unittest.mock.Mock(return_value=Session())
            result = onboard_start.reset_halted_start(ports, "probe", session_factory=factory)
        self.assertEqual(events, ["halt", "drain-in", "drain-out", "drain-in", "drain-out", "resume", "close"])
        self.assertEqual(result["method"], "reset-halt-drain-resume")
        self.assertFalse(factory.call_args.kwargs["options"]["auto_unlock"])
        self.assertFalse(factory.call_args.kwargs["options"]["resume_on_disconnect"])
        events.clear()
        target.get_state = lambda: SimpleNamespace(name="RUNNING")
        with self.assertRaises(RuntimeError):
            onboard_start.reset_halted_start(ports, "probe", session_factory=lambda **kw: Session())
        self.assertEqual(events, ["halt", "close"])

    def test_single_result_collectors_reject_late_extra_bytes(self) -> None:
        class Chunks:
            def __init__(self, chunks):
                self.chunks = list(chunks)

            @property
            def in_waiting(self):
                return len(self.chunks[0]) if self.chunks else 0

            def read(self, size):
                return self.chunks.pop(0)

        for name, exception_name in (("m24_twim_onboard", "TwimHilFailure"),
                                     ("m25_onboard", "M25HilFailure"),
                                     ("m26_onboard", "M26HilFailure")):
            with self.subTest(runner=name):
                specification = importlib.util.spec_from_file_location(
                    f"test_quiet_{name}", SCRIPT.with_name(f"{name}.py")
                )
                module = importlib.util.module_from_spec(specification)
                specification.loader.exec_module(module)
                streams = {"COM5": Chunks([]), "COM6": Chunks([bytes(32), b"x"])}
                with patch.object(module.time, "sleep"):
                    with self.assertRaises(getattr(module, exception_name)):
                        if name == "m26_onboard":
                            module.collect_packet(streams, 1.0)
                        else:
                            module.collect_frame(streams, None, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
