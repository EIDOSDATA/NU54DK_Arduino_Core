"""! @brief M33 전체 원장과 릴리스 정책의 fail-closed 규칙을 검사합니다. """

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/bluetooth/m33_contract.py"
TARGET_PATH = ROOT / "variants/nu54dk/m33-release-readiness.json"
SPEC = importlib.util.spec_from_file_location("m33_contract_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
EXPECTED_W05_INSTALLED_EVIDENCE_PATH = MODULE.W05_INSTALLED_EVIDENCE_PATH


def w05_evidence_fixture() -> dict:
    """! @brief W05 완료 계약을 만족하는 최소 설치 evidence fixture를 만듭니다. """

    libraries = [
        {
            "directory": f"Library{index:02}",
            "name": f"Library {index:02}",
            "example_count": 8 if index < 23 else 20,
        }
        for index in range(24)
    ]
    builds = [
        {
            "identity": f"Library{index % 24:02}/Example{index:03}",
            "status": "PASS",
            "exit_code": 0,
            "timed_out": False,
        }
        for index in range(204)
    ]
    negatives = [
        {
            "id": f"negative_{index:02}",
            "identity": f"Library{index:02}/Negative{index:02}",
            "status": "PASS",
            "exit_code": 1,
            "timed_out": False,
            "unexpected_artifact_count": 0,
        }
        for index in range(9)
    ]
    return {
        "schema_version": 1,
        "work_id": "M33-W05",
        "test_id": "M33-EXAMPLE-01",
        "status": "PASS",
        "finished_utc": "2026-10-04T12:00:00+00:00",
        "source_revision": MODULE.W05_SOURCE_REVISION,
        "installed_source_revision": MODULE.W05_SOURCE_REVISION,
        "source_revision_after": MODULE.W05_SOURCE_REVISION,
        "installed_revision_after": MODULE.W05_SOURCE_REVISION,
        "source_clean_before": True,
        "source_clean_after": True,
        "installed_clean_after": True,
        "installed_tree_unchanged": True,
        "denominators": {
            "catalog": 204,
            "discovered": 204,
            "compiled": 204,
            "negative_profiles": 9,
        },
        "isolation": {
            "source_path_sha256": "1" * 64,
            "installed_path_sha256": "2" * 64,
            "build_path_sha256": "3" * 64,
            "source_install_separate": True,
            "fresh_build_root": True,
            "jobs": 2,
        },
        "libraries": libraries,
        "profile_counts": {"standard": 204},
        "builds": builds,
        "negative_profiles": negatives,
        "diagnostic_retest_policy": {
            "maximum_per_failed_build": 1,
            "fresh_build_directory": True,
            "serial": True,
            "initial_failure_is_preserved": True,
        },
        "diagnostic_retests": [],
        "summary": {
            "catalog": 204,
            "discovered": 204,
            "compiled_pass": 204,
            "compiled_fail": 0,
            "initial_compile_fail": 0,
            "diagnostic_retest_pass": 0,
            "diagnostic_retest_fail": 0,
            "negative_pass": 9,
            "negative_fail": 0,
        },
    }


def w06_in_progress_fixture(document: dict) -> dict:
    """! @brief 저장된 완료 여부와 무관하게 독립 시험의 W06 입력만 초기화합니다. """

    value = copy.deepcopy(document)
    value["work_packages"][5].update({"status": "in_progress", "exact_evidence": None})
    for family in value["test_families"]:
        if MODULE.TEST_OWNER[family["id"]] == "M33-W06":
            for case in family["cases"]:
                case.update({"status": "NOT_RUN", "source_revision": None, "evidence": None})
    value["counts"]["work_completed"] = sum(
        entry["status"] == "completed" for entry in value["work_packages"]
    )
    value["counts"]["test_case_passed"] = sum(
        case["status"] == "PASS" for family in value["test_families"] for case in family["cases"]
    )
    return value


class M33ReadinessContractTests(unittest.TestCase):
    """! @brief 원장 분모·owner·승격·후속 실물 gate를 고정합니다. """

    def setUp(self) -> None:
        """! @brief 저장된 현행 readiness를 각 시험에 복제합니다. """

        self.document = w06_in_progress_fixture(
            json.loads(TARGET_PATH.read_text(encoding="utf-8"))
        )
        w05_family = next(
            family for family in self.document["test_families"]
            if family["id"] == "M33-EXAMPLE-01"
        )
        for case in w05_family["cases"]:
            case["source_revision"] = MODULE.W05_SOURCE_REVISION
        self.temporary = tempfile.TemporaryDirectory(prefix="m33-w05-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.w05_evidence_path = Path(self.temporary.name) / "installed-examples.json"
        self.w05_evidence_path.write_text(
            json.dumps(w05_evidence_fixture(), ensure_ascii=False), encoding="utf-8"
        )
        self.w05_path_patch = mock.patch.object(
            MODULE, "W05_INSTALLED_EVIDENCE_PATH", self.w05_evidence_path
        )
        self.w05_path_patch.start()
        self.addCleanup(self.w05_path_patch.stop)

    def _promote_w06(self, document: dict, evidence: str,
                     revision: str) -> list[dict]:
        """! @brief 시험용 readiness의 W06 package와 세 case를 원자적으로 승격합니다. """
        package = document["work_packages"][5]
        package.update({"status": "completed", "exact_evidence": evidence})
        cases = [
            case
            for family in document["test_families"]
            if MODULE.TEST_OWNER[family["id"]] == "M33-W06"
            for case in family["cases"]
        ]
        for case in cases:
            case.update({
                "status": "PASS",
                "source_revision": revision,
                "evidence": evidence,
            })
        document["counts"]["work_completed"] += 1
        document["counts"]["test_case_passed"] += len(cases)
        return cases

    def _qualification(self) -> list[dict]:
        """! @brief 고정 NCS 3.4.0 component 조사 결과 세 행을 만듭니다. """
        return [
            {
                "component": component,
                "applicability": "applicable",
                "component_status": "EVIDENCE_RECORDED",
                "component_version": "NCS 3.4.0 LTS",
                "design_identifier": identifier,
                "product_status": "NOT_ASSESSED",
                "example_status_implied": False,
                "official_reference": MODULE.QUALIFICATION_OFFICIAL_REFERENCE,
                "remaining_product_procedure": "제품 소유자가 공개 전 별도 절차를 완료합니다.",
            }
            for component, identifier in MODULE.QUALIFICATION_IDENTIFIERS.items()
        ]

    def _git(self, repository: Path, *arguments: str) -> str:
        """! @brief 임시 closure 저장소에서 Git 명령을 실행합니다. """

        return subprocess.check_output(
            ["git", "-C", str(repository), *arguments], text=True
        ).strip()

    def _write_w05_evidence(self, document: dict) -> None:
        """! @brief 시험용 W05 evidence를 현재 임시 경로에 기록합니다. """

        self.w05_evidence_path.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )

    def _closure_repository(
        self,
        root: Path,
        *,
        intermediate: bool = False,
        source_change: str | None = None,
        outside_change: bool = False,
        completion_name: str = "302_M33_W06_완료.md",
        closure_documents: bool = False,
    ) -> tuple[str, str, Path]:
        """! @brief exact source S와 기록 전용 child C를 가진 임시 저장소를 만듭니다. """

        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "M33 Contract Test")
        self._git(root, "config", "user.email", "m33-contract@example.invalid")
        protected = {
            "implementation": root / "libraries/NUCODE/source.cpp",
            "runner": root / "tests/hil/nu54dk/runner.py",
            "target": root / "tests/zephyr/app/src/main.cpp",
            "lock": root / "tools/ci/ncs-3.4.0.lock.json",
        }
        for path in protected.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source = 1\n", encoding="utf-8")
        source_readiness = root / "variants/nu54dk/m33-release-readiness.json"
        source_readiness.parent.mkdir(parents=True)
        source_readiness.write_text(
            '{"status":"not_started"}\n', encoding="utf-8"
        )
        self._git(root, "add", ".")
        self._git(root, "commit", "-q", "-m", "source")
        source = self._git(root, "rev-parse", "HEAD")

        if intermediate:
            (root / "00_Docs").mkdir()
            (root / "00_Docs/TODO_M33.md").write_text(
                "intermediate\n", encoding="utf-8"
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-q", "-m", "intermediate")

        evidence = (
            root / "00_Docs/04_검증 기록/evidence/m33-w06-test/closure.json"
        )
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("{}\n", encoding="utf-8")
        completion = root / "00_Docs/04_검증 기록" / completion_name
        completion.parent.mkdir(parents=True, exist_ok=True)
        completion.write_text("완료\n", encoding="utf-8")
        readiness = root / "variants/nu54dk/m33-release-readiness.json"
        readiness.parent.mkdir(parents=True, exist_ok=True)
        readiness.write_text("{}\n", encoding="utf-8")
        if closure_documents:
            for relative in MODULE.W06_CLOSURE_DOCUMENTS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("완료 근거와 지원 경계\n", encoding="utf-8")
        if source_change is not None:
            protected[source_change].write_text("source = 2\n", encoding="utf-8")
        if outside_change:
            (root / "unapproved.txt").write_text("outside\n", encoding="utf-8")
        self._git(root, "add", ".")
        self._git(root, "commit", "-q", "-m", "closure")
        closure = self._git(root, "rev-parse", "HEAD")
        return source, closure, evidence

    def test_source_hash_is_independent_of_checkout_line_endings(self) -> None:
        """! @brief LF와 CRLF checkout이 같은 예제 source identity를 가집니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m33-eol-") as temporary:
            lf_path = Path(temporary) / "lf.ino"
            crlf_path = Path(temporary) / "crlf.ino"
            lf_path.write_bytes(b"void setup() {}\nvoid loop() {}\n")
            crlf_path.write_bytes(b"void setup() {}\r\nvoid loop() {}\r\n")
            self.assertEqual(MODULE._sha256_text(lf_path), MODULE._sha256_text(crlf_path))

    def test_w05_exact_revision_path_and_work_status_are_fixed(self) -> None:
        """! @brief W05 exact 입력과 W06 진행 중 상태를 생성 계약에 고정합니다. """

        self.assertEqual(
            MODULE.W05_SOURCE_REVISION,
            "5f9b2257e2d9630fc919d9cd6508f918d93207cc",
        )
        self.assertEqual(
            EXPECTED_W05_INSTALLED_EVIDENCE_PATH.relative_to(MODULE.CORE).as_posix(),
            (
                "00_Docs/04_검증 기록/evidence/"
                "m33-w05-exact-5f9b2257/installed-examples.json"
            ),
        )
        self.assertEqual(
            [MODULE._work_status(index) for index in range(1, 9)],
            [
                "completed", "completed", "completed", "completed", "completed",
                "in_progress", "not_started", "not_started",
            ],
        )

    def test_w05_installed_evidence_accepts_preserved_single_retest(self) -> None:
        """! @brief 최초 FAIL과 한 번의 성공 재시험을 보존한 최종 PASS를 허용합니다. """

        evidence = w05_evidence_fixture()
        retry = copy.deepcopy(evidence["builds"][0])
        initial = copy.deepcopy(retry)
        initial.update({"status": "FAIL", "exit_code": 1})
        evidence["diagnostic_retests"] = [{
            "identity": retry["identity"],
            "reason": "initial_compile_failure",
            "attempt": 2,
            "initial": initial,
            "retry": retry,
        }]
        evidence["summary"].update({
            "initial_compile_fail": 1,
            "diagnostic_retest_pass": 1,
        })
        self._write_w05_evidence(evidence)
        validated = MODULE._validate_w05_installed_evidence(self.w05_evidence_path)
        self.assertEqual(validated["diagnostic_retests"][0]["initial"], initial)

        duplicate = copy.deepcopy(evidence)
        duplicate["diagnostic_retests"].append(
            copy.deepcopy(duplicate["diagnostic_retests"][0])
        )
        duplicate["summary"].update({
            "initial_compile_fail": 2,
            "diagnostic_retest_pass": 2,
        })
        self._write_w05_evidence(duplicate)
        with self.assertRaisesRegex(ValueError, "diagnostic retest"):
            MODULE._validate_w05_installed_evidence(self.w05_evidence_path)

        mismatched = copy.deepcopy(evidence)
        mismatched["diagnostic_retests"][0]["retry"]["exit_code"] = 7
        self._write_w05_evidence(mismatched)
        with self.assertRaisesRegex(ValueError, "diagnostic retest"):
            MODULE._validate_w05_installed_evidence(self.w05_evidence_path)

    def test_w05_installed_evidence_rejects_completion_drift_and_secrets(self) -> None:
        """! @brief W05 분모·결과·revision·경로·민감값 변조를 모두 거부합니다. """

        mutations = []

        def add(label: str, mutate) -> None:
            document = w05_evidence_fixture()
            mutate(document)
            mutations.append((label, document))

        add("status", lambda row: row.update({"status": "IN_PROGRESS"}))
        add("finished", lambda row: row.update({"finished_utc": None}))
        add("revision", lambda row: row.update({"installed_revision_after": "f" * 40}))
        add("clean", lambda row: row.update({"installed_clean_after": False}))
        add("libraries", lambda row: row["libraries"].pop())
        add(
            "build identity",
            lambda row: row["builds"][1].update({
                "identity": row["builds"][0]["identity"]
            }),
        )
        add("build timeout", lambda row: row["builds"][0].update({"timed_out": True}))
        add("negative exit", lambda row: row["negative_profiles"][0].update({"exit_code": 0}))
        add(
            "negative timeout",
            lambda row: row["negative_profiles"][0].update({"timed_out": True}),
        )
        add(
            "negative artifact",
            lambda row: row["negative_profiles"][0].update({
                "unexpected_artifact_count": 1
            }),
        )
        add("summary", lambda row: row["summary"].update({"compiled_pass": 203}))
        add("profile", lambda row: row.update({"profile_counts": {"standard": 203}}))
        add("absolute path", lambda row: row.update({"note": r"C:\private\build"}))
        add("raw UID", lambda row: row.update({"raw_uid": "0011223344556677"}))
        add("secret", lambda row: row.update({"note": "token=plain-text-secret"}))
        for label, document in mutations:
            with self.subTest(label=label):
                self._write_w05_evidence(document)
                with self.assertRaises(ValueError):
                    MODULE._validate_w05_installed_evidence(self.w05_evidence_path)

    def test_w05_completion_rejects_missing_committed_payload(self) -> None:
        """! @brief 완료 Markdown만 있고 설치 payload가 없으면 계약 검사를 실패시킵니다. """

        missing = Path(self.temporary.name) / "missing.json"
        with mock.patch.object(MODULE, "W05_INSTALLED_EVIDENCE_PATH", missing):
            with self.assertRaisesRegex(ValueError, "evidence가 없습니다"):
                MODULE.validate(self.document)

    def test_canonical_inventory_denominators(self) -> None:
        """! @brief 고정 SDK·M33·예제·service·시험 분모를 확인합니다. """
        MODULE.validate(self.document)
        counts = self.document["counts"]
        self.assertEqual(counts["work_total"], 8)
        self.assertEqual(counts["work_completed"], 5)
        self.assertEqual(counts["master_sample_total"], 190)
        self.assertEqual(counts["master_variant_total"], 474)
        self.assertEqual(counts["m33_sample_total"], 108)
        self.assertEqual(counts["m33_variant_total"], 318)
        self.assertEqual(counts["installed_example_total"], 204)
        self.assertEqual(counts["installed_ble_radio_example_total"], 175)
        self.assertEqual(counts["installed_core_peripheral_example_total"], 29)
        self.assertEqual(counts["sig_service_total"], 69)
        self.assertEqual(counts["test_family_total"], 12)
        self.assertEqual(counts["test_case_total"], 28)
        self.assertEqual(counts["test_case_passed"], 22)

    def test_deduplication_denominators_are_explicit(self) -> None:
        """! @brief 파일 중복 제거와 기능군 통합 분모를 혼동하지 않습니다. """
        summary = self.document["deduplication_summary"]
        self.assertEqual(
            summary["variant_to_sample"],
            {
                "master_before": 474,
                "master_after": 190,
                "m33_before": 318,
                "m33_after": 108,
            },
        )
        sketches = summary["installed_sketch_exact"]
        self.assertEqual(sketches["before"], 204)
        self.assertEqual(sketches["unique_content_after"], 204)
        self.assertEqual(sketches["exact_duplicate_group_count"], 0)
        self.assertEqual(sketches["unique_name_after"], 204)
        self.assertEqual(sketches["duplicate_name_group_count"], 0)
        self.assertEqual(
            sketches["domain_counts"],
            {"core_peripheral": 29, "bluetooth_radio": 175},
        )
        functional = summary["planned_functional_groups"]
        self.assertEqual(
            functional["by_owner"],
            {"M33-W02": 12, "M33-W03": 4, "M33-W04": 6},
        )
        self.assertEqual(functional["total"], 22)
        self.assertFalse(summary["role_distinct_sketches_are_duplicates"])

        broken = copy.deepcopy(self.document)
        broken["deduplication_summary"]["planned_functional_groups"]["total"] = 21
        with self.assertRaisesRegex(ValueError, "deduplication"):
            MODULE.validate(broken)

    def test_example_discovery_keeps_a_small_front_door(self) -> None:
        """! @brief 대표 진입점과 전체 reference 원장을 동시에 보존합니다. """
        discovery = self.document["example_discovery"]
        self.assertEqual(
            discovery["presentation_tiers"],
            ["start_here", "functional_recipe", "reference"],
        )
        self.assertEqual(len(discovery["start_here_journeys"]), 12)
        self.assertGreaterEqual(discovery["functional_recipe_group_total"], 20)
        self.assertEqual(discovery["m33_planned_functional_group_total"], 22)
        self.assertEqual(discovery["reference_sketch_total"], 204)
        self.assertEqual(discovery["missing_featured_paths"], [])
        self.assertEqual(discovery["featured_sketch_total"], 24)
        self.assertEqual(
            discovery["guidance_contract"]["required_fields"],
            [
                "purpose", "requirements", "configuration", "run_steps",
                "success_output", "common_errors", "next_examples",
            ],
        )
        self.assertEqual(
            discovery["guidance_contract"]["status"],
            "completed",
        )
        self.assertEqual(
            discovery["runtime_role_contract"],
            {
                "example_total": 204,
                "documented_role_slot_total": 372,
                "procedure_status": "documented_not_physical_pass",
                "physical_result_source": "installed_example_catalog.stages.functional_hil",
            },
        )
        self.assertEqual(
            sum(
                entry["presentation_tier"] == "start_here"
                for entry in self.document["installed_example_catalog"]
            ),
            24,
        )
        self.assertTrue(all(
            entry["recipe_group"]
            for entry in self.document["installed_example_catalog"]
        ))
        self.assertFalse(discovery["rules"]["root_readme_lists_every_sketch"])
        self.assertTrue(discovery["rules"]["full_catalog_remains_searchable"])

        example_family = next(
            family for family in self.document["test_families"]
            if family["id"] == "M33-EXAMPLE-01"
        )
        self.assertEqual(
            [case["id"] for case in example_family["cases"]],
            [
                "M33-EXAMPLE-01:catalog",
                "M33-EXAMPLE-01:discovery",
                "M33-EXAMPLE-01:compile",
                "M33-EXAMPLE-01:negative_profiles",
                "M33-EXAMPLE-01:runtime_roles",
            ],
        )
        self.assertEqual(
            [case["denominator"] for case in example_family["cases"]],
            [204, 204, 204, 9, 372],
        )

        broken = copy.deepcopy(self.document)
        broken["example_discovery"]["start_here_journeys"][0]["sketches"][0] = (
            "libraries/missing/Missing.ino"
        )
        with self.assertRaisesRegex(ValueError, "discovery"):
            MODULE.validate(broken)

    def test_duplicate_missing_owner_and_reasonless_exclusion_are_rejected(self) -> None:
        """! @brief 누락·중복·미배정 owner·이유 없는 제외를 거부합니다. """
        duplicate = copy.deepcopy(self.document)
        duplicate["upstream_catalog"].append(copy.deepcopy(duplicate["upstream_catalog"][0]))
        missing_owner = copy.deepcopy(self.document)
        missing_owner["upstream_catalog"][0]["owner_work_id"] = ""
        excluded = copy.deepcopy(self.document)
        row = next(
            entry for entry in excluded["upstream_catalog"]
            if entry["route"] == "excluded"
        )
        row["exclusion_reason"] = None
        for broken in (duplicate, missing_owner, excluded):
            with self.subTest(rows=len(broken["upstream_catalog"])):
                with self.assertRaises(ValueError):
                    MODULE.validate(broken)

    def test_unverified_support_and_publication_are_rejected(self) -> None:
        """! @brief source/build/NOT_RUN을 지원·공개 상태로 승격하지 않습니다. """
        support = copy.deepcopy(self.document)
        support["release_contract"]["validated_support_ids"] = ["source_only"]
        publication = copy.deepcopy(self.document)
        publication["release_contract"]["publication_status"] = "published"
        not_run = copy.deepcopy(self.document)
        not_run["release_contract"]["not_run_is_pass"] = True
        for broken in (support, publication, not_run):
            with self.assertRaisesRegex(ValueError, "promotion"):
                MODULE.validate(broken)

    def test_required_implementation_cannot_be_hidden_as_user_follow_up(self) -> None:
        """! @brief 필수 구현 case를 사용자 후속으로 바꾸지 못하게 합니다. """
        broken = copy.deepcopy(self.document)
        case = broken["test_families"][0]["cases"][0]
        case.update({
            "verification_owner": "user",
            "verification_stage": "user_follow_up",
            "development_blocker": False,
            "release_blocker": False,
        })
        with self.assertRaisesRegex(ValueError, "hidden"):
            MODULE.validate(broken)

    def test_user_follow_up_and_final_host_gate_are_distinct(self) -> None:
        """! @brief 외부 제품 비차단과 Ubuntu/macOS 최종 gate를 구분합니다. """
        external = copy.deepcopy(self.document)
        external["follow_up_cases"][0]["release_blocker"] = True
        host = copy.deepcopy(self.document)
        host["follow_up_cases"][-1]["release_blocker"] = False
        fake_pass = copy.deepcopy(self.document)
        fake_pass["follow_up_cases"][0]["status"] = "PASS"
        for broken in (external, host, fake_pass):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_not_run_and_pass_evidence_rules_are_enforced(self) -> None:
        """! @brief 미실행 evidence와 exact 근거 없는 PASS를 모두 거부합니다. """
        not_run = copy.deepcopy(self.document)
        example = next(
            entry for entry in not_run["test_families"]
            if entry["id"] == "M33-REG-01"
        )
        example["cases"][0]["evidence"] = MODULE.CONTRACT_EVIDENCE
        fake_pass = copy.deepcopy(self.document)
        example = next(
            entry for entry in fake_pass["test_families"]
            if entry["id"] == "M33-REG-01"
        )
        example["cases"][0]["status"] = "PASS"
        for broken in (not_run, fake_pass):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_w06_in_progress_does_not_invoke_closure(self) -> None:
        """! @brief 진행 중인 W06은 완료 전 strict closure를 실행하지 않습니다. """

        self.document["work_packages"][5]["status"] = "in_progress"
        with mock.patch.object(MODULE.m33_regression, "snapshot") as snapshot:
            MODULE.validate(self.document)
        snapshot.assert_not_called()

    def test_w06_completion_invokes_current_clean_strict_closure(self) -> None:
        """! @brief W06 완료를 source S와 바로 다음 기록 commit C에 결합합니다. """
        source_revision = "a" * 40
        closure_revision = "b" * 40
        with tempfile.TemporaryDirectory(prefix="m33-w06-contract-", dir=ROOT) as temporary:
            closure_path = Path(temporary) / "closure.json"
            relative = closure_path.relative_to(ROOT).as_posix()
            closure = {
                "source_revision": source_revision,
                "source_clean": True,
                "qualification": self._qualification(),
            }
            closure_path.write_text(
                json.dumps(closure, ensure_ascii=False), encoding="utf-8"
            )
            self._promote_w06(self.document, relative, source_revision)
            current = {
                "source_revision": closure_revision,
                "source_clean": True,
                "inputs": {
                    "M33": {
                        "path": MODULE.W06_READINESS_PATH.as_posix(),
                        "sha256": "c" * 64,
                    },
                },
            }
            audit = {
                "status": "AUDIT_ONLY",
                "actual_run": "NOT_VERIFIED",
                "source_revision": source_revision,
                "product_qualification": "NOT_ASSESSED",
            }
            with mock.patch.object(
                MODULE.m33_regression, "snapshot", return_value=current
            ) as snapshot, mock.patch.object(
                MODULE.m33_regression, "validate_closure", return_value=audit
            ) as validate_closure, mock.patch.object(
                MODULE,
                "_validate_w06_commit_bridge",
                return_value=[Path(relative)],
            ) as validate_bridge, mock.patch.object(
                MODULE, "_git_blob_sha256", return_value="d" * 64
            ) as blob_digest:
                MODULE.validate(self.document)
            snapshot.assert_called_once_with(MODULE.CORE)
            validate_bridge.assert_called_once_with(
                source_revision, closure_revision, closure_path, MODULE.CORE
            )
            source_context = dict(current)
            source_context["source_revision"] = source_revision
            source_context["inputs"] = {
                "M33": {
                    "path": MODULE.W06_READINESS_PATH.as_posix(),
                    "sha256": "d" * 64,
                },
            }
            blob_digest.assert_called_once_with(
                MODULE.CORE, source_revision, MODULE.W06_READINESS_PATH
            )
            validate_closure.assert_called_once_with(
                closure, closure_path.parent, source_context
            )

    def test_w06_commit_bridge_accepts_only_single_record_child(self) -> None:
        """! @brief S 바로 다음 C의 evidence·완료 문서·readiness 변경만 허용합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-bridge-") as temporary:
            repository = Path(temporary)
            source, closure, evidence = self._closure_repository(repository)
            changed = MODULE._validate_w06_commit_bridge(
                source, closure, evidence, repository
            )
            self.assertIn(
                Path("variants/nu54dk/m33-release-readiness.json"), changed
            )
            self.assertIn(
                Path("00_Docs/04_검증 기록/302_M33_W06_완료.md"), changed
            )
            self.assertEqual(
                MODULE._git_blob_sha256(
                    repository, source, MODULE.W06_READINESS_PATH
                ),
                hashlib.sha256(
                    b'{"status":"not_started"}\n'
                ).hexdigest(),
            )

    def test_w06_external_index_resolves_raw_through_real_git_completion_bridge(self) -> None:
        """! @brief 실제 S→C Git 경계와 외부 byte 검사 뒤에만 strict oracle을 호출합니다. """

        regression = MODULE.m33_regression
        with tempfile.TemporaryDirectory(prefix="m33-w06-public-bridge-") as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            source, _, old_evidence = self._closure_repository(
                repository, completion_name="304_M33_W06_통합_검증_완료.md"
            )
            bundle = root / "private"
            bundle.mkdir()
            closure = {"source_revision": source, "source_clean": True,
                       "qualification": self._qualification()}
            (bundle / "closure.json").write_text(json.dumps(closure), encoding="utf-8")
            raw = bundle / "private.artifact.hex"
            raw.write_bytes(b"private-fixture-byte")
            audit = {"status": "AUDIT_ONLY", "actual_run": "NOT_VERIFIED",
                     "source_revision": source, "product_qualification": "NOT_ASSESSED"}
            with mock.patch.object(regression, "snapshot", return_value={
                    "source_revision": source, "source_clean": True}), \
                    mock.patch.object(regression, "validate_closure", return_value=audit):
                regression.export_closure(bundle / "closure.json", root / "public", repository)
            old_evidence.unlink()
            for path in (root / "public").iterdir():
                (old_evidence.parent / path.name).write_bytes(path.read_bytes())
            evidence = old_evidence.parent / "closure-reference.json"
            relative = evidence.relative_to(repository).as_posix()
            cases = self._promote_w06(self.document, relative, source)
            (repository / MODULE.W06_READINESS_PATH).write_text(
                json.dumps(self.document), encoding="utf-8"
            )
            self._git(repository, "add", ".")
            self._git(repository, "commit", "--amend", "--no-edit", "-q")
            current = {"source_revision": self._git(repository, "rev-parse", "HEAD"),
                       "source_clean": True, "inputs": {"M33": {
                           "path": MODULE.W06_READINESS_PATH.as_posix(), "sha256": "c" * 64}}}
            with mock.patch.object(MODULE, "CORE", repository), \
                    mock.patch.object(regression, "snapshot", return_value=current), \
                    mock.patch.dict(os.environ, {regression.EXTERNAL_CLOSURE_ENV: str(bundle)}), \
                    mock.patch.object(regression, "validate_closure", return_value=audit) as validate:
                MODULE._validate_w06_closure(self.document["work_packages"][5], cases)
                self.assertEqual(1, validate.call_count)
                called_closure, called_base, called_context = validate.call_args.args
                self.assertEqual(closure, called_closure)
                self.assertEqual(bundle, called_base)
                self.assertEqual(source, called_context["source_revision"])
                self.assertEqual(MODULE._git_blob_sha256(repository, source, MODULE.W06_READINESS_PATH),
                                 called_context["inputs"]["M33"]["sha256"])
                validate.reset_mock()
                raw.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "byte/hash drift"):
                    MODULE._validate_w06_closure(self.document["work_packages"][5], cases)
                validate.assert_not_called()

    def test_w06_commit_bridge_rejects_dirty_and_arbitrary_ancestor(self) -> None:
        """! @brief dirty tree와 S 사이에 commit이 끼어든 ancestor 재사용을 거부합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-dirty-") as temporary:
            repository = Path(temporary)
            source, closure, evidence = self._closure_repository(repository)
            (repository / "dirty.tmp").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "clean working tree"):
                MODULE._validate_w06_commit_bridge(
                    source, closure, evidence, repository
                )

        with tempfile.TemporaryDirectory(prefix="m33-w06-ancestor-") as temporary:
            repository = Path(temporary)
            source, closure, evidence = self._closure_repository(
                repository, intermediate=True
            )
            with self.assertRaisesRegex(ValueError, "non-merge child"):
                MODULE._validate_w06_commit_bridge(
                    source, closure, evidence, repository
                )

    def test_w06_commit_bridge_accepts_required_completion_documents(self) -> None:
        """! @brief 전체 현행 문서와 새 번호의 완료 기록을 같은 S→C 경계에서 검사합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-document-bridge-") as temporary:
            repository = Path(temporary)
            source, closure, evidence = self._closure_repository(
                repository, closure_documents=True,
                completion_name="304_M33_W06_통합_검증_완료.md",
            )
            changed = MODULE._validate_w06_commit_bridge(source, closure, evidence, repository)
            self.assertTrue(MODULE.W06_CLOSURE_DOCUMENTS <= set(changed))
            evidence_directory = evidence.parent.relative_to(repository)
            for rejected in (
                "00_Docs/04_검증 기록/304_M33_W06_계획.md",
                "00_Docs/04_검증 기록/304_M33_W07_완료.md",
                "00_Docs/04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md",
                "00_Docs/unapproved.md", "tools/bluetooth/m33_contract.py",
                "00_Docs/TODO_M32.md",
            ):
                with self.subTest(rejected=rejected):
                    self.assertFalse(MODULE._w06_allowed_closure_path(
                        Path(rejected), evidence_directory
                    ))

    def test_w06_unit_fixture_is_independent_of_completed_readiness(self) -> None:
        """! @brief 저장 원장 완료 후에도 시험 fixture의 case·분모만 독립 초기화합니다. """

        completed = copy.deepcopy(self.document)
        self._promote_w06(completed, "recorded/closure.json", "a" * 40)
        original = copy.deepcopy(completed)
        restored = w06_in_progress_fixture(completed)
        self.assertEqual(original, completed)
        self.assertEqual(self.document, restored)
        MODULE.validate(restored)

    def test_w06_commit_bridge_rejects_source_and_outside_changes(self) -> None:
        """! @brief 구현·runner·target·lock과 allowlist 밖 기록 변경을 모두 거부합니다. """

        for field in (
            "implementation",
            "runner",
            "target",
            "lock",
            "outside_change",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory(
                    prefix=f"m33-w06-{field}-") as temporary:
                repository = Path(temporary)
                source, closure, evidence = self._closure_repository(
                    repository,
                    source_change=(
                        field if field != "outside_change" else None
                    ),
                    outside_change=field == "outside_change",
                )
                with self.assertRaisesRegex(ValueError, "allowlist"):
                    MODULE._validate_w06_commit_bridge(
                        source, closure, evidence, repository
                    )

    def test_w06_commit_bridge_rejects_merge_commit(self) -> None:
        """! @brief 기록 파일만 바뀌어도 두 parent merge commit은 허용하지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-merge-") as temporary:
            repository = Path(temporary)
            self._git(repository, "init", "-q")
            self._git(repository, "config", "user.name", "M33 Contract Test")
            self._git(
                repository,
                "config",
                "user.email",
                "m33-contract@example.invalid",
            )
            (repository / "base.txt").write_text("base\n", encoding="utf-8")
            self._git(repository, "add", ".")
            self._git(repository, "commit", "-q", "-m", "source")
            source = self._git(repository, "rev-parse", "HEAD")
            primary = self._git(repository, "rev-parse", "--abbrev-ref", "HEAD")
            self._git(repository, "checkout", "-q", "-b", "side")
            (repository / "00_Docs").mkdir()
            (repository / "00_Docs/TODO_M33.md").write_text(
                "side\n", encoding="utf-8"
            )
            self._git(repository, "add", ".")
            self._git(repository, "commit", "-q", "-m", "side")
            self._git(repository, "checkout", "-q", primary)
            evidence = (
                repository /
                "00_Docs/04_검증 기록/evidence/m33-w06-test/closure.json"
            )
            evidence.parent.mkdir(parents=True)
            evidence.write_text("{}\n", encoding="utf-8")
            completion = (
                repository / "00_Docs/04_검증 기록/302_M33_W06_완료.md"
            )
            completion.write_text("완료\n", encoding="utf-8")
            readiness = repository / "variants/nu54dk/m33-release-readiness.json"
            readiness.parent.mkdir(parents=True)
            readiness.write_text("{}\n", encoding="utf-8")
            self._git(repository, "add", ".")
            self._git(repository, "commit", "-q", "-m", "main record")
            self._git(repository, "merge", "-q", "--no-ff", "side", "-m", "merge")
            closure = self._git(repository, "rev-parse", "HEAD")
            with self.assertRaisesRegex(ValueError, "non-merge child"):
                MODULE._validate_w06_commit_bridge(
                    source, closure, evidence, repository
                )

    def test_w06_false_pass_and_qualification_promotion_are_rejected(self) -> None:
        """! @brief 부분 PASS와 component·제품 자격의 근거 없는 승격을 모두 거부합니다. """
        partial = copy.deepcopy(self.document)
        case = next(
            case
            for family in partial["test_families"]
            if MODULE.TEST_OWNER[family["id"]] == "M33-W06"
            for case in family["cases"]
        )
        case.update({
            "status": "PASS",
            "source_revision": MODULE.W05_SOURCE_REVISION,
            "evidence": MODULE.W05_EVIDENCE,
        })
        partial["counts"]["test_case_passed"] += 1
        with self.assertRaisesRegex(ValueError, "atomic"):
            MODULE.validate(partial)

        valid = {"qualification": self._qualification()}
        mutations = (
            ("component_status", "QUALIFIED"),
            ("applicability", "not_applicable"),
            ("component_version", "NCS 3.4.1"),
            ("design_identifier", "Q123456"),
            ("product_status", "QUALIFIED"),
            ("official_reference", "https://example.com/not-nordic"),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                broken = copy.deepcopy(valid)
                broken["qualification"][0][field] = value
                with self.assertRaisesRegex(ValueError, "qualification"):
                    MODULE._validate_w06_qualification(broken)

    def test_w04_automatic_and_physical_cases_are_distinct(self) -> None:
        """! @brief 자동 필수 검사와 외부 Host 실기 NOT_RUN을 분리합니다. """
        diagnostic = next(
            entry for entry in self.document["test_families"]
            if entry["id"] == "M33-DIAG-01"
        )
        self.assertEqual(
            [case["id"] for case in diagnostic["cases"]],
            [
                "M33-DIAG-01:dtm_twowire",
                "M33-DIAG-01:dtm_h4",
                "M33-DIAG-01:hci_automatic",
            ],
        )
        self.assertTrue(all(
            case["verification_owner"] == "developer" and
            case["development_blocker"] and case["release_blocker"] and
            case["status"] == "PASS" and
            case["source_revision"] == MODULE.W04_SOURCE_REVISION and
            case["evidence"] == MODULE.W04_EVIDENCE
            for case in diagnostic["cases"]
        ))
        follow_up = {
            entry["id"]: entry for entry in self.document["follow_up_cases"]
        }
        expected = {
            "hci_uart_external_host_physical",
            "hci_async_uart_external_host_physical",
            "hci_threewire_external_host_physical",
            "hci_lpuart_external_host_physical",
            "hci_spi_external_host_physical",
        }
        self.assertTrue(expected.issubset(follow_up))
        self.assertTrue(all(
            follow_up[identifier]["status"] == "NOT_RUN" and
            not follow_up[identifier]["development_blocker"] and
            not follow_up[identifier]["release_blocker"]
            for identifier in expected
        ))

    def test_w05_installed_examples_use_exact_build_evidence(self) -> None:
        """! @brief W05 설치 build와 runtime 미실행 경계를 exact 근거로 고정합니다. """

        work = self.document["work_packages"][4]
        self.assertEqual(work["status"], "completed")
        self.assertEqual(work["exact_evidence"], MODULE.W05_EVIDENCE)
        family = next(
            entry for entry in self.document["test_families"]
            if entry["id"] == "M33-EXAMPLE-01"
        )
        self.assertEqual(len(family["cases"]), 5)
        self.assertTrue(all(
            case["status"] == "PASS" and
            case["source_revision"] == MODULE.W05_SOURCE_REVISION and
            case["evidence"] == MODULE.W05_EVIDENCE
            for case in family["cases"]
        ))
        examples = [
            entry for entry in self.document["installed_example_catalog"]
            if entry["owner_work_id"] == "M33-W05"
        ]
        self.assertEqual(len(examples), 6)
        self.assertTrue(all(
            entry["traceability"] == "m33_w05_exact" and
            entry["stages"]["arduino_build"]["status"] == "PASS" and
            entry["stages"]["functional_hil"]["status"] == "NOT_RUN" and
            entry["stages"]["external_peer_interop"]["status"] == "NOT_RUN"
            for entry in examples
        ))

    def test_w01_pass_uses_clean_exact_source_and_evidence(self) -> None:
        """! @brief W01 완료와 네 inventory PASS가 같은 exact 증거를 사용합니다. """
        work = self.document["work_packages"][0]
        self.assertEqual(work["status"], "completed")
        self.assertEqual(work["exact_evidence"], MODULE.W01_EVIDENCE)
        inventory = self.document["test_families"][0]
        self.assertEqual(len(inventory["cases"]), 4)
        self.assertTrue(all(
            case["status"] == "PASS" and
            case["source_revision"] == MODULE.W01_SOURCE_REVISION and
            case["evidence"] == MODULE.W01_EVIDENCE
            for case in inventory["cases"]
        ))

    def test_w02_profile_and_beacon_exact_completion(self) -> None:
        """! @brief W02 profile·Beacon 자동 검사와 HIL 완료를 exact 근거로 고정합니다. """

        work = self.document["work_packages"][1]
        self.assertEqual(work["status"], "completed")
        self.assertEqual(work["exact_evidence"], MODULE.W02_EVIDENCE)
        profile = next(
            entry for entry in self.document["test_families"]
            if entry["id"] == "M33-PROFILE-01"
        )
        beacon = next(
            entry for entry in self.document["test_families"]
            if entry["id"] == "M33-BEACON-01"
        )
        self.assertEqual(len(profile["cases"]), 1)
        self.assertEqual(len(beacon["cases"]), 2)
        self.assertTrue(all(
            case["status"] == "PASS" and
            case["source_revision"] == MODULE.W02_SOURCE_REVISION and
            case["evidence"] == MODULE.W02_EVIDENCE
            for family in (profile, beacon)
            for case in family["cases"]
        ))
        examples = [
            entry for entry in self.document["installed_example_catalog"]
            if entry["owner_work_id"] == "M33-W02"
        ]
        self.assertEqual(len(examples), 9)
        self.assertTrue(all(
            entry["owner_work_id"] == "M33-W02" and
            entry["stages"]["arduino_build"]["status"] == "PASS" and
            entry["stages"]["functional_hil"]["status"] == "PASS" and
            entry["stages"]["external_peer_interop"]["status"] == "NOT_RUN"
            for entry in examples
        ))
        upstream = [
            entry for entry in self.document["upstream_catalog"]
            if entry["owner_work_id"] == "M33-W02" and not entry["exclusion_reason"]
        ]
        self.assertTrue(upstream)
        self.assertTrue(all(
            entry["delivery_state"] == "implemented_m33" and
            entry["execution_requirements"]["resolution"] == "implemented_m33_family"
            for entry in upstream
        ))
        services = [
            entry for entry in self.document["sig_service_catalog"]
            if entry["owner_work_id"] == "M33-W02"
        ]
        profiles = [
            entry for entry in self.document["profile_delivery_catalog"]
            if entry["owner_work_id"] == "M33-W02"
        ]
        self.assertEqual(len(services), 9)
        self.assertEqual(len(profiles), 8)
        self.assertTrue(all(
            entry["delivery_status"] == "implemented_m33"
            for entry in services + profiles
        ))

    def test_w03_ecosystem_exact_completion_and_external_boundary(self) -> None:
        """! @brief W03 자동 검사와 외부 제품 NOT_RUN 경계를 독립적으로 고정합니다. """

        work = self.document["work_packages"][2]
        self.assertEqual(work["status"], "completed")
        self.assertEqual(work["exact_evidence"], MODULE.W03_EVIDENCE)
        ecosystem = next(
            entry for entry in self.document["test_families"]
            if entry["id"] == "M33-ECOSYSTEM-01"
        )
        self.assertEqual(
            [case["id"].split(":", 1)[1] for case in ecosystem["cases"]],
            [
                "fast_pair_input", "fast_pair_locator", "ancs", "ams",
                "access", "templates", "os_ux",
            ],
        )
        self.assertTrue(all(
            case["status"] == "PASS" and
            case["source_revision"] == MODULE.W03_SOURCE_REVISION and
            case["evidence"] == MODULE.W03_EVIDENCE
            for case in ecosystem["cases"]
        ))
        examples = [
            entry for entry in self.document["installed_example_catalog"]
            if entry["owner_work_id"] == "M33-W03"
        ]
        self.assertEqual(len(examples), 2)
        self.assertTrue(all(
            entry["stages"]["arduino_build"]["status"] == "PASS" and
            entry["stages"]["functional_hil"]["status"] == "PASS" and
            entry["stages"]["external_peer_interop"]["status"] == "NOT_RUN"
            for entry in examples
        ))
        external = {
            entry["id"]: entry["status"]
            for entry in self.document["follow_up_cases"]
            if entry["id"].startswith(("apple_", "google_", "enocean_", "memfault_"))
        }
        self.assertEqual(len(external), 5)
        self.assertEqual(set(external.values()), {"NOT_RUN"})

    def test_example_and_sig_service_drift_are_rejected(self) -> None:
        """! @brief 설치 Sketch·service UUID 원장 수작업 drift를 막습니다. """
        example = copy.deepcopy(self.document)
        example["installed_example_catalog"][0]["owner_work_id"] = ""
        service = copy.deepcopy(self.document)
        service["sig_service_catalog"][0]["decision_reason"] = ""
        for broken in (example, service):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_upstream_requirements_and_example_stages_are_separate(self) -> None:
        """! @brief 역할 요구와 source/build/HIL/peer 상태의 분리를 고정합니다. """
        self.assertTrue(all(
            entry["execution_requirements"]["source"]
            for entry in self.document["upstream_catalog"]
        ))
        self.assertTrue(all(
            entry["arduino_delivery"]["owner_work_id"] == entry["owner_work_id"]
            for entry in self.document["upstream_catalog"]
        ))
        self.assertTrue(all(
            set(entry["stages"]) == {
                "source_candidate", "native_build", "arduino_build",
                "functional_hil", "external_peer_interop",
            }
            for entry in self.document["installed_example_catalog"]
        ))

        requirements = copy.deepcopy(self.document)
        requirements["upstream_catalog"][0]["execution_requirements"]["source"] = ""
        stages = copy.deepcopy(self.document)
        del stages["installed_example_catalog"][0]["stages"]["functional_hil"]
        for broken in (requirements, stages):
            with self.assertRaises(ValueError):
                MODULE.validate(broken)

    def test_ncs_340_policy_and_conditional_risks_are_preserved(self) -> None:
        """! @brief SDK 자동 전환과 patch note의 원인 단정을 거부합니다. """
        upgrade = copy.deepcopy(self.document)
        upgrade["sdk_policy"]["active_version"] = "3.4.1"
        cause = copy.deepcopy(self.document)
        cause["sdk_policy"]["patch_note_is_failure_cause"] = True
        for broken in (upgrade, cause):
            with self.assertRaisesRegex(ValueError, "3.4.0 policy"):
                MODULE.validate(broken)
        self.assertEqual(
            self.document["sdk_risk_regressions"], MODULE._sdk_risk_catalog()
        )
        risk_ids = {entry["id"] for entry in MODULE._sdk_risk_catalog()}
        self.assertEqual(risk_ids, set(MODULE.m33_regression.SDK_RISK_CAMPAIGNS))
        self.assertNotIn("DRGN-29446_DRGN-29320", risk_ids)
        self.assertNotIn("MESH_LPN_MCUboot_WDT", risk_ids)
        combined = copy.deepcopy(self.document)
        combined["sdk_risk_regressions"][2]["id"] = "DRGN-29446_DRGN-29320"
        with self.assertRaisesRegex(ValueError, "catalog drift"):
            MODULE.validate(combined)


if __name__ == "__main__":
    unittest.main()
