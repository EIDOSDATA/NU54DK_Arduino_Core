#!/usr/bin/env python3
"""! @brief M33-W05 8-shard aggregate의 fail-closed 계약을 검사합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = ROOT / "tools" / "ci"
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))


def load_module(name: str, path: Path):
    """! @brief 지정 파일을 독립 module 이름으로 로드합니다. """

    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


RUNNER = load_module(
    "m33_w05_aggregate_test_runner", CI_ROOT / "m33_w05_installed_examples.py"
)
AGGREGATE = load_module(
    "m33_w05_aggregate_test", CI_ROOT / "m33_w05_aggregate.py"
)
TARGET_REVISION = "adb0982d3ea1f2e1a08158289fab8396f9ee899b"
HASH = "a" * 64


def build_row(identity: str, catalog: dict[str, dict]) -> dict[str, object]:
    """! @brief 최종 PASS build evidence fixture를 만듭니다. """

    return {
        "identity": identity,
        "profile": catalog[identity]["profile"],
        "status": "PASS",
        "exit_code": 0,
        "timed_out": False,
        "elapsed_s": 1.0,
        "sketch_sha256": catalog[identity]["sketch_sha256"],
        "log_sha256": HASH,
        "manifest_sha256": HASH,
        "hex_sha256": HASH,
        "failure": None,
        "failure_tail": [],
    }


def negative_row(case: dict[str, str]) -> dict[str, object]:
    """! @brief 기대 profile 거부 PASS evidence fixture를 만듭니다. """

    return {
        "id": case["id"],
        "identity": case["identity"],
        "rejected_profile": case["profile"],
        "expected_marker": case["marker"],
        "status": "PASS",
        "exit_code": 1,
        "timed_out": False,
        "unexpected_artifact_count": 0,
        "elapsed_s": 1.0,
        "log_sha256": HASH,
        "failure_tail": [],
    }


def shard_documents() -> list[dict[str, object]]:
    """! @brief 실제 source catalog에 맞는 8개 shard fixture를 만듭니다. """

    catalog = RUNNER.load_catalog(ROOT)
    libraries = []
    for row in AGGREGATE.expected_library_rows(ROOT, catalog).values():
        libraries.append({**row, "container_platform": "nucode:zephyr@0.5.0"})
    common = {
        "schema_version": 1,
        "work_id": "M33-W05",
        "test_id": "M33-EXAMPLE-01",
        "status": "PASS",
        "observed_utc": "2026-10-04T00:00:00+00:00",
        "source_revision": TARGET_REVISION,
        "installed_source_revision": TARGET_REVISION,
        "source_clean_before": True,
        "installed_clean_before": True,
        "host_scope": "Windows clean installed tree",
        "fixed_inputs": AGGREGATE.expected_fixed_inputs(ROOT),
        "tools": {
            "arduino_cli_sha256": HASH,
            "arduino_config_sha256": HASH,
        },
        "diagnostic_retest_policy": {
            "maximum_per_failed_build": 1,
            "fresh_build_directory": True,
            "serial": True,
            "initial_failure_is_preserved": True,
        },
        "denominators": {
            "catalog": 204,
            "discovered": 204,
            "compiled": 204,
            "negative_profiles": 9,
        },
        "profile_counts": AGGREGATE.expected_profile_counts(catalog),
        "claim_boundary": {
            "compile_is_runtime": False,
            "negative_rejection_is_feature_runtime": False,
            "external_io_not_run_is_pass": False,
            "physical_runtime_recorded_elsewhere": True,
        },
        "metadata_sha256": RUNNER.sha256_file(
            ROOT / "libraries" / "example-metadata.json"
        ),
        "libraries": libraries,
        "diagnostic_retests": [],
        "source_clean_after": True,
        "source_revision_after": TARGET_REVISION,
        "installed_clean_after": True,
        "installed_revision_after": TARGET_REVISION,
        "installed_tree_unchanged": True,
        "finished_utc": "2026-10-04T01:00:00+00:00",
    }
    documents = []
    for index in range(RUNNER.CI_SHARD_COUNT):
        identities, cases = RUNNER.selected_work(
            catalog, index, RUNNER.CI_SHARD_COUNT
        )
        builds = [build_row(identity, catalog) for identity in identities]
        negatives = [negative_row(case) for case in cases]
        document = json.loads(json.dumps(common))
        document.update({
            "isolation": {
                "source_path_sha256": "b" * 64,
                "installed_path_sha256": "c" * 64,
                "build_path_sha256": f"{index:x}" * 64,
                "source_install_separate": True,
                "fresh_build_root": True,
                "jobs": 2,
            },
            "shard": {
                "index": index,
                "count": RUNNER.CI_SHARD_COUNT,
                "assignment": RUNNER.CI_SHARD_ASSIGNMENT,
                "global_compiled": RUNNER.EXPECTED_EXAMPLES,
                "global_negative_profiles": len(RUNNER.NEGATIVE_PROFILE_MATRIX),
                "assigned_compiled": len(builds),
                "assigned_negative_profiles": len(negatives),
            },
            "builds": builds,
            "negative_profiles": negatives,
            "summary": {
                "catalog": RUNNER.EXPECTED_EXAMPLES,
                "discovered": RUNNER.EXPECTED_EXAMPLES,
                "compiled_pass": len(builds),
                "compiled_fail": 0,
                "initial_compile_fail": 0,
                "diagnostic_retest_pass": 0,
                "diagnostic_retest_fail": 0,
                "negative_pass": len(negatives),
                "negative_fail": 0,
            },
        })
        documents.append(document)
    return documents


def write_shards(root: Path, documents: list[dict[str, object]]) -> list[Path]:
    """! @brief shard fixture를 JSON 파일로 기록합니다. """

    paths = []
    for index, document in enumerate(documents):
        path = root / f"shard-{index}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(path)
    return paths


class M33W05AggregateTests(unittest.TestCase):
    """! @brief 204+9 aggregate의 완전성·민감정보·병렬도 거부를 검사합니다. """

    def aggregate_documents(self, documents: list[dict[str, object]]) -> dict:
        """! @brief clean checkout 검사를 대체하고 fixture를 집계합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-aggregate-") as temporary:
            paths = write_shards(Path(temporary), documents)
            with mock.patch.object(AGGREGATE, "validate_target_checkout"):
                return AGGREGATE.aggregate(ROOT, TARGET_REVISION, paths)

    def test_aggregate_accepts_exact_eight_shards(self) -> None:
        """! @brief 완전한 8개 shard를 기존 204+9 evidence schema로 병합합니다. """

        result = self.aggregate_documents(shard_documents())
        self.assertEqual("PASS", result["status"])
        self.assertEqual(204, len(result["builds"]))
        self.assertEqual(204, len({row["identity"] for row in result["builds"]}))
        self.assertEqual(9, len(result["negative_profiles"]))
        self.assertEqual(8, result["isolation"]["shards"])
        self.assertEqual(2, result["isolation"]["jobs_per_shard_max"])
        self.assertEqual(204, result["summary"]["compiled_pass"])
        self.assertEqual(9, result["summary"]["negative_pass"])

    def test_aggregate_rejects_missing_duplicate_and_wrong_assignment(self) -> None:
        """! @brief shard 누락·index 중복·다른 shard identity를 모두 거부합니다. """

        documents = shard_documents()
        with self.assertRaises(AGGREGATE.M33W05AggregateFailure):
            self.aggregate_documents(documents[:-1])

        documents = shard_documents()
        documents[1]["shard"]["index"] = 0
        with self.assertRaises(AGGREGATE.M33W05AggregateFailure):
            self.aggregate_documents(documents)

        documents = shard_documents()
        documents[1]["builds"][0] = documents[0]["builds"][0]
        with self.assertRaises(AGGREGATE.M33W05AggregateFailure):
            self.aggregate_documents(documents)

    def test_aggregate_rejects_timeout_artifact_and_more_than_two_jobs(self) -> None:
        """! @brief timeout·negative artifact·jobs 상한 위반을 성공으로 집계하지 않습니다. """

        for mutation in ("timeout", "artifact", "jobs"):
            with self.subTest(mutation=mutation):
                documents = shard_documents()
                if mutation == "timeout":
                    documents[0]["builds"][0]["timed_out"] = True
                elif mutation == "artifact":
                    documents[0]["negative_profiles"][0]["unexpected_artifact_count"] = 1
                else:
                    documents[0]["isolation"]["jobs"] = 3
                with self.assertRaises(AGGREGATE.M33W05AggregateFailure):
                    self.aggregate_documents(documents)

    def test_aggregate_preserves_one_retest_and_rejects_duplicate(self) -> None:
        """! @brief 최초 FAIL과 최종 PASS를 묶은 identity별 단일 재시험만 허용합니다. """

        documents = shard_documents()
        retry = documents[0]["builds"][0]
        identity = retry["identity"]
        retest = {
            "identity": identity,
            "reason": "initial_compile_failure",
            "attempt": 2,
            "initial": {
                "identity": identity,
                "status": "FAIL",
                "failure": "compile_or_manifest_failure",
            },
            "retry": retry,
        }
        documents[0]["diagnostic_retests"] = [retest]
        documents[0]["summary"]["initial_compile_fail"] = 1
        documents[0]["summary"]["diagnostic_retest_pass"] = 1
        result = self.aggregate_documents(documents)
        self.assertEqual(1, result["summary"]["initial_compile_fail"])
        self.assertEqual("FAIL", result["diagnostic_retests"][0]["initial"]["status"])

        documents[0]["diagnostic_retests"] = [retest, retest]
        documents[0]["summary"]["initial_compile_fail"] = 2
        documents[0]["summary"]["diagnostic_retest_pass"] = 2
        with self.assertRaises(AGGREGATE.M33W05AggregateFailure):
            self.aggregate_documents(documents)

    def test_aggregate_rejects_sensitive_values(self) -> None:
        """! @brief 절대 경로·raw UID·secret이 든 shard artifact를 거부합니다. """

        mutations = (
            ("note", "C:\\Users\\runner\\private.txt"),
            ("raw_uid", "0011223344556677"),
            ("note", "authorization: bearer do-not-publish"),
        )
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                documents = shard_documents()
                documents[0][key] = value
                with self.assertRaises(AGGREGATE.M33W05AggregateFailure):
                    self.aggregate_documents(documents)

    def test_workflow_separates_control_target_and_eight_shards(self) -> None:
        """! @brief workflow의 branch·exact target·8-shard·jobs 2 계약을 고정합니다. """

        workflow = (
            ROOT / ".github" / "workflows" / "m33-w05-installed-examples.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertIn("target_source_sha:", workflow)
        self.assertIn("path: control", workflow)
        self.assertIn("path: target", workflow)
        self.assertIn("path: installed", workflow)
        self.assertIn("-ItemType Junction", workflow)
        self.assertIn("shard: [0, 1, 2, 3, 4, 5, 6, 7]", workflow)
        self.assertIn("--jobs 2", workflow)
        self.assertIn("--target-revision $env:TARGET_SOURCE_SHA", workflow)
        self.assertNotIn("gh release", workflow.casefold())


if __name__ == "__main__":
    unittest.main(verbosity=2)
