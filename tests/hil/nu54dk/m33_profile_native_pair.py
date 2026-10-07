#!/usr/bin/env python3
"""! @brief native fresh pairing과 reboot 복원 evidence를 exact pair로 검증합니다. """
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from m33_profile_run import (public_board_identity, validate_exact_program_bundle,
                             validate_native_security, validate_second_peer)

PAIR_SCHEMA = "nucode-m33-profile-native-pair-v1"
SUCCESS = {"PASS"}


def evidence_nonce(evidence: dict) -> str:
    """! @brief RESULT와 모든 STOPPED가 공유하는 run nonce를 반환합니다. """
    nonce = evidence.get("results", {}).get("client", {}).get("nonce")
    cleanup = evidence.get("cleanup", {})
    if (not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce)
            or len(cleanup) != 3
            or any(record.get("nonce") != nonce for record in cleanup.values()
                   if isinstance(record, dict))
            or any(not isinstance(record, dict) for record in cleanup.values())):
        raise ValueError("native pair nonce/cleanup mismatch")
    return nonce


def load_phase(path: Path, phase: str) -> tuple[dict, bytes]:
    """! @brief 지정 phase의 성공 evidence와 내부 보안 분모를 다시 검증합니다. """
    raw = path.read_bytes()
    evidence = json.loads(raw)
    if (evidence.get("schema") != "nucode-m33-profile-hil-v1"
            or evidence.get("family") != "native"
            or evidence.get("native_security_phase") != phase
            or evidence.get("status") not in SUCCESS
            or evidence.get("reason") is not None
            or evidence.get("late_failures") != []):
        raise ValueError(f"native {phase} evidence is not a clean success")
    if phase == "second-peer":
        validate_second_peer(evidence.get("results", {}),
                             evidence.get("native_security", {}),
                             evidence.get("identity_cleanup", {}))
    else:
        validate_native_security(phase, evidence.get("results", {}),
                                 evidence.get("server", {}),
                                 evidence.get("native_security", {}))
    validate_exact_program_bundle(path, evidence)
    evidence_nonce(evidence)
    return evidence, raw


