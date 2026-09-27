#!/usr/bin/env python3
"""! @brief 예제 metadata와 공개 `.ino` 설정 안내를 동기화합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
METADATA_PATH = ROOT / "libraries" / "example-metadata.json"
BEGIN_MARKER = "/** @nucode_example_setup_begin"
END_MARKER = " * @nucode_example_setup_end */"
ALLOWED_PROFILES = {
    "standard",
    "ble",
    "adaptive",
    "fabric",
    "secure_ble_dfu",
    "ble_audio_io",
}
PROFILE_LABELS = {
    "standard": "Standard peripherals",
    "ble": "BLE NUS",
    "adaptive": "Adaptive capabilities (experimental)",
    "fabric": "Peripheral Fabric (DAP UART disconnected)",
    "secure_ble_dfu": "Secure BLE DFU (MCUboot)",
    "ble_audio_io": "BLE Audio external I/O (DAP UART disconnected)",
}
SIDECAR_NAMES = {
    "nucode-build.json",
    "prj.conf",
    "app.overlay",
    "sysbuild.conf",
    "sysbuild.cmake",
}


class ExampleGuidanceError(RuntimeError):
    """! @brief 예제 metadata 또는 생성 안내의 계약 위반입니다. """


def load_metadata(path: Path = METADATA_PATH) -> dict[str, Any]:
    """! @brief 중복 key를 포함하지 않는 UTF-8 metadata를 읽습니다. """

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ExampleGuidanceError(f"중복 metadata key입니다: {key}")
            document[key] = value
        return document

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExampleGuidanceError(f"예제 metadata를 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ExampleGuidanceError("예제 metadata schema_version이 1이 아닙니다.")
    return document


def public_examples(root: Path = ROOT) -> dict[str, Path]:
    """! @brief 설치 대상 공개 예제를 identity별로 열거합니다. """

    result: dict[str, Path] = {}
    for library in sorted((root / "libraries").iterdir(), key=lambda item: item.name.casefold()):
        if not library.is_dir() or not (library / "library.properties").is_file():
            continue
        example_root = library / "examples"
        if not example_root.is_dir():
            continue
        for example in sorted(example_root.iterdir(), key=lambda item: item.name.casefold()):
            sketch = example / f"{example.name}.ino"
            if not example.is_dir() or not sketch.is_file():
                continue
            identity = f"{library.name}/{example.name}"
            if identity in result:
                raise ExampleGuidanceError(f"중복 공개 예제 identity입니다: {identity}")
            result[identity] = sketch
    return result


def metadata_digest(identity: str, record: dict[str, Any]) -> str:
    """! @brief 사용자 안내에 결합할 identity metadata SHA-256을 계산합니다. """

    canonical = json.dumps(
        {"identity": identity, **record}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_metadata(
    document: dict[str, Any], examples: dict[str, Path], root: Path = ROOT
) -> list[str]:
    """! @brief metadata 분모·profile·sidecar·역할 계약을 전수 검증합니다. """

    issues: list[str] = []
    records = document.get("examples")
    if not isinstance(records, dict):
        return ["metadata examples가 object가 아닙니다"]
    if set(records) != set(examples):
        for identity in sorted(set(examples).difference(records), key=str.casefold):
            issues.append(f"metadata 누락: {identity}")
        for identity in sorted(set(records).difference(examples), key=str.casefold):
            issues.append(f"존재하지 않는 metadata: {identity}")
    if document.get("example_count") != len(examples):
        issues.append(
            f"example_count 불일치: {document.get('example_count')} != {len(examples)}"
        )
    for identity, sketch in examples.items():
        record = records.get(identity)
        if not isinstance(record, dict):
            continue
        recommended = record.get("recommended_profile")
        if recommended not in ALLOWED_PROFILES:
            issues.append(f"권장 profile 오류: {identity}: {recommended}")
        alternatives = record.get("alternative_profiles")
        if not isinstance(alternatives, list):
            issues.append(f"대안 profile 배열 누락: {identity}")
        else:
            seen: set[str] = set()
            for alternative in alternatives:
                if not isinstance(alternative, dict):
                    issues.append(f"대안 profile 형식 오류: {identity}")
                    continue
                profile = alternative.get("profile")
                classification = alternative.get("classification")
                if (
                    profile not in ALLOWED_PROFILES
                    or profile == recommended
                    or profile in seen
                    or classification not in {"compatible", "experimental", "dedicated"}
                ):
                    issues.append(f"대안 profile 계약 오류: {identity}: {alternative}")
                if isinstance(profile, str):
                    seen.add(profile)
        board_count = record.get("board_count")
        roles = record.get("roles")
        if (
            not isinstance(board_count, int)
            or board_count < 1
            or not isinstance(roles, list)
            or len(roles) != board_count
            or any(not isinstance(role, str) or not role.strip() for role in roles)
        ):
            issues.append(f"보드 수·역할 오류: {identity}")
        baud = record.get("serial_baud")
        if baud is not None and (not isinstance(baud, int) or baud <= 0):
            issues.append(f"Serial baud 오류: {identity}: {baud}")
        sidecars = record.get("sidecars")
        if (
            not isinstance(sidecars, list)
            or len(sidecars) != len(set(sidecars))
            or any(not isinstance(name, str) or name not in SIDECAR_NAMES for name in sidecars)
        ):
            issues.append(f"sidecar 목록 오류: {identity}")
            continue
        actual_sidecars = sorted(
            path.name for path in sketch.parent.iterdir()
            if path.is_file() and path.name in SIDECAR_NAMES
        )
        if sorted(sidecars) != actual_sidecars:
            issues.append(
                f"sidecar 불일치: {identity}: metadata={sorted(sidecars)} actual={actual_sidecars}"
            )
        conditions = record.get("conditions")
        if not isinstance(conditions, list) or any(
            not isinstance(condition, str) or not condition.strip() for condition in conditions
        ):
            issues.append(f"추가 조건 배열 오류: {identity}")
        expected_path = sketch.relative_to(root).as_posix()
        if record.get("path") != expected_path:
            issues.append(f"예제 경로 불일치: {identity}: {record.get('path')} != {expected_path}")
    return issues


def render_guidance(identity: str, record: dict[str, Any]) -> str:
    """! @brief metadata 한 건을 Arduino IDE에서 읽을 Doxygen 안내로 렌더링합니다. """

    recommended = str(record["recommended_profile"])
    alternatives = record["alternative_profiles"]
    alternative_text = "없음"
    if alternatives:
        rendered = []
        labels = {
            "compatible": "호환",
            "experimental": "실험적 대안",
            "dedicated": "전용 구성",
        }
        for alternative in alternatives:
            profile = str(alternative["profile"])
            rendered.append(
                f"{PROFILE_LABELS[profile]} ({profile}, {labels[str(alternative['classification'])]})"
            )
        alternative_text = "; ".join(rendered)
    roles = "; ".join(
        f"{index + 1}) {role}" for index, role in enumerate(record["roles"])
    )
    baud = (
        f"{record['serial_baud']} baud"
        if record["serial_baud"] is not None
        else "사용하지 않음"
    )
    sidecars = ", ".join(record["sidecars"]) if record["sidecars"] else "없음"
    conditions = "; ".join(record["conditions"]) if record["conditions"] else "추가 조건 없음"
    digest = metadata_digest(identity, record)
    lines = [
        BEGIN_MARKER,
        " * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.",
        " * @par Board",
        " * NU54DK (nRF54L15, Zephyr)",
        " * @par Feature set",
        f" * 기본 권장: {PROFILE_LABELS[recommended]} (`{recommended}`)",
        f" * 호환 대안: {alternative_text}",
        " * @par 보드와 역할",
        f" * {record['board_count']}대 — {roles}",
        " * @par Serial Monitor",
        f" * {baud}",
        " * @par 필수 sidecar",
        f" * {sidecars}",
        " * @par Upload probe",
        " * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.",
        " * @par 추가 조건",
        f" * {conditions}",
        " * @par Metadata",
        f" * identity `{identity}`, sha256 `{digest}`",
        END_MARKER,
    ]
    return "\n".join(lines) + "\n\n"


def replace_guidance(text: str, rendered: str) -> str:
    """! @brief 기존 생성 블록 하나를 교체하거나 파일 맨 앞에 추가합니다. """

    pattern = re.compile(
        rf"\A{re.escape(BEGIN_MARKER)}.*?{re.escape(END_MARKER)}\r?\n(?:\r?\n)?",
        flags=re.DOTALL,
    )
    if pattern.match(text):
        return pattern.sub(rendered, text, count=1)
    if BEGIN_MARKER in text or END_MARKER in text:
        raise ExampleGuidanceError("예제 설정 안내 marker가 파일 시작에서 완전한 한 쌍이 아닙니다.")
    return rendered + text


def synchronize(*, write: bool, root: Path = ROOT) -> list[str]:
    """! @brief 전 예제 안내를 검사하거나 metadata와 byte 일치하도록 갱신합니다. """

    document = load_metadata(root / "libraries" / "example-metadata.json")
    examples = public_examples(root)
    issues = validate_metadata(document, examples, root)
    if issues:
        return issues
    records = document["examples"]
    for identity, sketch in examples.items():
        original = sketch.read_text(encoding="utf-8")
        expected = replace_guidance(original, render_guidance(identity, records[identity]))
        if expected == original:
            continue
        if write:
            sketch.write_text(expected, encoding="utf-8", newline="\n")
        else:
            issues.append(f"생성 안내 불일치: {identity}")
    return issues


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 예제 안내 동기화 CLI를 실행합니다. """

    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parsed = parser.parse_args(arguments)
    try:
        issues = synchronize(write=parsed.write)
    except ExampleGuidanceError as error:
        print(f"RC2_EXAMPLE_GUIDANCE_FAIL: {error}", file=sys.stderr)
        return 1
    if issues:
        for issue in issues:
            print(f"RC2_EXAMPLE_GUIDANCE_ISSUE: {issue}", file=sys.stderr)
        return 1
    print(f"RC2_EXAMPLE_GUIDANCE_PASS=examples:{len(public_examples())};mode:{'write' if parsed.write else 'check'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
