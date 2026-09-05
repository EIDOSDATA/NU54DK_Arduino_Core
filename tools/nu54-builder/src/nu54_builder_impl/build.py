"""! @brief configure·context·feature migration·최종 link orchestration을 소유합니다. """

from __future__ import annotations
from .models import ArtifactManifest, BuildContext

from pathlib import Path
from typing import Any
from typing import Sequence
import argparse
import datetime as dt
import json
import re
import sys
import time
from .artifacts import publish_artifact_generation, validate_linked_code_partition
from .cache import (
    cache_input_manifest,
    cache_key_for_manifest,
    ccache_delta,
    prune_build_cache,
    read_ccache_stats,
    remove_cache_entry,
    transition_cache_state,
)
from .common import (
    ADAPTER_VERSION,
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    AdapterError,
    CACHE_SCHEMA_VERSION,
    DEFAULT_PROFILE,
    NCS_VERSION,
    SESSION_CONTEXT_SCHEMA_VERSION,
    atomic_write_bytes,
    atomic_write_bytes_if_changed,
    atomic_write_json,
    atomic_write_text,
    canonical_path,
    file_sha256,
    is_within,
    load_json_object,
    optional_file_sha256,
    run_checked,
)
from .configuration import (
    declared_path,
    load_configuration_profile,
    load_product_identity,
    resolve_library_features,
)
from .environment import tool_environment
from .locking import build_lock
from .paths import (
    adapter_paths,
    add_workspace_paths,
    build_cache_root,
    cache_workspace,
    local_cache_root,
    paths_from_context,
    record_path,
)
from .source_graph import (
    invalidate_source_records,
    records_for_objects,
    selected_bundled_libraries,
    write_source_manifest,
)


