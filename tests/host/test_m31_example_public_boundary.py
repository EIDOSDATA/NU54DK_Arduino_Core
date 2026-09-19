#!/usr/bin/env python3
"""! @brief 공개 Arduino 예제가 내부 검증 코드를 다시 노출하지 않도록 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "m31_example_audit_test", ROOT / "tools/ci/m31_example_audit.py"
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class M31ExamplePublicBoundaryTests(unittest.TestCase):
    """! @brief 공개 흐름·역할·Zephyr 경계의 실제 sketch 변조를 거부합니다. """

    def test_iso_role_and_backend_flow_must_match(self) -> None:
        """! @brief Kconfig 역할과 공개 Program 역할의 불일치를 거부합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_ISO"
            source = ROOT / "libraries/NUCODE_BLE_ISO"
            sketch = library / "examples/CISCentral/CISCentral.ino"
            sketch.parent.mkdir(parents=True)
            shutil.copy2(source / "examples/CISCentral/CISCentral.ino", sketch)
            shutil.copy2(source / "examples/CISCentral/prj.conf", sketch.parent / "prj.conf")
            backend = library / "src/NUCODE_BLE_ISO_RawCis.cpp"
            backend.parent.mkdir(parents=True)
            shutil.copy2(source / "src/NUCODE_BLE_ISO_RawCis.cpp", backend)
            original = sketch.read_text(encoding="utf-8")
            self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                             "VISIBLE_CODE")

            mutations = (
                (original.replace("Role::cis_central", "Role::cis_peripheral"),
                 "PUBLIC_ISO_DATA_FLOW_MISSING"),
                (original.replace("cis.poll();", "// cis.poll();"),
                 "PUBLIC_ISO_DATA_FLOW_MISSING"),
                (original + "\n#define M31_TEST_ROLE 1\n", "PUBLIC_MILESTONE_IDENTIFIER"),
                (original + "\nvoid test() { bt_enable(nullptr); }\n",
                 "PUBLIC_ZEPHYR_DIRECT_USE"),
            )
            for changed, expected in mutations:
                sketch.write_text(changed, encoding="utf-8")
                with self.subTest(expected=expected):
                    self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"], expected)

    def test_audio_sketch_must_call_public_codec(self) -> None:
        """! @brief 공개 LC3 encode/decode 흐름을 제거한 예제를 거부합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_Audio"
            sketch = library / "examples/Lc3SyntheticLoopback/Lc3SyntheticLoopback.ino"
            sketch.parent.mkdir(parents=True)
            source = ROOT / "libraries/NUCODE_BLE_Audio/examples/Lc3SyntheticLoopback/Lc3SyntheticLoopback.ino"
            shutil.copy2(source, sketch)
            self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"], "VISIBLE_CODE")
            sketch.write_text(
                sketch.read_text(encoding="utf-8").replace("codec.encode(", "codec.fake("),
                encoding="utf-8",
            )
            self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                             "PUBLIC_AUDIO_API_FLOW_MISSING")

    def test_broadcast_audio_sketches_must_keep_public_data_flow(self) -> None:
        """! @brief 방송 예제가 공개 BAP 송수신 흐름을 유지하는지 검사합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_Audio"
            for name, token in (
                ("BapBroadcastSource", "audioSource.sendFrame("),
                ("BapBroadcastSink", "audioSink.readFrame("),
            ):
                source = ROOT / "libraries/NUCODE_BLE_Audio/examples" / name
                sketch = library / "examples" / name / f"{name}.ino"
                sketch.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / f"{name}.ino", sketch)
                shutil.copy2(source / "prj.conf", sketch.parent / "prj.conf")
                with self.subTest(name=name, state="valid"):
                    self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                                     "VISIBLE_CODE")
                sketch.write_text(
                    sketch.read_text(encoding="utf-8").replace(token, token.replace("(", "Fake(")),
                    encoding="utf-8",
                )
                with self.subTest(name=name, state="mutated"):
                    self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                                     "PUBLIC_AUDIO_API_FLOW_MISSING")

    def test_cap_sketches_must_keep_public_profile_flow(self) -> None:
        """! @brief CAP 역할 예제의 공개 절차와 역할 Kconfig를 검사합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_Audio"
            for name, token in (
                ("CapInitiator", "initiator.updateContext("),
                ("CapAcceptor", "acceptor.begin("),
                ("CapCommander", "commander.stopReception("),
            ):
                source = ROOT / "libraries/NUCODE_BLE_Audio/examples" / name
                sketch = library / "examples" / name / f"{name}.ino"
                sketch.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / f"{name}.ino", sketch)
                shutil.copy2(source / "prj.conf", sketch.parent / "prj.conf")
                with self.subTest(name=name, state="valid"):
                    self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                                     "VISIBLE_CODE")
                sketch.write_text(
                    sketch.read_text(encoding="utf-8").replace(
                        token, token.replace("(", "Fake(")
                    ),
                    encoding="utf-8",
                )
                with self.subTest(name=name, state="mutated"):
                    self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                                     "PUBLIC_AUDIO_API_FLOW_MISSING")

    def test_cap_unicast_sketches_keep_group_and_data_flow(self) -> None:
        """! @brief CAP unicast의 공개 group·취소·LC3 흐름을 검사합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_Audio"
            for name, token in (
                ("CapUnicastInitiator", "initiator.cancel("),
                ("CapUnicastAcceptor", "audioSink.readFrame("),
            ):
                source = ROOT / "libraries/NUCODE_BLE_Audio/examples" / name
                sketch = library / "examples" / name / f"{name}.ino"
                sketch.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / f"{name}.ino", sketch)
                shutil.copy2(source / "prj.conf", sketch.parent / "prj.conf")
                with self.subTest(name=name, state="valid"):
                    self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                                     "VISIBLE_CODE")
                sketch.write_text(
                    sketch.read_text(encoding="utf-8").replace(
                        token, token.replace("(", "Fake(")
                    ),
                    encoding="utf-8",
                )
                with self.subTest(name=name, state="mutated"):
                    self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                                     "PUBLIC_AUDIO_API_FLOW_MISSING")

    def test_cap_delegated_sink_must_cleanup_failed_reception(self) -> None:
        """! @brief peer loss 오류 뒤 예약된 BASS cleanup이 먼저 실행되는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_BroadcastSink.cpp"
        ).read_text(encoding="utf-8")
        poll_start = source.index("void BroadcastSink::poll() noexcept")
        cleanup = source.index("atomic_cas(&sink_state.delegated_cleanup", poll_start)
        failed_return = source.index(
            "if (stage_ == BroadcastStage::failed)", poll_start
        )
        self.assertLess(cleanup, failed_return)

        release_start = source.index("int releaseDelegatedReception() noexcept")
        release_end = source.index("} // namespace", release_start)
        release = source[release_start:release_end]
        self.assertIn("atomic_set(&sink_state.error, 0);", release)

    def test_cap_commander_detects_loss_only_while_idle(self) -> None:
        """! @brief 의도한 CAP stop 알림을 peer loss로 오인하지 않는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/examples/CapCommander/CapCommander.ino"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "streamWasSynchronized && commander.hasSource() && commander.ready()",
            source,
        )

    def test_direction_finding_sketch_must_keep_public_control_flow(self) -> None:
        """! @brief CTE 송신 예제의 공개 start/stop 호출과 Kconfig를 검사합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_DirectionFinding"
            sketch = library / "examples/CteBeacon/CteBeacon.ino"
            sketch.parent.mkdir(parents=True)
            source = ROOT / "libraries/NUCODE_BLE_DirectionFinding/examples/CteBeacon"
            shutil.copy2(source / "CteBeacon.ino", sketch)
            shutil.copy2(source / "prj.conf", sketch.parent / "prj.conf")
            self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"], "VISIBLE_CODE")
            sketch.write_text(
                sketch.read_text(encoding="utf-8").replace("beacon.stop()", "beacon.fake()"),
                encoding="utf-8",
            )
            self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                             "PUBLIC_DF_API_FLOW_MISSING")

    def test_channel_sounding_sketch_must_keep_public_ranging_flow(self) -> None:
        """! @brief RAS 예제의 공개 수신 흐름과 역할 설정을 검사합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_ChannelSounding"
            source = ROOT / "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator"
            sketch = library / "examples/RasInitiator/RasInitiator.ino"
            sketch.parent.mkdir(parents=True)
            shutil.copy2(source / "RasInitiator.ino", sketch)
            shutil.copy2(source / "prj.conf", sketch.parent / "prj.conf")
            self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"], "VISIBLE_CODE")
            sketch.write_text(
                sketch.read_text(encoding="utf-8").replace("initiator.read(",
                                                         "initiator.fake("),
                encoding="utf-8",
            )
            self.assertEqual(AUDIT.inspect_sketch(library, sketch)["status"],
                             "PUBLIC_CS_API_FLOW_MISSING")


if __name__ == "__main__":
    unittest.main()
