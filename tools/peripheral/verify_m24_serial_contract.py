#!/usr/bin/env python3
"""Validate and render the M24 serial-fabric route/API contract."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY / "variants" / "nu54dk" / "serial-fabric-contract.json"
SCHEMA_PATH = Path(__file__).with_name("serial-fabric-contract.schema.json")
MANIFEST_PATH = REPOSITORY / "variants" / "nu54dk" / "peripheral-manifest.json"
LOCK_PATH = REPOSITORY / "tools" / "ci" / "ncs-3.4.0.lock.json"
DOCUMENT_PATH = (
    REPOSITORY
    / "00_Docs"
    / "01_아두이노 코어 설계"
    / "10_M24_Serial_Fabric_경로와_API_계약.md"
)
PUBLIC_HEADER_PATH = REPOSITORY / "cores" / "arduino" / "nucode" / "SerialFabric.h"
BACKEND_SOURCE_PATH = REPOSITORY / "cores" / "arduino" / "SerialFabric.cpp"
BACKEND_SOURCE_PATHS = (
    BACKEND_SOURCE_PATH,
    REPOSITORY / "cores/arduino/internal/serial/SerialFabricRegistry.cpp",
    REPOSITORY / "cores/arduino/internal/serial/SerialFabricLifecycle.cpp",
)
ROUTE_SOURCE_PATH = REPOSITORY / "variants" / "nu54dk" / "serial_fabric_routes.cpp"

EXPECTED_BLOCKS = {
    "serial00": (0, "0x4004a000", 74, {"uarte00", "spim00", "spis00"}),
    "serial20": (
        20,
        "0x400c6000",
        198,
        {"uarte20", "spim20", "spis20", "twim20", "twis20"},
    ),
    "serial21": (
        21,
        "0x400c7000",
        199,
        {"uarte21", "spim21", "spis21", "twim21", "twis21"},
    ),
    "serial22": (
        22,
        "0x400c8000",
        200,
        {"uarte22", "spim22", "spis22", "twim22", "twis22"},
    ),
    "serial30": (
        30,
        "0x40104000",
        260,
        {"uarte30", "spim30", "spis30", "twim30", "twis30"},
    ),
}
EXPECTED_SINGLETONS = {
    "Serial": "uarte20",
    "Serial1": "uarte30",
    "Wire": "twim22",
    "SPI": "spim00",
}
EXPECTED_FORBIDDEN_ALIASES = {"Serial2", "SPI_HS", "Wire1"}
EXPECTED_SELECTORS = {
    "uarte": ("UarteHandle", (0, 20, 21, 22, 30)),
    "spim": ("SpimHandle", (0, 20, 21, 22, 30)),
    "spis": ("SpisHandle", (0, 20, 21, 22, 30)),
    "twim": ("TwimHandle", (20, 21, 22, 30)),
    "twis": ("TwisHandle", (20, 21, 22, 30)),
}
EXPECTED_PIN_BANKS = {
    "p2-dedicated20": (2, "approved", {0, 20}),
    "p2-dedicated21": (2, "not-approved", {0, 21}),
    "p1-flexible": (1, "conditional", {20, 21, 22}),
    "p0-flexible": (0, "conditional", {30}),
}
EXPECTED_P2_SIGNALS = {
    "p2-dedicated20": {
        "uarte": {"rxd": "P2.0", "txd": "P2.2", "cts": "P2.4", "rts": "P2.5"},
        "spim": {
            "dcx": "P2.0",
            "sck": "P2.1",
            "mosi": "P2.2",
            "miso": "P2.4",
            "csn": "P2.5",
        },
        "spis": {"sck": "P2.1", "miso": "P2.2", "mosi": "P2.4", "csn": "P2.5"},
    },
    "p2-dedicated21": {
        "uarte": {"rxd": "P2.7", "txd": "P2.8", "cts": "P2.9", "rts": "P2.10"},
        "spim": {
            "dcx": "P2.7",
            "sck": "P2.6",
            "mosi": "P2.8",
            "miso": "P2.9",
            "csn": "P2.10",
        },
        "spis": {"sck": "P2.6", "miso": "P2.8", "mosi": "P2.9", "csn": "P2.10"},
    },
}
EXPECTED_CURRENT_PROFILES = {
    "uarte20": {"txd": "P1.4", "rxd": "P1.5", "rts": "P1.6", "cts": "P1.7"},
    "uarte30": {"txd": "P0.0", "rxd": "P0.1", "rts": "P0.2", "cts": "P0.3"},
    "spim00": {"sck": "P2.1", "mosi": "P2.2", "miso": "P2.4"},
    "twim22": {"sda": "P1.2", "scl": "P1.3"},
}
EXPECTED_TEST_RESOURCES = {
    "dap-vcom-p1": (
        "host-uart-bridge",
        "onboard",
        "onboard-automatic",
        {"uarte20", "uarte21", "uarte22"},
    ),
    "dap-vcom-p0": (
        "host-uart-bridge",
        "onboard",
        "onboard-automatic",
        {"uarte30"},
    ),
    "pmic-bq25186-i2c": (
        "onboard-i2c-target",
        "onboard",
        "onboard-automatic",
        {"twim20", "twim21", "twim22"},
    ),
    "p2-header-fixture": (
        "header-fixture",
        "connector",
        "external-fixture",
        {"uarte00", "spim00", "spis00", "spim20", "spis20"},
    ),
    "p1-header-fixture": (
        "header-fixture",
        "connector",
        "external-fixture",
        {"spim21", "spis21", "twis20", "twis21", "spim22", "spis22", "twis22"},
    ),
    "p0-header-fixture": (
        "header-fixture",
        "connector",
        "external-fixture",
        {"spim30", "spis30", "twim30", "twis30"},
    ),
}
REQUIRED_SIGNALS = {
    "uarte": {"txd", "rxd"},
    "spim": {"sck", "mosi", "miso"},
    "spis": {"sck", "mosi", "miso", "csn"},
    "twim": {"sda", "scl"},
    "twis": {"sda", "scl"},
}
OPTIONAL_SIGNALS = {
    "uarte": {"cts", "rts"},
    "spim": {"csn", "dcx"},
    "spis": set(),
    "twim": set(),
    "twis": set(),
}
EXPECTED_ERRATA = {(7, "uarte"), (8, "spim"), (21, "spim"), (54, "spis"), (105, "twim")}


class ContractFailure(RuntimeError):
    """Raised when the serial-fabric contract is incomplete or inconsistent."""


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractFailure(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def strict_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractFailure(f"cannot read strict JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractFailure(f"JSON root must be an object: {path}")
    return value


def _expect_keys(value: dict[str, Any], expected: Iterable[str], context: str) -> None:
    expected_set = set(expected)
    observed = set(value)
    if observed != expected_set:
        raise ContractFailure(
            f"{context} keys mismatch; missing={sorted(expected_set - observed)}, "
            f"extra={sorted(observed - expected_set)}"
        )


def _unique_by(items: list[dict[str, Any]], key: str, context: str) -> dict[Any, dict[str, Any]]:
    result: dict[Any, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or key not in item:
            raise ContractFailure(f"{context} contains an invalid record")
        identity = item[key]
        if identity in result:
            raise ContractFailure(f"{context} has duplicate {key}: {identity!r}")
        result[identity] = item
    return result


def canonical_source_payload(payload: bytes, hash_mode: str) -> bytes:
    if hash_mode == "raw":
        return payload
    if hash_mode == "lf-normalized":
        if b"\x00" in payload:
            raise ContractFailure("LF-normalized source contains binary NUL data")
        return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    raise ContractFailure(f"unsupported local source hash mode: {hash_mode!r}")


def validate_schema_contract(schema: dict[str, Any]) -> None:
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractFailure("schema must use JSON Schema draft 2020-12")
    if schema.get("additionalProperties") is not False:
        raise ContractFailure("schema root must reject additional properties")
    required = set(schema.get("required", []))
    expected = {
        "schema_version", "identity", "sources", "stable_surface", "advanced_api",
        "pin_banks", "blocks", "test_resources", "approved_profiles", "lifecycle", "errata",
        "completion_gates",
    }
    if required != expected:
        raise ContractFailure("schema required fields drifted from validator")
    properties = schema.get("properties", {})
    if properties.get("schema_version", {}).get("const") != 2:
        raise ContractFailure("schema version must describe onboard HIL resources")
    if properties.get("advanced_api", {}).get("properties", {}).get("status", {}).get("const") != "candidate-source-not-released":
        raise ContractFailure("schema must keep the advanced API source candidate unreleased")


def validate_identity(identity: dict[str, Any]) -> None:
    _expect_keys(
        identity,
        {"soc", "ncs_version", "ncs_revision", "zephyr_version", "zephyr_revision", "board", "board_revision"},
        "identity",
    )
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
    if identity != expected:
        raise ContractFailure(f"contract identity mismatch; observed={identity}, expected={expected}")


def validate_sources(sources: list[dict[str, Any]]) -> None:
    lookup = _unique_by(sources, "id", "sources")
    required = {
        "board-schematic", "board-pinctrl", "board-common-dts", "variant-pin-policy",
        "runtime-dts", "nordic-uarte", "nordic-spim", "nordic-spis", "nordic-twim",
        "nordic-twis", "nordic-dedicated-pins", "nordic-csp47-pins",
        "nordic-errata-engineering-b", "competitor-v1-0-17",
    }
    if set(lookup) != required:
        raise ContractFailure(
            f"source set mismatch; missing={sorted(required - set(lookup))}, "
            f"extra={sorted(set(lookup) - required)}"
        )
    for identifier, source in lookup.items():
        _expect_keys(
            source,
            {"id", "kind", "path", "url", "sha256", "hash_mode"},
            f"source {identifier}",
        )
        if source["kind"] == "local":
            if not isinstance(source["path"], str) or source["url"] is not None:
                raise ContractFailure(f"local source {identifier} must use only a repository path")
            path = (REPOSITORY / source["path"]).resolve()
            if not path.is_relative_to(REPOSITORY.resolve()) or not path.is_file():
                raise ContractFailure(f"local source is missing or outside repository: {source['path']}")
            payload = canonical_source_payload(path.read_bytes(), source["hash_mode"])
            digest = hashlib.sha256(payload).hexdigest()
            if digest != source["sha256"]:
                raise ContractFailure(
                    f"local source checksum mismatch for {source['path']}: {digest} != {source['sha256']}"
                )
        else:
            if (
                source["path"] is not None
                or source["sha256"] is not None
                or source["hash_mode"] != "none"
            ):
                raise ContractFailure(f"external source {identifier} must not pretend to be locally pinned")
            url = source["url"]
            if not isinstance(url, str) or not url.startswith("https://"):
                raise ContractFailure(f"external source {identifier} must use HTTPS")
            if source["kind"] == "official" and "docs.nordicsemi.com/" not in url:
                raise ContractFailure(f"official source {identifier} is not on Nordic documentation")
    competitor = lookup["competitor-v1-0-17"]["url"]
    if "a6bb99879aa14cbff362a5478d5f1189848b4200" not in competitor:
        raise ContractFailure("competitor source is not pinned to the reviewed commit")


def validate_surface(contract: dict[str, Any]) -> None:
    surface = contract["stable_surface"]
    _expect_keys(surface, {"singletons", "forbidden_aliases"}, "stable_surface")
    singletons = _unique_by(surface["singletons"], "name", "stable singletons")
    observed = {name: item.get("identity") for name, item in singletons.items()}
    if observed != EXPECTED_SINGLETONS:
        raise ContractFailure(f"stable singleton identity drifted: {observed}")
    if any(item.get("compatibility") != "immutable" for item in singletons.values()):
        raise ContractFailure("every stable singleton must remain immutable")
    if set(surface["forbidden_aliases"]) != EXPECTED_FORBIDDEN_ALIASES:
        raise ContractFailure("forbidden alias set drifted")

    api = contract["advanced_api"]
    _expect_keys(
        api,
        {"status", "header", "namespace", "factory", "allocation", "identity_selector", "selectors", "rules"},
        "advanced_api",
    )
    expected_scalars = {
        "status": "candidate-source-not-released",
        "header": "nucode/SerialFabric.h",
        "namespace": "nucode::arduino",
        "factory": "serialFabric()",
        "allocation": "static-opaque-handles",
        "identity_selector": "kind-and-instance",
    }
    for field, expected in expected_scalars.items():
        if api[field] != expected:
            raise ContractFailure(f"advanced_api.{field} drifted")
    selectors = _unique_by(api["selectors"], "name", "advanced selectors")
    observed_selectors = {
        name: (item.get("return_type"), tuple(item.get("instances", [])))
        for name, item in selectors.items()
    }
    if observed_selectors != EXPECTED_SELECTORS:
        raise ContractFailure(f"advanced selector set drifted: {observed_selectors}")
    rules = api["rules"]
    if not isinstance(rules, list) or len(rules) < 8 or len(set(rules)) != len(rules):
        raise ContractFailure("advanced API rules must be unique and exhaustive")
    joined = " ".join(rules).lower()
    for token in ("raw register", "same serial block", "dma", "singleton", "source candidate"):
        if token not in joined:
            raise ContractFailure(f"advanced API rules omit {token!r}")

    required_sources = (PUBLIC_HEADER_PATH, *BACKEND_SOURCE_PATHS, ROUTE_SOURCE_PATH)
    missing = [path.relative_to(REPOSITORY).as_posix() for path in required_sources if not path.is_file()]
    if missing:
        raise ContractFailure(f"advanced API candidate source is missing: {missing}")
    header = PUBLIC_HEADER_PATH.read_text(encoding="utf-8")
    backend = "\n".join(path.read_text(encoding="utf-8") for path in BACKEND_SOURCE_PATHS)
    route = ROUTE_SOURCE_PATH.read_text(encoding="utf-8")
    for token in ("class SerialFabric", "class UarteHandle", "class SpimHandle", "class SpisHandle", "class TwimHandle", "class TwisHandle"):
        if token not in header:
            raise ContractFailure(f"advanced API header omits {token!r}")
    for token in ("reserveIoResources", "commitIoResources", "rollbackIoResources", "releaseIoResources", "registerSerialFabricAdapter"):
        if token not in backend:
            raise ContractFailure(f"serial fabric backend omits {token!r}")
    if "validateNu54dkSerialFabricRoute" not in route:
        raise ContractFailure("NU54DK serial route validator is missing")


def validate_pin_banks(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    banks = _unique_by(contract["pin_banks"], "id", "pin banks")
    if set(banks) != set(EXPECTED_PIN_BANKS):
        raise ContractFailure("pin bank set drifted")
    for identifier, (port, status, blocks) in EXPECTED_PIN_BANKS.items():
        bank = banks[identifier]
        _expect_keys(
            bank,
            {"id", "port", "silicon_status", "board_status", "allowed_blocks", "signal_sets", "preconditions", "blocked_pins"},
            f"pin bank {identifier}",
        )
        if (
            bank["port"] != port
            or bank["silicon_status"] != "verified"
            or bank["board_status"] != status
            or set(bank["allowed_blocks"]) != blocks
        ):
            raise ContractFailure(f"pin bank identity/status drifted: {identifier}")
        blocked = _unique_by(bank["blocked_pins"], "pin", f"{identifier} blocked pins")
        for pin in blocked:
            if not re.fullmatch(rf"P{port}\.[0-9]{{1,2}}", pin):
                raise ContractFailure(f"{identifier} blocked pin is on the wrong port: {pin}")
    for identifier, expected in EXPECTED_P2_SIGNALS.items():
        if banks[identifier]["signal_sets"] != expected:
            raise ContractFailure(f"Nordic dedicated signal mapping drifted: {identifier}")
    blocked21 = {item["pin"] for item in banks["p2-dedicated21"]["blocked_pins"]}
    if blocked21 != {"P2.7", "P2.8", "P2.9", "P2.10"}:
        raise ContractFailure("P2 dedicated21 board conflicts are incomplete")
    return banks


def _kind(identifier: str) -> str:
    match = re.match(r"^(uarte|spim|spis|twim|twis)", identifier)
    if match is None:
        raise ContractFailure(f"invalid serial identity: {identifier}")
    return match.group(1)


def validate_blocks(contract: dict[str, Any], banks: dict[str, dict[str, Any]]) -> set[str]:
    blocks = _unique_by(contract["blocks"], "id", "serial blocks")
    if set(blocks) != set(EXPECTED_BLOCKS):
        raise ContractFailure("serial block set drifted")
    all_identities: set[str] = set()
    for identifier, (number, base, irq, personalities) in EXPECTED_BLOCKS.items():
        block = blocks[identifier]
        _expect_keys(
            block,
            {"id", "instance", "nonsecure_base", "irq", "personalities", "route_classes", "current_identity", "activation_state"},
            f"block {identifier}",
        )
        if (
            block["instance"] != number
            or block["nonsecure_base"] != base
            or block["irq"] != irq
            or set(block["personalities"]) != personalities
        ):
            raise ContractFailure(f"block identity/personality drifted: {identifier}")
        all_identities.update(personalities)
        expected_kinds = {_kind(item) for item in personalities}
        if set(block["route_classes"]) != expected_kinds:
            raise ContractFailure(f"block route personality set drifted: {identifier}")
        for kind, routes in block["route_classes"].items():
            if not isinstance(routes, list) or not routes or len(set(routes)) != len(routes):
                raise ContractFailure(f"block route set is invalid: {identifier}.{kind}")
            for route in routes:
                if route not in banks or number not in banks[route]["allowed_blocks"]:
                    raise ContractFailure(f"{identifier}.{kind} selects an impossible route class: {route}")
        current = block["current_identity"]
        if current is None:
            if block["activation_state"] != "unassigned":
                raise ContractFailure(f"{identifier} current activation state is inconsistent")
        elif current not in personalities or block["activation_state"] != "current-public":
            raise ContractFailure(f"{identifier} current public identity is inconsistent")
    if len(all_identities) != 23:
        raise ContractFailure(f"serial personality identity count is {len(all_identities)}, expected 23")
    return all_identities


def validate_test_resources(
    contract: dict[str, Any], identities: set[str]
) -> dict[str, dict[str, Any]]:
    resources = _unique_by(contract["test_resources"], "id", "test resources")
    if set(resources) != set(EXPECTED_TEST_RESOURCES):
        raise ContractFailure("board test resource set drifted")
    covered: set[str] = set()
    for identifier, (kind, location, execution_class, expected_identities) in (
        EXPECTED_TEST_RESOURCES.items()
    ):
        resource = resources[identifier]
        _expect_keys(
            resource,
            {
                "id",
                "kind",
                "location",
                "execution_class",
                "board_nets",
                "identities",
                "automation_scope",
                "preconditions",
            },
            f"test resource {identifier}",
        )
        observed_identities = set(resource["identities"])
        if (
            resource["kind"] != kind
            or resource["location"] != location
            or resource["execution_class"] != execution_class
            or observed_identities != expected_identities
        ):
            raise ContractFailure(f"board test resource identity/class drifted: {identifier}")
        if covered & observed_identities:
            raise ContractFailure(f"board test resources overlap: {identifier}")
        covered.update(observed_identities)
        nets = resource["board_nets"]
        if not isinstance(nets, list) or len(nets) < 2 or len(set(nets)) != len(nets):
            raise ContractFailure(f"board test resource nets are incomplete: {identifier}")
        if any(not re.fullmatch(r"P[0-2]\.[0-9]{1,2}", pin) for pin in nets):
            raise ContractFailure(f"board test resource has an invalid net: {identifier}")
        for field in ("automation_scope", "preconditions"):
            values = resource[field]
            if not isinstance(values, list) or not values or len(set(values)) != len(values):
                raise ContractFailure(f"board test resource {field} is incomplete: {identifier}")
    if covered != identities:
        raise ContractFailure("board test resources do not partition all 23 personalities")
    automatic = {
        identity
        for resource in resources.values()
        if resource["execution_class"] == "onboard-automatic"
        for identity in resource["identities"]
    }
    if automatic != {
        "uarte20",
        "uarte21",
        "uarte22",
        "uarte30",
        "twim20",
        "twim21",
        "twim22",
    }:
        raise ContractFailure(f"onboard automatic identity set drifted: {automatic}")
    return resources


def validate_profiles(
    contract: dict[str, Any],
    banks: dict[str, dict[str, Any]],
    identities: set[str],
    resources: dict[str, dict[str, Any]],
) -> None:
    profiles = _unique_by(contract["approved_profiles"], "id", "approved profiles")
    coverage = Counter(item.get("identity") for item in profiles.values())
    if set(coverage) != identities or any(count != 1 for count in coverage.values()):
        raise ContractFailure(
            f"every personality needs exactly one HIL route profile; coverage={dict(coverage)}"
        )
    seen_current: dict[str, dict[str, str]] = {}
    for identifier, profile in profiles.items():
        _expect_keys(
            profile,
            {
                "id",
                "identity",
                "route_class",
                "pins",
                "test_resource",
                "execution_class",
                "preconditions",
                "status",
            },
            f"profile {identifier}",
        )
        personality = profile["identity"]
        kind = _kind(personality)
        resource = resources.get(profile["test_resource"])
        if resource is None or personality not in resource["identities"]:
            raise ContractFailure(f"profile {identifier} selects an unrelated test resource")
        if profile["execution_class"] != resource["execution_class"]:
            raise ContractFailure(f"profile {identifier} execution class differs from its resource")
        bank = banks.get(profile["route_class"])
        if bank is None:
            raise ContractFailure(f"profile {identifier} uses an unknown route class")
        if bank["board_status"] == "not-approved":
            raise ContractFailure(f"profile {identifier} uses a board route that is not approved")
        pins = profile["pins"]
        if not isinstance(pins, dict):
            raise ContractFailure(f"profile {identifier} pins must be an object")
        observed_signals = set(pins)
        if not REQUIRED_SIGNALS[kind].issubset(observed_signals):
            raise ContractFailure(f"profile {identifier} omits required {kind} signals")
        if not observed_signals.issubset(REQUIRED_SIGNALS[kind] | OPTIONAL_SIGNALS[kind]):
            raise ContractFailure(f"profile {identifier} has invalid {kind} signals")
        if len(set(pins.values())) != len(pins):
            raise ContractFailure(f"profile {identifier} reuses a pin for multiple signals")
        for pin in pins.values():
            if not re.fullmatch(rf"P{bank['port']}\.[0-9]{{1,2}}", pin):
                raise ContractFailure(f"profile {identifier} uses {pin} outside {profile['route_class']}")
        if profile["route_class"].startswith("p2-"):
            dedicated = bank["signal_sets"][kind]
            if any(dedicated.get(signal) != pin for signal, pin in pins.items()):
                raise ContractFailure(f"profile {identifier} violates the dedicated P2 signal map")
        if profile["route_class"] == "p1-flexible":
            if kind not in {"twim", "twis"} and {"P1.2", "P1.3"} & set(pins.values()):
                raise ContractFailure(f"profile {identifier} drives the board I2C nets as {kind}")
            forbidden = {"P1.0", "P1.1", "P1.8", "P1.9", "P1.11", "P1.13"}
            if forbidden & set(pins.values()):
                raise ContractFailure(f"profile {identifier} uses a blocked P1 pin")
            if {"P1.4", "P1.5", "P1.6", "P1.7"} & set(pins.values()):
                joined = " ".join(profile["preconditions"]).lower()
                if kind == "uarte":
                    if (
                        "dap uart switch" not in joined
                        or "enabled" not in joined
                        or (personality != "uarte20" and "console" not in joined)
                    ):
                        raise ContractFailure(f"profile {identifier} omits DAP UART handover")
                elif "console" not in joined or "dap uart switch" not in joined or "disabled" not in joined:
                    raise ContractFailure(f"profile {identifier} omits console/DAP isolation")
        if profile["route_class"] == "p0-flexible" and personality != "uarte30":
            joined = " ".join(profile["preconditions"]).lower()
            if "dap uart switch" not in joined or "serial1" not in joined:
                raise ContractFailure(f"profile {identifier} omits Serial1/DAP isolation")
        if profile["status"] == "current-verified":
            seen_current[personality] = pins
    if seen_current != EXPECTED_CURRENT_PROFILES:
        raise ContractFailure(f"current verified routes drifted: {seen_current}")


def validate_lifecycle_and_errata(contract: dict[str, Any]) -> None:
    lifecycle = contract["lifecycle"]
    _expect_keys(
        lifecycle,
        {"activation_order", "deactivation_order", "dma_buffer_states", "callback_context", "timeout_policy"},
        "lifecycle",
    )
    if len(lifecycle["activation_order"]) < 5 or len(lifecycle["deactivation_order"]) < 5:
        raise ContractFailure("activation/deactivation lifecycle is incomplete")
    if set(lifecycle["dma_buffer_states"]) != {
        "application-owned", "queued", "dma-owned", "completed", "cancelled", "error"
    }:
        raise ContractFailure("DMA buffer state machine drifted")
    if lifecycle["callback_context"] != "bounded-isr-event-deferred-to-thread":
        raise ContractFailure("callback context contract drifted")
    if lifecycle["timeout_policy"] != "bounded-stop-then-fail-closed-reset-required":
        raise ContractFailure("timeout policy contract drifted")
    observed_errata = {(item.get("id"), item.get("peripheral")) for item in contract["errata"]}
    if observed_errata != EXPECTED_ERRATA:
        raise ContractFailure(f"M24 errata coverage drifted: {observed_errata}")
    if len(contract["completion_gates"]) < 7:
        raise ContractFailure("M24 completion gates are incomplete")


def validate_manifest_alignment(contract: dict[str, Any], identities: set[str]) -> None:
    manifest = strict_json_object(MANIFEST_PATH)
    for field in ("soc", "ncs_version", "ncs_revision", "zephyr_version", "zephyr_revision", "board", "board_revision"):
        if manifest["identity"][field] != contract["identity"][field]:
            raise ContractFailure(f"manifest and M24 identity differ at {field}")
    m24 = {item["id"]: item for item in manifest["instances"] if item["milestone"] == "M24"}
    if set(m24) != identities:
        raise ContractFailure("M24 contract and peripheral manifest identity sets differ")
    grouped: dict[str, set[str]] = {}
    for item in m24.values():
        grouped.setdefault(item["sharing_group"], set()).add(item["id"])
    for block, (_number, _base, _irq, personalities) in EXPECTED_BLOCKS.items():
        if grouped.get(block) != personalities:
            raise ContractFailure(f"manifest personality group drifted: {block}")
    public = {item["public_object"]: item["id"] for item in m24.values() if item["public_object"]}
    if public != EXPECTED_SINGLETONS:
        raise ContractFailure("manifest public objects differ from the M24 contract")
    candidates = identities - set(EXPECTED_SINGLETONS.values())
    for identity in candidates:
        item = m24[identity]
        states = item["states"]
        expected_dma = {
            "uarte": "double_buffered",
            "spim": "asynchronous",
            "spis": "double_buffered",
            "twim": "asynchronous",
            "twis": "double_buffered",
        }[item["kind"]]
        if (
            states["source"] != "implemented"
            or states["exposure"] != "internal"
            or states["build"] != "pass"
            or states["semantic"] != "pass"
            or states["hil"] != "pass"
            or states["concurrent_hil"] != "not_run"
            or item["dma"]["public_mode"] != expected_dma
            or not item["evidence"]
        ):
            raise ContractFailure(f"functionally verified candidate identity state drifted: {identity}")


def validate_repository_routes() -> None:
    pinctrl = (
        REPOSITORY
        / "board_package"
        / "NU54DK_Zephyr_DTS"
        / "boards"
        / "nucode"
        / "nu54dk"
        / "nu54dk-pinctrl.dtsi"
    ).read_text(encoding="utf-8")
    for token in (
        "NRF_PSEL(UART_TX, 1, 4)", "NRF_PSEL(UART_RX, 1, 5)",
        "NRF_PSEL(UART_RTS, 1, 6)", "NRF_PSEL(UART_CTS, 1, 7)",
        "NRF_PSEL(UART_TX, 0, 0)", "NRF_PSEL(UART_RX, 0, 1)",
        "NRF_PSEL(UART_RTS, 0, 2)", "NRF_PSEL(UART_CTS, 0, 3)",
        "NRF_PSEL(SPIM_SCK, 2, 1)", "NRF_PSEL(SPIM_MOSI, 2, 2)",
        "NRF_PSEL(SPIM_MISO, 2, 4)", "NRF_PSEL(TWIM_SDA, 1, 2)",
        "NRF_PSEL(TWIM_SCL, 1, 3)",
    ):
        if token not in pinctrl:
            raise ContractFailure(f"current board pinctrl route is missing: {token}")
    common = (
        REPOSITORY
        / "board_package"
        / "NU54DK_Zephyr_DTS"
        / "boards"
        / "nucode"
        / "nu54dk"
        / "nu54dk_cpuapp_common.dtsi"
    ).read_text(encoding="utf-8")
    for token in ("zephyr,console = &uart20;", "&uart20", "&i2c22"):
        if token not in common:
            raise ContractFailure(f"board owner route is missing: {token}")


def validate_contract(contract: dict[str, Any]) -> set[str]:
    _expect_keys(
        contract,
        {"schema_version", "identity", "sources", "stable_surface", "advanced_api", "pin_banks", "blocks", "test_resources", "approved_profiles", "lifecycle", "errata", "completion_gates"},
        "contract",
    )
    if contract["schema_version"] != 2:
        raise ContractFailure("unsupported serial-fabric contract schema_version")
    validate_identity(contract["identity"])
    validate_sources(contract["sources"])
    validate_surface(contract)
    banks = validate_pin_banks(contract)
    identities = validate_blocks(contract, banks)
    resources = validate_test_resources(contract, identities)
    validate_profiles(contract, banks, identities, resources)
    validate_lifecycle_and_errata(contract)
    validate_manifest_alignment(contract, identities)
    validate_repository_routes()
    return identities


def validate_ncs_dts(contract: dict[str, Any], ncs_root: Path) -> None:
    manifest = strict_json_object(MANIFEST_PATH)
    source_texts: list[str] = []
    for source in manifest["identity"]["soc_dts_sources"]:
        path = ncs_root.resolve() / source["path"]
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise ContractFailure(f"cannot read pinned NCS DTS {path}: {error}") from error
        digest = hashlib.sha256(payload).hexdigest()
        if digest != source["sha256"]:
            raise ContractFailure(f"NCS DTS checksum mismatch: {path}")
        source_texts.append(payload.decode("utf-8"))
    dts = "\n".join(source_texts)
    node_offsets = {0: "4a000", 20: "c6000", 21: "c7000", 22: "c8000", 30: "104000"}
    for block in contract["blocks"]:
        number = block["instance"]
        for identity in block["personalities"]:
            kind = _kind(identity)
            if kind in {"spim", "spis"}:
                label = f"spi{number:02d}"
            elif kind in {"twim", "twis"}:
                label = f"i2c{number:02d}"
            else:
                label = f"uart{number:02d}"
            match = re.search(
                rf"(?ms)^\s*{re.escape(label)}:\s+[^{{]+\{{(.*?)^\s*\}};",
                dts,
            )
            if match is None:
                raise ContractFailure(f"pinned NCS DTS node is missing: {label}")
            body = match.group(1)
            if f"reg = <0x{node_offsets[number]} 0x1000>;" not in body:
                raise ContractFailure(f"pinned NCS DTS base drifted: {label}")
            if f"interrupts = <{block['irq']} NRF_DEFAULT_IRQ_PRIORITY>;" not in body:
                raise ContractFailure(f"pinned NCS DTS IRQ drifted: {label}")


def _pins(profile: dict[str, Any]) -> str:
    return ", ".join(f"{signal.upper()} {pin}" for signal, pin in profile["pins"].items())


def _conditions(items: list[str]) -> str:
    return "<br>".join(items) if items else "—"


def render_document(contract: dict[str, Any]) -> str:
    identity = contract["identity"]
    lines = [
        "# M24 작업 1~5 — Serial Fabric 전 instance와 EasyDMA",
        "",
        "> 이 파일은 `variants/nu54dk/serial-fabric-contract.json`에서 자동 생성합니다. 직접 수정하지 마세요.",
        "> 현재 판정은 **공통 backend와 23개 personality adapter의 source/build/semantic 및 승인 route 단독 기능 HIL 완료**입니다. 최대 동시성·성능·soak와 공개 통합은 아직 완료되지 않았습니다.",
        "",
        "| 항목 | 값 |",
        "| --- | --- |",
        "| 문서 ID | `DESIGN-M24-SERIAL-FABRIC-001` |",
        "| 제품선 | `v0.4.0` / M24 |",
        f"| SoC / SDK | `{identity['soc']}` / `{identity['ncs_version']}` / Zephyr `{identity['zephyr_version']}` |",
        f"| Board | `{identity['board']}` / `{identity['board_revision']}` |",
        "| 상태 | 작업 1~5 source/build/semantic 완료 — 23개 personality 단독 기능 HIL PASS, 최대 동시성·성능·soak 대기 |",
        "| 갱신일 | 2026-09-06 |",
        "",
        "## 1. 이번 작업의 경계",
        "",
        "이 계약은 23개 serial personality의 실제 identity, 공유 block, 허용 pin bank, 현재 route,",
        "고급 선택 API와 DMA 수명주기를 고정한다. 작업 2에서 allocation-free typed handle, 원자적",
        "route/DMA lease, bounded stop과 fail-closed handover를 구현했고 작업 3~5에서 UARTE, SPIM/SPIS,",
        "TWIM/TWIS direct nrfx adapter를 연결했다. Kconfig는 기본 off인 v0.4.0 후보다.",
        "단독 기능 HIL을 통과했지만 최대 동시성·soak와 설치 package gate 전에는 stable 공개 지원으로 승격하지 않는다.",
        "",
        "M24의 후속 순서는 다음과 같다.",
        "",
        "1. **작업 1(완료):** route/API/errata 계약과 자동 drift 검사",
        "2. **작업 2(완료):** 공통 serial-fabric backend, typed handle과 personality handover",
        "3. **작업 3(완료):** UARTE 5개와 async RX/TX DMA source/build/semantic",
        "4. **작업 4(완료):** SPIM/SPIS 각 5개와 sync/async·double buffer source/build/semantic",
        "5. **작업 5(완료):** TWIM/TWIS 각 4개와 repeated-start·target double buffer source/build/semantic",
        "6. **작업 6(진행):** 온보드 기본, UART Fixture 101~103, SPI Fixture 201~203과 TWI Fixture 301 PASS; 최대 동시성·성능·soak 대기",
        "",
        "현재 온보드 증거는 [41번 기록](<../04_검증 기록/41_M24_M26_온보드_protocol_교정과_실기_재검증.md>),",
        "UART Fixture 101~103은 [44번](<../04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>)·[45번](<../04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>)·[46번](<../04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>),",
        "SPI Fixture 201~203은 [47번](<../04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>)·[48번](<../04_검증 기록/48_M24_Fixture_202_SPI_실기_검증.md>)·[49번 기록](<../04_검증 기록/49_M24_Fixture_203_SPI_실기_검증.md>)을 따른다.",
        "TWI Fixture 301은 [50번 기록](<../04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>)을 따른다.",
        "`functional-hil-pass`는 해당 단독 route의 기능 HIL 판정이며 전체 동시성·soak 또는 공개 지원 완료가 아니다.",
        "",
        "## 2. 공개 객체와 고급 API",
        "",
        "기존 Arduino 객체의 identity는 바꾸지 않는다.",
        "",
        "| 공개 객체 | 실제 identity | 호환 계약 |",
        "| --- | --- | --- |",
    ]
    for item in contract["stable_surface"]["singletons"]:
        lines.append(f"| `{item['name']}` | `{item['identity']}` | `{item['compatibility']}` |")
    aliases = "`, `".join(contract["stable_surface"]["forbidden_aliases"])
    lines.extend(
        [
            "",
            f"독립 hardware처럼 보이는 가짜 별칭 `{aliases}`은 만들지 않는다.",
            "",
            "고급 API는 향후 `<nucode/SerialFabric.h>`의 `nucode::arduino::serialFabric()`에서",
            "allocation 없는 typed handle로 제공한다. Raw base address는 받지 않고 kind+instance로만",
            "선택한다. 계약 단계에서는 header 자체를 공개하지 않는다.",
            "",
            "| 선택 함수 | 반환 handle | 허용 instance |",
            "| --- | --- | --- |",
        ]
    )
    for item in contract["advanced_api"]["selectors"]:
        values = ", ".join(str(number) for number in item["instances"])
        lines.append(f"| `{item['name']}()` | `{item['return_type']}` | {values} |")
    lines.extend(["", "### API 불변 조건", ""])
    lines.extend(f"- {rule}" for rule in contract["advanced_api"]["rules"])

    lines.extend(
        [
            "",
            "## 3. 물리 block과 가능한 personality",
            "",
            "같은 행은 register base와 IRQ를 공유하므로 단 하나의 personality만 active일 수 있다.",
            "",
            "| Block | Non-secure base / IRQ | Personality | 현재 identity | 허용 route class |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for block in contract["blocks"]:
        routes = "; ".join(
            f"{kind.upper()}: {', '.join(values)}" for kind, values in block["route_classes"].items()
        )
        current = f"`{block['current_identity']}`" if block["current_identity"] else "—"
        personalities = ", ".join(f"`{item}`" for item in block["personalities"])
        lines.append(
            f"| `{block['id']}` | `{block['nonsecure_base']}` / {block['irq']} | "
            f"{personalities} | {current} | {routes} |"
        )

    lines.extend(
        [
            "",
            "## 4. Pin bank 판정",
            "",
            "| Route class | Silicon | NU54DK 판정 | Block | 조건·차단 이유 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for bank in contract["pin_banks"]:
        details = list(bank["preconditions"])
        details.extend(f"{item['pin']}: {item['reason']}" for item in bank["blocked_pins"])
        blocks = ", ".join(str(number) for number in bank["allowed_blocks"])
        lines.append(
            f"| `{bank['id']}` | {bank['silicon_status']} | **{bank['board_status']}** | "
            f"{blocks} | {_conditions(details)} |"
        )
    lines.extend(
        [
            "",
            "P2의 `dedicated21`은 실리콘 pin matrix에는 존재하지만 P2.7~P2.10이 LED, MOD_SWO와",
            "PMIC_PG/PMIC_CE에 연결돼 기본 보드에서 승인하지 않는다. UARTE/SPIM/SPIS21은 P1 경로를",
            "사용한다. P0의 non-UARTE 경로는 점퍼가 아니라 보드의 DAP UART switch를 끈 상태가 필요하다.",
            "TWI Fixture 301은 target TWIS 내부 pull-up을 사용하며 외부 pull-up과 보드 간 전원 rail을 연결하지 않는다.",
            "",
            "## 5. 보드 자체 시험 자원",
            "",
            "회로도 9쪽 전수를 다시 대조해 USB와 온보드 회로만으로 자동화할 수 있는 단독 데이터 경로와",
            "외부 fixture가 필요한 경로를 분리했다. `onboard-automatic`은 구현 완료를 뜻하지 않으며,",
            "M24 작업 3~5의 image/runner로 물리 HIL을 자동 실행할 수 있다는 시험 자원 판정이다.",
            "",
            "| 자원 | 위치 / 실행 | 단독 HIL의 primary identity | 보드 net | 자동화 범위 | 선행조건 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for resource in contract["test_resources"]:
        identities = ", ".join(f"`{item}`" for item in resource["identities"])
        nets = ", ".join(resource["board_nets"])
        scope = ", ".join(resource["automation_scope"])
        lines.append(
            f"| `{resource['id']}` | {resource['location']} / **{resource['execution_class']}** | "
            f"{identities} | {nets} | {scope} | {_conditions(resource['preconditions'])} |"
        )
    automatic_count = sum(
        len(resource["identities"])
        for resource in contract["test_resources"]
        if resource["execution_class"] == "onboard-automatic"
    )
    fixture_count = (
        len({item for block in contract["blocks"] for item in block["personalities"]})
        - automatic_count
    )
    lines.extend(
        [
            "",
            f"23개 identity 중 {automatic_count}개는 USB와 온보드 회로만으로 단독 data-path HIL을 자동화할 수 있고,",
            f"나머지 {fixture_count}개는 외부 loopback, controller/target 또는 pull-up fixture가 필요하다.",
            "모든 23개 identity의 build, activation, ownership-conflict와 fail-closed semantic 검사는",
            "fixture 없이 자동화한다. P1 DAP UART를 시험할 때 P0 DAP UART를 제어·결과 채널로 사용하고",
            "반대로 UARTE30을 시험할 때는 UARTE20을 제어·결과 채널로 사용한다.",
            "",
            "## 6. 단독 HIL 기준 route",
            "",
            "`current-verified`는 기존 v0.3.0 증거가 있는 route, `functional-hil-pass`는 M24 단독 기능 HIL을",
            "통과한 고정 route다. 두 상태 모두 고급 API의 v0.4.0 stable 공개 승인을 뜻하지 않는다.",
            "",
            "| Identity | Route | 핀 | 실행 분류 / 자원 | 상태 | 선행조건 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for profile in contract["approved_profiles"]:
        lines.append(
            f"| `{profile['identity']}` | `{profile['route_class']}` | {_pins(profile)} | "
            f"**{profile['execution_class']}** / `{profile['test_resource']}` | "
            f"**{profile['status']}** | {_conditions(profile['preconditions'])} |"
        )

    lines.extend(["", "## 7. DMA와 lifecycle", "", "### 활성화", ""])
    lines.extend(f"{index}. {item}" for index, item in enumerate(contract["lifecycle"]["activation_order"], 1))
    lines.extend(["", "### 종료·취소", ""])
    lines.extend(f"{index}. {item}" for index, item in enumerate(contract["lifecycle"]["deactivation_order"], 1))
    states = ", ".join(f"`{item}`" for item in contract["lifecycle"]["dma_buffer_states"])
    lines.extend(
        [
            "",
            f"Buffer 상태 집합은 {states}다. 완료·취소·오류 event 전에는 application이 buffer를",
            "재사용할 수 없다. ISR은 bounded event만 기록하고 사용자 callback은 thread 문맥으로 넘긴다.",
            "Bounded stop으로 DMA 정지를 증명하지 못하면 해당 block을 fail-closed로 latch하고 reset 전",
            "재사용을 금지한다.",
            "",
            "## 8. M24에 적용할 errata",
            "",
            "| ID | Peripheral | 구현·시험 의무 |",
            "| --- | --- | --- |",
        ]
    )
    for item in contract["errata"]:
        lines.append(f"| {item['id']} | {item['peripheral'].upper()} | {item['obligation']} |")

    lines.extend(["", "## 9. M24 완료 gate", ""])
    lines.extend(f"- {item}" for item in contract["completion_gates"])
    lines.extend(
        [
            "",
            "최대 동시성은 이름 개수가 아니라 충돌 없는 실제 topology로 판정한다. 기준 topology는",
            "`SPIM00 + UARTE20 console + UARTE21(P1.10/P1.14) + TWIM22 + UARTE30`의 다섯 block이다.",
            "UARTE21 단독 시험은 P1 DAP UART를 재사용하지만 이 최대 동시 topology에서는",
            "UARTE20과 핀이 겹치지 않는 P1.10/P1.14 connector fixture route를 사용한다.",
            "각 handle의 DMA buffer는 겹치지 않아야 하며 LED/PMIC/DAP 전기 상태도 함께 기록한다.",
            "",
            "[42번 범위 합의](<../04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)에 따라 두 NU54DK의",
            "실제 통신·기대 데이터·DMA·복구·허용 동시성·soak를 검증한다. 외부 계측기는 필수가 아니며",
            "정밀 파형·전력·부품별 호환성을 보증하지 않는다. Errata 대응과 안전한 배선 조건은 유지하고",
            "기능 시험이 성립하지 않은 항목은 HOLD로 남긴다.",
            "",
            "## 10. 단일 원본과 검사",
            "",
            "- Contract: [`variants/nu54dk/serial-fabric-contract.json`](../../variants/nu54dk/serial-fabric-contract.json)",
            "- Schema: [`tools/peripheral/serial-fabric-contract.schema.json`](../../tools/peripheral/serial-fabric-contract.schema.json)",
            "- 검증·생성기: [`tools/peripheral/verify_m24_serial_contract.py`](../../tools/peripheral/verify_m24_serial_contract.py)",
            "- M23 inventory: [`variants/nu54dk/peripheral-manifest.json`](../../variants/nu54dk/peripheral-manifest.json)",
            "",
            "검증기는 exact block/base/IRQ/personality, 6개 보드 시험 자원, 23개 HIL route, P2 dedicated pin map, 보드 source",
            "checksum, stable singleton, 가짜 alias, lifecycle·errata, candidate/stable 경계와 생성 문서 drift를",
            "검사한다. `--ncs-root`를 주면 고정 NCS DTS의 checksum, node base와 IRQ도 대조한다.",
            "",
            "## 11. 근거",
            "",
        ]
    )
    for source in contract["sources"]:
        if source["kind"] == "local":
            target = "../../" + source["path"].replace(" ", "%20")
            lines.append(
                f"- [{source['id']}]({target}) — SHA-256 `{source['sha256']}` "
                f"(`{source['hash_mode']}`)"
            )
        else:
            lines.append(f"- [{source['id']}]({source['url']})")
    lines.append("")
    return "\n".join(lines)


def _check_or_write(path: Path, expected: str, write: bool) -> None:
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8", newline="\n")
        print(f"M24_GENERATED={path.relative_to(REPOSITORY).as_posix()}")
        return
    try:
        observed = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContractFailure(f"generated file is missing: {path}: {error}") from error
    if observed != expected:
        raise ContractFailure(
            f"generated file drifted: {path.relative_to(REPOSITORY)}; run "
            "python tools/peripheral/verify_m24_serial_contract.py --write"
        )


def run(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ncs-root", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(arguments)

    schema = strict_json_object(SCHEMA_PATH)
    contract = strict_json_object(CONTRACT_PATH)
    validate_schema_contract(schema)
    identities = validate_contract(contract)
    if args.ncs_root is not None:
        validate_ncs_dts(contract, args.ncs_root)
    _check_or_write(DOCUMENT_PATH, render_document(contract), args.write)
    automatic = sum(
        len(resource["identities"])
        for resource in contract["test_resources"]
        if resource["execution_class"] == "onboard-automatic"
    )
    print(
        f"M24_SERIAL_CONTRACT_PASS=blocks:{len(contract['blocks'])};"
        f"identities:{len(identities)};profiles:{len(contract['approved_profiles'])};"
        f"onboard:{automatic};fixture:{len(identities) - automatic}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except ContractFailure as error:
        print(f"M24_SERIAL_CONTRACT_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
