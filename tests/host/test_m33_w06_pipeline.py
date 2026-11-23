#!/usr/bin/env python3
"""! @brief M33-W06 새 planner·schema·증거 승격 경계를 검증합니다. """

from __future__ import annotations

import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "tools/ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))

import m33_w06_artifacts as artifacts  # noqa: E402
import m33_w06_pipeline as pipeline  # noqa: E402

# @note 뒤이어 로드되는 기존 동적 import 시험이 같은 이름의 module cache를
#       재사용하지 않도록 이 시험이 선점한 이름만 해제합니다.
for imported_name, imported_module in (
        ("m33_regression", pipeline.regression),
        ("m33_regression_run", pipeline.campaign_runner)):
    if sys.modules.get(imported_name) is imported_module:
        del sys.modules[imported_name]


SOURCE = {
    "source_revision": "1" * 40,
    "source_clean": True,
    "board_revision": "2" * 40,
    "board_clean": True,
    "ncs_version": "3.4.0",
    "ncs_revision": "3" * 40,
    "ncs_clean": True,
    "zephyr_revision": "4" * 40,
    "zephyr_clean": True,
    "toolchain_bundle_id": "dcbdc366a1",
    "sdk_root": "C:/ncs/v3.4.0",
    "toolchain_root": "C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk",
    "lock_sha256": "5" * 64,
}


