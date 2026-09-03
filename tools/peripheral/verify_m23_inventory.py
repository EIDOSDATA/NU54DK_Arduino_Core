#!/usr/bin/env python3
"""Validate and generate the M23 nRF54L15/NU54DK peripheral inventory."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY / "variants" / "nu54dk" / "peripheral-manifest.json"
SCHEMA_PATH = Path(__file__).with_name("peripheral-manifest.schema.json")
CPP_PATH = REPOSITORY / "cores" / "arduino" / "generated" / "PeripheralInventory.inc"
MATRIX_PATH = (
    REPOSITORY
    / "00_Docs"
    / "01_아두이노 코어 설계"
    / "09_M23_Peripheral_인스턴스_매트릭스.md"
)
LOCK_PATH = REPOSITORY / "tools" / "ci" / "ncs-3.4.0.lock.json"

EXPECTED_IDS = frozenset(
    """
    uarte00 uarte20 uarte21 uarte22 uarte30
    spim00 spim20 spim21 spim22 spim30
    spis00 spis20 spis21 spis22 spis30
    twim20 twim21 twim22 twim30
    twis20 twis21 twis22 twis30
    gpio0 gpio1 gpio2 gpiote20 gpiote30
    egu10 egu20
    dppic00 dppic10 dppic20 dppic30
    ppib00 ppib01 ppib10 ppib11 ppib20 ppib21 ppib22 ppib30
    timer00 timer10 timer20 timer21 timer22 timer23 timer24 grtc
    saadc pwm20 pwm21 pwm22 pdm20 pdm21 i2s20 qdec20 qdec21
    comp lpcomp temp wdt30 wdt31 nfct radio
    cracen kmu rng tampc power clock cache vpr sqspi
    """.split()
)

EXPECTED_SERIAL_GROUPS = {
    "serial00": {"uarte00", "spim00", "spis00"},
    "serial20": {"uarte20", "spim20", "spis20", "twim20", "twis20"},
    "serial21": {"uarte21", "spim21", "spis21", "twim21", "twis21"},
    "serial22": {"uarte22", "spim22", "spis22", "twim22", "twis22"},
    "serial30": {"uarte30", "spim30", "spis30", "twim30", "twis30"},
}

EXPECTED_PUBLIC_OBJECTS = {
    "Serial": "uarte20",
    "Serial1": "uarte30",
    "Wire": "twim22",
    "SPI": "spim00",
}

KIND_VALUES = (
    "uarte", "spim", "spis", "twim", "twis", "gpio", "gpiote", "egu",
    "dppic", "ppib", "timer", "grtc", "saadc", "pwm", "pdm", "i2s",
    "qdec", "comp", "lpcomp", "temp", "wdt", "nfct", "radio", "cracen",
    "kmu", "rng", "tampc", "power", "clock", "cache", "vpr", "sqspi",
)
ROUTE_VALUES = ("not_required", "candidate", "partial", "verified", "unroutable")
OWNER_VALUES = (
    "gpio", "gpiote", "serial", "wire", "spi", "timer", "pwm", "adc",
    "dppi", "pdm", "i2s", "qdec", "comparator", "radio", "security",
    "system", "application",
)
SOURCE_VALUES = ("absent", "internal", "partial", "implemented")
EXPOSURE_VALUES = ("none", "internal", "public")
VERIFICATION_VALUES = ("not_applicable", "not_run", "partial", "pass")
DMA_MODE_VALUES = ("none", "synchronous", "asynchronous", "continuous", "double_buffered")
STATE_KEYS = ("silicon", "source", "exposure", "build", "semantic", "hil", "concurrent_hil")

REQUIRED_INSTANCE_KEYS = {
    "id", "kind", "instance", "sharing_group", "dt_node", "route", "owner",
    "public_object", "public_api", "driver", "dma", "states", "milestone", "evidence",
}


class InventoryFailure(RuntimeError):
    """Raised when the inventory no longer matches its fail-closed contract."""


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryFailure(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryFailure(f"cannot read strict JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise InventoryFailure(f"JSON root must be an object: {path}")
    return value


def _expect_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise InventoryFailure(f"{context} keys mismatch; missing={missing}, extra={extra}")


def _expect_enum(value: Any, allowed: Iterable[str], context: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise InventoryFailure(f"{context} has unsupported value {value!r}")
    return value


def _expected_dt_node(instance: dict[str, Any]) -> str | None:
    kind = instance["kind"]
    number = instance["instance"]
    if kind == "uarte":
        return f"uart{number:02d}"
    if kind in {"spim", "spis"}:
        return f"spi{number:02d}"
    if kind in {"twim", "twis"}:
        return f"i2c{number:02d}"
    overrides = {
        "saadc": "adc",
        "lpcomp": "comp",
        "vpr": "cpuflpr_vpr",
        "cracen": None,
        "kmu": None,
        "rng": None,
        "tampc": None,
        "cache": None,
        "sqspi": None,
    }
    return overrides.get(kind, instance["id"])


def validate_schema_contract(schema: dict[str, Any]) -> None:
    """Validate the checked-in schema fields used by the dependency-free validator."""
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise InventoryFailure("schema must use JSON Schema draft 2020-12")
    instance = schema.get("$defs", {}).get("instance")
    if not isinstance(instance, dict):
        raise InventoryFailure("schema $defs.instance is missing")
    if set(instance.get("required", [])) != REQUIRED_INSTANCE_KEYS:
        raise InventoryFailure("schema required instance fields drifted from validator")
    properties = instance.get("properties", {})
    enum_contracts = {
        "kind": KIND_VALUES,
        "owner": OWNER_VALUES,
        "milestone": ("M24", "M25", "M26"),
    }
    for field, expected in enum_contracts.items():
        observed = tuple(properties.get(field, {}).get("enum", []))
        if field == "milestone":
            pattern = properties.get(field, {}).get("pattern")
            if pattern != "^M(24|25|26)$":
                raise InventoryFailure("schema milestone pattern drifted")
        elif observed != expected:
            raise InventoryFailure(f"schema {field} enum drifted")


def validate_identity(identity: dict[str, Any]) -> None:
    required = {
        "soc", "ncs_version", "ncs_revision", "zephyr_version", "zephyr_revision",
        "board", "board_revision", "soc_dts_sources",
    }
    _expect_keys(identity, required, "identity")
    lock = strict_json_object(LOCK_PATH)
    expected = {
        "soc": "nRF54L15",
        "ncs_version": "v3.4.0",
        "ncs_revision": lock["ncs"]["revision"],
        "zephyr_version": lock["zephyr"]["version"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "board_revision": lock["board"]["revision"],
    }
    for key, expected_value in expected.items():
        if identity.get(key) != expected_value:
            raise InventoryFailure(
                f"identity.{key}={identity.get(key)!r}, expected {expected_value!r}"
            )
    sources = identity["soc_dts_sources"]
    if not isinstance(sources, list) or len(sources) != 2:
        raise InventoryFailure("identity.soc_dts_sources must contain exactly two pinned files")
    paths: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise InventoryFailure(f"soc_dts_sources[{index}] must be an object")
        _expect_keys(source, {"path", "sha256"}, f"soc_dts_sources[{index}]")
        if not isinstance(source["path"], str) or not source["path"]:
            raise InventoryFailure(f"soc_dts_sources[{index}].path is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
            raise InventoryFailure(f"soc_dts_sources[{index}].sha256 is invalid")
        if source["path"] in paths:
            raise InventoryFailure(f"duplicate DTS source path: {source['path']}")
        paths.add(source["path"])


def validate_instance(instance: dict[str, Any], index: int) -> None:
    context = f"instances[{index}]"
    _expect_keys(instance, REQUIRED_INSTANCE_KEYS, context)
    identifier = instance["id"]
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", identifier):
        raise InventoryFailure(f"{context}.id is invalid")
    _expect_enum(instance["kind"], KIND_VALUES, f"{identifier}.kind")
    if not isinstance(instance["instance"], int) or not 0 <= instance["instance"] <= 255:
        raise InventoryFailure(f"{identifier}.instance is invalid")
    if instance["dt_node"] != _expected_dt_node(instance):
        raise InventoryFailure(
            f"{identifier}.dt_node={instance['dt_node']!r}, expected {_expected_dt_node(instance)!r}"
        )
    sharing_group = instance["sharing_group"]
    if sharing_group is not None and (not isinstance(sharing_group, str) or not sharing_group):
        raise InventoryFailure(f"{identifier}.sharing_group is invalid")

    route = instance["route"]
    if not isinstance(route, dict):
        raise InventoryFailure(f"{identifier}.route must be an object")
    _expect_keys(route, {"state", "token"}, f"{identifier}.route")
    _expect_enum(route["state"], ROUTE_VALUES, f"{identifier}.route.state")
    if not isinstance(route["token"], str) or not route["token"]:
        raise InventoryFailure(f"{identifier}.route.token is invalid")

    _expect_enum(instance["owner"], OWNER_VALUES, f"{identifier}.owner")
    public_object = instance["public_object"]
    if public_object is not None and (not isinstance(public_object, str) or not public_object):
        raise InventoryFailure(f"{identifier}.public_object is invalid")
    public_api = instance["public_api"]
    if (
        not isinstance(public_api, list)
        or any(not isinstance(item, str) or not item for item in public_api)
        or len(set(public_api)) != len(public_api)
    ):
        raise InventoryFailure(f"{identifier}.public_api is invalid")
    if not isinstance(instance["driver"], str) or not instance["driver"]:
        raise InventoryFailure(f"{identifier}.driver is invalid")

    dma = instance["dma"]
    if not isinstance(dma, dict):
        raise InventoryFailure(f"{identifier}.dma must be an object")
    _expect_keys(dma, {"hardware", "driver_managed", "public_mode", "max_count_bits"}, f"{identifier}.dma")
    if not isinstance(dma["hardware"], bool) or not isinstance(dma["driver_managed"], bool):
        raise InventoryFailure(f"{identifier}.dma boolean fields are invalid")
    _expect_enum(dma["public_mode"], DMA_MODE_VALUES, f"{identifier}.dma.public_mode")
    bits = dma["max_count_bits"]
    if bits is not None and (not isinstance(bits, int) or not 1 <= bits <= 32):
        raise InventoryFailure(f"{identifier}.dma.max_count_bits is invalid")
    if not dma["hardware"] and (
        dma["driver_managed"] or dma["public_mode"] != "none" or bits is not None
    ):
        raise InventoryFailure(f"{identifier} exposes DMA metadata without DMA hardware")
    if dma["public_mode"] != "none" and not dma["hardware"]:
        raise InventoryFailure(f"{identifier} exposes a DMA API without DMA hardware")

    states = instance["states"]
    if not isinstance(states, dict):
        raise InventoryFailure(f"{identifier}.states must be an object")
    _expect_keys(states, set(STATE_KEYS), f"{identifier}.states")
    _expect_enum(states["silicon"], VERIFICATION_VALUES, f"{identifier}.states.silicon")
    _expect_enum(states["source"], SOURCE_VALUES, f"{identifier}.states.source")
    _expect_enum(states["exposure"], EXPOSURE_VALUES, f"{identifier}.states.exposure")
    for axis in ("build", "semantic", "hil", "concurrent_hil"):
        _expect_enum(states[axis], VERIFICATION_VALUES, f"{identifier}.states.{axis}")
    if states["silicon"] != "pass":
        raise InventoryFailure(f"{identifier} is in the silicon inventory without silicon PASS")
    if states["source"] == "absent" and states["exposure"] != "none":
        raise InventoryFailure(f"{identifier} exposes an API without Core source")
    if bool(public_object is not None or public_api) != (states["exposure"] == "public"):
        raise InventoryFailure(f"{identifier} public surface and exposure state disagree")
    if states["build"] == "pass" and states["source"] == "absent":
        raise InventoryFailure(f"{identifier} build PASS has no Core source")
    if states["semantic"] == "pass" and states["build"] != "pass":
        raise InventoryFailure(f"{identifier} semantic PASS lacks build PASS")
    if states["hil"] == "pass" and states["semantic"] != "pass":
        raise InventoryFailure(f"{identifier} HIL PASS lacks semantic PASS")
    if states["concurrent_hil"] == "pass" and states["hil"] != "pass":
        raise InventoryFailure(f"{identifier} concurrent HIL PASS lacks HIL PASS")

    if instance["milestone"] not in {"M24", "M25", "M26"}:
        raise InventoryFailure(f"{identifier}.milestone is invalid")
    evidence = instance["evidence"]
    if (
        not isinstance(evidence, list)
        or any(not isinstance(item, str) or not item for item in evidence)
        or len(set(evidence)) != len(evidence)
    ):
        raise InventoryFailure(f"{identifier}.evidence is invalid")
    for relative in evidence:
        path = (REPOSITORY / relative).resolve()
        if not path.is_relative_to(REPOSITORY.resolve()) or not path.is_file():
            raise InventoryFailure(f"{identifier} evidence does not exist: {relative}")


def validate_inventory(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    _expect_keys(manifest, {"schema_version", "identity", "instances"}, "manifest")
    if manifest["schema_version"] != 1:
        raise InventoryFailure("unsupported manifest schema_version")
    if not isinstance(manifest["identity"], dict):
        raise InventoryFailure("identity must be an object")
    validate_identity(manifest["identity"])
    instances = manifest["instances"]
    if not isinstance(instances, list):
        raise InventoryFailure("instances must be an array")
    for index, instance in enumerate(instances):
        if not isinstance(instance, dict):
            raise InventoryFailure(f"instances[{index}] must be an object")
        validate_instance(instance, index)

    identifiers = [item["id"] for item in instances]
    duplicates = sorted(key for key, count in Counter(identifiers).items() if count > 1)
    if duplicates:
        raise InventoryFailure(f"duplicate instance ids: {duplicates}")
    observed = set(identifiers)
    if observed != EXPECTED_IDS:
        raise InventoryFailure(
            f"exhaustive instance set mismatch; missing={sorted(EXPECTED_IDS - observed)}, "
            f"extra={sorted(observed - EXPECTED_IDS)}"
        )

    grouped: dict[str, set[str]] = defaultdict(set)
    public_objects: dict[str, str] = {}
    for item in instances:
        if item["sharing_group"]:
            grouped[item["sharing_group"]].add(item["id"])
        if item["public_object"]:
            name = item["public_object"]
            if name in public_objects:
                raise InventoryFailure(
                    f"public object alias is forbidden: {name} maps to both "
                    f"{public_objects[name]} and {item['id']}"
                )
            public_objects[name] = item["id"]
    for group, expected_members in EXPECTED_SERIAL_GROUPS.items():
        if grouped.get(group) != expected_members:
            raise InventoryFailure(
                f"{group} personality set mismatch; observed={sorted(grouped.get(group, set()))}"
            )
    if public_objects != EXPECTED_PUBLIC_OBJECTS:
        raise InventoryFailure(
            f"public object identity mismatch; observed={public_objects}, "
            f"expected={EXPECTED_PUBLIC_OBJECTS}"
        )
    return instances


def validate_repository_sources(instances: list[dict[str, Any]]) -> None:
    """Prove current public identities and verified board routes from checked-in sources."""
    contracts = {
        "uarte20": {
            "cores/arduino/HardwareSerial.cpp": ("HardwareSerial &Serial", "DT_CHOSEN(zephyr_console)"),
            "board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/nu54dk_cpuapp_common.dtsi": ("&uart20",),
        },
        "uarte30": {
            "cores/arduino/HardwareSerial.cpp": ("Serial1", "serial1RouteBinding"),
            "variants/nu54dk/peripheral_routes.cpp": ("DT_NODELABEL(uart30)",),
            "dts/nucode/nu54dk-arduino-runtime.dtsi": ("&uart30",),
        },
        "spim00": {
            "cores/arduino/SPI.cpp": ("SPIClass &SPI",),
            "variants/nu54dk/peripheral_routes.cpp": ("DT_NODELABEL(spi00)",),
        },
        "twim22": {
            "cores/arduino/Wire.cpp": ("TwoWire &Wire",),
            "variants/nu54dk/peripheral_routes.cpp": ("DT_NODELABEL(i2c22)",),
        },
        "saadc": {
            "dts/nucode/nu54dk-arduino-runtime.dtsi": ("&adc", "<&adc 7>"),
        },
        "pwm20": {"variants/nu54dk/pwm_runtime_routes.cpp": ("DT_NODELABEL(pwm20)",)},
        "pwm21": {"variants/nu54dk/pwm_runtime_routes.cpp": ("DT_NODELABEL(pwm21)",)},
        "pwm22": {"variants/nu54dk/pwm_runtime_routes.cpp": ("DT_NODELABEL(pwm22)",)},
        "wdt31": {
            "libraries/NUCODE_NU54DK/zephyr/board-system.overlay": ("&wdt31",),
            "libraries/NUCODE_NU54DK/src/NUCODE_NU54DK.cpp": ("DT_ALIAS(watchdog0)",),
        },
    }
    inventory = {item["id"]: item for item in instances}
    for identifier, files in contracts.items():
        item = inventory[identifier]
        if item["states"]["source"] == "absent":
            raise InventoryFailure(f"source contract {identifier} is marked absent")
        for relative, needles in files.items():
            text = (REPOSITORY / relative).read_text(encoding="utf-8")
            for needle in needles:
                if needle not in text:
                    raise InventoryFailure(f"{identifier} source contract missing {needle!r} in {relative}")


def validate_ncs_dts(identity: dict[str, Any], ncs_root: Path) -> None:
    root = ncs_root.resolve()
    source_texts: list[str] = []
    for source in identity["soc_dts_sources"]:
        path = root / source["path"]
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise InventoryFailure(f"cannot read pinned NCS DTS {path}: {error}") from error
        digest = hashlib.sha256(payload).hexdigest()
        if digest != source["sha256"]:
            raise InventoryFailure(
                f"NCS DTS checksum mismatch for {source['path']}: {digest} != {source['sha256']}"
            )
        source_texts.append(payload.decode("utf-8"))
    all_dts = "\n".join(source_texts)
    manifest = strict_json_object(MANIFEST_PATH)
    labels = {item["dt_node"] for item in manifest["instances"] if item["dt_node"]}
    missing = sorted(
        label for label in labels
        if re.search(rf"(?m)^\s*{re.escape(label)}:\s+", all_dts) is None
    )
    if missing:
        raise InventoryFailure(f"pinned NCS DTS labels are missing: {missing}")


def _cpp_string(value: str | None) -> str:
    if value is None:
        value = ""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _cpp_state(enum_name: str, value: str) -> str:
    mapping = {
        "not_required": "not_required",
        "candidate": "candidate",
        "partial": "partial",
        "verified": "verified",
        "unroutable": "unroutable",
        "absent": "absent",
        "internal": "internal",
        "implemented": "implemented",
        "none": "none",
        "public": "public_api",
        "not_applicable": "not_applicable",
        "not_run": "not_run",
        "pass": "pass",
    }
    return f"{enum_name}::{mapping[value]}"


def _dma_bits(dma: dict[str, Any]) -> int:
    value = 0
    if dma["hardware"]:
        value |= 1 << 0
    if dma["driver_managed"]:
        value |= 1 << 1
    value |= {
        "none": 0,
        "synchronous": 1 << 2,
        "asynchronous": 1 << 3,
        "continuous": 1 << 4,
        "double_buffered": 1 << 5,
    }[dma["public_mode"]]
    return value


def render_cpp(instances: list[dict[str, Any]]) -> str:
    lines = [
        "/* Auto-generated by tools/peripheral/verify_m23_inventory.py; do not edit. */",
        "/* SPDX-License-Identifier: MIT */",
    ]
    for item in instances:
        states = item["states"]
        dma = item["dma"]
        fields = (
            _cpp_string(item["id"]),
            f"PeripheralKind::{item['kind']}",
            f"{item['instance']}U",
            _cpp_string(item["sharing_group"]),
            _cpp_string(item["dt_node"]),
            _cpp_string(item["route"]["token"]),
            _cpp_string(item["driver"]),
            _cpp_string(item["public_object"]),
            _cpp_string(",".join(item["public_api"])),
            _cpp_string(item["milestone"]),
            _cpp_state("PeripheralRouteState", item["route"]["state"]),
            _cpp_state("PeripheralSourceState", states["source"]),
            _cpp_state("PeripheralExposureState", states["exposure"]),
            _cpp_state("PeripheralVerificationState", states["silicon"]),
            _cpp_state("PeripheralVerificationState", states["build"]),
            _cpp_state("PeripheralVerificationState", states["semantic"]),
            _cpp_state("PeripheralVerificationState", states["hil"]),
            _cpp_state("PeripheralVerificationState", states["concurrent_hil"]),
            f"static_cast<PeripheralDmaCapability>({_dma_bits(dma)}U)",
            f"{dma['max_count_bits'] or 0}U",
        )
        lines.append("\t{" + ", ".join(fields) + "},")
    return "\n".join(lines) + "\n"


def _display(value: str) -> str:
    return value.replace("_", "-")


def _surface(item: dict[str, Any]) -> str:
    values: list[str] = []
    if item["public_object"]:
        values.append(f"`{item['public_object']}`")
    values.extend(f"`{name}`" for name in item["public_api"])
    return ", ".join(values) if values else "—"


def _dma_display(item: dict[str, Any]) -> str:
    dma = item["dma"]
    if not dma["hardware"]:
        return "없음"
    bits = f"/{dma['max_count_bits']} bit" if dma["max_count_bits"] else ""
    managed = "driver" if dma["driver_managed"] else "direct 예정"
    return f"EasyDMA{bits}; {managed}; {_display(dma['public_mode'])}"


def render_matrix(manifest: dict[str, Any], instances: list[dict[str, Any]]) -> str:
    identity = manifest["identity"]
    counts = Counter(item["milestone"] for item in instances)
    current_public = sum(1 for item in instances if item["states"]["exposure"] == "public")
    hil_pass = sum(1 for item in instances if item["states"]["hil"] == "pass")
    lines = [
        "# M23 — nRF54L15/NU54DK Peripheral 인스턴스 매트릭스",
        "",
        "> 이 파일은 `variants/nu54dk/peripheral-manifest.json`에서 자동 생성합니다. 직접 수정하지 마세요.",
        "> 표의 `candidate`, `absent`, `not-run`은 현재 지원 선언이 아닙니다.",
        "",
        "| 항목 | 값 |",
        "| --- | --- |",
        f"| SoC | `{identity['soc']}` |",
        f"| NCS / Zephyr | `{identity['ncs_version']}` / `{identity['zephyr_version']}` |",
        f"| Board | `{identity['board']}` |",
        f"| Manifest schema | `{manifest['schema_version']}` |",
        f"| 추적 identity | **{len(instances)}개** |",
        f"| 현재 public surface가 있는 identity | **{current_public}개** |",
        f"| 현재 HIL PASS identity | **{hil_pass}개** |",
        f"| 후속 구현 배정 | M24 {counts['M24']} / M25 {counts['M25']} / M26 {counts['M26']} |",
        "",
        "## 판정 읽는 법",
        "",
        "- `source`는 NU54DK Core 자체 구현 수준이며 upstream driver 존재 여부와 다릅니다.",
        "- `public`은 Arduino 사용자가 선택할 surface가 있다는 뜻이지 전 기능 완료를 뜻하지 않습니다.",
        "- `build`, `semantic`, `HIL`, `concurrent`는 서로 독립이며 앞 단계 PASS가 뒤 단계 PASS를 대신하지 않습니다.",
        "- 같은 `block` 값의 personality는 같은 register/IRQ 자원을 공유하므로 동시에 사용할 수 없습니다.",
        "- 서로 다른 block도 pin, DPPI, timer channel과 DMA RAM lease가 모두 성공해야 동시 실행할 수 있습니다.",
        "",
    ]
    for milestone in ("M24", "M25", "M26"):
        lines.extend(
            [
                f"## {milestone} 배정 identity",
                "",
                "| Identity | block / DTS | board route | source / public | DMA | build | semantic | HIL | concurrent |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in instances:
            if item["milestone"] != milestone:
                continue
            states = item["states"]
            block = item["sharing_group"] or "—"
            dts = item["dt_node"] or "—"
            lines.append(
                f"| `{item['id']}` | `{block}` / `{dts}` | "
                f"{_display(item['route']['state'])}: `{item['route']['token']}` | "
                f"{_display(states['source'])} / {_display(states['exposure'])}: {_surface(item)} | "
                f"{_dma_display(item)} | {_display(states['build'])} | "
                f"{_display(states['semantic'])} | {_display(states['hil'])} | "
                f"{_display(states['concurrent_hil'])} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 단일 원본과 검사",
            "",
            "- Manifest: [`variants/nu54dk/peripheral-manifest.json`](../../variants/nu54dk/peripheral-manifest.json)",
            "- Schema: [`tools/peripheral/peripheral-manifest.schema.json`](../../tools/peripheral/peripheral-manifest.schema.json)",
            "- 검증·생성기: [`tools/peripheral/verify_m23_inventory.py`](../../tools/peripheral/verify_m23_inventory.py)",
            "- Runtime table: [`cores/arduino/generated/PeripheralInventory.inc`](../../cores/arduino/generated/PeripheralInventory.inc)",
            "",
            "검증기는 identity 누락, public object 중복 alias, 공유 block 오류, evidence 파일 누락과 생성물 drift를 거부한다.",
            "`--ncs-root`를 주면 exact NCS DTS checksum과 node label까지 대조한다.",
            "",
        ]
    )
    return "\n".join(lines)


def _check_or_write(path: Path, expected: str, write: bool) -> None:
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8", newline="\n")
        print(f"M23_GENERATED={path.relative_to(REPOSITORY).as_posix()}")
        return
    try:
        observed = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InventoryFailure(f"generated file is missing: {path}: {error}") from error
    if observed != expected:
        raise InventoryFailure(
            f"generated file drifted: {path.relative_to(REPOSITORY)}; run "
            "python tools/peripheral/verify_m23_inventory.py --write"
        )


def run(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ncs-root", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(arguments)

    schema = strict_json_object(SCHEMA_PATH)
    manifest = strict_json_object(MANIFEST_PATH)
    validate_schema_contract(schema)
    instances = validate_inventory(manifest)
    validate_repository_sources(instances)
    if args.ncs_root is not None:
        validate_ncs_dts(manifest["identity"], args.ncs_root)
    _check_or_write(CPP_PATH, render_cpp(instances), args.write)
    _check_or_write(MATRIX_PATH, render_matrix(manifest, instances), args.write)
    print(f"M23_INVENTORY_PASS=instances:{len(instances)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except InventoryFailure as error:
        print(f"M23_INVENTORY_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
