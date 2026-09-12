#!/usr/bin/env python3
"""! @brief M28 BLE GAP·Link·Privacy 착수 준비 계약을 검증합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "m28-ble-readiness.json"
LOCK_PATH = REPOSITORY / "tools" / "ci" / "ncs-3.4.0.lock.json"
DESIGN_PATH = (
    REPOSITORY
    / "00_Docs"
    / "01_아두이노 코어 설계"
    / "15_M28_BLE_GAP_Link_Privacy_착수_계약.md"
)
TODO_PATH = REPOSITORY / "00_Docs" / "TODO_v0.5.0.md"
CAPABILITY_CONFIG_PATH = (
    REPOSITORY / "tests" / "zephyr" / "m28_ble_capability" / "prj.conf"
)


class M28ReadinessTests(unittest.TestCase):
    """! @brief 기준선·지원 후보·유한 실행 계획의 fail-closed 경계를 고정합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 준비 계약과 CI lock을 한 번 읽습니다. """

        cls.readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
        cls.lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    def test_identity_and_revisions_match_the_supported_baseline(self) -> None:
        """! @brief v0.4.1 기준선과 고정 NCS·Zephyr·보드 revision을 대조합니다. """

        baseline = self.readiness["baseline"]
        self.assertEqual(self.readiness["schema_version"], 2)
        self.assertEqual(self.readiness["milestone"], "M28")
        self.assertEqual(self.readiness["product_target"], "v0.5.0")
        self.assertEqual(self.readiness["phase"], "implementation")
        self.assertEqual(self.readiness["milestone_status"], "in_progress")
        self.assertEqual(baseline["supported_release"], "v0.4.1")
        self.assertEqual(baseline["ncs_revision"], self.lock["ncs"]["revision"])
        self.assertEqual(baseline["zephyr_revision"], self.lock["zephyr"]["revision"])
        self.assertEqual(baseline["board_revision"], self.lock["board"]["revision"])
        self.assertEqual(
            baseline["toolchain_bundle"],
            self.lock["windows_toolchain"]["bundle_id"],
        )

    def test_current_single_link_source_contract_is_not_mislabeled_as_m28(self) -> None:
        """! @brief 현재 단일 링크 제약이 바뀌면 준비 원장을 함께 갱신하도록 강제합니다. """

        for assertion in self.readiness["baseline_assertions"]:
            path = REPOSITORY / assertion["path"]
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            for token in assertion["contains"]:
                self.assertIn(token, text, f"{path}: {token}")
        baseline = self.readiness["baseline"]
        self.assertEqual(baseline["current_max_connections"], 1)
        self.assertEqual(baseline["current_advertising_payload_bytes"], 31)

    def test_every_source_candidate_remains_runtime_not_run(self) -> None:
        """! @brief 정적 SDK 근거를 실제 HCI·실기 PASS로 승격하지 못하게 합니다. """

        capabilities = self.readiness["source_capabilities"]
        expected = {
            "multi_role_multi_link",
            "extended_advertising_scanning",
            "periodic_advertising_sync_past",
            "pawr_advertiser_scanner",
            "privacy_rpa",
            "per_link_control",
        }
        self.assertEqual({entry["id"] for entry in capabilities}, expected)
        for entry in capabilities:
            self.assertEqual(entry["source_status"], "candidate", entry["id"])
            self.assertEqual(entry["runtime_hci_status"], "not_run", entry["id"])
            self.assertIn(
                entry["implementation_status"],
                {"not_started", "baseline_partial"},
                entry["id"],
            )
            self.assertGreater(len(entry["required_kconfig"]), 0, entry["id"])
            self.assertGreater(len(entry["source_references"]), 0, entry["id"])
            for reference in entry["source_references"]:
                self.assertNotRegex(reference, r"^[A-Za-z]:[\\/]", reference)

    def test_public_contract_preserves_compatibility_and_bounds_resources(self) -> None:
        """! @brief M28 공개 경계가 두 링크·역할별 한 slot과 기존 symbol을 고정합니다. """

        contract = self.readiness["public_contract"]
        self.assertEqual(contract["target_max_connections"], 2)
        self.assertEqual(contract["target_peripheral_connections"], 1)
        self.assertEqual(contract["target_central_connections"], 1)
        self.assertEqual(
            set(contract["compatibility_symbols"]),
            {"BLEDevice", "BLEAdvertising", "BLEScan", "BLEConnection"},
        )
        self.assertGreaterEqual(len(contract["new_contracts"]), 4)
        self.assertGreaterEqual(len(contract["forbidden_shortcuts"]), 4)

    def test_execution_plan_has_fixed_finite_acceptance_criteria(self) -> None:
        """! @brief 각 필수 시험에 장비 수·timeout·수치 판정이 있는지 확인합니다. """

        plan = self.readiness["execution_plan"]
        expected_ids = {
            "M28-CAP-01",
            "M28-REG-01",
            "M28-LINK-01",
            "M28-ADV-01",
            "M28-PER-01",
            "M28-PAWR-01",
            "M28-PRIV-01",
            "M28-CTRL-01",
            "M28-SOAK-01",
        }
        self.assertEqual({entry["id"] for entry in plan}, expected_ids)
        for entry in plan:
            self.assertGreaterEqual(entry["boards"], 1, entry["id"])
            self.assertGreater(entry["timeout_seconds"], 0, entry["id"])
            self.assertLessEqual(entry["timeout_seconds"], 3600, entry["id"])
            self.assertGreater(len(entry["criteria"]), 0, entry["id"])
            for name, value in entry["criteria"].items():
                self.assertIsInstance(value, int, f"{entry['id']}:{name}")
                self.assertGreaterEqual(value, 0, f"{entry['id']}:{name}")
        link = next(entry for entry in plan if entry["id"] == "M28-LINK-01")
        self.assertEqual(link["criteria"]["simultaneous_connections"], 2)
        self.assertEqual(link["criteria"]["payload_loss"], 0)
        self.assertEqual(link["criteria"]["stale_link_events"], 0)
        self.assertEqual(self.readiness["equipment"]["availability"], "not_confirmed")
        self.assertEqual(self.readiness["equipment"]["required"]["nu54dk_boards"], 3)

    def test_work_packages_and_documents_form_a_complete_preparation_index(self) -> None:
        """! @brief 8개 작업 묶음과 현행 문서의 M28 상태 연결을 검사합니다. """

        work_packages = self.readiness["work_packages"]
        self.assertEqual(len(work_packages), 8)
        for index, package in enumerate(work_packages, start=1):
            self.assertTrue(package.startswith(f"M28-W{index:02d}"), package)
        for path in (DESIGN_PATH, TODO_PATH):
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("m28-ble-readiness.json", text)
            self.assertIn("M28-CAP-01", text)
            self.assertIn("NOT RUN", text)

    def test_w01_host_target_ready_does_not_complete_hardware_capability(self) -> None:
        """! @brief W01 Host·build PASS와 실제 HCI NOT RUN을 별도 상태로 고정합니다. """

        statuses = self.readiness["work_package_status"]
        self.assertEqual(len(statuses), 8)
        for index, status in enumerate(statuses, start=1):
            self.assertEqual(status["id"], f"M28-W{index:02d}")
        w01 = statuses[0]
        self.assertEqual(w01["status"], "host_target_ready_hil_not_run")
        self.assertFalse(w01["completed"])
        self.assertEqual(w01["protocol"], "M28CAP/1")
        self.assertEqual(w01["host_parser_tests"], "passed")
        self.assertEqual(w01["target_build"], "passed")
        self.assertEqual(w01["physical_hci"], "not_run")
        for path in w01["paths"].values():
            self.assertTrue((REPOSITORY / path).exists(), path)
        capability_config = CAPABILITY_CONFIG_PATH.read_text(encoding="utf-8")
        for capability in self.readiness["source_capabilities"]:
            for setting in capability["required_kconfig"]:
                self.assertIn(setting, capability_config, capability["id"])
        progress = self.readiness["progress"]
        self.assertEqual(progress["completed_work_packages"], 0)
        self.assertEqual(progress["total_work_packages"], 8)
        self.assertEqual(progress["percent"], 0)
        self.assertEqual(progress["current_work_package"], "M28-W01")
        self.assertEqual(
            self.readiness["not_yet_claimed"],
            [
                "production BLE implementation",
                "physical HIL PASS",
                "Bluetooth qualification",
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
