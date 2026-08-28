#!/usr/bin/env python3
"""! @brief NU54DK DTS 단일 원본과 Arduino digital pin 계약을 검증합니다. """

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD_ROOT = REPOSITORY_ROOT / "board_package" / "NU54DK_Zephyr_DTS"
PIN_LIST = REPOSITORY_ROOT / "variants" / "nu54dk" / "digital_pins.inc"
VARIANT_HEADER = REPOSITORY_ROOT / "variants" / "nu54dk" / "variant.h"
VARIANT_SOURCE = REPOSITORY_ROOT / "variants" / "nu54dk" / "variant.cpp"

PIN_ENTRY_PATTERN = re.compile(
    r"^\s*NUCODE_NU54DK_DIGITAL_PIN\(\s*"
    r"(?P<logical>[A-Z][A-Z0-9_]*)\s*,\s*"
    r"(?P<alias>(?:led|sw)\d+)\s*,\s*"
    r"(?P<kind>led|button|pwm_owned)\s*\)\s*$",
    re.MULTILINE,
)
NUMERIC_DEFINE_PATTERN = re.compile(
    r"^\s*#define\s+(?P<name>[A-Z][A-Z0-9_]*)\s+"
    r"(?P<value>(?:0x[0-9a-fA-F]+|\d+))U?\s*$",
    re.MULTILINE,
)
ALIAS_BLOCK_PATTERN = re.compile(r"\baliases\s*\{(?P<body>.*?)\};", re.DOTALL)
ALIAS_PATTERN = re.compile(r"\b(?P<alias>[a-z][a-z0-9-]*)\s*=\s*&(?P<label>[A-Za-z_]\w*)\s*;")
GPIO_NODE_PATTERN = re.compile(
    r"\b(?P<label>[A-Za-z_]\w*)\s*:\s*[^{};]+\{"
    r"(?P<body>[^{}]*?\bgpios\s*=\s*<(?P<spec>[^>]+)>;[^{}]*?)\};",
    re.DOTALL,
)
GPIO_SPEC_PATTERN = re.compile(
    r"^\s*&(?P<controller>[A-Za-z_]\w*)\s+"
    r"(?P<pin>0x[0-9a-fA-F]+|\d+)\s+(?P<flags>.+?)\s*$",
    re.DOTALL,
)


class PinMapContractError(RuntimeError):
    """! @brief DTS와 Variant pin 계약이 일치하지 않을 때 발생합니다. """


## @brief UTF-8 text 파일을 읽고 오류를 계약 실패로 변환합니다.
def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PinMapContractError(f"파일을 읽지 못했습니다: {path}: {error}") from error


