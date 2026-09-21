"""! @brief compiler probe와 선언을 안정된 capability 집합으로 해석합니다. """

from __future__ import annotations

from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from typing import Iterable
from typing import Sequence
import json
import re

from .common import (
    AdapterError,
    CAPABILITY_DECLARATION_SCHEMA_VERSION,
    CAPABILITY_REGISTRY_SCHEMA_VERSION,
    CAPABILITY_RESOLUTION_SCHEMA_VERSION,
    DuplicateJsonKeyError,
    atomic_write_json,
    canonical_path,
    is_within,
    strict_json_object,
)


CAPABILITY_ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*")
ROLE_ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
CAPACITY_ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*")
CONFIG_PATTERN = re.compile(r"CONFIG_[A-Z0-9_]+=(?:y|n|[0-9]+|\"[^\"\r\n]*\")")
SOURCE_GATE_PATTERN = re.compile(r"CONFIG_[A-Z0-9_]+")
CAPACITY_CONFIG_PATTERN = re.compile(r"CONFIG_[A-Z0-9_]+=\{value\}")


## @brief strict JSON object를 capability 오류로 변환하여 읽습니다.
def _load_strict_json(path: Path, error_code: str) -> dict[str, Any]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=strict_json_object
        )
    except DuplicateJsonKeyError as error:
        raise AdapterError(f"[NU54:{error_code}] {error}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AdapterError(
            f"[NU54:{error_code}] JSON을 읽지 못했습니다: {path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise AdapterError(f"[NU54:{error_code}] JSON root가 object가 아닙니다: {path}")
    return document


## @brief 문자열 배열의 형식·중복을 한 번에 검증합니다.
def _string_array(
    value: Any,
    *,
    owner: str,
    field: str,
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AdapterError(
            f"[NU54:E_CAPABILITY_SCHEMA] {owner}.{field}는 문자열 배열이어야 합니다."
        )
    if len(value) != len(set(value)):
        raise AdapterError(
            f"[NU54:E_CAPABILITY_SCHEMA] {owner}.{field}에 중복 값이 있습니다."
        )
    if pattern is not None:
        invalid = [item for item in value if pattern.fullmatch(item) is None]
        if invalid:
            raise AdapterError(
                f"[NU54:E_CAPABILITY_SCHEMA] {owner}.{field} 값 형식이 잘못되었습니다: {invalid}"
            )
    return list(value)


## @brief capability registry와 probe symbol mapping을 엄격히 검증합니다.
def load_capability_registry(platform_root: Path) -> dict[str, Any]:
    path = platform_root / "variants" / "nu54dk" / "capability-registry.json"
    document = _load_strict_json(path, "E_CAPABILITY_SCHEMA")
    allowed = {
        "schema_version",
        "probe_mapping_version",
        "defaults",
        "source_roots",
        "capabilities",
        "roles",
        "capacities",
        "probe_symbols",
    }
    if set(document) != allowed or document.get("schema_version") != CAPABILITY_REGISTRY_SCHEMA_VERSION:
        raise AdapterError(
            "[NU54:E_CAPABILITY_SCHEMA] capability registry field/schema가 올바르지 않습니다."
        )
    mapping_version = document.get("probe_mapping_version")
    if not isinstance(mapping_version, int) or isinstance(mapping_version, bool) or mapping_version < 1:
        raise AdapterError(
            "[NU54:E_CAPABILITY_SCHEMA] probe_mapping_version은 양의 정수여야 합니다."
        )

    defaults = _string_array(
        document.get("defaults"),
        owner="registry",
        field="defaults",
        pattern=CAPABILITY_ID_PATTERN,
    )
    source_roots = _string_array(
        document.get("source_roots"), owner="registry", field="source_roots"
    )
    for value in source_roots:
        source_root = canonical_path(platform_root / value)
        if (
            Path(value).is_absolute()
            or PureWindowsPath(value).is_absolute()
            or value.startswith(("\\\\", "//"))
            or not is_within(source_root, platform_root)
            or not source_root.is_dir()
        ):
            raise AdapterError(
                f"[NU54:E_CAPABILITY_PATH] source root가 없거나 platform을 벗어납니다: {value}"
            )
    capability_items = document.get("capabilities")
    if not isinstance(capability_items, list):
        raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] capabilities는 배열이어야 합니다.")
    capabilities: dict[str, dict[str, Any]] = {}
    capability_fields = {
        "id",
        "requires",
        "requires_any_role",
        "conflicts",
        "conf",
        "overlays",
        "sources",
        "source_gates",
    }
    for item in capability_items:
        if not isinstance(item, dict) or set(item) != capability_fields:
            raise AdapterError(
                "[NU54:E_CAPABILITY_SCHEMA] capability field가 올바르지 않습니다."
            )
        identifier = item.get("id")
        if not isinstance(identifier, str) or CAPABILITY_ID_PATTERN.fullmatch(identifier) is None:
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] capability ID가 잘못되었습니다: {identifier}")
        if identifier in capabilities:
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] capability ID가 중복됩니다: {identifier}")
        normalized = {
            "id": identifier,
            "requires": _string_array(
                item.get("requires"), owner=identifier, field="requires", pattern=CAPABILITY_ID_PATTERN
            ),
            "requires_any_role": _string_array(
                item.get("requires_any_role"),
                owner=identifier,
                field="requires_any_role",
                pattern=ROLE_ID_PATTERN,
            ),
            "conflicts": _string_array(
                item.get("conflicts"), owner=identifier, field="conflicts", pattern=CAPABILITY_ID_PATTERN
            ),
            "conf": _string_array(
                item.get("conf"), owner=identifier, field="conf", pattern=CONFIG_PATTERN
            ),
            "overlays": _string_array(item.get("overlays"), owner=identifier, field="overlays"),
            "sources": _string_array(item.get("sources"), owner=identifier, field="sources"),
            "source_gates": _string_array(
                item.get("source_gates"),
                owner=identifier,
                field="source_gates",
                pattern=SOURCE_GATE_PATTERN,
            ),
        }
        for value in normalized["overlays"]:
            overlay = canonical_path(platform_root / value)
            if (
                Path(value).is_absolute()
                or PureWindowsPath(value).is_absolute()
                or value.startswith(("\\\\", "//"))
                or not is_within(overlay, platform_root)
                or not overlay.is_file()
            ):
                raise AdapterError(
                    f"[NU54:E_CAPABILITY_PATH] capability overlay가 없거나 root를 벗어납니다: {value}"
                )
        for value in normalized["sources"]:
            source = canonical_path(platform_root / value)
            if (
                Path(value).is_absolute()
                or PureWindowsPath(value).is_absolute()
                or value.startswith(("\\\\", "//"))
                or not is_within(source, platform_root)
                or not source.exists()
            ):
                raise AdapterError(
                    f"[NU54:E_CAPABILITY_PATH] capability source가 없거나 root를 벗어납니다: {value}"
                )
        capabilities[identifier] = normalized

    capacity_items = document.get("capacities")
    if not isinstance(capacity_items, list):
        raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] capacities는 배열이어야 합니다.")
    capacities: dict[str, dict[str, Any]] = {}
    capacity_fields = {"id", "aggregation", "minimum", "maximum", "unit", "conf"}
    for item in capacity_items:
        if not isinstance(item, dict) or set(item) != capacity_fields:
            raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] capacity field가 올바르지 않습니다.")
        identifier = item.get("id")
        aggregation = item.get("aggregation")
        minimum = item.get("minimum")
        maximum = item.get("maximum")
        unit = item.get("unit")
        conf = _string_array(
            item.get("conf"),
            owner=str(identifier),
            field="conf",
            pattern=CAPACITY_CONFIG_PATTERN,
        )
        if not isinstance(identifier, str) or CAPACITY_ID_PATTERN.fullmatch(identifier) is None:
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] capacity ID가 잘못되었습니다: {identifier}")
        if identifier in capacities:
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] capacity ID가 중복됩니다: {identifier}")
        if aggregation not in {"maximum", "sum", "identical"}:
            raise AdapterError(
                f"[NU54:E_CAPABILITY_SCHEMA] capacity 집계 방식이 잘못되었습니다: {identifier}"
            )
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or minimum < 0
            or maximum < minimum
            or not isinstance(unit, str)
            or not unit
        ):
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] capacity 범위가 잘못되었습니다: {identifier}")
        capacities[identifier] = {**item, "conf": conf}

    role_items = document.get("roles")
    if not isinstance(role_items, list):
        raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] roles는 배열이어야 합니다.")
    roles: dict[str, dict[str, Any]] = {}
    role_fields = {"id", "capabilities", "capacities", "conflicts"}
    for item in role_items:
        if not isinstance(item, dict) or set(item) != role_fields:
            raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] role field가 올바르지 않습니다.")
        identifier = item.get("id")
        if not isinstance(identifier, str) or ROLE_ID_PATTERN.fullmatch(identifier) is None:
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] role ID가 잘못되었습니다: {identifier}")
        if identifier in roles:
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] role ID가 중복됩니다: {identifier}")
        role_capacities = item.get("capacities")
        if not isinstance(role_capacities, dict) or not all(
            isinstance(key, str)
            and isinstance(value, int)
            and not isinstance(value, bool)
            for key, value in role_capacities.items()
        ):
            raise AdapterError(
                f"[NU54:E_CAPABILITY_SCHEMA] role capacity가 잘못되었습니다: {identifier}"
            )
        roles[identifier] = {
            "id": identifier,
            "capabilities": _string_array(
                item.get("capabilities"),
                owner=identifier,
                field="capabilities",
                pattern=CAPABILITY_ID_PATTERN,
            ),
            "capacities": dict(role_capacities),
            "conflicts": _string_array(
                item.get("conflicts"), owner=identifier, field="conflicts", pattern=ROLE_ID_PATTERN
            ),
        }

    symbol_items = document.get("probe_symbols")
    if not isinstance(symbol_items, list):
        raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] probe_symbols는 배열이어야 합니다.")
    probe_symbols: dict[str, str] = {}
    for item in symbol_items:
        if not isinstance(item, dict) or set(item) != {"symbol", "capability"}:
            raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] probe symbol field가 올바르지 않습니다.")
        symbol = item.get("symbol")
        capability = item.get("capability")
        if not isinstance(symbol, str) or not symbol or "\n" in symbol or "\r" in symbol:
            raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] probe symbol이 잘못되었습니다.")
        if symbol in probe_symbols:
            raise AdapterError(f"[NU54:E_CAPABILITY_SCHEMA] probe symbol이 중복됩니다: {symbol}")
        if not isinstance(capability, str):
            raise AdapterError("[NU54:E_CAPABILITY_SCHEMA] probe capability가 문자열이 아닙니다.")
        probe_symbols[symbol] = capability

    capability_ids = set(capabilities)
    role_ids = set(roles)
    capacity_ids = set(capacities)
    unknown_capabilities = set(defaults) - capability_ids
    unknown_capacities: set[str] = set()
    unknown_roles: set[str] = set()
    for item in capabilities.values():
        unknown_capabilities.update(set(item["requires"]) - capability_ids)
        unknown_capabilities.update(set(item["conflicts"]) - capability_ids)
        unknown_roles.update(set(item["requires_any_role"]) - role_ids)
    for item in roles.values():
        unknown_capabilities.update(set(item["capabilities"]) - capability_ids)
        unknown_capacities.update(set(item["capacities"]) - capacity_ids)
        unknown_roles.update(set(item["conflicts"]) - role_ids)
    unknown_capabilities.update(set(probe_symbols.values()) - capability_ids)
    if unknown_capabilities or unknown_capacities or unknown_roles:
        raise AdapterError(
            "[NU54:E_CAPABILITY_REFERENCE] registry 참조가 정의되지 않았습니다: "
            f"capabilities={sorted(unknown_capabilities)}, capacities={sorted(unknown_capacities)}, "
            f"roles={sorted(unknown_roles)}"
        )
    return {
        "schema_version": document["schema_version"],
        "probe_mapping_version": mapping_version,
        "defaults": defaults,
        "source_roots": source_roots,
        "capabilities": capabilities,
        "roles": roles,
        "capacities": capacities,
        "probe_symbols": probe_symbols,
        "path": path,
    }


