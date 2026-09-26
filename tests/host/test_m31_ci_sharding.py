"""! @brief M31 W08 GitHub Windows shard와 집계 계약을 검사합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RELEASE_ROOT = ROOT / "tools" / "release"
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))


## @brief release 도구를 독립 module 이름으로 로드합니다.
def load_module(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(name, RELEASE_ROOT / filename)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


LIFECYCLE = load_module("m31_ci_test_lifecycle", "m31_windows_lifecycle.py")
SHARD = load_module("m31_ci_test_shard", "m31_windows_example_shard.py")
AGGREGATE = load_module("m31_ci_test_aggregate", "m31_ci_aggregate.py")


class FakeReleaseTool:
    """! @brief unit test에서 package byte 검사만 대체합니다. """

    def __init__(self, plan: dict[str, object]) -> None:
        self.plan = plan

    def validate_plan(self, _path: Path, *, repository: Path) -> dict[str, object]:
        """! @brief 미리 만든 plan을 반환합니다. """
        self.repository = repository
        return self.plan


class M31CiShardingTests(unittest.TestCase):
    """! @brief 8개 shard의 완전성·중복 거부를 검사합니다. """

    def test_eight_shards_partition_all_examples_once(self) -> None:
        """! @brief 113개 예제가 15/14개 shard로 정확히 한 번 나뉩니다. """
        examples = LIFECYCLE.installed_examples(ROOT)
        selections = [SHARD.select_shard(examples, index, 8) for index in range(8)]
        identities = [item[0] for selection in selections for item in selection]
        self.assertEqual([15, 14, 14, 14, 14, 14, 14, 14], [len(item) for item in selections])
        self.assertEqual(LIFECYCLE.EXPECTED_EXAMPLES, len(identities))
        self.assertEqual(LIFECYCLE.EXPECTED_EXAMPLES, len(set(identities)))

    def test_workflow_uses_eight_windows_shards_without_publication(self) -> None:
        """! @brief workflow가 고정 Action과 비공개 8분할만 사용합니다. """
        workflow = (
            ROOT / ".github" / "workflows" / "m31-w08-windows-rc.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("shard: [0, 1, 2, 3, 4, 5, 6, 7]", workflow)
        self.assertIn("fail-fast: false", workflow)
        self.assertIn("--compile-mode representative", workflow)
        self.assertIn("d3f86a106a0bac45b974a628896c90dbdf5c8093", workflow)
        self.assertNotIn("gh release", workflow.casefold())
        self.assertNotIn("publish-release", workflow)
        self.assertNotIn("publish-index", workflow)

    def test_aggregate_accepts_complete_evidence_and_rejects_duplicate(self) -> None:
        """! @brief 동일 package의 8개 완전 shard만 PASS로 집계합니다. """
        examples = LIFECYCLE.installed_examples(ROOT)
        plan: dict[str, object] = {
            "core_revision": "a" * 40,
            "board_revision": "b" * 40,
            "runtime_payload_sha256": "c" * 64,
            "package_reproducibility": {"status": "PASS"},
            "artifacts": {"archive": {"sha256": "d" * 64}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shard_paths: list[Path] = []
            for index in range(8):
                selected = SHARD.select_shard(examples, index, 8)
                document = {
                    "status": "PASS",
                    "source_revision": plan["core_revision"],
                    "release_version": LIFECYCLE.VERSION,
                    "package": {
                        "archive_sha256": plan["artifacts"]["archive"]["sha256"],
                        "runtime_payload_sha256": plan["runtime_payload_sha256"],
                        "board_revision": plan["board_revision"],
                    },
                    "shard": {
                        "index": index,
                        "count": 8,
                        "assignment": "sorted_identity_position_modulo",
                        "global_denominator": LIFECYCLE.EXPECTED_EXAMPLES,
                        "assigned": len(selected),
                        "compiled": len(selected),
                        "failed": 0,
                    },
                    "results": [
                        {"identity": identity, "profile": profile, "status": "PASS"}
                        for identity, _sketch, profile in selected
                    ],
                }
                path = root / f"shard-{index}.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                shard_paths.append(path)
            lifecycle_path = root / "lifecycle.json"
            lifecycle_path.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "source_revision": plan["core_revision"],
                        "release_version": LIFECYCLE.VERSION,
                        "previous_version": LIFECYCLE.PREVIOUS_VERSION,
                        "package": {"archive_sha256": plan["artifacts"]["archive"]["sha256"]},
                        "examples": {
                            "discovered": LIFECYCLE.EXPECTED_EXAMPLES,
                            "compiled": 1,
                            "compile_mode": "representative",
                            "failed": 0,
                        },
                        "execution": {"mode": "serial", "workers": 1, "cache_roots": 1},
                        "lifecycle": {
                            "install_previous": "PASS",
                            "upgrade_candidate": "PASS",
                            "unknown_version_rejected": True,
                            "uninstall": "PASS",
                            "prerequisite_preserved": True,
                            "reinstall": "PASS",
                            "rediscovered_examples": LIFECYCLE.EXPECTED_EXAMPLES,
                            "cache_rebuild": "PASS",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                AGGREGATE.lifecycle, "load_release_tool",
                return_value=FakeReleaseTool(plan),
            ):
                result = AGGREGATE.aggregate(ROOT, root / "plan.json", shard_paths, lifecycle_path)
                self.assertEqual("PASS", result["status"])
                self.assertEqual(LIFECYCLE.EXPECTED_EXAMPLES, result["examples"]["compiled"])

                duplicate = json.loads(shard_paths[1].read_text(encoding="utf-8"))
                duplicate["results"][0] = json.loads(
                    shard_paths[0].read_text(encoding="utf-8")
                )["results"][0]
                shard_paths[1].write_text(json.dumps(duplicate), encoding="utf-8")
                with self.assertRaises(AGGREGATE.M31AggregateFailure):
                    AGGREGATE.aggregate(ROOT, root / "plan.json", shard_paths, lifecycle_path)


if __name__ == "__main__":
    unittest.main()
