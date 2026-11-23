#!/usr/bin/env python3
"""! @brief M33-W05 Windows shard evidence를 fail-closed로 집계합니다. """

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import m33_w05_installed_examples as runner  # noqa: E402


class M33W05AggregateFailure(RuntimeError):
    """! @brief shard 누락·중복·변조를 나타냅니다. """


def utc_now() -> str:
    """! @brief 현재 UTC 시각을 evidence 문자열로 반환합니다. """

    return datetime.now(timezone.utc).isoformat()


def require_sha256(value: object, label: str) -> str:
    """! @brief 값이 소문자 SHA-256인지 검사해 반환합니다. """

    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise M33W05AggregateFailure(f"{label} SHA-256이 잘못되었습니다")
    return value


def validate_target_checkout(repository: Path, target_revision: str) -> None:
    """! @brief aggregate 대상 checkout이 요청한 exact clean source인지 검사합니다. """

    if re.fullmatch(r"[0-9a-f]{40}", target_revision) is None:
        raise M33W05AggregateFailure("target revision은 full lowercase SHA여야 합니다")
    if runner.git_output(repository, "status", "--porcelain"):
        raise M33W05AggregateFailure("aggregate target checkout이 clean하지 않습니다")
    if runner.git_output(repository, "rev-parse", "HEAD") != target_revision:
        raise M33W05AggregateFailure("aggregate target checkout revision이 다릅니다")


def expected_profile_counts(catalog: dict[str, dict]) -> dict[str, int]:
    """! @brief exact source catalog의 권장 profile 분모를 계산합니다. """

    return {
        profile: sum(entry["profile"] == profile for entry in catalog.values())
        for profile in sorted(
            {entry["profile"] for entry in catalog.values()}, key=str.casefold
        )
    }


def expected_library_rows(
    repository: Path, catalog: dict[str, dict]
) -> dict[str, dict[str, Any]]:
    """! @brief source에서 library identity·분모·tree 지문을 계산합니다. """

    groups: dict[str, set[str]] = {}
    for identity in catalog:
        library = identity.split("/", 1)[0]
        groups.setdefault(library, set()).add(identity)
    result: dict[str, dict[str, Any]] = {}
    for directory in sorted(groups, key=str.casefold):
        root = repository / "libraries" / directory
        file_count, tree_sha256 = runner.tree_fingerprint(root)
        result[directory] = {
            "directory": directory,
            "name": runner.library_name(root / "library.properties"),
            "example_count": len(groups[directory]),
            "file_count": file_count,
            "tree_sha256": tree_sha256,
        }
    if len(result) != 24 or sum(
        row["example_count"] for row in result.values()
    ) != runner.EXPECTED_EXAMPLES:
        raise M33W05AggregateFailure("source library 분모가 24/204가 아닙니다")
    return result