## @brief variant.h의 직접 숫자 상수를 읽습니다.
def parse_numeric_defines(source: str) -> dict[str, int]:
    values = {
        match.group("name"): int(match.group("value"), 0)
        for match in NUMERIC_DEFINE_PATTERN.finditer(source)
    }
    required = {
        "LED_BUILTIN",
        "PIN_BUTTON0",
        "PIN_A0",
        "PIN_PWM0",
        "PIN_LED1",
        "PIN_LED2",
        "PIN_LED3",
        "PIN_BUTTON1",
        "PIN_BUTTON2",
        "PIN_BUTTON3",
        "NUM_DIGITAL_PINS",
        "NUM_DIGITAL_CAPABLE_PINS",
        "NUM_PIN_ROLES",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise PinMapContractError(f"variant.h 숫자 상수가 누락되었습니다: {missing}")
    return values


## @brief X-macro pin 목록을 순서대로 읽습니다.
def parse_pin_entries(source: str) -> list[dict[str, str]]:
    entries = [match.groupdict() for match in PIN_ENTRY_PATTERN.finditer(source)]
    if not entries:
        raise PinMapContractError("digital_pins.inc에 공개 digital pin이 없습니다.")
    return entries


## @brief common DTS에서 alias와 GPIO spec을 읽습니다.
def parse_board_dts(source: str) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    alias_match = ALIAS_BLOCK_PATTERN.search(source)
    if alias_match is None:
        raise PinMapContractError("NU54DK common DTS에 aliases node가 없습니다.")
    aliases = {
        match.group("alias"): match.group("label")
        for match in ALIAS_PATTERN.finditer(alias_match.group("body"))
    }

    nodes: dict[str, dict[str, Any]] = {}
    for node_match in GPIO_NODE_PATTERN.finditer(source):
        spec_match = GPIO_SPEC_PATTERN.match(node_match.group("spec"))
        if spec_match is None:
            continue
        label = node_match.group("label")
        nodes[label] = {
            "controller": spec_match.group("controller"),
            "pin": int(spec_match.group("pin"), 0),
            "flags": " ".join(spec_match.group("flags").split()),
        }
    return aliases, nodes


## @brief Variant가 물리 GPIO 값을 별도 원본으로 기록하지 않았는지 검사합니다.
def validate_no_physical_pin_copy(pin_list: str, variant_source: str) -> None:
    combined = f"{pin_list}\n{variant_source}"
    forbidden_patterns = (
        r"\bP[012]\.\d+\b",
        r"<&gpio[012]\s+\d+",
        r"\{\s*&gpio[012]\s*,\s*\d+",
    )
    for pattern in forbidden_patterns:
        if re.search(pattern, combined):
            raise PinMapContractError(
                "Variant 실행 원본에 물리 GPIO controller/pin 값이 복제되었습니다."
            )
    if '#include "digital_pins.inc"' not in variant_source:
        raise PinMapContractError("variant.cpp가 고정 digital pin X-macro를 사용하지 않습니다.")
    if "GPIO_DT_SPEC_GET(DT_ALIAS(alias_name), gpios)" not in variant_source:
        raise PinMapContractError("variant.cpp가 DTS alias에서 gpio_dt_spec을 생성하지 않습니다.")


## @brief 실제 고정 DTS와 논리 pin/capability 계약을 검증하고 evidence를 생성합니다.
def verify_pinmap(repository_root: Path, board_root: Path) -> dict[str, Any]:
    pin_list_path = repository_root / "variants" / "nu54dk" / "digital_pins.inc"
    header_path = repository_root / "variants" / "nu54dk" / "variant.h"
    source_path = repository_root / "variants" / "nu54dk" / "variant.cpp"
    board_dts_path = (
        board_root
        / "boards"
        / "nucode"
        / "nu54dk"
        / "nu54dk_common.dtsi"
    )

    pin_list_source = read_text(pin_list_path)
    header_source = read_text(header_path)
    variant_source = read_text(source_path)
    board_source = read_text(board_dts_path)

    values = parse_numeric_defines(header_source)
    entries = parse_pin_entries(pin_list_source)
    aliases, nodes = parse_board_dts(board_source)
    validate_no_physical_pin_copy(pin_list_source, variant_source)

    legacy_values = {
        "LED_BUILTIN": 0,
        "PIN_BUTTON0": 1,
        "PIN_A0": 2,
        "PIN_PWM0": 3,
    }
    for name, expected in legacy_values.items():
        if values[name] != expected:
            raise PinMapContractError(
                f"v0.1 공개 pin 값이 변경되었습니다: {name}={values[name]}, expected={expected}"
            )

    logical_names = [entry["logical"] for entry in entries]
    alias_names = [entry["alias"] for entry in entries]
    if len(set(logical_names)) != len(logical_names):
        raise PinMapContractError("공개 digital 논리 이름이 중복되었습니다.")
    if len(set(alias_names)) != len(alias_names):
        raise PinMapContractError("공개 digital DTS alias가 중복되었습니다.")
    if values["NUM_DIGITAL_PINS"] != values["NUM_PIN_ROLES"]:
        raise PinMapContractError("digital sparse ID 상한과 전체 논리 역할 범위가 다릅니다.")

    logical_ids: list[int] = []
    physical_ids: set[tuple[str, int]] = set()
    evidence_pins: list[dict[str, Any]] = []
    reserved_pins: list[dict[str, Any]] = []
    capability_by_kind = {
        "led": ["digital-input", "digital-output", "interrupt"],
        "button": ["digital-input", "interrupt"],
        "pwm_owned": [],
    }
    for entry in entries:
        logical = entry["logical"]
        alias = entry["alias"]
        kind = entry["kind"]
        if logical not in values:
            raise PinMapContractError(f"variant.h에 논리 pin 상수가 없습니다: {logical}")
        logical_id = values[logical]
        if logical_id >= values["NUM_PIN_ROLES"]:
            raise PinMapContractError(f"논리 pin이 NUM_PIN_ROLES 범위를 벗어났습니다: {logical}")
        if alias not in aliases:
            raise PinMapContractError(f"고정 DTS에 alias가 없습니다: {alias}")
        label = aliases[alias]
        if label not in nodes:
            raise PinMapContractError(f"DTS alias 대상에 gpios가 없습니다: {alias} -> {label}")
        physical = nodes[label]
        physical_id = (str(physical["controller"]), int(physical["pin"]))
        if physical_id in physical_ids:
            raise PinMapContractError(f"둘 이상의 digital 논리 pin이 같은 GPIO를 사용합니다: {physical_id}")
        physical_ids.add(physical_id)
        pin_evidence = {
            "logical_name": logical,
            "logical_id": logical_id,
            "dts_alias": alias,
            "dts_label": label,
            "gpio_controller": physical["controller"],
            "gpio_pin": physical["pin"],
            "gpio_flags": physical["flags"],
            "capabilities": capability_by_kind[kind],
        }
        if kind == "pwm_owned":
            pin_evidence["owner"] = "PIN_PWM0"
            reserved_pins.append(pin_evidence)
        else:
            logical_ids.append(logical_id)
            evidence_pins.append(pin_evidence)

    if len(set(logical_ids)) != len(logical_ids):
        raise PinMapContractError("둘 이상의 digital 이름이 같은 논리 ID를 사용합니다.")
    if values["NUM_DIGITAL_CAPABLE_PINS"] != len(evidence_pins):
        raise PinMapContractError("NUM_DIGITAL_CAPABLE_PINS와 실제 descriptor 수가 다릅니다.")
    reserved_ids = {values["PIN_A0"], values["PIN_PWM0"], values["PIN_LED1"]}
    if reserved_ids.intersection(logical_ids):
        raise PinMapContractError("A0/PWM/PWM-owned LED slot에 digital descriptor를 등록했습니다.")

    return {
        "schema_version": 1,
        "gate": "m14-nu54dk-variant-contract",
        "status": "passed",
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "dts_source": board_dts_path.relative_to(board_root).as_posix(),
        "digital_pin_count": len(evidence_pins),
        "mapped_pin_count": len(entries),
        "digital_pin_id_limit": values["NUM_DIGITAL_PINS"],
        "pin_role_span": values["NUM_PIN_ROLES"],
        "reserved_non_digital_ids": sorted(reserved_ids),
        "reserved_pins": reserved_pins,
        "pins": evidence_pins,
    }


## @brief CLI 인자를 처리하고 pin map evidence를 선택적으로 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--board-root", type=Path, default=DEFAULT_BOARD_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(arguments)

    evidence = verify_pinmap(args.repository.resolve(), args.board_root.resolve())
    encoded = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    print("M14_VARIANT_CONTRACT_PASS=8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PinMapContractError as error:
        print(f"M14_VARIANT_CONTRACT_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
