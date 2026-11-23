#!/usr/bin/env python3
"""! @brief M33-W06 개발 탐색과 최종 검증의 계획·증거 경계를 관리합니다.

@note 이 도구는 plan과 evidence 계약만 다룹니다. 보드를 flash하거나 HIL PASS를
      생성하지 않으며, fake transport 결과를 최종 완료 증거로 승격하지 않습니다.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
BLUETOOTH_TOOLS = REPOSITORY / "tools/bluetooth"
HIL_TOOLS = REPOSITORY / "tests/hil/nu54dk"
for module_root in (BLUETOOTH_TOOLS, HIL_TOOLS):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

import m33_execution as execution
import m33_regression as regression
import m33_regression_run as campaign_runner
import m33_w06_artifacts as artifacts


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]*\Z")
INVENTORY_KIND = "m33_w06_pipeline_inventory"
PLAN_KIND = "m33_w06_pipeline_execution_plan"
RECORD_KIND = "m33_w06_pipeline_record"
IMPACT_KIND = "m33_w06_change_impact"
BUNDLE_KIND = "m33_w06_minimal_bundle"
IMPORT_KIND = "m33_w06_minimal_bundle_import"
CACHE_KIND = "m33_w06_cache_contract"
GC_KIND = "m33_w06_gc_plan"
TIMING_KIND = "m33_w06_timing_summary"
SCHEMA_VERSION = 1
MODES = ("development_smoke", "final")
EVIDENCE_CLASSES = {"DEVELOPMENT", "FINAL"}
RECORD_STATUSES = {"PASS", "FAIL", "NOT_RUN", "SAFETY_HOLD", "CANCELLED"}
FINAL_DENOMINATORS = {
    "campaigns": 48,
    "build_slots": 141,
    "runtime_slots": 9,
    "stage_slots": 150,
    "families": 33,
    "resources": 8,
    "automatic_peers": 8,
    "groups": 49,
    "soak_seconds": 1800,
    "sdk_risks": 7,
    "qualification_components": 3,
}
TIMING_PHASES = (
    "queue", "setup", "build", "download", "program", "test", "cleanup",
)
HIGH_RISK_GROUPS = (
    ("families", "gatt_cache"),
    ("families", "signed_write"),
    ("families", "bond_identity"),
    ("families", "new_profiles"),
    ("resources", "security_dfu"),
    ("resources", "profiles_companion"),
    ("automatic_peers", "security"),
    ("automatic_peers", "profiles"),
)
NEGATIVE_TOKENS = (
    "negative", "reject", "wrong", "stale", "mismatch", "cancel",
    "rollback", "peer_loss", "access_denied", "malformed", "timeout",
)
PIPELINE_CONSUMERS = (
    "tools/ci/m33_w06_artifacts.py",
    "tests/hil/nu54dk/m33_regression_run.py",
    "tools/bluetooth/m33_regression.py",
    "tools/bluetooth/m33_execution.py",
)


class PipelineFailure(ValueError):
    """! @brief 계획 또는 증거 계약 위반을 명시적으로 나타냅니다. """


def require(condition: bool, message: str) -> None:
    """! @brief 불완전하거나 모호한 입력은 성공으로 복구하지 않습니다. """

    if not condition:
        raise PipelineFailure(message)


def canonical_sha256(value: object) -> str:
    """! @brief 위치와 무관한 canonical JSON SHA-256을 반환합니다. """

    return execution.canonical(value)


def read_json(path: Path) -> dict:
    """! @brief 중복 key·부분 JSON·link를 허용하지 않고 JSON을 읽습니다. """

    return execution.read_json(path)


def _source_identity(plan: dict) -> dict:
    """! @brief artifact plan의 clean exact source identity를 축약 없이 보존합니다. """

    source = plan.get("source")
    require(isinstance(source, dict), "artifact plan source identity가 없습니다")
    revision = source.get("source_revision")
    require(isinstance(revision, str) and REVISION.fullmatch(revision) is not None,
            "artifact plan Core revision이 잘못됐습니다")
    require(source.get("source_clean") is True,
            "pipeline inventory는 clean source plan만 허용합니다")
    return source


def _smoke_cycles(full_cycles: int, verification: str,
                  supports_reduction: bool) -> int:
    """! @brief 짧은 탐색의 유한 반복 수를 최종 분모와 별도로 계산합니다. """

    require(type(full_cycles) is int and full_cycles > 0,
            "campaign 반복 수가 잘못됐습니다")
    if not supports_reduction:
        return full_cycles
    if verification == "build_semantic":
        return 1
    if full_cycles <= 4:
        return 1
    if full_cycles <= 24:
        return 2
    return 3


def _smoke_semantics(semantics: Sequence[str]) -> dict:
    """! @brief core·negative·cleanup 경계를 숨김없이 분리합니다. """

    require(bool(semantics) and all(isinstance(value, str) and value for value in semantics),
            "campaign semantic 계약이 비어 있습니다")
    negative = next(
        (value for value in semantics
         if any(token in value for token in NEGATIVE_TOKENS)),
        None,
    )
    cleanup = next((value for value in semantics if "cleanup" in value), None)
    return {
        "core": semantics[0],
        "feature_negative": negative,
        "adapter_negative": "wrong_nonce_or_role_rejected",
        "cleanup": cleanup,
        "all_final_semantics": list(semantics),
    }


def _artifact_rows(plan: dict, campaign_id: str) -> tuple[list[dict], list[dict]]:
    """! @brief campaign이 소비하는 build/runtime slot을 원래 순서로 반환합니다. """

    build = artifacts.build_artifacts(plan)
    runtime = artifacts.runtime_artifacts(plan)

    def rows(values: dict) -> list[dict]:
        return [
            {
                "name": name,
                "kind": artifact["kind"],
                "binding": artifact["binding"],
                "required_for_dispatch": artifact["required_for_dispatch"],
            }
            for (owner, name), artifact in values.items()
            if owner == campaign_id
        ]

    return rows(build), rows(runtime)


def _campaign_inventory(plan: dict, campaign_id: str) -> dict:
    """! @brief runner·oracle·artifact·비용을 하나의 검증 가능한 행으로 결합합니다. """

    definition = regression.CAMPAIGNS[campaign_id]
    plan_row = next(
        (row for row in plan["campaigns"] if row["id"] == campaign_id),
        None,
    )
    require(plan_row is not None, f"artifact plan에 campaign이 없습니다: {campaign_id}")
    runner_path = REPOSITORY / definition["runner"]
    require(runner_path.is_file(), f"campaign runner가 없습니다: {campaign_id}")
    build, runtime = _artifact_rows(plan, campaign_id)
    full_cycles = definition["minimum_cycles"]
    options = artifacts.runner_options(
        runner_path,
        artifacts.SUBCOMMANDS.get(campaign_id),
    )
    cycle_options = sorted(options & {"--cycles", "--procedures"})
    fixed_denominator = campaign_id in {
        "m33_profiles_standard", "m33_profiles_native", "m33_diagnostics_dtm",
    }
    supports_reduction = bool(cycle_options) and not fixed_denominator
    smoke_cycles = _smoke_cycles(
        full_cycles,
        definition["verification"],
        supports_reduction,
    )
    return {
        "id": campaign_id,
        "verification": definition["verification"],
        "adapter": campaign_runner.NATIVE_ADAPTER_REGISTRY[campaign_id],
        "preparation": campaign_runner.CAMPAIGN_PREPARATION_MODE[campaign_id],
        "runner": {
            "path": definition["runner"],
            "sha256": execution.digest(runner_path),
        },
        "oracle": {
            "path": "tests/hil/nu54dk/m33_regression_run.py",
            "sha256": execution.digest(
                REPOSITORY / "tests/hil/nu54dk/m33_regression_run.py"
            ),
        },
        "applications": list(definition["applications"]),
        "roles": list(definition["roles"]),
        "artifacts": {"build": build, "runtime": runtime},
        "cost": {
            "full_cycles": full_cycles,
            "smoke_cycles": smoke_cycles,
            "full_timeout_seconds": campaign_runner.campaign_timeout_seconds({
                "id": campaign_id,
                "minimum_cycles": full_cycles,
            }),
            "physical_boards": len(definition["roles"]),
            "smoke_cycle_options": cycle_options,
            "smoke_strategy": (
                "runner_cycle_option" if supports_reduction
                else "existing_full_denominator"
            ),
        },
        "smoke": {
            "mode": "development_smoke",
            "completion_eligible": False,
            "semantics": _smoke_semantics(definition["semantics"]),
            "omitted": [
                "final_repetition_denominator",
                "long_duration_stability",
                "independent_1800_second_soak",
                "external_product_interoperability",
                "final_closure_claim",
            ],
            "requires_stop": definition["verification"] == "physical_hil",
        },
    }


def create_inventory(plan: dict, repository: Path = REPOSITORY) -> dict:
    """! @brief 49 group·48 campaign·141/9/150 slot의 단일 R1 지도를 생성합니다. """

    require(repository.resolve() == REPOSITORY.resolve(),
            "현재 저장소 밖의 registry는 inventory로 허용하지 않습니다")
    artifacts.validate_plan(plan, repository)
    source = _source_identity(plan)
    campaign_ids = list(regression.CAMPAIGNS)
    require([row["id"] for row in plan["campaigns"]] == campaign_ids,
            "artifact plan campaign 순서가 registry와 다릅니다")
    campaigns = [_campaign_inventory(plan, campaign_id)
                 for campaign_id in campaign_ids]
    campaign_by_id = {row["id"]: row for row in campaigns}
    groups = []
    for field, registry in regression.CAMPAIGN_REGISTRIES.items():
        for identifier, routed_campaigns in registry.items():
            require(all(campaign_id in campaign_by_id
                        for campaign_id in routed_campaigns),
                    f"group campaign route가 잘못됐습니다: {field}:{identifier}")
            groups.append({
                "field": field,
                "id": identifier,
                "campaigns": list(routed_campaigns),
                "consumers": sorted({
                    campaign_by_id[campaign_id]["runner"]["path"]
                    for campaign_id in routed_campaigns
                } | set(PIPELINE_CONSUMERS)),
            })
    build_count = len(artifacts.build_artifacts(plan))
    runtime_count = len(artifacts.runtime_artifacts(plan))
    counts = {
        "campaigns": len(campaigns),
        "build_slots": build_count,
        "runtime_slots": runtime_count,
        "stage_slots": build_count + runtime_count,
        "families": len(regression.FAMILY_CAMPAIGNS),
        "resources": len(regression.RESOURCE_CAMPAIGNS),
        "automatic_peers": len(regression.AUTOMATIC_PEER_CAMPAIGNS),
        "groups": len(groups),
    }
    for name, expected in FINAL_DENOMINATORS.items():
        if name in counts:
            require(counts[name] == expected,
                    f"R1 denominator가 다릅니다: {name}={counts[name]}")
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": INVENTORY_KIND,
        "source": source,
        "artifact_plan_sha256": plan["contract_sha256"],
        "counts": counts,
        "final_denominators": FINAL_DENOMINATORS,
        "campaigns": campaigns,
        "groups": groups,
        "record_schema": {
            "kind": RECORD_KIND,
            "required_identity": [
                "mode", "evidence_class", "source", "input_fingerprint",
                "runner_fingerprint", "oracle_fingerprint", "schema_fingerprint",
                "field", "group", "campaign", "attempt",
            ],
            "required_lifecycle": [
                "parent", "prerequisites", "started_at", "ended_at", "status",
                "error_class", "raw_outputs", "outputs", "device", "cleanup",
            ],
        },
    }
    document["inventory_sha256"] = canonical_sha256(document)
    validate_inventory(document)
    return document


def validate_inventory(document: dict) -> None:
    """! @brief inventory의 schema·분모·중복·hash를 fail-closed로 검사합니다. """

    require(document.get("schema_version") == SCHEMA_VERSION and
            document.get("kind") == INVENTORY_KIND,
            "pipeline inventory schema가 다릅니다")
    source = document.get("source")
    require(isinstance(source, dict) and
            REVISION.fullmatch(str(source.get("source_revision", ""))) is not None and
            source.get("source_clean") is True,
            "pipeline inventory source가 잘못됐습니다")
    require(document.get("counts") == {
        key: FINAL_DENOMINATORS[key]
        for key in ("campaigns", "build_slots", "runtime_slots", "stage_slots",
                    "families", "resources", "automatic_peers", "groups")
    }, "pipeline inventory 분모가 다릅니다")
    campaigns = document.get("campaigns")
    groups = document.get("groups")
    require(isinstance(campaigns, list) and isinstance(groups, list),
            "pipeline inventory 행이 없습니다")
    campaign_ids = [row.get("id") for row in campaigns if isinstance(row, dict)]
    require(campaign_ids == list(regression.CAMPAIGNS) and
            len(set(campaign_ids)) == FINAL_DENOMINATORS["campaigns"],
            "pipeline campaign 누락·중복·순서 오류")
    expected_groups = [
        (field, identifier)
        for field, registry in regression.CAMPAIGN_REGISTRIES.items()
        for identifier in registry
    ]
    actual_groups = [
        (row.get("field"), row.get("id"))
        for row in groups if isinstance(row, dict)
    ]
    require(actual_groups == expected_groups and len(set(actual_groups)) == len(actual_groups),
            "pipeline group 누락·중복·순서 오류")
    require(all(
        row.get("adapter") == campaign_runner.NATIVE_ADAPTER_REGISTRY[row["id"]]
        and row.get("preparation") == campaign_runner.CAMPAIGN_PREPARATION_MODE[row["id"]]
        and row.get("smoke", {}).get("completion_eligible") is False
        for row in campaigns
    ), "pipeline adapter 또는 smoke 경계가 다릅니다")
    checksum = document.get("inventory_sha256")
    clone = dict(document)
    clone.pop("inventory_sha256", None)
    require(isinstance(checksum, str) and SHA256.fullmatch(checksum) is not None and
            canonical_sha256(clone) == checksum,
            "pipeline inventory hash가 다릅니다")


def _group_keys(inventory: dict) -> list[tuple[str, str]]:
    """! @brief inventory의 canonical group key 순서를 반환합니다. """

    return [(row["field"], row["id"]) for row in inventory["groups"]]


def _ordered_group_keys(keys: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """! @brief NVM·reboot·구성 전환 고위험 경계를 먼저 배치합니다. """

    priority = {key: index for index, key in enumerate(HIGH_RISK_GROUPS)}
    original = {key: index for index, key in enumerate(keys)}
    return sorted(keys, key=lambda key: (
        0 if key in priority else 1,
        priority.get(key, original[key]),
        original[key],
    ))


def create_execution_plan(
    inventory: dict,
    mode: str,
    selected: Sequence[tuple[str, str]] | None = None,
    reason: str = "all_registered_groups",
) -> dict:
    """! @brief development smoke와 final 분모를 섞지 않는 순수 실행 계획을 만듭니다. """

    validate_inventory(inventory)
    require(mode in MODES, "알 수 없는 pipeline mode입니다")
    all_keys = _group_keys(inventory)
    requested = list(selected) if selected is not None else list(all_keys)
    require(len(requested) == len(set(requested)), "선택 group이 중복됐습니다")
    require(all(key in all_keys for key in requested), "선택 group이 registry에 없습니다")
    if mode == "final":
        require(requested == all_keys,
                "final mode는 49개 canonical group 전체를 요구합니다")
    rows_by_key = {(row["field"], row["id"]): row for row in inventory["groups"]}
    campaigns = {row["id"]: row for row in inventory["campaigns"]}
    tasks = []
    for ordinal, key in enumerate(_ordered_group_keys(requested), start=1):
        group = rows_by_key[key]
        campaign_rows = []
        for campaign_id in group["campaigns"]:
            campaign = campaigns[campaign_id]
            campaign_rows.append({
                "id": campaign_id,
                "cycles": (
                    campaign["cost"]["smoke_cycles"]
                    if mode == "development_smoke"
                    else campaign["cost"]["full_cycles"]
                ),
                "runner_sha256": campaign["runner"]["sha256"],
                "oracle_sha256": campaign["oracle"]["sha256"],
                "requires_stop": campaign["smoke"]["requires_stop"],
                "omitted": (campaign["smoke"]["omitted"]
                            if mode == "development_smoke" else []),
            })
        tasks.append({
            "ordinal": ordinal,
            "field": key[0],
            "group": key[1],
            "selection_reason": reason,
            "campaigns": campaign_rows,
        })
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "mode": mode,
        "evidence_class": "DEVELOPMENT" if mode == "development_smoke" else "FINAL",
        "completion_eligible": mode == "final",
        "source": inventory["source"],
        "inventory_sha256": inventory["inventory_sha256"],
        "artifact_plan_sha256": inventory["artifact_plan_sha256"],
        "selected_group_count": len(tasks),
        "final_denominators": FINAL_DENOMINATORS,
        "tasks": tasks,
    }
    document["input_fingerprint"] = canonical_sha256(document)
    validate_execution_plan(document, inventory)
    return document


def validate_execution_plan(document: dict, inventory: dict) -> None:
    """! @brief mode·source·선택·분모가 바뀐 계획의 재개를 거부합니다. """

    validate_inventory(inventory)
    require(document.get("schema_version") == SCHEMA_VERSION and
            document.get("kind") == PLAN_KIND and document.get("mode") in MODES,
            "pipeline execution plan schema가 다릅니다")
    require(document.get("source") == inventory["source"] and
            document.get("inventory_sha256") == inventory["inventory_sha256"] and
            document.get("artifact_plan_sha256") == inventory["artifact_plan_sha256"],
            "pipeline plan source/input이 다릅니다")
    mode = document["mode"]
    require(document.get("evidence_class") == (
        "DEVELOPMENT" if mode == "development_smoke" else "FINAL"
    ) and document.get("completion_eligible") is (mode == "final"),
            "pipeline plan mode 승격 경계가 다릅니다")
    tasks = document.get("tasks")
    require(isinstance(tasks, list) and
            document.get("selected_group_count") == len(tasks) and
            [row.get("ordinal") for row in tasks] == list(range(1, len(tasks) + 1)),
            "pipeline task 순서·분모가 다릅니다")
    keys = [(row.get("field"), row.get("group")) for row in tasks]
    require(len(keys) == len(set(keys)) and all(key in _group_keys(inventory) for key in keys),
            "pipeline task group이 누락·중복됐습니다")
    if mode == "final":
        require(keys == _ordered_group_keys(_group_keys(inventory)) and len(keys) == 49,
                "final pipeline group 분모가 다릅니다")
        require(all(not campaign.get("omitted")
                    for task in tasks for campaign in task.get("campaigns", [])),
                "final pipeline에 생략 범위가 있습니다")
    else:
        require(all(campaign.get("omitted")
                    for task in tasks for campaign in task.get("campaigns", [])),
                "development smoke 생략 범위가 명시되지 않았습니다")
    checksum = document.get("input_fingerprint")
    clone = dict(document)
    clone.pop("input_fingerprint", None)
    require(isinstance(checksum, str) and SHA256.fullmatch(checksum) is not None and
            canonical_sha256(clone) == checksum,
            "pipeline plan fingerprint가 다릅니다")


def _timestamp(value: object) -> datetime:
    """! @brief timezone이 있는 ISO-8601 시각만 허용합니다. """

    require(isinstance(value, str) and value, "pipeline record 시각이 없습니다")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PipelineFailure("pipeline record 시각이 잘못됐습니다") from error
    require(parsed.tzinfo is not None, "pipeline record 시각에 timezone이 없습니다")
    return parsed


def validate_record(
    document: dict,
    record_root: Path,
    plan: dict | None = None,
    completion: bool = False,
) -> None:
    """! @brief fake·wrong source/mode·손상·cleanup 누락의 최종 승격을 거부합니다. """

    required = {
        "schema_version", "kind", "mode", "evidence_class", "transport",
        "source", "input_fingerprint", "runner_fingerprint",
        "oracle_fingerprint", "schema_fingerprint", "field", "group",
        "campaign", "attempt", "parent", "prerequisites", "started_at",
        "ended_at", "status", "error_class", "raw_outputs", "outputs",
        "device", "cleanup",
    }
    require(isinstance(document, dict) and set(document) == required and
            document.get("schema_version") == SCHEMA_VERSION and
            document.get("kind") == RECORD_KIND,
            "pipeline record schema가 다릅니다")
    mode = document["mode"]
    evidence_class = document["evidence_class"]
    require(mode in MODES and evidence_class in EVIDENCE_CLASSES and
            evidence_class == ("DEVELOPMENT" if mode == "development_smoke" else "FINAL"),
            "pipeline record mode/evidence class가 다릅니다")
    source = document["source"]
    require(isinstance(source, dict) and
            REVISION.fullmatch(str(source.get("source_revision", ""))) is not None and
            isinstance(source.get("source_clean"), bool),
            "pipeline record source가 잘못됐습니다")
    require(all(SHA256.fullmatch(str(document[field])) is not None
                for field in ("input_fingerprint", "runner_fingerprint",
                              "oracle_fingerprint", "schema_fingerprint")),
            "pipeline record fingerprint가 잘못됐습니다")
    require(document["field"] in regression.CAMPAIGN_REGISTRIES and
            document["group"] in regression.CAMPAIGN_REGISTRIES[document["field"]] and
            document["campaign"] in
            regression.CAMPAIGN_REGISTRIES[document["field"]][document["group"]],
            "pipeline record group/campaign route가 잘못됐습니다")
    require(type(document["attempt"]) is int and document["attempt"] > 0,
            "pipeline record attempt가 잘못됐습니다")
    require(document["parent"] is None or isinstance(document["parent"], dict),
            "pipeline record parent가 잘못됐습니다")
    require(isinstance(document["prerequisites"], list),
            "pipeline record prerequisite가 잘못됐습니다")
    started = _timestamp(document["started_at"])
    ended = _timestamp(document["ended_at"])
    require(ended >= started, "pipeline record 종료 시각이 시작 전입니다")
    status = document["status"]
    require(status in RECORD_STATUSES,
            "pipeline record status가 잘못됐습니다")
    require((status == "PASS" and document["error_class"] is None) or
            (status != "PASS" and isinstance(document["error_class"], str)),
            "pipeline record error class가 status와 다릅니다")
    require(document["transport"] in {"physical", "fake"},
            "pipeline record transport가 잘못됐습니다")
    if document["transport"] == "fake":
        require(mode == "development_smoke" and evidence_class == "DEVELOPMENT",
                "fake transport는 개발 증거로만 허용합니다")
    for field in ("raw_outputs", "outputs"):
        execution.validate_references(record_root, document[field])
    require(isinstance(document["device"], dict) and
            isinstance(document["cleanup"], dict),
            "pipeline record 장치/cleanup 결과가 없습니다")
    if plan is not None:
        require(document["mode"] == plan.get("mode") and
                document["source"] == plan.get("source") and
                document["input_fingerprint"] == plan.get("input_fingerprint"),
                "pipeline record source/mode/input이 계획과 다릅니다")
        require(any(
            task.get("field") == document["field"] and
            task.get("group") == document["group"] and
            any(row.get("id") == document["campaign"]
                for row in task.get("campaigns", []))
            for task in plan.get("tasks", [])
        ), "pipeline record가 계획된 task가 아닙니다")
    if completion:
        require(mode == "final" and evidence_class == "FINAL" and
                document["transport"] == "physical" and
                source.get("source_clean") is True and status == "PASS" and
                document["cleanup"].get("status") == "PASS" and
                document["device"].get("end_state") == "SAFE_STOPPED",
                "pipeline record는 최종 완료 증거가 아닙니다")


def validate_record_set(records: Sequence[dict], record_root: Path, plan: dict) -> None:
    """! @brief 중복 attempt와 누락 task를 최종 record 집합에서 거부합니다. """

    keys = []
    covered = set()
    for document in records:
        validate_record(document, record_root, plan, completion=plan["mode"] == "final")
        key = (
            document["field"], document["group"], document["campaign"],
            document["attempt"],
        )
        require(key not in keys, "pipeline record가 중복됐습니다")
        keys.append(key)
        if document["status"] == "PASS":
            covered.add((document["field"], document["group"], document["campaign"]))
    expected = {
        (task["field"], task["group"], campaign["id"])
        for task in plan["tasks"] for campaign in task["campaigns"]
    }
    require(covered == expected, "pipeline record PASS 분모가 누락되거나 과다합니다")


def classify_changes(inventory: dict, paths: Sequence[str]) -> dict:
    """! @brief 변경 경로를 group 선택과 final cache 무효화로 보수적으로 변환합니다. """

    validate_inventory(inventory)
    normalized = []
    for value in paths:
        require(isinstance(value, str) and value and "\\" not in value and
                not Path(value).is_absolute() and ".." not in Path(value).parts,
                "change path가 저장소 상대 POSIX 경로가 아닙니다")
        normalized.append(value)
    require(len(normalized) == len(set(normalized)), "change path가 중복됐습니다")
    all_keys = _group_keys(inventory)
    consumers = {}
    for group in inventory["groups"]:
        key = (group["field"], group["id"])
        for consumer in group["consumers"]:
            consumers.setdefault(consumer, set()).add(key)
        for campaign_id in group["campaigns"]:
            campaign = next(row for row in inventory["campaigns"]
                            if row["id"] == campaign_id)
            for application in campaign["applications"]:
                consumers.setdefault(application, set()).add(key)
    selected = set()
    classification = "targeted"
    reasons = []
    for path in normalized:
        if path == "AGENTS.md" or path.endswith(".md") or path.startswith("00_Docs/"):
            reasons.append({"path": path, "reason": "documentation_only"})
            continue
        matched = set()
        for consumer, keys in consumers.items():
            if path == consumer or path.startswith(consumer.rstrip("/") + "/"):
                matched.update(keys)
        if matched:
            selected.update(matched)
            reasons.append({"path": path, "reason": "registered_consumer",
                            "groups": [f"{field}:{identifier}"
                                       for field, identifier in sorted(matched)]})
            continue
        classification = "full"
        selected = set(all_keys)
        reasons.append({"path": path, "reason": "unknown_or_global_change"})
    if not normalized:
        classification = "full"
        selected = set(all_keys)
        reasons.append({"path": None, "reason": "unproven_change_scope"})
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": IMPACT_KIND,
        "classification": classification,
        "changed_paths": normalized,
        "selected_groups": [
            {"field": field, "id": identifier}
            for field, identifier in all_keys if (field, identifier) in selected
        ],
        "final_artifact_reuse": False if normalized else False,
        "reasons": reasons,
    }
    document["impact_sha256"] = canonical_sha256(document)
    return document


def _bundle_relative(path: Path, root: Path) -> str:
    """! @brief bundle 내부의 탈출 없는 POSIX 상대경로를 반환합니다. """

    relative = path.relative_to(root).as_posix()
    require(relative and not Path(relative).is_absolute() and
            all(part not in {"", ".", ".."} for part in relative.split("/")),
            "minimal bundle 상대경로가 잘못됐습니다")
    return relative


def create_minimal_bundle(
    artifact_plan: dict,
    artifact_root: Path,
    campaign_ids: Sequence[str],
    output: Path,
) -> dict:
    """! @brief 선택한 native campaign의 image·provenance byte만 이동 가능한 bundle로 만듭니다.

    @note R3의 한 수직 경로용 계약입니다. runtime input·Arduino 외부 config·전체 150 slot을
          포함하지 않으므로 final artifact root나 W06 완료 증거로 사용할 수 없습니다.
    """

    artifacts.validate_plan(artifact_plan)
    selected = list(campaign_ids)
    require(selected and len(selected) == len(set(selected)) and
            all(campaign_id in regression.CAMPAIGNS for campaign_id in selected),
            "minimal bundle campaign 선택이 비었거나 중복·미등록 상태입니다")
    require(not output.exists(), "minimal bundle output overwrite를 거부합니다")
    artifact_root = artifact_root.resolve()
    require(artifact_root.is_dir(), "minimal bundle artifact root가 없습니다")
    output.mkdir(parents=True)
    payload = output / "payload"
    payload.mkdir()
    plan_rows = artifacts.plan_artifacts(artifact_plan)
    entries = []
    try:
        for campaign_id in selected:
            keys = [key for key in plan_rows if key[0] == campaign_id]
            require(keys, f"minimal bundle campaign artifact가 없습니다: {campaign_id}")
            for key in keys:
                contract = plan_rows[key]
                require(contract["kind"] == "target_image" and
                        key in artifacts.build_artifacts(artifact_plan),
                        f"R3 minimal bundle은 native target image만 허용합니다: {key}")
                link = artifact_root / campaign_id / key[1]
                require(link.is_symlink(), f"staged artifact symlink가 없습니다: {key}")
                source = link.resolve(strict=True)
                require(source.is_file(), f"minimal bundle source image가 파일이 아닙니다: {key}")
                record = artifacts.adjacent_build_record(source).resolve(strict=True)
                require(record.name == "nucode_arduino_core_build.yml",
                        f"R3 portable bundle은 native build record만 허용합니다: {key}")
                source_root = record.parent
                require(source.is_relative_to(source_root),
                        f"native image가 build record root 밖에 있습니다: {key}")
                object_root = payload / campaign_id / key[1]
                image_target = object_root / source.relative_to(source_root)
                record_target = object_root / record.name
                image_target.parent.mkdir(parents=True)
                shutil.copy2(source, image_target)
                shutil.copy2(record, record_target)
                entries.append({
                    "campaign_id": campaign_id,
                    "name": key[1],
                    "kind": contract["kind"],
                    "artifact": {
                        "path": _bundle_relative(image_target, output),
                        "bytes": image_target.stat().st_size,
                        "sha256": execution.digest(image_target),
                    },
                    "build_record": {
                        "path": _bundle_relative(record_target, output),
                        "bytes": record_target.stat().st_size,
                        "sha256": execution.digest(record_target),
                    },
                })
        document = {
            "schema_version": SCHEMA_VERSION,
            "kind": BUNDLE_KIND,
            "evidence_class": "DEVELOPMENT",
            "completion_eligible": False,
            "source": artifact_plan["source"],
            "artifact_plan_sha256": artifact_plan["contract_sha256"],
            "campaigns": selected,
            "entries": entries,
        }
        document["bundle_sha256"] = canonical_sha256(document)
        execution.write_new_json(output / "m33-w06-minimal-bundle.json", document)
        validate_minimal_bundle(output)
        return document
    except BaseException:
        # @note 실패 root는 진단을 위해 보존하며 성공 manifest가 없으면 import할 수 없습니다.
        raise


def validate_minimal_bundle(root: Path) -> dict:
    """! @brief 이동한 bundle의 경로·byte·중복·개발 전용 경계를 재검증합니다. """

    root = root.resolve()
    manifest = read_json(root / "m33-w06-minimal-bundle.json")
    require(manifest.get("schema_version") == SCHEMA_VERSION and
            manifest.get("kind") == BUNDLE_KIND and
            manifest.get("evidence_class") == "DEVELOPMENT" and
            manifest.get("completion_eligible") is False,
            "minimal bundle schema 또는 승격 경계가 다릅니다")
    checksum = manifest.get("bundle_sha256")
    clone = dict(manifest)
    clone.pop("bundle_sha256", None)
    require(isinstance(checksum, str) and SHA256.fullmatch(checksum) is not None and
            canonical_sha256(clone) == checksum,
            "minimal bundle manifest hash가 다릅니다")
    entries = manifest.get("entries")
    require(isinstance(entries, list) and entries,
            "minimal bundle entry가 없습니다")
    keys = []
    referenced = {root / "m33-w06-minimal-bundle.json"}
    for entry in entries:
        require(isinstance(entry, dict) and
                set(entry) == {"campaign_id", "name", "kind", "artifact", "build_record"},
                "minimal bundle entry schema가 다릅니다")
        key = (entry["campaign_id"], entry["name"])
        require(key not in keys and entry["campaign_id"] in manifest["campaigns"] and
                entry["kind"] == "target_image",
                "minimal bundle entry가 중복·미등록 상태입니다")
        keys.append(key)
        for field in ("artifact", "build_record"):
            reference = entry[field]
            require(isinstance(reference, dict) and
                    set(reference) == {"path", "bytes", "sha256"} and
                    type(reference["bytes"]) is int and reference["bytes"] > 0 and
                    SHA256.fullmatch(str(reference["sha256"])) is not None,
                    "minimal bundle file reference가 잘못됐습니다")
            path = root / reference["path"]
            require(path.is_file() and not path.is_symlink() and
                    path.resolve().is_relative_to(root) and
                    path.stat().st_size == reference["bytes"] and
                    execution.digest(path) == reference["sha256"],
                    "minimal bundle file byte/hash가 다릅니다")
            referenced.add(path)
    actual = {path for path in root.rglob("*") if path.is_file()}
    require(actual == referenced,
            "minimal bundle에 누락 또는 비계약 파일이 있습니다")
    return manifest


def import_minimal_bundle(bundle: Path, output: Path) -> dict:
    """! @brief 검증한 bundle을 다른 root에 복사하고 campaign artifact symlink를 재생성합니다. """

    bundle = bundle.resolve()
    manifest = validate_minimal_bundle(bundle)
    require(not output.exists(), "minimal bundle import output overwrite를 거부합니다")
    temporary = output.with_name(output.name + f".staging-{os.getpid()}")
    require(not temporary.exists(), "minimal bundle import temporary root가 이미 있습니다")
    temporary.mkdir(parents=True)
    try:
        shutil.copytree(bundle / "payload", temporary / "payload")
        artifact_root = temporary / "artifacts"
        artifact_root.mkdir()
        aliases = []
        for entry in manifest["entries"]:
            campaign = artifact_root / entry["campaign_id"]
            campaign.mkdir(exist_ok=True)
            target = temporary / entry["artifact"]["path"]
            link = campaign / entry["name"]
            relative_target = os.path.relpath(target, start=link.parent)
            os.symlink(relative_target, str(link), target_is_directory=False)
            aliases.append({
                "campaign_id": entry["campaign_id"],
                "name": entry["name"],
                "target": target.relative_to(temporary).as_posix(),
                "sha256": entry["artifact"]["sha256"],
            })
        document = {
            "schema_version": SCHEMA_VERSION,
            "kind": IMPORT_KIND,
            "evidence_class": "DEVELOPMENT",
            "completion_eligible": False,
            "source": manifest["source"],
            "bundle_sha256": manifest["bundle_sha256"],
            "aliases": aliases,
        }
        document["import_sha256"] = canonical_sha256(document)
        execution.write_new_json(temporary / "m33-w06-minimal-import.json", document)
        temporary.replace(output)
        validate_minimal_import(output)
        return document
    except BaseException:
        # @note 부분 import는 최종 이름으로 공개되지 않으며 staging root를 진단용으로 보존합니다.
        raise


def validate_minimal_import(root: Path) -> dict:
    """! @brief import alias가 새 root의 검증된 payload만 가리키는지 확인합니다. """

    root = root.resolve()
    document = read_json(root / "m33-w06-minimal-import.json")
    require(document.get("schema_version") == SCHEMA_VERSION and
            document.get("kind") == IMPORT_KIND and
            document.get("evidence_class") == "DEVELOPMENT" and
            document.get("completion_eligible") is False,
            "minimal bundle import schema가 다릅니다")
    checksum = document.get("import_sha256")
    clone = dict(document)
    clone.pop("import_sha256", None)
    require(isinstance(checksum, str) and canonical_sha256(clone) == checksum,
            "minimal bundle import hash가 다릅니다")
    for alias in document.get("aliases", []):
        require(isinstance(alias, dict) and
                set(alias) == {"campaign_id", "name", "target", "sha256"},
                "minimal bundle alias schema가 다릅니다")
        link = root / "artifacts" / alias["campaign_id"] / alias["name"]
        target = root / alias["target"]
        require(link.is_symlink() and link.resolve() == target.resolve() and
                target.is_file() and target.resolve().is_relative_to(root) and
                execution.digest(target) == alias["sha256"],
                "minimal bundle alias target/hash가 다릅니다")
        record = artifacts.adjacent_build_record(target)
        require(record.is_file() and record.resolve().is_relative_to(root),
                "minimal bundle native provenance가 import root에 없습니다")
    return document


def create_cache_contract(plan: dict, dependencies: dict[str, str]) -> dict:
    """! @brief source·mode·schema·runner 입력을 묶은 cache 무효화 계약을 만듭니다. """

    require(plan.get("kind") == PLAN_KIND and
            SHA256.fullmatch(str(plan.get("input_fingerprint", ""))) is not None,
            "cache plan fingerprint가 잘못됐습니다")
    require(isinstance(dependencies, dict) and dependencies and
            all(isinstance(key, str) and key and
                isinstance(value, str) and SHA256.fullmatch(value) is not None
                for key, value in dependencies.items()),
            "cache dependency hash가 잘못됐습니다")
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": CACHE_KIND,
        "mode": plan["mode"],
        "source": plan["source"],
        "plan_fingerprint": plan["input_fingerprint"],
        "dependencies": dict(sorted(dependencies.items())),
    }
    document["cache_key"] = canonical_sha256(document)
    return document


def validate_cache_contract(
    document: dict,
    plan: dict,
    dependencies: dict[str, str],
) -> None:
    """! @brief dependency/source/mode drift가 있는 cache hit를 거부합니다. """

    expected = create_cache_contract(plan, dependencies)
    require(document == expected, "cache contract가 현재 입력과 다릅니다")


def create_gc_plan(rows: Sequence[dict], requested: Sequence[str] | None = None) -> dict:
    """! @brief active·마지막 원본·실패 증거를 제외한 재생성 cache만 정리 후보로 냅니다. """

    normalized = []
    seen = set()
    required = {
        "path", "category", "referenced", "active", "last_original",
        "failure_evidence", "reproducible",
    }
    for row in rows:
        require(isinstance(row, dict) and set(row) == required,
                "GC inventory schema가 다릅니다")
        path = row["path"]
        require(isinstance(path, str) and path and path not in seen and
                not Path(path).is_absolute() and ".." not in Path(path).parts and
                "\\" not in path,
                "GC inventory path가 중복·절대·탈출 상태입니다")
        require(row["category"] in {"artifact", "run", "cache", "tmp", "archive"} and
                all(isinstance(row[field], bool) for field in required - {"path", "category"}),
                "GC inventory 상태가 잘못됐습니다")
        seen.add(path)
        normalized.append(dict(row))
    request = list(requested) if requested is not None else [
        row["path"] for row in normalized
        if row["category"] in {"cache", "tmp"} and row["reproducible"]
    ]
    require(len(request) == len(set(request)) and all(path in seen for path in request),
            "GC 요청 path가 중복되거나 inventory에 없습니다")
    by_path = {row["path"]: row for row in normalized}
    protected = []
    candidates = []
    for path in request:
        row = by_path[path]
        reasons = [
            field for field in (
                "referenced", "active", "last_original", "failure_evidence"
            ) if row[field]
        ]
        if not row["reproducible"]:
            reasons.append("not_reproducible")
        if row["category"] not in {"cache", "tmp"}:
            reasons.append("non_cache_material")
        if reasons:
            protected.append({"path": path, "reasons": reasons})
        else:
            candidates.append(path)
    require(not protected,
            "GC 요청에 active·원본·실패·비재생성 자료가 포함됐습니다")
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": GC_KIND,
        "dry_run": True,
        "candidates": candidates,
        "receipt_required": True,
    }
    document["gc_sha256"] = canonical_sha256(document)
    return document


def summarize_timings(rows: Sequence[dict]) -> dict:
    """! @brief queue부터 cleanup까지 실측 시간을 phase별로 분리합니다. """

    summary = {
        phase: {"samples": 0, "total_ms": 0, "minimum_ms": None, "maximum_ms": None}
        for phase in TIMING_PHASES
    }
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"phase", "duration_ms"} and
                row["phase"] in TIMING_PHASES and
                type(row["duration_ms"]) is int and row["duration_ms"] >= 0,
                "timing measurement schema가 잘못됐습니다")
        target = summary[row["phase"]]
        duration = row["duration_ms"]
        target["samples"] += 1
        target["total_ms"] += duration
        target["minimum_ms"] = duration if target["minimum_ms"] is None else min(
            target["minimum_ms"], duration
        )
        target["maximum_ms"] = duration if target["maximum_ms"] is None else max(
            target["maximum_ms"], duration
        )
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": TIMING_KIND,
        "phases": summary,
        "total_ms": sum(row["duration_ms"] for row in rows),
        "estimated_completion": None,
        "estimate_policy": "동일 mode·조건 표본이 없으면 완료 시각을 산출하지 않음",
    }
    document["timing_sha256"] = canonical_sha256(document)
    return document


def _write_document(path: Path, document: dict) -> None:
    """! @brief 기존 evidence를 덮어쓰지 않고 JSON을 원자 확정합니다. """

    execution.write_new_json(path, document)


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief R1/R2의 inventory·plan·record·영향 검사를 CLI로 제공합니다. """

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--artifact-plan", type=Path, required=True)
    inventory_parser.add_argument("--output", type=Path, required=True)
    validate_inventory_parser = subparsers.add_parser("validate-inventory")
    validate_inventory_parser.add_argument("--inventory", type=Path, required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--inventory", type=Path, required=True)
    plan_parser.add_argument("--mode", choices=MODES, required=True)
    plan_parser.add_argument("--group", action="append", default=[])
    plan_parser.add_argument("--reason", default="explicit_cli_selection")
    plan_parser.add_argument("--output", type=Path, required=True)
    record_parser = subparsers.add_parser("validate-record")
    record_parser.add_argument("--record", type=Path, required=True)
    record_parser.add_argument("--record-root", type=Path, required=True)
    record_parser.add_argument("--plan", type=Path)
    record_parser.add_argument("--completion", action="store_true")
    impact_parser = subparsers.add_parser("impact")
    impact_parser.add_argument("--inventory", type=Path, required=True)
    impact_parser.add_argument("--changed-path", action="append", default=[])
    impact_parser.add_argument("--output", type=Path, required=True)
    bundle_parser = subparsers.add_parser("bundle")
    bundle_parser.add_argument("--artifact-plan", type=Path, required=True)
    bundle_parser.add_argument("--artifact-root", type=Path, required=True)
    bundle_parser.add_argument("--campaign", action="append", required=True)
    bundle_parser.add_argument("--output", type=Path, required=True)
    validate_bundle_parser = subparsers.add_parser("validate-bundle")
    validate_bundle_parser.add_argument("--bundle", type=Path, required=True)
    import_parser = subparsers.add_parser("import-bundle")
    import_parser.add_argument("--bundle", type=Path, required=True)
    import_parser.add_argument("--output", type=Path, required=True)
    validate_import_parser = subparsers.add_parser("validate-import")
    validate_import_parser.add_argument("--import-root", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        result: dict | None = None
        if args.command == "inventory":
            result = create_inventory(read_json(args.artifact_plan.resolve()))
            _write_document(args.output.resolve(), result)
        elif args.command == "validate-inventory":
            result = read_json(args.inventory.resolve())
            validate_inventory(result)
        elif args.command == "plan":
            inventory = read_json(args.inventory.resolve())
            selected = []
            for value in args.group:
                parts = value.split(":", 1)
                require(len(parts) == 2 and all(parts),
                        "group은 field:identifier 형식이어야 합니다")
                selected.append((parts[0], parts[1]))
            result = create_execution_plan(
                inventory,
                args.mode,
                selected if args.group else None,
                args.reason,
            )
            _write_document(args.output.resolve(), result)
        elif args.command == "validate-record":
            result = read_json(args.record.resolve())
            plan = read_json(args.plan.resolve()) if args.plan else None
            validate_record(
                result,
                args.record_root.resolve(),
                plan,
                completion=args.completion,
            )
        elif args.command == "impact":
            result = classify_changes(
                read_json(args.inventory.resolve()), args.changed_path
            )
            _write_document(args.output.resolve(), result)
        elif args.command == "bundle":
            result = create_minimal_bundle(
                read_json(args.artifact_plan.resolve()),
                args.artifact_root,
                args.campaign,
                args.output,
            )
        elif args.command == "validate-bundle":
            result = validate_minimal_bundle(args.bundle)
        elif args.command == "import-bundle":
            result = import_minimal_bundle(args.bundle, args.output)
        elif args.command == "validate-import":
            result = validate_minimal_import(args.import_root)
        require(result is not None, "pipeline command 결과가 없습니다")
        print(json.dumps({
            "status": "PASS",
            "command": args.command,
            "output": str(getattr(args, "output", "")) or None,
        }))
        return 0
    except (OSError, KeyError, TypeError, ValueError) as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(f"M33 W06 pipeline rejected: {message[:400]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
