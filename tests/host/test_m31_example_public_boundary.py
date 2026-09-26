#!/usr/bin/env python3
"""! @brief 공개 Arduino 예제가 내부 검증 코드를 다시 노출하지 않도록 검사합니다. """

from __future__ import annotations

import importlib.util
import errno
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/host"))
from host_compiler import compiler_command, run_executable

SPEC = importlib.util.spec_from_file_location(
    "m31_example_audit_test", ROOT / "tools/ci/m31_example_audit.py"
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class ServerImageRebind:
    """! @brief image-lifetime immutable/mutable rebind 계약을 재현합니다. """

    def __init__(self) -> None:
        self.immutable: tuple[int, ...] | None = None
        self.state: dict[str, int] = {}

    def begin(self, immutable: tuple[int, ...], mutable: dict[str, int]) -> bool:
        """! @brief immutable 일치 시에만 mutable 상태를 모두 다시 적용합니다. """
        if self.immutable is None:
            self.immutable = immutable
        elif self.immutable != immutable:
            return False
        self.state = dict(mutable)
        return True


class ProfileRecoveryWatchdog:
    """! @brief 보안 요청 실패와 profile deadline 복구를 재현합니다. """

    def __init__(self) -> None:
        self.phase = "idle"
        self.recoveries = 0

    def connected(self, security_request_ok: bool) -> None:
        """! @brief 연결 직후 보안 요청의 동기 결과를 처리합니다. """
        self.phase = "securing"
        if not security_request_ok:
            self.recover()

    def secured(self) -> None:
        """! @brief 보안 성공 뒤 volume discovery watchdog을 시작합니다. """
        self.phase = "volume_discovery"

    def volume_ready(self) -> None:
        """! @brief volume 성공 뒤 microphone discovery watchdog을 시작합니다. """
        self.phase = "microphone_discovery"

    def timeout(self) -> None:
        """! @brief 준비 중인 단계만 bounded recovery로 전환합니다. """
        if self.phase in {"securing", "volume_discovery", "microphone_discovery"}:
            self.recover()

    def recover(self) -> None:
        """! @brief profile recovery 횟수와 phase를 갱신합니다. """
        self.recoveries += 1
        self.phase = "recovering"


class M31ExamplePublicBoundaryTests(unittest.TestCase):
    """! @brief 공개 흐름·역할·Zephyr 경계의 실제 sketch 변조를 거부합니다. """

    def test_audio_library_declares_ble_dependency(self) -> None:
        """! @brief Audio만 include하는 sketch도 BLE backend header를 찾도록 의존성을 고정합니다. """

        properties = (
            ROOT / "libraries/NUCODE_BLE_Audio/library.properties"
        ).read_text(encoding="utf-8")
        header = (
            ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio.h"
        ).read_text(encoding="utf-8")
        self.assertIn("\ndepends=NUCODE BLE\n", f"\n{properties.rstrip()}\n")
        self.assertIn("#include <NUCODE_BLE.h>", header)

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

        controller_sketch = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/examples/AudioControlController/AudioControlController.ino"
        ).read_text(encoding="utf-8")
        for public_read in (
            "volumeController.readVolume()",
            "volumeController.readOffset()",
            "volumeController.readInput()",
            "microphoneController.readMicrophone()",
            "microphoneController.readInput()",
        ):
            self.assertIn(public_read, controller_sketch)

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
        self.assertGreaterEqual(source.count("bt_conn_ref(expected_connection);"), 7)
        self.assertIn("volumeBackend.native_disconnected = true", source)
        self.assertIn("microphoneControllerBackend.native_disconnected = true", source)
        self.assertIn("releaseDisconnectedVocsLocked(connection)", source)
        self.assertIn("BT_CONN_CB_DEFINE(nucode_audio_control_connection_callbacks)", source)

    def test_audio_control_bootstrap_reads_actual_remote_state(self) -> None:
        """! @brief discovery 뒤 실제 VCP·VOCS·AICS·MICP 상태를 모두 읽는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "startVolumeBootstrap(",
            "controller->state_handle",
            "controller->vol_flag_handle",
            "struct bt_vocs_client, vocs)->state_handle",
            "struct bt_vocs_client, vocs)->location_handle",
            "input_service->cli.gain_handle",
            "input_service->cli.type_handle",
            "input_service->cli.status_handle",
            "bt_gatt_read(connection, &volumeBackend.bootstrap_read)",
            "startMicrophoneBootstrap(",
            "controller->mute_handle",
            "&microphoneControllerBackend.bootstrap_read",
        ):
            self.assertIn(token, source)

        microphone_order = (
            "microphone_state",
            "input_state",
            "input_status",
            "input_gain_setting",
            "input_type",
        )
        for step in microphone_order:
            self.assertIn(f"MicrophoneBootstrapStep::{step}", source)
        microphone_start = source.index("void startMicrophoneBootstrap")
        microphone_end = source.index("void serviceMicrophoneBootstrap", microphone_start)
        microphone_bootstrap = source[microphone_start:microphone_end]
        for call in (
            "controller->mute_handle",
            "input_service->cli.state_handle",
            "input_service->cli.status_handle",
            "input_service->cli.gain_handle",
            "input_service->cli.type_handle",
        ):
            self.assertIn(call, microphone_bootstrap)

    def test_audio_control_lifecycle_runtime_interleavings(self) -> None:
        """! @brief notification/read/end/begin 경쟁을 C++ stub 실행으로 검사합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m31-audio-control-") as temporary:
            binary = Path(temporary) / "audio-control-lifecycle.exe"
            command = [
                *compiler,
                "-std=gnu++20",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-unused-variable",
                "-pthread",
                "-include",
                str(
                    ROOT
                    / "tests/host/audio_control_runtime_stubs/audio_control_runtime_stubs.h"
                ),
                "-I",
                str(ROOT / "tests/host/audio_control_runtime_stubs/include"),
                "-I",
                str(ROOT / "libraries/NUCODE_BLE_Audio/src"),
                str(ROOT / "tests/host/m31_audio_control_lifecycle_main.cpp"),
                "-o",
                str(binary),
            ]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            result = run_executable([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("bootstrapTimeoutMs = 5000U", source)
        self.assertIn("maximumBootstrapRetryIntervalMs = 160U", source)
        self.assertIn("result == -EBUSY", source)
        self.assertIn("volumeBootstrapReadComplete", source)
        self.assertIn("microphoneBootstrapReadComplete", source)
        self.assertIn("bt_gatt_cancel(connection, &volumeBackend.bootstrap_read)", source)
        self.assertIn(
            "bt_gatt_cancel(connection, &microphoneControllerBackend.bootstrap_read)", source
        )
        self.assertIn("serviceVolumeBootstrap(generation_)", source)
        self.assertIn("serviceMicrophoneBootstrap(generation_)", source)
        self.assertIn("NUCODE_VOLUME_CONTROLLER_READ_REQUEST(read_volume", source)
        self.assertIn("NUCODE_MIC_CONTROLLER_READ_REQUEST(", source)
        self.assertIn("read_update_epoch", source)
        self.assertIn("markVolumeUpdate", source)
        self.assertIn("markMicrophoneUpdate", source)
        self.assertIn("volumeBackend.controller->state", source)
        self.assertIn("input_service->cli.change_counter", source)
        for ambiguous_read in (
            "bt_vcp_vol_ctlr_read_state(",
            "bt_vocs_state_get(",
            "bt_aics_state_get(",
            "bt_micp_mic_ctlr_mute_get(",
        ):
            self.assertNotIn(ambiguous_read, source)

    def test_audio_control_bootstrap_busy_and_timeout_are_bounded(self) -> None:
        """! @brief busy 재시도가 조기 횟수 제한 없이 전체 deadline을 따르는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"
        ).read_text(encoding="utf-8")
        self.assertNotIn("maximumBootstrapRetries", source)
        self.assertGreaterEqual(source.count("deadlineReached(now,"), 4)
        self.assertGreaterEqual(source.count("bootstrapRetryInterval("), 3)
        self.assertIn("failVolumeBootstrap(generation, -ETIMEDOUT)", source)
        self.assertIn("failMicrophoneBootstrap(generation, -ETIMEDOUT)", source)

    def test_audio_control_late_callback_keeps_ingress_epoch(self) -> None:
        """! @brief end 뒤 늦은 callback이 새 owner generation에 적용되지 않는지 검사합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("struct VolumeCallbackEpoch", source)
        self.assertIn("struct MicrophoneCallbackEpoch", source)
        self.assertIn("callbacks_inflight", source)
        self.assertIn("bt_conn_ref(expected_connection);", source)
        self.assertIn("volumeBackend.callbacks_inflight == 0U", source)
        self.assertIn("microphoneControllerBackend.callbacks_inflight == 0U", source)

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

        image = ServerImageRebind()
        immutable = (1, 1, 1)
        self.assertTrue(image.begin(immutable, {"volume": 10, "gain": 2}))
        before = dict(image.state)
        self.assertFalse(image.begin((1, 0, 1), {"volume": 99, "gain": 9}))
        self.assertEqual(image.state, before)
        self.assertTrue(image.begin(immutable, {"volume": 20, "gain": 4}))
        self.assertEqual(image.state, {"volume": 20, "gain": 4})

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
        self.assertIn("scheduleProfileRecovery();", source[source.index(
            "if (!BLESecurity.requestSecurity(peerConnection))"
        ):])
        self.assertIn("SecurityEvent::pairing_failed", source)
        self.assertIn("securityTimeoutMs = 10000U", source)
        self.assertIn("profileTimeoutMs = 10000U", source)
        self.assertIn("Audio control phase timeout", source)

        synchronous_failure = ProfileRecoveryWatchdog()
        synchronous_failure.connected(False)
        self.assertEqual(synchronous_failure.phase, "recovering")
        self.assertEqual(synchronous_failure.recoveries, 1)

        profile_timeout = ProfileRecoveryWatchdog()
        profile_timeout.connected(True)
        profile_timeout.secured()
        profile_timeout.timeout()
        self.assertEqual(profile_timeout.phase, "recovering")
        self.assertEqual(profile_timeout.recoveries, 1)

    def test_audio_control_client_description_write_is_fail_closed(self) -> None:
        """! @brief 잠긴 SDK의 AICS description write를 호출하지 않고 상태를 보존합니다. """
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"
        ).read_text(encoding="utf-8")
        starts = []
        offset = 0
        needle = "Error VolumeController::setInputDescription"
        starts.append(source.index(needle, offset))
        needle = "Error MicrophoneController::setInputDescription"
        starts.append(source.index(needle, starts[0] + 1))
        for start in starts:
            end = source.index("\n    }", start) + len("\n    }")
            method = source[start:end]
            self.assertIn("return record(Error::unsupported, -ENOTSUP);", method)
            self.assertNotIn("bt_aics_description_set", method)

        state = {"stage": "ready", "busy": False, "updates": 7}
        before = dict(state)
        result = -errno.ENOTSUP
        self.assertEqual(result, -errno.ENOTSUP)
        self.assertEqual(state, before)

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
            "CONFIG_BT_AICS_MAX_INPUT_DESCRIPTION_SIZE=32",
            "CONFIG_BT_VOCS_MAX_OUTPUT_DESCRIPTION_SIZE=32",
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

        merged = {}
        for line in device.splitlines():
            if line.startswith("CONFIG_") and "=" in line:
                key, value = line.split("=", 1)
                merged[key] = value
        self.assertGreaterEqual(int(merged["CONFIG_BT_AICS_MAX_INPUT_DESCRIPTION_SIZE"]), 32)
        self.assertGreaterEqual(int(merged["CONFIG_BT_VOCS_MAX_OUTPUT_DESCRIPTION_SIZE"]), 32)

        backend = (
            ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlDevice.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("static_assert(CONFIG_BT_AICS_MAX_INPUT_DESCRIPTION_SIZE", backend)
        self.assertIn("static_assert(CONFIG_BT_VOCS_MAX_OUTPUT_DESCRIPTION_SIZE", backend)

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
        self.assertIn("atomic_get(&sink_state.advertised_encrypted) != 0", sink)
        self.assertIn("Error::unsupported", source)
        self.assertIn("Error::unsupported", sink)
        self.assertIn("PublicBroadcastQuality::standard", wrapper)

    def test_public_audio_scan_matches_security_and_exact_ad_bytes(self) -> None:
        """! @brief PBA 보안 조건과 길이 기반 이름 검사를 고정합니다. """
        sink = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_BroadcastSink.cpp"
        ).read_text(encoding="utf-8")
        compact = " ".join(sink.split())

        self.assertIn(
            "match.encrypted == match.has_broadcast_code",
            compact,
        )
        self.assertIn("BT_GAP_ADV_PROP_CONNECTABLE", sink)
        self.assertGreaterEqual(sink.count("memchr("), 2)
        self.assertIn("data->data_len == strlen(match->target_name)", compact)
        self.assertIn("memcmp(data->data, match->target_name", compact)

    def test_public_audio_base_selects_supported_bis(self) -> None:
        """! @brief BASE codec를 검사한 BIS만 sync 호출에 전달하는지 검사합니다. """
        sink = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_BroadcastSink.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "bt_bap_base_foreach_subgroup(",
            "bt_bap_base_subgroup_foreach_bis(",
            "bt_audio_codec_cfg_get_freq(",
            "BT_AUDIO_CODEC_CFG_FREQ_16KHZ",
            "BT_AUDIO_CODEC_CFG_DURATION_10",
            "bt_audio_codec_cfg_get_octets_per_frame(",
            "bt_audio_codec_cfg_get_frame_blocks_per_sdu(",
            "atomic_get(&sink_state.selected_bis)",
            "streams, broadcast_code",
            "atomic_set(&sink_state.error, -EMSGSIZE);",
        ):
            self.assertIn(token, sink)

    def test_public_audio_teardown_preserves_failed_resources(self) -> None:
        """! @brief teardown 실패가 소유권을 잃거나 즉시 재시작되지 않게 고정합니다. """
        sink = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_BroadcastSink.cpp"
        ).read_text(encoding="utf-8")
        source = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_CapInitiator.cpp"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT
            / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_PublicBroadcast.cpp"
        ).read_text(encoding="utf-8")

        self.assertIn("BaseSelection selection = {};", sink)
        self.assertNotIn("stream_generation_slots", sink)
        self.assertIn("atomic_ptr_t callback_sink", sink)
        self.assertIn("atomic_ptr_t periodic_sync", sink)
        self.assertIn("atomic_t selected_bis", sink)
        self.assertIn("atomic_t sync_requested", sink)
        self.assertIn("atomic_t delegated_source", sink)
        self.assertIn("atomic_cas(&sink_state.found, 0, -1)", sink)
        self.assertIn("atomic_t state_callbacks_in_flight", sink)
        self.assertIn("int drainStateCallbacks() noexcept", sink)
        self.assertEqual(sink.count("const TransportCallbackFlight flight;"), 9)
        self.assertIn("int drainTransportCallbacks() noexcept", sink)
        self.assertIn("K_MUTEX_DEFINE(sink_state_mutex)", sink)
        self.assertIn("stream 목록이 이미 비어 있다는 뜻입니다", sink)
        self.assertIn("const int wait_result = k_sem_take(&sink_stopped", sink)
        self.assertIn("stage_ = BroadcastStage::failed;", sink)
        wait = sink.index("const int wait_result = k_sem_take(&sink_stopped")
        callback_drain = sink.index("drainTransportCallbacks();", wait)
        delete = sink.index("bt_bap_broadcast_sink_delete(", wait)
        deactivate = sink.index("atomic_set(&sink_state.active, 0);", delete)
        self.assertLess(wait, callback_drain)
        self.assertLess(callback_drain, delete)
        self.assertLess(wait, delete)
        self.assertLess(delete, deactivate)
        self.assertIn("int releaseCapSource() noexcept", source)
        self.assertIn("const int wait_result =", source)
        self.assertIn("atomic_get(&cap_source_state.stopping) == 0", source)
        self.assertIn("atomic_ptr_t callback_source", source)
        self.assertIn("atomic_t source_started", source)
        self.assertIn("atomic_t active", source)
        self.assertEqual(source.count("const CapCallbackFlight flight;"), 4)
        self.assertIn("int drainCapCallbacks() noexcept", source)
        source_wait = source.index("k_sem_take(&cap_source_stopped")
        source_drain = source.index("drainCapCallbacks();", source_wait)
        source_delete = source.index(
            "bt_cap_initiator_broadcast_audio_delete(", source_wait
        )
        source_deactivate = source.index(
            "atomic_set(&cap_source_state.active, 0);", source_delete
        )
        self.assertLess(source_wait, source_drain)
        self.assertLess(source_drain, source_delete)
        self.assertLess(source_wait, source_delete)
        self.assertLess(source_delete, source_deactivate)
        self.assertIn("return CapStage::failed;", source)
        self.assertIn("sink_started_ = false;", wrapper)
        self.assertIn("acceptor_started_ = false;", wrapper)

    def test_public_audio_recovery_checks_end_and_uses_backoff(self) -> None:
        """! @brief 공개 예제가 end 오류와 재시도 backoff를 처리하는지 검사합니다. """
        examples = ROOT / "libraries/NUCODE_BLE_Audio/examples"
        for name, stop_call in (
            ("PublicAudioBroadcastSource", "stopBroadcast()"),
            ("PublicAudioBroadcastSink", "stopListening()"),
        ):
            sketch = (examples / name / f"{name}.ino").read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("scheduleRecovery()", sketch)
                self.assertIn("recoveryAt = millis() + 1000U;", sketch)
                self.assertIn(stop_call, sketch)
                self.assertIn("stop failed", sketch)
                self.assertNotIn("<zephyr/", sketch)
                self.assertNotIn("M31", sketch)

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
