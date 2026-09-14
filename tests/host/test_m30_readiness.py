#!/usr/bin/env python3
"""! @brief M30 보안·profile·DFU 착수 계약을 검증합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "m30-ble-readiness.json"
LOCK_PATH = REPOSITORY / "tools" / "ci" / "ncs-3.4.0.lock.json"
CONTRACT_PATH = (
    REPOSITORY
    / "00_Docs"
    / "01_아두이노 코어 설계"
    / "17_M30_BLE_Security_Profile_DFU_착수_계약.md"
)
TODO_PATH = REPOSITORY / "00_Docs" / "TODO_v0.5.0.md"
HANDOFF_PATH = REPOSITORY / "00_Docs" / "HANDOFF.md"


class M30ReadinessTests(unittest.TestCase):
    """! @brief M30 범위·자원·유한 실행 계획의 fail-closed 경계입니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief readiness와 고정 SDK lock을 읽습니다. """

        cls.readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
        cls.lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    def test_identity_and_revisions_match_locked_baseline(self) -> None:
        """! @brief M30 기준선이 v0.4.1과 고정 SDK·board에 연결되는지 검사합니다. """

        baseline = self.readiness["baseline"]
        self.assertEqual(self.readiness["schema_version"], 1)
        self.assertEqual(self.readiness["milestone"], "M30")
        self.assertEqual(self.readiness["product_target"], "v0.5.0")
        self.assertEqual(self.readiness["milestone_status"], "in_progress")
        self.assertEqual(baseline["supported_release"], "v0.4.1")
        self.assertRegex(baseline["core_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(baseline["ncs_revision"], self.lock["ncs"]["revision"])
        self.assertEqual(baseline["zephyr_revision"], self.lock["zephyr"]["revision"])
        self.assertEqual(baseline["board_revision"], self.lock["board"]["revision"])
        self.assertEqual(baseline["toolchain_bundle"], self.lock["windows_toolchain"]["bundle_id"])
        self.assertEqual(baseline["max_connections"], 2)

    def test_security_and_oob_policy_are_explicit(self) -> None:
        """! @brief 16-byte SC 기본값과 유선 OOB/NFC 비검증 경계를 검사합니다. """

        security = self.readiness["security_policy"]
        self.assertEqual(security["default_pairing"], "le_secure_connections_only")
        self.assertEqual(security["minimum_encryption_key_bytes"], 16)
        self.assertEqual(security["simultaneous_security_contexts"], 2)
        self.assertFalse(security["legacy_pairing_default_enabled"])
        oob = self.readiness["oob_policy"]
        self.assertEqual(oob["primary"]["carrier"], "wired_usb_daplink_vcom")
        self.assertTrue(oob["primary"]["physical_hil_required"])
        self.assertTrue(oob["nfc"]["implementation_required"])
        self.assertFalse(oob["nfc"]["default_enabled"])
        self.assertFalse(oob["nfc"]["supported"])
        self.assertEqual(oob["nfc"]["physical_hil"], "not_run_by_scope_decision")

    def test_dfu_layout_and_key_policy_are_fixed(self) -> None:
        """! @brief MCUboot dual-slot·서명·loaderless 보존 계약을 검사합니다. """

        policy = self.readiness["dfu_policy"]
        self.assertTrue(policy["default_loaderless_profile_unchanged"])
        self.assertEqual(policy["bootloader"], "mcuboot")
        self.assertEqual(policy["transport"], "mcumgr_smp_over_ble")
        self.assertEqual(policy["transport_security"], "authenticated_encrypted_connection")
        self.assertTrue(policy["power_loss_recovery_required"])
        layout = policy["layout"]
        self.assertEqual(layout["boot_bytes"], 62 * 1024)
        self.assertEqual(layout["slot0_bytes"], 712 * 1024)
        self.assertEqual(layout["slot1_bytes"], 712 * 1024)
        self.assertEqual(layout["storage_bytes"], 36 * 1024)
        self.assertLessEqual(layout["storage_offset"] + layout["storage_bytes"], 1536 * 1024)
        key = policy["trust_key"]
        self.assertEqual(key["algorithm"], "ecdsa_p256")
        self.assertEqual(key["repository_private_key"], "forbidden")

    def test_resources_and_work_packages_are_bounded(self) -> None:
        """! @brief 두 link 보안 상태와 W01~W08 상태를 검사합니다. """

        resources = self.readiness["resource_contract"]
        self.assertEqual(resources["security_link_contexts"], 2)
        self.assertEqual(resources["pairing_response_slots"], 2)
        self.assertEqual(resources["bond_records"], 4)
        self.assertEqual(resources["dfu_slots"], 2)
        for name, value in resources.items():
            self.assertIsInstance(value, int, name)
            self.assertGreater(value, 0, name)
        packages = self.readiness["work_packages"]
        self.assertEqual(len(packages), 8)
        for index, package in enumerate(packages, start=1):
            self.assertEqual(package["id"], f"M30-W{index:02d}")
        self.assertEqual(packages[0]["status"], "completed")
        self.assertEqual(packages[0]["host_parser_tests"], 13)
        self.assertEqual(packages[0]["target_build"], "passed")
        self.assertEqual(packages[0]["physical_capability"], "passed")
        self.assertEqual(packages[1]["status"], "completed")
        self.assertEqual(packages[1]["production_host_scenarios"], 17)
        self.assertEqual(packages[1]["target_builds"], 10)
        self.assertEqual(packages[1]["physical_pairings"], 50)
        self.assertEqual(packages[2]["status"], "completed")
        self.assertEqual(packages[2]["wired_oob_pairings"], 20)
        self.assertEqual(packages[2]["bonded_reconnects"], 20)
        self.assertEqual(packages[2]["nfc_rf"], "not_run_by_scope_decision")
        for relative in packages[2]["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        self.assertEqual(packages[3]["status"], "completed")
        self.assertEqual(packages[3]["catalog_entries"], 7)
        self.assertEqual(packages[3]["operations_per_service"], 100)
        self.assertEqual(packages[3]["payload_errors"], 0)
        for relative in packages[3]["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        self.assertEqual(packages[4]["status"], "in_progress")
        self.assertEqual(packages[-1]["status"], "blocked_by_power_hil")
        host_packages = self.readiness["host_work_packages"]
        self.assertEqual(len(host_packages), 8)
        for index, package in enumerate(host_packages, start=1):
            self.assertEqual(package["id"], f"HOST-W{index:02d}")

    def test_execution_plan_is_finite_and_stops_at_real_power_cut(self) -> None:
        """! @brief 열 개 test ID의 보드·timeout·정수 합격값과 중단점을 검사합니다. """

        expected = {
            "M30-CAP-01", "M30-PAIR-01", "M30-OOB-01", "M30-BOND-01",
            "M30-PROFILE-01", "M30-BOOT-01", "M30-DFU-01", "M30-DFU-NEG-01",
            "M30-MULTI-01", "M30-POWER-01",
        }
        plan = self.readiness["execution_plan"]
        self.assertEqual({entry["id"] for entry in plan}, expected)
        for entry in plan:
            self.assertIn(entry["boards"], {1, 2, 3}, entry["id"])
            self.assertGreater(entry["timeout_seconds"], 0, entry["id"])
            self.assertLessEqual(entry["timeout_seconds"], 1800, entry["id"])
            for name, value in entry["criteria"].items():
                self.assertIsInstance(value, int, f"{entry['id']}:{name}")
                self.assertGreaterEqual(value, 0, f"{entry['id']}:{name}")
        power = next(entry for entry in plan if entry["id"] == "M30-POWER-01")
        capability = next(entry for entry in plan if entry["id"] == "M30-CAP-01")
        pairing = next(entry for entry in plan if entry["id"] == "M30-PAIR-01")
        oob = next(entry for entry in plan if entry["id"] == "M30-OOB-01")
        bond = next(entry for entry in plan if entry["id"] == "M30-BOND-01")
        profile = next(entry for entry in plan if entry["id"] == "M30-PROFILE-01")
        self.assertEqual(capability["status"], "passed")
        for relative in capability["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        self.assertEqual(pairing["status"], "passed")
        self.assertEqual(pairing["criteria"]["io_capabilities"], 5)
        self.assertEqual(pairing["criteria"]["rounds_per_capability"], 10)
        for relative in pairing["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        pairing_evidence = json.loads(
            (REPOSITORY / pairing["evidence_files"][0]).read_text(encoding="utf-8")
        )
        self.assertEqual(pairing_evidence["status"], "passed")
        self.assertEqual(pairing_evidence["core_revision"], pairing["tested_core_revision"])
        self.assertEqual(pairing_evidence["total_pairings"], 50)
        self.assertEqual(pairing_evidence["unexpected_auth_failures"], 0)
        self.assertEqual(pairing_evidence["passkey_evidence_policy"], "redacted")
        self.assertFalse(pairing_evidence["power_cut_injected"])
        self.assertFalse(pairing_evidence["mass_erase_or_recover"])
        self.assertEqual(
            {endpoint["volume"] for endpoint in pairing_evidence["endpoints"].values()},
            {"F:", "G:"},
        )
        for entry in (oob, bond):
            self.assertEqual(entry["status"], "passed")
            for relative in entry["evidence_files"]:
                self.assertTrue((REPOSITORY / relative).is_file(), relative)
            evidence = json.loads(
                (REPOSITORY / entry["evidence_files"][0]).read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["status"], "passed")
            self.assertEqual(evidence["core_revision"], entry["tested_core_revision"])
            self.assertFalse(evidence["power_cut_injected"])
            self.assertFalse(evidence["mass_erase_or_recover"])
        self.assertEqual(oob["criteria"]["nfc_rf_runs"], 0)
        self.assertEqual(bond["criteria"]["privacy_rotations"], 3)
        self.assertEqual(profile["status"], "passed")
        self.assertEqual(profile["criteria"]["catalog_entries"], 7)
        self.assertEqual(profile["criteria"]["operations_per_service"], 100)
        profile_evidence = json.loads(
            (REPOSITORY / profile["evidence_files"][0]).read_text(encoding="utf-8")
        )
        self.assertEqual(profile_evidence["core_revision"], profile["tested_core_revision"])
        self.assertEqual(profile_evidence["payload_errors"], 0)
        self.assertFalse(profile_evidence["power_cut_injected"])
        self.assertFalse(profile_evidence["mass_erase_or_recover"])
        self.assertEqual(power["status"], "blocked_human_power_cut")
        self.assertEqual(power["criteria"]["injection_points"], 4)
        self.assertEqual(power["criteria"]["cuts_per_point"], 3)
        self.assertEqual(
            self.readiness["completion"]["current_stop_boundary"],
            "before_m30_power_01_physical_cut",
        )
        self.assertEqual(self.readiness["completion"]["completed_work_packages"], 4)
        self.assertEqual(self.readiness["completion"]["passed_test_ids"], 5)

    def test_profile_catalog_and_equipment_scope_are_explicit(self) -> None:
        """! @brief 기존/신규 profile과 세 보드·전원 장비 경계를 검사합니다. """

        catalog = self.readiness["profile_catalog"]
        self.assertEqual(len(catalog), 7)
        self.assertEqual(sum(entry["status"] == "baseline" for entry in catalog), 3)
        equipment = self.readiness["equipment"]
        self.assertEqual(equipment["nu54dk_boards"], 3)
        self.assertEqual(equipment["independent_dap_uart_paths"], 3)
        self.assertEqual(equipment["wired_oob_path"], "daplink_vcom")
        self.assertTrue(equipment["manual_power_cut_required"])

    def test_contract_and_current_documents_are_linked(self) -> None:
        """! @brief 사람이 읽는 계약과 TODO·HANDOFF 연결을 검사합니다. """

        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        for token in (
            "M30-W01", "M30-W08", "M30-CAP-01", "M30-POWER-01",
            "wired USB/DAPLink VCOM", "NFC", "m30-ble-readiness.json",
        ):
            self.assertIn(token, contract)
        for path in (TODO_PATH, HANDOFF_PATH):
            text = path.read_text(encoding="utf-8")
            self.assertIn("17_M30_BLE_Security_Profile_DFU_착수_계약.md", text, path)
            self.assertIn("m30-ble-readiness.json", text, path)
            self.assertIn("M30-W01", text, path)
            self.assertIn("M30-POWER-01", text, path)


if __name__ == "__main__":
    unittest.main()
