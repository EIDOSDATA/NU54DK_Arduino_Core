#!/usr/bin/env python3
"""! @brief M29 ATT/GATT·L2CAP 착수 계약을 검증합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "m29-ble-readiness.json"
LOCK_PATH = REPOSITORY / "tools" / "ci" / "ncs-3.4.0.lock.json"
CONTRACT_PATH = (
    REPOSITORY
    / "00_Docs"
    / "01_아두이노 코어 설계"
    / "16_M29_ATT_GATT_L2CAP_착수_계약.md"
)
TODO_PATH = REPOSITORY / "00_Docs" / "TODO_v0.5.0.md"
HANDOFF_PATH = REPOSITORY / "00_Docs" / "HANDOFF.md"


class M29ReadinessTests(unittest.TestCase):
    """! @brief M29 정책·고정 자원·유한 실행 계획의 fail-closed 경계를 고정합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief readiness 원장과 CI lock을 한 번 읽습니다. """

        cls.readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
        cls.lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    def test_identity_and_revisions_match_locked_baseline(self) -> None:
        """! @brief M29 기준선이 고정 Core·SDK·board·toolchain과 일치하는지 검사합니다. """

        baseline = self.readiness["baseline"]
        self.assertEqual(self.readiness["schema_version"], 1)
        self.assertEqual(self.readiness["milestone"], "M29")
        self.assertEqual(self.readiness["product_target"], "v0.5.0")
        self.assertEqual(self.readiness["phase"], "w07_hil_ready")
        self.assertEqual(self.readiness["milestone_status"], "in_progress")
        self.assertEqual(baseline["supported_release"], "v0.4.1")
        self.assertRegex(baseline["core_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(baseline["ncs_revision"], self.lock["ncs"]["revision"])
        self.assertEqual(baseline["zephyr_revision"], self.lock["zephyr"]["revision"])
        self.assertEqual(baseline["board_revision"], self.lock["board"]["revision"])
        self.assertEqual(
            baseline["toolchain_bundle"],
            self.lock["windows_toolchain"]["bundle_id"],
        )
        self.assertEqual(baseline["max_connections"], 2)

    def test_deprecated_and_experimental_features_are_explicit_opt_ins(self) -> None:
        """! @brief Signed Write와 EATT를 자동 승격하거나 조용히 제외하지 못하게 합니다. """

        signed = self.readiness["policy"]["signed_write"]
        self.assertEqual(signed["sdk_status"], "deprecated")
        self.assertEqual(signed["publication"], "legacy_opt_in")
        self.assertFalse(signed["default_enabled"])
        self.assertEqual(
            set(signed["completion_requires"]),
            {"csrk_persistence", "sign_counter_persistence", "replay_rejection"},
        )

        eatt = self.readiness["policy"]["eatt"]
        self.assertEqual(eatt["sdk_status"], "experimental")
        self.assertEqual(eatt["publication"], "experimental_opt_in")
        self.assertFalse(eatt["default_enabled"])
        self.assertEqual(eatt["maximum_bearers_per_connection"], 2)
        self.assertIn("encrypted_link", eatt["completion_requires"])
        self.assertIn("peer_support", eatt["completion_requires"])

    def test_source_candidates_are_not_implementation_passes(self) -> None:
        """! @brief 고정 SDK source 후보가 실제 구현·HIL PASS로 승격되지 않았는지 검사합니다. """

        expected = {
            "gatt_long_reliable",
            "gatt_read_multiple",
            "gatt_service_changed_cache",
            "l2cap_credit_based_channel",
            "signed_write",
            "eatt",
        }
        capabilities = self.readiness["source_capabilities"]
        self.assertEqual({entry["id"] for entry in capabilities}, expected)
        for entry in capabilities:
            self.assertTrue(entry["source_status"].startswith("candidate"), entry["id"])
            expected_status = "target_ready" if entry["id"] in {
                "signed_write",
                "eatt",
            } else "passed"
            self.assertEqual(entry["implementation_status"], expected_status, entry["id"])
            self.assertGreater(len(entry["source_references"]), 0, entry["id"])
            for reference in entry["source_references"]:
                self.assertNotRegex(reference, r"^[A-Za-z]:[\\/]", reference)

    def test_resource_contract_is_fixed_and_bounded(self) -> None:
        """! @brief GATT·CoC 공개 자원이 고정 상한을 갖는지 검사합니다. """

        resources = self.readiness["resource_contract"]
        self.assertEqual(resources["gatt_client_contexts"], 2)
        self.assertEqual(resources["pending_operations_per_link"], 1)
        self.assertEqual(resources["maximum_value_bytes"], 512)
        self.assertEqual(resources["prepare_transactions_per_link"], 1)
        self.assertEqual(resources["descriptors_per_characteristic"], 4)
        self.assertEqual(resources["read_multiple_handles"], 4)
        self.assertEqual(resources["l2cap_servers"], 1)
        self.assertEqual(resources["l2cap_channels_total"], 2)
        self.assertEqual(resources["l2cap_sdu_bytes"], 512)
        self.assertEqual(resources["l2cap_rx_records_per_channel"], 4)
        self.assertEqual(resources["l2cap_tx_buffers_total"], 4)
        for name, value in resources.items():
            self.assertIsInstance(value, int, name)
            self.assertGreater(value, 0, name)

    def test_work_packages_begin_at_w07_after_w06_completion(self) -> None:
        """! @brief W01~W06 완료와 W07 target 준비 상태를 검사합니다. """

        packages = self.readiness["work_packages"]
        self.assertEqual(len(packages), 8)
        for index, package in enumerate(packages, start=1):
            self.assertEqual(package["id"], f"M29-W{index:02d}")
            expected_status = (
                "completed" if index <= 6 else
                "in_progress" if index == 7 else
                "not_started"
            )
            self.assertEqual(package["status"], expected_status, package["id"])
        w01 = packages[0]
        self.assertEqual(w01["host_parser_tests"], 16)
        self.assertEqual(w01["target_build"], "passed")
        self.assertEqual(w01["physical_capability"], "passed")
        self.assertRegex(w01["tested_core_revision"], r"^[0-9a-f]{40}$")
        w02 = packages[1]
        self.assertEqual(w02["production_host_scenarios"], 14)
        self.assertEqual(w02["host_contract_tests"], 6)
        self.assertEqual(w02["host_parser_tests"], 11)
        self.assertEqual(w02["target_builds"], 2)
        self.assertEqual(w02["physical_long_read"], "passed")
        self.assertRegex(w02["tested_core_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(w02["evidence_files"]), 3)
        for relative in w02["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        w03 = packages[2]
        self.assertEqual(w03["production_host_scenarios"], 15)
        self.assertEqual(w03["host_contract_tests"], 6)
        self.assertEqual(w03["host_parser_tests"], 11)
        self.assertEqual(w03["target_builds"], 2)
        self.assertEqual(w03["physical_long_reliable_write"], "passed")
        self.assertRegex(w03["tested_core_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(w03["failure_evidence_files"]), 2)
        self.assertEqual(len(w03["evidence_files"]), 3)
        for relative in w03["failure_evidence_files"] + w03["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        w04 = packages[3]
        self.assertEqual(w04["production_host_scenarios"], 17)
        self.assertEqual(w04["host_contract_tests"], 8)
        self.assertEqual(w04["host_parser_tests"], 11)
        self.assertEqual(w04["target_builds"], 2)
        self.assertEqual(w04["physical_descriptor_authorization"], "passed")
        self.assertRegex(w04["tested_core_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(w04["failure_evidence_files"]), 2)
        self.assertEqual(len(w04["evidence_files"]), 3)
        for relative in w04["failure_evidence_files"] + w04["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        w05 = packages[4]
        self.assertEqual(w05["production_host_scenarios"], 18)
        self.assertEqual(w05["host_contract_tests"], 9)
        self.assertEqual(w05["host_parser_tests"], 14)
        self.assertEqual(w05["target_builds"], 2)
        self.assertEqual(w05["physical_cache_migration"], "passed")
        self.assertRegex(w05["tested_core_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(w05["failure_evidence_files"]), 6)
        self.assertEqual(len(w05["evidence_files"]), 3)
        for relative in w05["failure_evidence_files"] + w05["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        w06 = packages[5]
        self.assertEqual(w06["production_host_scenarios"], 7)
        self.assertEqual(w06["host_contract_tests"], 7)
        self.assertEqual(w06["host_parser_tests"], 12)
        self.assertEqual(w06["target_builds"], 2)
        self.assertEqual(w06["physical_le_coc"], "passed")
        self.assertRegex(w06["tested_core_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(w06["failure_evidence_files"]), 2)
        self.assertEqual(len(w06["evidence_files"]), 3)
        for relative in w06["failure_evidence_files"] + w06["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        w07 = packages[6]
        self.assertEqual(w07["production_host_scenarios"], 3)
        self.assertEqual(w07["host_contract_tests"], 7)
        self.assertEqual(w07["host_parser_tests"], 14)
        self.assertEqual(w07["target_builds"], 2)
        self.assertEqual(w07["physical_signed_write"], "not_run")
        self.assertEqual(w07["physical_eatt"], "not_run")
        self.assertEqual(w07["physical_multi_link"], "not_run")
        self.assertEqual(w07["physical_regression"], "not_run")
        completion = self.readiness["completion"]
        self.assertEqual(completion["completed_work_packages"], 6)
        self.assertEqual(completion["total_work_packages"], 8)
        self.assertEqual(completion["passed_test_ids"], 6)
        self.assertEqual(completion["total_test_ids"], 10)

    def test_execution_plan_is_finite_fail_closed_and_not_run(self) -> None:
        """! @brief 열 개 test ID에 보드·timeout·정수 합격값이 있는지 검사합니다. """

        expected = {
            "M29-CAP-01",
            "M29-LONG-01",
            "M29-DESC-01",
            "M29-CACHE-01",
            "M29-COC-01",
            "M29-NEG-01",
            "M29-SIGN-01",
            "M29-EATT-01",
            "M29-MULTI-01",
            "M29-REG-01",
        }
        plan = self.readiness["execution_plan"]
        self.assertEqual({entry["id"] for entry in plan}, expected)
        for entry in plan:
            self.assertIn(entry["boards"], {1, 2, 3}, entry["id"])
            self.assertGreater(entry["timeout_seconds"], 0, entry["id"])
            self.assertLessEqual(entry["timeout_seconds"], 1800, entry["id"])
            expected_status = (
                "passed"
                if entry["id"]
                in {
                    "M29-CAP-01",
                    "M29-LONG-01",
                    "M29-DESC-01",
                    "M29-CACHE-01",
                    "M29-COC-01",
                    "M29-NEG-01",
                }
                else "not_run"
            )
            self.assertEqual(entry["status"], expected_status, entry["id"])
            self.assertGreater(len(entry["criteria"]), 0, entry["id"])
            for name, value in entry["criteria"].items():
                self.assertIsInstance(value, int, f"{entry['id']}:{name}")
                self.assertGreaterEqual(value, 0, f"{entry['id']}:{name}")

        multi = next(entry for entry in plan if entry["id"] == "M29-MULTI-01")
        self.assertEqual(multi["boards"], 3)
        self.assertEqual(multi["criteria"]["simultaneous_links"], 2)
        coc = next(entry for entry in plan if entry["id"] == "M29-COC-01")
        self.assertEqual(coc["criteria"]["channels"], 2)
        self.assertEqual(coc["criteria"]["payload_errors"], 0)
        capability = next(entry for entry in plan if entry["id"] == "M29-CAP-01")
        self.assertEqual(len(capability["evidence_files"]), 2)
        for relative in capability["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        long_write = next(entry for entry in plan if entry["id"] == "M29-LONG-01")
        self.assertEqual(len(long_write["evidence_files"]), 3)
        for relative in long_write["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        descriptor = next(entry for entry in plan if entry["id"] == "M29-DESC-01")
        self.assertEqual(len(descriptor["evidence_files"]), 3)
        for relative in descriptor["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        cache = next(entry for entry in plan if entry["id"] == "M29-CACHE-01")
        self.assertEqual(len(cache["evidence_files"]), 3)
        for relative in cache["evidence_files"]:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        negative = next(entry for entry in plan if entry["id"] == "M29-NEG-01")
        for entry in (coc, negative):
            self.assertEqual(len(entry["evidence_files"]), 3)
            for relative in entry["evidence_files"]:
                self.assertTrue((REPOSITORY / relative).is_file(), relative)

    def test_equipment_distinguishes_known_boards_from_unknown_peers(self) -> None:
        """! @brief 확인한 세 보드와 아직 확인하지 않은 cross-vendor 장비를 분리합니다. """

        equipment = self.readiness["equipment"]
        self.assertEqual(equipment["nu54dk_boards"], 3)
        self.assertEqual(equipment["independent_dap_uart_paths"], 3)
        self.assertEqual(equipment["external_bluetooth_sniffer"], "unconfirmed")
        self.assertEqual(
            set(equipment["cross_vendor_peers"]),
            {"android", "ios", "windows", "linux"},
        )
        for status in equipment["cross_vendor_peers"].values():
            self.assertEqual(status, "unconfirmed")

    def test_contract_and_current_documents_are_linked(self) -> None:
        """! @brief 사람이 읽는 계약과 현행 TODO·HANDOFF의 M29 링크를 검사합니다. """

        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        for token in (
            "M29-W01",
            "M29-W08",
            "M29-CAP-01",
            "M29-REG-01",
            "legacy opt-in",
            "experimental opt-in",
            "m29-ble-readiness.json",
        ):
            self.assertIn(token, contract)

        for path in (TODO_PATH, HANDOFF_PATH):
            text = path.read_text(encoding="utf-8")
            self.assertIn("16_M29_ATT_GATT_L2CAP_착수_계약.md", text, path)
            self.assertIn("m29-ble-readiness.json", text, path)
            self.assertIn("M29-W01", text, path)
            self.assertIn("6/8", text, path)


if __name__ == "__main__":
    unittest.main()
