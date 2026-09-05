"""! @brief partition·artifact publication과 manifest 무결성을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Iterator
import argparse
import contextlib
import os
import re
import shutil
import tempfile
from .cache import cache_key_for_manifest
from .common import (
    ADAPTER_VERSION,
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    AdapterError,
    CACHE_SCHEMA_VERSION,
    CONTEXT_DIRECTORY,
    SESSION_CONTEXT_SCHEMA_VERSION,
    atomic_write_bytes,
    atomic_write_json,
    canonical_path,
    file_sha256,
    is_within,
    load_json_object,
    path_key,
)
from .paths import adapter_paths, paths_from_context


## @brief 생성된 devicetree에서 이름을 가진 mapped partition의 주소와 크기를 반환합니다.
def generated_mapped_partition(
    devicetree: str, label: str, *, required: bool = True
) -> tuple[int, int] | None:
    node = re.search(
        rf"^\s*{re.escape(label)}:\s+partition@[0-9a-fA-F]+\s*\{{(?P<body>.*?)^\s*\}};",
        devicetree,
        re.MULTILINE | re.DOTALL,
    )
    if node is None:
        if required:
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] generated devicetree에 {label} partition이 없습니다."
            )
        return None
    body = node.group("body")
    if not re.search(r'compatible\s*=\s*"zephyr,mapped-partition"\s*;', body):
        raise AdapterError(
            f"[NU54:E_MEMORY_LAYOUT] {label}이 zephyr,mapped-partition이 아닙니다."
        )
    region = re.search(
        r"reg\s*=\s*<\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*>\s*;",
        body,
    )
    if region is None:
        raise AdapterError(
            f"[NU54:E_MEMORY_LAYOUT] {label} partition의 reg 영역을 해석할 수 없습니다."
        )
    address, size = (int(value, 16) for value in region.groups())
    if size <= 0:
        raise AdapterError(f"[NU54:E_MEMORY_LAYOUT] {label} partition 크기가 0입니다.")
    return address, size


## @brief 선택한 code partition과 실제 linker FLASH 영역이 같은지 fail-closed로 검증합니다.
def validate_linked_code_partition(zephyr_output: Path) -> dict[str, int | str]:
    configuration_path = zephyr_output / ".config"
    devicetree_path = zephyr_output / "zephyr.dts"
    map_path = zephyr_output / "zephyr.map"
    for required in (configuration_path, devicetree_path, map_path):
        if not required.is_file():
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] linker memory 검증 입력이 없습니다: {required}"
            )

    configuration = configuration_path.read_text(encoding="utf-8")
    for symbol in ("CONFIG_USE_DT_CODE_PARTITION", "CONFIG_FLASH_USES_MAPPED_PARTITION"):
        if not re.search(rf"^{re.escape(symbol)}=y\s*$", configuration, re.MULTILINE):
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] {symbol}=y가 아니므로 linker 경계를 보장할 수 없습니다."
            )

    devicetree = devicetree_path.read_text(encoding="utf-8")
    chosen = re.search(
        r"zephyr,code-partition\s*=\s*&([A-Za-z_][A-Za-z0-9_]*)\s*;",
        devicetree,
    )
    if chosen is None:
        raise AdapterError(
            "[NU54:E_MEMORY_LAYOUT] /chosen/zephyr,code-partition을 해석할 수 없습니다."
        )
    code_label = chosen.group(1)
    code_region = generated_mapped_partition(devicetree, code_label)
    assert code_region is not None
    code_start, code_size = code_region
    code_end = code_start + code_size

    reserved_regions: list[tuple[str, int, int]] = []
    for label in ("arduino_fs_partition", "storage_partition"):
        region = generated_mapped_partition(devicetree, label, required=False)
        if region is not None:
            start, size = region
            reserved_regions.append((label, start, start + size))
    for label, start, end in reserved_regions:
        if max(code_start, start) < min(code_end, end):
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] code partition이 {label}과 겹칩됩니다: "
                f"0x{code_start:x}..0x{code_end:x} / 0x{start:x}..0x{end:x}"
            )
    ordered_reserved = sorted(reserved_regions, key=lambda item: item[1])
    for previous, current in zip(ordered_reserved, ordered_reserved[1:]):
        if previous[2] > current[1]:
            raise AdapterError(
                f"[NU54:E_MEMORY_LAYOUT] {previous[0]}와 {current[0]} 저장소가 겹칩됩니다."
            )

    memory_map = map_path.read_text(encoding="utf-8")
    flash = re.search(
        r"^FLASH\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+\S+\s*$",
        memory_map,
        re.MULTILINE,
    )
    if flash is None:
        raise AdapterError("[NU54:E_MEMORY_LAYOUT] linker map의 FLASH 영역을 해석할 수 없습니다.")
    linker_start, linker_size = (int(value, 16) for value in flash.groups())
    if (linker_start, linker_size) != code_region:
        raise AdapterError(
            "[NU54:E_MEMORY_LAYOUT] linker FLASH 영역과 devicetree code partition이 다릅니다: "
            f"linker=0x{linker_start:x}+0x{linker_size:x}, "
            f"devicetree=0x{code_start:x}+0x{code_size:x}"
        )
    return {
        "code_partition": code_label,
        "flash_origin": code_start,
        "flash_size": code_size,
        "flash_end": code_end,
    }


## @brief Zephyr artifact를 Arduino build path로 원자적으로 복사합니다.
def copy_artifact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise AdapterError(f"Zephyr artifact가 없습니다: {source}")
    atomic_write_bytes(destination, source.read_bytes())


## @brief 모든 artifact를 staging한 뒤 한 generation으로 export하고 실패 시 복원합니다.
def export_artifacts_transactionally(
    artifacts: dict[str, Path], build_path: Path, project_name: str
) -> dict[str, Any]:
    staging_parent = build_path / CONTEXT_DIRECTORY / "artifact-staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="generation-", dir=staging_parent))
    backup = staging / "backup"
    backup.mkdir()
    staged: dict[str, Path] = {}
    destinations: dict[str, Path] = {}
    exported: dict[str, Any] = {}
    committed: list[str] = []
    preserve_staging = False
    try:
        for extension, source in artifacts.items():
            staged_path = staging / f"new.{extension}"
            copy_artifact(source, staged_path)
            staged[extension] = staged_path
            destination = build_path / f"{project_name}.{extension}"
            destinations[extension] = destination
            exported[extension] = {
                "path": destination.as_posix(),
                "sha256": file_sha256(staged_path),
                "size": staged_path.stat().st_size,
            }
        for extension, destination in destinations.items():
            if destination.is_file():
                shutil.copy2(destination, backup / extension)
        try:
            for extension in artifacts:
                destination = destinations[extension]
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged[extension], destination)
                committed.append(extension)
            for extension, destination in destinations.items():
                record = exported[extension]
                if (
                    not destination.is_file()
                    or destination.stat().st_size != record["size"]
                    or file_sha256(destination) != record["sha256"]
                ):
                    raise AdapterError(
                        f"[NU54:E_EXPORT_INTEGRITY] export artifact 검증에 실패했습니다: {destination}"
                    )
        except BaseException as original_error:
            try:
                for extension, destination in destinations.items():
                    old_artifact = backup / extension
                    if old_artifact.is_file():
                        os.replace(old_artifact, destination)
                    elif extension in committed:
                        try:
                            destination.unlink()
                        except FileNotFoundError:
                            pass
            except BaseException as rollback_error:
                preserve_staging = True
                raise AdapterError(
                    "[NU54:E_EXPORT_ROLLBACK] artifact 복구에 실패했습니다. "
                    f"수동 복구 directory: {staging}; 원인: {rollback_error}"
                ) from original_error
            raise
        return exported
    finally:
        if not preserve_staging:
            shutil.rmtree(staging, ignore_errors=True)


## @brief artifact와 공개 manifest를 metadata commit 끝까지 하나의 rollback 범위로 묶습니다.
@contextlib.contextmanager
def publish_artifact_generation(
    artifacts: dict[str, Path],
    build_path: Path,
    project_name: str,
    manifest_path: Path,
    context_path: Path,
    rollback_context: dict[str, Any] | None,
) -> Iterator[dict[str, Any]]:
    transaction_root = build_path / CONTEXT_DIRECTORY / "publish-transactions"
    transaction_root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="generation-", dir=transaction_root))
    preserve_backup = False
    destinations = {
        extension: build_path / f"{project_name}.{extension}"
        for extension in artifacts
    }
    existed: dict[str, bool] = {}
    try:
        for extension, destination in destinations.items():
            existed[extension] = destination.is_file()
            if existed[extension]:
                shutil.copy2(destination, backup / extension)
        manifest_existed = manifest_path.is_file()
        if manifest_existed:
            shutil.copy2(manifest_path, backup / "manifest.json")
        context_bytes = context_path.read_bytes() if context_path.is_file() else None
        exported = export_artifacts_transactionally(artifacts, build_path, project_name)
        try:
            yield exported
        except BaseException as original_error:
            try:
                for extension, destination in destinations.items():
                    previous = backup / extension
                    if existed[extension]:
                        os.replace(previous, destination)
                    else:
                        try:
                            destination.unlink()
                        except FileNotFoundError:
                            pass
                if rollback_context is not None:
                    atomic_write_json(context_path, rollback_context)
                elif context_bytes is not None:
                    atomic_write_bytes(context_path, context_bytes)
                else:
                    try:
                        context_path.unlink()
                    except FileNotFoundError:
                        pass
                if manifest_existed:
                    os.replace(backup / "manifest.json", manifest_path)
                else:
                    try:
                        manifest_path.unlink()
                    except FileNotFoundError:
                        pass
            except BaseException as rollback_error:
                preserve_backup = True
                raise AdapterError(
                    "[NU54:E_EXPORT_ROLLBACK] 공개 generation 복구에 실패했습니다. "
                    f"수동 복구 directory: {backup}; 원인: {rollback_error}"
                ) from original_error
            raise
    finally:
        if not preserve_backup:
            shutil.rmtree(backup, ignore_errors=True)


## @brief manifest artifact 한 개의 경로, 크기와 SHA-256을 검증합니다.
def validate_manifest_artifact(
    manifest: dict[str, Any], extension: str, build_path: Path
) -> tuple[Path, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get(extension), dict):
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] manifest에 {extension} artifact가 없습니다.")
    record = artifacts[extension]
    artifact = canonical_path(str(record.get("path", "")))
    if not is_within(artifact, build_path):
        raise AdapterError(
            f"[NU54:E_FLASH_ARTIFACT_PATH] {extension} artifact가 Arduino build directory 밖에 있습니다: {artifact}"
        )
    if not artifact.is_file() or artifact.stat().st_size == 0:
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] {extension} artifact가 없습니다: {artifact}")
    expected_size = record.get("size")
    expected_hash = record.get("sha256")
    if not isinstance(expected_size, int) or expected_size != artifact.stat().st_size:
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_HASH] {extension} artifact 크기가 manifest와 다릅니다.")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_HASH] {extension} SHA-256 기록이 잘못되었습니다.")
    actual_hash = file_sha256(artifact)
    if actual_hash != expected_hash:
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_HASH] {extension} artifact SHA-256이 manifest와 다릅니다.")
    return artifact, actual_hash


## @brief M8 upload가 사용할 manifest와 native Zephyr artifact를 검증합니다.
def validate_flash_manifest(args: argparse.Namespace) -> dict[str, Any]:
    build_path = canonical_path(args.build_path)
    manifest_path = canonical_path(args.manifest)
    expected_manifest = build_path / f"{args.project_name}.nu54-build.json"
    if path_key(manifest_path) != path_key(expected_manifest):
        raise AdapterError(
            f"[NU54:E_FLASH_MANIFEST_PATH] 현재 build의 manifest가 아닙니다: {manifest_path}"
        )
    if not manifest_path.is_file():
        raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] build manifest가 없습니다: {manifest_path}")
    manifest = load_json_object(manifest_path, "E_FLASH_MANIFEST")
    if (
        manifest.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION
        or manifest.get("adapter_version") != ADAPTER_VERSION
    ):
        raise AdapterError("[NU54:E_FLASH_MANIFEST_VERSION] 지원하지 않는 build manifest version입니다.")
    if manifest.get("fqbn") != args.fqbn or manifest.get("board") != args.board:
        raise AdapterError("[NU54:E_FLASH_BOARD_MISMATCH] manifest의 FQBN 또는 Zephyr board가 다릅니다.")
    if manifest.get("sysbuild") is not False:
        raise AdapterError(
            "[NU54:E_FLASH_SYSBUILD_UNSUPPORTED] M8 upload는 non-sysbuild zephyr.hex만 지원합니다."
        )

    context = manifest.get("context")
    if not isinstance(context, dict):
        raise AdapterError("[NU54:E_FLASH_CONTEXT] manifest에 build context가 없습니다.")
    if context.get("schema_version") != SESSION_CONTEXT_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_FLASH_CONTEXT] 지원하지 않는 session context version입니다.")
    if context.get("state") != "built":
        raise AdapterError("[NU54:E_FLASH_CONTEXT] 마지막으로 완료된 build context가 아닙니다.")
    context_pairs = {
        "fqbn": args.fqbn,
        "board": args.board,
        "build_path": build_path.as_posix(),
        "platform_root": canonical_path(args.platform_root).as_posix(),
    }
    for key, expected in context_pairs.items():
        value = context.get(key)
        if key.endswith("_path") or key.endswith("_root"):
            matches = isinstance(value, str) and path_key(value) == path_key(expected)
        else:
            matches = value == expected
        if not matches:
            raise AdapterError(f"[NU54:E_FLASH_CONTEXT] build context의 {key} 값이 현재 요청과 다릅니다.")

    cache = manifest.get("cache")
    if not isinstance(cache, dict) or cache.get("schema_version") != CACHE_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_FLASH_CACHE] manifest의 M9 cache metadata가 잘못되었습니다.")
    cache_key = cache.get("key")
    input_manifest = cache.get("input_manifest")
    if (
        not isinstance(cache_key, str)
        or not re.fullmatch(r"[0-9a-f]{64}", cache_key)
        or not isinstance(input_manifest, dict)
        or cache_key_for_manifest(input_manifest) != cache_key
        or context.get("cache_key") != cache_key
    ):
        raise AdapterError("[NU54:E_FLASH_CACHE] cache key 또는 input manifest가 일치하지 않습니다.")
    contextual_paths = paths_from_context(adapter_paths(args), context)
    if path_key(str(cache.get("cache_dir", ""))) != path_key(contextual_paths["workspace"]):
        raise AdapterError("[NU54:E_FLASH_CACHE] artifact와 context의 cache directory가 다릅니다.")
    stored_input = load_json_object(
        contextual_paths["workspace"] / "input-manifest.json", "E_FLASH_CACHE"
    )
    state_document = load_json_object(
        contextual_paths["workspace"] / "state.json", "E_FLASH_CACHE"
    )
    if stored_input != input_manifest or (
        state_document.get("schema_version") != CACHE_SCHEMA_VERSION
        or state_document.get("cache_key") != cache_key
        or state_document.get("state") != "ready"
        or state_document.get("last_build_result") != "success"
    ):
        raise AdapterError("[NU54:E_FLASH_CACHE] 현재 cache generation이 build manifest와 다릅니다.")

    exported_hex, hex_hash = validate_manifest_artifact(manifest, "hex", build_path)
    exported_elf, elf_hash = validate_manifest_artifact(manifest, "elf", build_path)
    zephyr_build = canonical_path(str(context.get("zephyr_build_dir", "")))
    if path_key(zephyr_build) != path_key(contextual_paths["zephyr_build"]):
        raise AdapterError("[NU54:E_FLASH_CONTEXT] Zephyr build directory가 cache context와 다릅니다.")
    if not (zephyr_build / "CMakeCache.txt").is_file() or not (zephyr_build / "build.ninja").is_file():
        raise AdapterError(f"[NU54:E_FLASH_CONTEXT] 유효한 Zephyr build directory가 아닙니다: {zephyr_build}")
    native_hex = zephyr_build / "zephyr" / "zephyr.hex"
    native_elf = zephyr_build / "zephyr" / "zephyr.elf"
    for extension, native, exported_hash in (
        ("hex", native_hex, hex_hash),
        ("elf", native_elf, elf_hash),
    ):
        if not native.is_file() or native.stat().st_size == 0:
            raise AdapterError(f"[NU54:E_FLASH_ARTIFACT_MISSING] native {extension} artifact가 없습니다: {native}")
        if file_sha256(native) != exported_hash:
            raise AdapterError(
                f"[NU54:E_FLASH_ARTIFACT_HASH] native {extension}와 export artifact가 다릅니다."
            )
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "build_path": build_path,
        "zephyr_build": zephyr_build,
        "hex": exported_hex,
        "elf": exported_elf,
        "hex_sha256": hex_hash,
        "elf_sha256": elf_hash,
    }


## @brief cache tree와 독립적으로 export artifact의 manifest 무결성을 검증합니다.
def verify_artifact(args: argparse.Namespace) -> None:
    artifact = canonical_path(args.artifact)
    build_path = canonical_path(args.build_path)
    manifest_path = build_path / f"{args.project_name}.nu54-build.json"
    manifest = load_json_object(manifest_path, "E_ARTIFACT_MANIFEST")
    if (
        manifest.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION
        or manifest.get("adapter_version") != ADAPTER_VERSION
        or manifest.get("fqbn") != args.fqbn
        or manifest.get("board") != args.board
    ):
        raise AdapterError("export artifact manifest의 version 또는 target이 다릅니다.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise AdapterError("export artifact manifest에 artifact 목록이 없습니다.")
    matching = [
        extension
        for extension, record in artifacts.items()
        if isinstance(record, dict)
        and isinstance(record.get("path"), str)
        and path_key(record["path"]) == path_key(artifact)
    ]
    if len(matching) != 1:
        raise AdapterError(f"요청 artifact가 현재 build manifest에 없습니다: {artifact}")
    validate_manifest_artifact(manifest, matching[0], build_path)
