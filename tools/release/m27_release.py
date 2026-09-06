#!/usr/bin/env python3
"""Prepare and validate the private M27 v0.4.0 release-candidate package."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE_MODULE = REPOSITORY / "packaging" / "boards-manager" / "nu54_package.py"
READINESS_PATH = REPOSITORY / "variants" / "nu54dk" / "v0.4.0-release-readiness.json"
VERSION = "0.4.0-rc.1"
STABLE_VERSION = "0.4.0"
BASE_RC_VERSIONS = (
    "0.1.0-rc.2",
    "0.2.0-rc.1",
    "0.2.0-rc.2",
    "0.3.0-rc.1",
    "0.3.0-rc.2",
    "0.3.0-rc.3",
)
BASE_STABLE_VERSIONS = ("0.1.0", "0.2.0", "0.3.0")
REQUIRED_GATE_IDS = (
    "m23_inventory",
    "m24_serial_source_build",
    "m24_onboard_hil",
    "m24_fixture_hil",
    "m25_source_build",
    "m25_onboard_hil",
    "m25_fixture_hil",
    "m26_inventory",
    "m26_onboard_hil",
    "host_regression",
    "documentation",
    "zephyr_repro_build",
    "package_reproducibility",
    "boards_manager_lifecycle",
    "legacy_assets_immutable",
    "project_owner_approval",
)
PACKAGE_GATE_ID = "package_reproducibility"
VERIFICATION_SCOPE = {
    "id": "v0.4.0-core-functional-hil-v1",
    "decision_record": "00_Docs/04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md",
    "required_fixture": "nu54dk-onboard-or-two-board-peer-with-safe-wiring",
    "external_measurement_equipment_required": False,
    "third_party_device_qualification_required": False,
    "unverified_core_function_policy": "hold-not-pass",
}


class M27ReleaseFailure(RuntimeError):
    """The M27 candidate package or release-readiness contract failed."""


def strict_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M27ReleaseFailure(f"duplicate JSON key: {path}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M27ReleaseFailure(f"invalid UTF-8 JSON: {path}: {error}") from error


def canonical_json(document: Any) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise M27ReleaseFailure(f"Git query failed: {result.stderr.strip()}")
    return result.stdout.strip()


def assert_exact_clean_commit(repository: Path, revision: str) -> str:
    commit = git_output(repository, "rev-parse", f"{revision}^{{commit}}")
    if git_output(repository, "rev-parse", "HEAD") != commit:
        raise M27ReleaseFailure("candidate packaging requires HEAD to match the requested commit")
    status = git_output(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    if status:
        raise M27ReleaseFailure("candidate packaging requires a clean source checkout")
    submodules = git_output(repository, "submodule", "status", "--recursive")
    if any(
        line.startswith(("+", "-", "U"))
        or re.fullmatch(r" ?[0-9a-f]{40} [^\r\n]+", line) is None
        for line in submodules.splitlines()
        if line
    ):
        raise M27ReleaseFailure("candidate packaging requires exact clean submodules")
    return commit


def load_package_module() -> Any:
    specification = importlib.util.spec_from_file_location(
        "nu54_m27_package", PACKAGE_MODULE
    )
    if specification is None or specification.loader is None:
        raise M27ReleaseFailure(f"cannot load package module: {PACKAGE_MODULE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def configure_v04_candidate(package: Any) -> None:
    if tuple(package.RELEASE_CANDIDATE_VERSIONS) != BASE_RC_VERSIONS:
        raise M27ReleaseFailure("historical release-candidate allowlist changed")
    if tuple(package.STABLE_VERSIONS) != BASE_STABLE_VERSIONS:
        raise M27ReleaseFailure("historical stable allowlist changed")
    package.configure_release_candidates(BASE_RC_VERSIONS + (VERSION,))


def validate_contract(repository: Path = REPOSITORY) -> dict[str, Any]:
    ledger = strict_json(repository / READINESS_PATH.relative_to(REPOSITORY))
    if not isinstance(ledger, dict):
        raise M27ReleaseFailure("readiness ledger must be an object")
    fixed = {
        "schema_version": 1,
        "milestone": "M27",
        "candidate_version": VERSION,
        "stable_version": STABLE_VERSION,
        "publication_policy": (
            "no-tag-release-or-index-publication-until-every-required-gate-passes"
        ),
    }
    if any(ledger.get(key) != value for key, value in fixed.items()):
        raise M27ReleaseFailure("M27 release identity or publication policy drifted")
    scope = ledger.get("verification_scope")
    if (
        not isinstance(scope, dict)
        or canonical_json(scope) != canonical_json(VERIFICATION_SCOPE)
    ):
        raise M27ReleaseFailure("M27 owner-approved functional verification scope drifted")
    decision = (repository / scope["decision_record"]).resolve()
    if not decision.is_relative_to(repository.resolve()) or not decision.is_file():
        raise M27ReleaseFailure("M27 verification scope decision record is missing")
    gates = ledger.get("gates")
    if not isinstance(gates, list):
        raise M27ReleaseFailure("M27 gates must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("id"), str):
            raise M27ReleaseFailure("every M27 gate must have a string id")
        gate_id = gate["id"]
        if gate_id in by_id:
            raise M27ReleaseFailure(f"duplicate M27 gate: {gate_id}")
        if gate.get("kind") not in {"automated", "physical", "human"}:
            raise M27ReleaseFailure(f"invalid M27 gate kind: {gate_id}")
        if gate.get("required") is not True:
            raise M27ReleaseFailure(f"M27 release gate cannot be optional: {gate_id}")
        state = gate.get("state")
        if state not in {"passed", "pending", "hold"}:
            raise M27ReleaseFailure(f"invalid M27 gate state: {gate_id}")
        if state == "passed":
            evidence = gate.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                raise M27ReleaseFailure(f"passed gate has no evidence: {gate_id}")
            for relative in evidence:
                if not isinstance(relative, str):
                    raise M27ReleaseFailure(f"invalid evidence path: {gate_id}")
                path = (repository / relative).resolve()
                if not path.is_relative_to(repository.resolve()) or not path.is_file():
                    raise M27ReleaseFailure(f"missing gate evidence: {gate_id}: {relative}")
        elif not isinstance(gate.get("reason"), str) or not gate["reason"]:
            raise M27ReleaseFailure(f"unpassed gate has no reason: {gate_id}")
        by_id[gate_id] = gate
    if tuple(by_id) != REQUIRED_GATE_IDS:
        raise M27ReleaseFailure("M27 required gate set or order drifted")
    if by_id["project_owner_approval"]["kind"] != "human":
        raise M27ReleaseFailure("stable publication must retain a human approval gate")
    if by_id["m24_fixture_hil"]["kind"] != "physical" or by_id[
        "m25_fixture_hil"
    ]["kind"] != "physical":
        raise M27ReleaseFailure("external fixture gates must remain physical")
    return ledger


def effective_readiness(
    ledger: dict[str, Any], *, package_reproducibility_passed: bool
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    for gate in ledger["gates"]:
        state = gate["state"]
        if gate["id"] == PACKAGE_GATE_ID and package_reproducibility_passed:
            state = "passed"
        if gate["required"] and state != "passed":
            blockers.append(gate["id"])
    return not blockers, blockers


def artifact_record(base: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file():
        raise M27ReleaseFailure(f"artifact escaped output directory: {path}")
    return {
        "path": resolved.relative_to(base.resolve()).as_posix(),
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def compare_reproducible_builds(
    first: dict[str, Path], second: dict[str, Path]
) -> dict[str, str]:
    if set(first) != set(second):
        raise M27ReleaseFailure("isolated package builds produced different artifact roles")
    hashes: dict[str, str] = {}
    for role in sorted(first):
        first_hash = sha256_file(first[role])
        second_hash = sha256_file(second[role])
        if first_hash != second_hash or first[role].stat().st_size != second[role].stat().st_size:
            raise M27ReleaseFailure(f"package reproducibility mismatch: {role}")
        hashes[role] = first_hash
    return hashes


def prepare(repository: Path, output_dir: Path, revision: str) -> Path:
    repository = repository.resolve()
    output_dir = output_dir.resolve()
    commit = assert_exact_clean_commit(repository, revision)
    ledger = validate_contract(repository)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise M27ReleaseFailure(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_dir / "artifacts"
    package = load_package_module()
    configure_v04_candidate(package)
    try:
        with tempfile.TemporaryDirectory(prefix="nu54-m27-repro-") as temporary:
            first = package.build_package(repository, artifacts_dir, VERSION, commit)
            second = package.build_package(
                repository, Path(temporary) / "artifacts", VERSION, commit
            )
            reproducible_hashes = compare_reproducible_builds(first, second)
        index = package.generate_index(artifacts_dir, [VERSION])
        manifest = package.validate_archive(
            first["archive"], expected_version=VERSION, expected_commit=commit
        )
        package.validate_index(index, artifact_dir=artifacts_dir)
    except package.PackageError as error:
        raise M27ReleaseFailure(str(error)) from error

    ready, blockers = effective_readiness(
        ledger, package_reproducibility_passed=True
    )
    if ready:
        raise M27ReleaseFailure(
            "candidate preparation cannot consume project-owner publication approval"
        )
    artifacts = {role: artifact_record(output_dir, path) for role, path in first.items()}
    artifacts["index"] = artifact_record(output_dir, index)
    plan = {
        "schema_version": 1,
        "milestone": "M27",
        "version": VERSION,
        "stable_version": STABLE_VERSION,
        "status": "hold",
        "publication_allowed": False,
        "core_revision": commit,
        "board_revision": manifest["board_revision"],
        "runtime_payload_sha256": manifest["runtime_payload_sha256"],
        "readiness_contract_sha256": sha256_file(
            repository / READINESS_PATH.relative_to(REPOSITORY)
        ),
        "package_reproducibility": {
            "status": "passed",
            "isolated_builds": 2,
            "artifact_hashes": reproducible_hashes,
        },
        "blockers": blockers,
        "artifacts": artifacts,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    plan_path = output_dir / "m27-release-plan.json"
    temporary_plan = plan_path.with_suffix(".json.tmp")
    temporary_plan.write_bytes(canonical_json(plan))
    temporary_plan.replace(plan_path)
    validate_plan(plan_path, repository=repository)
    return plan_path


def validate_plan(plan_path: Path, *, repository: Path = REPOSITORY) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    plan = strict_json(plan_path)
    if (
        not isinstance(plan, dict)
        or plan.get("schema_version") != 1
        or plan.get("milestone") != "M27"
        or plan.get("version") != VERSION
        or plan.get("stable_version") != STABLE_VERSION
        or plan.get("status") != "hold"
        or plan.get("publication_allowed") is not False
    ):
        raise M27ReleaseFailure("M27 plan identity or HOLD policy is invalid")
    if not isinstance(plan.get("blockers"), list) or not plan["blockers"]:
        raise M27ReleaseFailure("M27 plan must retain at least one release blocker")
    ledger = validate_contract(repository.resolve())
    if plan.get("readiness_contract_sha256") != sha256_file(
        repository.resolve() / READINESS_PATH.relative_to(REPOSITORY)
    ):
        raise M27ReleaseFailure("M27 plan readiness contract checksum changed")
    ready, expected_blockers = effective_readiness(
        ledger, package_reproducibility_passed=True
    )
    if ready or plan["blockers"] != expected_blockers:
        raise M27ReleaseFailure("M27 plan blocker set does not match the release contract")
    artifacts = plan.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        "archive",
        "checksums",
        "licenses",
        "manifest",
        "notices",
        "sbom",
        "index",
    }:
        raise M27ReleaseFailure("M27 plan artifact set is invalid")
    resolved: dict[str, Path] = {}
    for role, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise M27ReleaseFailure(f"invalid M27 artifact record: {role}")
        candidate = (plan_path.parent / str(record["path"])).resolve()
        if not candidate.is_relative_to(plan_path.parent) or not candidate.is_file():
            raise M27ReleaseFailure(f"missing or escaped M27 artifact: {role}")
        if candidate.stat().st_size != record["size"] or sha256_file(candidate) != record["sha256"]:
            raise M27ReleaseFailure(f"M27 artifact identity changed: {role}")
        resolved[role] = candidate
    package = load_package_module()
    configure_v04_candidate(package)
    try:
        manifest = package.validate_archive(
            resolved["archive"],
            expected_version=VERSION,
            expected_commit=plan["core_revision"],
        )
        package.validate_index(resolved["index"], artifact_dir=resolved["index"].parent)
    except package.PackageError as error:
        raise M27ReleaseFailure(str(error)) from error
    if (
        manifest["board_revision"] != plan.get("board_revision")
        or manifest["runtime_payload_sha256"] != plan.get("runtime_payload_sha256")
    ):
        raise M27ReleaseFailure("M27 plan and package provenance differ")
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M27 private v0.4.0 RC preparation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("contract")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--repository", type=Path, default=REPOSITORY)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--commit", default="HEAD")
    validate_parser = subparsers.add_parser("validate-plan")
    validate_parser.add_argument("--plan", type=Path, required=True)
    validate_parser.add_argument("--repository", type=Path, default=REPOSITORY)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "contract":
        ledger = validate_contract()
        ready, blockers = effective_readiness(
            ledger, package_reproducibility_passed=False
        )
        if ready:
            raise M27ReleaseFailure("unpublished M27 contract unexpectedly became ready")
        print(f"M27_RELEASE_CONTRACT_PASS=gates:{len(ledger['gates'])};blockers:{len(blockers)}")
    elif parsed.command == "prepare":
        plan = prepare(parsed.repository, parsed.output_dir, parsed.commit)
        print(f"M27_RELEASE_PREPARE_HOLD=1;PLAN={plan}")
    elif parsed.command == "validate-plan":
        plan = validate_plan(parsed.plan, repository=parsed.repository)
        print(f"M27_RELEASE_PLAN_HOLD=1;BLOCKERS={len(plan['blockers'])}")
    else:
        raise M27ReleaseFailure(f"unsupported command: {parsed.command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M27ReleaseFailure as error:
        print(f"M27_RELEASE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