## @brief west configure command를 cache 정책에 맞게 생성합니다.
def configure_command(
    paths: dict[str, Path],
    args: argparse.Namespace,
    tools: dict[str, Any],
    board_root: Path,
    *,
    pristine: bool,
) -> list[str | Path]:
    command: list[str | Path] = [
        tools["west"],
        "-z",
        tools["zephyr_base"],
        "build",
        "--cmake-only",
        "--no-sysbuild",
    ]
    if pristine:
        command.append("--pristine=always")
    command.extend(
        [
            "-b",
            args.board,
            "-d",
            paths["zephyr_build"],
            paths["app"],
            "--",
            "-UCONFIG_*",
            f"-DBOARD_ROOT={board_root.as_posix()}",
            f"-DEXTRA_ZEPHYR_MODULES={paths['platform_root'].as_posix()}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ]
    )
    ccache = tools.get("ccache")
    if isinstance(ccache, Path) and ccache.is_file():
        command.extend(
            (
                f"-DCMAKE_C_COMPILER_LAUNCHER={ccache.as_posix()}",
                f"-DCMAKE_CXX_COMPILER_LAUNCHER={ccache.as_posix()}",
            )
        )
    overlay = paths["app"] / "app.overlay"
    if overlay.is_file():
        command.append(f"-DDTC_OVERLAY_FILE={overlay.as_posix()}")
    return command


## @brief west build가 application과 build directory의 volume에서 실행될 작업 directory를 반환합니다.
def west_build_working_directory(paths: dict[str, Path]) -> Path:
    app_root = paths["app"]
    build_root = paths["zephyr_build"]
    if app_root.drive.casefold() != build_root.drive.casefold():
        raise AdapterError(
            "[NU54:E_BUILD_VOLUME] application과 Zephyr build directory가 서로 다른 volume에 있습니다: "
            f"{app_root} != {build_root}"
        )
    return app_root


## @brief Zephyr application template과 사용자 config/overlay를 materialize합니다.
def materialize_application(
    paths: dict[str, Path], args: argparse.Namespace,
    selected_library_names: Sequence[str] = (),
) -> None:
    platform_root = paths["platform_root"]
    sketch_root = paths["sketch_root"]
    app_root = paths["app"]
    template = platform_root / "tools" / "nu54-builder" / "templates" / "zephyr-app"
    for required in ("CMakeLists.txt", "prj.conf", "app.overlay", "sources.cmake", "src/bootstrap.cpp"):
        if not (template / required).is_file():
            raise AdapterError(f"Zephyr application template이 불완전합니다: {template / required}")
    app_root.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes_if_changed(app_root / "CMakeLists.txt", (template / "CMakeLists.txt").read_bytes())
    atomic_write_bytes_if_changed(app_root / "src" / "bootstrap.cpp", (template / "src" / "bootstrap.cpp").read_bytes())
    sources = app_root / "sources.cmake"
    if not sources.exists():
        atomic_write_bytes(sources, (template / "sources.cmake").read_bytes())

    profile = load_configuration_profile(
        platform_root,
        getattr(args, "profile", DEFAULT_PROFILE),
        fqbn=args.fqbn,
        zephyr_board=args.board,
    )
    features = resolve_library_features(platform_root, profile, selected_library_names)
    base_config = (template / "prj.conf").read_text(encoding="utf-8").rstrip() + "\n"
    base_config += "\n# Selected profile: " + profile["id"] + "\n" + profile["conf_path"].read_text(encoding="utf-8").rstrip() + "\n"
    for feature in features:
        for relative in feature["conf"]:
            base_config += "\n# Library feature: " + feature["id"] + "\n" + declared_path(feature["root"], relative, "E_FEATURE_PATH").read_text(encoding="utf-8").rstrip() + "\n"
    sketch_config = sketch_root / "prj.conf"
    if sketch_config.is_file():
        base_config += "\n# Sketch prj.conf\n" + sketch_config.read_text(encoding="utf-8").rstrip() + "\n"
    atomic_write_text(app_root / "prj.conf", base_config)

    generated_overlay = app_root / "app.overlay"
    base_overlay = (template / "app.overlay").read_text(encoding="utf-8").rstrip() + "\n"
    base_overlay += "\n/** @brief 선택한 구성 profile의 overlay입니다. */\n" + profile["overlay_path"].read_text(encoding="utf-8").rstrip() + "\n"
    for feature in features:
        for relative in feature["overlays"]:
            base_overlay += "\n/** @brief 허용된 bundled library feature overlay입니다. */\n" + declared_path(feature["root"], relative, "E_FEATURE_PATH").read_text(encoding="utf-8").rstrip() + "\n"
    sketch_overlay = sketch_root / "app.overlay"
    if sketch_overlay.is_file():
        combined_overlay = (
            base_overlay
            + "\n/** Sketch가 제공한 app.overlay override입니다. */\n"
            + sketch_overlay.read_text(encoding="utf-8").rstrip()
            + "\n"
        )
        atomic_write_text(generated_overlay, combined_overlay)
    else:
        atomic_write_text(generated_overlay, base_overlay)


## @brief 현재 고정 입력으로 Zephyr configure-only를 수행하고 context를 기록합니다.
def prepare(args: argparse.Namespace) -> BuildContext:
    session_paths = adapter_paths(args)
    platform_root = session_paths["platform_root"]
    board_root = platform_root / "board_package" / "NU54DK_Zephyr_DTS"
    if not (board_root / "boards" / "nucode" / "nu54dk" / "board.yml").is_file():
        raise AdapterError(f"NU54DK board package를 찾을 수 없습니다: {board_root}")
    cache_root = build_cache_root()
    if cache_root == platform_root or is_within(cache_root, platform_root):
        raise AdapterError(
            "M9 build cache를 platform/board fingerprint 내부에 둘 수 없습니다: "
            f"{cache_root}"
        )
    product_identity = load_product_identity(platform_root)
    tools = tool_environment(platform_root)
    input_manifest = cache_input_manifest(session_paths, args, tools)
    cache_key = cache_key_for_manifest(input_manifest)
    workspace = cache_workspace(cache_key, root=cache_root)
    paths = add_workspace_paths(session_paths, workspace)
    paths["build_path"].mkdir(parents=True, exist_ok=True)
    paths["state_root"].mkdir(parents=True, exist_ok=True)

    with build_lock(paths["state_root"], operation="prepare-session"):
        # Arduino의 library 선택과 include graph는 cache key와 독립적으로 바뀔 수 있습니다.
        # Placeholder만 매번 지워 graph를 다시 수집하고 실제 compile은 Ninja가 증분 판정합니다.
        invalidate_source_records(paths)
        workspace.mkdir(parents=True, exist_ok=True)
        with build_lock(workspace, operation="prepare-cache"):
            input_path = workspace / "input-manifest.json"
            stored_input: dict[str, Any] | None = None
            if input_path.is_file():
                try:
                    stored_input = load_json_object(input_path, "E_CACHE_INPUT")
                except AdapterError:
                    stored_input = None
            if (
                stored_input is not None
                and cache_key_for_manifest(stored_input) != cache_key
            ):
                raise AdapterError(
                    "[NU54:E_CACHE_KEY_COLLISION] 축약 cache directory의 전체 SHA-256이 다릅니다."
                )
            state_path = workspace / "state.json"
            state_document: dict[str, Any] | None = None
            if state_path.is_file():
                try:
                    state_document = load_json_object(state_path, "E_CACHE_STATE")
                except AdapterError:
                    state_document = None
            stored_state_key = (state_document or {}).get("cache_key")
            if (
                isinstance(stored_state_key, str)
                and re.fullmatch(r"[0-9a-f]{64}", stored_state_key)
                and stored_state_key != cache_key
            ):
                raise AdapterError(
                    "[NU54:E_CACHE_KEY_COLLISION] 축약 cache directory의 state SHA-256이 다릅니다."
                )

            # 전체 key 충돌 여부를 확인한 뒤에만 persistent tree를 변경합니다.
            materialize_application(paths, args)

            cache_exists = (paths["zephyr_build"] / "CMakeCache.txt").is_file()
            build_graph_exists = (paths["zephyr_build"] / "build.ninja").is_file()
            input_matches = stored_input == input_manifest
            state_matches = bool(
                state_document
                and state_document.get("schema_version") == CACHE_SCHEMA_VERSION
                and state_document.get("cache_key") == cache_key
                and state_document.get("state") == "ready"
                and state_document.get("first_configure_complete") is True
                and state_document.get("last_build_result") in {"not-built", "success"}
            )
            configure_required = not (
                cache_exists and build_graph_exists and input_matches and state_matches
            )
            if not cache_exists and not build_graph_exists and stored_input is None:
                configure_reason = "new-cache"
            elif not input_matches:
                configure_reason = "input-manifest-recovery"
            elif not state_matches:
                configure_reason = "state-recovery"
            else:
                configure_reason = "build-graph-recovery"

            atomic_write_json(input_path, input_manifest)
            configure_seconds = 0.0
            pristine_count = int((state_document or {}).get("pristine_configure_count", 0))
            recovery_count = int((state_document or {}).get("recovery_count", 0))
            if configure_required:
                transition_cache_state(
                    workspace,
                    cache_key,
                    "configuring",
                    configure_reason=configure_reason,
                    first_configure_complete=False,
                )
                started = time.perf_counter()
                try:
                    run_checked(
                        configure_command(
                            paths, args, tools, board_root.resolve(), pristine=True
                        ),
                        cwd=west_build_working_directory(paths),
                        environment=tools["environment"],
                    )
                except Exception as error:
                    transition_cache_state(
                        workspace,
                        cache_key,
                        "failed",
                        last_build_result="configure-failed",
                        failure=str(error),
                    )
                    raise
                configure_seconds = time.perf_counter() - started
                pristine_count += 1
                if configure_reason != "new-cache":
                    recovery_count += 1

            transition_cache_state(
                workspace,
                cache_key,
                "ready",
                first_configure_complete=True,
                last_build_result=(
                    "not-built"
                    if configure_required
                    else (state_document or {}).get("last_build_result", "not-built")
                ),
                configure_reason=configure_reason if configure_required else "cache-hit",
                configure_duration_seconds=round(configure_seconds, 6),
                pristine_configure_count=pristine_count,
                recovery_count=recovery_count,
            )
            context = {
                "schema_version": SESSION_CONTEXT_SCHEMA_VERSION,
                "adapter_version": ADAPTER_VERSION,
                "product_identity": product_identity,
                "state": "configured",
                "fqbn": args.fqbn,
                "board": args.board,
                "profile": getattr(args, "profile", DEFAULT_PROFILE),
                "sysbuild": False,
                "ncs_version": NCS_VERSION,
                "zephyr_version": "4.4.0",
                "platform_root": platform_root.as_posix(),
                "board_root": board_root.resolve().as_posix(),
                "sketch_root": paths["sketch_root"].as_posix(),
                "build_path": paths["build_path"].as_posix(),
                "cache_schema_version": CACHE_SCHEMA_VERSION,
                "cache_key": cache_key,
                "cache_root": cache_root.as_posix(),
                "cache_dir": workspace.as_posix(),
                "input_manifest": input_path.as_posix(),
                "app_dir": paths["app"].as_posix(),
                "zephyr_build_dir": paths["zephyr_build"].as_posix(),
                "ncs_root": tools["ncs_root"].as_posix(),
                "toolchain_root": tools["toolchain_root"].as_posix(),
                "toolchain_bundle_id": tools["toolchain_root"].name,
                "cxx_compiler": tools["compiler"].as_posix(),
                "size_tool": tools["size"].as_posix(),
                "ccache": tools["ccache"].as_posix() if tools.get("ccache") else None,
                "ccache_dir": tools["ccache_root"].as_posix(),
                "configuration_fingerprint": f"sha256:{cache_key}",
                "configure_mode": "cmake-only",
                "configure_reason": configure_reason if configure_required else "cache-hit",
                "configure_duration_seconds": round(configure_seconds, 6),
                "configure_skipped": not configure_required,
                "cache_reused": not configure_required,
                "pristine_configure_count": pristine_count,
                "recovery_count": recovery_count,
                "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            atomic_write_json(paths["context"], context)
            return context


## @brief context가 없으면 preprocessor 단계에서도 안전하게 최초 configure를 수행합니다.
def load_context(args: argparse.Namespace, create: bool = True) -> BuildContext:
    path = adapter_paths(args)["context"]
    if not path.is_file():
        if not create:
            raise AdapterError(f"configure context가 없습니다: {path}")
        return prepare(args)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"configure context를 읽지 못했습니다: {error}") from error


## @brief 현재 Arduino session이 가리키는 build tree만 제거합니다.
def clean_build(args: argparse.Namespace) -> None:
    paths = adapter_paths(args)
    with build_lock(paths["state_root"], operation="clean-session"):
        context = load_context(args, create=False)
        cache_key = context.get("cache_key")
        if not isinstance(cache_key, str):
            raise AdapterError("현재 session에 cache key가 없습니다.")
        contextual_paths = paths_from_context(paths, context)
        cache_root = local_cache_root(str(context["cache_root"]))
        removed_bytes = remove_cache_entry(cache_key, root=cache_root)
        if contextual_paths["workspace"].exists():
            raise AdapterError("현재 session의 cache tree 삭제가 완료되지 않았습니다.")
        for path in (
            paths["context"],
            paths["build_path"] / f"{args.project_name}.nu54-build.json",
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    print(json.dumps({"cache_key": cache_key, "removed_bytes": removed_bytes}, sort_keys=True))


## @brief 최종 feature cache key로 source record와 context를 원자적으로 이관합니다.
def migrate_feature_workspace(
    session_paths: dict[str, Path], args: argparse.Namespace, tools: dict[str, Any],
    context: dict[str, Any], records: Sequence[dict[str, Any]],
    selected_libraries: Sequence[str], input_manifest: dict[str, Any],
) -> tuple[dict[str, Path], dict[str, Any], str]:
    cache_key = cache_key_for_manifest(input_manifest)
    if context.get("cache_key") == cache_key:
        context.update({
            "selected_libraries": list(selected_libraries),
            "selected_features": input_manifest.get("configuration", {}).get("selected_features", []),
        })
        atomic_write_json(session_paths["context"], context)
        return paths_from_context(session_paths, context), context, cache_key
    cache_root = local_cache_root(str(context["cache_root"]))
    workspace = cache_workspace(cache_key, root=cache_root)
    paths = add_workspace_paths(session_paths, workspace)
    board_root = canonical_path(context["board_root"])
    workspace.mkdir(parents=True, exist_ok=True)
    with build_lock(workspace, operation="feature-cache-migration"):
        input_path = workspace / "input-manifest.json"
        stored = load_json_object(input_path, "E_CACHE_INPUT") if input_path.is_file() else None
        state = load_json_object(workspace / "state.json", "E_CACHE_STATE") if (workspace / "state.json").is_file() else None
        if stored is not None and cache_key_for_manifest(stored) != cache_key:
            raise AdapterError("[NU54:E_CACHE_KEY_COLLISION] feature cache directory의 전체 SHA-256이 다릅니다.")
        stored_state_key = (state or {}).get("cache_key")
        if isinstance(stored_state_key, str) and re.fullmatch(r"[0-9a-f]{64}", stored_state_key) and stored_state_key != cache_key:
            raise AdapterError("[NU54:E_CACHE_KEY_COLLISION] feature cache state의 전체 SHA-256이 다릅니다.")
        reusable = bool(stored == input_manifest and state and state.get("cache_key") == cache_key and state.get("state") == "ready" and state.get("first_configure_complete") is True and (paths["zephyr_build"] / "CMakeCache.txt").is_file() and (paths["zephyr_build"] / "build.ninja").is_file())
        materialize_application(paths, args, selected_libraries)
        atomic_write_json(input_path, input_manifest)
        configure_seconds = 0.0
        if not reusable:
            transition_cache_state(workspace, cache_key, "configuring", first_configure_complete=False, configure_reason="selected-features")
            started = time.perf_counter()
            try:
                run_checked(
                    configure_command(paths, args, tools, board_root, pristine=True),
                    cwd=west_build_working_directory(paths),
                    environment=tools["environment"],
                )
            except Exception as error:
                transition_cache_state(workspace, cache_key, "failed", first_configure_complete=False, last_build_result="configure-failed", failure=str(error))
                raise
            configure_seconds = time.perf_counter() - started
            transition_cache_state(workspace, cache_key, "ready", first_configure_complete=True, last_build_result="not-built", configure_reason="selected-features", configure_duration_seconds=round(configure_seconds, 6), pristine_configure_count=int((state or {}).get("pristine_configure_count", 0)) + 1)
    old_key = str(context["cache_key"])
    context.update({
        "cache_key": cache_key,
        "cache_dir": workspace.as_posix(),
        "input_manifest": (workspace / "input-manifest.json").as_posix(),
        "app_dir": paths["app"].as_posix(),
        "zephyr_build_dir": paths["zephyr_build"].as_posix(),
        "configuration_fingerprint": f"sha256:{cache_key}",
        "selected_libraries": list(selected_libraries),
        "selected_features": input_manifest.get("configuration", {}).get("selected_features", []),
        "provisional_cache_key": old_key,
        "configure_reason": "feature-cache-hit" if reusable else "selected-features",
        "configure_duration_seconds": round(configure_seconds, 6),
        "configure_skipped": reusable,
        "cache_reused": reusable,
        "pristine_configure_count": int((state or {}).get("pristine_configure_count", 0)) + (0 if reusable else 1),
    })
    atomic_write_json(session_paths["context"], context)
    for record in records:
        record["cache_key"] = cache_key
        atomic_write_json(record_path(session_paths["records"], canonical_path(record["object"])), record)
    return paths, context, cache_key


## @brief source manifest를 갱신하고 Full Zephyr image를 build/export합니다.
def link(args: argparse.Namespace) -> None:
    session_paths = adapter_paths(args)
    tools = tool_environment(canonical_path(args.platform_root))
    output_manifest = session_paths["build_path"] / f"{args.project_name}.nu54-build.json"

    with build_lock(session_paths["state_root"], operation="link-session"):
        context = load_context(args, create=False)
        rollback_context: dict[str, Any] | None = None
        if output_manifest.is_file():
            try:
                previous_manifest = load_json_object(output_manifest, "E_ARTIFACT_MANIFEST")
                previous_context = previous_manifest.get("context")
                if isinstance(previous_context, dict):
                    rollback_context = previous_context
            except AdapterError:
                rollback_context = None
        provisional_paths = paths_from_context(session_paths, context)
        records = records_for_objects(provisional_paths, args.objects, context)
        selected_libraries = selected_bundled_libraries(session_paths, records)
        current_input = cache_input_manifest(session_paths, args, tools, selected_libraries)
        paths, context, cache_key = migrate_feature_workspace(
            session_paths, args, tools, context, records, selected_libraries, current_input
        )
        with build_lock(paths["workspace"], operation="link-cache"):
            state_document = load_json_object(paths["workspace"] / "state.json", "E_CACHE_STATE")
            if (
                state_document.get("schema_version") != CACHE_SCHEMA_VERSION
                or state_document.get("cache_key") != cache_key
                or state_document.get("state") != "ready"
                or state_document.get("first_configure_complete") is not True
            ):
                raise AdapterError("[NU54:E_CACHE_STATE] build cache가 ready 상태가 아닙니다.")
            stored_input = load_json_object(
                paths["workspace"] / "input-manifest.json", "E_CACHE_INPUT"
            )
            if stored_input != current_input:
                raise AdapterError("[NU54:E_CACHE_CONTEXT_STALE] cache input manifest가 변경되었습니다.")
            transition_cache_state(
                paths["workspace"], cache_key, "building", last_build_result="running"
            )
            try:
                sources, source_provenance, manifest_changed = write_source_manifest(
                    paths, records
                )
                if not sources:
                    raise AdapterError(
                        "최종 Zephyr build에 전달할 sketch/library source가 없습니다."
                    )
            except Exception as error:
                transition_cache_state(
                    paths["workspace"],
                    cache_key,
                    "failed",
                    last_build_result="source-graph-failed",
                    failure=str(error),
                )
                raise

            ccache_before = read_ccache_stats(tools)
            configure_seconds = 0.0
            build_started = time.perf_counter()
            try:
                if manifest_changed:
                    configure_started = time.perf_counter()
                    run_checked(
                        configure_command(
                            paths,
                            args,
                            tools,
                            canonical_path(context["board_root"]),
                            pristine=False,
                        ),
                        cwd=west_build_working_directory(paths),
                        environment=tools["environment"],
                    )
                    configure_seconds = time.perf_counter() - configure_started
                run_checked(
                    [
                        tools["west"],
                        "-z",
                        tools["zephyr_base"],
                        "build",
                        "-d",
                        paths["zephyr_build"],
                    ],
                    cwd=west_build_working_directory(paths),
                    environment=tools["environment"],
                )
                memory_layout = validate_linked_code_partition(
                    paths["zephyr_build"] / "zephyr"
                )
            except Exception as error:
                transition_cache_state(
                    paths["workspace"],
                    cache_key,
                    "failed",
                    last_build_result="build-failed",
                    failure=str(error),
                )
                raise
            build_seconds = time.perf_counter() - build_started
            try:
                ccache_after = read_ccache_stats(tools)
                zephyr_output = paths["zephyr_build"] / "zephyr"
                artifacts = {
                    "elf": zephyr_output / "zephyr.elf",
                    "hex": zephyr_output / "zephyr.hex",
                    "bin": zephyr_output / "zephyr.bin",
                    "map": zephyr_output / "zephyr.map",
                }
                with publish_artifact_generation(
                    artifacts,
                    paths["build_path"],
                    args.project_name,
                    output_manifest,
                    paths["context"],
                    rollback_context,
                ) as exported:
                    build_record = paths["zephyr_build"] / "nucode_arduino_core_build.yml"
                    if not build_record.is_file():
                        raise AdapterError(
                            f"[NU54:E_BUILD_RECORD] live build record가 없습니다: {build_record}"
                        )
                    source_provenance["live_build_record"] = {
                        "path": build_record.as_posix(),
                        "sha256": file_sha256(build_record),
                    }
                    context.update(
                        {
                            "state": "built",
                            "source_manifest_changed": manifest_changed,
                            "link_configure_duration_seconds": round(configure_seconds, 6),
                            "build_duration_seconds": round(build_seconds, 6),
                            "ccache_stats_before": ccache_before,
                            "ccache_stats_after": ccache_after,
                            "ccache_stats_delta": ccache_delta(ccache_before, ccache_after),
                            "memory_layout": memory_layout,
                            "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                        }
                    )
                    atomic_write_json(paths["context"], context)
                    manifest: ArtifactManifest = {
                    "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
                    "adapter_version": ADAPTER_VERSION,
                    "product_identity": load_product_identity(paths["platform_root"]),
                    "fqbn": args.fqbn,
                    "board": args.board,
                    "sysbuild": False,
                    "cache": {
                        "schema_version": CACHE_SCHEMA_VERSION,
                        "key": cache_key,
                        "input_manifest": current_input,
                        "cache_dir": paths["workspace"].as_posix(),
                        "source_manifest_sha256": optional_file_sha256(
                            paths["app"] / "sources.cmake"
                        ),
                    },
                    "metrics": {
                        "configure_seconds": round(configure_seconds, 6),
                        "build_seconds": round(build_seconds, 6),
                        "ccache_delta": ccache_delta(ccache_before, ccache_after),
                    },
                    "context": context,
                    "sources": [path.as_posix() for path in sources],
                    "source_inputs": source_provenance,
                    "artifacts": exported,
                    "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    }
                    # Artifact와 context가 모두 완성된 뒤 manifest를 마지막으로 공개합니다.
                    atomic_write_json(output_manifest, manifest)
                    transition_cache_state(
                        paths["workspace"],
                        cache_key,
                        "ready",
                        first_configure_complete=True,
                        last_build_result="success",
                        last_artifact_manifest=output_manifest.as_posix(),
                        last_build_duration_seconds=round(build_seconds, 6),
                    )
            except Exception as error:
                transition_cache_state(
                    paths["workspace"],
                    cache_key,
                    "failed",
                    last_build_result="export-failed",
                    failure=str(error),
                )
                raise
    try:
        prune_build_cache(current_key=cache_key)
    except (AdapterError, OSError) as error:
        print(f"nu54-builder: warning: cache prune를 건너뜁니다: {error}", file=sys.stderr)


## @brief Arduino IDE가 parsing할 수 있는 FLASH/RAM 사용량을 출력합니다.
def print_size(args: argparse.Namespace) -> None:
    context = load_context(args, create=False)
    tools = tool_environment(canonical_path(args.platform_root))
    elf = canonical_path(args.build_path) / f"{args.project_name}.elf"
    result = run_checked(
        [context["size_tool"], elf],
        cwd=canonical_path(args.build_path),
        environment=tools["environment"],
        capture=True,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+[0-9a-fA-F]+", output, re.MULTILINE)
    if not match:
        raise AdapterError("ELF size 출력을 해석할 수 없습니다.")
    text_size, data_size, bss_size = (int(value) for value in match.groups())
    print(f"NU54_FLASH_USED={text_size + data_size}")
    print(f"NU54_RAM_USED={data_size + bss_size}")
