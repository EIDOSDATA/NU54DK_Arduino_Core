#!/usr/bin/env python3
"""! @brief M17 NCS v3.4.0 coverage 원장을 엄격하게 검증하고 요약을 생성합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable


SCHEMA_VERSION = 1
DATASET_NAME = "ncs-v3.4.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")

MANIFEST_FIELDS = {"schema_version", "dataset", "description", "pins", "records"}
PIN_FIELDS = {"repository", "revision"}
MANIFEST_RECORD_FIELDS = {"id", "path", "sha256"}
RECORD_FIELDS = {
    "schema_version",
    "id",
    "title",
    "area",
    "route",
    "status",
    "profile",
    "hardware",
    "source",
    "validation",
    "notes",
}
SOURCE_FIELDS = {"type", "repository", "revision", "path", "license"}
VALIDATION_FIELDS = {"kind", "state", "evidence"}

PIN_NAMES = {"ncs", "zephyr", "board"}
AREAS = {"board-system", "ble", "settings-storage", "crypto-random", "sensor", "radio-networking"}
ROUTES = {"arduino-wrapper", "ncs-direct-example", "build-profile-only", "excluded-deferred"}
STATUSES = {"supported", "build-only", "deferred"}
PROFILES = {"none", "standard", "ble", "radio"}
HARDWARE = {"none", "nu54dk", "external-optional"}
SOURCE_TYPES = {"ncs", "zephyr", "board", "external"}
VALIDATION_KINDS = {
    "host-contract",
    "hil",
    "arduino-library-compile",
    "ncs-direct-build",
    "build-feasibility",
}
VALIDATION_STATES = {"pass", "fail", "planned", "not-run"}
EVIDENCED_VALIDATION_STATES = {"pass", "fail"}
BLOCKING_FAILURE_STATUSES = {"supported", "build-only"}

REQUIRED_RECORDS = {
    "board.system",
    "nrf.ble-nus",
    "zephyr.settings-storage",
    "nrf.crypto-rng",
    "arduino.adafruit-lsm6ds",
    "zephyr.sensor-direct",
    "nrf.802154-phy-test",
    "nrf.openthread-cli",
    "nrf.matter-template",
}
DEFERRED_NETWORK_RECORDS = {
    "nrf.802154-phy-test",
    "nrf.openthread-cli",
    "nrf.matter-template",
}


class CoverageError(RuntimeError):
    """! @brief Coverage 원장 계약 위반입니다. """


## @brief JSON object의 중복 key를 즉시 거부합니다.
def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise CoverageError(f"중복 JSON key를 허용하지 않습니다: {key}")
        document[key] = value
    return document


## @brief UTF-8 JSON을 중복 key 없이 object로 읽습니다.
def strict_load_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CoverageError(f"JSON을 UTF-8로 읽지 못했습니다: {path}: {error}") from error
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except CoverageError:
        raise
    except json.JSONDecodeError as error:
        raise CoverageError(f"유효하지 않은 JSON입니다: {path}: {error}") from error
    if not isinstance(value, dict):
        raise CoverageError(f"JSON 최상위 값은 object여야 합니다: {path}")
    return value


## @brief 선언된 field 집합과 실제 field 집합이 정확히 같은지 확인합니다.
def _require_exact_fields(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise CoverageError(f"{context} field 계약이 다릅니다: missing={missing}, unknown={unknown}")


## @brief enum 값이 허용 목록에 포함되는지 확인합니다.
def _require_enum(value: Any, allowed: set[str], context: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise CoverageError(f"{context} 값이 허용 목록에 없습니다: {value!r}")
    return value


## @brief 비어 있지 않은 문자열을 확인합니다.
def _require_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CoverageError(f"{context}는 앞뒤 공백 없는 비어 있지 않은 문자열이어야 합니다.")
    if any(ord(character) < 0x20 for character in value):
        raise CoverageError(f"{context}에 제어 문자를 허용하지 않습니다.")
    return value


## @brief 경로 탈출, 절대 경로와 Windows 구분자를 거부합니다.
def _safe_relative_path(value: Any, context: str) -> str:
    path_text = _require_string(value, context)
    if "\\" in path_text:
        raise CoverageError(f"{context}는 forward slash만 사용해야 합니다: {path_text}")
    if re.match(r"^[A-Za-z]:", path_text) or path_text.startswith("//"):
        raise CoverageError(f"{context}에 Windows drive 또는 UNC 경로를 허용하지 않습니다: {path_text}")
    raw_parts = path_text.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise CoverageError(f"{context}에 안전하지 않은 상대 경로가 있습니다: {path_text}")
    candidate = PurePosixPath(path_text)
    if (
        candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or any(":" in part for part in candidate.parts)
    ):
        raise CoverageError(f"{context}에 안전하지 않은 상대 경로가 있습니다: {path_text}")
    return candidate.as_posix()


## @brief 상대 경로의 실제 resolve 결과가 지정 root 안에 있는지 검증합니다.
def _resolve_contained(root: Path, relative_path: str, context: str) -> Path:
    root = root.resolve()
    target = (root / PurePosixPath(relative_path)).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise CoverageError(f"{context}의 실제 경로가 허용 root 밖입니다: {relative_path}") from error
    if target == root:
        raise CoverageError(f"{context}가 허용 root 자체를 가리킬 수 없습니다.")
    return target


## @brief Git text checkout과 무관하도록 CRLF를 LF로 정규화합니다.
def _normalize_lf_bytes(content: bytes, context: str) -> bytes:
    canonical = content.replace(b"\r\n", b"\n")
    if b"\r" in canonical:
        raise CoverageError(f"{context}에 단독 CR 줄바꿈을 허용하지 않습니다.")
    return canonical


## @brief Git text checkout과 무관한 LF 기준 record SHA-256을 계산합니다.
def _record_sha256(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise CoverageError(f"record 파일을 읽지 못했습니다: {path}: {error}") from error
    canonical = _normalize_lf_bytes(content, f"record 파일 {path}")
    return hashlib.sha256(canonical).hexdigest()


## @brief lock file에서 M17이 사용하는 exact pin만 추출합니다.
def _load_expected_pins(repo_root: Path) -> dict[str, dict[str, str]]:
    lock_path = repo_root / "tools" / "ci" / "ncs-3.4.0.lock.json"
    lock = strict_load_json(lock_path)
    try:
        pins = {
            "ncs": {
                "repository": lock["ncs"]["repository"],
                "revision": lock["ncs"]["revision"],
            },
            "zephyr": {
                "repository": lock["zephyr"]["repository"],
                "revision": lock["zephyr"]["revision"],
            },
            "board": {
                "repository": lock["board"]["repository"],
                "revision": lock["board"]["revision"],
            },
        }
    except (KeyError, TypeError) as error:
        raise CoverageError("NCS lock file에 필수 revision 정보가 없습니다.") from error
    for name, pin in pins.items():
        if not isinstance(pin["repository"], str) or not REVISION_RE.fullmatch(str(pin["revision"])):
            raise CoverageError(f"NCS lock의 {name} pin이 유효하지 않습니다.")
    return pins


## @brief board submodule checkout이 lock의 exact commit인지 확인합니다.
def _verify_board_checkout(repo_root: Path, expected_revision: str) -> None:
    board_root = repo_root / "board_package" / "NU54DK_Zephyr_DTS"
    try:
        revision_result = subprocess.run(
            ["git", "-C", str(board_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        status_result = subprocess.run(
            ["git", "-C", str(board_root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise CoverageError("board submodule revision을 확인하지 못했습니다.") from error
    actual = revision_result.stdout.strip().lower()
    if actual != expected_revision:
        raise CoverageError(
            f"board submodule revision mismatch: expected={expected_revision}, actual={actual}"
        )
    if status_result.stdout.strip():
        raise CoverageError("board submodule에 미커밋 변경이 있어 exact revision으로 인정할 수 없습니다.")


## @brief record의 source와 고정 revision 계약을 검증합니다.
def _validate_source(source: Any, pins: dict[str, dict[str, str]], record_id: str) -> None:
    if not isinstance(source, dict):
        raise CoverageError(f"{record_id}.source는 object여야 합니다.")
    _require_exact_fields(source, SOURCE_FIELDS, f"{record_id}.source")
    source_type = _require_enum(source["type"], SOURCE_TYPES, f"{record_id}.source.type")
    repository = _require_string(source["repository"], f"{record_id}.source.repository")
    revision = _require_string(source["revision"], f"{record_id}.source.revision")
    _safe_relative_path(source["path"], f"{record_id}.source.path")
    _require_string(source["license"], f"{record_id}.source.license")
    if not revision == revision.lower() or not REVISION_RE.fullmatch(revision):
        raise CoverageError(f"{record_id}.source.revision은 lowercase 40자리 commit이어야 합니다.")
    if source_type in pins:
        expected = pins[source_type]
        if repository != expected["repository"] or revision != expected["revision"]:
            raise CoverageError(f"{record_id}.source가 {source_type} exact pin과 다릅니다.")
    elif not repository.startswith("https://"):
        raise CoverageError(f"{record_id}.source external repository는 HTTPS URL이어야 합니다.")


## @brief record validation evidence의 형식과 상태를 검증합니다.
def _validate_validation(value: Any, record_id: str) -> None:
    if not isinstance(value, dict):
        raise CoverageError(f"{record_id}.validation은 object여야 합니다.")
    _require_exact_fields(value, VALIDATION_FIELDS, f"{record_id}.validation")
    _require_enum(value["kind"], VALIDATION_KINDS, f"{record_id}.validation.kind")
    state = _require_enum(value["state"], VALIDATION_STATES, f"{record_id}.validation.state")
    evidence = value["evidence"]
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise CoverageError(f"{record_id}.validation.evidence는 경로 문자열 배열이어야 합니다.")
    normalized = [_safe_relative_path(item, f"{record_id}.validation.evidence") for item in evidence]
    if normalized != sorted(set(normalized)):
        raise CoverageError(f"{record_id}.validation.evidence는 중복 없이 정렬해야 합니다.")
    if state in EVIDENCED_VALIDATION_STATES and not normalized:
        raise CoverageError(
            f"{record_id} {state.upper()}에는 최소 한 개의 evidence 경로가 필요합니다."
        )
    if state not in EVIDENCED_VALIDATION_STATES and normalized:
        raise CoverageError(
            f"{record_id}의 {state} validation에는 evidence를 연결할 수 없습니다."
        )


## @brief 한 coverage record의 strict schema와 정책 불변식을 검증합니다.
def _validate_record(record: dict[str, Any], expected_id: str, pins: dict[str, dict[str, str]]) -> None:
    _require_exact_fields(record, RECORD_FIELDS, f"record {expected_id}")
    if record["schema_version"] != SCHEMA_VERSION or isinstance(record["schema_version"], bool):
        raise CoverageError(f"{expected_id} schema_version이 지원 범위와 다릅니다.")
    record_id = _require_string(record["id"], f"{expected_id}.id")
    if record_id != expected_id or not ID_RE.fullmatch(record_id):
        raise CoverageError(f"record id와 manifest id가 다르거나 형식이 잘못되었습니다: {record_id}")
    _require_string(record["title"], f"{record_id}.title")
    area = _require_enum(record["area"], AREAS, f"{record_id}.area")
    route = _require_enum(record["route"], ROUTES, f"{record_id}.route")
    status = _require_enum(record["status"], STATUSES, f"{record_id}.status")
    _require_enum(record["profile"], PROFILES, f"{record_id}.profile")
    _require_enum(record["hardware"], HARDWARE, f"{record_id}.hardware")
    _validate_source(record["source"], pins, record_id)
    _validate_validation(record["validation"], record_id)
    notes = record["notes"]
    if not isinstance(notes, list) or not notes:
        raise CoverageError(f"{record_id}.notes는 하나 이상의 문자열을 가져야 합니다.")
    normalized_notes = [_require_string(item, f"{record_id}.notes") for item in notes]
    if normalized_notes != sorted(set(normalized_notes)):
        raise CoverageError(f"{record_id}.notes는 중복 없이 정렬해야 합니다.")
    if area == "sensor" and route == "arduino-wrapper":
        raise CoverageError(f"{record_id}: M17에서는 sensor wrapper를 제공할 수 없습니다.")
    if area == "radio-networking" and (
        status != "deferred"
        or route != "excluded-deferred"
        or record["validation"]["kind"] != "build-feasibility"
    ):
        raise CoverageError(f"{record_id}: v0.2 radio networking은 feasibility+deferred만 허용합니다.")
    validation_state = record["validation"]["state"]
    if validation_state == "fail" and status in BLOCKING_FAILURE_STATUSES:
        raise CoverageError(f"{record_id} {status} validation FAIL은 coverage gate 실패입니다.")
    if status == "supported" and validation_state != "pass":
        raise CoverageError(f"{record_id} supported 선언에는 PASS evidence가 필요합니다.")


## @brief manifest schema, record hash와 전체 M17 정책을 fail-closed로 검증합니다.
def validate_dataset(
    repo_root: Path,
    dataset_root: Path | None = None,
    *,
    verify_board_checkout: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repo_root = repo_root.resolve()
    explicit_dataset_root = dataset_root is not None
    dataset_root = (dataset_root or repo_root / "coverage" / DATASET_NAME).resolve()
    if not explicit_dataset_root:
        try:
            dataset_root.relative_to(repo_root)
        except ValueError as error:
            raise CoverageError("coverage dataset의 실제 경로가 저장소 밖입니다.") from error
    manifest_path = dataset_root / "manifest.json"
    manifest = strict_load_json(manifest_path)
    _require_exact_fields(manifest, MANIFEST_FIELDS, "manifest")
    if manifest["schema_version"] != SCHEMA_VERSION or isinstance(manifest["schema_version"], bool):
        raise CoverageError("manifest schema_version이 지원 범위와 다릅니다.")
    if manifest["dataset"] != DATASET_NAME:
        raise CoverageError(f"dataset 이름이 고정 계약과 다릅니다: {manifest['dataset']!r}")
    _require_string(manifest["description"], "manifest.description")

    pins = manifest["pins"]
    if not isinstance(pins, dict):
        raise CoverageError("manifest.pins는 object여야 합니다.")
    _require_exact_fields(pins, PIN_NAMES, "manifest.pins")
    expected_pins = _load_expected_pins(repo_root)
    for name in sorted(PIN_NAMES):
        pin = pins[name]
        if not isinstance(pin, dict):
            raise CoverageError(f"manifest.pins.{name}은 object여야 합니다.")
        _require_exact_fields(pin, PIN_FIELDS, f"manifest.pins.{name}")
        if pin != expected_pins[name]:
            raise CoverageError(f"manifest {name} revision/repository가 NCS lock과 다릅니다.")
    if verify_board_checkout:
        _verify_board_checkout(repo_root, expected_pins["board"]["revision"])

    entries = manifest["records"]
    if not isinstance(entries, list) or not entries:
        raise CoverageError("manifest.records는 비어 있지 않은 배열이어야 합니다.")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    normalized_entries: list[tuple[str, str]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CoverageError(f"manifest.records[{index}]는 object여야 합니다.")
        _require_exact_fields(entry, MANIFEST_RECORD_FIELDS, f"manifest.records[{index}]")
        record_id = _require_string(entry["id"], f"manifest.records[{index}].id")
        if not ID_RE.fullmatch(record_id) or record_id in seen_ids:
            raise CoverageError(f"record id가 중복되었거나 형식이 잘못되었습니다: {record_id}")
        seen_ids.add(record_id)
        relative_path = _safe_relative_path(entry["path"], f"manifest.records[{index}].path")
        expected_path = f"records/{record_id}.json"
        if relative_path != expected_path:
            raise CoverageError(f"record path는 id에서 정확히 유도해야 합니다: {relative_path}")
        declared_hash = _require_string(entry["sha256"], f"manifest.records[{index}].sha256")
        if not SHA256_RE.fullmatch(declared_hash):
            raise CoverageError(f"record SHA-256 형식이 잘못되었습니다: {record_id}")
        record_path = _resolve_contained(
            dataset_root, relative_path, f"manifest.records[{index}].path"
        )
        if not record_path.is_file():
            raise CoverageError(f"record 파일이 없습니다: {relative_path}")
        actual_hash = _record_sha256(record_path)
        if actual_hash != declared_hash:
            raise CoverageError(
                f"record SHA-256 mismatch: {record_id}: expected={declared_hash}, actual={actual_hash}"
            )
        record = strict_load_json(record_path)
        _validate_record(record, record_id, expected_pins)
        for evidence_path in record["validation"]["evidence"]:
            resolved_evidence = _resolve_contained(
                repo_root, evidence_path, f"{record_id}.validation.evidence"
            )
            if not resolved_evidence.is_file():
                raise CoverageError(f"{record_id} evidence 파일이 없습니다: {evidence_path}")
        records.append(record)
        normalized_entries.append((record_id, relative_path))
    if normalized_entries != sorted(normalized_entries):
        raise CoverageError("manifest.records는 id/path 순서로 정렬해야 합니다.")
    missing = sorted(REQUIRED_RECORDS - seen_ids)
    if missing:
        raise CoverageError(f"M17 필수 coverage record가 없습니다: {missing}")
    for record in records:
        if record["id"] in DEFERRED_NETWORK_RECORDS and record["status"] != "deferred":
            raise CoverageError(f"{record['id']}는 v0.2 supported로 승격할 수 없습니다.")
    return manifest, records


## @brief deterministic JSON 요약 object를 만듭니다.
def build_summary(manifest: dict[str, Any], records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: item["id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset": manifest["dataset"],
        "pins": manifest["pins"],
        "counts": {
            "area": dict(sorted(Counter(item["area"] for item in ordered).items())),
            "status": dict(sorted(Counter(item["status"] for item in ordered).items())),
            "validation_state": dict(
                sorted(Counter(item["validation"]["state"] for item in ordered).items())
            ),
            "total": len(ordered),
        },
        "records": [
            {
                "id": item["id"],
                "title": item["title"],
                "area": item["area"],
                "route": item["route"],
                "status": item["status"],
                "profile": item["profile"],
                "hardware": item["hardware"],
                "source_type": item["source"]["type"],
                "source_revision": item["source"]["revision"],
                "validation_kind": item["validation"]["kind"],
                "validation_state": item["validation"]["state"],
            }
            for item in ordered
        ],
    }


## @brief Markdown table cell의 구분 문자를 안전하게 표시합니다.
def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


## @brief 사람이 검토할 deterministic Markdown 요약을 만듭니다.
def render_markdown(summary: dict[str, Any]) -> str:
    pins = summary["pins"]
    counts = summary["counts"]
    lines = [
        "# NCS v3.4.0 coverage 요약",
        "",
        "> 이 파일은 `tools/coverage/m17_coverage.py render`로 생성합니다. 직접 수정하지 마십시오.",
        "",
        "## Exact revision",
        "",
        "| 구성 | revision |",
        "| --- | --- |",
    ]
    for name in ("ncs", "zephyr", "board"):
        lines.append(f"| {name} | `{pins[name]['revision']}` |")
    lines.extend(
        [
            "",
            "## 집계",
            "",
            f"- 전체 record: {counts['total']}",
            "- 상태: " + ", ".join(f"{key}={value}" for key, value in counts["status"].items()),
            "- 검증: "
            + ", ".join(f"{key}={value}" for key, value in counts["validation_state"].items()),
            "",
            "## Record",
            "",
            "| ID | 영역 | 제공 경로 | 상태 | 검증 | profile |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in summary["records"]:
        validation = f"{record['validation_kind']}:{record['validation_state']}"
        if record["validation_state"] == "fail":
            validation = f"**{validation}**"
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    f"`{record['id']}`",
                    record["area"],
                    record["route"],
                    record["status"],
                    validation,
                    record["profile"],
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Thread/Matter/802.15.4는 v0.2.0에서 build feasibility만 추적하며 정식 지원이 아닙니다.",
            "Sensor 항목은 direct/build example 또는 외부 library compile만 추적하며 bundled wrapper를 제공하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


## @brief 생성 파일 byte를 만들고 write 또는 check를 수행합니다.
def render_outputs(repo_root: Path, *, check: bool = False) -> None:
    dataset_root = repo_root / "coverage" / DATASET_NAME
    manifest, records = validate_dataset(repo_root, dataset_root)
    summary = build_summary(manifest, records)
    outputs = {
        dataset_root / "generated" / "summary.json": (
            json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8"),
        dataset_root / "generated" / "summary.md": render_markdown(summary).encode("utf-8"),
    }
    for path, expected in outputs.items():
        if check:
            try:
                actual = path.read_bytes()
            except OSError as error:
                raise CoverageError(f"생성 파일을 읽지 못했습니다: {path}: {error}") from error
            actual = _normalize_lf_bytes(actual, f"생성 파일 {path}")
            if actual != expected:
                raise CoverageError(f"생성 파일이 stale 상태입니다: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)


## @brief CLI 인자를 해석하고 fail-closed 검증 또는 render를 실행합니다.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M17 NCS v3.4.0 coverage 원장 도구")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="NU54DK Arduino Core 저장소 root",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="manifest, record와 pin을 엄격하게 검증")
    render_parser = subparsers.add_parser("render", help="재현 가능한 JSON/Markdown 요약 생성")
    render_parser.add_argument("--check", action="store_true", help="생성 파일을 쓰지 않고 byte 비교")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            _, records = validate_dataset(args.repo_root)
            print(f"M17 coverage PASS: records={len(records)}")
        else:
            render_outputs(args.repo_root.resolve(), check=args.check)
            print(f"M17 coverage render {'CHECK PASS' if args.check else 'PASS'}")
    except CoverageError as error:
        print(f"M17 coverage FAIL: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
