"""! @brief source record와 결정적인 CMake 입력·provenance을 소유합니다. """

from __future__ import annotations
from .installed_platform import platform_compiled_path

from pathlib import Path
from typing import Any
from typing import Sequence
from .common import (
    AdapterError,
    FEATURE_ALLOWLIST,
    SOURCE_RECORD_SCHEMA_VERSION,
    atomic_write_bytes_if_changed,
    atomic_write_text,
    canonical_path,
    file_sha256,
    is_within,
    load_json_object,
    path_key,
    tree_content_sha256,
)
from .paths import record_path


## @brief cache key 변경 시 이전 placeholder와 source record만 안전하게 무효화합니다.
def invalidate_source_records(paths: dict[str, Path]) -> None:
    records_root = paths["records"]
    if not records_root.is_dir():
        return
    for record_file in records_root.glob("*.json"):
        try:
            record = load_json_object(record_file, "E_SOURCE_RECORD")
        except AdapterError:
            record = {}
        object_value = record.get("object")
        if isinstance(object_value, str):
            object_path = canonical_path(object_value)
            if is_within(object_path, paths["build_path"]):
                for candidate in (object_path, object_path.with_suffix(".d")):
                    try:
                        candidate.unlink()
                    except FileNotFoundError:
                        pass
        try:
            record_file.unlink()
        except FileNotFoundError:
            pass