## @brief sketch의 공개 build declaration을 읽거나 빈 선언을 반환합니다.
def load_capability_declaration(sketch_root: Path) -> dict[str, Any]:
    path = sketch_root / "nucode-build.json"
    if not path.is_file():
        return {
            "schema_version": CAPABILITY_DECLARATION_SCHEMA_VERSION,
            "capabilities": [],
            "roles": [],
            "capacities": {},
            "path": None,
        }
    document = _load_strict_json(path, "E_CAPABILITY_DECLARATION")
    allowed = {"schema_version", "capabilities", "roles", "capacities"}
    if set(document) != allowed or document.get("schema_version") != CAPABILITY_DECLARATION_SCHEMA_VERSION:
        raise AdapterError(
            "[NU54:E_CAPABILITY_DECLARATION] build declaration field/schema가 올바르지 않습니다."
        )
    capabilities = _string_array(
        document.get("capabilities"),
        owner="declaration",
        field="capabilities",
        pattern=CAPABILITY_ID_PATTERN,
    )
    roles = _string_array(
        document.get("roles"), owner="declaration", field="roles", pattern=ROLE_ID_PATTERN
    )
    capacities = document.get("capacities")
    if not isinstance(capacities, dict) or not all(
        isinstance(key, str)
        and CAPACITY_ID_PATTERN.fullmatch(key) is not None
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        for key, value in capacities.items()
    ):
        raise AdapterError(
            "[NU54:E_CAPABILITY_DECLARATION] capacities는 음이 아닌 정수 object여야 합니다."
        )
    return {
        "schema_version": document["schema_version"],
        "capabilities": capabilities,
        "roles": roles,
        "capacities": dict(capacities),
        "path": path,
    }


