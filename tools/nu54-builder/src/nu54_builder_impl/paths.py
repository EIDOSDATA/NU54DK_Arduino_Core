"""! @brief Arduino session과 cache 경로 계약을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import hashlib
import os
import re
from .common import AdapterError, CACHE_SCHEMA_VERSION, CONTEXT_DIRECTORY, canonical_path, path_key


## @brief cache root가 단일 host의 local filesystem인지 검증합니다.
def local_cache_root(value: str | Path) -> Path:
    root = canonical_path(value)
    if os.name == "nt" and str(root).startswith(("\\\\", "//")):
        raise AdapterError("M9 build cache는 UNC/network 경로를 지원하지 않습니다.")
    return root


## @brief M9 영구 build cache root를 환경 또는 짧은 사용자 local data 경로에서 계산합니다.
def build_cache_root() -> Path:
    configured = os.environ.get("NUCODE_BUILD_CACHE_ROOT")
    if configured:
        return local_cache_root(configured)
    local_data = os.environ.get("LOCALAPPDATA")
    if local_data:
        base = canonical_path(local_data)
    else:
        base = canonical_path(Path.home() / ".cache")
    ## @note nRF Security의 긴 object 이름이 Windows MAX_PATH를 넘지 않도록 build 전용
    ##       기본 경로는 짧게 유지하고 설치 상태와 log는 기존 NUCODE 경로를 사용합니다.
    return local_cache_root(base / "NU54" / "c")


## @brief 정수형 환경 설정을 유효한 양수로 읽습니다.
def positive_environment_integer(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise AdapterError(f"{name}은 양의 정수여야 합니다: {value}") from error
    if parsed <= 0:
        raise AdapterError(f"{name}은 양의 정수여야 합니다: {value}")
    return parsed


## @brief common argument에서 adapter의 고정 directory를 계산합니다.
def adapter_paths(args: argparse.Namespace) -> dict[str, Path]:
    platform_root = canonical_path(args.platform_root)
    build_path = canonical_path(args.build_path)
    state_root = build_path / CONTEXT_DIRECTORY
    return {
        "platform_root": platform_root,
        "build_path": build_path,
        "sketch_root": canonical_path(args.sketch_root),
        "state_root": state_root,
        "context": state_root / "context.json",
        "records": state_root / "records",
    }


## @brief cache workspace 경로를 adapter path 집합에 결합합니다.
def add_workspace_paths(paths: dict[str, Path], workspace: Path) -> dict[str, Path]:
    combined = dict(paths)
    combined.update(
        {
            "workspace": canonical_path(workspace),
            "app": canonical_path(workspace) / "app",
            "zephyr_build": canonical_path(workspace) / "build",
        }
    )
    return combined


## @brief 저장된 context의 cache workspace를 검증하고 path 집합에 결합합니다.
def paths_from_context(paths: dict[str, Path], context: dict[str, Any]) -> dict[str, Path]:
    workspace_value = context.get("cache_dir") or context.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value:
        raise AdapterError("build context에 M9 cache directory가 없습니다. 다시 compile하십시오.")
    cache_key = context.get("cache_key")
    cache_root_value = context.get("cache_root")
    if not isinstance(cache_key, str) or not re.fullmatch(r"[0-9a-f]{64}", cache_key):
        raise AdapterError("build context의 M9 cache key가 잘못되었습니다. 다시 compile하십시오.")
    if not isinstance(cache_root_value, str) or not cache_root_value:
        raise AdapterError("build context에 M9 cache root가 없습니다. 다시 compile하십시오.")
    workspace = canonical_path(workspace_value)
    cache_root = local_cache_root(cache_root_value)
    expected = cache_workspace(cache_key, root=cache_root)
    if path_key(workspace) != path_key(expected):
        raise AdapterError(
            f"build context의 cache directory가 key/root 계약과 다릅니다: {workspace}"
        )
    return add_workspace_paths(paths, workspace)


## @brief cache key의 persistent workspace path를 계산합니다.
def cache_workspace(cache_key: str, *, root: Path | None = None) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", cache_key):
        raise AdapterError(f"잘못된 cache key입니다: {cache_key}")
    directory_key = cache_key[:32]
    cache_root = local_cache_root(root or build_cache_root())
    return cache_root / f"v{CACHE_SCHEMA_VERSION}" / directory_key[:2] / directory_key


## @brief object path와 일대일로 대응하는 record file 경로를 계산합니다.
def record_path(records_root: Path, object_path: Path) -> Path:
    digest = hashlib.sha256(path_key(object_path).encode("utf-8")).hexdigest()
    return records_root / f"{digest}.json"
