#!/usr/bin/env python3
"""W03-10 TMAP/GMAP 공개 Serial HIL 계약을 검사합니다."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


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

    def test_boot_binary_prefix_recovers_only_exact_public_line(self) -> None:
        """! @brief CMSIS-DAP VCOM 부팅 잔여에서 공개 줄만 엄격히 복원합니다. """
        self.assertEqual(
            MODULE.decode_public_line(b"\xff\x00<DAPLink:Overflow>\x81TMAP local roles=0x5 service=TMAS\r"),
            "TMAP local roles=0x5 service=TMAS",
        )
        self.assertIsNone(MODULE.decode_public_line(b"\xff\x00<DAPLink:Overflow>\x81"))
        with self.assertRaises(MODULE.HilFailure):
            MODULE.decode_public_line(b"\xffFATAL fault\x00TMAP local roles=0x5 service=TMAS")

    def test_post_flash_boot_order_matches_transport(self) -> None:
        """! @brief unicast와 broadcast의 안정적인 peer 부팅 순서를 고정합니다. """

        class FakePort:
            """! @brief input buffer clear 순서만 기록하는 fake serial입니다. """

            def __init__(self, role: str) -> None:
                self.role = role

            def reset_input_buffer(self) -> None:
                events.append(("clear", self.role))

        for scenario_name, first, second in (
            ("tmap-unicast", "sink-probe", "source-probe"),
            ("tmap-broadcast", "source-probe", "sink-probe"),
        ):
            with self.subTest(scenario=scenario_name):
                events = []
                source = FakePort("source")
                sink = FakePort("sink")
                expected_harness = object()
                observation = MODULE.Observation(MODULE.SCENARIOS[scenario_name])

                def reset(uid: str) -> None:
                    events.append(("reset", uid))

                def wait(seconds: float) -> None:
                    events.append(("wait", seconds))

                def create(_source, _sink, _observation):
                    events.append(("harness",))
                    return expected_harness

                with patch.object(MODULE, "hardware_reset", side_effect=reset), \
                     patch.object(MODULE.time, "sleep", side_effect=wait), \
                     patch.object(MODULE, "SerialHarness", side_effect=create):
                    harness = MODULE.create_fresh_serial_harness(
                        source, sink, "source-probe", "sink-probe", observation
                    )

                self.assertIs(harness, expected_harness)
                self.assertEqual(
                    events,
                    [
                        ("clear", "source"),
                        ("clear", "sink"),
                        ("reset", first),
                        ("wait", 1.0),
                        ("reset", second),
                        ("harness",),
                    ],
                )
        runner_source = RUNNER.read_text(encoding="utf-8")
        execute_source = runner_source[runner_source.index("def execute("):]
        sink_flash = execute_source.index('sink_flash = flash_image_pyocd("sink"')
        source_flash = execute_source.index('source_flash = flash_image_pyocd("source"')
        fresh_boot = execute_source.index("harness = create_fresh_serial_harness(")
        self.assertLess(sink_flash, source_flash)
        self.assertLess(source_flash, fresh_boot)

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

    def test_broadcast_final_stop_disarms_sink_before_source(self) -> None:
        """! @brief 최종 broadcaster 종료가 정상 receiver 종료 뒤에만 실행됩니다. """
        source = RUNNER.read_text(encoding="utf-8")
        start = source.index("final_source_stop =")
        block = source[start:source.index("    return {", start)]
        sink_stop = block.index('harness.command("sink", "s")')
        source_stop = block.index('harness.command("source", "s")')
        self.assertLess(sink_stop, source_stop)
        self.assertIn("harness.observation.sink_stop_count > final_sink_stop", block)

    def test_adjacent_arduino_build_manifest_is_preferred_and_bound_to_hex(self) -> None:
        core_revision = "a" * 40
        board_revision = "b" * 40
        expected_revisions = {
            "NUCODE_CORE_REVISION": core_revision,
            "NUCODE_BOARD_REVISION": board_revision,
            "NUCODE_NCS_REVISION":
                "99553055607b2e9885fbc80ccd11fa9da81c2df0",
            "NUCODE_ZEPHYR_REVISION":
                "bf801e4e3d19e1ffa76164346480cb7734dd2800",
        }
        with tempfile.TemporaryDirectory(prefix="nu54-w03-10-build-record-") as directory:
            root = Path(directory) / "build" / "TelephonyMediaGateway"
            root.mkdir(parents=True)
            platform_root = (Path(directory) / "platform").resolve()
            image = root / "TelephonyMediaGateway.ino.hex"
            image.write_bytes(b":00000001FF\n")
            record = image.with_suffix(".nu54-build.json")
            document = {
                "artifacts": {
                    "hex": {
                        "path": image.resolve().as_posix(),
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "size": image.stat().st_size,
                    }
                },
                "board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
                "cache": {
                    "input_manifest": {
                        "adapter": {
                            "embedded_core_revision": core_revision,
                        },
                        "board_package": {
                            "revision": board_revision,
                        },
                        "ncs": {
                            "nrf_revision": expected_revisions[
                                "NUCODE_NCS_REVISION"
                            ],
                            "zephyr_revision": expected_revisions[
                                "NUCODE_ZEPHYR_REVISION"
                            ],
                        },
                        "configuration": {
                            "selected_features": [],
                        },
                        "toolchain": {
                            "bundle_id": "dcbdc366a1",
                            "compiler": "arm-zephyr-eabi-g++.exe 14.3.0",
                        }
                    }
                },
                "context": {
                    "platform_root": platform_root.as_posix(),
                    "selected_libraries": [],
                },
                "source_inputs": {},
            }
            (root.parent / "nucode_arduino_core_build.yml").write_text(
                "invalid legacy record", encoding="utf-8"
            )

            revision_families = (
                ("NUCODE_BLE_ISO", "nucode.ble.iso", "m31_iso_revisions"),
                ("NUCODE_BLE_Audio", "nucode.ble.audio", "m31_audio_revisions"),
                (
                    "NUCODE_BLE_DirectionFinding",
                    "nucode.ble.direction_finding",
                    "m31_df_revisions",
                ),
                (
                    "NUCODE_BLE_ChannelSounding",
                    "nucode.ble.channel_sounding",
                    "m31_cs_revisions",
                ),
            )
            for library, feature_id, revision_key in revision_families:
                with self.subTest(revision_key=revision_key):
                    document["context"]["selected_libraries"] = [library]
                    document["cache"]["input_manifest"]["configuration"][
                        "selected_features"
                    ] = [{"id": feature_id}]
                    document["source_inputs"] = {
                        "sources": [{
                            "logical_identity":
                                f"platform:libraries/{library}/src/fixture.cpp",
                            "source_path": (
                                platform_root / "libraries" / library
                                / "src/fixture.cpp"
                            ).as_posix(),
                        }],
                        revision_key: expected_revisions
                    }
                    record.write_text(json.dumps(document), encoding="utf-8")

                    result = MODULE.validate_build_record(
                        image, core_revision, board_revision, root
                    )

                    self.assertEqual(result["record_name"], record.name)
                    self.assertEqual(result["record_format"], "nu54-build-json")
                    self.assertEqual(
                        result["hex_sha256"],
                        document["artifacts"]["hex"]["sha256"],
                    )

            selected = (
                (
                    "NUCODE_BLE_Audio",
                    "nucode.ble.audio",
                    "m31_audio_revisions",
                ),
                (
                    "NUCODE_BLE_ChannelSounding",
                    "nucode.ble.channel_sounding",
                    "m31_cs_revisions",
                ),
            )
            document["context"]["selected_libraries"] = [
                library for library, _feature_id, _revision_key in selected
            ]
            document["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [
                {"id": feature_id}
                for _library, feature_id, _revision_key in selected
            ]
            document["source_inputs"] = {
                "sources": [{
                    "logical_identity":
                        f"platform:libraries/{library}/src/fixture.cpp",
                    "source_path": (
                        platform_root / "libraries" / library
                        / "src/fixture.cpp"
                    ).as_posix(),
                } for library, _feature_id, _revision_key in selected],
                **{
                    revision_key: expected_revisions
                    for _library, _feature_id, revision_key in selected
                },
            }
            record.write_text(json.dumps(document), encoding="utf-8")
            MODULE.validate_build_record(
                image, core_revision, board_revision, root
            )

    def test_adjacent_arduino_build_manifest_rejects_stale_hex_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nu54-w03-10-build-record-") as directory:
            root = Path(directory)
            platform_root = (root / "platform").resolve()
            image = root / "TelephonyMediaGateway.ino.hex"
            image.write_bytes(b":00000001FF\n")
            record = image.with_suffix(".nu54-build.json")
            document = {
                "artifacts": {
                    "hex": {
                        "path": image.resolve().as_posix(),
                        "sha256": "0" * 64,
                        "size": image.stat().st_size,
                    }
                },
                "board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
                "cache": {
                    "input_manifest": {
                        "adapter": {
                            "embedded_core_revision": "a" * 40,
                        },
                        "board_package": {
                            "revision": "b" * 40,
                        },
                        "ncs": {
                            "nrf_revision":
                                "99553055607b2e9885fbc80ccd11fa9da81c2df0",
                            "zephyr_revision":
                                "bf801e4e3d19e1ffa76164346480cb7734dd2800",
                        },
                        "configuration": {
                            "selected_features": [{"id": "nucode.ble.audio"}],
                        },
                        "toolchain": {
                            "bundle_id": "dcbdc366a1",
                            "compiler": "arm-zephyr-eabi-g++.exe 14.3.0",
                        }
                    }
                },
                "context": {
                    "platform_root": platform_root.as_posix(),
                    "selected_libraries": ["NUCODE_BLE_Audio"],
                },
                "source_inputs": {
                    "sources": [{
                        "logical_identity":
                            "platform:libraries/NUCODE_BLE_Audio/src/fixture.cpp",
                        "source_path": (
                            platform_root
                            / "libraries/NUCODE_BLE_Audio/src/fixture.cpp"
                        ).as_posix(),
                    }],
                    "m31_audio_revisions": {
                        "NUCODE_CORE_REVISION": "a" * 40,
                        "NUCODE_BOARD_REVISION": "b" * 40,
                        "NUCODE_NCS_REVISION":
                            "99553055607b2e9885fbc80ccd11fa9da81c2df0",
                        "NUCODE_ZEPHYR_REVISION":
                            "bf801e4e3d19e1ffa76164346480cb7734dd2800",
                    }
                },
            }
            record.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaises(RuntimeError):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["artifacts"]["hex"]["sha256"] = hashlib.sha256(
                image.read_bytes()
            ).hexdigest()
            document["source_inputs"]["m31_audio_revisions"][
                "NUCODE_CORE_REVISION"
            ] = "c" * 40
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "revision 불일치"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            expected_revisions = {
                "NUCODE_CORE_REVISION": "a" * 40,
                "NUCODE_BOARD_REVISION": "b" * 40,
                "NUCODE_NCS_REVISION":
                    "99553055607b2e9885fbc80ccd11fa9da81c2df0",
                "NUCODE_ZEPHYR_REVISION":
                    "bf801e4e3d19e1ffa76164346480cb7734dd2800",
            }
            document["context"]["selected_libraries"] = ["NUCODE_BLE"]
            document["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [{"id": "nucode.ble.nus"}]
            document["source_inputs"] = {
                "sources": [{
                    "logical_identity":
                        "platform:libraries/NUCODE_BLE/src/fixture.cpp",
                    "source_path": (
                        platform_root / "libraries/NUCODE_BLE/src/fixture.cpp"
                    ).as_posix(),
                }],
            }
            record.write_text(json.dumps(document), encoding="utf-8")
            MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["context"]["selected_libraries"] = [
                "NUCODE_BLE_ChannelSounding"
            ]
            document["source_inputs"] = {
                "sources": [{
                    "logical_identity":
                        "platform:libraries/NUCODE_BLE_ChannelSounding/"
                        "src/fixture.cpp",
                    "source_path": (
                        platform_root
                        / "libraries/NUCODE_BLE_ChannelSounding/src/fixture.cpp"
                    ).as_posix(),
                }],
                "m31_cs_revisions": expected_revisions,
            }
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "selected library/cache feature"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [{"id": "nucode.ble.channel_sounding"}]
            document["source_inputs"].pop("m31_cs_revisions")
            document["source_inputs"]["m31_audio_revisions"] = expected_revisions
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "selected library/revision"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["context"]["selected_libraries"] = [
                "NUCODE_BLE_Audio", "NUCODE_BLE_ChannelSounding"
            ]
            document["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [
                {"id": "nucode.ble.audio"},
                {"id": "nucode.ble.channel_sounding"},
            ]
            document["source_inputs"] = {
                "sources": [
                    {
                        "logical_identity":
                            "platform:libraries/NUCODE_BLE_Audio/"
                            "src/fixture.cpp",
                        "source_path": (
                            platform_root
                            / "libraries/NUCODE_BLE_Audio/src/fixture.cpp"
                        ).as_posix(),
                    },
                    {
                        "logical_identity":
                            "platform:libraries/NUCODE_BLE_ChannelSounding/"
                            "src/fixture.cpp",
                        "source_path": (
                            platform_root
                            / "libraries/NUCODE_BLE_ChannelSounding/"
                            "src/fixture.cpp"
                        ).as_posix(),
                    },
                ],
                "m31_cs_revisions": expected_revisions,
            }
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "selected library/revision"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["source_inputs"]["m31_audio_revisions"] = expected_revisions
            document["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [{"id": "nucode.ble.audio"}]
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "selected library/cache feature"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [
                {"id": "nucode.ble.audio"},
                {"id": "nucode.ble.channel_sounding"},
                {"id": "nucode.ble.iso"},
            ]
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "selected library/cache feature"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [
                {"id": "nucode.ble.audio"},
                {"id": "nucode.ble.channel_sounding"},
            ]
            document["source_inputs"]["m31_iso_revisions"] = expected_revisions
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "selected library/revision"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["source_inputs"].pop("m31_iso_revisions")
            document["source_inputs"]["m31_typo_revisions"] = expected_revisions
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "알 수 없는 revision family"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["source_inputs"].pop("m31_typo_revisions")
            document["source_inputs"]["m31_cs_revisions"] = {
                **expected_revisions,
                "UNDECLARED_REVISION": "d" * 40,
            }
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "revision 불일치"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["source_inputs"]["m31_cs_revisions"] = expected_revisions
            document["cache"]["input_manifest"]["ncs"]["nrf_revision"] = (
                "e" * 40
            )
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "cache revision 불일치"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["cache"]["input_manifest"]["ncs"]["nrf_revision"] = (
                expected_revisions["NUCODE_NCS_REVISION"]
            )
            document["source_inputs"]["sources"][0]["source_path"] = (
                platform_root
                / "libraries/NUCODE_BLE_ChannelSounding/src/spoof.cpp"
            ).as_posix()
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "source identity/path"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["source_inputs"]["sources"][0]["source_path"] = (
                platform_root / "libraries/NUCODE_BLE_Audio/src/spoof.cpp"
            ).as_posix()
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "source identity/path"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

            document["source_inputs"]["sources"][0]["source_path"] = (
                platform_root / "libraries/NUCODE_BLE_Audio/src/fixture.cpp"
            ).as_posix()
            document["source_inputs"]["sources"] = [
                document["source_inputs"]["sources"][0]
            ]
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "selected library/source graph"):
                MODULE.validate_build_record(image, "a" * 40, "b" * 40, root)

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