## @brief compiler/linker의 undefined symbol을 안정된 capability ID로 변환합니다.
def capabilities_for_probe_symbols(
    registry: dict[str, Any], symbols: Iterable[str]
) -> list[str]:
    mapping = registry["probe_symbols"]
    return sorted({mapping[symbol] for symbol in symbols if symbol in mapping})


## @brief nm의 undefined symbol 출력을 source 문자열을 보지 않고 해석합니다.
def parse_undefined_symbols(output: str) -> list[str]:
    symbols: set[str] = set()
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[-2] in {"U", "w", "v"}:
            symbols.add(fields[-1])
        elif len(fields) == 2 and fields[1] in {"U", "w", "v"}:
            symbols.add(fields[0])
    return sorted(symbols)


## @brief 명시된 capacity 집계 의미를 적용하고 범위를 검증합니다.
def _resolve_capacities(
    registry: dict[str, Any],
    roles: Sequence[str],
    declaration: dict[str, Any],
) -> list[dict[str, Any]]:
    contributions: dict[str, list[tuple[int, str]]] = {}
    for role_id in roles:
        for capacity_id, value in registry["roles"][role_id]["capacities"].items():
            contributions.setdefault(capacity_id, []).append((value, f"role:{role_id}"))
    for capacity_id, value in declaration["capacities"].items():
        contributions.setdefault(capacity_id, []).append((value, "declaration"))

    unknown = sorted(set(contributions) - set(registry["capacities"]))
    if unknown:
        raise AdapterError(f"[NU54:E_CAPACITY_UNKNOWN] 알 수 없는 capacity입니다: {unknown}")
    resolved: list[dict[str, Any]] = []
    for capacity_id in sorted(contributions):
        definition = registry["capacities"][capacity_id]
        values = contributions[capacity_id]
        if definition["aggregation"] == "maximum":
            value = max(item[0] for item in values)
        elif definition["aggregation"] == "sum":
            value = sum(item[0] for item in values)
        else:
            unique = {item[0] for item in values}
            if len(unique) != 1:
                raise AdapterError(
                    f"[NU54:E_CAPACITY_CONFLICT] {capacity_id}는 같은 값이어야 합니다: {sorted(unique)}"
                )
            value = next(iter(unique))
        if value < definition["minimum"] or value > definition["maximum"]:
            raise AdapterError(
                f"[NU54:E_CAPACITY_RANGE] {capacity_id}={value}가 검증 범위 "
                f"{definition['minimum']}..{definition['maximum']} 밖입니다."
            )
        resolved.append(
            {
                "id": capacity_id,
                "value": value,
                "unit": definition["unit"],
                "aggregation": definition["aggregation"],
                "conf": [template.format(value=value) for template in definition["conf"]],
                "sources": [
                    {"source": source, "value": contribution}
                    for contribution, source in sorted(values, key=lambda item: (item[1], item[0]))
                ],
            }
        )
    return resolved