class M33W06PipelineTests(unittest.TestCase):
    """! @brief R1/R2의 실제 registry와 fail-closed record를 검사합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 실제 registry에서 artifact plan과 pipeline inventory를 파생합니다. """

        cls.artifact_plan = artifacts.build_plan(dict(SOURCE))
        cls.inventory = pipeline.create_inventory(cls.artifact_plan)

    def development_plan(self) -> dict:
        """! @brief 한 group의 이동 가능한 개발 계획을 반환합니다. """

        return pipeline.create_execution_plan(
            self.inventory,
            "development_smoke",
            [("families", "gap_links")],
            "unit_fixture",
        )

    def record(self, root: Path, plan: dict, transport: str = "fake") -> dict:
        """! @brief 실제 record parser가 소비할 최소 byte-bearing fixture를 만듭니다. """

        raw = root / "raw.log"
        result = root / "result.json"
        raw.write_bytes(b"READY\nCORE_PATH_PASS\nSTOP\n")
        result.write_bytes(b'{"status":"PASS"}\n')
        return {
            "schema_version": 1,
            "kind": pipeline.RECORD_KIND,
            "mode": plan["mode"],
            "evidence_class": plan["evidence_class"],
            "transport": transport,
            "source": plan["source"],
            "input_fingerprint": plan["input_fingerprint"],
            "runner_fingerprint": "6" * 64,
            "oracle_fingerprint": "7" * 64,
            "schema_fingerprint": "8" * 64,
            "field": "families",
            "group": "gap_links",
            "campaign": "m28_link",
            "attempt": 1,
            "parent": None,
            "prerequisites": [],
            "started_at": "2026-10-07T10:00:00+09:00",
            "ended_at": "2026-10-07T10:00:01+09:00",
            "status": "PASS",
            "error_class": None,
            "raw_outputs": pipeline.execution.references(root, [raw]),
            "outputs": pipeline.execution.references(root, [result]),
            "device": {"start_state": "FAKE_READY", "end_state": "SAFE_STOPPED"},
            "cleanup": {"status": "PASS", "pins": "RELEASED", "clocks": "OFF"},
        }

    def staged_native_campaign(self, root: Path, campaign_id: str) -> Path:
        """! @brief 실제 stage와 같은 symlink layout의 작은 native fixture를 만듭니다. """

        artifact_root = root / "artifacts"
        campaign_root = artifact_root / campaign_id
        campaign_root.mkdir(parents=True)
        rows = [
            row for row in artifacts.plan_artifacts(self.artifact_plan)
            if row[0] == campaign_id
        ]
        for _owner, name in rows:
            build = root / "builds" / name
            image = build / "zephyr" / "zephyr.hex"
            image.parent.mkdir(parents=True)
            image.write_text(":00000001FF\n", encoding="ascii")
            (build / "nucode_arduino_core_build.yml").write_text(
                "source: unit-fixture\n",
                encoding="utf-8",
            )
            (campaign_root / name).symlink_to(image)
        return artifact_root

    def test_r1_maps_all_denominators_consumers_and_adapters(self) -> None:
        """! @brief 49 group·48 campaign·141/9/150 연결에 누락이 없습니다. """

        counts = self.inventory["counts"]
        self.assertEqual(48, counts["campaigns"])
        self.assertEqual(141, counts["build_slots"])
        self.assertEqual(9, counts["runtime_slots"])
        self.assertEqual(150, counts["stage_slots"])
        self.assertEqual(49, counts["groups"])
        self.assertTrue(all(row["consumers"] for row in self.inventory["groups"]))
        self.assertTrue(all(row["adapter"] and row["preparation"]
                            for row in self.inventory["campaigns"]))

    def test_inventory_rejects_duplicate_group_and_hash_rewrite(self) -> None:
        """! @brief 중복 group과 내용에 맞지 않는 hash를 모두 거부합니다. """

        duplicate = copy.deepcopy(self.inventory)
        duplicate["groups"].append(copy.deepcopy(duplicate["groups"][0]))
        duplicate["counts"]["groups"] += 1
        duplicate.pop("inventory_sha256")
        duplicate["inventory_sha256"] = pipeline.canonical_sha256(duplicate)
        with self.assertRaisesRegex(ValueError, "분모|누락|중복"):
            pipeline.validate_inventory(duplicate)

        changed = copy.deepcopy(self.inventory)
        changed["campaigns"][0]["adapter"] = "forged"
        with self.assertRaisesRegex(ValueError, "adapter|hash"):
            pipeline.validate_inventory(changed)

    def test_smoke_plan_prioritizes_stateful_boundaries_and_lists_omissions(self) -> None:
        """! @brief 개발 탐색은 고위험 전환을 먼저 두고 생략 범위를 표시합니다. """

        plan = pipeline.create_execution_plan(self.inventory, "development_smoke")
        first = [(row["field"], row["group"])
                 for row in plan["tasks"][:len(pipeline.HIGH_RISK_GROUPS)]]
        self.assertEqual(list(pipeline.HIGH_RISK_GROUPS), first)
        self.assertFalse(plan["completion_eligible"])
        self.assertTrue(all(campaign["omitted"]
                            for task in plan["tasks"]
                            for campaign in task["campaigns"]))

    def test_each_smoke_campaign_declares_core_negative_and_cleanup_boundaries(self) -> None:
        """! @brief boot-only PASS를 막도록 기능·음성·STOP 경계를 분리합니다. """

        for campaign in self.inventory["campaigns"]:
            semantics = campaign["smoke"]["semantics"]
            self.assertTrue(semantics["core"])
            self.assertEqual("wrong_nonce_or_role_rejected",
                             semantics["adapter_negative"])
            self.assertIn("all_final_semantics", semantics)
            if campaign["verification"] == "physical_hil":
                self.assertTrue(campaign["smoke"]["requires_stop"])

    def test_final_plan_requires_all_groups_and_has_no_omissions(self) -> None:
        """! @brief final mode의 선택 실행이나 smoke 생략 승계를 거부합니다. """

        with self.assertRaisesRegex(ValueError, "49개"):
            pipeline.create_execution_plan(
                self.inventory,
                "final",
                [("families", "gap_links")],
            )
        plan = pipeline.create_execution_plan(self.inventory, "final")
        self.assertEqual(49, plan["selected_group_count"])
        self.assertTrue(plan["completion_eligible"])
        self.assertTrue(all(not campaign["omitted"]
                            for task in plan["tasks"]
                            for campaign in task["campaigns"]))

    def test_plan_rejects_duplicate_wrong_group_mode_and_fingerprint(self) -> None:
        """! @brief 중복·미등록·잘못된 mode·변조 계획은 실행 전에 실패합니다. """

        with self.assertRaisesRegex(ValueError, "중복"):
            pipeline.create_execution_plan(
                self.inventory,
                "development_smoke",
                [("families", "gap_links"), ("families", "gap_links")],
            )
        with self.assertRaisesRegex(ValueError, "registry"):
            pipeline.create_execution_plan(
                self.inventory,
                "development_smoke",
                [("families", "missing")],
            )
        with self.assertRaisesRegex(ValueError, "mode"):
            pipeline.create_execution_plan(self.inventory, "quick")
        changed = self.development_plan()
        changed["tasks"][0]["group"] = "privacy"
        with self.assertRaisesRegex(ValueError, "fingerprint|task"):
            pipeline.validate_execution_plan(changed, self.inventory)

    def test_fake_record_passes_development_parser_but_not_completion_importer(self) -> None:
        """! @brief 같은 parser를 통과한 fake 결과도 물리 최종 PASS로 승격되지 않습니다. """

        plan = self.development_plan()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = self.record(root, plan)
            pipeline.validate_record(record, root, plan)
            with self.assertRaisesRegex(ValueError, "최종 완료"):
                pipeline.validate_record(record, root, plan, completion=True)

    def test_record_rejects_wrong_source_mode_and_unplanned_campaign(self) -> None:
        """! @brief source/mode/campaign drift를 다음 보드 동작 전에 거부합니다. """

        plan = self.development_plan()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = self.record(root, plan)
            wrong_source = copy.deepcopy(record)
            wrong_source["source"]["source_revision"] = "9" * 40
            with self.assertRaisesRegex(ValueError, "source/mode/input"):
                pipeline.validate_record(wrong_source, root, plan)
            wrong_mode = copy.deepcopy(record)
            wrong_mode["mode"] = "final"
            wrong_mode["evidence_class"] = "FINAL"
            wrong_mode["transport"] = "physical"
            with self.assertRaisesRegex(ValueError, "source/mode/input"):
                pipeline.validate_record(wrong_mode, root, plan)
            wrong_campaign = copy.deepcopy(record)
            wrong_campaign["campaign"] = "m28_periodic_past"
            with self.assertRaisesRegex(ValueError, "route|계획"):
                pipeline.validate_record(wrong_campaign, root, plan)

    def test_final_record_rejects_fake_transport_and_cleanup_hold(self) -> None:
        """! @brief final source라도 fake transport와 미확인 STOP을 PASS로 내보내지 않습니다. """

        plan = pipeline.create_execution_plan(self.inventory, "final")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = self.record(root, plan, transport="fake")
            with self.assertRaisesRegex(ValueError, "fake"):
                pipeline.validate_record(record, root, plan)
            record["transport"] = "physical"
            record["cleanup"]["status"] = "SAFETY_HOLD"
            with self.assertRaisesRegex(ValueError, "최종 완료"):
                pipeline.validate_record(record, root, plan, completion=True)

    def test_corrupt_and_relocated_outputs_are_distinguished(self) -> None:
        """! @brief 이동 root는 허용하고 byte 손상은 거부합니다. """

        plan = self.development_plan()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            moved = Path(folder) / "moved"
            source.mkdir()
            record = self.record(source, plan)
            shutil.copytree(source, moved)
            pipeline.validate_record(record, moved, plan)
            (moved / "raw.log").write_bytes(b"mutated")
            with self.assertRaisesRegex(ValueError, "hash|byte"):
                pipeline.validate_record(record, moved, plan)

    def test_record_set_rejects_duplicate_and_missing_pass_denominator(self) -> None:
        """! @brief 중복 attempt와 누락 PASS를 record 집합에서 숨길 수 없습니다. """

        plan = self.development_plan()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = self.record(root, plan)
            with self.assertRaisesRegex(ValueError, "중복"):
                pipeline.validate_record_set([record, record], root, plan)
            failed = copy.deepcopy(record)
            failed["status"] = "FAIL"
            failed["error_class"] = "FUNCTIONAL"
            with self.assertRaisesRegex(ValueError, "분모"):
                pipeline.validate_record_set([failed], root, plan)

    def test_document_only_change_does_not_select_physical_groups(self) -> None:
        """! @brief 순수 문서 변경은 firmware/HIL을 자동 예약하지 않습니다. """

        impact = pipeline.classify_changes(
            self.inventory,
            ["00_Docs/HANDOFF.md", "tools/ci/m33_w06_artifacts.md"],
        )
        self.assertEqual("targeted", impact["classification"])
        self.assertEqual([], impact["selected_groups"])

    def test_registered_runner_change_selects_only_consuming_groups(self) -> None:
        """! @brief 알려진 runner 변경은 그 campaign을 소비하는 group만 선택합니다. """

        impact = pipeline.classify_changes(
            self.inventory,
            ["tests/hil/nu54dk/m29_ble_cache.py"],
        )
        selected = {(row["field"], row["id"])
                    for row in impact["selected_groups"]}
        self.assertEqual("targeted", impact["classification"])
        self.assertIn(("families", "gatt_cache"), selected)
        self.assertNotIn(("families", "iso"), selected)

    def test_unknown_change_falls_back_to_all_groups(self) -> None:
        """! @brief 영향을 입증할 수 없는 변경은 49개 group 전체로 확장합니다. """

        impact = pipeline.classify_changes(
            self.inventory,
            ["cores/arduino/unknown-new-path.cpp"],
        )
        self.assertEqual("full", impact["classification"])
        self.assertEqual(49, len(impact["selected_groups"]))
        self.assertFalse(impact["final_artifact_reuse"])

    def test_r3_native_bundle_imports_in_another_root_with_provenance(self) -> None:
        """! @brief 한 campaign의 image·record가 이동 root에서 같은 hash로 소비됩니다. """

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifact_root = self.staged_native_campaign(root, "m28_link")
            bundle = root / "bundle"
            imported = root / "relocated" / "imported"
            pipeline.create_minimal_bundle(
                self.artifact_plan,
                artifact_root,
                ["m28_link"],
                bundle,
            )
            document = pipeline.import_minimal_bundle(bundle, imported)
            self.assertFalse(document["completion_eligible"])
            validated = pipeline.validate_minimal_import(imported)
            self.assertEqual(3, len(validated["aliases"]))
            for alias in validated["aliases"]:
                link = imported / "artifacts" / alias["campaign_id"] / alias["name"]
                self.assertTrue(link.is_symlink())
                self.assertTrue(artifacts.adjacent_build_record(link.resolve()).is_file())

    def test_minimal_bundle_rejects_tamper_extra_and_runtime_slots(self) -> None:
        """! @brief byte 변조·비계약 파일·runtime input 포함을 모두 거부합니다. """

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifact_root = self.staged_native_campaign(root, "m28_link")
            bundle = root / "bundle"
            document = pipeline.create_minimal_bundle(
                self.artifact_plan,
                artifact_root,
                ["m28_link"],
                bundle,
            )
            first = bundle / document["entries"][0]["artifact"]["path"]
            first.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "byte/hash"):
                pipeline.validate_minimal_bundle(bundle)

            profile_root = self.staged_native_campaign(root, "m33_profiles_standard")
            with self.assertRaisesRegex(ValueError, "native target image"):
                pipeline.create_minimal_bundle(
                    self.artifact_plan,
                    profile_root,
                    ["m33_profiles_standard"],
                    root / "profile-bundle",
                )

    def test_minimal_import_is_development_only_and_alias_drift_fails(self) -> None:
        """! @brief R3 bundle은 final artifact로 승격되지 않고 alias 변경을 검출합니다. """

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifact_root = self.staged_native_campaign(root, "m28_link")
            bundle = root / "bundle"
            imported = root / "imported"
            pipeline.create_minimal_bundle(
                self.artifact_plan,
                artifact_root,
                ["m28_link"],
                bundle,
            )
            pipeline.import_minimal_bundle(bundle, imported)
            import_manifest = pipeline.validate_minimal_import(imported)
            self.assertEqual("DEVELOPMENT", import_manifest["evidence_class"])
            self.assertFalse(import_manifest["completion_eligible"])
            alias = import_manifest["aliases"][0]
            link = imported / "artifacts" / alias["campaign_id"] / alias["name"]
            link.unlink()
            link.symlink_to(imported / "payload" / "missing.hex")
            with self.assertRaisesRegex(ValueError, "alias"):
                pipeline.validate_minimal_import(imported)

    def test_cache_contract_invalidates_source_mode_and_dependency_drift(self) -> None:
        """! @brief cache hit는 source·mode·runner/schema hash가 모두 같을 때만 허용됩니다. """

        plan = self.development_plan()
        dependencies = {"runner": "6" * 64, "schema": "7" * 64}
        contract = pipeline.create_cache_contract(plan, dependencies)
        pipeline.validate_cache_contract(contract, plan, dependencies)
        changed = dict(dependencies)
        changed["runner"] = "8" * 64
        with self.assertRaisesRegex(ValueError, "cache"):
            pipeline.validate_cache_contract(contract, plan, changed)
        final = pipeline.create_execution_plan(self.inventory, "final")
        with self.assertRaisesRegex(ValueError, "cache"):
            pipeline.validate_cache_contract(contract, final, dependencies)

    def test_gc_plan_keeps_active_last_original_and_failure_evidence(self) -> None:
        """! @brief 활성 자료·마지막 원본·실패 raw는 정리 후보가 될 수 없습니다. """

        rows = [
            {"path": "cache/rebuildable", "category": "cache",
             "referenced": False, "active": False, "last_original": False,
             "failure_evidence": False, "reproducible": True},
            {"path": "runs/failed", "category": "run",
             "referenced": True, "active": False, "last_original": True,
             "failure_evidence": True, "reproducible": False},
        ]
        plan = pipeline.create_gc_plan(rows, ["cache/rebuildable"])
        self.assertTrue(plan["dry_run"])
        self.assertEqual(["cache/rebuildable"], plan["candidates"])
        with self.assertRaisesRegex(ValueError, "GC"):
            pipeline.create_gc_plan(rows, ["runs/failed"])

    def test_timing_summary_separates_each_phase_without_eta(self) -> None:
        """! @brief queue/setup/build/download/program/test/cleanup 시간을 혼합하지 않습니다. """

        summary = pipeline.summarize_timings([
            {"phase": "build", "duration_ms": 1200},
            {"phase": "build", "duration_ms": 800},
            {"phase": "test", "duration_ms": 300},
            {"phase": "cleanup", "duration_ms": 20},
        ])
        self.assertEqual(2000, summary["phases"]["build"]["total_ms"])
        self.assertEqual(2, summary["phases"]["build"]["samples"])
        self.assertEqual(2320, summary["total_ms"])
        self.assertIsNone(summary["estimated_completion"])
        with self.assertRaisesRegex(ValueError, "timing"):
            pipeline.summarize_timings([{"phase": "combined", "duration_ms": 1}])


if __name__ == "__main__":
    unittest.main()
