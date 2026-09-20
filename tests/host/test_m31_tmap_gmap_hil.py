#!/usr/bin/env python3
"""W03-10 TMAP/GMAP 공개 Serial HIL 계약을 검사합니다."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY / "tests/hil/nu54dk/m31_tmap_gmap_run.py"
SPEC = importlib.util.spec_from_file_location("m31_tmap_gmap_run", RUNNER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TmapGmapHilContractTest(unittest.TestCase):
    """공개 예제 8역할과 fail-closed parser 계약을 고정합니다."""

    def test_four_scenarios_cover_eight_distinct_roles(self) -> None:
        pairs = {
            (scenario.profile, scenario.source_role)
            for scenario in MODULE.SCENARIOS.values()
        } | {
            (scenario.profile, scenario.sink_role)
            for scenario in MODULE.SCENARIOS.values()
        }
        self.assertEqual(len(MODULE.SCENARIOS), 4)
        self.assertEqual(len(pairs), 8)

    def test_public_examples_publish_the_hil_contract_without_internal_api(self) -> None:
        for scenario in MODULE.SCENARIOS.values():
            for root, ready in ((scenario.source_root, scenario.source_ready),
                                (scenario.sink_root, scenario.sink_ready)):
                sketch = next(root.glob("*.ino"))
                text = sketch.read_text(encoding="utf-8")
                self.assertIn(ready, text)
                self.assertIn(scenario.quality_negative, text)
                self.assertIn("command == 'q'", text)
                self.assertNotIn("#include <zephyr/", text)
                self.assertNotIn("bt_", text)
                self.assertNotIn("M31", text)

    def test_all_scenarios_accept_complete_public_transcripts(self) -> None:
        for name, scenario in MODULE.SCENARIOS.items():
            with self.subTest(name=name):
                observation = MODULE.Observation(scenario)
                observation.ingest("source", scenario.source_ready)
                observation.ingest("sink", scenario.sink_ready)
                observation.ingest("source", scenario.source_streaming)
                if scenario.transport == "unicast":
                    observation.ingest("source", f"{scenario.profile} peer roles=0x{scenario.sink_role:X}")
                if name == "gmap-unicast":
                    observation.ingest(
                        "source",
                        "GMAP peer features=ugg:0x0,ugt:0x4,bgs:0x0,bgr:0x0",
                    )
                source_line, sink_line = self._frame_lines(name, 17600)
                observation.ingest("source", source_line)
                observation.ingest("sink", sink_line)
                for role in ("source", "sink"):
                    role_token = (scenario.source_negative_role if role == "source"
                                  else scenario.sink_negative_role)
                    observation.ingest(role, role_token)
                    observation.ingest(role, scenario.quality_negative)
                    if scenario.feature_negative is not None:
                        observation.ingest(role, scenario.feature_negative)
                self.assertTrue(observation.ready())
                self.assertTrue(observation.negatives_complete())
                self.assertEqual(observation.source_frames.total, 17600)
                self.assertEqual(observation.sink_frames.total, 17600)

    def test_peer_role_and_frame_drop_fail_closed(self) -> None:
        scenario = MODULE.SCENARIOS["tmap-unicast"]
        with self.assertRaises(MODULE.HilFailure):
            MODULE.Observation(scenario).ingest("source", "TMAP peer roles=0x20")
        with self.assertRaises(MODULE.HilFailure):
            MODULE.Observation(scenario).ingest(
                "sink", "TMAP decoded frames=100 dropped=1"
            )

    def test_counter_accumulates_across_restart(self) -> None:
        counter = MODULE.Counter()
        for value in (100, 200, 100, 200):
            counter.update(value)
        self.assertEqual(counter.total, 400)

    def test_transcript_redacts_probe_and_ble_identity(self) -> None:
        probe = "0123456789abcdef0123456789abcdef"
        raw = f"probe={probe} peer=AA:BB:CC:DD:EE:FF\r\n".encode("ascii")
        sanitized = MODULE.sanitize_transcript(raw, (probe,))
        self.assertNotIn(probe.encode("ascii"), sanitized)
        self.assertNotIn(b"AA:BB:CC:DD:EE:FF", sanitized)
        self.assertIn(b"<redacted-probe>", sanitized)
        self.assertIn(b"<redacted-ble-address>", sanitized)

    def test_completion_limits_are_fail_closed(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('args.cycles != 20', source)
        self.assertIn('args.soak_seconds < 180.0', source)
        self.assertIn('args.minimum_soak_frames < 17500', source)
        self.assertNotIn('"raw_uid"', source)
        self.assertNotIn('"daplink_uid"', source)
        parser = MODULE.build_parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertNotIn("--uid", options)
        self.assertNotIn("--probe-id", options)
        self.assertIn("--source-probe-sha256", options)
        self.assertIn("--sink-probe-sha256", options)

    @staticmethod
    def _frame_lines(name: str, count: int) -> tuple[str, str]:
        if name == "tmap-unicast":
            return f"TMAP sent frames={count}", f"TMAP decoded frames={count} dropped=0"
        if name == "tmap-broadcast":
            return f"TMAP broadcast sent={count}", f"TMAP broadcast received={count} dropped=0"
        if name == "gmap-unicast":
            return f"Gaming sent frames={count}", f"Gaming decoded frames={count} dropped=0"
        return f"Gaming broadcast sent={count}", f"Gaming broadcast received={count} dropped=0"


if __name__ == "__main__":
    unittest.main()
