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
                             validate_native_cleanup,
                             validate_bms_predecessor, validate_native_predecessor,
                             validate_identity_readiness, validate_results,
                             validate_primary_cleanup, validate_second_peer,
                             validate_stop_record)
from m33_profile_bond_cleanup import validate_ownership_chain, validate_proof
from m33_profile_build_record import validate_compile_identity
from m33_profile_idle_fixture import audit_idle_ram
from m33_profile_native_pair import validate_pair


class ProfileHilTests(unittest.TestCase):
    @staticmethod
    def attach_exact_bundle(root, evidence, stem):
        """! @brief predecessor fixture에 실제 image·build·readback·transcript byte를 결합합니다. """
        programs = {}
        for role, board in evidence["boards"].items():
            image = root / f"{stem}.{role}.image.hex"
            build = root / f"{stem}.{role}.build-record"
            readback = root / f"{stem}.{role}.readback.json"
            image.write_text(
                ":080000000102030405060708D4\n:00000001FF\n", encoding="ascii"
            )
            build.write_bytes(f"profile-build:{role}".encode("ascii"))
            image_sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
            board["image_sha256"] = image_sha256
            evidence["build_identity"][role]["image_sha256"] = image_sha256
            evidence["build_identity"][role]["manifest_sha256"] = hashlib.sha256(
                build.read_bytes()
            ).hexdigest()
            readback_value = {
                "schema_version": 1, "kind": "m33_exact_program_readback",
                "status": "PASS", "role": role,
                "probe_sha256": board["probe_sha256"],
                "image_sha256": image_sha256,
                  "backend": "pyocd-live-target", "halted": True,
                  "resumed": True,
                  "pre_state": "RUNNING", "post_state": "RUNNING",
                  "restored": True,
                  "ranges": [{
                    "start": 0, "length": 8, "status": "PASS",
                    "expected_sha256": hashlib.sha256(
                        b"\x01\x02\x03\x04\x05\x06\x07\x08"
                    ).hexdigest(),
                    "observed_sha256": hashlib.sha256(
                        b"\x01\x02\x03\x04\x05\x06\x07\x08"
                    ).hexdigest(),
                }],
            }
            readback.write_text(json.dumps(readback_value), encoding="utf-8")
            programs[role] = {
                "probe_sha256": board["probe_sha256"],
                "image": {"path": image.name,
                          "sha256": hashlib.sha256(image.read_bytes()).hexdigest()},
                "build_record": {"path": build.name,
                                 "sha256": hashlib.sha256(build.read_bytes()).hexdigest()},
                "flash": {"mode": "pyocd-sector", "programmed_bytes": 8,
                          "erase": "sector", "auto_unlock": False,
                          "mass_erase": False, "automatic_recover": False},
                "readback": {"path": readback.name,
                             "sha256": hashlib.sha256(readback.read_bytes()).hexdigest()},
            }
        transcript = root / f"{stem}.transcript.log"
        transcript.write_bytes(f"profile-transcript:{stem}".encode("ascii"))
        evidence["exact_program"] = programs
        evidence["transcript_sha256"] = hashlib.sha256(
            transcript.read_bytes()
        ).hexdigest()
        evidence["transcript"] = {"path": transcript.name,
                                  "sha256": evidence["transcript_sha256"]}

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
        result = {"nonce": nonce, "passkey_events": passkeys,
                  "object_operations": "14", "glucose": "2", "native_checks": "7",
                  "single_link": "1", "native_sessions": "3", "normal_reconnects": "1",
                  "coc_cancels": "1", "cancel_reconnects": "1", "reconnect_reads": "1",
                  "reconnect_writes": "1", "authenticated_links": "3"}
        server = {"passkey_events": passkeys, "object_writes": "3", "single_link": "1",
                  "native_links": "3", "native_disconnects": "2", "authenticated_links": "3"}
        return {"schema": "nucode-m33-profile-hil-v1", "family": "native",
                "status": "PASS", "reason": None, "late_failures": [],
                "native_security_phase": phase, "native_prior_evidence_sha256": prior,
                "native_security": cls.native_security(phase),
                "results": {"client": result}, "server": server, "cleanup": cleanup,
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
        ready = {
            "server": {"fresh": "0", "restored": "1", "passkey_events": "0",
                       "candidate": "1", "verified": "1", "existing_unchanged": "1"},
            "client": {"fresh": "1", "restored": "0", "passkey_events": "1",
                       "candidate": "0", "verified": "0", "existing_unchanged": "1"},
        }
        result = {
            role: {"removed": "1", "fresh": value["fresh"],
                   "restored": value["restored"], "existing_unchanged": "1",
                   "disconnected": "1"}
            for role, value in ready.items()
        }
        security = {
            "server": {"passkey_events": 0, "security_changed_levels": [4],
                       "bond_restored_candidates": 1, "bond_verified": 1},
            "client": {"passkey_events": 1, "security_changed_levels": [4],
                       "bond_restored_candidates": 0, "bond_verified": 0},
        }
        validate_native_cleanup(ready, result, result, security)
        broken = json.loads(json.dumps(result))
        broken["client"]["existing_unchanged"] = "0"
        with self.assertRaises(ValueError):
            validate_native_cleanup(ready, broken, result, security)

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
                          "role": role, "source_revision": revision,
                          "development": False, "sha256": image_hash,
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
                relocated_paths = []
                original_commands = {}
                for role, filename in paths:
                    output = root / role
                    record = json.loads(Path(filename).read_text(encoding="utf-8"))
                    compile_commands = output / "compile_commands.json"
                    original_commands[role] = compile_commands.read_bytes()
                    commands = json.loads(compile_commands.read_text(encoding="utf-8"))
                    commands[0]["file"] = (
                        "D:/a/NU54DK_Arduino_Core/NU54DK_Arduino_Core/"
                        "tests/zephyr/m33_profile_hil/src/main.cpp"
                    )
                    compile_commands.write_text(
                        json.dumps(commands), encoding="utf-8"
                    )
                    record["image"] = f"D:/runner/records/{role}/image.hex"
                    for group in ("artifacts", "provenance"):
                        for name, descriptor in record[group].items():
                            descriptor["path"] = (
                                f"D:/runner/records/{role}/{Path(descriptor['path']).name}"
                            )
                            local = output / Path(descriptor["path"]).name
                            descriptor["sha256"] = hashlib.sha256(
                                local.read_bytes()
                            ).hexdigest()
                    record["command_identity"]["compile_commands_sha256"] = (
                        record["provenance"]["compile_commands"]["sha256"]
                    )
                    relocated = output / "build-record.json"
                    relocated.write_text(json.dumps(record), encoding="utf-8")
                    relocated_paths.append([role, str(relocated)])
                self.assertEqual(
                    set(load_build_identities(relocated_paths, "native", boards)),
                    set(boards),
                )
                relocated_server = Path(relocated_paths[0][1])
                relocated_record = json.loads(relocated_server.read_text())
                relocated_record["image"] = "D:/runner/records/server/wrong.hex"
                relocated_server.write_text(json.dumps(relocated_record), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "artifact path mismatch"):
                    load_build_identities(relocated_paths, "native", boards)
                for role, raw in original_commands.items():
                    (root / role / "compile_commands.json").write_bytes(raw)
                server_path = Path(paths[0][1])
                original = json.loads(server_path.read_text())
                for name, change in (("role", {**original, "role": "client"}),
                                     ("image", {**original, "sha256": "f" * 64}),
                                     ("development", {**original, "development": True})):
                    server_path.write_text(json.dumps(change), encoding="utf-8")
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        load_build_identities(paths, "native", boards)
                    server_path.write_text(json.dumps(original), encoding="utf-8")
                source.write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "source hash"):
                    load_build_identities(paths, "native", boards)

    def test_native_second_peer_compile_identity(self):
        with tempfile.TemporaryDirectory(prefix="nu54-native-second-peer-") as folder:
            root = Path(folder)
            source = root / "tests/zephyr/m33_profile_hil/src/main.cpp"
            source.parent.mkdir(parents=True)
            source.write_text("fixture", encoding="utf-8")
            revision = "a" * 40
            compile_commands = root / "compile_commands.json"
            command = (f'g++ -DM33_PROFILE_CORE_REVISION=\\"{revision}\\" '
                       '-DM33_PROFILE_ROLE=\\"watcher\\" -DM33_PROFILE_NATIVE=1 '
                       '-DM33_PROFILE_SECOND_PEER=1')
            compile_commands.write_text(json.dumps([{"file": str(source), "command": command}]),
                                        encoding="utf-8")
            validate_compile_identity(compile_commands, "native", "watcher", revision, root)
            compile_commands.write_text(json.dumps([{"file": str(source),
                                                       "command": command.replace(
                                                           " -DM33_PROFILE_SECOND_PEER=1", "")}]),
                                        encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "role macro"):
                validate_compile_identity(compile_commands, "native", "watcher", revision, root)

    def test_native_pair_rejects_missing_mismatch_and_replay(self):
        with tempfile.TemporaryDirectory(prefix="nu54-native-pair-") as folder:
            root = Path(folder)
            fresh_path = root / "fresh.json"
            restored_path = root / "restored.json"
            fresh = self.native_evidence("fresh", "1" * 32, "2026-10-03T01:00:00+00:00")
            self.attach_exact_bundle(root, fresh, "fresh")
            fresh_path.write_text(json.dumps(fresh), encoding="utf-8")
            fresh_hash = hashlib.sha256(fresh_path.read_bytes()).hexdigest()
            restored = self.native_evidence("restored", "2" * 32,
                                            "2026-10-03T01:01:00+00:00", fresh_hash)
            self.attach_exact_bundle(root, restored, "restored")
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

    def test_native_second_peer_predecessor_chain(self):
        """! @brief second-peer 실행이 직전 restored pair와 같은 주 peer에 묶이는지 검사합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-native-second-predecessor-") as folder:
            path = Path(folder) / "restored.json"
            evidence = self.native_evidence(
                "restored", "2" * 32, "2026-10-03T01:01:00+00:00", "f" * 64)
            self.attach_exact_bundle(path.parent, evidence, "restored")
            path.write_text(json.dumps(evidence), encoding="utf-8")
            boards = json.loads(json.dumps(evidence["boards"]))
            identities = json.loads(json.dumps(evidence["build_identity"]))
            boards["watcher"]["image_sha256"] = "e" * 64
            identities["watcher"] = {
                "manifest_sha256": "d" * 64,
                "image_sha256": boards["watcher"]["image_sha256"],
                "source_sha256": "c" * 64,
            }
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(validate_native_predecessor(
                path, evidence["revisions"], boards, identities, "restored"), expected)
            for name, mutate in (
                    ("missing-chain", lambda value: value.update(
                        native_prior_evidence_sha256=None)),
                    ("primary-build", lambda value: value["build_identity"]["server"].update(
                        source_sha256="0" * 64)),
                    ("denominator", lambda value: value["server"].update(native_links="2")),
                    ("watcher-probe", lambda value: value["boards"]["watcher"].update(
                        probe_sha256="0" * 64))):
                changed = json.loads(json.dumps(evidence))
                mutate(changed)
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_native_predecessor(
                        path, evidence["revisions"], boards, identities, "restored")

    def test_bms_persistence_predecessor_chain(self):
        """! @brief BMS restored 실행이 fresh 보존 실행과 동일한 image/probe인지 검사합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-bms-predecessor-") as folder:
            path = Path(folder) / "fresh.json"
            revisions = {"core": "b" * 40}
            boards = {role: {"probe_sha256": str(index) * 64,
                             "image_sha256": str(index + 3) * 64}
                      for index, role in enumerate(("server", "client", "watcher"), 1)}
            identities = {role: {"manifest_sha256": str(index + 6) * 64,
                                 "image_sha256": board["image_sha256"],
                                 "source_sha256": "a" * 64}
                          for index, (role, board) in enumerate(boards.items(), 1)}
            evidence = {
                "schema": "nucode-m33-profile-hil-v1", "family": "standard",
                "status": "PASS", "reason": None, "late_failures": [],
                "bms_persistence_phase": "fresh", "bms_prior_evidence_sha256": None,
                "revisions": revisions, "boards": boards, "build_identity": identities,
                "results": {
                    "client": {"profiles": "7", "measurements": "30", "rejected": "3",
                               "att_gap_rejects": "3", "bms_positive": "0",
                               "bms_client_cleanup": "0", "bms_teardown_errors": "0",
                               "bms_persistence_preserved": "1",
                               "bms_persistence_restored": "0"},
                    "watcher": {"profiles": "7", "measurements": "25", "rejected": "3",
                                "att_gap_rejects": "3"},
                },
                "server": {"max_links": "2", "email_deliveries": "5",
                           "alert_denied": "5", "bond_deletions": "0",
                           "bms_positive": "0", "bms_skipped": "0",
                           "bms_persistence_preserved": "1",
                           "bms_persistence_restored": "0",
                           "send_stats": {f"{slot}:{profile}": {"sent": "5", "no_ccc": "1"}
                                          for slot in range(2) for profile in range(5)},
                           "no_ccc_errors": "10", "pending_errors": "0",
                           "dropped_events": "0"},
                "bms_evidence": {
                    "BMS_READY": {"negative_checks": "2", "client_fresh": "1"},
                    "BMS_PRESERVED": {"fresh": "1", "bond_present": "1",
                                      "existing_unchanged": "1"},
                },
            }
            self.attach_exact_bundle(path.parent, evidence, "bms-fresh")
            path.write_text(json.dumps(evidence), encoding="utf-8")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(validate_bms_predecessor(
                path, revisions, boards, identities), expected)
            for name, mutate in (
                    ("not-preserved", lambda value: value["results"]["client"].update(
                        bms_persistence_preserved="0")),
                    ("handshake", lambda value: value["bms_evidence"].pop("BMS_PRESERVED")),
                    ("probe", lambda value: value["boards"]["server"].update(
                        probe_sha256="0" * 64)),
                    ("image", lambda value: value["build_identity"]["client"].update(
                        image_sha256="0" * 64))):
                changed = json.loads(json.dumps(evidence))
                mutate(changed)
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_bms_predecessor(path, revisions, boards, identities)

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
        pairing = source.split(
            "if (event.event == SecurityEvent::pairing_requested)", 1)[1].split(
                "if (!BLESecurity.acceptPairing(event.connection, true))", 1)[0]
        self.assertIn("identity_probe_mode", pairing)
        self.assertIn("BLESecurity.acceptPairing(event.connection, false)", pairing)
        self.assertIn("bms_persistence_restored_mode", pairing)
        self.assertIn("bms-restored-unexpected-pairing-request", pairing)
        scoped = source.split(
            '"M33PROFILE|1|CLEAN_PRIMARY|nonce="', 1
        )[1].split("#if !defined(M33_PROFILE_NATIVE)", 1)[0]
        self.assertIn("identity_primary_captured", scoped)
        self.assertIn("identity_primary_verified", scoped)
        self.assertIn("BLESecurity.eraseBond(identity_primary_address)", scoped)
        self.assertIn("startupBondsWithout(identity_primary_address)", scoped)
        self.assertIn("second_peer_preserved=1", scoped)
        self.assertNotIn("eraseAll", scoped)

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

    def test_bms_reboot_persistence_handshakes(self):
        ready = {"negative_checks": "2", "client_fresh": "1"}
        self.assertEqual(bms_transition(0, "client", "BMS_READY", ready, "fresh"),
                         (1, "server", "PRESERVE"))
        preserved = {key: "1" for key in ("fresh", "bond_present", "existing_unchanged")}
        self.assertEqual(bms_transition(1, "server", "BMS_PRESERVED", preserved, "fresh"),
                         (2, "client", "BMS_PRESERVED"))
        restored_ready = {"negative_checks": "2", "client_restored": "1",
                          "candidate": "1", "verified": "1"}
        self.assertEqual(bms_transition(0, "client", "BMS_RESTORED_READY",
                                        restored_ready, "restored"),
                         (1, "server", "ARM_RESTORED"))
        self.assertEqual(bms_transition(1, "server", "BMS_ARMED",
                                        {"fresh": "0", "restored": "1"}, "restored"),
                         (2, "client", "BMS_DELETE"))
        proof = {"accepted": "1", "fresh": "0", "restored": "1",
                 "watcher_unchanged": "1", "requester_absent": "1"}
        self.assertEqual(bms_transition(2, "server", "BMS_DELETED", proof, "restored"),
                         (3, "client", "BMS_DONE"))
        cleanup = {"fresh": "0", "restored": "1", "server_absent": "1",
                   "existing_unchanged": "1", "disconnected": "1"}
        self.assertEqual(bms_transition(3, "client", "BMS_CLEANED", cleanup, "restored"),
                         (5, "", ""))
        for broken in ({**restored_ready, "verified": "0"},
                       {**proof, "restored": "0"}, {**cleanup, "fresh": "1"}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                if "negative_checks" in broken:
                    bms_transition(0, "client", "BMS_RESTORED_READY", broken, "restored")
                elif "accepted" in broken:
                    bms_transition(2, "server", "BMS_DELETED", broken, "restored")
                else:
                    bms_transition(3, "client", "BMS_CLEANED", broken, "restored")

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
        sent.clear()
        start_roles("native", ports, b"start", lambda _: None, lambda *args: None,
                    native_second_peer=True)
        self.assertEqual(sent, ["server", "client"])

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

    def test_bms_reboot_persistence_denominators(self):
        results = {"client": {"profiles": "7", "measurements": "30", "rejected": "3",
                              "att_gap_rejects": "3", "bms_positive": "0",
                              "bms_client_cleanup": "0", "bms_teardown_errors": "0",
                              "bms_persistence_preserved": "1",
                              "bms_persistence_restored": "0"},
                   "watcher": {"profiles": "7", "measurements": "25", "rejected": "3",
                               "att_gap_rejects": "3"}}
        stats = {"max_links": "2", "email_deliveries": "5", "alert_denied": "5",
                 "bond_deletions": "0", "bms_positive": "0", "bms_skipped": "0",
                 "bms_persistence_preserved": "1", "bms_persistence_restored": "0",
                 "send_stats": {f"{slot}:{profile}": {"sent": "5", "no_ccc": "1"}
                                for slot in range(2) for profile in range(5)},
                 "no_ccc_errors": "10", "pending_errors": "0", "dropped_events": "0"}
        validate_results("standard", results, stats, "fresh")
        restored_results = {**results, "client": {**results["client"], "bms_positive": "1",
                                                    "bms_client_cleanup": "1",
                                                    "bms_persistence_preserved": "0",
                                                    "bms_persistence_restored": "1"}}
        restored_stats = {**stats, "bond_deletions": "1", "bms_positive": "1",
                          "bms_persistence_preserved": "0", "bms_persistence_restored": "1"}
        validate_results("standard", restored_results, restored_stats, "restored")
        with self.assertRaisesRegex(ValueError, "fresh reboot-preservation"):
            validate_results("standard", results,
                             {**stats, "bms_persistence_preserved": "0"}, "fresh")
        with self.assertRaisesRegex(ValueError, "unexpected bond deletion"):
            validate_results("standard", restored_results,
                             {**restored_stats, "bond_deletions": "0"}, "restored")

    def test_native_denominators(self):
        results = {"client": {"object_operations": "14", "glucose": "2", "native_checks": "7", "single_link": "1",
                              "native_sessions": "3", "normal_reconnects": "1", "coc_cancels": "1",
                              "cancel_reconnects": "1", "reconnect_reads": "1", "reconnect_writes": "1", "authenticated_links": "3"}}
        stats = {"object_writes": "3", "single_link": "1", "native_links": "3", "native_disconnects": "2", "authenticated_links": "3"}
        validate_results("native", results, stats)
        for key in results["client"]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_results("native", {"client": {**results["client"], key: "0"}}, stats)

    def test_native_second_peer_identity_denominators(self):
        results = {
            "server": {"identity_primary": "1", "identity_second_peer": "1",
                       "identities_distinct": "1", "restored_links": "2",
                       "passkey_events": "0", "existing_unchanged": "1",
                       "startup_bonds": "2"},
            "client": {"identity_primary": "1", "restored": "1",
                       "passkey_events": "0", "existing_unchanged": "1"},
            "watcher": {"identity_second_peer": "1", "restored": "1",
                        "passkey_events": "0", "existing_unchanged": "1"},
        }
        security = {
            "server": {"passkey_events": 0, "security_changed_levels": [4, 2],
                       "bond_restored_candidates": 2, "bond_verified": 2},
            "client": {"passkey_events": 0, "security_changed_levels": [4],
                       "bond_restored_candidates": 1, "bond_verified": 1},
            "watcher": {"passkey_events": 0, "security_changed_levels": [2],
                        "bond_restored_candidates": 1, "bond_verified": 1},
        }
        cleanup = {
            "server": {"removed": "1", "primary_absent": "1",
                       "existing_unchanged": "1", "second_peer_preserved": "1"},
            "client": {"removed": "1", "primary_absent": "1",
                       "existing_unchanged": "1",
                       "second_peer_preserved": "not_applicable"},
        }
        validate_second_peer(results, security, cleanup)
        for role, field, value in (("watcher", "restored", "0"),
                                   ("server", "startup_bonds", "1")):
            broken = json.loads(json.dumps(results))
            broken[role][field] = value
            with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                validate_second_peer(broken, security, cleanup)
        broken_security = json.loads(json.dumps(security))
        broken_security["watcher"]["bond_restored_candidates"] = 0
        with self.assertRaisesRegex(ValueError, "security events"):
            validate_second_peer(results, broken_security, cleanup)
        for name, mutate in (
                ("missing-client", lambda value: value.pop("client")),
                ("server-second", lambda value: value["server"].update(
                    second_peer_preserved="0")),
                ("client-history", lambda value: value["client"].update(
                    existing_unchanged="0"))):
            broken_cleanup = json.loads(json.dumps(cleanup))
            mutate(broken_cleanup)
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_primary_cleanup(broken_cleanup)

    def test_native_identity_readiness_denominators(self):
        """! @brief identity 단계 전환이 복원과 bond 불변 증거 없이는 진행되지 않는지 검사합니다. """
        primary = {key: "1" for key in
                   ("restored", "candidate", "verified", "existing_unchanged")}
        primary.update(passkey_events="0", peer_distinct="0", startup_bonds="2")
        validate_identity_readiness("server", primary, False)
        validate_identity_readiness("client", {**primary, "startup_bonds": "1"}, False)
        second = {**primary, "peer_distinct": "1"}
        validate_identity_readiness("server", second, True)
        validate_identity_readiness("watcher", {**second, "startup_bonds": "1"}, True)
        for name, role, value, is_second in (
                ("candidate", "server", {**primary, "candidate": "0"}, False),
                ("distinct", "watcher", {**second, "peer_distinct": "0"}, True),
                ("server-bonds", "server", {**second, "startup_bonds": "1"}, True),
                ("role", "client", second, True)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_identity_readiness(role, value, is_second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
