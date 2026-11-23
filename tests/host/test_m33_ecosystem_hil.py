#!/usr/bin/env python3
"""! @brief 합성 peer HIL의 identity·분모·실물 증거 fail-closed 경계를 검사합니다. """
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ecosystem_hil", ROOT / "tools/bluetooth/m33_ecosystem_hil.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
IDENTITY = "a" * 40 + "b" * 64
NONCE = "0123456789abcdef" * 2


class EcosystemHilTests(unittest.TestCase):
    """! @brief 실제 firmware protocol과 같은 byte record를 검사합니다. """

    def line(self, case="ancs", role="client", security_mode="fresh", event="PASS",
             nonce=NONCE):
        """! @brief 독립 기준표로 정확한 정상 결과 record를 만듭니다. """
        expected = {
            ("access_denied", "client"): (0, 0, 0, 1),
            ("access_denied", "peer"): (0, 0, 0, 1),
            ("ancs", "client"): (1, 1, 2, 1), ("ancs", "peer"): (1, 1, 2, 0),
            ("ams", "client"): (1, 1, 2, 1), ("ams", "peer"): (1, 0, 3, 0),
            ("ancs_bad", "client"): (0, 0, 0, 2), ("ancs_bad", "peer"): (1, 0, 0, 1),
            ("ams_bad", "client"): (0, 0, 1, 2), ("ams_bad", "peer"): (1, 0, 1, 1),
        }
        security = {
            "denied": (0, 0, 0, 0, 1, 0),
            "fresh": (1, 1, 1, 0, 0, 1),
            "reconnect": (1, 0, 1, 1, 0, 1),
            "cleaned": (0, 0, 0, 0, 0, 0),
        }
        packet, attributes, writes, negative = expected[(case, role)]
        secured, pairings, bonded, reconnects, rejects, test_bond = security[security_mode]
        if security_mode == "denied" and role == "client":
            rejects = 0
        return (f"M33ECO|2|{event}|role={role}|nonce={nonce}|case={case}|revision={IDENTITY[:40]}"
                f"|identity={IDENTITY}|packets={packet}|attributes={attributes}|writes={writes}"
                f"|negative={negative}|links={0 if event == 'CLEANED' else 1}"
                f"|security={secured}|pairings={pairings}|bonded={bonded}"
                f"|reconnects={reconnects}|security_rejects={rejects}|test_bond={test_bond}")

    def test_all_roles_and_cases_have_exact_denominators(self):
        """! @brief 정상·보안 거부·malformed 하위 case를 분리하고 허위 성공을 거부합니다. """
        for case in MODULE.CASES:
            for role in MODULE.ROLES:
                with self.subTest(case=case, role=role):
                    mode = "denied" if case == "access_denied" else "fresh"
                    record = MODULE.parse(self.line(case, role, mode), role, IDENTITY)
                    MODULE.validate_pass(record, case, role, NONCE, mode)
                    record["negative"] += 1
                    with self.assertRaises(ValueError):
                        MODULE.validate_pass(record, case, role, NONCE, mode)
        for case in ("ancs", "ams", "ancs_bad", "ams_bad"):
            for role in MODULE.ROLES:
                with self.subTest(case=case, role=role, mode="reconnect"):
                    record = MODULE.parse(self.line(case, role, "reconnect"), role, IDENTITY)
                    MODULE.validate_pass(record, case, role, NONCE, "reconnect")

    def test_regression_schedule_requires_twenty_ancs_and_ams_cycles(self):
        """! @brief ANCS·AMS 각 20회와 malformed 각 2회를 누락·중복 없이 고정합니다. """
        schedule = MODULE.regression_schedule()
        cases = [{"cycle": 0, "case": "access_denied", "status": "PASS"}]
        cases.extend(
            {"cycle": cycle, "case": case, "status": "PASS"}
            for cycle, case, _security in schedule
        )
        self.assertEqual(
            MODULE.validate_case_denominators(cases),
            {"access_denied": 1, "ancs": 20, "ams": 20,
             "ancs_bad": 2, "ams_bad": 2},
        )
        self.assertEqual(len(schedule), 44)
        self.assertEqual(schedule[0], (1, "ancs", "fresh"))
        self.assertTrue(all(
            security == "reconnect"
            for cycle, case, security in schedule
            if not (cycle == 1 and case == "ancs")
        ))
        with self.assertRaisesRegex(ValueError, "denominator"):
            MODULE.validate_case_denominators(cases[:-1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE.validate_case_denominators(cases + [dict(cases[-1])])

    def test_exact_test_bond_cleanup_record(self):
        """! @brief 시험 소유 bond 제거는 link·보안·소유 표식 0을 모두 요구합니다. """
        original = self.line("ancs", "client", "cleaned", "CLEANED")
        record = MODULE.parse(original, "client", IDENTITY)
        MODULE.validate_cleanup(record, "client", NONCE)
        for key in ("links", "bonded", "test_bond"):
            changed = dict(record)
            changed[key] = 1
            with self.assertRaises(ValueError):
                MODULE.validate_cleanup(changed, "client", NONCE)

    def test_stale_nonce_wrong_image_role_duplicate_and_missing_field(self):
        """! @brief 다른 session/image와 조작된 protocol은 증거에 채택하지 않습니다. """
        original = self.line()
        for changed in (original + "|links=1", original.replace("|links=1", ""),
                        original.replace("|links=1", "|links=-1"), original.replace("|writes=2", "|writes=x"),
                        original.replace("|case=ancs", "|case=unknown"), original.replace("role=client", "role=peer"),
                        original.replace(IDENTITY, "c" * 104), original.replace("|2|PASS", "|1|PASS"),
                        original.replace("|2|PASS", "|2|SUCCESS")):
            with self.subTest(line=changed):
                with self.assertRaises(ValueError):
                    MODULE.parse(changed, "client", IDENTITY)
        record = MODULE.parse(original, "client", IDENTITY)
        with self.assertRaises(ValueError):
            MODULE.validate_pass(record, "ancs", "client", "f" * 32, "fresh")
        record["links"] = 0
        with self.assertRaises(ValueError):
            MODULE.validate_pass(record, "ancs", "client", NONCE, "fresh")

    def test_fixture_needs_exact_images_and_debugger_proof(self):
        """! @brief flash를 추정하지 않고 image와 사전 실물 증거 hash를 요구합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof = root / "preflight.json"
            proof.write_text('{"test_only": true}', encoding="utf-8")
            image = root / "image.hex"
            image.write_text(":00000001FF\n", encoding="ascii")
            boards = []
            for index, role in enumerate(MODULE.ROLES):
                config = root / f"{role}.config"
                config.write_text("CONFIG_BT=y\n", encoding="utf-8")
                elf = root / f"{role}.elf"
                elf.write_bytes(b"ELF" + role.encode("ascii"))
                command = [
                    "python", "-m", "west", "build", "-b", MODULE.BOARD,
                    str(MODULE.APPLICATION), f"-DCOMPANION_ROLE={role}",
                ]
                record = root / f"{role}.build-manifest.json"
                record.write_text(json.dumps({
                    "schema_version": 1,
                    "role": role,
                    "identity": IDENTITY,
                    "identity_stable": True,
                    "source_revision": IDENTITY[:40],
                    "source_clean": True,
                    "ncs_revision": MODULE.LOCK["ncs"]["revision"],
                    "zephyr_revision": MODULE.LOCK["zephyr"]["revision"],
                    "board_revision": MODULE.LOCK["board"]["revision"],
                    "command": command,
                    "command_sha256": hashlib.sha256(json.dumps(
                        command, separators=(",", ":")
                    ).encode("utf-8")).hexdigest(),
                    "image_sha256": MODULE.digest(image),
                    "config": str(config),
                    "config_sha256": MODULE.digest(config),
                    "elf": str(elf),
                    "elf_sha256": MODULE.digest(elf),
                    "exit_code": 0,
                    "runtime": "NOT_RUN",
                }), encoding="utf-8")
                boards.append({
                    "role": role,
                    "port": f"COM{index + 1}",
                    "readback": "verified",
                    "probe_sha256": str(index + 1) * 64,
                    "image": str(image),
                    "image_sha256": MODULE.digest(image),
                    "build_record": str(record),
                    "build_record_sha256": MODULE.digest(record),
                    "flash": {
                        "mode": "pyocd-sector-no-reset",
                        "programmed_bytes": image.stat().st_size,
                        "erase": "sector",
                        "auto_unlock": False,
                        "mass_erase": False,
                        "automatic_recover": False,
                    },
                })
            fixture = {"schema_version": 1, "identity": IDENTITY, "other_radios": "isolated_verified",
                       "test_owned_bond_cleanup": True,
                       "preflight_evidence": str(proof), "preflight_sha256": MODULE.digest(proof),
                       "boards": boards}
            MODULE.validate_fixture(fixture)
            for field, value in (("identity", "a" * 40), ("preflight_sha256", "f" * 64),
                                 ("test_owned_bond_cleanup", False),
                                 ("other_radios", "unknown"), ("boards", fixture["boards"][:1])):
                changed = copy.deepcopy(fixture)
                changed[field] = value
                with self.assertRaises(ValueError):
                    MODULE.validate_fixture(changed)
            for field, value in (("readback", "assumed"), ("image_sha256", "f" * 64),
                                 ("build_record_sha256", "f" * 64),
                                 ("probe_sha256", "RAW_UID"), ("port", "COM1")):
                changed = copy.deepcopy(fixture)
                changed["boards"][1][field] = value
                with self.assertRaises(ValueError):
                    MODULE.validate_fixture(changed)

    def test_restart_scan_does_not_reuse_controller_duplicate_history(self):
        """! @brief nonce가 바뀐 같은 advertiser를 controller duplicate cache가 숨기지 않습니다. """
        source = (ROOT / "tests/zephyr/m33_ecosystem_hil/src/main.cpp").read_text(encoding="utf-8")
        configuration = (ROOT / "tests/zephyr/m33_ecosystem_hil/prj.conf").read_text(encoding="utf-8")
        self.assertIn("BLEScan.startExtended(true, false, false)", source)
        self.assertIn("BLEScan.running()", source)
        self.assertIn('record("CLIENT_READY")', source)
        self.assertIn('record("GO_ACK")', source)
        self.assertIn('fail("scan_restart")', source)
        self.assertIn('Serial.print("M33ECO_ERROR reason=")', source)
        self.assertIn('Serial.print("M33ECO_GAP event=")', source)
        self.assertIn("CONFIG_BT_EXT_ADV=y", configuration)
        self.assertIn("CONFIG_BT_EXT_ADV_MAX_ADV_SET=1", configuration)

    def test_diagnostic_line_is_preserved_before_protocol_failure(self):
        """! @brief protocol 밖 진단 문구도 실패 원인 분석용 transcript에 보존합니다. """
        class Port:
            """! @brief 두 줄만 반환하는 최소 serial 대역입니다. """

            def __init__(self, lines):
                self.lines = iter(lines)

            def readline(self, _size):
                return next(self.lines, b"")

        transcript = []
        endpoint = MODULE.Endpoint(
            Port([b"M33ECO_ERROR reason=scan_start_failed\n",
                  (self.line(event="FAIL") + "\n").encode("ascii")]),
            "client", IDENTITY, transcript)
        with self.assertRaisesRegex(ValueError, "firmware failed"):
            endpoint.receive("PASS", timeout=0.1, nonce=NONCE)
        self.assertEqual(transcript[0], "client< M33ECO_ERROR reason=scan_start_failed")

    def test_global_transcript_replays_every_command_and_cleanup(self):
        """! @brief 45 case의 START·GO·STOP과 최종 CLEANUP 순서를 raw transcript에서 재생합니다. """

        lines = []
        for role in MODULE.ROLES:
            lines.append(role + "> STATUS")
            lines.append(role + "< " + self.line(role=role, event="READY"))
            for command in ("START " + "0" * 32 + " ancs",
                            "START invalid ancs", "X" * 120):
                lines.append(role + "> " + command)
                lines.append(role + "< " + self.line(role=role, event="REJECT"))

        wrong_nonces = {"client": "1" * 32, "peer": "2" * 32}
        for role in MODULE.ROLES:
            nonce = wrong_nonces[role]
            lines.append(f"{role}> START {nonce} ancs")
            lines.append(role + "< " + self.line(
                role=role, event="STARTED", nonce=nonce
            ))
        for role in MODULE.ROLES:
            nonce = wrong_nonces[role]
            lines.append(role + "> STATUS")
            lines.append(role + "< " + self.line(
                role=role, event="READY", nonce=nonce
            ))
            lines.append(f"{role}> STOP {nonce}")
            lines.append(role + "< " + self.line(
                role=role, event="STOPPED", nonce=nonce
            ))

        cases = [{"cycle": 0, "case": "access_denied", "nonce": "3" * 32,
                  "status": "PASS"}]
        for index, (cycle, case, _security) in enumerate(
                MODULE.regression_schedule(), start=4):
            cases.append({"cycle": cycle, "case": case,
                          "nonce": f"{index:032x}", "status": "PASS"})
        for row in cases:
            nonce = row["nonce"]
            case = row["case"]
            for role in MODULE.ROLES:
                lines.append(f"{role}> START {nonce} {case}")
                lines.append(role + "< " + self.line(
                    case=case, role=role, event="STARTED", nonce=nonce
                ))
            if case != "access_denied":
                lines.append("client< " + self.line(
                    case=case, role="client", event="CLIENT_READY", nonce=nonce
                ))
                lines.append(f"peer> GO {nonce}")
                lines.append("peer< " + self.line(
                    case=case, role="peer", event="GO_ACK", nonce=nonce
                ))
            for role in MODULE.ROLES:
                mode = "denied" if case == "access_denied" else "reconnect"
                lines.append(role + "< " + self.line(
                    case=case, role=role, security_mode=mode,
                    event="PASS", nonce=nonce
                ))
            for role in MODULE.ROLES:
                if case != "access_denied":
                    lines.append(role + "> STOP " + "f" * 32)
                    lines.append(role + "< " + self.line(
                        case=case, role=role, event="REJECT", nonce=nonce
                    ))
                lines.append(f"{role}> STOP {nonce}")
            for role in MODULE.ROLES:
                lines.append(role + "< " + self.line(
                    case=case, role=role, event="STOPPED", nonce=nonce
                ))

        bond_nonce = next(row["nonce"] for row in cases
                          if row["case"] == "ancs" and row["cycle"] == 1)
        for role in MODULE.ROLES:
            lines.append(f"{role}> CLEANUP {bond_nonce}")
        for role in MODULE.ROLES:
            lines.append(role + "< " + self.line(
                role=role, security_mode="cleaned", event="CLEANED",
                nonce=bond_nonce
            ))
        for role in MODULE.ROLES:
            lines.append(role + "> STATUS")
            lines.append(role + "< " + self.line(
                role=role, security_mode="cleaned", event="READY",
                nonce=bond_nonce
            ))

        report = {
            "identity": IDENTITY,
            "negative": [{"wrong_peer_nonces": wrong_nonces}],
            "cases": cases,
            "cleanup": [
                {"role": role, "status": "PASS", "stop": "PASS",
                 "serial_close": "PASS"}
                for role in MODULE.ROLES
            ],
        }
        MODULE.validate_transcript_evidence(report, lines)
        changed = list(lines)
        changed.remove(f"peer> GO {cases[1]['nonce']}")
        with self.assertRaisesRegex(ValueError, "command missing"):
            MODULE.validate_transcript_evidence(report, changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
