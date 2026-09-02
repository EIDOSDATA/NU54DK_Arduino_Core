#!/usr/bin/env python3
"""! @brief NU54DK Core-owned 31핀 DTS와 Arduino canonical pin 계약을 검증합니다. """

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD_ROOT = REPOSITORY_ROOT / "board_package" / "NU54DK_Zephyr_DTS"

PIN_ENTRY_PATTERN = re.compile(
    r"^\s*NUCODE_NU54DK_PHYSICAL_PIN\(\s*"
    r"(?P<logical>[A-Z][A-Z0-9_]*)\s*,\s*"
    r"(?P<label>arduino_p[012]_\d{2})\s*\)\s*$",
    re.MULTILINE,
)
DEFINE_PATTERN = re.compile(
    r"^[ \t]*#define[ \t]+(?P<name>[A-Z][A-Z0-9_]*)[ \t]+"
    r"(?P<value>[^\r\n#]+?)[ \t]*$",
    re.MULTILINE,
)
PIN_NODE_PATTERN = re.compile(
    r"\b(?P<label>arduino_p[012]_\d{2})\s*:\s*[^{};]+\{"
    r"(?P<body>[^{}]*?)\};",
    re.DOTALL,
)
GPIO_PATTERN = re.compile(
    r"\bgpios\s*=\s*<&(?P<controller>gpio[012])\s+"
    r"(?P<pin>0x[0-9a-fA-F]+|\d+)\s+(?P<flags>[^>]+)>\s*;"
)
PROPERTY_PATTERN = re.compile(
    r"\b(?P<name>nucode,[a-z-]+)\s*=\s*<(?P<value>[^>]+)>\s*;"
)
TOKEN_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]*\b")


class PinMapContractError(RuntimeError):
    """! @brief DTS와 Variant pin 계약이 일치하지 않을 때 발생합니다. """


## @brief UTF-8 text 파일을 읽고 오류를 계약 실패로 변환합니다.
def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PinMapContractError(f"파일을 읽지 못했습니다: {path}: {error}") from error


## @brief C 전처리기의 줄 연속 표기를 한 논리 줄로 결합합니다.
def join_continued_lines(source: str) -> str:
    return re.sub(r"\\\r?\n", " ", source)


## @brief 단순 object-like #define 식을 수집합니다.
def parse_defines(*sources: str) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for source in sources:
        for match in DEFINE_PATTERN.finditer(join_continued_lines(source)):
            value = match.group("value").split("//", 1)[0].strip()
            if value:
                definitions[match.group("name")] = value
    return definitions


## @brief 정수 전처리기 식을 제한된 연산만 허용해 계산합니다.
def evaluate(expression: str, definitions: dict[str, str], stack: tuple[str, ...] = ()) -> int:
    expanded = expression.strip()
    expanded = re.sub(
        r"\b(?P<number>(?:0x[0-9a-fA-F]+|\d+))[uUlL]+\b",
        lambda match: match.group("number"),
        expanded,
    )

    def replace_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if token not in definitions:
            raise PinMapContractError(f"정수 식에서 알 수 없는 macro입니다: {token}")
        if token in stack:
            raise PinMapContractError(f"순환 macro 정의입니다: {' -> '.join((*stack, token))}")
        return str(evaluate(definitions[token], definitions, (*stack, token)))

    expanded = TOKEN_PATTERN.sub(replace_token, expanded)
    if not re.fullmatch(r"[0-9a-fA-FxX()<>|&+\-*/~\s]+", expanded):
        raise PinMapContractError(f"허용하지 않은 정수 식입니다: {expression}")
    try:
        return int(eval(expanded, {"__builtins__": {}}, {}))
    except (SyntaxError, TypeError, ValueError, ZeroDivisionError) as error:
        raise PinMapContractError(f"정수 식을 계산하지 못했습니다: {expression}") from error


## @brief X-macro의 canonical 논리 ID와 DTS label을 읽습니다.
def parse_pin_entries(source: str) -> list[dict[str, str]]:
    entries = [match.groupdict() for match in PIN_ENTRY_PATTERN.finditer(source)]
    if not entries:
        raise PinMapContractError("digital_pins.inc에 canonical physical pin이 없습니다.")
    return entries


