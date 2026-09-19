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

    def test_audio_control_sketches_keep_roles_and_state_flow(self) -> None:
        """! @brief VCP·VOCS·AICS·MICP 예제의 공개 상태 흐름을 검사합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_Audio"
            for name, token in (
                ("AudioControlDevice", "renderer.setOffset("),
                ("AudioControlController", "microphoneController.setInputGain("),
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

    def test_audio_control_backend_keeps_generation_and_fail_closed_busy(self) -> None:
        """! @brief controller callback가 stale owner와 중첩 작업을 거부하는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("volumeBackend.pending_generation != generation", source)
        self.assertIn("microphoneControllerBackend.pending_generation != generation", source)
        self.assertIn("atomic_cas(&volumeBackend.busy, 0, 1)", source)
        self.assertIn("atomic_cas(&microphoneControllerBackend.busy, 0, 1)", source)
        self.assertIn("internal::activeConnection(connection)", source)
        self.assertIn("K_MUTEX_DEFINE(volumeBackendMutex)", source)
        self.assertIn("K_MUTEX_DEFINE(microphoneControllerBackendMutex)", source)
        self.assertIn("retiredVolumeConnectionActive()", source)
        self.assertIn("retiredMicrophoneConnectionActive()", source)
        self.assertGreaterEqual(source.count("retired_connection = active != nullptr"), 2)

    def test_audio_control_bootstrap_reads_actual_remote_state(self) -> None:
        """! @brief discovery 뒤 실제 VCP·VOCS·AICS·MICP 상태를 모두 읽는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "startVolumeBootstrap(",
            "bt_vcp_vol_ctlr_read_state(controller)",
            "bt_vcp_vol_ctlr_read_flags(controller)",
            "bt_vocs_state_get(output_service)",
            "bt_vocs_location_get(output_service)",
            "bt_aics_gain_setting_get(input_service)",
            "bt_aics_type_get(input_service)",
            "bt_aics_status_get(input_service)",
            "startMicrophoneBootstrap(",
            "bt_micp_mic_ctlr_mute_get(controller)",
        ):
            self.assertIn(token, source)

    def test_audio_control_device_rebind_is_consistent(self) -> None:
        """! @brief image-lifetime service 재소유가 immutable 불일치와 stale cache를 거부합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlDevice.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "K_MUTEX_DEFINE(rendererBackendMutex)",
            "K_MUTEX_DEFINE(microphoneBackendMutex)",
            "rendererImmutableConfigMatches(config)",
            "microphoneImmutableConfigMatches(config)",
            "bt_vocs_location_set(output_service, config.output.location)",
            "setServerInputMode(input_service, config.input.mode)",
            "bt_aics_status_get(input_service)",
            "validUtf8(description, length)",
        ):
            self.assertIn(token, source)

    def test_audio_control_controller_has_bounded_failure_recovery(self) -> None:
        """! @brief async discovery 실패가 bounded disconnect·rescan으로 복구되는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/examples/AudioControlController/AudioControlController.ino"
        ).read_text(encoding="utf-8")
        self.assertIn("maximumProfileRecoveries = 3U", source)
        self.assertIn("maximumDisconnectAttempts = 3U", source)
        self.assertIn("scheduleProfileRecovery();", source)
        self.assertIn("BLEConnection.disconnect(peerConnection)", source)
        self.assertIn("scanPending = true;", source)

    def test_audio_control_instance_counts_are_exact(self) -> None:
        """! @brief 두 역할 image의 포함 service pool 합계를 고정합니다. """
        device = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/examples/AudioControlDevice/prj.conf"
        ).read_text(encoding="utf-8")
        controller = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/examples/AudioControlController/prj.conf"
        ).read_text(encoding="utf-8")
        for token in (
            "CONFIG_BT_AICS_MAX_INSTANCE_COUNT=2",
            "CONFIG_BT_VCP_VOL_REND_AICS_INSTANCE_COUNT=1",
            "CONFIG_BT_MICP_MIC_DEV_AICS_INSTANCE_COUNT=1",
            "CONFIG_BT_VOCS_MAX_INSTANCE_COUNT=1",
            "CONFIG_BT_VCP_VOL_REND_VOCS_INSTANCE_COUNT=1",
        ):
            self.assertIn(token, device)
        for token in (
            "CONFIG_BT_AICS_CLIENT_MAX_INSTANCE_COUNT=2",
            "CONFIG_BT_VCP_VOL_CTLR_MAX_AICS_INST=1",
            "CONFIG_BT_MICP_MIC_CTLR_MAX_AICS_INST=1",
            "CONFIG_BT_VOCS_CLIENT_MAX_INSTANCE_COUNT=1",
            "CONFIG_BT_VCP_VOL_CTLR_MAX_VOCS_INST=1",
        ):
            self.assertIn(token, controller)

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

    def test_public_audio_broadcast_sketches_keep_profile_flow(self) -> None:
        """! @brief 공개 방송 source/sink 예제의 품질·송수신 흐름을 검사합니다. """
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "NUCODE_BLE_Audio"
            for name, token in (
                ("PublicAudioBroadcastSource", "audioSource.sendFrame("),
                ("PublicAudioBroadcastSink", "audioSink.selected("),
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

    def test_public_audio_broadcast_backend_is_profile_bounded(self) -> None:
        """! @brief PBA 생성·해석과 Standard 전용 실패 경계를 검사합니다. """
        header = (
            ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio.h"
        ).read_text(encoding="utf-8")
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_CapInitiator.cpp"
        ).read_text(encoding="utf-8")
        sink = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_BroadcastSink.cpp"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_PublicBroadcast.cpp"
        ).read_text(encoding="utf-8")

        for declaration in (
            "enum class PublicBroadcastQuality",
            "struct PublicBroadcastSourceConfig",
            "struct PublicBroadcastFilter",
            "struct PublicBroadcastInfo",
            "class PublicAudioBroadcastSource final",
            "class PublicAudioBroadcastSink final",
        ):
            self.assertIn(declaration, header)
        self.assertIn("bt_pbp_get_announcement(", source)
        self.assertIn("BT_PBP_ANNOUNCEMENT_FEATURE_STANDARD_QUALITY", source)
        self.assertIn("bt_pbp_parse_announcement(", sink)
        self.assertIn("sink_state.encrypted != sink_state.advertised_encrypted", sink)
        self.assertIn("Error::unsupported", source)
        self.assertIn("Error::unsupported", sink)
        self.assertIn("PublicBroadcastQuality::standard", wrapper)

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
