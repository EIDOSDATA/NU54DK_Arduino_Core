"""! @brief Profile 20-cycle aggregate가 phase 재사용과 scoped cleanup 위조를 거부하는지 검사합니다. """
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hil/nu54dk"))
from m33_profile_campaign import (EXPECTED_CYCLES, SCHEMA, SEMANTICS,
                                  ROOT as CAMPAIGN_ROOT, execute_campaign,
                                  final_hardware,
                                  validate_campaign_evidence)
import m33_profile_campaign as campaign_runner


REVISION = "b" * 40


def digest(path: Path) -> str:
    """! @brief fixture byte hash를 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProfileCampaignTests(unittest.TestCase):
    def revisions(self) -> dict[str, str]:
        """! @brief 현재 NCS 3.4.0 lock의 full revision fixture를 반환합니다. """
        lock = json.loads(
            (CAMPAIGN_ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(
                encoding="utf-8"
            )
        )
        return {
            "core": getattr(self, "revision", REVISION),
            "board": lock["board"]["revision"],
            "ncs": lock["ncs"]["revision"],
            "zephyr": lock["zephyr"]["revision"],
        }

    def build_record(self, root: Path, stem: str, role: str, family: str,
                     image: Path) -> tuple[Path, dict[str, str]]:
        """! @brief aggregate가 재검증할 canonical build provenance를 만듭니다. """
        cache = getattr(self, "_build_record_cache", {})
        cache_key = (root.resolve(), family, role)
        if cache_key in cache:
            return cache[cache_key]
        revision = getattr(self, "revision", REVISION)
        prefix = root / f"{stem}.{role}.build"
        elf = prefix.with_suffix(".elf")
        config = root / f"{stem}.{role}.config"
        sysbuild = root / f"{stem}.{role}.sysbuild"
        commands = root / f"{stem}.{role}.compile-commands.json"
        build_info = root / f"{stem}.{role}.build-info.yml"
        elf.write_bytes(b"profile-test-elf")
        config.write_text("CONFIG_SOC_NRF54L15_CPUAPP=y\n", encoding="utf-8")
        sysbuild.write_text("SB_CONFIG_FLPRCORE_NONE=y\n", encoding="utf-8")
        source = CAMPAIGN_ROOT / "tests/zephyr/m33_profile_hil/src/main.cpp"
        command = (f'g++ -DM33_PROFILE_CORE_REVISION=\\"{revision}\\" '
                   f'-DM33_PROFILE_ROLE=\\"{role}\\"')
        if family == "native":
            command += " -DM33_PROFILE_NATIVE=1"
        if role == "server":
            command += " -DM33_PROFILE_SERVER=1"
        elif role == "watcher":
            command += (" -DM33_PROFILE_SECOND_PEER=1" if family == "native"
                        else " -DM33_PROFILE_WATCHER=1")
        commands.write_text(json.dumps([{
            "file": str(source), "command": command,
        }]), encoding="utf-8")
        build_info.write_text("version: test\n", encoding="utf-8")

        def descriptor(value: Path) -> dict[str, str]:
            return {"path": str(value), "sha256": digest(value)}

        sources = {
            source.relative_to(CAMPAIGN_ROOT).as_posix(): digest(source),
        }
        image_hash = digest(image)
        record = {
            "schema": "nucode-m33-profile-build-v1",
            "family": family,
            "role": role,
            "source_revision": revision,
            "development": False,
            "sha256": image_hash,
            "image": str(image),
            "owned_source_sha256": sources,
            "command_identity": {
                "sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "compile_commands_sha256": digest(commands),
                "build_info_sha256": digest(build_info),
            },
            "artifacts": {
                "elf": descriptor(elf),
                "config": descriptor(config),
                "sysbuild": descriptor(sysbuild),
            },
            "provenance": {
                "compile_commands": descriptor(commands),
                "build_info": descriptor(build_info),
            },
        }
        path = root / f"{stem}.{role}.build.json"
        path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        identity = {
            "manifest_sha256": digest(path),
            "image_sha256": image_hash,
            "source_sha256": hashlib.sha256(json.dumps(
                sources, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest(),
        }
        cache[cache_key] = (path, identity)
        self._build_record_cache = cache
        return path, identity

    @staticmethod
    def write_program_fixture(image: Path, readback: Path, role: str,
                              probe: str) -> tuple[str, str]:
        """! @brief 유효한 Intel HEX와 exact range readback을 기록합니다. """
        image.write_text(":080000000102030405060708D4\n:00000001FF\n", encoding="ascii")
        image_hash = digest(image)
        range_hash = hashlib.sha256(b"\x01\x02\x03\x04\x05\x06\x07\x08").hexdigest()
        readback.write_text(json.dumps({
            "schema_version": 1,
            "kind": "m33_exact_program_readback",
            "status": "PASS",
            "role": role,
            "probe_sha256": probe,
            "image_sha256": image_hash,
            "backend": "pyocd-live-target",
            "halted": True,
            "resumed": True,
            "pre_state": "RUNNING",
            "post_state": "RUNNING",
            "restored": True,
            "ranges": [{"start": 0, "length": 8,
                        "expected_sha256": range_hash,
                        "observed_sha256": range_hash, "status": "PASS"}],
        }, sort_keys=True), encoding="utf-8")
        return image_hash, digest(readback)

    def standard_phase(self, root: Path, stem: str, phase: str, nonce: str,
                       observed: str, prior: str | None) -> tuple[Path, dict]:
        """! @brief standard BMS fresh/restored phase의 실제 raw denominator fixture를 만듭니다. """
        roles = ("server", "client", "watcher")
        boards = {role: {"probe_sha256": str(index) * 64, "image_sha256": ""}
                  for index, role in enumerate(roles, 1)}
        builds = {}
        exact = {}
        for role in roles:
            image = root / f"{stem}.{role}.image.hex"
            readback = root / f"{stem}.{role}.readback.json"
            image_hash, readback_hash = self.write_program_fixture(
                image, readback, role, boards[role]["probe_sha256"]
            )
            build, builds[role] = self.build_record(
                root, stem, role, "standard", image
            )
            boards[role]["image_sha256"] = image_hash
            exact[role] = {
                "probe_sha256": boards[role]["probe_sha256"],
                "image": {"path": image.name, "sha256": image_hash},
                "build_record": {"path": build.name, "sha256": digest(build)},
                "flash": {"mode": "pyocd-sector", "programmed_bytes": 8,
                          "erase": "sector", "auto_unlock": False,
                          "mass_erase": False, "automatic_recover": False},
                "readback": {"path": readback.name, "sha256": readback_hash},
            }
        restored = phase == "restored"
        results = {
            "client": {"nonce": nonce, "profiles": "7", "measurements": "30",
                       "rejected": "3", "att_gap_rejects": "3",
                       "bms_positive": "1" if restored else "0",
                       "bms_client_cleanup": "1" if restored else "0",
                       "bms_teardown_errors": "0",
                       "bms_persistence_preserved": "0" if restored else "1",
                       "bms_persistence_restored": "1" if restored else "0"},
            "watcher": {"profiles": "7", "measurements": "25",
                        "rejected": "3", "att_gap_rejects": "3"},
        }
        server = {
            "max_links": "2", "email_deliveries": "5", "alert_denied": "5",
            "bond_deletions": "1" if restored else "0",
            "bms_positive": "1" if restored else "0", "bms_skipped": "0",
            "bms_persistence_preserved": "0" if restored else "1",
            "bms_persistence_restored": "1" if restored else "0",
            "send_stats": {f"{slot}:{profile}": {"sent": "5", "no_ccc": "1"}
                           for slot in range(2) for profile in range(5)},
            "no_ccc_errors": "10", "pending_errors": "0", "dropped_events": "0",
        }
        bms = ({
            "BMS_RESTORED_READY": {"negative_checks": "2", "client_restored": "1",
                                   "candidate": "1", "verified": "1"},
            "BMS_ARMED": {"fresh": "0", "restored": "1"},
            "BMS_DELETED": {"accepted": "1", "fresh": "0", "restored": "1",
                            "watcher_unchanged": "1", "requester_absent": "1"},
            "BMS_CLEANED": {"fresh": "0", "restored": "1", "server_absent": "1",
                            "existing_unchanged": "1", "disconnected": "1"},
        } if restored else {
            "BMS_READY": {"negative_checks": "2", "client_fresh": "1"},
            "BMS_PRESERVED": {"fresh": "1", "bond_present": "1",
                              "existing_unchanged": "1"},
        })
        cleanup = {role: {"nonce": nonce, "native_links": "0", "links": "0",
                          "pending": "0", "scan": "0", "advertising": "0",
                          "watchdog": "0", "serial_close": "PASS"} for role in roles}
        transcript = root / f"{stem}.transcript.log"
        transcript.write_text(f"phase:{stem}\n", encoding="ascii")
        evidence = {
            "schema": "nucode-m33-profile-hil-v1", "family": "standard",
            "status": "PASS", "reason": None, "late_failures": [],
            "development": False, "bms_persistence_phase": phase,
            "bms_prior_evidence_sha256": prior, "results": results,
            "server": server, "bms_evidence": bms, "cleanup": cleanup,
            "revisions": self.revisions(),
            "boards": boards, "build_identity": builds,
            "observed_utc": observed, "exact_program": exact,
            "transcript_sha256": digest(transcript),
            "transcript": {"path": transcript.name, "sha256": digest(transcript)},
        }
        path = root / f"{stem}.json"
        path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
        return path, evidence

    def phase(self, root: Path, stem: str, phase: str, nonce: str,
              observed: str, prior: str | None) -> tuple[Path, dict]:
        """! @brief native phase validator를 통과하는 content-addressed fixture를 만듭니다. """
        second = phase == "second-peer"
        roles = ("server", "client", "watcher")
        boards = {
            role: {"probe_sha256": str(index) * 64, "image_sha256": ""}
            for index, role in enumerate(roles, 1)
        }
        builds = {}
        exact = {}
        for role in roles:
            family = "native" if role != "watcher" or second else "standard"
            image = root / f"{stem}.{role}.image.hex"
            readback = root / f"{stem}.{role}.readback.json"
            image_hash, readback_hash = self.write_program_fixture(
                image, readback, role, boards[role]["probe_sha256"]
            )
            build, builds[role] = self.build_record(
                root, stem, role, family, image
            )
            boards[role]["image_sha256"] = image_hash
            exact[role] = {
                "probe_sha256": boards[role]["probe_sha256"],
                "image": {"path": image.name, "sha256": image_hash},
                "build_record": {"path": build.name, "sha256": digest(build)},
                "flash": {"mode": "pyocd-sector", "programmed_bytes": 8,
                          "erase": "sector", "auto_unlock": False,
                          "mass_erase": False, "automatic_recover": False},
                "readback": {"path": readback.name, "sha256": readback_hash},
            }
        cleanup = {
            role: {"nonce": nonce, "native_links": "0", "links": "0",
                   "pending": "0", "scan": "0", "advertising": "0",
                   "watchdog": "0", "serial_close": "PASS"}
            for role in roles
        }
        if second:
            results = {
                "server": {"nonce": nonce, "identity_primary": "1",
                           "identity_second_peer": "1", "identities_distinct": "1",
                           "restored_links": "2", "passkey_events": "0",
                           "existing_unchanged": "1", "startup_bonds": "2"},
                "client": {"nonce": nonce, "identity_primary": "1", "restored": "1",
                           "passkey_events": "0", "existing_unchanged": "1"},
                "watcher": {"nonce": nonce, "identity_second_peer": "1",
                            "restored": "1", "passkey_events": "0",
                            "existing_unchanged": "1"},
            }
            security = {
                "server": {"passkey_events": 0, "security_changed_levels": [4, 2],
                           "bond_restored_candidates": 2, "bond_verified": 2},
                "client": {"passkey_events": 0, "security_changed_levels": [4],
                           "bond_restored_candidates": 1, "bond_verified": 1},
                "watcher": {"passkey_events": 0, "security_changed_levels": [2],
                            "bond_restored_candidates": 1, "bond_verified": 1},
            }
            identity_cleanup = {
                "server": {"removed": "1", "primary_absent": "1",
                           "existing_unchanged": "1", "second_peer_preserved": "1"},
                "client": {"removed": "1", "primary_absent": "1",
                           "existing_unchanged": "1",
                           "second_peer_preserved": "not_applicable"},
            }
            server = {}
        else:
            passkeys = "1" if phase == "fresh" else "0"
            restored_count = 0 if phase == "fresh" else 3
            result = {"nonce": nonce, "passkey_events": passkeys,
                      "object_operations": "14", "glucose": "2", "native_checks": "7",
                      "single_link": "1", "native_sessions": "3",
                      "normal_reconnects": "1", "coc_cancels": "1",
                      "cancel_reconnects": "1", "reconnect_reads": "1",
                      "reconnect_writes": "1", "authenticated_links": "3"}
            results = {"client": result}
            server = {"passkey_events": passkeys, "object_writes": "3",
                      "single_link": "1", "native_links": "3",
                      "native_disconnects": "2", "authenticated_links": "3"}
            security = {
                role: {"passkey_events": int(passkeys),
                       "security_changed_levels": [4, 4, 4],
                       "bond_restored_candidates": restored_count,
                       "bond_verified": restored_count}
                for role in ("server", "client")
            }
            identity_cleanup = {}
        transcript = root / f"{stem}.transcript.log"
        transcript.write_text(f"phase:{stem}\n", encoding="ascii")
        evidence = {
            "schema": "nucode-m33-profile-hil-v1", "family": "native",
            "status": "PASS", "reason": None, "late_failures": [],
            "development": False, "native_security_phase": phase,
            "native_prior_evidence_sha256": prior,
            "native_security": security, "identity_cleanup": identity_cleanup,
            "results": results, "server": server, "cleanup": cleanup,
            "revisions": self.revisions(), "boards": boards,
            "build_identity": builds, "observed_utc": observed,
            "exact_program": exact, "transcript_sha256": digest(transcript),
            "transcript": {"path": transcript.name, "sha256": digest(transcript)},
        }
        path = root / f"{stem}.json"
        path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
        return path, evidence

    def campaign(self, root: Path, revision: str = REVISION) -> Path:
        """! @brief 20개 fresh→restored→second-peer 실제 byte chain fixture를 만듭니다. """
        self.revision = revision
        base = datetime(2026, 10, 4, tzinfo=timezone.utc)
        records = []
        final = None
        boards = None
        builds = None
        for cycle in range(1, EXPECTED_CYCLES + 1):
            refs = []
            fresh_path, _ = self.phase(
                root, f"c{cycle:02d}-fresh", "fresh", f"{cycle * 3 - 2:032x}",
                (base + timedelta(minutes=cycle * 3 - 2)).isoformat(), None
            )
            fresh_hash = digest(fresh_path)
            restored_path, _ = self.phase(
                root, f"c{cycle:02d}-restored", "restored", f"{cycle * 3 - 1:032x}",
                (base + timedelta(minutes=cycle * 3 - 1)).isoformat(), fresh_hash
            )
            restored_hash = digest(restored_path)
            second_path, final = self.phase(
                root, f"c{cycle:02d}-second", "second-peer", f"{cycle * 3:032x}",
                (base + timedelta(minutes=cycle * 3)).isoformat(), restored_hash
            )
            for phase_path in (fresh_path, restored_path, second_path):
                value = json.loads(phase_path.read_text(encoding="utf-8"))
                refs.append({"path": phase_path.name, "sha256": digest(phase_path),
                             "nonce": value["results"]["client"]["nonce"],
                             "observed_utc": value["observed_utc"]})
            if boards is None:
                boards = {"server": final["boards"]["server"],
                          "client": final["boards"]["client"],
                          "second_peer": final["boards"]["watcher"]}
                builds = {"server": final["build_identity"]["server"],
                          "client": final["build_identity"]["client"],
                          "second_peer": final["build_identity"]["watcher"]}
            records.append({
                "cycle": cycle, "status": "PASS",
                "semantics": {token: "PASS" for token in SEMANTICS["native"]},
                "previous_cycle_closure_sha256": (
                    None if cycle == 1 else records[-1]["phases"][-1]["sha256"]
                ),
                "phases": refs,
            })
        hardware = final_hardware(final, "native")
        attestation_records = [
            {"cycle": cycle, "status": "PASS",
             "semantics": {token: "PASS" for token in SEMANTICS["native"]}}
            for cycle in range(1, EXPECTED_CYCLES + 1)
        ]
        campaign = {
            "schema": SCHEMA, "family": "native", "status": "PASS",
            "source_clean": True, "revisions": self.revisions(),
            "cycles": EXPECTED_CYCLES, "boards": boards,
            "build_identity": builds, "cycle_records": records,
            "m33_dispatch_attestation": {
                "schema_version": 1, "kind": "m33_native_campaign_attestation",
                "campaign_id": "m33_profiles_native", "source_revision": revision,
                "source_clean": True,
                "semantic_status": {token: "PASS" for token in SEMANTICS["native"]},
                "cycle_records": attestation_records, "hardware": hardware,
            },
        }
        path = root / "campaign.json"
        path.write_text(json.dumps(campaign, sort_keys=True), encoding="utf-8")
        return path

    def standard_campaign(self, root: Path, revision: str = REVISION) -> Path:
        """! @brief 20개 fresh→reboot→restored BMS chain fixture를 만듭니다. """
        self.revision = revision
        base = datetime(2026, 10, 4, tzinfo=timezone.utc)
        records = []
        final = None
        for cycle in range(1, EXPECTED_CYCLES + 1):
            fresh_path, _ = self.standard_phase(
                root, f"s{cycle:02d}-fresh", "fresh", f"{cycle * 2 - 1:032x}",
                (base + timedelta(minutes=cycle * 2 - 1)).isoformat(), None
            )
            restored_path, final = self.standard_phase(
                root, f"s{cycle:02d}-restored", "restored", f"{cycle * 2:032x}",
                (base + timedelta(minutes=cycle * 2)).isoformat(), digest(fresh_path)
            )
            refs = []
            for phase_path in (fresh_path, restored_path):
                value = json.loads(phase_path.read_text(encoding="utf-8"))
                refs.append({"path": phase_path.name, "sha256": digest(phase_path),
                             "nonce": value["results"]["client"]["nonce"],
                             "observed_utc": value["observed_utc"]})
            records.append({
                "cycle": cycle, "status": "PASS",
                "semantics": {token: "PASS" for token in SEMANTICS["standard"]},
                "previous_cycle_closure_sha256": (
                    None if cycle == 1 else records[-1]["phases"][-1]["sha256"]
                ), "phases": refs,
            })
        attestation_records = [
            {"cycle": cycle, "status": "PASS",
             "semantics": {token: "PASS" for token in SEMANTICS["standard"]}}
            for cycle in range(1, EXPECTED_CYCLES + 1)
        ]
        campaign = {
            "schema": SCHEMA, "family": "standard", "status": "PASS",
            "source_clean": True, "revisions": self.revisions(),
            "cycles": EXPECTED_CYCLES, "boards": final["boards"],
            "build_identity": final["build_identity"], "cycle_records": records,
            "m33_dispatch_attestation": {
                "schema_version": 1, "kind": "m33_native_campaign_attestation",
                "campaign_id": "m33_profiles_standard", "source_revision": revision,
                "source_clean": True,
                "semantic_status": {token: "PASS" for token in SEMANTICS["standard"]},
                "cycle_records": attestation_records,
                "hardware": final_hardware(final, "standard"),
            },
        }
        path = root / "standard-campaign.json"
        path.write_text(json.dumps(campaign, sort_keys=True), encoding="utf-8")
        return path

    def test_native_twenty_cycle_chain_and_scoped_cleanup(self):
        """! @brief 60개 물리 phase와 20개 primary-only cleanup chain을 승인합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-profile-campaign-") as folder:
            root = Path(folder)
            path = self.campaign(root)
            self.assertEqual(
                EXPECTED_CYCLES,
                validate_campaign_evidence(path, "native", REVISION)["cycles"]
            )
            campaign = json.loads(path.read_text(encoding="utf-8"))
            last_ref = campaign["cycle_records"][-1]["phases"][-1]
            phase_path = root / last_ref["path"]
            phase = json.loads(phase_path.read_text(encoding="utf-8"))
            phase["identity_cleanup"]["server"]["second_peer_preserved"] = "0"
            phase_path.write_text(json.dumps(phase, sort_keys=True), encoding="utf-8")
            last_ref["sha256"] = digest(phase_path)
            path.write_text(json.dumps(campaign, sort_keys=True), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scoped cleanup"):
                validate_campaign_evidence(path, "native", REVISION)

    def test_standard_twenty_cycle_chain_and_tamper_boundaries(self):
        """! @brief standard 40 phase와 predecessor/probe/readback/cleanup 조작 거부를 고정합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-profile-standard-") as folder:
            root = Path(folder)
            path = self.standard_campaign(root)
            self.assertEqual(
                EXPECTED_CYCLES,
                validate_campaign_evidence(path, "standard", REVISION)["cycles"]
            )
            original_campaign = path.read_bytes()
            campaign = json.loads(original_campaign)
            reference = campaign["cycle_records"][-1]["phases"][-1]
            phase_path = root / reference["path"]
            original_phase = phase_path.read_bytes()
            phase = json.loads(original_phase)
            readback_ref = phase["exact_program"]["server"]["readback"]
            readback_path = root / readback_ref["path"]
            original_readback = readback_path.read_bytes()

            def reject(name, mutate_phase=None, mutate_readback=None,
                       rebind_readback=False, pattern=""):
                phase_path.write_bytes(original_phase)
                readback_path.write_bytes(original_readback)
                value = json.loads(original_phase)
                if mutate_phase is not None:
                    mutate_phase(value)
                if mutate_readback is not None:
                    mutate_readback(readback_path)
                    if rebind_readback:
                        value["exact_program"]["server"]["readback"]["sha256"] = \
                            digest(readback_path)
                phase_path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
                aggregate = json.loads(original_campaign)
                aggregate["cycle_records"][-1]["phases"][-1]["sha256"] = digest(phase_path)
                path.write_text(json.dumps(aggregate, sort_keys=True), encoding="utf-8")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, pattern):
                    validate_campaign_evidence(path, "standard", REVISION)

            reject("predecessor", lambda value: value.update(
                bms_prior_evidence_sha256="0" * 64), pattern="predecessor")
            reject("probe", lambda value: value["boards"]["server"].update(
                probe_sha256="f" * 64), pattern="probe")
            reject("readback", mutate_readback=lambda target: target.write_bytes(b"tampered"),
                   pattern="readback byte")
            reject("cleanup", lambda value: value["cleanup"]["server"].update(links="1"),
                   pattern="STOP cleanup")
            reject("serial-close", lambda value: value["cleanup"]["server"].update(
                serial_close="FAIL"), pattern="STOP cleanup")
            reject("programmed-bytes", lambda value: value["exact_program"]["server"][
                "flash"].update(programmed_bytes=7), pattern="sector program")

            def alter_readback_backend(target: Path) -> None:
                value = json.loads(target.read_text(encoding="utf-8"))
                value["backend"] = "claimed"
                target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            reject("readback-backend", mutate_readback=alter_readback_backend,
                   rebind_readback=True, pattern="programmed readback")

            def forge_build(value: dict) -> None:
                program = value["exact_program"]["server"]
                original = root / program["build_record"]["path"]
                build = json.loads(original.read_text(encoding="utf-8"))
                config = root / "forged.config"
                config.write_text("CONFIG_SOC_NRF54L15_CPUAPP=n\n", encoding="utf-8")
                build["artifacts"]["config"] = {
                    "path": str(config), "sha256": digest(config),
                }
                forged = root / "forged-build.json"
                forged.write_text(json.dumps(build, sort_keys=True), encoding="utf-8")
                program["build_record"] = {
                    "path": forged.name, "sha256": digest(forged),
                }
                value["build_identity"]["server"]["manifest_sha256"] = digest(forged)

            reject("build-provenance", forge_build, pattern="target configuration")

            aggregate = json.loads(original_campaign)
            aggregate["revisions"]["board"] = "f" * 40
            path.write_text(json.dumps(aggregate, sort_keys=True), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity"):
                validate_campaign_evidence(path, "standard", REVISION)

    def test_execution_rejects_reduced_denominator(self):
        """! @brief 19회나 preflight를 물리 20-cycle PASS로 승격하지 않습니다. """
        args = argparse.Namespace(cycles=19, execute=True)
        with self.assertRaisesRegex(ValueError, "20-cycle"):
            execute_campaign(args)

    def test_execution_writes_every_phase_without_clobber(self):
        """! @brief 실제 실행기를 40/60회 연결하고 점을 포함한 phase 경로와 원본 보존을 검증합니다. """
        for family, phase_count in (("standard", 40), ("native", 60)):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                temporary_root = Path(folder)
                (temporary_root / "path-alias").mkdir()
                ## @note Windows 8.3 여부와 무관하게 비정규 표기를 정규화하는 경계를 검사합니다.
                root = (temporary_root / "path-alias" / "..").resolve()
                self._build_record_cache = {}
                roles = []
                records = []
                for index, role in enumerate(("server", "client", "watcher"), 1):
                    image = root / f"input-{role}.hex"
                    record = root / f"input-{role}.json"
                    image.write_bytes(b"mock physical input")
                    record.write_bytes(b"mock physical provenance")
                    roles.append([role, str(index) * 64, str(image)])
                    records.append([role, str(record)])
                args = argparse.Namespace(
                    family=family, cycles=20, execute=True,
                    output=root / "release.v1.campaign.json", role=roles,
                    build_record=records, sdk_root=root / "mock-sdk",
                    second_peer_role=(roles[-1][1:] if family == "native" else None),
                    second_peer_build_record=(Path(records[-1][1]) if family == "native" else None),
                )
                calls = []
                generated = {}
                base = datetime(2026, 10, 4, tzinfo=timezone.utc)

                def execute_phase(phase_args):
                    """! @brief 물리 접근만 대체하고 실제 phase runner의 no-clobber 파일 규칙을 적용합니다. """
                    path = phase_args.output_prefix.with_suffix(".json")
                    self.assertFalse(path.exists(), f"phase output collision: {path.name}")
                    for previous_path, previous_bytes in generated.items():
                        self.assertEqual(previous_bytes, previous_path.read_bytes())
                    phase = (phase_args.native_security_phase if family == "native"
                             else phase_args.bms_persistence_phase)
                    predecessor = (phase_args.native_prior_evidence if family == "native"
                                   else phase_args.bms_prior_evidence)
                    prior = digest(predecessor) if predecessor is not None else None
                    number = len(calls) + 1
                    factory = self.phase if family == "native" else self.standard_phase
                    actual_path, evidence = factory(
                        root, path.stem, phase, f"{number:032x}",
                        (base + timedelta(minutes=number)).isoformat(), prior,
                    )
                    self.assertEqual(path, actual_path)
                    generated[path] = path.read_bytes()
                    calls.append(phase)
                    return evidence

                prefixes = campaign_runner.planned_phase_prefixes(args.output, family)
                final_phase = "second-peer" if family == "native" else "restored"
                final_path = prefixes[(20, final_phase)].with_suffix(".json")
                final_sidecars = campaign_runner.phase_runner.reserve_sidecars(
                    final_path, ("server", "client", "watcher")
                )
                reserved_paths = [
                    args.output, final_path, final_path.with_suffix(".transcript.log"),
                    *final_sidecars["watcher"].values(),
                ]
                for reserved_path in reserved_paths:
                    reserved_path.write_bytes(b"existing evidence must remain unchanged")
                    forbidden_phase = mock.Mock(side_effect=AssertionError("physical phase started"))
                    with (
                        mock.patch.object(campaign_runner, "source_is_clean", return_value=True),
                        mock.patch.object(campaign_runner, "git_revision", return_value=REVISION),
                        self.assertRaises((ValueError, RuntimeError)),
                    ):
                        execute_campaign(args, execute_phase=forbidden_phase)
                    forbidden_phase.assert_not_called()
                    self.assertEqual(
                        b"existing evidence must remain unchanged", reserved_path.read_bytes()
                    )
                    reserved_path.unlink()

                with (
                    mock.patch.object(campaign_runner, "source_is_clean", return_value=True),
                    mock.patch.object(campaign_runner, "git_revision", return_value=REVISION),
                ):
                    result = execute_campaign(args, execute_phase=execute_phase)
                self.assertEqual("PASS", result["status"])
                self.assertEqual(phase_count, len(calls))
                self.assertEqual(phase_count, len(generated))
                self.assertEqual(20, len(result["cycle_records"]))
                for path, raw in generated.items():
                    self.assertEqual(raw, path.read_bytes())

                args.output = root / "source.drift.json"
                with (
                    mock.patch.object(campaign_runner, "source_is_clean", side_effect=[True, False]),
                    mock.patch.object(campaign_runner, "git_revision", return_value=REVISION),
                    self.assertRaisesRegex(ValueError, "source changed"),
                ):
                    execute_campaign(args, execute_phase=execute_phase)
                self.assertFalse(args.output.exists())
                self.assertEqual(phase_count * 2, len(calls))
                for path, raw in generated.items():
                    self.assertEqual(raw, path.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
