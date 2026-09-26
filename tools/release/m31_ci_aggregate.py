#!/usr/bin/env python3
"""! @brief M31 W08 Windows shard와 lifecycle 증거를 fail-closed로 집계합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import m31_windows_lifecycle as lifecycle  # noqa: E402


class M31AggregateFailure(RuntimeError):
    """! @brief shard 누락·중복·identity drift를 나타냅니다. """


## @brief UTF-8 JSON object를 읽습니다.
def read_object(path: Path) -> dict[str, Any]:
    value = lifecycle.read_json(path)
    if not isinstance(value, dict):
        raise M31AggregateFailure(f"JSON object가 아닙니다: {path}")
    return value


## @brief 8개 shard와 대표 lifecycle이 동일 RC를 검증했는지 집계합니다.
def aggregate(
    repository: Path, plan_path: Path, shard_paths: list[Path],
    lifecycle_path: Path,
) -> dict[str, Any]:
    release_tool = lifecycle.load_release_tool()
    plan = release_tool.validate_plan(plan_path, repository=repository)
    expected = lifecycle.installed_examples(repository)
    expected_by_identity = {
        identity: {"position": position, "profile": profile}
        for position, (identity, _sketch, profile) in enumerate(expected)
    }
    if len(expected_by_identity) != lifecycle.EXPECTED_EXAMPLES:
        raise M31AggregateFailure("source 예제 분모가 113이 아닙니다")

    shard_documents = [read_object(path) for path in shard_paths]
    if len(shard_documents) != 8:
        raise M31AggregateFailure(f"shard evidence가 8개가 아닙니다: {len(shard_documents)}")
    by_index: dict[int, dict[str, Any]] = {}
    observed: dict[str, int] = {}
    for document in shard_documents:
        shard = document.get("shard", {})
        index = shard.get("index")
        if (
            document.get("status") != "PASS"
            or document.get("source_revision") != plan["core_revision"]
            or document.get("release_version") != lifecycle.VERSION
            or document.get("package", {}).get("archive_sha256")
            != plan["artifacts"]["archive"]["sha256"]
            or document.get("package", {}).get("runtime_payload_sha256")
            != plan["runtime_payload_sha256"]
            or document.get("package", {}).get("board_revision") != plan["board_revision"]
            or not isinstance(index, int)
            or shard.get("count") != 8
            or shard.get("assignment") != "sorted_identity_position_modulo"
            or shard.get("global_denominator") != lifecycle.EXPECTED_EXAMPLES
            or shard.get("assigned") != shard.get("compiled")
            or shard.get("failed") != 0
            or index in by_index
        ):
            raise M31AggregateFailure("shard identity·분모·package 계약이 다릅니다")
        by_index[index] = document
        results = document.get("results")
        if not isinstance(results, list) or len(results) != shard["compiled"]:
            raise M31AggregateFailure(f"shard {index} 결과 분모가 다릅니다")
        for result in results:
            identity = result.get("identity")
            expected_record = expected_by_identity.get(identity)
            if (
                expected_record is None
                or result.get("status") != "PASS"
                or result.get("profile") != expected_record["profile"]
                or expected_record["position"] % 8 != index
                or identity in observed
            ):
                raise M31AggregateFailure(f"shard {index} 예제 identity가 다릅니다: {identity}")
            observed[identity] = index
    if set(by_index) != set(range(8)):
        raise M31AggregateFailure("shard index 0~7이 완전하지 않습니다")
    if set(observed) != set(expected_by_identity):
        missing = sorted(set(expected_by_identity) - set(observed))
        raise M31AggregateFailure(f"설치 예제 누락이 있습니다: {missing[:3]}")

    lifecycle_document = read_object(lifecycle_path)
    lifecycle_result = lifecycle_document.get("lifecycle", {})
    examples = lifecycle_document.get("examples", {})
    execution = lifecycle_document.get("execution", {})
    if (
        lifecycle_document.get("status") != "PASS"
        or lifecycle_document.get("source_revision") != plan["core_revision"]
        or lifecycle_document.get("package", {}).get("archive_sha256")
        != plan["artifacts"]["archive"]["sha256"]
        or examples.get("discovered") != lifecycle.EXPECTED_EXAMPLES
        or examples.get("compiled") != 1
        or examples.get("compile_mode") != "representative"
        or examples.get("failed") != 0
        or execution != {"mode": "serial", "workers": 1, "cache_roots": 1}
        or lifecycle_result.get("install_previous") != "PASS"
        or lifecycle_result.get("upgrade_candidate") != "PASS"
        or lifecycle_result.get("unknown_version_rejected") is not True
        or lifecycle_result.get("uninstall") != "PASS"
        or lifecycle_result.get("prerequisite_preserved") is not True
        or lifecycle_result.get("reinstall") != "PASS"
        or lifecycle_result.get("rediscovered_examples") != lifecycle.EXPECTED_EXAMPLES
        or lifecycle_result.get("cache_rebuild") != "PASS"
    ):
        raise M31AggregateFailure("Windows lifecycle 증거가 완전하지 않습니다")

    return {
        "schema_version": 1,
        "work_id": "M31-W08",
        "status": "PASS",
        "test": "github_windows_rc_examples_and_lifecycle",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": plan["core_revision"],
        "host_scope": "GitHub Actions windows-2025",
        "package": {
            "archive_sha256": plan["artifacts"]["archive"]["sha256"],
            "runtime_payload_sha256": plan["runtime_payload_sha256"],
            "board_revision": plan["board_revision"],
            "reproducibility": plan["package_reproducibility"],
        },
        "examples": {
            "shards": 8,
            "discovered": lifecycle.EXPECTED_EXAMPLES,
            "compiled": len(observed),
            "failed": 0,
            "missing": 0,
            "duplicates": 0,
            "assignment": "sorted_identity_position_modulo",
            "per_shard": {
                str(index): by_index[index]["shard"]["compiled"]
                for index in sorted(by_index)
            },
        },
        "lifecycle": {
            "status": "PASS",
            "previous_version": lifecycle_document["previous_version"],
            "candidate_version": lifecycle_document["release_version"],
            "representative_compiled": examples["compiled"],
            "unknown_version_rejected": True,
            "uninstall": "PASS",
            "prerequisite_preserved": True,
            "reinstall": "PASS",
            "rediscovered_examples": lifecycle.EXPECTED_EXAMPLES,
            "cache_rebuild": "PASS",
        },
        "publication_allowed": False,
    }


## @brief 집계 JSON을 원자적으로 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parsed = parser.parse_args(arguments)
    if parsed.output.exists():
        parser.error("기존 evidence를 덮어쓰지 않습니다")
    shard_paths = sorted(parsed.shards.resolve().rglob("shard-*.json"))
    result = aggregate(
        parsed.repository.resolve(), parsed.plan.resolve(), shard_paths,
        parsed.lifecycle.resolve(),
    )
    parsed.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = parsed.output.with_suffix(parsed.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(parsed.output)
    print(
        f"M31_CI_AGGREGATE_PASS=shards:{result['examples']['shards']};"
        f"examples:{result['examples']['compiled']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"M31_CI_AGGREGATE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
