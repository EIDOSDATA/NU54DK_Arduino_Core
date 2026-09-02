#!/usr/bin/env python3
"""! @brief 통과한 M22 clean-room의 보류된 exact-leaf 정리만 안전하게 재개합니다. """

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

from m22_cleanroom import (
    CleanroomFailure,
    MARKER_NAME,
    file_sha256,
    is_reparse,
    safe_cleanup_run,
    strict_json,
    write_json,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


## @brief tree 내부 Windows 읽기 전용 regular file 개수를 계산합니다.
def count_readonly_files(run_root: Path) -> int:
    readonly_attribute = getattr(stat, "FILE_ATTRIBUTE_READONLY", 0)
    count = 0
    for directory, names, files in os.walk(run_root, followlinks=False):
        for name in [*names, *files]:
            path = Path(directory) / name
            if is_reparse(path):
                raise CleanroomFailure(f"cleanup tree에 reparse point가 있습니다: {path}")
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
            if path.is_file() and attributes & readonly_attribute:
                count += 1
    return count


## @brief cleanup=pending인 통과 증적의 exact run leaf 정리만 재개합니다.
def recover_cleanup(parent: Path, run_root: Path, evidence_path: Path) -> dict[str, object]:
    parent = parent.absolute()
    run_root = run_root.absolute()
    evidence_path = evidence_path.absolute()
    if run_root.parent != parent:
        raise CleanroomFailure("복구 대상은 지정 parent의 exact run leaf여야 합니다.")
    if not parent.is_dir() or not run_root.is_dir():
        raise CleanroomFailure("복구 parent 또는 exact run leaf가 없습니다.")
    if is_reparse(parent) or is_reparse(run_root):
        raise CleanroomFailure("복구 parent/run leaf에 reparse point가 있습니다.")

    marker = strict_json(run_root / MARKER_NAME)
    evidence = strict_json(evidence_path)
    cleanup = evidence.get("cleanup", {})
    if evidence.get("status") != "passed" or not isinstance(cleanup, dict):
        raise CleanroomFailure("기능 검증을 통과한 clean-room 증적이 아닙니다.")
    if cleanup.get("status") != "pending":
        raise CleanroomFailure("cleanup=pending 증적만 복구할 수 있습니다.")

    run_id = marker.get("run_id")
    token = marker.get("cleanup_token")
    if not isinstance(run_id, str) or not isinstance(token, str):
        raise CleanroomFailure("cleanup marker identity가 없습니다.")

    readonly_count = count_readonly_files(run_root)
    pending_evidence_sha256 = file_sha256(evidence_path)
    safe_cleanup_run(parent, run_root, run_id, token, evidence_path)
    evidence["cleanup"] = {
        "status": "passed",
        "exact_run_leaf_removed": True,
        "external_evidence_preserved": True,
        "reparse_scan_passed": True,
        "marker_verified": True,
        "recovery": {
            "attempts": 2,
            "initial_failure": "windows-read-only-file-attribute",
            "readonly_files_detected": readonly_count,
            "pending_evidence_sha256": pending_evidence_sha256,
            "runner": "tools/release/m22_cleanup_recovery.py",
            "runner_sha256": file_sha256(Path(__file__).resolve()),
        },
    }
    write_json(evidence_path, evidence)
    return evidence["cleanup"]


## @brief cleanup 복구 parser를 구성합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M22 exact-leaf cleanup recovery")
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser


## @brief cleanup 복구 진입점입니다.
def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        cleanup = recover_cleanup(args.parent, args.run_root, args.evidence)
        print(json.dumps(cleanup, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except CleanroomFailure as error:
        print(f"M22_CLEANUP_RECOVERY_FAIL: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(
            f"M22_CLEANUP_RECOVERY_FAIL: 예상하지 못한 내부 오류({type(error).__name__})",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
