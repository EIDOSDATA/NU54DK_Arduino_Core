"""! @brief Core identity와 allowlisted profile·feature 해석을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from typing import Sequence
import json
import os
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
    allowed = {
        "schema_version",
        "id",
        "display_name",
        "board",
        "zephyr_board",
        "ncs_version",
        "conf",
        "overlay",
        "sysbuild",
        "sysbuild_files",
        "signing_key_env",
        "features",
        "conflicts",
        "requires_hil",
    }
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
    if not isinstance(document["sysbuild"], bool):
        raise AdapterError("[NU54:E_PROFILE_SCHEMA] sysbuild는 boolean이어야 합니다.")
    if not isinstance(document["sysbuild_files"], list) or not all(
        isinstance(item, str) for item in document["sysbuild_files"]
    ):
        raise AdapterError("[NU54:E_PROFILE_SCHEMA] sysbuild_files는 문자열 배열이어야 합니다.")
    signing_key_env = document["signing_key_env"]
    if signing_key_env is not None and not isinstance(signing_key_env, str):
        raise AdapterError("[NU54:E_PROFILE_SCHEMA] signing_key_env는 문자열 또는 null이어야 합니다.")
    if document["sysbuild"]:
        if (
            not document["sysbuild_files"]
            or "sysbuild.conf" not in document["sysbuild_files"]
            or not isinstance(signing_key_env, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]*", signing_key_env)
        ):
            raise AdapterError("[NU54:E_PROFILE_SCHEMA] sysbuild profile의 파일·서명 키 환경 계약이 없습니다.")
    elif document["sysbuild_files"] or signing_key_env is not None:
        raise AdapterError("[NU54:E_PROFILE_SCHEMA] loaderless profile에 sysbuild 입력이 선언되었습니다.")
    conf = declared_path(root, document["conf"], "E_PROFILE_PATH")
    overlay = declared_path(root, document["overlay"], "E_PROFILE_PATH")
    if not conf.is_file() or not overlay.is_file():
        raise AdapterError("[NU54:E_PROFILE_PATH] profile fragment가 없습니다.")
    sysbuild_paths = [
        declared_path(root, value, "E_PROFILE_PATH")
        for value in document["sysbuild_files"]
    ]
    if not all(item.is_file() for item in sysbuild_paths):
        raise AdapterError("[NU54:E_PROFILE_PATH] sysbuild profile fragment가 없습니다.")
    return {
        **document,
        "root": root,
        "path": path,
        "conf_path": conf,
        "overlay_path": overlay,
        "sysbuild_paths": sysbuild_paths,
    }


## @brief sysbuild profile의 저장소 외부 private signing key를 검증합니다.
def resolve_profile_signing_key(
    platform_root: Path, profile: dict[str, Any]
) -> Path | None:
    if not profile["sysbuild"]:
        return None
    variable = profile["signing_key_env"]
    value = os.environ.get(variable, "").strip()
    if not value:
        raise AdapterError(
            f"[NU54:E_DFU_SIGNING_KEY] {variable}에 저장소 외부 ECDSA P-256 private key를 지정하십시오."
        )
    key = canonical_path(value)
    if is_within(key, platform_root):
        raise AdapterError("[NU54:E_DFU_SIGNING_KEY_REPOSITORY] DFU private key는 저장소 안에 둘 수 없습니다.")
    if not key.is_file() or key.suffix.casefold() != ".pem":
        raise AdapterError("[NU54:E_DFU_SIGNING_KEY] DFU signing key PEM 파일을 찾을 수 없습니다.")
    try:
        header = key.read_text(encoding="ascii")[:80]
    except (OSError, UnicodeError) as error:
        raise AdapterError("[NU54:E_DFU_SIGNING_KEY] DFU signing key PEM을 읽을 수 없습니다.") from error
    if "-----BEGIN " not in header or "PRIVATE KEY-----" not in header:
        raise AdapterError("[NU54:E_DFU_SIGNING_KEY] private key PEM header가 올바르지 않습니다.")
    return key


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
    allowed = {
        "schema_version",
        "id",
        "requires",
        "capabilities",
        "conf",
        "overlays",
        "conflicts",
        "compatible_profiles",
    }
    if not isinstance(document, dict) or set(document) != allowed or document.get("schema_version") != FEATURE_SCHEMA_VERSION or document.get("id") != expected_id:
        raise AdapterError(f"[NU54:E_FEATURE_SCHEMA] allowlist feature 계약이 잘못되었습니다: {library_name}")
    for field in (
        "requires",
        "capabilities",
        "conf",
        "overlays",
        "conflicts",
        "compatible_profiles",
    ):
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
    selected = [
        feature
        for library_name in sorted(set(library_names), key=str.casefold)
        if (feature := load_library_feature(platform_root, library_name)) is not None
    ]
    available_features = profile_features | {feature["id"] for feature in selected}
    conflict_owners = {
        resource: f"profile:{profile['id']}" for resource in profile["conflicts"]
    }
    for feature in selected:
        if profile["id"] not in feature["compatible_profiles"]:
            raise AdapterError(f"[NU54:E_FEATURE_PROFILE] {feature['id']}는 {profile['id']} profile과 호환되지 않습니다.")
        missing = sorted(set(feature["requires"]) - available_features)
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