def validate_libraries(
    rows: object, expected: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """! @brief shard의 24개 discovery row를 exact source와 대조합니다. """

    if not isinstance(rows, list) or len(rows) != len(expected):
        raise M33W05AggregateFailure("shard library 분모가 다릅니다")
    observed: dict[str, dict[str, Any]] = {}
    required_keys = {
        "directory", "name", "example_count", "file_count", "tree_sha256",
        "container_platform",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != required_keys:
            raise M33W05AggregateFailure("shard library row schema가 다릅니다")
        directory = row.get("directory")
        if not isinstance(directory, str) or directory in observed:
            raise M33W05AggregateFailure("shard library identity가 중복됐습니다")
        expected_row = expected.get(directory)
        if expected_row is None or any(
            row.get(key) != value for key, value in expected_row.items()
        ):
            raise M33W05AggregateFailure(f"shard library source 지문이 다릅니다: {directory}")
        container = row.get("container_platform")
        if container is not None and not isinstance(container, str):
            raise M33W05AggregateFailure("container platform 값이 잘못되었습니다")
        observed[directory] = row
    if set(observed) != set(expected):
        raise M33W05AggregateFailure("shard library identity 집합이 다릅니다")
    return rows


def expected_fixed_inputs(repository: Path) -> dict[str, str]:
    """! @brief source lock에서 shard가 기록해야 할 고정 입력을 반환합니다. """

    lock = runner.read_json(repository / "tools" / "ci" / "ncs-3.4.0.lock.json")
    return {
        "ncs_version": "3.4.0",
        "nrf_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "board_revision": lock["board"]["revision"],
        "target": runner.TARGET_BOARD,
    }


def validate_build_rows(
    rows: object, expected_identities: list[str], catalog: dict[str, dict]
) -> dict[str, dict[str, Any]]:
    """! @brief shard build가 배정 identity를 최종 PASS로 정확히 한 번 포함하는지 검사합니다. """

    if not isinstance(rows, list) or len(rows) != len(expected_identities):
        raise M33W05AggregateFailure("shard build 분모가 다릅니다")
    observed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise M33W05AggregateFailure("shard build row가 object가 아닙니다")
        identity = row.get("identity")
        exit_code = row.get("exit_code")
        elapsed = row.get("elapsed_s")
        if (
            not isinstance(identity, str)
            or identity in observed
            or identity not in catalog
            or row.get("profile") != catalog[identity]["profile"]
            or row.get("sketch_sha256") != catalog[identity]["sketch_sha256"]
            or row.get("status") != "PASS"
            or not isinstance(exit_code, int)
            or isinstance(exit_code, bool)
            or exit_code != 0
            or row.get("timed_out") is not False
            or not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or elapsed < 0
            or row.get("failure") is not None
            or row.get("failure_tail") != []
        ):
            raise M33W05AggregateFailure(f"shard build 결과가 잘못되었습니다: {identity}")
        for key in ("log_sha256", "manifest_sha256", "hex_sha256"):
            require_sha256(row.get(key), f"build {identity} {key}")
        observed[identity] = row
    if set(observed) != set(expected_identities):
        raise M33W05AggregateFailure("shard build 배정 identity가 다릅니다")
    return observed


def validate_retests(
    rows: object, builds: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """! @brief 최초 실패 보존과 identity별 최대 1회 진단 재시험을 검사합니다. """

    if not isinstance(rows, list):
        raise M33W05AggregateFailure("진단 재시험 row가 배열이 아닙니다")
    identities: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise M33W05AggregateFailure("진단 재시험 row가 object가 아닙니다")
        identity = row.get("identity")
        initial = row.get("initial")
        retry = row.get("retry")
        if (
            not isinstance(identity, str)
            or identity in identities
            or identity not in builds
            or row.get("reason") != "initial_compile_failure"
            or row.get("attempt") != 2
            or not isinstance(initial, dict)
            or initial.get("identity") != identity
            or initial.get("status") != "FAIL"
            or not isinstance(retry, dict)
            or retry != builds[identity]
        ):
            raise M33W05AggregateFailure(f"진단 재시험 계약이 다릅니다: {identity}")
        identities.add(identity)
    return rows


def validate_negative_rows(
    rows: object, expected_cases: list[dict[str, str]]
) -> dict[str, dict[str, Any]]:
    """! @brief 배정 negative가 nonzero·no-timeout·artifact 0인지 검사합니다. """

    if not isinstance(rows, list) or len(rows) != len(expected_cases):
        raise M33W05AggregateFailure("shard negative 분모가 다릅니다")
    expected = {case["id"]: case for case in expected_cases}
    observed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise M33W05AggregateFailure("shard negative row가 object가 아닙니다")
        identifier = row.get("id")
        case = expected.get(identifier) if isinstance(identifier, str) else None
        exit_code = row.get("exit_code")
        elapsed = row.get("elapsed_s")
        if (
            case is None
            or identifier in observed
            or row.get("identity") != case["identity"]
            or row.get("rejected_profile") != case["profile"]
            or row.get("expected_marker") != case["marker"]
            or row.get("status") != "PASS"
            or not isinstance(exit_code, int)
            or isinstance(exit_code, bool)
            or exit_code == 0
            or row.get("timed_out") is not False
            or row.get("unexpected_artifact_count") != 0
            or not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or elapsed < 0
            or row.get("failure_tail") != []
        ):
            raise M33W05AggregateFailure(f"shard negative 결과가 잘못되었습니다: {identifier}")
        require_sha256(row.get("log_sha256"), f"negative {identifier} log")
        observed[identifier] = row
    if set(observed) != set(expected):
        raise M33W05AggregateFailure("shard negative 배정 identity가 다릅니다")
    return observed


def validate_shard(
    document: dict[str, Any], repository: Path, target_revision: str,
    catalog: dict[str, dict], library_rows: dict[str, dict[str, Any]],
) -> tuple[int, dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """! @brief 단일 shard의 source·분모·결과·불변성 계약을 검사합니다. """

    try:
        runner.validate_public_values(document)
    except runner.M33W05Failure as error:
        raise M33W05AggregateFailure(str(error)) from error
    shard = document.get("shard")
    if not isinstance(shard, dict):
        raise M33W05AggregateFailure("shard metadata가 없습니다")
    index = shard.get("index")
    if not isinstance(index, int) or isinstance(index, bool):
        raise M33W05AggregateFailure("shard index가 정수가 아닙니다")
    expected_build_identities, expected_negative_cases = runner.selected_work(
        catalog, index, runner.CI_SHARD_COUNT
    )
    expected_shard = {
        "index": index,
        "count": runner.CI_SHARD_COUNT,
        "assignment": runner.CI_SHARD_ASSIGNMENT,
        "global_compiled": runner.EXPECTED_EXAMPLES,
        "global_negative_profiles": len(runner.NEGATIVE_PROFILE_MATRIX),
        "assigned_compiled": len(expected_build_identities),
        "assigned_negative_profiles": len(expected_negative_cases),
    }
    if shard != expected_shard:
        raise M33W05AggregateFailure(f"shard {index} 배정 metadata가 다릅니다")
    revision_fields = (
        "source_revision", "installed_source_revision",
        "source_revision_after", "installed_revision_after",
    )
    if (
        document.get("schema_version") != 1
        or document.get("work_id") != "M33-W05"
        or document.get("test_id") != "M33-EXAMPLE-01"
        or document.get("status") != "PASS"
        or any(document.get(field) != target_revision for field in revision_fields)
        or document.get("source_clean_before") is not True
        or document.get("installed_clean_before") is not True
        or document.get("source_clean_after") is not True
        or document.get("installed_clean_after") is not True
        or document.get("installed_tree_unchanged") is not True
        or not isinstance(document.get("observed_utc"), str)
        or not document["observed_utc"].strip()
        or not isinstance(document.get("finished_utc"), str)
        or not document["finished_utc"].strip()
    ):
        raise M33W05AggregateFailure(f"shard {index} 완료·revision 계약이 다릅니다")
    if document.get("fixed_inputs") != expected_fixed_inputs(repository):
        raise M33W05AggregateFailure(f"shard {index} fixed input이 다릅니다")
    if document.get("denominators") != {
        "catalog": runner.EXPECTED_EXAMPLES,
        "discovered": runner.EXPECTED_EXAMPLES,
        "compiled": runner.EXPECTED_EXAMPLES,
        "negative_profiles": len(runner.NEGATIVE_PROFILE_MATRIX),
    }:
        raise M33W05AggregateFailure(f"shard {index} global 분모가 다릅니다")
    isolation = document.get("isolation")
    if (
        not isinstance(isolation, dict)
        or set(isolation) != {
            "source_path_sha256", "installed_path_sha256", "build_path_sha256",
            "source_install_separate", "fresh_build_root", "jobs",
        }
        or isolation.get("source_install_separate") is not True
        or isolation.get("fresh_build_root") is not True
        or not isinstance(isolation.get("jobs"), int)
        or isinstance(isolation.get("jobs"), bool)
        or not 1 <= isolation["jobs"] <= 2
    ):
        raise M33W05AggregateFailure(f"shard {index} 격리·병렬도 계약이 다릅니다")
    for key in ("source_path_sha256", "installed_path_sha256", "build_path_sha256"):
        require_sha256(isolation.get(key), f"shard {index} {key}")
    if isolation["source_path_sha256"] == isolation["installed_path_sha256"]:
        raise M33W05AggregateFailure(f"shard {index} source/install 경로가 같습니다")
    tools = document.get("tools")
    if not isinstance(tools, dict) or set(tools) != {
        "arduino_cli_sha256", "arduino_config_sha256",
    }:
        raise M33W05AggregateFailure(f"shard {index} tool schema가 다릅니다")
    for key, value in tools.items():
        require_sha256(value, f"shard {index} {key}")
    if document.get("metadata_sha256") != runner.sha256_file(
        repository / "libraries" / "example-metadata.json"
    ):
        raise M33W05AggregateFailure(f"shard {index} metadata hash가 다릅니다")
    if document.get("profile_counts") != expected_profile_counts(catalog):
        raise M33W05AggregateFailure(f"shard {index} profile 분모가 다릅니다")
    libraries = validate_libraries(document.get("libraries"), library_rows)
    builds = validate_build_rows(
        document.get("builds"), expected_build_identities, catalog
    )
    retests = validate_retests(document.get("diagnostic_retests"), builds)
    negatives = validate_negative_rows(
        document.get("negative_profiles"), expected_negative_cases
    )
    if document.get("diagnostic_retest_policy") != {
        "maximum_per_failed_build": runner.MAX_DIAGNOSTIC_RETESTS_PER_BUILD,
        "fresh_build_directory": True,
        "serial": True,
        "initial_failure_is_preserved": True,
    }:
        raise M33W05AggregateFailure(f"shard {index} 재시험 정책이 다릅니다")
    if document.get("claim_boundary") != {
        "compile_is_runtime": False,
        "negative_rejection_is_feature_runtime": False,
        "external_io_not_run_is_pass": False,
        "physical_runtime_recorded_elsewhere": True,
    }:
        raise M33W05AggregateFailure(f"shard {index} claim boundary가 다릅니다")
    summary = document.get("summary")
    if summary != {
        "catalog": runner.EXPECTED_EXAMPLES,
        "discovered": runner.EXPECTED_EXAMPLES,
        "compiled_pass": len(builds),
        "compiled_fail": 0,
        "initial_compile_fail": len(retests),
        "diagnostic_retest_pass": len(retests),
        "diagnostic_retest_fail": 0,
        "negative_pass": len(negatives),
        "negative_fail": 0,
    }:
        raise M33W05AggregateFailure(f"shard {index} summary가 다릅니다")
    if sum(row["example_count"] for row in libraries) != runner.EXPECTED_EXAMPLES:
        raise M33W05AggregateFailure(f"shard {index} discovery 합계가 다릅니다")
    return index, builds, retests, negatives


def aggregate(
    repository: Path, target_revision: str, shard_paths: list[Path]
) -> dict[str, Any]:
    """! @brief 8개 shard를 기존 전수 evidence schema로 병합합니다. """

    validate_target_checkout(repository, target_revision)
    catalog = runner.load_catalog(repository)
    library_rows = expected_library_rows(repository, catalog)
    if len(shard_paths) != runner.CI_SHARD_COUNT:
        raise M33W05AggregateFailure(
            f"shard evidence가 8개가 아닙니다: {len(shard_paths)}"
        )
    documents = [runner.read_json(path) for path in shard_paths]
    by_index: dict[int, dict[str, Any]] = {}
    builds: dict[str, dict[str, Any]] = {}
    negatives: dict[str, dict[str, Any]] = {}
    retests: list[dict[str, Any]] = []
    common_fields = (
        "fixed_inputs", "tools", "diagnostic_retest_policy", "denominators",
        "profile_counts", "claim_boundary", "metadata_sha256", "libraries",
    )
    reference: dict[str, Any] | None = None
    for document in documents:
        index, shard_builds, shard_retests, shard_negatives = validate_shard(
            document, repository, target_revision, catalog, library_rows
        )
        if index in by_index:
            raise M33W05AggregateFailure(f"shard index가 중복됐습니다: {index}")
        if reference is None:
            reference = document
        elif any(document.get(field) != reference.get(field) for field in common_fields):
            raise M33W05AggregateFailure(f"shard {index} 공통 입력이 다릅니다")
        duplicates = set(builds) & set(shard_builds)
        if duplicates:
            raise M33W05AggregateFailure(f"build identity가 중복됐습니다: {sorted(duplicates)[0]}")
        negative_duplicates = set(negatives) & set(shard_negatives)
        if negative_duplicates:
            raise M33W05AggregateFailure(
                f"negative id가 중복됐습니다: {sorted(negative_duplicates)[0]}"
            )
        by_index[index] = document
        builds.update(shard_builds)
        negatives.update(shard_negatives)
        retests.extend(shard_retests)
    if set(by_index) != set(range(runner.CI_SHARD_COUNT)):
        raise M33W05AggregateFailure("shard index 0~7이 완전하지 않습니다")
    source_paths = {
        document["isolation"]["source_path_sha256"] for document in by_index.values()
    }
    installed_paths = {
        document["isolation"]["installed_path_sha256"] for document in by_index.values()
    }
    build_paths = {
        document["isolation"]["build_path_sha256"] for document in by_index.values()
    }
    if (
        len(source_paths) != 1
        or len(installed_paths) != 1
        or len(build_paths) != runner.CI_SHARD_COUNT
    ):
        raise M33W05AggregateFailure("shard source/install 또는 build 경로 격리가 다릅니다")
    if set(builds) != set(catalog):
        raise M33W05AggregateFailure("204개 build identity가 완전하지 않습니다")
    expected_negative_ids = {case["id"] for case in runner.NEGATIVE_PROFILE_MATRIX}
    if set(negatives) != expected_negative_ids:
        raise M33W05AggregateFailure("9개 negative identity가 완전하지 않습니다")
    if reference is None:
        raise M33W05AggregateFailure("aggregate reference shard가 없습니다")
    build_path_digest = hashlib.sha256()
    for index in sorted(by_index):
        build_path_digest.update(
            by_index[index]["isolation"]["build_path_sha256"].encode("ascii")
        )
    observed = utc_now()
    result: dict[str, Any] = {
        "schema_version": 1,
        "work_id": "M33-W05",
        "test_id": "M33-EXAMPLE-01",
        "status": "PASS",
        "observed_utc": observed,
        "source_revision": target_revision,
        "installed_source_revision": target_revision,
        "source_clean_before": True,
        "installed_clean_before": True,
        "host_scope": "GitHub Actions Windows clean installed tree, 8 shards",
        "fixed_inputs": reference["fixed_inputs"],
        "tools": reference["tools"],
        "isolation": {
            "source_path_sha256": reference["isolation"]["source_path_sha256"],
            "installed_path_sha256": reference["isolation"]["installed_path_sha256"],
            "build_path_sha256": build_path_digest.hexdigest(),
            "source_install_separate": True,
            "fresh_build_root": True,
            "jobs": max(by_index[index]["isolation"]["jobs"] for index in by_index),
            "shards": runner.CI_SHARD_COUNT,
            "jobs_per_shard_max": 2,
            "assignment": runner.CI_SHARD_ASSIGNMENT,
        },
        "diagnostic_retest_policy": reference["diagnostic_retest_policy"],
        "denominators": reference["denominators"],
        "profile_counts": reference["profile_counts"],
        "claim_boundary": reference["claim_boundary"],
        "metadata_sha256": reference["metadata_sha256"],
        "libraries": reference["libraries"],
        "builds": [builds[identity] for identity in sorted(builds, key=str.casefold)],
        "diagnostic_retests": sorted(
            retests, key=lambda item: item["identity"].casefold()
        ),
        "negative_profiles": [
            negatives[identifier] for identifier in sorted(negatives, key=str.casefold)
        ],
        "summary": {
            "catalog": runner.EXPECTED_EXAMPLES,
            "discovered": runner.EXPECTED_EXAMPLES,
            "compiled_pass": len(builds),
            "compiled_fail": 0,
            "initial_compile_fail": len(retests),
            "diagnostic_retest_pass": len(retests),
            "diagnostic_retest_fail": 0,
            "negative_pass": len(negatives),
            "negative_fail": 0,
        },
        "source_clean_after": True,
        "source_revision_after": target_revision,
        "installed_clean_after": True,
        "installed_revision_after": target_revision,
        "installed_tree_unchanged": True,
        "ci_shards": [
            {
                "index": index,
                "compiled": len(by_index[index]["builds"]),
                "negative_profiles": len(by_index[index]["negative_profiles"]),
                "jobs": by_index[index]["isolation"]["jobs"],
            }
            for index in sorted(by_index)
        ],
        "finished_utc": observed,
    }
    try:
        runner.validate_public_values(result)
    except runner.M33W05Failure as error:
        raise M33W05AggregateFailure(str(error)) from error
    return result


def argument_parser() -> ArgumentParser:
    """! @brief aggregate CLI parser를 만듭니다. """

    parser = ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--target-revision", required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief shard artifact를 찾아 전수 evidence를 원자적으로 기록합니다. """

    parsed = argument_parser().parse_args(arguments)
    if parsed.output.exists():
        print("M33_W05_AGGREGATE_FAIL: 기존 evidence를 덮어쓰지 않습니다", file=sys.stderr)
        return 1
    shard_paths = sorted(parsed.shards.resolve().rglob("shard-*.json"))
    try:
        result = aggregate(
            parsed.repository.resolve(), parsed.target_revision, shard_paths
        )
        runner.write_evidence(parsed.output.resolve(), result)
    except (M33W05AggregateFailure, runner.M33W05Failure, OSError, json.JSONDecodeError) as error:
        print(f"M33_W05_AGGREGATE_FAIL: {error}", file=sys.stderr)
        return 1
    print(
        f"M33_W05_AGGREGATE=PASS;SHARDS={runner.CI_SHARD_COUNT};"
        f"COMPILED={result['summary']['compiled_pass']}/{runner.EXPECTED_EXAMPLES};"
        f"NEGATIVE={result['summary']['negative_pass']}/{len(runner.NEGATIVE_PROFILE_MATRIX)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
