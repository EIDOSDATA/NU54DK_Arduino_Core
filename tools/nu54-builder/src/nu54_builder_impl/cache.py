"""! @brief cache key·generation·회복·용량 관리를 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Sequence
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from .common import (
    ADAPTER_VERSION,
    AdapterError,
    CACHE_SCHEMA_VERSION,
    CacheBusyError,
    DEFAULT_BUILD_CACHE_MAX_BYTES,
    DEFAULT_BUILD_CACHE_MAX_ENTRIES,
    DEFAULT_PROFILE,
    NCS_VERSION,
    atomic_write_json,
    canonical_path,
    exact_git_revision,
    git_or_release_revision,
    is_within,
    load_json_object,
    optional_file_sha256,
    run_checked,
    tree_content_sha256,
)
from .configuration import declared_path, load_configuration_profile, resolve_library_features
from .environment import compiler_version, tool_environment
from .locking import build_lock, operating_system_lock
from .installed_platform import requires_platform_copy
from .paths import build_cache_root, cache_workspace, local_cache_root, positive_environment_integer


## @brief M9 cache key에 사용할 canonical input manifest를 생성합니다.
def cache_input_manifest(
    paths: dict[str, Path], args: argparse.Namespace, tools: dict[str, Any],
    selected_library_names: Sequence[str] = (),
) -> dict[str, Any]:
    platform_root = paths["platform_root"]
    board_root = platform_root / "board_package" / "NU54DK_Zephyr_DTS"
    ncs_root = tools["ncs_root"]
    toolchain_root = tools["toolchain_root"]
    platform_inputs = (
        "release-manifest.json",
        "post_install.bat",
        "platform.txt",
        "boards.txt",
        "programmers.txt",
        "cores",
        "variants",
        "dts",
        "zephyr",
        "third_party/ArduinoCore-API",
        "tools/nu54-builder/src",
        "tools/nu54-builder/templates",
        "tools/nu54-prerequisites",
    )
    board_inputs = ("boards/nucode/nu54dk",)
    nrf_root = ncs_root / "nrf"
    zephyr_root = ncs_root / "zephyr"
    toolchain_manifest = toolchain_root / "manifest.json"
    bundled_git = tools.get("git")
    revision_arguments: dict[str, str | Path] = {}
    if isinstance(bundled_git, Path) and bundled_git.is_file():
        revision_arguments["git_executable"] = bundled_git
    profile_id = getattr(args, "profile", DEFAULT_PROFILE)
    profile_path = platform_root / "variants" / "nu54dk" / "profiles" / profile_id / "profile.json"
    profile = (
        load_configuration_profile(
            platform_root,
            profile_id,
            fqbn=args.fqbn,
            zephyr_board=args.board,
        )
        if profile_path.is_file()
        else None
    )
    features = resolve_library_features(platform_root, profile, selected_library_names) if profile is not None else []
    manifest = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "adapter": {
            "version": ADAPTER_VERSION,
            "platform_root": platform_root.as_posix(),
            "platform_content": tree_content_sha256(platform_root, platform_inputs),
        },
        "target": {
            "fqbn": args.fqbn,
            "board": args.board,
            "sysbuild": False,
            "profile": profile_id,
        },
        "sketch": {
            "root": paths["sketch_root"].as_posix(),
            "prj_conf": optional_file_sha256(paths["sketch_root"] / "prj.conf"),
            "app_overlay": optional_file_sha256(paths["sketch_root"] / "app.overlay"),
        },
        "board_package": {
            "root": board_root.resolve().as_posix(),
            "revision": git_or_release_revision(
                board_root, platform_root, "board_revision"
            ),
            "content": tree_content_sha256(board_root, board_inputs),
        },
        "ncs": {
            "declared_version": NCS_VERSION,
            "root": ncs_root.as_posix(),
            "nrf_revision": exact_git_revision(
                nrf_root, **revision_arguments
            ),
            "nrf_west_yml": optional_file_sha256(nrf_root / "west.yml"),
            "zephyr_revision": exact_git_revision(
                zephyr_root, **revision_arguments
            ),
            "zephyr_version_file": optional_file_sha256(zephyr_root / "VERSION"),
        },
        "toolchain": {
            "root": toolchain_root.as_posix(),
            "bundle_id": toolchain_root.name,
            "environment": optional_file_sha256(toolchain_root / "environment.json"),
            "manifest": optional_file_sha256(toolchain_manifest),
            "compiler": compiler_version(tools["compiler"], tools["environment"]),
        },
    }
    if profile is not None:
        manifest["configuration"] = {
            "profile": {"id": profile["id"], "manifest": optional_file_sha256(profile["path"]), "conf": optional_file_sha256(profile["conf_path"]), "overlay": optional_file_sha256(profile["overlay_path"])},
            "selected_features": [{"id": item["id"], "manifest": optional_file_sha256(item["path"]), "conf": [optional_file_sha256(declared_path(item["root"], value, "E_FEATURE_PATH")) for value in item["conf"]], "overlays": [optional_file_sha256(declared_path(item["root"], value, "E_FEATURE_PATH")) for value in item["overlays"]]} for item in features],
        }
    elif hasattr(args, "profile"):
        raise AdapterError(f"[NU54:E_PROFILE_SCHEMA] profile을 찾을 수 없습니다: {profile_path}")
    if requires_platform_copy(platform_root):
        manifest['platform_build_copy'] = {'content': tree_content_sha256(platform_root, ('.',))}
    return manifest


## @brief canonical input manifest에서 전체 SHA-256 cache key를 계산합니다.
def cache_key_for_manifest(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


## @brief cache access 시각과 크기 계산용 metadata를 갱신합니다.
def touch_cache_access(workspace: Path, cache_key: str) -> None:
    atomic_write_json(
        workspace / "access.json",
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "last_accessed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )


## @brief cache state를 원자적으로 전이하고 기존 누적값을 보존합니다.
def transition_cache_state(workspace: Path, cache_key: str, state: str, **updates: Any) -> dict[str, Any]:
    state_path = workspace / "state.json"
    previous: dict[str, Any] = {}
    if state_path.is_file():
        try:
            previous = load_json_object(state_path, "E_CACHE_STATE")
        except AdapterError:
            previous = {}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    document = dict(previous)
    if state == "ready":
        document.pop("failure", None)
        document.pop("failed_at_utc", None)
    elif state == "failed":
        updates.setdefault("failed_at_utc", now)
    document.update(updates)
    document.update(
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "state": state,
            "updated_at_utc": now,
        }
    )
    document.setdefault("created_at_utc", now)
    atomic_write_json(state_path, document)
    touch_cache_access(workspace, cache_key)
    return document


## @brief ccache의 machine-readable 통계를 dictionary로 읽습니다.
def read_ccache_stats(tools: dict[str, Any]) -> dict[str, int]:
    ccache = tools.get("ccache")
    if not isinstance(ccache, Path) or not ccache.is_file():
        return {}
    try:
        result = subprocess.run(
            [str(ccache), "--print-stats"],
            env=tools["environment"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except OSError:
        return {}
    if result.returncode != 0:
        return {}
    statistics: dict[str, int] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t", 1)
        if len(fields) == 2 and fields[1].strip().isdigit():
            statistics[fields[0].strip()] = int(fields[1].strip())
    return statistics


## @brief 두 ccache snapshot의 증가량만 반환합니다.
def ccache_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {key: after.get(key, 0) - before.get(key, 0) for key in sorted(keys)}


## @brief directory가 사용하는 전체 byte 수를 계산합니다.
def directory_size(path: Path) -> int:
    total = 0
    if not path.is_dir():
        return total
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


## @brief cache entry의 운영체제 lock이 현재 다른 worker에 점유됐는지 확인합니다.
def cache_entry_is_locked(entry: Path) -> bool:
    try:
        with operating_system_lock(entry, 0.0):
            return False
    except TimeoutError:
        return True


## @brief 현재 schema namespace의 canonical build cache entry를 나열합니다.
def cache_entries(root: Path | None = None) -> list[dict[str, Any]]:
    cache_root = local_cache_root(root or build_cache_root())
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    entries: list[dict[str, Any]] = []
    if not namespace.is_dir():
        return entries
    for shard in sorted(namespace.iterdir(), key=lambda path: path.name):
        if not shard.is_dir() or not re.fullmatch(r"[0-9a-f]{2}", shard.name):
            continue
        for entry in sorted(shard.iterdir(), key=lambda path: path.name):
            if (
                not entry.is_dir()
                or not re.fullmatch(r"[0-9a-f]{32}", entry.name)
                or entry.name[:2] != shard.name
                or not is_within(entry, namespace)
            ):
                continue
            access_document: dict[str, Any] = {}
            access_path = entry / "access.json"
            if access_path.is_file():
                try:
                    access_document = load_json_object(access_path, "E_CACHE_ACCESS")
                except AdapterError:
                    access_document = {}
            state_document: dict[str, Any] = {}
            state_path = entry / "state.json"
            if state_path.is_file():
                try:
                    state_document = load_json_object(state_path, "E_CACHE_STATE")
                except AdapterError:
                    state_document = {}
            try:
                fallback_access = entry.stat().st_mtime
            except OSError:
                fallback_access = 0.0
            access_text = access_document.get("last_accessed_at_utc")
            try:
                access_timestamp = (
                    dt.datetime.fromisoformat(str(access_text)).timestamp()
                    if access_text
                    else fallback_access
                )
            except ValueError:
                access_timestamp = fallback_access
            full_key = state_document.get("cache_key")
            valid_key = isinstance(full_key, str) and bool(
                re.fullmatch(r"[0-9a-f]{64}", full_key)
            )
            valid_key = bool(valid_key and str(full_key).startswith(entry.name))
            entries.append(
                {
                    "key": full_key if valid_key else None,
                    "directory_key": entry.name,
                    "valid": valid_key,
                    "path": entry,
                    "size": directory_size(entry),
                    "last_access_timestamp": access_timestamp,
                    "last_accessed_at_utc": access_text,
                    "state": state_document.get("state", "unknown"),
                    "locked": cache_entry_is_locked(entry),
                    "pinned": (entry / ".pin").exists(),
                }
            )
    return entries


## @brief 검증된 canonical entry를 운영체제 lock 안에서 재귀 삭제합니다.
def remove_cache_entry_path(
    entry: Path,
    *,
    namespace: Path,
    expected_key: str | None,
    lock_timeout: float,
    operation: str,
) -> int:
    namespace = canonical_path(namespace)
    resolved_entry = canonical_path(entry)
    try:
        relative = resolved_entry.relative_to(namespace)
    except ValueError as error:
        raise AdapterError(f"cache root 밖의 경로는 삭제할 수 없습니다: {resolved_entry}") from error
    if (
        len(relative.parts) != 2
        or not re.fullmatch(r"[0-9a-f]{2}", relative.parts[0])
        or not re.fullmatch(r"[0-9a-f]{32}", relative.parts[1])
        or relative.parts[1][:2] != relative.parts[0]
    ):
        raise AdapterError(f"canonical cache entry가 아닌 경로는 삭제할 수 없습니다: {resolved_entry}")
    try:
        with operating_system_lock(resolved_entry, lock_timeout):
            if not resolved_entry.exists():
                return 0
            if (resolved_entry / ".pin").exists():
                raise AdapterError(f"고정된 cache entry는 삭제할 수 없습니다: {resolved_entry.name}")
            if expected_key is not None:
                state_path = resolved_entry / "state.json"
                if not state_path.is_file():
                    raise AdapterError(
                        f"state가 없는 cache entry는 key로 삭제할 수 없습니다: {expected_key}"
                    )
                state_document = load_json_object(state_path, "E_CACHE_STATE")
                if state_document.get("cache_key") != expected_key:
                    raise AdapterError(
                        "[NU54:E_CACHE_KEY_COLLISION] 삭제 요청과 cache state의 전체 SHA-256이 다릅니다."
                    )
            size = directory_size(resolved_entry)
            shutil.rmtree(resolved_entry)
    except TimeoutError as error:
        raise CacheBusyError(
            f"[NU54:E_CACHE_BUSY] 활성 worker가 사용 중인 cache entry입니다: {resolved_entry.name}"
        ) from error
    try:
        resolved_entry.parent.rmdir()
    except OSError:
        pass
    return size


## @brief 검증된 cache entry 하나를 maintenance 및 entry lock 안에서 삭제합니다.
def remove_cache_entry(
    cache_key: str,
    *,
    root: Path | None = None,
    lock_timeout: float = 0.05,
) -> int:
    if not re.fullmatch(r"[0-9a-f]{64}", cache_key):
        raise AdapterError(f"cache key 형식이 잘못되었습니다: {cache_key}")
    cache_root = local_cache_root(root or build_cache_root())
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    entry = cache_workspace(cache_key, root=cache_root)
    with build_lock(cache_root / ".maintenance", operation="cache-remove"):
        return remove_cache_entry_path(
            entry,
            namespace=namespace,
            expected_key=cache_key,
            lock_timeout=lock_timeout,
            operation="cache-remove",
        )


## @brief quota와 LRU 정책에 따라 비활성 build cache를 안전하게 정리합니다.
def prune_build_cache(
    *,
    current_key: str | None = None,
    root: Path | None = None,
    max_bytes: int | None = None,
    max_entries: int | None = None,
) -> dict[str, Any]:
    configured_max_bytes = max_bytes or positive_environment_integer(
        "NUCODE_BUILD_CACHE_MAX_BYTES", DEFAULT_BUILD_CACHE_MAX_BYTES
    )
    configured_max_entries = max_entries or positive_environment_integer(
        "NUCODE_BUILD_CACHE_MAX_ENTRIES", DEFAULT_BUILD_CACHE_MAX_ENTRIES
    )
    cache_root = local_cache_root(root or build_cache_root())
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with build_lock(cache_root / ".maintenance", operation="cache-prune"):
        entries = cache_entries(cache_root)
        total_size = sum(int(entry["size"]) for entry in entries)
        candidates = sorted(entries, key=lambda entry: float(entry["last_access_timestamp"]))
        remaining_count = len(entries)
        for entry in candidates:
            if total_size <= configured_max_bytes and remaining_count <= configured_max_entries:
                break
            if entry["key"] == current_key or entry["pinned"]:
                continue
            try:
                removed_size = remove_cache_entry_path(
                    entry["path"],
                    namespace=namespace,
                    expected_key=str(entry["key"]) if entry["valid"] else None,
                    lock_timeout=0.0,
                    operation="cache-prune",
                )
            except AdapterError as error:
                skipped.append({"directory_key": entry["directory_key"], "reason": str(error)})
                continue
            removed.append(
                {
                    "key": entry["key"],
                    "directory_key": entry["directory_key"],
                    "bytes": removed_size,
                }
            )
            total_size -= removed_size
            remaining_count -= 1
    return {
        "schema_version": 1,
        "max_bytes": configured_max_bytes,
        "max_entries": configured_max_entries,
        "remaining_bytes": total_size,
        "remaining_entries": remaining_count,
        "removed": removed,
        "skipped": skipped,
        "quota_satisfied": (
            total_size <= configured_max_bytes and remaining_count <= configured_max_entries
        ),
    }


## @brief ccache 자체 동시성 제어를 사용해 compiler cache 내용만 비웁니다.
def clear_compiler_cache(cache_root: Path) -> int:
    compiler_cache = cache_root / "compiler-cache"
    if not compiler_cache.exists():
        return 0
    if not is_within(compiler_cache, cache_root) or compiler_cache == cache_root:
        raise AdapterError(f"compiler cache 경로가 잘못되었습니다: {compiler_cache}")
    removed_bytes = directory_size(compiler_cache)
    tools = tool_environment()
    ccache = tools.get("ccache")
    if not isinstance(ccache, Path) or not ccache.is_file():
        raise AdapterError("compiler cache를 안전하게 비울 ccache 실행 파일이 없습니다.")
    environment = tools["environment"].copy()
    environment["CCACHE_DIR"] = str(compiler_cache)
    run_checked([ccache, "--clear"], cwd=cache_root, environment=environment)
    return removed_bytes


## @brief 비활성 build cache 전체와 선택한 compiler cache를 안전하게 비웁니다.
def clear_build_cache(cache_root: Path, *, include_compiler: bool) -> dict[str, Any]:
    cache_root = local_cache_root(cache_root)
    namespace = cache_root / f"v{CACHE_SCHEMA_VERSION}"
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with build_lock(cache_root / ".maintenance", operation="cache-clear"):
        for entry in cache_entries(cache_root):
            if entry["pinned"]:
                skipped.append({"directory_key": entry["directory_key"], "reason": "pinned"})
                continue
            try:
                removed_size = remove_cache_entry_path(
                    entry["path"],
                    namespace=namespace,
                    expected_key=str(entry["key"]) if entry["valid"] else None,
                    lock_timeout=0.0,
                    operation="cache-clear",
                )
            except AdapterError as error:
                skipped.append({"directory_key": entry["directory_key"], "reason": str(error)})
                continue
            removed.append(
                {
                    "key": entry["key"],
                    "directory_key": entry["directory_key"],
                    "bytes": removed_size,
                }
            )
        compiler_removed = clear_compiler_cache(cache_root) if include_compiler else 0
    return {
        "removed": removed,
        "skipped": skipped,
        "compiler_cache_removed_bytes": compiler_removed,
    }


## @brief cache 관리 CLI 작업을 수행합니다.
def manage_cache(args: argparse.Namespace) -> None:
    root = local_cache_root(args.cache_root) if args.cache_root else build_cache_root()
    action = args.cache_action
    try:
        if action == "list":
            result: Any = [
                {key: value.as_posix() if isinstance(value, Path) else value for key, value in entry.items()}
                for entry in cache_entries(root)
            ]
        elif action == "inspect":
            matching = [entry for entry in cache_entries(root) if entry["key"] == args.key]
            if not matching:
                raise AdapterError(f"cache entry를 찾을 수 없습니다: {args.key}")
            entry = matching[0]
            result = {
                key: value.as_posix() if isinstance(value, Path) else value
                for key, value in entry.items()
            }
            for filename in ("input-manifest.json", "state.json", "access.json"):
                document_path = entry["path"] / filename
                if document_path.is_file():
                    result[filename] = load_json_object(document_path, "E_CACHE_METADATA")
        elif action == "prune":
            result = prune_build_cache(root=root)
        elif action == "remove":
            result = {"key": args.key, "removed_bytes": remove_cache_entry(args.key, root=root)}
        elif action == "clear":
            result = clear_build_cache(root, include_compiler=args.include_compiler)
        else:
            raise AdapterError(f"알 수 없는 cache action입니다: {action}")
    except OSError as error:
        raise AdapterError(f"cache {action} 작업 중 filesystem 오류가 발생했습니다: {error}") from error
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
