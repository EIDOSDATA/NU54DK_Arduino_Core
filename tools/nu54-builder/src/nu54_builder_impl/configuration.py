"""! @brief Core identity와 allowlisted profile·feature 해석을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from typing import Sequence
import json
import re
from .common import (
    AdapterError,
    DEFAULT_BOARD,
    DuplicateJsonKeyError,
    FEATURE_ALLOWLIST,
    FEATURE_SCHEMA_VERSION,
    NCS_VERSION,
    PROFILE_SCHEMA_VERSION,
    canonical_path,
    is_within,
    strict_json_object,
)


## @brief Core 소스 버전과 설치 배포 버전을 각각 원본에서 읽습니다.
def load_product_identity(platform_root: Path) -> dict[str, str]:
    try:
        header = (platform_root / "cores/arduino/internal/CoreIdentity.h").read_text(encoding="utf-8")
        platform = (platform_root / "platform.txt").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise AdapterError("[NU54:E_PRODUCT_IDENTITY] 제품 identity 원본을 읽을 수 없습니다.") from error
    definitions = [line for line in header.splitlines()
                   if re.match(r"^#define[ \t]+NUCODE_CORE_SOURCE_VERSION[ \t]+", line)]
    versions = [line[len("version="):] for line in platform.splitlines() if line.startswith("version=")]
    if len(definitions) != 1 or len(versions) != 1:
        raise AdapterError("[NU54:E_PRODUCT_IDENTITY] 소스·배포 버전은 각각 하나여야 합니다.")
    match = re.fullmatch(r'#define[ \t]+NUCODE_CORE_SOURCE_VERSION[ \t]+"([^"\r\n]+)"[ \t]*', definitions[0])
    pattern = r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
    if match is None or not re.fullmatch(pattern, match[1]) or not re.fullmatch(pattern, versions[0]):
        raise AdapterError("[NU54:E_PRODUCT_IDENTITY] 제품 버전 형식이 올바르지 않습니다.")
    return {"source_version": match[1], "package_version": versions[0]}


## @brief root를 벗어나지 않는 선언형 상대 경로만 허용합니다.
def declared_path(root: Path, value: str, error_code: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or PureWindowsPath(value).is_absolute() or value.startswith(("\\\\", "//")):
        raise AdapterError(f"[NU54:{error_code}] 상대 경로가 아닙니다: {value}")
    candidate = canonical_path(root / value)
    if not is_within(candidate, root):
        raise AdapterError(f"[NU54:{error_code}] 경로가 root를 벗어납니다: {value}")
    return candidate


## @brief 선택한 NU54DK 구성 profile과 실제 build target을 엄격히 검증하여 읽습니다.
def load_configuration_profile(
    platform_root: Path,
    profile_id: str,
    *,
    fqbn: str = "nucode:zephyr:nu54dk",
    zephyr_board: str = DEFAULT_BOARD,
) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", profile_id):
        raise AdapterError(f"[NU54:E_PROFILE_ID] 잘못된 profile ID입니다: {profile_id}")
    root = platform_root / "variants" / "nu54dk" / "profiles" / profile_id
    path = root / "profile.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_json_object)
    except DuplicateJsonKeyError as error:
        raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] {error}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] profile을 읽지 못했습니다: {path}: {error}") from error
    allowed = {"schema_version", "id", "display_name", "board", "zephyr_board", "ncs_version", "conf", "overlay", "features", "conflicts", "requires_hil"}
    if not isinstance(document, dict) or set(document) != allowed or document.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_PROFILE_SCHEMA] profile field/schema가 올바르지 않습니다.")
    for field in ("id", "display_name", "board", "zephyr_board", "ncs_version", "conf", "overlay"):
        if not isinstance(document.get(field), str):
            raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] {field}는 문자열이어야 합니다.")
    fqbn_parts = fqbn.split(":") if isinstance(fqbn, str) else []
    fqbn_board = ":".join(fqbn_parts[:3]) if len(fqbn_parts) >= 3 else ""
    if (
        document.get("id") != profile_id
        or document.get("board") != fqbn_board
        or document.get("zephyr_board") != zephyr_board
        or document.get("ncs_version") != NCS_VERSION
    ):
        raise AdapterError("[NU54:E_PROFILE_TARGET] profile target 계약이 현재 build와 다릅니다.")
    for field in ("features", "conflicts", "requires_hil"):
        if not isinstance(document[field], list) or not all(isinstance(item, str) for item in document[field]):
            raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] {field}는 문자열 배열이어야 합니다.")
    conf = declared_path(root, document["conf"], "E_PROFILE_PATH")
    overlay = declared_path(root, document["overlay"], "E_PROFILE_PATH")
    if not conf.is_file() or not overlay.is_file():
        raise AdapterError("[NU54:E_PROFILE_PATH] profile fragment가 없습니다.")
    return {**document, "root": root, "path": path, "conf_path": conf, "overlay_path": overlay}


## @brief bundled library의 선언형 feature manifest만 allowlist로 읽습니다.
def load_library_feature(platform_root: Path, library_name: str) -> dict[str, Any] | None:
    expected_id = FEATURE_ALLOWLIST.get(library_name)
    if expected_id is None:
        return None
    root = platform_root / "libraries" / library_name / "zephyr"
    path = root / "feature.yml"
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_json_object)
    except DuplicateJsonKeyError as error:
        raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] {error}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] feature manifest를 읽지 못했습니다: {path}: {error}") from error
    allowed = {"schema_version", "id", "requires", "conf", "overlays", "conflicts", "compatible_profiles"}
    if not isinstance(document, dict) or set(document) != allowed or document.get("schema_version") != FEATURE_SCHEMA_VERSION or document.get("id") != expected_id:
        raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] allowlist feature 계약이 잘못되었습니다: {library_name}")
    for field in ("requires", "conf", "overlays", "conflicts", "compatible_profiles"):
        if not isinstance(document[field], list) or not all(isinstance(item, str) for item in document[field]):
            raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] {field}는 문자열 배열이어야 합니다.")
    for field in ("conf", "overlays"):
        for value in document[field]:
            if not declared_path(root, value, "E_FEATURE_PATH").is_file():
                raise AdapterError(f"[NU54:E_FEATURE_PATH] feature fragment가 없습니다: {value}")
    return {**document, "root": root, "path": path}


## @brief 선택된 bundled library feature의 profile 적합성과 충돌을 판정합니다.
def resolve_library_features(
    platform_root: Path, profile: dict[str, Any], library_names: Sequence[str]
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    profile_features = set(profile["features"])
    conflict_owners = {
        resource: f"profile:{profile['id']}" for resource in profile["conflicts"]
    }
    for library_name in sorted(set(library_names), key=str.casefold):
        feature = load_library_feature(platform_root, library_name)
        if feature is None:
            continue
        if profile["id"] not in feature["compatible_profiles"]:
            raise AdapterError(f"[NU54:E_FEATURE_PROFILE] {feature['id']}는 {profile['id']} profile과 호환되지 않습니다.")
        missing = sorted(set(feature["requires"]) - profile_features)
        conflicts = sorted(set(feature["conflicts"]) & conflict_owners.keys())
        if missing:
            raise AdapterError(f"[NU54:E_FEATURE_REQUIREMENT] {feature['id']} 요구 기능이 없습니다: {missing}")
        if conflicts:
            detail = ", ".join(
                f"{resource} ({conflict_owners[resource]} <-> {feature['id']})"
                for resource in conflicts
            )
            raise AdapterError(f"[NU54:E_FEATURE_CONFLICT] 충돌 자원: {detail}")
        for resource in feature["conflicts"]:
            conflict_owners[resource] = feature["id"]
        resolved.append(feature)
    return resolved