## @brief link recipe object 목록에 대응하는 검증된 sketch/library record를 읽습니다.
def records_for_objects(
    paths: dict[str, Path], objects: Sequence[str], context: dict[str, Any]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for object_name in objects:
        if not object_name:
            continue
        object_path = canonical_path(object_name)
        if not is_within(object_path, paths["build_path"]):
            raise AdapterError(f"object가 Arduino build directory 밖에 있습니다: {object_path}")
        record_file = record_path(paths["records"], object_path)
        if not record_file.is_file():
            if object_path.suffix.lower() in {".a", ".ar"}:
                raise AdapterError(f"M5는 precompiled Arduino library를 지원하지 않습니다: {object_path}")
            missing.append(object_path.as_posix())
            continue
        record = load_json_object(record_file, "E_SOURCE_RECORD")
        include_dirs = record.get("include_dirs")
        if (
            record.get("schema_version") != SOURCE_RECORD_SCHEMA_VERSION
            or record.get("language") not in {"c", "cxx", "asm"}
            or not isinstance(record.get("source"), str)
            or not isinstance(record.get("object"), str)
            or path_key(record["object"]) != path_key(object_path)
            or not isinstance(include_dirs, list)
            or not all(isinstance(value, str) for value in include_dirs)
            or path_key(str(record.get("platform_root", "")))
            != path_key(paths["platform_root"])
            or record.get("cache_key") != context.get("cache_key")
        ):
            raise AdapterError(
                f"[NU54:E_SOURCE_RECORD_STALE] source record가 현재 build context와 다릅니다: {record_file}"
            )
        records.append(record)
    if missing:
        raise AdapterError("object에 대응하는 source record가 없습니다: " + ", ".join(missing))
    return records


## @brief source record에서 실제 선택된 bundled Arduino library 이름만 수집합니다.
def selected_bundled_libraries(
    paths: dict[str, Path], records: Sequence[dict[str, Any]]
) -> list[str]:
    libraries_root = paths["platform_root"] / "libraries"
    selected: set[str] = set()
    for record in records:
        candidates = [canonical_path(record["source"])]
        candidates.extend(canonical_path(value) for value in record.get("include_dirs", []) if isinstance(value, str))
        for candidate in candidates:
            if not is_within(candidate, libraries_root):
                continue
            try:
                relative = candidate.relative_to(libraries_root)
            except ValueError:
                continue
            if relative.parts and relative.parts[0] in FEATURE_ALLOWLIST:
                selected.add(relative.parts[0])
    return sorted(selected, key=str.casefold)


## @brief CMake string literal에 사용할 path를 escape합니다.
def cmake_quote(path: Path) -> str:
    return path.as_posix().replace("\\", "/").replace("\"", "\\\"").replace(";", "\\;")


## @brief Arduino 임시 build path와 무관한 source logical identity를 생성합니다.
def source_logical_identity(source: Path, paths: dict[str, Path]) -> str:
    if is_within(source, paths["build_path"]):
        try:
            relative = source.resolve().relative_to(paths["build_path"].resolve()).as_posix()
        except ValueError:
            relative = source.name
        return f"arduino-generated:{relative}"
    if is_within(source, paths["sketch_root"]):
        relative = source.resolve().relative_to(paths["sketch_root"].resolve()).as_posix()
        return f"sketch:{relative}"
    if is_within(source, paths["platform_root"]):
        relative = source.resolve().relative_to(paths["platform_root"].resolve()).as_posix()
        return f"platform:{relative}"
    return f"external:{path_key(source)}"


## @brief source record를 결정적인 sources.cmake와 provenance로 변환합니다.
def write_source_manifest(
    paths: dict[str, Path], records: Sequence[dict[str, Any]]
) -> tuple[list[Path], dict[str, Any], bool]:
    core_root = paths["platform_root"] / "cores"
    variant_root = paths["platform_root"] / "variants"
    sources: list[Path] = []
    source_keys: set[str] = set()
    includes: list[Path] = []
    include_keys: set[str] = set()

    def add_include(include: Path) -> None:
        key = path_key(include)
        if key not in include_keys and include.is_dir() and not is_within(include, paths["build_path"]):
            include_keys.add(key)
            includes.append(platform_compiled_path(include, paths))

    # Arduino의 sketch-local header 우선권을 보존합니다.
    add_include(paths["sketch_root"])
    for record in records:
        source = canonical_path(record["source"])
        if is_within(source, core_root) or is_within(source, variant_root):
            continue
        if not source.is_file():
            raise AdapterError(f"Arduino source가 사라졌습니다: {source}")
        source_key = path_key(source)
        if source_key not in source_keys:
            source_keys.add(source_key)
            sources.append(source)
        for value in record.get("include_dirs", []):
            add_include(canonical_path(value))
        if not is_within(source.parent, paths["build_path"]):
            add_include(source.parent)

    compiled_sources: list[Path] = []
    source_inputs: list[dict[str, str]] = []
    mirror_root = paths["app"] / "generated-sources"
    mirror_owners: dict[str, str] = {}
    for source in sources:
        logical_identity = source_logical_identity(source, paths)
        compiled_source = platform_compiled_path(source, paths)
        if compiled_source != source and file_sha256(compiled_source) != file_sha256(source):
            raise AdapterError('[NU54:E_PLATFORM_COPY_STALE] 설치 source와 build 복사본 bytes가 다릅니다.')
        if is_within(source, paths["build_path"]):
            relative = source.resolve().relative_to(paths["build_path"].resolve())
            mirror = canonical_path(mirror_root / relative)
            if not is_within(mirror, mirror_root):
                raise AdapterError(f"[NU54:E_SOURCE_MIRROR_PATH] mirror 경로가 잘못되었습니다: {mirror}")
            mirror_key = path_key(mirror)
            previous_owner = mirror_owners.get(mirror_key)
            if previous_owner is not None and previous_owner != logical_identity:
                raise AdapterError(
                    "[NU54:E_SOURCE_MIRROR_COLLISION] 서로 다른 source가 같은 mirror를 사용합니다: "
                    f"{previous_owner}, {logical_identity}"
                )
            mirror_owners[mirror_key] = logical_identity
            atomic_write_bytes_if_changed(mirror, source.read_bytes())
            compiled_source = mirror
            add_include(mirror.parent)
        compiled_sources.append(compiled_source)
        source_inputs.append(
            {
                "logical_identity": logical_identity,
                "source_path": source.as_posix(),
                "compiled_path": compiled_source.as_posix(),
                "sha256": file_sha256(source),
            }
        )

    lines = ["# nu54-builder가 원자적으로 생성한 source manifest입니다.", "set(NUCODE_ARDUINO_SKETCH_SOURCES"]
    lines.extend(f'  "{cmake_quote(path)}"' for path in compiled_sources)
    lines.append(")")
    lines.append("set(NUCODE_ARDUINO_INCLUDE_DIRS")
    lines.extend(f'  "{cmake_quote(path)}"' for path in includes)
    lines.extend((")", ""))
    changed = atomic_write_text(paths["app"] / "sources.cmake", "\n".join(lines))
    provenance = {
        "sources": source_inputs,
        "include_roots": [
            {
                "path": include.as_posix(),
                "content_sha256": tree_content_sha256(include, (".",)),
            }
            for include in includes
        ],
    }
    return sources, provenance, changed
