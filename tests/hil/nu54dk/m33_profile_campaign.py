#!/usr/bin/env python3
"""! @brief Profile reboot/second-peer 물리 phase 20회를 content-addressed campaign으로 결합합니다. """
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

import m33_profile_run as phase_runner
from ble_pair_hil_common import git_revision
from m33_profile_native_pair import (evidence_nonce, parse_time,
                                     validate_campaign_triplet)

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "nucode-m33-profile-campaign-v1"
EXPECTED_CYCLES = 20
SEMANTICS = {
    "standard": ("standard_profiles", "bms_reboot_restore",
                 "scoped_bond_delete", "cleanup"),
    "native": ("native_fresh_restore", "native_second_peer",
               "key_identity", "cleanup"),
}


def digest(path: Path) -> str:
    """! @brief 실제 파일 byte의 SHA-256을 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_is_clean() -> bool:
    """! @brief untracked를 포함한 current checkout이 clean인지 확인합니다. """
    output = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1",
         "--untracked-files=all"], capture_output=True, text=True,
        check=True
    ).stdout
    return output == ""


def release_revisions(revision: str) -> dict[str, str]:
    """! @brief Core·board·NCS·Zephyr full revision을 3.4.0 lock에 결합합니다. """
    lock = json.loads(
        (ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
    )
    expected = {
        "core": revision,
        "board": lock["board"]["revision"],
        "ncs": lock["ncs"]["revision"],
        "zephyr": lock["zephyr"]["revision"],
    }
    if (phase_runner.git_revision(phase_runner.BOARD_ROOT) != expected["board"]
            or any(not isinstance(value, str) or len(value) != 40
                   for value in expected.values())):
        raise ValueError("profile campaign release revision lock mismatch")
    return expected


def parse_roles(entries: list[list[str]], expected: set[str]) -> dict[str, tuple[str, Path]]:
    """! @brief 중복 없는 역할→probe/image 입력을 고정합니다. """
    roles = {}
    for role, probe, filename in entries:
        image = Path(filename).resolve()
        if role in roles or role not in expected or not image.is_file():
            raise ValueError("profile campaign role mapping mismatch")
        roles[role] = (probe, image)
    if set(roles) != expected:
        raise ValueError("profile campaign role denominator mismatch")
    return roles


def parse_build_records(entries: list[list[str]], expected: set[str]) -> dict[str, Path]:
    """! @brief 역할별 exact build record 경로를 중복 없이 고정합니다. """
    records = {}
    for role, filename in entries:
        path = Path(filename).resolve()
        if role in records or role not in expected or not path.is_file():
            raise ValueError("profile campaign build record mismatch")
        records[role] = path
    if set(records) != expected:
        raise ValueError("profile campaign build record denominator mismatch")
    return records


def phase_reference(path: Path, evidence: dict) -> dict:
    """! @brief phase JSON의 실제 byte·nonce·시각을 aggregate record에 결합합니다. """
    if not path.is_file() or evidence.get("status") != "PASS":
        raise ValueError("profile campaign phase did not pass")
    return {
        "path": path.name,
        "sha256": digest(path),
        "nonce": evidence_nonce(evidence),
        "observed_utc": evidence["observed_utc"],
    }


def phase_namespace(args: argparse.Namespace, family: str, phase: str,
                    roles: dict[str, tuple[str, Path]],
                    records: dict[str, Path], prefix: Path,
                    predecessor: Path | None) -> argparse.Namespace:
    """! @brief 단일 물리 phase runner에 전달할 명시 인자를 생성합니다. """
    return argparse.Namespace(
        family=family,
        role=[[role, probe, str(image)] for role, (probe, image) in roles.items()],
        sdk_root=args.sdk_root,
        output_prefix=prefix,
        build_record=[[role, str(records[role])] for role in roles],
        native_security_phase=phase if family == "native" else None,
        native_prior_evidence=predecessor if family == "native" else None,
        bms_persistence_phase=phase if family == "standard" else None,
        bms_prior_evidence=predecessor if family == "standard" else None,
        execute=True,
        development=False,
        diagnostic_only=False,
    )


def planned_phase_prefixes(output: Path, family: str) -> dict[tuple[int, str], Path]:
    """! @brief 전체 phase의 JSON·transcript·sidecar 충돌을 물리 접근 전에 거부합니다. """
    phases = (("fresh", "restored", "second-peer")
              if family == "native" else ("fresh", "restored"))
    prefixes = {}
    used = {str(output).casefold()}
    for cycle in range(1, EXPECTED_CYCLES + 1):
        for phase in phases:
            ## @note 마지막 .run만 교체하므로 출력 이름의 점과 phase 식별자를 보존합니다.
            prefix = output.with_name(f"{output.stem}.cycle-{cycle:02d}.{phase}.run")
            native_path = prefix.with_suffix(".json")
            sidecars = phase_runner.reserve_sidecars(
                native_path, ("server", "client", "watcher")
            )
            paths = [native_path, prefix.with_suffix(".transcript.log")]
            paths.extend(path for values in sidecars.values() for path in values.values())
            for path in paths:
                key = str(path).casefold()
                if key in used or path.exists() or path.is_symlink():
                    raise ValueError("existing or duplicate profile campaign phase output")
                used.add(key)
            prefixes[(cycle, phase)] = prefix
    return prefixes


def _same_public_identity(left: dict, right: dict, roles: tuple[str, ...]) -> bool:
    """! @brief cycle 사이 probe/image/build identity가 바뀌지 않았는지 검사합니다. """
    return all(left.get(role) == right.get(role) for role in roles)


def final_hardware(evidence: dict, family: str) -> list[dict]:
    """! @brief 마지막 실제 phase의 exact program receipt를 공통 역할명으로 정규화합니다. """
    programs = evidence.get("exact_program", {})
    expected = {"server", "client", "watcher"}
    if set(programs) != expected:
        raise ValueError("profile campaign final hardware denominator")
    rows = []
    for role in ("server", "client", "watcher"):
        row = dict(programs[role])
        row["role"] = "second_peer" if family == "native" and role == "watcher" else role
        rows.append(row)
    return rows


def validate_campaign_evidence(path: Path, expected_family: str,
                               expected_revision: str | None = None) -> dict:
    """! @brief aggregate가 참조한 모든 phase byte와 raw 분모를 재검증합니다. """
    path = path.resolve()
    campaign = json.loads(path.read_text(encoding="utf-8"))
    revision = expected_revision or git_revision(ROOT)
    expected_revisions = release_revisions(revision)
    if (campaign.get("schema") != SCHEMA or campaign.get("family") != expected_family
            or campaign.get("status") != "PASS"
            or campaign.get("source_clean") is not True
            or campaign.get("cycles") != EXPECTED_CYCLES
            or campaign.get("revisions") != expected_revisions):
        raise ValueError("profile campaign identity mismatch")
    records = campaign.get("cycle_records")
    if (not isinstance(records, list) or len(records) != EXPECTED_CYCLES
            or [row.get("cycle") for row in records if isinstance(row, dict)]
               != list(range(1, EXPECTED_CYCLES + 1))):
        raise ValueError("profile campaign cycle denominator mismatch")
    statuses = {token: "PASS" for token in SEMANTICS[expected_family]}
    used_paths = set()
    used_hashes = set()
    used_nonces = set()
    previous_time = None
    aggregate_boards = None
    aggregate_builds = None
    last_phase = None

    def load_phase(reference: dict, phase: str) -> tuple[Path, dict]:
        if (not isinstance(reference, dict)
                or set(reference) != {"path", "sha256", "nonce", "observed_utc"}
                or not isinstance(reference.get("path"), str)
                or Path(reference["path"]).name != reference["path"]):
            raise ValueError("profile phase reference mismatch")
        phase_path = (path.parent / reference["path"]).resolve()
        if (phase_path.parent != path.parent or not phase_path.is_file()
                or digest(phase_path) != reference.get("sha256")):
            raise ValueError("profile phase byte mismatch")
        value = json.loads(phase_path.read_text(encoding="utf-8"))
        actual_phase = (value.get("native_security_phase") if expected_family == "native"
                        else value.get("bms_persistence_phase"))
        if (value.get("schema") != "nucode-m33-profile-hil-v1"
                or value.get("family") != expected_family
                or value.get("status") != "PASS" or value.get("development") is not False
                or value.get("reason") is not None or value.get("late_failures") != []
                or value.get("revisions") != expected_revisions
                or actual_phase != phase or evidence_nonce(value) != reference.get("nonce")
                or value.get("observed_utc") != reference.get("observed_utc")):
            raise ValueError("profile phase release evidence mismatch")
        phase_runner.validate_exact_program_bundle(phase_path, value)
        cleanup = value.get("cleanup", {})
        if set(cleanup) != {"server", "client", "watcher"}:
            raise ValueError("profile phase cleanup denominator mismatch")
        for role, record in cleanup.items():
            if not phase_runner.validate_stop_record(
                    "STOPPED", record, reference["nonce"], False) or \
                    record.get("serial_close") != "PASS":
                raise ValueError(f"profile {role} STOP cleanup mismatch")
        for role, program in value.get("exact_program", {}).items():
            descriptor = program.get("build_record", {})
            record_path = (phase_path.parent / descriptor.get("path", "")).resolve()
            if (not isinstance(descriptor, dict) or record_path.parent != phase_path.parent
                    or not record_path.is_file() or digest(record_path) != descriptor.get("sha256")):
                raise ValueError("profile phase build record byte mismatch")
            build = json.loads(record_path.read_text(encoding="utf-8"))
            build_family = ("standard" if expected_family == "native"
                            and phase != "second-peer" and role == "watcher"
                            else expected_family)
            if (build.get("schema") != "nucode-m33-profile-build-v1"
                    or build.get("source_revision") != revision
                    or build.get("development") is not False
                    or build.get("role") != role or build.get("family") != build_family):
                raise ValueError("profile release build record mismatch")
            image_reference = program.get("image", {})
            image_path = (phase_path.parent /
                          image_reference.get("path", "")).resolve()
            identity = phase_runner.validate_build_record_identity(
                record_path, build_family, role, digest(image_path), revision
            )
            if identity != value.get("build_identity", {}).get(role):
                raise ValueError("profile release build identity mismatch")
        return phase_path, value

    for index, record in enumerate(records, 1):
        previous_closure = None if index == 1 else records[index - 2]["phases"][-1]["sha256"]
        if (set(record) != {"cycle", "status", "semantics",
                            "previous_cycle_closure_sha256", "phases"}
                or record.get("cycle") != index or record.get("status") != "PASS"
                or record.get("semantics") != statuses
                or record.get("previous_cycle_closure_sha256") != previous_closure):
            raise ValueError("profile typed cycle record mismatch")
        phase_names = (("fresh", "restored", "second-peer")
                       if expected_family == "native" else ("fresh", "restored"))
        if not isinstance(record["phases"], list) or len(record["phases"]) != len(phase_names):
            raise ValueError("profile campaign phase denominator mismatch")
        phases = []
        for phase_name, reference in zip(phase_names, record["phases"], strict=True):
            phase_path, value = load_phase(reference, phase_name)
            if (reference["path"] in used_paths or reference["sha256"] in used_hashes
                    or reference["nonce"] in used_nonces):
                raise ValueError("profile campaign phase replay detected")
            observed = parse_time(value)
            if previous_time is not None and observed <= previous_time:
                raise ValueError("profile campaign phase order mismatch")
            previous_time = observed
            used_paths.add(reference["path"])
            used_hashes.add(reference["sha256"])
            used_nonces.add(reference["nonce"])
            phases.append((phase_path, value))
        if expected_family == "native":
            normalized = validate_campaign_triplet(
                phases[0][0], phases[1][0], phases[2][0]
            )
            boards = normalized["boards"]
            builds = normalized["build_identity"]
        else:
            fresh_path, fresh = phases[0]
            _, restored = phases[1]
            if restored.get("bms_prior_evidence_sha256") != digest(fresh_path):
                raise ValueError("standard profile predecessor hash mismatch")
            phase_runner.validate_bms_predecessor(
                fresh_path, fresh["revisions"], fresh["boards"], fresh["build_identity"]
            )
            phase_runner.validate_results(
                "standard", restored["results"], restored["server"], "restored"
            )
            bms = restored.get("bms_evidence", {})
            stage = 0
            for role, kind in (("client", "BMS_RESTORED_READY"),
                               ("server", "BMS_ARMED"),
                               ("server", "BMS_DELETED"),
                               ("client", "BMS_CLEANED")):
                if kind not in bms:
                    raise ValueError("standard restored BMS evidence missing")
                stage, _, _ = phase_runner.bms_transition(
                    stage, role, kind, bms[kind], "restored"
                )
            if stage != 5:
                raise ValueError("standard restored BMS cleanup incomplete")
            boards = phase_runner.public_board_identity(restored["boards"])
            builds = restored["build_identity"]
        if aggregate_boards is None:
            aggregate_boards = boards
            aggregate_builds = builds
        elif aggregate_boards != boards or aggregate_builds != builds:
            raise ValueError("profile campaign cycle identity drift")
        last_phase = phases[-1][1]

    if (campaign.get("boards") != aggregate_boards
            or campaign.get("build_identity") != aggregate_builds):
        raise ValueError("profile aggregate public identity mismatch")
    attestation = campaign.get("m33_dispatch_attestation", {})
    if (attestation.get("campaign_id") != f"m33_profiles_{expected_family}"
            or attestation.get("source_revision") != revision
            or attestation.get("source_clean") is not True
            or attestation.get("semantic_status") != statuses
            or attestation.get("hardware") != final_hardware(last_phase, expected_family)):
        raise ValueError("profile campaign attestation mismatch")
    expected_attestation_records = [
        {"cycle": cycle, "status": "PASS", "semantics": dict(statuses)}
        for cycle in range(1, EXPECTED_CYCLES + 1)
    ]
    if attestation.get("cycle_records") != expected_attestation_records:
        raise ValueError("profile campaign cycle denominator mismatch")
    return campaign


def execute_campaign(args: argparse.Namespace, execute_phase=phase_runner.execute) -> dict:
    """! @brief 20개 실제 reboot chain을 순차 실행하고 raw phase 분모만 집계합니다. """
    if args.cycles != EXPECTED_CYCLES or not args.execute:
        raise ValueError("profile campaign requires explicit 20-cycle execution")
    if not source_is_clean():
        raise ValueError("profile campaign requires clean source")
    revision = git_revision(ROOT)
    output = args.output.resolve()
    if output.exists() or output.suffix.lower() != ".json":
        raise ValueError("new profile campaign JSON output required")
    output.parent.mkdir(parents=True, exist_ok=True)
    base_roles = parse_roles(args.role, {"server", "client", "watcher"})
    base_records = parse_build_records(
        args.build_record, {"server", "client", "watcher"}
    )
    second_roles = None
    second_records = None
    if args.family == "native":
        if args.second_peer_role is None or args.second_peer_build_record is None:
            raise ValueError("native campaign requires exact second-peer image and record")
        probe, filename = args.second_peer_role
        second_image = Path(filename).resolve()
        second_record = args.second_peer_build_record.resolve()
        if (not second_image.is_file() or not second_record.is_file()
                or probe != base_roles["watcher"][0]):
            raise ValueError("native second-peer physical role mismatch")
        second_roles = {**base_roles, "watcher": (probe, second_image)}
        second_records = {**base_records, "watcher": second_record}
    elif args.second_peer_role is not None or args.second_peer_build_record is not None:
        raise ValueError("standard campaign cannot carry second-peer inputs")

    prefixes = planned_phase_prefixes(output, args.family)
    cycle_records = []
    used_paths = set()
    used_hashes = set()
    used_nonces = set()
    previous_time = None
    public_boards = None
    public_builds = None
    last_evidence = None
    for cycle in range(1, args.cycles + 1):
        phases = []
        fresh_prefix = prefixes[(cycle, "fresh")]
        fresh = execute_phase(phase_namespace(
            args, args.family, "fresh", base_roles, base_records,
            fresh_prefix, None
        ))
        fresh_path = fresh_prefix.with_suffix(".json")
        phases.append(phase_reference(fresh_path, fresh))

        restored_prefix = prefixes[(cycle, "restored")]
        restored = execute_phase(phase_namespace(
            args, args.family, "restored", base_roles, base_records,
            restored_prefix, fresh_path
        ))
        restored_path = restored_prefix.with_suffix(".json")
        phases.append(phase_reference(restored_path, restored))

        if args.family == "native":
            second_prefix = prefixes[(cycle, "second-peer")]
            second = execute_phase(phase_namespace(
                args, "native", "second-peer", second_roles, second_records,
                second_prefix, restored_path
            ))
            second_path = second_prefix.with_suffix(".json")
            phases.append(phase_reference(second_path, second))
            normalized = validate_campaign_triplet(
                fresh_path, restored_path, second_path
            )
            boards = normalized["boards"]
            builds = normalized["build_identity"]
            last_evidence = second
        else:
            if restored.get("bms_prior_evidence_sha256") != hashlib.sha256(
                    fresh_path.read_bytes()).hexdigest():
                raise ValueError("standard profile predecessor chain mismatch")
            phase_runner.validate_bms_predecessor(
                fresh_path, fresh["revisions"], fresh["boards"],
                fresh["build_identity"]
            )
            phase_runner.validate_results(
                "standard", restored.get("results", {}),
                restored.get("server", {}), "restored"
            )
            if (restored.get("status") != "PASS"
                    or restored.get("bms_persistence_phase") != "restored"
                    or restored.get("reason") is not None
                    or restored.get("late_failures") != []):
                raise ValueError("standard restored phase did not close")
            boards = phase_runner.public_board_identity(restored["boards"])
            builds = restored["build_identity"]
            last_evidence = restored

        for reference in phases:
            if (reference["path"] in used_paths or reference["sha256"] in used_hashes
                    or reference["nonce"] in used_nonces):
                raise ValueError("profile campaign phase replay detected")
            observed = datetime.fromisoformat(reference["observed_utc"])
            if observed.tzinfo is None or observed.utcoffset() is None:
                raise ValueError("profile campaign phase time lacks timezone")
            if previous_time is not None and observed <= previous_time:
                raise ValueError("profile campaign phase order mismatch")
            previous_time = observed
            used_paths.add(reference["path"])
            used_hashes.add(reference["sha256"])
            used_nonces.add(reference["nonce"])

        if public_boards is None:
            public_boards = boards
            public_builds = builds
        else:
            roles = tuple(public_boards)
            if (not _same_public_identity(public_boards, boards, roles)
                    or not _same_public_identity(public_builds, builds, roles)):
                raise ValueError("profile campaign cycle identity drift")
        cycle_records.append({
            "cycle": cycle,
            "status": "PASS",
            "semantics": {token: "PASS" for token in SEMANTICS[args.family]},
            "previous_cycle_closure_sha256": (
                None if cycle == 1 else cycle_records[-1]["phases"][-1]["sha256"]
            ),
            "phases": phases,
        })

    if not source_is_clean() or git_revision(ROOT) != revision:
        raise ValueError("profile campaign source changed during execution")
    attestation = {
        "schema_version": 1,
        "kind": "m33_native_campaign_attestation",
        "campaign_id": f"m33_profiles_{args.family}",
        "source_revision": revision,
        "source_clean": True,
        "semantic_status": {token: "PASS" for token in SEMANTICS[args.family]},
        "cycle_records": [
            {"cycle": row["cycle"], "status": "PASS",
             "semantics": dict(row["semantics"])}
            for row in cycle_records
        ],
        "hardware": final_hardware(last_evidence, args.family),
    }
    result = {
        "schema": SCHEMA,
        "family": args.family,
        "status": "PASS",
        "source_clean": True,
        "revisions": last_evidence["revisions"],
        "cycles": args.cycles,
        "boards": public_boards,
        "build_identity": public_builds,
        "cycle_records": cycle_records,
        "m33_dispatch_attestation": attestation,
    }
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return validate_campaign_evidence(output, args.family, revision)


def main() -> int:
    """! @brief 자동 삭제 없이 명시 승인된 20-cycle profile campaign을 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=("standard", "native"), required=True)
    parser.add_argument("--role", nargs=3, action="append",
                        metavar=("ROLE", "PROBE_SHA256", "HEX"), required=True)
    parser.add_argument("--build-record", nargs=2, action="append",
                        metavar=("ROLE", "JSON"), required=True)
    parser.add_argument("--second-peer-role", nargs=2,
                        metavar=("PROBE_SHA256", "HEX"))
    parser.add_argument("--second-peer-build-record", type=Path)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=EXPECTED_CYCLES)
    parser.add_argument("--execute", action="store_true")
    try:
        result = execute_campaign(parser.parse_args())
    except (KeyError, OSError, RuntimeError, subprocess.SubprocessError,
            TypeError, ValueError) as error:
        print("M33 profile campaign FAIL: " + str(error))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
