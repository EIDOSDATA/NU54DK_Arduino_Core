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
GUIDE_PATH = ROOT / "libraries" / "EXAMPLES.md"
READINESS_PATH = ROOT / "variants" / "nu54dk" / "m33-release-readiness.json"
LOCK_PATH = ROOT / "tools" / "ci" / "ncs-3.4.0.lock.json"
BEGIN_MARKER = "/** @nucode_example_setup_begin"
END_MARKER = " * @nucode_example_setup_end */"
GUIDANCE_FIELDS = (
    "purpose",
    "requirements",
    "configuration",
    "run_steps",
    "success_output",
    "common_errors",
    "next_examples",
)
TRACEABILITY_FIELDS = (
    "recipe_group",
    "source_traceability",
    "lifecycle",
    "security",
    "limitations",
    "negative_conditions",
    "evidence_id",
    "build_classification",
    "runtime_classification",
)
ALLOWED_PROFILES = {
    "standard",
    "ble",
    "adaptive",
    "fabric",
    "secure_ble_dfu",
    "ble_audio_io",
    "radio_ieee802154",
    "radio_esb",
    "coexistence_ble_mesh",
    "coexistence_ble_154",
    "coexistence_ble_esb",
    "external_coexistence",
}
PROFILE_LABELS = {
    "standard": "Standard peripherals",
    "ble": "BLE NUS",
    "adaptive": "Adaptive capabilities (experimental)",
    "fabric": "Peripheral Fabric (DAP UART disconnected)",
    "secure_ble_dfu": "Secure BLE DFU (MCUboot)",
    "ble_audio_io": "BLE Audio external I/O (DAP UART disconnected)",
    "radio_ieee802154": "Standalone IEEE 802.15.4 radio",
    "radio_esb": "Standalone Enhanced ShockBurst radio",
    "coexistence_ble_mesh": "BLE + Bluetooth Mesh coexistence",
    "coexistence_ble_154": "BLE + IEEE 802.15.4 coexistence",
    "coexistence_ble_esb": "BLE + ESB coexistence candidate",
    "external_coexistence": "BLE external 1-wire coexistence",
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


def _without_generated_guidance(text: str) -> str:
    """! @brief 생성 안내를 제외한 사용자가 작성한 Sketch 본문을 반환합니다. """

    pattern = re.compile(
        rf"\A{re.escape(BEGIN_MARKER)}.*?{re.escape(END_MARKER)}\r?\n(?:\r?\n)?",
        flags=re.DOTALL,
    )
    return pattern.sub("", text, count=1)


def _first_brief(text: str, identity: str) -> str:
    """! @brief Sketch의 첫 사용자 Doxygen brief를 목적 문장으로 사용합니다. """

    match = re.search(r"@brief\s+([^\r\n]+)", _without_generated_guidance(text))
    if match is None:
        return f"`{identity}` 공개 API의 기본 사용 흐름을 실행합니다."
    return match.group(1).strip()


def _serial_messages(text: str, *, failures: bool) -> list[str]:
    """! @brief Sketch의 고정 Serial 문구를 성공 또는 오류 안내 후보로 수집합니다. """

    failure_tokens = (
        "fail", "error", "invalid", "missing", "denied", "mismatch",
        "timeout", "reject", "unsupported", "cannot", "bad ",
    )
    messages: list[str] = []
    for match in re.finditer(
        r'Serial\.(?:print|println|printf)\(\s*"((?:\\.|[^"\\])*)"',
        _without_generated_guidance(text),
    ):
        value = match.group(1).replace(r"\n", " ").strip()
        if not value or (any(token in value.casefold() for token in failure_tokens) != failures):
            continue
        if value not in messages:
            messages.append(value)
        if len(messages) == 3:
            break
    return messages


def _recipe_group(library: str, sketch: str) -> str:
    """! @brief M33 readiness와 같은 규칙으로 공개 예제의 primary Recipe를 정합니다. """

    if library in {"EEPROM", "LittleFS"} or sketch == "SettingsStorage":
        return "storage"
    if library == "Servo":
        return "servo_motion"
    if library == "SPI" or sketch.startswith("SPI"):
        return "spi"
    if library == "Wire" or sketch.startswith("Wire"):
        return "i2c_wire"
    if library == "NUCODE_Peripheral_Fabric":
        return "peripheral_fabric"
    if library == "NUCODE_NU54DK":
        if sketch.startswith(("Analog", "DynamicPWM", "PWM", "Tone")):
            return "analog_pwm_tone"
        if sketch.startswith(("Blink", "Interrupt")):
            return "gpio_interrupt"
        if sketch.startswith("Serial"):
            return "serial"
        return "board_system_power"
    direct_groups = {
        "NUCODE_Radio_IEEE802154": "radio_802154",
        "NUCODE_Radio_ESB": "radio_esb",
        "NUCODE_Radio_Coexistence": "radio_coexistence",
        "NUCODE_BLE_Audio": "ble_audio",
        "NUCODE_BLE_ISO": "ble_iso",
        "NUCODE_BLE_ChannelSounding": "ble_channel_sounding",
        "NUCODE_BLE_DirectionFinding": "ble_direction_finding",
        "NUCODE_BLE_DFU": "ble_dfu",
        "NUCODE_BLE_Mesh": "ble_mesh_models",
        "NUCODE_BLE_Mesh_Management": "ble_mesh_management",
        "NUCODE_BLE_Mesh_Update": "ble_mesh_update",
        "NUCODE_BLE_EATT": "ble_gatt_extensions",
        "NUCODE_BLE_LegacySigning": "ble_gatt_extensions",
        "NUCODE_BLE_Security": "ble_profiles_and_ecosystems",
        "NUCODE_BLE_Profiles": "ble_profiles_and_ecosystems",
        "NUCODE_BLE_Companion": "ble_profiles_and_ecosystems",
    }
    if library in direct_groups:
        return direct_groups[library]
    if library == "NUCODE_BLE":
        if sketch in {"BeaconAdvertiser", "BeaconObserver"}:
            return "ble_beacons"
        if sketch.startswith("NUS"):
            return "ble_uart"
        if any(token in sketch for token in ("Gatt", "ReliableWrite")):
            return "ble_gatt"
        if sketch.startswith("L2cap"):
            return "ble_l2cap"
        if any(token in sketch for token in (
            "Advertising", "Scanner", "Periodic", "Pawr", "Past", "Privacy",
        )):
            return "ble_advertising_scanning"
        if any(token in sketch for token in (
            "Connection", "Power", "PathLoss", "Rssi", "Radio", "Channel",
            "FrameSpace", "Llpm", "SleepClock",
        )):
            return "ble_link_control"
        return "ble_gap_multilink"
    raise ExampleGuidanceError(f"Recipe 분류가 없습니다: {library}/{sketch}")


def _security_guidance(identity: str) -> dict[str, str]:
    """! @brief 예제가 주장하는 보안 범위를 과장하지 않는 분류를 만듭니다. """

    sensitive_tokens = ("Security", "Dfu", "Mesh_Update", "Companion", "LegacySigning")
    if any(token in identity for token in sensitive_tokens):
        return {
            "classification": "explicit_security_or_signed_artifact_flow",
            "guidance": "예제의 pairing·bond·서명·credential 조건을 생략하지 않고 오류 출력을 확인합니다.",
        }
    if identity.startswith(("NUCODE_BLE", "NUCODE_Radio")):
        return {
            "classification": "wireless_example_no_implicit_security_claim",
            "guidance": "무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.",
        }
    return {
        "classification": "no_security_property_claimed",
        "guidance": "이 예제는 별도의 보안 속성을 주장하지 않습니다.",
    }


def _materialized_record(
    identity: str,
    record: dict[str, Any],
    sketch: Path,
    identities: list[str],
) -> dict[str, Any]:
    """! @brief 한 예제의 7개 사용자 안내와 추적 필드를 결정적으로 채웁니다. """

    result = dict(record)
    source = sketch.read_text(encoding="utf-8")
    library, example = identity.split("/", 1)
    role_text = "; ".join(
        f"{index + 1}) {role}" for index, role in enumerate(record["roles"])
    )
    requirements = [f"NU54DK 보드 {record['board_count']}대 — {role_text}"]
    requirements.extend(record["conditions"])
    configuration = [
        f"Tools → Feature set에서 `{record['recommended_profile']}` profile을 선택합니다.",
    ]
    if record["sidecars"]:
        configuration.append(
            "Sketch 폴더의 sidecar를 함께 설치합니다: " + ", ".join(record["sidecars"])
        )
    configuration.append(
        f"Serial Monitor는 {record['serial_baud']} baud로 엽니다."
        if record["serial_baud"] is not None
        else "이 예제는 Serial Monitor 출력을 필수 결과로 사용하지 않습니다."
    )
    run_steps = [
        "권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.",
        "probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.",
        "peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.",
    ]
    successes = _serial_messages(source, failures=False)
    if successes:
        success_output = [f"Serial 문구 `{message}`를 포함한 정상 상태 전이를 확인합니다." for message in successes]
    elif record["serial_baud"] is not None:
        success_output = ["Serial Monitor에서 오류 문구 없이 목적 기능의 상태 전이가 완료되는지 확인합니다."]
    else:
        success_output = ["목적에 적힌 LED·pin·peer 동작을 직접 확인합니다. Compile PASS만으로 runtime PASS로 처리하지 않습니다."]
    errors = _serial_messages(source, failures=True)
    common_errors = [
        "권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.",
        "여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.",
    ]
    common_errors.extend(f"`{message}` 출력은 실패이며 원인을 확인한 뒤 재시작합니다." for message in errors)
    same_library = [candidate for candidate in identities if candidate.startswith(f"{library}/")]
    position = identities.index(identity)
    ordered_candidates = same_library if len(same_library) > 1 else identities
    candidate_position = ordered_candidates.index(identity)
    next_examples = [
        ordered_candidates[(candidate_position + offset) % len(ordered_candidates)]
        for offset in range(1, min(3, len(ordered_candidates)))
    ]
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    result.update({
        "recipe_group": _recipe_group(library, example),
        "purpose": _first_brief(source, identity),
        "requirements": requirements,
        "configuration": configuration,
        "run_steps": run_steps,
        "success_output": success_output,
        "common_errors": common_errors,
        "next_examples": next_examples,
        "source_traceability": {
            "classification": "local_public_api_example_not_direct_upstream_copy",
            "upstream_path": None,
            "ncs_revision": lock["ncs"]["revision"],
            "zephyr_revision": lock["zephyr"]["revision"],
            "board_revision": "fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3",
        },
        "lifecycle": {
            "termination": "예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.",
            "restart": "실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.",
        },
        "security": _security_guidance(identity),
        "limitations": [
            "Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.",
            "목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.",
        ],
        "negative_conditions": [
            "wrong_profile_or_missing_sidecar",
            "missing_or_wrong_role_peer",
            "startup_or_runtime_error_reported",
        ],
        "evidence_id": "M33-EXAMPLE-01:" + identity.replace("/", ":"),
        "build_classification": "clean_installed_compile_required",
        "runtime_classification": "procedure_documented_not_physical_pass",
    })
    return result


def materialize_metadata(
    document: dict[str, Any], examples: dict[str, Path]
) -> dict[str, Any]:
    """! @brief 현재 공개 예제에서 W05 안내 metadata 전체를 재생성합니다. """

    result = dict(document)
    records = result.get("examples")
    if not isinstance(records, dict):
        raise ExampleGuidanceError("metadata examples가 object가 아닙니다")
    identities = sorted(examples, key=str.casefold)
    result["example_count"] = len(identities)
    result["guidance_contract"] = {
        "required_fields": list(GUIDANCE_FIELDS),
        "traceability_fields": list(TRACEABILITY_FIELDS),
        "build_classification": "clean_installed_tree",
        "runtime_classification": "per_role_procedure_separate_from_physical_result",
    }
    result["examples"] = {
        identity: _materialized_record(identity, records[identity], examples[identity], identities)
        for identity in identities
    }
    return result


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
    guidance_contract = document.get("guidance_contract")
    if not isinstance(guidance_contract, dict):
        issues.append("W05 guidance_contract 누락")
    elif (
        guidance_contract.get("required_fields") != list(GUIDANCE_FIELDS)
        or guidance_contract.get("traceability_fields") != list(TRACEABILITY_FIELDS)
        or guidance_contract.get("build_classification") != "clean_installed_tree"
        or guidance_contract.get("runtime_classification")
        != "per_role_procedure_separate_from_physical_result"
    ):
        issues.append("W05 guidance_contract 불일치")
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
        for field in GUIDANCE_FIELDS:
            value = record.get(field)
            if field == "purpose":
                if not isinstance(value, str) or not value.strip():
                    issues.append(f"사용자 안내 누락: {identity}: {field}")
            elif (
                not isinstance(value, list)
                or not value
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                issues.append(f"사용자 안내 누락: {identity}: {field}")
        if not isinstance(record.get("recipe_group"), str) or not record["recipe_group"]:
            issues.append(f"Recipe 누락: {identity}")
        traceability = record.get("source_traceability")
        if (
            not isinstance(traceability, dict)
            or traceability.get("classification")
            != "local_public_api_example_not_direct_upstream_copy"
            or traceability.get("upstream_path") is not None
            or not isinstance(traceability.get("ncs_revision"), str)
            or not isinstance(traceability.get("zephyr_revision"), str)
            or not isinstance(traceability.get("board_revision"), str)
        ):
            issues.append(f"원본 revision 추적 누락: {identity}")
        for field in ("lifecycle", "security"):
            value = record.get(field)
            if not isinstance(value, dict) or not value or any(
                not isinstance(item, str) or not item.strip() for item in value.values()
            ):
                issues.append(f"추적 안내 누락: {identity}: {field}")
        for field in ("limitations", "negative_conditions"):
            value = record.get(field)
            if (
                not isinstance(value, list)
                or not value
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                issues.append(f"추적 안내 누락: {identity}: {field}")
        if record.get("evidence_id") != "M33-EXAMPLE-01:" + identity.replace("/", ":"):
            issues.append(f"증거 ID 불일치: {identity}")
        if record.get("build_classification") != "clean_installed_compile_required":
            issues.append(f"build 분류 불일치: {identity}")
        if record.get("runtime_classification") != "procedure_documented_not_physical_pass":
            issues.append(f"runtime 분류 불일치: {identity}")
    return issues


def _render_items(lines: list[str], title: str, items: list[str]) -> None:
    """! @brief Doxygen 단락에 문자열 목록을 추가합니다. """

    lines.extend((f" * @par {title}", *(f" * - {item}" for item in items)))


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
        " * @par 목적",
        f" * {record['purpose']}",
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
    ]
    _render_items(lines, "준비물", record["requirements"])
    _render_items(lines, "설정", record["configuration"])
    _render_items(lines, "실행 순서", record["run_steps"])
    _render_items(lines, "성공 출력", record["success_output"])
    _render_items(lines, "흔한 오류", record["common_errors"])
    _render_items(
        lines,
        "다음 예제",
        [f"`{next_identity}`" for next_identity in record["next_examples"]],
    )
    _render_items(lines, "종료와 재시작", list(record["lifecycle"].values()))
    _render_items(lines, "보안", list(record["security"].values()))
    _render_items(lines, "제한", record["limitations"])
    _render_items(lines, "Negative", record["negative_conditions"])
    traceability = record["source_traceability"]
    lines.extend((
        " * @par Traceability",
        f" * Recipe `{record['recipe_group']}`; 내부 증거 ID는 metadata에서 관리합니다.",
        f" * 직접 upstream 복사 아님; NCS `{traceability['ncs_revision']}`, Zephyr `{traceability['zephyr_revision']}`",
        f" * build `{record['build_classification']}`, runtime `{record['runtime_classification']}`",
        " * @par Metadata",
        f" * identity `{identity}`, sha256 `{digest}`",
        END_MARKER,
    ))
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


def _markdown_text(value: str) -> str:
    """! @brief Markdown 표에 넣을 문자열을 한 줄로 정규화합니다. """

    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def render_example_guide(
    document: dict[str, Any], root: Path = ROOT
) -> str:
    """! @brief Start Here·Recipe·Reference 3층 사용자 안내를 생성합니다. """

    try:
        readiness = json.loads(
            (root / "variants" / "nu54dk" / "m33-release-readiness.json").read_text(
                encoding="utf-8"
            )
        )
        journeys = readiness["example_discovery"]["start_here_journeys"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ExampleGuidanceError(f"Start Here 원장을 읽지 못했습니다: {error}") from error
    records = document["examples"]
    path_to_identity = {record["path"]: identity for identity, record in records.items()}
    lines = [
        "# NU54DK 예제 안내",
        "",
        "공개 예제는 모두 보존하되, 처음부터 204개를 읽지 않아도 되도록 `Start Here → Functional Recipe → Reference` 순서로 찾습니다.",
        "Build 결과와 실제 보드 runtime, 외부 제품 상호운용은 서로 다른 판정입니다. 각 Sketch 맨 위의 생성 안내에서 profile·역할·성공 조건을 먼저 확인하십시오.",
        "",
        "## Start Here — 12개 사용 시나리오",
        "",
    ]
    for index, journey in enumerate(journeys, 1):
        lines.append(f"### {index}. {journey['user_intent']}")
        lines.append("")
        for path in journey["sketches"]:
            identity = path_to_identity.get(path)
            if identity is None:
                raise ExampleGuidanceError(f"Start Here 예제가 metadata에 없습니다: {path}")
            record = records[identity]
            relative = Path(path).relative_to("libraries").as_posix()
            lines.append(
                f"- [{identity}](<{relative}>): {_markdown_text(record['purpose'])}"
            )
        lines.append("")
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for identity, record in records.items():
        groups.setdefault(record["recipe_group"], []).append((identity, record))
    lines.extend((
        "## Functional Recipe — 29개 기능군",
        "",
        "한 기능군 안에서도 central/peripheral, advertiser/observer처럼 역할과 상태 전이가 다르면 별도 Sketch로 유지합니다.",
        "",
    ))
    for group in sorted(groups, key=str.casefold):
        rows = sorted(groups[group], key=lambda item: item[0].casefold())
        lines.append(f"### `{group}` ({len(rows)}개)")
        lines.append("")
        lines.append(", ".join(
            f"[{identity}](<{Path(record['path']).relative_to('libraries').as_posix()}>)"
            for identity, record in rows
        ))
        lines.append("")
    lines.extend((
        "## Reference — 전체 204개",
        "",
        "| 예제 | Recipe | 권장 profile | 보드/역할 | runtime 판정 |",
        "| --- | --- | --- | --- | --- |",
    ))
    for identity, record in sorted(records.items(), key=lambda item: item[0].casefold()):
        relative = Path(record["path"]).relative_to("libraries").as_posix()
        roles = "; ".join(record["roles"])
        lines.append(
            f"| [{identity}](<{relative}>) | `{record['recipe_group']}` | "
            f"`{record['recommended_profile']}` | {record['board_count']}대 — "
            f"{_markdown_text(roles)} | `{record['runtime_classification']}` |"
        )
    lines.extend((
        "",
        "## 판정 경계",
        "",
        "- `clean_installed_compile_required`는 clean 설치본 compile 대상이라는 뜻이며 runtime PASS가 아닙니다.",
        "- `procedure_documented_not_physical_pass`는 실행 절차와 역할 계약이 있다는 뜻이며 미실행 실물을 PASS로 세지 않습니다.",
        "- Apple/Google peer, 외장 audio·sensor·RF 계측기는 사용자 후속 결과를 별도 `NOT_RUN` 또는 실제 결과로 기록합니다.",
        "- 자동 mass erase·unlock·recover는 예제 실행 절차에 포함하지 않습니다.",
        "",
    ))
    return "\n".join(lines)


def synchronize(*, write: bool, root: Path = ROOT) -> list[str]:
    """! @brief 전 예제 안내를 검사하거나 metadata와 byte 일치하도록 갱신합니다. """

    examples = public_examples(root)
    metadata_path = root / "libraries" / "example-metadata.json"
    document = load_metadata(metadata_path)
    if write:
        document = materialize_metadata(document, examples)
        metadata_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
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
    expected_guide = render_example_guide(document, root)
    guide_path = root / "libraries" / "EXAMPLES.md"
    if not guide_path.is_file() or guide_path.read_text(encoding="utf-8") != expected_guide:
        if write:
            guide_path.write_text(expected_guide, encoding="utf-8", newline="\n")
        else:
            issues.append("Start Here·Recipe·Reference 생성 안내 불일치")
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
