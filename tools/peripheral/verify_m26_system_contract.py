#!/usr/bin/env python3
"""Validate and render the M26 system-peripheral support boundary."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY / "variants" / "nu54dk" / "system-capability-contract.json"
MANIFEST_PATH = REPOSITORY / "variants" / "nu54dk" / "peripheral-manifest.json"
DOCUMENT_PATH = (
    REPOSITORY
    / "00_Docs"
    / "01_아두이노 코어 설계"
    / "11_M26_System_Peripheral_지원_경계.md"
)

EXPECTED_DISPOSITIONS = {
    "comp": "silicon-only",
    "lpcomp": "silicon-only",
    "temp": "partial",
    "wdt30": "partial",
    "wdt31": "supported",
    "nfct": "silicon-only",
    "radio": "partial",
    "cracen": "partial",
    "kmu": "silicon-only",
    "rng": "partial",
    "tampc": "silicon-only",
    "power": "supported",
    "clock": "partial",
    "cache": "not-applicable",
    "vpr": "silicon-only",
    "sqspi": "silicon-only",
}
DISPOSITIONS = {
    "supported", "partial", "silicon-only", "board-unroutable", "not-applicable"
}
SURFACES = {"none", "internal", "public"}
GATES = {"pass", "partial", "not_run", "not_applicable"}
CAPABILITY_KEYS = {
    "id", "disposition", "surface", "board_boundary", "coexistence",
    "automated_gate", "physical_gate", "evidence",
}


class ContractFailure(RuntimeError):
    """Raised when the M26 contract is incomplete or contradictory."""


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractFailure(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractFailure(f"cannot read strict JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractFailure(f"JSON root must be an object: {path}")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise ContractFailure(
            f"{context} keys mismatch; missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}"
        )


def validate_contract(contract: dict[str, Any]) -> list[dict[str, Any]]:
    _exact_keys(
        contract,
        {"schema_version", "product_line", "milestone", "board", "schematic",
         "raw_radio_policy", "capabilities"},
        "contract",
    )
    if contract["schema_version"] != 1:
        raise ContractFailure("unsupported schema_version")
    if contract["product_line"] != "v0.4.0" or contract["milestone"] != "M26":
        raise ContractFailure("product line or milestone drifted")
    manifest = strict_json(MANIFEST_PATH)
    if contract["board"] != manifest["identity"]["board"]:
        raise ContractFailure("board identity differs from peripheral manifest")

    schematic = contract["schematic"]
    if not isinstance(schematic, dict):
        raise ContractFailure("schematic must be an object")
    _exact_keys(schematic, {"path", "sha256"}, "schematic")
    schematic_path = REPOSITORY / schematic["path"]
    if not schematic_path.is_file():
        raise ContractFailure("pinned schematic is missing")
    digest = hashlib.sha256(schematic_path.read_bytes()).hexdigest()
    if digest != schematic["sha256"]:
        raise ContractFailure(f"schematic checksum mismatch: {digest}")
    if contract["raw_radio_policy"] != "exclusive-with-managed-ble-and-not-public-in-v0.4.0":
        raise ContractFailure("raw RADIO ownership policy drifted")

    capabilities = contract["capabilities"]
    if not isinstance(capabilities, list) or len(capabilities) != len(EXPECTED_DISPOSITIONS):
        raise ContractFailure("M26 capability count drifted")
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(capabilities):
        if not isinstance(item, dict):
            raise ContractFailure(f"capabilities[{index}] must be an object")
        _exact_keys(item, CAPABILITY_KEYS, f"capabilities[{index}]")
        identifier = item["id"]
        if not isinstance(identifier, str) or identifier in by_id:
            raise ContractFailure(f"invalid or duplicate capability id: {identifier!r}")
        if item["disposition"] not in DISPOSITIONS or item["disposition"] == "unknown":
            raise ContractFailure(f"{identifier} has invalid disposition")
        if item["surface"] not in SURFACES:
            raise ContractFailure(f"{identifier} has invalid surface")
        if item["automated_gate"] not in GATES or item["physical_gate"] not in GATES:
            raise ContractFailure(f"{identifier} has invalid gate state")
        for field in ("board_boundary", "coexistence"):
            if not isinstance(item[field], str) or len(item[field].strip()) < 12:
                raise ContractFailure(f"{identifier}.{field} lacks a concrete boundary")
        evidence = item["evidence"]
        if (not isinstance(evidence, list) or not evidence or
                len(evidence) != len(set(evidence))):
            raise ContractFailure(f"{identifier} evidence is missing or duplicated")
        for relative in evidence:
            path = (REPOSITORY / relative).resolve()
            if not path.is_relative_to(REPOSITORY.resolve()) or not path.is_file():
                raise ContractFailure(f"{identifier} evidence does not exist: {relative}")
        if item["disposition"] in {"silicon-only", "board-unroutable"} and item["surface"] != "none":
            raise ContractFailure(f"{identifier} exposes a silicon/board-only capability")
        if item["disposition"] == "supported" and (
            item["automated_gate"] != "pass" or item["physical_gate"] != "pass"
        ):
            raise ContractFailure(f"{identifier} supported disposition lacks PASS gates")
        by_id[identifier] = item

    observed = {identifier: item["disposition"] for identifier, item in by_id.items()}
    if observed != EXPECTED_DISPOSITIONS:
        raise ContractFailure(f"M26 disposition map drifted: {observed}")

    m26 = {
        item["id"]: item for item in manifest["instances"]
        if item["milestone"] == "M26"
    }
    if set(m26) != set(by_id):
        raise ContractFailure("M26 ledger and peripheral manifest identity sets differ")
    for identifier, item in by_id.items():
        states = m26[identifier]["states"]
        if item["surface"] != states["exposure"]:
            raise ContractFailure(f"{identifier} surface differs from manifest exposure")
        if item["disposition"] in {"supported", "partial"} and states["source"] == "absent":
            raise ContractFailure(f"{identifier} disposition has no integration source")
        if item["automated_gate"] == "pass" and states["silicon"] != "pass":
            raise ContractFailure(f"{identifier} automated classification lacks silicon PASS")
        if item["physical_gate"] == "pass" and states["hil"] != "pass":
            raise ContractFailure(f"{identifier} physical PASS differs from manifest HIL")

    source = (REPOSITORY / "cores" / "arduino" / "SystemFabric.cpp").read_text(encoding="utf-8")
    header = (REPOSITORY / "cores" / "arduino" / "nucode" / "SystemFabric.h").read_text(encoding="utf-8")
    for token in (
        "readCentiCelsius",
        "DEVICE_DT_GET(DT_NODELABEL(temp))",
        "WatchdogFabric(30U)",
        "WatchdogFabric(31U)",
    ):
        if token not in source and token not in header:
            raise ContractFailure(f"M26 SystemFabric source is missing {token}")
    return capabilities


def render_document(contract: dict[str, Any], capabilities: list[dict[str, Any]]) -> str:
    counts = Counter(item["disposition"] for item in capabilities)
    lines = [
        "# M26 System Peripheral 지원 경계",
        "",
        "> 이 파일은 `variants/nu54dk/system-capability-contract.json`에서 자동 생성합니다. 직접 수정하지 마세요.",
        "",
        "| 항목 | 값 |", "| --- | --- |",
        f"| 제품선 / 마일스톤 | `{contract['product_line']}` / `{contract['milestone']}` |",
        f"| Board | `{contract['board']}` |",
        f"| 전체 판정 | {len(capabilities)}개, unknown 0개 |",
        "| 상태 합계 | " + ", ".join(f"`{key}` {counts[key]}" for key in sorted(counts)) + " |",
        f"| raw RADIO 정책 | `{contract['raw_radio_policy']}` |",
        "", "## 상태 의미", "",
        "- `supported`: 공개 surface와 자동·물리 PASS가 모두 있다.",
        "- `partial`: Core/upstream 통합 경로가 있지만 API 또는 물리 검증 범위가 완전하지 않다.",
        "- `silicon-only`: silicon에는 있으나 v0.4.0 Arduino 제품 surface로 노출하지 않는다.",
        "- `board-unroutable`: silicon 기능을 현재 NU54DK 회로에서 사용할 수 없다.",
        "- `not-applicable`: 사용자 기능이 아니라 Core/driver 내부 책임으로 유지한다.",
        "", "## 판정표", "",
        "| Identity | 판정 | surface | 자동 gate | 물리 gate | 보드 경계 | 공존·소유권 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in capabilities:
        lines.append(
            f"| `{item['id']}` | `{item['disposition']}` | `{item['surface']}` | "
            f"`{item['automated_gate']}` | `{item['physical_gate']}` | "
            f"{item['board_boundary']} | {item['coexistence']} |"
        )
    lines.extend([
        "", "## M27 전 남은 물리 gate", "",
        "TEMP와 WDT30 후보 API의 온보드 실행, comparator threshold, NFC antenna/reader, sQSPI 외부 memory, "
        "raw RF 계측은 build나 문서 판정으로 대체하지 않는다. M27은 이 항목을 `NOT RUN`으로 보존하고 "
        "stable 공개를 HOLD한다.",
        "", "## 단일 원본과 검사", "",
        "- Contract: [`variants/nu54dk/system-capability-contract.json`](../../variants/nu54dk/system-capability-contract.json)",
        "- Verifier: [`tools/peripheral/verify_m26_system_contract.py`](../../tools/peripheral/verify_m26_system_contract.py)",
        "- Peripheral manifest: [`variants/nu54dk/peripheral-manifest.json`](../../variants/nu54dk/peripheral-manifest.json)",
        "",
    ])
    return "\n".join(lines)


def run(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(arguments)
    contract = strict_json(CONTRACT_PATH)
    capabilities = validate_contract(contract)
    expected = render_document(contract, capabilities)
    if args.write:
        DOCUMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOCUMENT_PATH.write_text(expected, encoding="utf-8", newline="\n")
        print(f"M26_GENERATED={DOCUMENT_PATH.relative_to(REPOSITORY).as_posix()}")
    elif not DOCUMENT_PATH.is_file() or DOCUMENT_PATH.read_text(encoding="utf-8") != expected:
        raise ContractFailure(
            "generated M26 document drifted; run "
            "python tools/peripheral/verify_m26_system_contract.py --write"
        )
    print(f"M26_SYSTEM_CONTRACT_PASS=capabilities:{len(capabilities)};unknown:0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except ContractFailure as error:
        print(f"M26_SYSTEM_CONTRACT_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
