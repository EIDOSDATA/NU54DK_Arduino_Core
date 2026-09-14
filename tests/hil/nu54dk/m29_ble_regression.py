#!/usr/bin/env python3
"""! @brief 기존 BLE 회귀 네 묶음을 M29-REG-01 증거로 결합합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from m29_ble_regression_protocol import (
    BOARD_TARGET,
    GROUP_ORDER,
    RegressionEvidenceFailure,
    validate_regression_session,
)


REPOSITORY = Path(__file__).resolve().parents[3]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"


def parse_arguments() -> argparse.Namespace:
    """! @brief 네 입력 증거와 신규 aggregate 출력 경로를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M19/M20/M21/M28 증거를 M29-REG-01 strict evidence로 결합합니다."
    )
    for group in GROUP_ORDER:
        parser.add_argument(f"--{group}-evidence", required=True)
    parser.add_argument("--expected-core-revision", required=True)
    parser.add_argument("--expected-board-revision")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--overwrite-evidence", action="store_true")
    return parser.parse_args()


def git_revision(repository: Path) -> str:
    """! @brief 지정 저장소의 full HEAD를 읽습니다. """

    result = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD"),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RegressionEvidenceFailure(f"Git revision을 읽을 수 없습니다: {repository}")
    return result.stdout.strip().lower()


def prepare_output(path_argument: str, overwrite: bool) -> Path:
    """! @brief 신규 JSON 경로와 overwrite 정책을 검사합니다. """

    path = Path(path_argument).resolve()
    if path.suffix.lower() != ".json":
        raise RegressionEvidenceFailure("--evidence는 .json 확장자여야 합니다.")
    if path.exists() and not overwrite:
        raise RegressionEvidenceFailure(f"기존 evidence를 덮어쓰지 않습니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def build_aggregate(
    results: dict,
    core_revision: str,
    board_revision: str,
) -> dict:
    """! @brief 검증 완료 결과를 고정 schema의 aggregate evidence로 만듭니다. """

    board_uids = sorted(
        {uid for result in results.values() for uid in result.board_uids}
    )
    groups = []
    for group in GROUP_ORDER:
        result = results[group]
        groups.append(
            {
                "group": result.group,
                "gate": result.gate,
                "status": "passed",
                "nonce": result.nonce,
                "board_uids": list(result.board_uids),
                "evidence_name": result.evidence_name,
                "evidence_sha256": result.evidence_sha256,
                "transcript_sha256": list(result.transcript_sha256),
            }
        )
    return {
        "schema_version": 1,
        "gate": "m29-ble-regression-hil",
        "test_id": "M29-REG-01",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": BOARD_TARGET,
        "boards": board_uids,
        "groups": groups,
        "criteria": {
            "required_boards": 3,
            "observed_boards": len(board_uids),
            "regression_groups": len(groups),
            "regression_failures": 0,
        },
        "scope": {
            "m19": "GAP advertising/filter/connect/reconnect",
            "m20": "GATT discovery/read/write/notify/indicate/reconnect",
            "m21": "pairing/bond/BAS/DIS/HID protocol",
            "m28": "extended advertising/PAwR/RPA/bonded reconnect",
            "cross_vendor_os_peer": "not_part_of_M29-REG-01",
        },
        "safety": {
            "external_wiring_required": False,
            "mass_erase_requested": False,
            "pmic_write_executed": False,
        },
    }


def main() -> int:
    """! @brief 입력을 검증하고 fail-closed aggregate JSON을 기록합니다. """

    args = parse_arguments()
    try:
        board_revision = (
            args.expected_board_revision.lower()
            if args.expected_board_revision
            else git_revision(BOARD_ROOT)
        )
        core_revision = args.expected_core_revision.lower()
        paths = {
            group: Path(getattr(args, f"{group}_evidence")) for group in GROUP_ORDER
        }
        results = validate_regression_session(paths, core_revision, board_revision)
        output = prepare_output(args.evidence, args.overwrite_evidence)
        aggregate = build_aggregate(results, core_revision, board_revision)
        output.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except RegressionEvidenceFailure as error:
        print(f"M29-REG-01 FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "M29-REG-01 PASS: "
        f"boards={aggregate['criteria']['observed_boards']}, "
        f"groups={aggregate['criteria']['regression_groups']}, evidence={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