## @brief probe·library·role 선언의 transitive closure와 충돌을 계산합니다.
def resolve_capabilities(
    registry: dict[str, Any],
    probe_capabilities: Sequence[str],
    library_features: Sequence[dict[str, Any]],
    declaration: dict[str, Any],
) -> dict[str, Any]:
    capabilities = registry["capabilities"]
    reasons: dict[str, set[str]] = {}

    def request(identifier: str, reason: str) -> None:
        if identifier not in capabilities:
            raise AdapterError(
                f"[NU54:E_CAPABILITY_UNKNOWN] {reason}이 알 수 없는 capability를 요구합니다: {identifier}"
            )
        reasons.setdefault(identifier, set()).add(reason)

    for identifier in registry["defaults"]:
        request(identifier, "registry:default")
    for identifier in probe_capabilities:
        request(identifier, "compiler-probe")
    for feature in library_features:
        feature_id = feature.get("id", "unknown")
        requirements = feature.get("capabilities")
        if not isinstance(requirements, list) or not all(
            isinstance(item, str) for item in requirements
        ):
            raise AdapterError(
                f"[NU54:E_FEATURE_SCHEMA] {feature_id} capability 요구가 없습니다."
            )
        for identifier in requirements:
            request(identifier, f"library:{feature_id}")
    for identifier in declaration["capabilities"]:
        request(identifier, "declaration")

    selected_roles = sorted(set(declaration["roles"]))
    unknown_roles = sorted(set(selected_roles) - set(registry["roles"]))
    if unknown_roles:
        raise AdapterError(f"[NU54:E_ROLE_UNKNOWN] 알 수 없는 role입니다: {unknown_roles}")
    selected_role_set = set(selected_roles)
    for role_id in selected_roles:
        role = registry["roles"][role_id]
        conflicts = sorted(set(role["conflicts"]) & selected_role_set)
        if conflicts:
            raise AdapterError(
                f"[NU54:E_ROLE_CONFLICT] {role_id}와 동시에 선택할 수 없습니다: {conflicts}"
            )
        for identifier in role["capabilities"]:
            request(identifier, f"role:{role_id}")

    states: dict[str, str] = {}
    path: list[str] = []

    def visit(identifier: str) -> None:
        state = states.get(identifier)
        if state == "done":
            return
        if state == "visiting":
            start = path.index(identifier)
            cycle = path[start:] + [identifier]
            raise AdapterError(
                f"[NU54:E_CAPABILITY_CYCLE] capability 순환 의존성입니다: {' -> '.join(cycle)}"
            )
        states[identifier] = "visiting"
        path.append(identifier)
        for required in capabilities[identifier]["requires"]:
            reasons.setdefault(required, set()).add(f"dependency:{identifier}")
            visit(required)
        path.pop()
        states[identifier] = "done"

    for identifier in sorted(list(reasons)):
        visit(identifier)

    selected = set(states)
    for identifier in sorted(selected):
        allowed_roles = set(capabilities[identifier]["requires_any_role"])
        if allowed_roles and not allowed_roles.intersection(selected_role_set):
            raise AdapterError(
                f"[NU54:E_ROLE_REQUIRED] {identifier}에는 다음 role 중 하나가 필요합니다: "
                f"{sorted(allowed_roles)}"
            )
    for identifier in sorted(selected):
        conflicts = sorted(set(capabilities[identifier]["conflicts"]) & selected)
        if conflicts:
            raise AdapterError(
                f"[NU54:E_CAPABILITY_CONFLICT] {identifier}와 동시에 선택할 수 없습니다: {conflicts}"
            )

    resolved_capabilities = []
    conf: list[str] = []
    overlays: list[str] = []
    source_gates: list[str] = []
    sources: list[str] = []
    for identifier in sorted(selected):
        item = capabilities[identifier]
        resolved_capabilities.append(
            {
                "id": identifier,
                "reasons": sorted(reasons.get(identifier, set())),
                "requires": list(item["requires"]),
                "requires_any_role": list(item["requires_any_role"]),
            }
        )
        conf.extend(item["conf"])
        overlays.extend(item["overlays"])
        source_gates.extend(item["source_gates"])
        sources.extend(item["sources"])

    resolved_capacities = _resolve_capacities(registry, selected_roles, declaration)
    for capacity in resolved_capacities:
        conf.extend(capacity["conf"])

    merged_conf: dict[str, str] = {}
    for line in conf:
        name, setting = line.split("=", 1)
        previous = merged_conf.get(name)
        if previous is not None and previous != setting:
            raise AdapterError(
                f"[NU54:E_CAPABILITY_CONFIG_CONFLICT] {name} 요구가 충돌합니다: "
                f"{previous} != {setting}"
            )
        merged_conf[name] = setting

    selected_conf_names = set(merged_conf)
    owned_boolean_conf = {
        line.split("=", 1)[0]
        for item in capabilities.values()
        for line in item["conf"]
        if line.endswith("=y")
    }
    disabled_conf = [
        f"{name}=n" for name in sorted(owned_boolean_conf - selected_conf_names)
    ]

    return {
        "schema_version": CAPABILITY_RESOLUTION_SCHEMA_VERSION,
        "registry": {
            "schema_version": registry["schema_version"],
            "probe_mapping_version": registry["probe_mapping_version"],
            "path": canonical_path(registry["path"]).as_posix(),
        },
        "probe_capabilities": sorted(set(probe_capabilities)),
        "library_features": sorted(
            feature["id"] for feature in library_features if isinstance(feature.get("id"), str)
        ),
        "roles": selected_roles,
        "capacities": resolved_capacities,
        "capabilities": resolved_capabilities,
        "generated": {
            "disabled_conf": disabled_conf,
            "conf": [f"{name}={setting}" for name, setting in merged_conf.items()],
            "overlays": list(dict.fromkeys(overlays)),
            "source_gates": list(dict.fromkeys(source_gates)),
            "source_roots": list(registry["source_roots"]),
            "sources": list(dict.fromkeys(sources)),
        },
    }


## @brief resolved-capabilities 단일 원본을 원자적으로 기록합니다.
def write_resolved_capabilities(path: Path, resolution: dict[str, Any]) -> bool:
    if resolution.get("schema_version") != CAPABILITY_RESOLUTION_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_CAPABILITY_RESULT] 지원하지 않는 resolution schema입니다.")
    return atomic_write_json(path, resolution)
