"""! @brief 표준 서비스와 실제 GATT backend의 runtime 계약을 검사합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest
from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]


class ProfileRuntimeTests(unittest.TestCase):
    def test_production_gatt_services(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        definitions = {
            "BT_OBSERVER": 1, "BT_DEVICE_NAME_MAX": 32,
            "NUCODE_BLE_CORE_EVENT_QUEUE_SIZE": 24, "NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE": 8,
            "BT_USER_PHY_UPDATE": 1, "NUCODE_BLE_GATT_SERVER": 1, "NUCODE_BLE_GATT_CLIENT": 1,
            "NUCODE_BLE_GATT_MAX_SERVICES": 2, "NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE": 8,
            "NUCODE_BLE_GATT_EVENT_QUEUE_SIZE": 24, "BT_SETTINGS": 1, "BT_SMP": 1,
            "BT_GATT_CACHING": 1, "BT_SIGNING": 1, "BT_EATT": 1,
        }
        sources = [
            "libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp",
            "libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp",
            "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp",
            *[str(p.relative_to(ROOT)) for p in (ROOT / "libraries/NUCODE_BLE/src/internal/gap").glob("*.cpp")],
            *[str(p.relative_to(ROOT)) for p in (ROOT / "libraries/NUCODE_BLE/src/internal/gatt").glob("*.cpp")],
            "libraries/NUCODE_BLE_Profiles/src/NUCODE_BLE_ProfileCodec.cpp",
            "libraries/NUCODE_BLE_Profiles/src/NUCODE_BLE_Profiles.cpp",
            "libraries/NUCODE_BLE_Profiles/src/NUCODE_BLE_ObjectStore.cpp",
            "tests/host/m33_profile_runtime_main.cpp",
        ]
        with tempfile.TemporaryDirectory(prefix="nu54-profile-runtime-") as folder:
            binary = Path(folder) / "profile.exe"
            command = [*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread"]
            command += [f"-DCONFIG_{name}={value}" for name, value in definitions.items()]
            for include in ("tests/host/ble_stubs", "third_party/ArduinoCore-API",
                            "libraries/NUCODE_BLE/src", "libraries/NUCODE_BLE_Security/src",
                            "libraries/NUCODE_BLE_Profiles/src"):
                command += ["-I", str(ROOT / include)]
            command += [str(ROOT / source) for source in sources]
            result = subprocess.run(command + ["-o", str(binary)], capture_output=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            for scenario in ("cts", "hts", "csc", "rscs", "ets", "alerts", "bonds", "object_store"):
                with self.subTest(scenario=scenario):
                    result = run_executable([str(binary), scenario], capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


    def test_stale_recovery_callbacks(self):
        """! @brief 실제 profile callback으로 한정된 후속 정리와 원형 종료 판정을 검증합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        source = (ROOT / "tests/zephyr/m33_profile_hil/src/main.cpp").read_text(encoding="utf-8")

        def function(signature):
            """! @brief 실제 함수 전체를 추출하며 조건 재구현이나 고정 산출물을 사용하지 않습니다. """
            begin = source.index("    " + signature)
            opening = source.index("\n    {", begin) + 1
            end = source.index("\n    }", opening) + len("\n    }")
            value = source[begin:end] + "\n"
            self.assertEqual(value.count("{"), value.count("}"), signature)
            return value

        declarations = source.split("    constexpr size_t stale_recovery_capacity", 1)[1].split(
            "    SensorService clock_service", 1
        )[0]
        declarations = "    constexpr size_t stale_recovery_capacity" + declarations
        signatures = (
            "void fail(",
            "bool sameAddress(",
            "bool copyPeerAddress(",
            "bool staleRecoveryEnabled()",
            "bool recoverStaleBond(BLEConnectionHandle connection, const PeerAddress &address)",
            "bool recoverStaleBond(const SecurityEventRecord &event)",
            "bool staleRecoveryPending(",
            "bool consumeStaleDisconnect(",
            "bool deferStaleRecoveryRestart(",
            "void pollStaleRecoveryRestart()",
            "void failStaleFollowup(",
            "bool deferOwnedStaleScanner(",
            "bool acceptStaleFollowupScan(",
            "void bindStaleFollowupConnection()",
            "bool observeStaleFollowupSecurity(",
            "bool observeStaleFollowupLink(",
            "bool remoteStaleInitialPhase()",
            "void failRemoteStale(",
            "void selectRemoteStalePeer(",
            "bool acceptRemoteStaleScan(",
            "void bindRemoteStaleConnection()",
            "bool observeRemoteStaleSecurity(",
            "bool observeRemoteStaleLink(",
            "void onSecurity(",
            "void onLink(",
            "void onScan(",
        )
        scenarios = (
            "normal19",
            "normal22",
            "pending_queue",
            "cleanup",
            "ready1_direct",
            "active_pairing",
            "L2_early_disconnect",
            "L2_BMS_disconnect",
            "L2_error",
            "error_remote19",
            "error_local22",
            "disconnect_first",
            "cross_error",
            "pairing_first",
            "retiring_connected",
            "retiring_pairing",
            "retired_pairing",
            "late_events",
            "late_L2",
            "late_timeout",
            "timeout",
            "security_other",
            "wrong_peer",
            "wrong_generation",
            "H2_62",
            "unsolicited22",
            "disconnect_rejected",
            "H3_error",
            "H3_62",
            "foreign_scan",
            "no_local_prune",
            "scan_not_running",
            "primary_second_peer",
            "remote_local_bond",
            "remote_restored",
            "remote_started_false",
            "remote_preprofile",
            "remote_first_l2",
            "remote_hci62",
            "remote_wrong_role",
            "remote_connected_error",
            "remote_no_connected_event",
            "remote_initial_ready1",
            "remote_ready1_success",
            "remote_queued_connected",
            "remote_ready0_no_reconnect",
            "remote_binding_guards",
            "remote_stop_delay",
            "remote_retired_conflict",
            "remote_retired_wrong_peer",
            "remote_retired_timeout",
            "remote_retired_gap_conflict",
            "remote_retired_role_conflict",
            "remote_retired_error_conflict",
            "remote_retired_duplicates",
            "remote_second_disconnect",
            "remote_second_security_error",
            "remote_second_wrong_peer",
            "remote_second_l2_disconnect",
        )
        watcher_signatures = tuple(signature for signature in signatures if signature in (
            "void fail(", "bool sameAddress(", "bool staleRecoveryEnabled()",
            "bool recoverStaleBond(BLEConnectionHandle connection, const PeerAddress &address)",
            "bool recoverStaleBond(const SecurityEventRecord &event)",
            "bool staleRecoveryPending(", "bool consumeStaleDisconnect(",
            "bool deferStaleRecoveryRestart(", "void pollStaleRecoveryRestart()",
            "void failStaleFollowup(", "bool observeStaleFollowupSecurity(",
            "bool observeStaleFollowupLink(",
        )) + (
            "bool deferWatcherDisconnect(", "bool consumeWatcherPendingSecurity(",
            "void finishWatcherDisconnect()", "void onSecurity(", "void onLink(",
            "void pollProfileEvents()",
        )
        watcher_scenarios = (
            "delayed_candidate", "candidate_before_disconnect", "candidate_absent",
            "candidate_next_poll", "no_local_bond", "wrong_candidate_handle",
            "wrong_candidate_type", "wrong_candidate_address", "candidate_wrong_level",
            "candidate_wrong_reason", "pairing_before_candidate", "error_before_candidate",
            "timeout_before_candidate", "l2_before_candidate", "removal_before_candidate",
            "duplicate_disconnect", "foreign_disconnect", "foreign_connected", "gap_error",
            "recycled_conflict", "reentrant_poll", "other_failure", "stop_pending",
            "cleanup_pending", "done_pending", "erase_rejected", "erase_verification_failed",
            "existing_address_slot", "capacity_exhausted", "duplicate_candidate",
            "stop_before_poll", "already_failed", "restored", "not_started", "invalid_startup",
            "profile_started", "post_l2", "wrong_link_role", "disconnect_driver_error",
            "disconnect_error", "reason62", "reason22", "outside_poll",
            "reentrant_during_erase", "resolved_stop",
            "recycled_wrong_role", "recycled_wrong_reason", "recycled_wrong_error",
            "recycled_wrong_driver", "existing_address_live_slot", "existing_consumed_handle",
            "delayed_candidate_late_errors", "candidate_before_disconnect_late_errors",
        )
        loop_source = source.split("void loop()\n{", 1)[1]
        self.assertLess(loop_source.index("pollProfileEvents();"),
                        loop_source.index("pollStaleRecoveryRestart();"))
        with tempfile.TemporaryDirectory(prefix="nu54-profile-stale-") as folder:
            temporary = Path(folder)
            (temporary / "stale-declarations.inc").write_text(declarations, encoding="utf-8")
            for role in ("server", "client", "watcher"):
                selected_signatures = watcher_signatures if role == "watcher" else signatures
                (temporary / "stale-functions.inc").write_text(
                    "\n".join(function(signature) for signature in selected_signatures),
                    encoding="utf-8",
                )
                binary = temporary / ("stale-" + role + ".exe")
                command = [*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror"]
                if role == "server":
                    command.append("-DM33_PROFILE_SERVER=1")
                elif role == "watcher":
                    command.append("-DM33_PROFILE_WATCHER=1")
                for include in (temporary, ROOT / "tests/zephyr/m33_profile_hil/src"):
                    command += ["-I", str(include)]
                command += [str(ROOT / "tests/host/m33_profile_stale_recovery_main.cpp"),
                            "-o", str(binary)]
                result = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                for scenario in watcher_scenarios if role == "watcher" else scenarios:
                    if role == "client" and scenario == "primary_second_peer":
                        continue
                    with self.subTest(role=role, scenario=scenario):
                        result = run_executable([str(binary), scenario], capture_output=True, timeout=10)
                        self.assertEqual(result.returncode, 0,
                                         (result.stdout + result.stderr).decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
