"""! @brief profile HIL 증거 해석기가 누락 분모와 cross-link 증거 손실을 거부하는지 검사합니다. """
from pathlib import Path
import hashlib
import json
import sys
import subprocess
import tempfile
import unittest
from unittest import mock
from host_compiler import compiler_command, run_executable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hil/nu54dk"))
import m33_profile_run as PROFILE_RUN
from m33_profile_run import (bms_transition, failure_details, fields, start_roles,
                             load_build_identities, validate_native_security,
                             validate_results, validate_stop_record)
from m33_profile_bond_cleanup import validate_ownership_chain, validate_proof
from m33_profile_idle_fixture import audit_idle_ram
from m33_profile_native_pair import validate_pair


class ProfileHilTests(unittest.TestCase):
    @staticmethod
    def native_security(phase):
        """! @brief fresh/restored 보안 event 분모를 만듭니다. """
        passkeys = 1 if phase == "fresh" else 0
        restored = 0 if phase == "fresh" else 3
        return {role: {"passkey_events": passkeys, "security_changed_levels": [4, 4, 4],
                       "bond_restored_candidates": restored, "bond_verified": restored}
                for role in ("server", "client")}

    @classmethod
    def native_evidence(cls, phase, nonce, observed, prior=None):
        """! @brief pair validator용 최소 성공 evidence를 만듭니다. """
        passkeys = "1" if phase == "fresh" else "0"
        boards = {role: {"probe_sha256": str(index) * 64,
                         "image_sha256": str(index + 3) * 64}
                  for index, role in enumerate(("server", "client", "watcher"), 1)}
        identities = {role: {"manifest_sha256": str(index + 6) * 64,
                             "image_sha256": boards[role]["image_sha256"],
                             "source_sha256": "a" * 64}
                      for index, role in enumerate(boards, 1)}
        cleanup = {role: {"nonce": nonce} for role in boards}
        return {"schema": "nucode-m33-profile-hil-v1", "family": "native",
                "status": "PASS", "reason": None, "late_failures": [],
                "native_security_phase": phase, "native_prior_evidence_sha256": prior,
                "native_security": cls.native_security(phase),
                "results": {"client": {"nonce": nonce, "passkey_events": passkeys}},
                "server": {"passkey_events": passkeys}, "cleanup": cleanup,
                "revisions": {"core": "b" * 40}, "boards": boards,
                "build_identity": identities, "observed_utc": observed}

    def test_native_security_phase_denominators(self):
        for phase in ("fresh", "restored"):
            security = self.native_security(phase)
            passkeys = "1" if phase == "fresh" else "0"
            validate_native_security(phase, {"client": {"passkey_events": passkeys}},
                                     {"passkey_events": passkeys}, security)
            for role, field, value in (("client", "passkey_events", 2),
                                       ("server", "security_changed_levels", [3, 4, 4]),
                                       ("client", "bond_restored_candidates", 2)):
                broken = json.loads(json.dumps(security))
                broken[role][field] = value
                if phase == "fresh" and field == "bond_restored_candidates":
                    continue
                with self.subTest(phase=phase, role=role, field=field), self.assertRaises(ValueError):
                    validate_native_security(phase, {"client": {"passkey_events": passkeys}},
                                             {"passkey_events": passkeys}, broken)

    def test_build_record_rejects_role_image_and_source_tampering(self):
        with tempfile.TemporaryDirectory(prefix="nu54-profile-build-") as folder:
            root = Path(folder)
            source = root / "src/profile.cpp"
            source.parent.mkdir()
            source.write_bytes(b"profile-source")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            image_hash = hashlib.sha256(b"image").hexdigest()
            revision = "b" * 40
            main_source = root / "tests/zephyr/m33_profile_hil/src/main.cpp"
            main_source.parent.mkdir(parents=True)
            main_source.write_bytes(b"fixture")
            boards = {}
            paths = []
            for role in ("server", "client", "watcher"):
                output = root / role
                output.mkdir()
                files = {"image": output / "image.hex", "elf": output / "image.elf",
                         "config": output / "config.txt", "sysbuild": output / "sysbuild.txt",
                         "compile_commands": output / "compile_commands.json",
                         "build_info": output / "build_info.yml"}
                files["image"].write_bytes(b"image")
                files["elf"].write_bytes(b"elf")
                files["config"].write_text("CONFIG_SOC_NRF54L15_CPUAPP=y\n")
                files["sysbuild"].write_text("SB_CONFIG_FLPRCORE_NONE=y\n")
                family = "standard" if role == "watcher" else "native"
                command = (f'g++ -DM33_PROFILE_CORE_REVISION=\\"{revision}\\" '
                           f'-DM33_PROFILE_ROLE=\\"{role}\\"')
                if family == "native":
                    command += " -DM33_PROFILE_NATIVE=1"
                if role in ("server", "watcher"):
                    command += f" -DM33_PROFILE_{role.upper()}=1"
                files["compile_commands"].write_text(json.dumps([
                    {"file": str(main_source), "command": command}]))
                files["build_info"].write_text("version: test\n")
                descriptor = lambda name: {"path": str(files[name]),
                                           "sha256": hashlib.sha256(files[name].read_bytes()).hexdigest()}
                boards[role] = {"image_sha256": image_hash, "image": files["image"]}
                record = {"schema": "nucode-m33-profile-build-v1",
                          "family": family,
                          "role": role, "source_revision": revision, "sha256": image_hash,
                          "image": str(files["image"]),
                          "owned_source_sha256": {"src/profile.cpp": source_hash},
                          "command_identity": {
                              "sha256": hashlib.sha256(command.encode()).hexdigest(),
                              "compile_commands_sha256": descriptor("compile_commands")["sha256"],
                              "build_info_sha256": descriptor("build_info")["sha256"]},
                          "artifacts": {name: descriptor(name) for name in ("elf", "config", "sysbuild")},
                          "provenance": {name: descriptor(name) for name in ("compile_commands", "build_info")}}
                path = root / (role + ".json")
                path.write_text(json.dumps(record), encoding="utf-8")
                paths.append([role, str(path)])
            with mock.patch.object(PROFILE_RUN, "ROOT", root), \
                    mock.patch.object(PROFILE_RUN, "git_revision", return_value=revision):
                self.assertEqual(set(load_build_identities(paths, "native", boards)), set(boards))
                server_path = Path(paths[0][1])
                original = json.loads(server_path.read_text())
                for name, change in (("role", {**original, "role": "client"}),
                                     ("image", {**original, "sha256": "f" * 64})):
                    server_path.write_text(json.dumps(change), encoding="utf-8")
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        load_build_identities(paths, "native", boards)
                    server_path.write_text(json.dumps(original), encoding="utf-8")
                source.write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "source hash"):
                    load_build_identities(paths, "native", boards)

    def test_native_pair_rejects_missing_mismatch_and_replay(self):
        with tempfile.TemporaryDirectory(prefix="nu54-native-pair-") as folder:
            root = Path(folder)
            fresh_path = root / "fresh.json"
            restored_path = root / "restored.json"
            fresh = self.native_evidence("fresh", "1" * 32, "2026-10-03T01:00:00+00:00")
            fresh_path.write_text(json.dumps(fresh), encoding="utf-8")
            fresh_hash = hashlib.sha256(fresh_path.read_bytes()).hexdigest()
            restored = self.native_evidence("restored", "2" * 32,
                                            "2026-10-03T01:01:00+00:00", fresh_hash)
            restored_path.write_text(json.dumps(restored), encoding="utf-8")
            self.assertEqual(validate_pair(fresh_path, restored_path)["status"], "PASS")
            with self.assertRaisesRegex(ValueError, "replayed"):
                validate_pair(fresh_path, fresh_path)
            mutations = (("missing", lambda value: value.pop("native_security")),
                         ("mismatch", lambda value: value["build_identity"]["client"].update(
                             source_sha256="f" * 64)),
                         ("replay", lambda value: value["results"]["client"].update(
                             nonce="1" * 32)))
            for name, mutate in mutations:
                changed = json.loads(json.dumps(restored))
                mutate(changed)
                if name == "replay":
                    for record in changed["cleanup"].values():
                        record["nonce"] = "1" * 32
                restored_path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_pair(fresh_path, restored_path)
    def test_idle_fixture_live_ram(self):
        nonce = "a" * 32
        values = {"nonce": (nonce + "\0").encode(), "started": b"\0", "cleanup_complete": b"\1",
                  "stop_reported": b"\1", "failed": b"\0", "watchdog_channel": b"\xff" * 4}
        symbols = {name: {"address": 0x20000000 + 64 * index, "size": len(value)}
                   for index, (name, value) in enumerate(values.items())}
        memory = {symbols[name]["address"]: value for name, value in values.items()}
        class Target:
            def read_memory_block8(self, address, length):
                return memory[address][:length]
        result = audit_idle_ram(Target(), symbols, nonce)
        self.assertEqual(len(result), 6)
        self.assertTrue(all(item["stable_reads"] == 2 for item in result))
        for name, value in values.items():
            address = symbols[name]["address"]
            memory[address] = bytes([value[0] ^ 1]) + value[1:]
            with self.assertRaisesRegex(ValueError, "live lifecycle"):
                audit_idle_ram(Target(), symbols, nonce)
            memory[address] = value

    def test_owned_chain_rejects_changed_evidence_and_pair(self):
        with tempfile.TemporaryDirectory(prefix="nu54-bond-chain-") as folder:
            root = Path(folder)
            nonce = "a" * 32
            revisions = {"core": "b" * 40}
            boards = {role: {"probe_sha256": str(index) * 64, "image_sha256": str(index + 3) * 64}
                      for index, role in enumerate(("server", "client", "watcher"), 1)}
            original = {"observed_utc": "0", "revisions": revisions, "boards": boards}
            chain = {"schema": "nucode-m33-profile-bond-chain-v1", "original_attempt_sha256": "c" * 64, "steps": {}}
            def save(name, value):
                raw = value.encode("ascii") if isinstance(value, str) else json.dumps(value).encode("ascii")
                (root / name).write_bytes(raw)
                return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}
            for index, name in enumerate(("cleanup008", "standard009", "standard010", "native003", "native004"), 1):
                cleanup = {role: {"nonce": nonce, **{key: "0" for key in ("native_links", "links", "pending", "scan", "advertising", "watchdog")}}
                           for role in boards}
                lines = []
                for role in boards:
                    lines.append(f"{role}: M33PROFILE|1|STOPPED|nonce={nonce}")
                if name.startswith("standard"):
                    lines += [f"server: M33PROFILE|1|BMS_DELETED|nonce={nonce}|fresh=1|accepted=1",
                              f"client: M33PROFILE|1|BMS_CLEANED|nonce={nonce}|fresh=1|existing_unchanged=1"]
                    lines += [f"{role}: M33PROFILE|1|PROGRESS|nonce={nonce}|reason=fresh-test-bond" for role in ("server", "client")]
                if name == "native003":
                    lines += [f"{role}: M33PROFILE|1|PROGRESS|nonce={nonce}|security_event=8|level=2" for role in ("server", "client")]
                transcript = save(name + ".log", "\n".join(lines))
                evidence = {"revisions": revisions, "boards": boards, "observed_utc": str(index), "cleanup": cleanup,
                            "transcript_sha256": transcript["sha256"], "late_failures": [], "family": "native",
                            "status": "PASS" if index == 1 else "DEVELOPMENT_PASS" if index < 4 else "FAIL",
                            "attempt_sha256": "c" * 64, "server": {"native_links": "1"},
                            "results": {"client": {"bms_positive": "1", "bms_client_cleanup": "1"}}}
                if index == 1:
                    evidence["results"] = {role: {"removed": 1, "existing_unchanged": True, "stopped": True} for role in ("server", "client")}
                step = {"evidence": save(name + ".json", evidence), "transcript": transcript, "manifests": {}}
                for role in boards:
                    source = {"tests/zephyr/m33_profile_hil/src/main.cpp": "changed" if name == "native004" and role == "client" else "base"}
                    manifest = {"sha256": boards[role]["image_sha256"], "owned_source_sha256": source,
                                "artifacts": {"elf": {"sha256": "e" * 64}}}
                    step["manifests"][role] = save(name + role + ".json", manifest)
                chain["steps"][name] = step
            path = root / "chain.json"
            path.write_text(json.dumps(chain), encoding="utf-8")
            self.assertEqual(validate_ownership_chain(path, original)["latest_nonce"], nonce)
            latest = root / "native004.json"
            valid = latest.read_bytes()
            latest.write_bytes(valid + b" ")
            with self.assertRaisesRegex(ValueError, "file hash"):
                validate_ownership_chain(path, original)
            broken = json.loads(valid)
            broken["boards"]["client"]["probe_sha256"] = "f" * 64
            chain["steps"]["native004"]["evidence"] = save("native004.json", broken)
            path.write_text(json.dumps(chain), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "board pair"):
                validate_ownership_chain(path, original)

    def test_cleanup_gate_ownership(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "tests/zephyr/m33_profile_hil/src/main.cpp").read_text(encoding="utf-8")
        native_rescan = source.split("if (!failed && restart_native_scan)", 1)[1].split("#endif", 1)[0]
        self.assertNotIn("bms_", native_rescan)
        bms_cleanup = source.split("if (bms_client_cleanup_requested)", 1)[1].split("if (move_next)", 1)[0]
        for gate in ("bms_disconnect_seen", "!bms_reject.active()", "bms_write_acknowledged", "bms_teardown_errors == 1U"):
            self.assertIn(gate, bms_cleanup)

    def test_target_reject_pair_orders(self):
        root = Path(__file__).resolve().parents[2]
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-reject-pair-") as folder:
            binary = Path(folder) / "pair.exe"
            result = subprocess.run([*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I", str(root / "tests/zephyr/m33_profile_hil/src"),
                str(root / "tests/host/m33_profile_reject_main.cpp"), "-o", str(binary)],
                capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            result = run_executable([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_failed_attempt_owned_cleanup_proof(self):
        nonce = "a" * 32
        identity = {"image_sha256": "b" * 64, "probe_sha256": "c" * 64}
        attempt = {"family": "standard", "status": "FAIL", "boards": {"server": identity},
                   "cleanup": {"client": {"nonce": nonce}}}
        private = {**identity, "role": "server", "nonce": nonce, "fresh_bond": True,
                   "peer": "01010203040506", "before": ["010708090a0b0c"]}
        public = {**{key: value for key, value in private.items() if key not in ("peer", "before")},
                  "flags": {"cleanup_complete": 1, "stop_reported": 1, "cleanup_expired": 0, "watchdog_channel": -1},
                  "startup_bond_count": 1, "peer_not_in_startup": True,
                  "before_sha256": hashlib.sha256(bytes.fromhex(private["before"][0])).hexdigest(),
                  "peer_sha256": hashlib.sha256(bytes.fromhex(private["peer"])).hexdigest()}
        command = validate_proof(attempt, "server", private, public)
        self.assertIn(b"|CLEAN|nonce=" + nonce.encode(), command)
        for key, value in (("fresh_bond", False), ("image_sha256", "d" * 64), ("peer", private["before"][0]),
                           ("nonce", "d" * 32), ("before", [private["before"][0]] * 2)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_proof(attempt, "server", {**private, key: value}, public)
        with self.assertRaises(ValueError):
            validate_proof(attempt, "server", private, {**public, "flags": {}})
        with self.assertRaises(ValueError):
            validate_proof({**attempt, "status": "PASS"}, "server", private, public)

    def test_bms_fresh_bond_handshake(self):
        self.assertEqual(bms_transition(0, "client", "BMS_READY", {"negative_checks": "2", "client_fresh": "1"}), (1, "server", "ARM"))
        self.assertEqual(bms_transition(1, "server", "BMS_ARMED", {"fresh": "1"}), (2, "client", "BMS_DELETE"))
        proof = {key: "1" for key in ("accepted", "fresh", "watcher_unchanged", "requester_absent")}
        self.assertEqual(bms_transition(2, "server", "BMS_DELETED", proof), (3, "client", "BMS_DONE"))
        cleanup = {key: "1" for key in ("fresh", "server_absent", "existing_unchanged", "disconnected")}
        self.assertEqual(bms_transition(3, "client", "BMS_CLEANED", cleanup), (5, "", ""))
        for key in cleanup:
            with self.subTest(key=key), self.assertRaises(ValueError):
                bms_transition(3, "client", "BMS_CLEANED", {**cleanup, key: "0"})
        with self.assertRaises(ValueError):
            bms_transition(0, "client", "BMS_READY", {"negative_checks": "2", "client_fresh": "0"})
        self.assertEqual(bms_transition(1, "server", "BMS_SKIPPED", {"reason": "preexisting-or-unproven-bond"}), (4, "client", "BMS_SKIP"))
        for key in proof:
            with self.subTest(key=key), self.assertRaises(ValueError):
                bms_transition(2, "server", "BMS_DELETED", {**proof, key: "0"})
        with self.assertRaises(ValueError):
            bms_transition(0, "client", "BMS_ARMED", {"fresh": "1"})

    def test_stop_fail_closed(self):
        clean = {"nonce": "session", **{key: "0" for key in (
            "native_links", "links", "pending", "scan", "advertising", "watchdog")}}
        self.assertTrue(validate_stop_record("STOPPED", clean, "session", False))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_stop_record("STOPPED", clean, "session", True)
        with self.assertRaisesRegex(ValueError, "nonce"):
            validate_stop_record("STOPPED", clean, "wrong", False)
        with self.assertRaisesRegex(ValueError, "late target FAIL"):
            validate_stop_record("FAIL", {"nonce": "session", "reason": "cleanup-timeout"}, "session", False)
        for key in clean.keys() - {"nonce"}:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "denominator"):
                validate_stop_record("STOPPED", {**clean, key: "1"}, "session", False)
        with self.assertRaisesRegex(ValueError, "denominator"):
            validate_stop_record("STOPPED", {"nonce": "session"}, "session", False)

    def test_start_barriers(self):
        sent, observed = [], []
        class Port:
            def __init__(self, role):
                self.role = role
            def write(self, _):
                sent.append(self.role)
            def flush(self):
                pass
        ports = {role: Port(role) for role in ("server", "client", "watcher")}
        def receive(role):
            if role == "watcher" and observed == []:
                self.assertEqual(sent, ["watcher"])
                return "PROGRESS", {"reason": "advertising-ready"}
            if role == "server" and observed == ["watcher"]:
                self.assertEqual(sent, ["watcher", "server"])
                return "PROGRESS", {"reason": "hub-ready"}
            return None
        start_roles("standard", ports, b"start", receive,
                    lambda role, kind, value: observed.append(role))
        self.assertEqual(sent, ["watcher", "server", "client"])
        ticks = iter((0.0, 31.0))
        with self.assertRaisesRegex(ValueError, "start barrier missing"):
            start_roles("standard", ports, b"start", lambda _: None, lambda *args: None,
                        lambda: next(ticks))

    def test_target_failure_details_are_bounded(self):
        value = {"reason": "start-step", "stage": "hub-scan-start", "ble_error": "6",
                 "ble_driver": "-16", "security_error": "0", "security_driver": "0",
                 "unrecognized": "discard"}
        result = failure_details("server", value)
        self.assertEqual(result, {"role": "server", **{key: value[key] for key in value if key != "unrecognized"}})
        self.assertEqual(len(failure_details("s" * 30, {"stage": "x" * 1000})["stage"]), 96)
        self.assertEqual(len(failure_details("s" * 30, {})["role"]), 16)
        deadline = {"reason": "deadline", "profile_index": "5", "phase": "3", "count": "0",
                    "quiet_since": "5000", "last_gatt": "4", "last_gatt_at": "5000",
                    "last_gatt_status": "0", "last_att_error": "0", "connected": "1"}
        self.assertEqual(failure_details("watcher", deadline), {"role": "watcher", **deadline})
        native = {"reason": "object-step", "object_stage": "2", "event_type": "4", "event_status": "0",
                  "object_id": "256", "object_length": "0", "object_error": "-16", "type_ok": "1",
                  "length_ok": "0", "data_ok": "1", "accepted": "0", "object_busy": "0"}
        self.assertEqual(failure_details("client", native), {"role": "client", **native})
        gap = {"gap_event": "3", "link_role": "2", "hci_reason": "19", "same_peer": "1",
               "link_valid": "1", "link_connected": "0", "event_handle_valid": "1",
               "security_event": "2", "stage": "hub-ready"}
        self.assertEqual(failure_details("server", gap), {"role": "server", **gap})
        response = {"glucose_stage": "1", "response_length": "3", "response_bytes": "030100"}
        self.assertEqual(failure_details("client", response), {"role": "client", **response})

    def test_strict_fields(self):
        self.assertEqual(fields("M33PROFILE|1|RESULT|count=5"), {"count": "5"})
        with self.assertRaises(ValueError):
            fields("M33PROFILE|1|RESULT|count=5|count=6")
        with self.assertRaises(ValueError):
            fields("x" * 513)

    def test_standard_denominators(self):
        results = {"client": {"profiles": "7", "measurements": "30", "rejected": "3", "att_gap_rejects": "3", "bms_positive": "0", "bms_client_cleanup": "0", "bms_teardown_errors": "0"},
                   "watcher": {"profiles": "7", "measurements": "25", "rejected": "3", "att_gap_rejects": "3"}}
        stats = {"max_links": "2", "email_deliveries": "5", "alert_denied": "5", "bond_deletions": "0", "bms_positive": "0", "bms_skipped": "1"}
        stats.update({"send_stats": {f"{slot}:{profile}": {"sent": "5", "no_ccc": "1"}
                                     for slot in range(2) for profile in range(5)},
                      "no_ccc_errors": "10", "pending_errors": "0", "dropped_events": "0"})
        validate_results("standard", results, stats)
        with self.assertRaisesRegex(ValueError, "pair denominator"):
            validate_results("standard", {**results, "watcher": {**results["watcher"], "att_gap_rejects": "2"}}, stats)
        validate_results("standard", {**results, "client": {**results["client"], "bms_positive": "1", "bms_client_cleanup": "1"}},
                         {**stats, "bond_deletions": "1", "bms_positive": "1", "bms_skipped": "0"})
        validate_results("standard", {**results, "client": {**results["client"], "bms_positive": "1", "bms_client_cleanup": "1", "bms_teardown_errors": "1"}},
                         {**stats, "bond_deletions": "1", "bms_positive": "1", "bms_skipped": "0"})
        for invalid in (None, "-1", "2"):
            with self.subTest(teardown=invalid), self.assertRaisesRegex(ValueError, "teardown"):
                validate_results("standard", {**results, "client": {**results["client"], "bms_teardown_errors": invalid}}, stats)
        with self.assertRaisesRegex(ValueError, "teardown"):
            validate_results("standard", {**results, "client": {**results["client"], "bms_teardown_errors": "1"}}, stats)
        with self.assertRaisesRegex(ValueError, "cleanup"):
            validate_results("standard", {**results, "client": {**results["client"], "bms_positive": "1"}},
                             {**stats, "bond_deletions": "1", "bms_positive": "1", "bms_skipped": "0"})
        for key, value in (("no_ccc_errors", "9"), ("pending_errors", "1"), ("dropped_events", "1"), ("send_stats", {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_results("standard", results, {**stats, key: value})
        for key, value in (("max_links", "1"), ("email_deliveries", "0"), ("alert_denied", "4"), ("bond_deletions", "1")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_results("standard", results, {**stats, key: value})
        with self.assertRaises(ValueError):
            validate_results("standard", {**results, "client": {"profiles": "7", "measurements": "29", "rejected": "3"}}, stats)

    def test_native_denominators(self):
        results = {"client": {"object_operations": "14", "glucose": "2", "native_checks": "7", "single_link": "1",
                              "native_sessions": "3", "normal_reconnects": "1", "coc_cancels": "1",
                              "cancel_reconnects": "1", "reconnect_reads": "1", "reconnect_writes": "1", "authenticated_links": "3"}}
        stats = {"object_writes": "3", "single_link": "1", "native_links": "3", "native_disconnects": "2", "authenticated_links": "3"}
        validate_results("native", results, stats)
        for key in results["client"]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_results("native", {"client": {**results["client"], key: "0"}}, stats)


if __name__ == "__main__":
    unittest.main(verbosity=2)
