#!/usr/bin/env python3
"""! @brief W01~W10의 열두 exact HIL family를 M32-REG-01로 결합합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


REPOSITORY = Path(__file__).resolve().parents[3]
FAMILY_TEST_IDS = {
    "capability": {"M32-CAP-01"},
    "power_path": {"M32-PWR-01:primary", "M32-PATH-01:primary"},
    "timing_feature": {
        "M32-SUB-01:primary",
        "M32-SCA-01:primary",
        "M32-TIME-01:primary",
        "M32-FEAT-01:primary",
    },
    "advertising": {"M32-ADV-01:primary"},
    "privacy": {"M32-PRIV-01:primary"},
    "ead": {"M32-EAD-01:primary"},
    "nordic_extensions": {
        "M32-NORDIC-01:primary",
        "M32-SYNC-01:primary",
        "M32-EVENT-01:primary",
    },
    "mesh_base": {"M32-MESH-01:traffic", "M32-MESHSEC-01:traffic"},
    "mesh_management": {"M32-MESH11-01:management"},
    "mesh_update": {"M32-BLOB-01:traffic", "M32-MDFU-01:primary"},
    "standalone_radio": {"M32-154-01:primary", "M32-ESB-01:primary"},
    "coexistence": {
        "M32-COEX-01:ble_154",
        "M32-COEX-01:ble_esb",
        "M32-COEX-01:ble_mesh",
    },
}
NEGATIVE_CLASSES = {"cross_link", "security_regression", "cleanup"}


class RegressionClosureFailure(RuntimeError):
    """! @brief W11 manifest·revision·family 증거 불일치를 나타냅니다. """


def _load_json(path: Path, maximum_bytes: int = 1024 * 1024) -> dict:
    """! @brief 크기가 제한된 JSON object를 읽습니다. """
    if not path.is_file() or path.stat().st_size > maximum_bytes:
        raise RegressionClosureFailure(f"JSON evidence 경로 또는 크기 오류: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegressionClosureFailure(f"JSON evidence 읽기 실패: {path}") from error
    if not isinstance(value, dict):
        raise RegressionClosureFailure(f"JSON evidence가 object가 아님: {path}")
    return value


def _test_ids(document: dict) -> set[str]:
    """! @brief 단일·복수 test ID를 문자열 집합으로 정규화합니다. """
    values = document.get("test_ids")
    if values is None:
        values = [document.get("test_id")]
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise RegressionClosureFailure("test_ids 형식 오류")
    return {item for item in values if item}


def _source_revision(document: dict) -> str:
    """! @brief runner별 revision 위치를 읽고 서로 다른 값은 거부합니다. """
    candidates = []
    identity = document.get("identity")
    if isinstance(identity, dict) and isinstance(identity.get("core"), str):
        candidates.append(identity["core"])
    for key in ("source_revision", "core_revision"):
        if isinstance(document.get(key), str):
            candidates.append(document[key])
    if not candidates or any(value != candidates[0] for value in candidates):
        raise RegressionClosureFailure("evidence source revision 누락 또는 충돌")
    if re.fullmatch(r"[0-9a-f]{40}", candidates[0]) is None:
        raise RegressionClosureFailure("evidence source revision 형식 오류")
    return candidates[0]


def _resolve_evidence(manifest: Path, value: str) -> Path:
    """! @brief manifest 상대 evidence 경로를 정규화합니다. """
    path = Path(value)
    if not path.is_absolute():
        path = manifest.parent / path
    return path.resolve()


def validate_manifest(manifest_path: Path, expected_revision: str) -> dict:
    """! @brief 열두 family의 exact PASS·negative·revision을 검증합니다. """
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise RegressionClosureFailure("W11 manifest schema_version 불일치")
    if manifest.get("source_revision") != expected_revision:
        raise RegressionClosureFailure("W11 manifest source revision 불일치")
    if manifest.get("source_clean") is not True:
        raise RegressionClosureFailure("W11 manifest source_clean 누락")
    negative = manifest.get("negative_classes")
    if not isinstance(negative, list) or set(negative) != NEGATIVE_CLASSES:
        raise RegressionClosureFailure("W11 negative class 분모 불일치")
    families = manifest.get("families")
    if not isinstance(families, dict) or set(families) != set(FAMILY_TEST_IDS):
        raise RegressionClosureFailure("W11 열두 family key 불일치")

    records = {}
    used_paths: set[Path] = set()
    for family, required_ids in FAMILY_TEST_IDS.items():
        values = families[family]
        if not isinstance(values, list) or not values or any(
            not isinstance(value, str) for value in values
        ):
            raise RegressionClosureFailure(f"{family} evidence 목록 오류")
        observed_ids: set[str] = set()
        evidence_records = []
        for value in values:
            path = _resolve_evidence(manifest_path, value)
            if path in used_paths:
                raise RegressionClosureFailure(f"evidence 중복 사용: {path.name}")
            used_paths.add(path)
            document = _load_json(path)
            if document.get("status") not in ("PASS", "passed"):
                raise RegressionClosureFailure(f"{family} evidence가 exact PASS가 아님")
            if document.get("source_clean") is not True:
                raise RegressionClosureFailure(f"{family} evidence source_clean 누락")
            if _source_revision(document) != expected_revision:
                raise RegressionClosureFailure(f"{family} evidence revision 불일치")
            ids = _test_ids(document)
            observed_ids.update(ids)
            evidence_records.append(
                {
                    "name": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "test_ids": sorted(ids),
                }
            )
        if not required_ids.issubset(observed_ids):
            missing = sorted(required_ids - observed_ids)
            raise RegressionClosureFailure(f"{family} test ID 누락: {missing}")
        records[family] = {
            "status": "PASS",
            "required_test_ids": sorted(required_ids),
            "evidence": evidence_records,
        }
    return records


def execute(args: argparse.Namespace) -> dict:
    """! @brief clean HEAD와 manifest를 검증하고 M32-REG-01 evidence를 씁니다. """
    head = subprocess.run(
        ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise RegressionClosureFailure("exact closure에는 clean source commit이 필요합니다")
    output = args.output.resolve()
    if output.exists():
        raise RegressionClosureFailure("기존 M32-REG-01 evidence를 덮어쓰지 않습니다")
    records = validate_manifest(args.manifest, head)
    result = {
        "test_ids": ["M32-REG-01:primary"],
        "status": "PASS_CANDIDATE" if dirty else "PASS",
        "scope": "m32_w01_w10_exact_hil_regression_closure",
        "source_revision": head,
        "source_clean": not bool(dirty),
        "baseline_family_denominator": len(FAMILY_TEST_IDS),
        "baseline_family_passed": len(records),
        "allowed_loss_packets": 0,
        "latency_limit_ms": 5000,
        "recovery_timeout_s": 30,
        "negative_classes": sorted(NEGATIVE_CLASSES),
        "families": records,
        "observed_utc": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    """! @brief W11 closure manifest와 출력 경로를 받습니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        print(
            f"M32_REGRESSION_CLOSURE_FAIL: {type(error).__name__}: {str(error)[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_REGRESSION_CLOSURE_STATUS={result['status']};"
        f"FAMILIES={result['baseline_family_passed']}/12"
    )
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