def parse_time(evidence: dict) -> datetime:
    """! @brief timezone이 포함된 UTC evidence 시각만 해석합니다. """
    try:
        observed = datetime.fromisoformat(evidence["observed_utc"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("native pair observed time is invalid") from error
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("native pair observed time lacks timezone")
    return observed


def validate_pair(fresh_path: Path, restored_path: Path) -> dict:
    """! @brief source/image가 같은 순차 fresh→restored evidence만 승인합니다. """
    fresh_path = fresh_path.resolve()
    restored_path = restored_path.resolve()
    if fresh_path == restored_path:
        raise ValueError("native pair replayed one evidence file")
    fresh, fresh_raw = load_phase(fresh_path, "fresh")
    restored, restored_raw = load_phase(restored_path, "restored")
    fresh_sha256 = hashlib.sha256(fresh_raw).hexdigest()
    restored_sha256 = hashlib.sha256(restored_raw).hexdigest()
    if restored.get("native_prior_evidence_sha256") != fresh_sha256:
        raise ValueError("restored evidence is not chained to fresh evidence")
    if fresh.get("native_prior_evidence_sha256") is not None:
        raise ValueError("fresh evidence unexpectedly has a predecessor")
    if (fresh.get("revisions") != restored.get("revisions")
            or fresh.get("build_identity") != restored.get("build_identity")
            or public_board_identity(fresh.get("boards", {}))
               != public_board_identity(restored.get("boards", {}))):
        raise ValueError("native pair source/image/board identity mismatch")
    identities = fresh.get("build_identity")
    boards = public_board_identity(fresh.get("boards", {}))
    if (not isinstance(identities, dict) or set(identities) != {"server", "client", "watcher"}
            or set(boards) != {"server", "client", "watcher"}
            or len({record.get("source_sha256") for record in identities.values()
                    if isinstance(record, dict)}) != 1
            or any(record.get("image_sha256")
                   != boards.get(role, {}).get("image_sha256")
                   for role, record in identities.items() if isinstance(record, dict))
            or any(not isinstance(record, dict) for record in identities.values())):
        raise ValueError("native pair exact build identity is incomplete")
    fresh_nonce = evidence_nonce(fresh)
    restored_nonce = evidence_nonce(restored)
    if fresh_nonce == restored_nonce or fresh_sha256 == restored_sha256:
        raise ValueError("native pair evidence replay detected")
    if parse_time(fresh) >= parse_time(restored):
        raise ValueError("native pair order is not fresh then restored")
    return {
        "schema": PAIR_SCHEMA,
        "status": "PASS",
        "revisions": fresh["revisions"],
        "build_identity": identities,
        "boards": boards,
        "fresh": {"path": str(fresh_path), "sha256": fresh_sha256,
                  "nonce": fresh_nonce, "observed_utc": fresh["observed_utc"]},
        "restored": {"path": str(restored_path), "sha256": restored_sha256,
                     "nonce": restored_nonce, "observed_utc": restored["observed_utc"]},
    }


def validate_campaign_triplet(fresh_path: Path, restored_path: Path,
                              second_peer_path: Path) -> dict:
    """! @brief fresh→restored→second-peer 실제 byte chain을 하나의 campaign으로 결합합니다. """
    pair = validate_pair(fresh_path, restored_path)
    second_peer_path = second_peer_path.resolve()
    if second_peer_path in {fresh_path.resolve(), restored_path.resolve()}:
        raise ValueError("native campaign replayed phase evidence")
    second, second_raw = load_phase(second_peer_path, "second-peer")
    restored_raw = restored_path.resolve().read_bytes()
    restored_sha256 = hashlib.sha256(restored_raw).hexdigest()
    second_sha256 = hashlib.sha256(second_raw).hexdigest()
    if second.get("native_prior_evidence_sha256") != restored_sha256:
        raise ValueError("second-peer evidence is not chained to restored evidence")
    pair_boards = pair["boards"]
    second_boards = public_board_identity(second.get("boards", {}))
    pair_build = pair["build_identity"]
    second_build = second.get("build_identity", {})
    if (pair["revisions"] != second.get("revisions")
            or any(pair_boards.get(role) != second_boards.get(role)
                   for role in ("server", "client"))
            or any(pair_build.get(role) != second_build.get(role)
                   for role in ("server", "client"))
            or pair_boards.get("watcher", {}).get("probe_sha256")
               != second_boards.get("watcher", {}).get("probe_sha256")
            or pair_build.get("watcher") == second_build.get("watcher")):
        raise ValueError("second-peer source/image/board identity mismatch")
    if parse_time({"observed_utc": pair["restored"]["observed_utc"]}) >= parse_time(second):
        raise ValueError("native campaign phase order mismatch")
    return {
        "schema": PAIR_SCHEMA,
        "status": "PASS",
        "revisions": pair["revisions"],
        "build_identity": {
            "server": second_build["server"],
            "client": second_build["client"],
            "second_peer": second_build["watcher"],
        },
        "boards": {
            "server": second_boards["server"],
            "client": second_boards["client"],
            "second_peer": second_boards["watcher"],
        },
        "fresh": pair["fresh"],
        "restored": pair["restored"],
        "second_peer": {"path": str(second_peer_path), "sha256": second_sha256,
                        "nonce": evidence_nonce(second),
                        "observed_utc": second["observed_utc"]},
    }


def main() -> int:
    """! @brief 두 evidence를 검증하고 pair manifest를 새 파일로 저장합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", type=Path, required=True)
    parser.add_argument("--restored", type=Path, required=True)
    parser.add_argument("--second-peer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("existing native pair output must not be overwritten")
        result = validate_campaign_triplet(
            args.fresh, args.restored, args.second_peer
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (KeyError, OSError, TypeError, ValueError) as error:
        print("M33 native pair FAIL: " + str(error))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