## @brief Core-owned DTS child의 GPIO와 metadata 식을 읽습니다.
def parse_pin_nodes(source: str, definitions: dict[str, str]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for match in PIN_NODE_PATTERN.finditer(source):
        label = match.group("label")
        body = match.group("body")
        gpio_match = GPIO_PATTERN.search(body)
        if gpio_match is None:
            raise PinMapContractError(f"pin map child에 gpios가 없습니다: {label}")
        properties = {
            item.group("name"): item.group("value").strip()
            for item in PROPERTY_PATTERN.finditer(body)
        }
        required = {
            "nucode,capability-mask",
            "nucode,policy",
            "nucode,ownership",
            "nucode,route-mask",
        }
        missing = sorted(required - properties.keys())
        if missing:
            raise PinMapContractError(f"pin metadata가 누락되었습니다: {label}: {missing}")
        nodes[label] = {
            "controller": gpio_match.group("controller"),
            "pin": int(gpio_match.group("pin"), 0),
            "flags": " ".join(gpio_match.group("flags").split()),
            "capabilities": evaluate(properties["nucode,capability-mask"], definitions),
            "policy": evaluate(properties["nucode,policy"], definitions),
            "ownership": evaluate(properties["nucode,ownership"], definitions),
            "routes": evaluate(properties["nucode,route-mask"], definitions),
            "analog_channel": (
                evaluate(properties["nucode,analog-channel"], definitions)
                if "nucode,analog-channel" in properties
                else -1
            ),
        }
    if not nodes:
        raise PinMapContractError("Core-owned DTS에 pin child가 없습니다.")
    return nodes


## @brief 비트 마스크를 evidence용 이름 배열로 변환합니다.
def mask_names(mask: int, ordered: tuple[tuple[int, str], ...]) -> list[str]:
    return [name for bit, name in ordered if mask & bit]


## @brief Core-owned DTS, Variant, legacy 호환성과 fail-closed 정책을 검증합니다.
def verify_pinmap(repository_root: Path, board_root: Path) -> dict[str, Any]:
    del board_root  # Board submodule은 pin metadata 원본이 아니며 수정·파싱하지 않습니다.
    pin_list_path = repository_root / "variants" / "nu54dk" / "digital_pins.inc"
    header_path = repository_root / "variants" / "nu54dk" / "variant.h"
    source_path = repository_root / "variants" / "nu54dk" / "variant.cpp"
    metadata_path = repository_root / "dts" / "nucode" / "nu54dk-arduino-pin-metadata.h"
    dts_path = repository_root / "dts" / "nucode" / "nu54dk-arduino-pins.dtsi"

    pin_list_source = read_text(pin_list_path)
    header_source = read_text(header_path)
    variant_source = read_text(source_path)
    metadata_source = read_text(metadata_path)
    dts_source = read_text(dts_path)
    definitions = parse_defines(metadata_source, dts_source, header_source)
    entries = parse_pin_entries(pin_list_source)
    nodes = parse_pin_nodes(dts_source, definitions)

    required_constants = {
        "LED_BUILTIN": 0,
        "PIN_BUTTON0": 1,
        "PIN_A0": 2,
        "PIN_PWM0": 3,
        "PIN_LED1": 4,
        "PIN_LED2": 5,
        "PIN_LED3": 6,
        "PIN_BUTTON1": 7,
        "PIN_BUTTON2": 8,
        "PIN_BUTTON3": 9,
        "PIN_GPIO0": 10,
        "PIN_GPIO1": 11,
        "NUM_PIN_ROLES": 32,
        "NUM_PHYSICAL_PINS": 31,
        "NUM_ANALOG_INPUTS": 8,
    }
    values = {name: evaluate(name, definitions) for name in required_constants}
    for name, expected in required_constants.items():
        if values[name] != expected:
            raise PinMapContractError(
                f"공개 pin/개수 값이 변경되었습니다: {name}={values[name]}, expected={expected}"
            )
    if evaluate("NUM_DIGITAL_PINS", definitions) != 32:
        raise PinMapContractError("NUM_DIGITAL_PINS가 legacy alias span 32와 다릅니다.")
    if not re.search(r"#define\s+NUM_DIGITAL_CAPABLE_PINS\s+\\?\s*\(20U\s*\+", header_source):
        raise PinMapContractError("기본 digital-capable 실제 pad 수 20 계약이 없습니다.")

    if len(entries) != 31 or len(nodes) != 31:
        raise PinMapContractError(
            f"31개 실제 pad가 아닙니다: xmacro={len(entries)}, dts={len(nodes)}"
        )
    if len({entry["label"] for entry in entries}) != len(entries):
        raise PinMapContractError("X-macro DTS label이 중복되었습니다.")
    if set(nodes) != {entry["label"] for entry in entries}:
        raise PinMapContractError("X-macro와 Core-owned DTS child 집합이 다릅니다.")

    expected_physical = {
        *(('gpio0', pin) for pin in range(0, 5)),
        *(('gpio1', pin) for pin in range(0, 15)),
        *(('gpio2', pin) for pin in range(0, 11)),
    }
    actual_physical = {(node["controller"], node["pin"]) for node in nodes.values()}
    if actual_physical != expected_physical:
        missing = sorted(expected_physical - actual_physical)
        extra = sorted(actual_physical - expected_physical)
        raise PinMapContractError(f"31개 pad 집합이 다릅니다: missing={missing}, extra={extra}")

    logical_ids = [evaluate(entry["logical"], definitions) for entry in entries]
    expected_ids = set(range(32)) - {4}
    if set(logical_ids) != expected_ids or len(set(logical_ids)) != 31:
        raise PinMapContractError("canonical ID는 0~31에서 legacy ID 4만 제외해야 합니다.")
    if "PIN_LED1" in {entry["logical"] for entry in entries}:
        raise PinMapContractError("legacy ID 4를 별도 물리 descriptor로 생성했습니다.")
    if "logical_pin == static_cast<std::size_t>(PIN_LED1)" not in variant_source or \
            "static_cast<std::size_t>(PIN_PWM0)" not in variant_source:
        raise PinMapContractError("variant.cpp에 legacy ID 4→canonical ID 3 정규화가 없습니다.")
    if "GPIO_DT_SPEC_GET(DT_NODELABEL(node_label), gpios)" not in variant_source:
        raise PinMapContractError("variant.cpp가 Core-owned DTS node에서 gpio_dt_spec을 생성하지 않습니다.")
    if '#include "digital_pins.inc"' not in variant_source:
        raise PinMapContractError("variant.cpp가 canonical X-macro를 사용하지 않습니다.")

    cap_bits = (
        (evaluate("NUCODE_PIN_CAP_INPUT", definitions), "digital-input"),
        (evaluate("NUCODE_PIN_CAP_OUTPUT", definitions), "digital-output"),
        (evaluate("NUCODE_PIN_CAP_INTERRUPT", definitions), "interrupt"),
        (evaluate("NUCODE_PIN_CAP_OPEN_DRAIN", definitions), "open-drain"),
        (evaluate("NUCODE_PIN_CAP_ANALOG", definitions), "analog-input"),
        (evaluate("NUCODE_PIN_CAP_PWM", definitions), "pwm-output"),
        (evaluate("NUCODE_PIN_CAP_WAKEUP", definitions), "wakeup"),
    )
    route_bits = tuple(
        (evaluate(macro, definitions), name)
        for macro, name in (
            ("NUCODE_PIN_ROUTE_GPIO", "gpio"),
            ("NUCODE_PIN_ROUTE_GPIOTE", "gpiote"),
            ("NUCODE_PIN_ROUTE_ADC", "adc"),
            ("NUCODE_PIN_ROUTE_LFXO", "lfxo"),
            ("NUCODE_PIN_ROUTE_NFCT", "nfct"),
            ("NUCODE_PIN_ROUTE_UART20_CONSOLE", "uart20-console"),
            ("NUCODE_PIN_ROUTE_UART30", "uart30"),
            ("NUCODE_PIN_ROUTE_I2C22", "i2c22"),
            ("NUCODE_PIN_ROUTE_SPI00", "spi00"),
            ("NUCODE_PIN_ROUTE_PWM20", "pwm20"),
            ("NUCODE_PIN_ROUTE_PWM21", "pwm21"),
            ("NUCODE_PIN_ROUTE_PWM22", "pwm22"),
            ("NUCODE_PIN_ROUTE_PORT0", "port0"),
            ("NUCODE_PIN_ROUTE_PORT1", "port1"),
            ("NUCODE_PIN_ROUTE_PORT2", "port2"),
        )
    )
    policy_names = {
        evaluate("NUCODE_PIN_POLICY_NORMAL", definitions): "normal",
        evaluate("NUCODE_PIN_POLICY_INPUT_ONLY", definitions): "input-only",
        evaluate("NUCODE_PIN_POLICY_TRANSFERABLE", definitions): "transferable",
        evaluate("NUCODE_PIN_POLICY_CONDITIONAL_LFXO", definitions): "conditional-lfxo",
        evaluate("NUCODE_PIN_POLICY_CONDITIONAL_DAP_UART", definitions): "conditional-dap-uart",
        evaluate("NUCODE_PIN_POLICY_SYSTEM_RESERVED", definitions): "system-reserved",
    }
    ownership_names = {
        evaluate(macro, definitions): name
        for macro, name in (
            ("NUCODE_PIN_OWNER_BOARD_LED", "board-led"),
            ("NUCODE_PIN_OWNER_BOARD_BUTTON", "board-button"),
            ("NUCODE_PIN_OWNER_CONNECTOR_GPIO", "connector-gpio"),
            ("NUCODE_PIN_OWNER_WIRE", "wire"),
            ("NUCODE_PIN_OWNER_SPI", "spi"),
            ("NUCODE_PIN_OWNER_PWM", "pwm"),
            ("NUCODE_PIN_OWNER_ADC", "adc"),
            ("NUCODE_PIN_OWNER_SERIAL", "serial"),
            ("NUCODE_PIN_OWNER_SYSTEM", "system"),
            ("NUCODE_PIN_OWNER_CONDITIONAL", "conditional"),
        )
    }

    interrupt_bit = evaluate("NUCODE_PIN_CAP_INTERRUPT", definitions)
    output_bit = evaluate("NUCODE_PIN_CAP_OUTPUT", definitions)
    gpiote_bit = evaluate("NUCODE_PIN_ROUTE_GPIOTE", definitions)
    uart30_bit = evaluate("NUCODE_PIN_ROUTE_UART30", definitions)
    i2c22_bit = evaluate("NUCODE_PIN_ROUTE_I2C22", definitions)
    spi00_bit = evaluate("NUCODE_PIN_ROUTE_SPI00", definitions)
    pwm_bits = sum(evaluate(name, definitions) for name in (
        "NUCODE_PIN_ROUTE_PWM20", "NUCODE_PIN_ROUTE_PWM21", "NUCODE_PIN_ROUTE_PWM22"
    ))
    input_only = evaluate("NUCODE_PIN_POLICY_INPUT_ONLY", definitions)
    system_reserved = evaluate("NUCODE_PIN_POLICY_SYSTEM_RESERVED", definitions)

    for label, node in nodes.items():
        controller = node["controller"]
        if controller == "gpio2" and ((node["capabilities"] & interrupt_bit) or
                                      (node["routes"] & gpiote_bit)):
            raise PinMapContractError(f"P2 interrupt는 fail-closed여야 합니다: {label}")
        if node["policy"] in (input_only, system_reserved) and \
                (node["capabilities"] & output_bit):
            raise PinMapContractError(f"input-only/system-reserved에 output이 있습니다: {label}")
        if controller == "gpio0" and not (node["routes"] & uart30_bit):
            raise PinMapContractError(f"P0 전체에 UARTE30 기술 route가 필요합니다: {label}")
        if controller == "gpio1" and \
                ((node["routes"] & i2c22_bit) == 0 or (node["routes"] & pwm_bits) != pwm_bits):
            raise PinMapContractError(f"P1 전체 기술 route matrix가 누락되었습니다: {label}")
        has_spi = bool(node["routes"] & spi00_bit)
        should_have_spi = (controller, node["pin"]) in {
            ("gpio2", 1), ("gpio2", 2), ("gpio2", 4)
        }
        if has_spi != should_have_spi:
            raise PinMapContractError(f"SPIM00 dedicated route가 다릅니다: {label}")

    evidence_pins: list[dict[str, Any]] = []
    for entry in entries:
        node = nodes[entry["label"]]
        evidence_pins.append({
            "logical_name": entry["logical"],
            "logical_id": evaluate(entry["logical"], definitions),
            "dts_label": entry["label"],
            "gpio_controller": node["controller"],
            "gpio_pin": node["pin"],
            "gpio_flags": node["flags"],
            "capabilities": mask_names(node["capabilities"], cap_bits),
            "policy": policy_names[node["policy"]],
            "ownership": ownership_names[node["ownership"]],
            "routes": mask_names(node["routes"], route_bits),
            "analog_channel": node["analog_channel"],
        })

    return {
        "schema_version": 2,
        "gate": "m14-nu54dk-variant-contract",
        "status": "passed",
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "dts_source": dts_path.relative_to(repository_root).as_posix(),
        "physical_pin_count": 31,
        "mapped_pin_count": 31,
        "digital_pin_id_limit": 32,
        "pin_role_span": 32,
        "digital_capable_default": 20,
        "conditional_gpio_pin_count": 6,
        "legacy_aliases": [{"logical_name": "PIN_LED1", "logical_id": 4,
                            "canonical_name": "PIN_PWM0", "canonical_id": 3}],
        "analog_input_count": 8,
        "pins": sorted(evidence_pins, key=lambda pin: pin["logical_id"]),
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
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PinMapContractError as error:
        print(f"NU54DK pin map contract failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
