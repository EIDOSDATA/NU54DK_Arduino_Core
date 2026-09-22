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
import sys
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
    run_checked,
)
from .paths import adapter_paths, paths_from_context


RESOURCE_AUDIT_SCHEMA_VERSION = 1
RESOURCE_RAM_WARNING_PERCENT = 75.0
RESOURCE_RAM_FAILURE_PERCENT = 85.0
RESOURCE_TOP_RAM_SYMBOLS = 32


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
    mcuboot = re.search(
        r"^CONFIG_BOOTLOADER_MCUBOOT=y\s*$", configuration, re.MULTILINE
    ) is not None
    if mcuboot:
        start_offset_match = re.search(
            r"^CONFIG_ROM_START_OFFSET=(0x[0-9a-fA-F]+|[0-9]+)\s*$",
            configuration,
            re.MULTILINE,
        )
        end_offset_match = re.search(
            r"^CONFIG_ROM_END_OFFSET=(0x[0-9a-fA-F]+|[0-9]+)\s*$",
            configuration,
            re.MULTILINE,
        )
        if start_offset_match is None or end_offset_match is None:
            raise AdapterError(
                "[NU54:E_MEMORY_LAYOUT] MCUboot image의 ROM header/trailer 경계를 해석할 수 없습니다."
            )
        start_offset = int(start_offset_match.group(1), 0)
        end_offset = int(end_offset_match.group(1), 0)
        linked_region_matches = (
            start_offset > 0
            and end_offset > 0
            and linker_start == code_start
            and linker_size + end_offset == code_size
        )
    else:
        linked_region_matches = (linker_start, linker_size) == code_region
    if not linked_region_matches:
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


## @brief GNU size 기본 출력에서 text/data/bss byte를 해석합니다.
def parse_size_summary(output: str) -> dict[str, int]:
    match = re.search(
        r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+[0-9a-fA-F]+\s+.+$",
        output,
        re.MULTILINE,
    )
    if match is None:
        raise AdapterError("[NU54:E_RESOURCE_SIZE] ELF size 출력을 해석할 수 없습니다.")
    text_size, data_size, bss_size, decimal_size = (
        int(value) for value in match.groups()
    )
    if decimal_size != text_size + data_size + bss_size:
        raise AdapterError("[NU54:E_RESOURCE_SIZE] ELF size 합계가 일치하지 않습니다.")
    return {
        "text": text_size,
        "data": data_size,
        "bss": bss_size,
        "flash": text_size + data_size,
        "ram": data_size + bss_size,
    }


## @brief GNU size section 출력에서 실제 할당 section의 byte와 주소를 읽습니다.
def parse_section_sizes(output: str) -> list[dict[str, int | str]]:
    sections: list[dict[str, int | str]] = []
    for line in output.splitlines():
        match = re.fullmatch(r"\s*(\S+)\s+(\d+)\s+(\d+)\s*", line)
        if match is None or match.group(1) in {"section", "Total"}:
            continue
        name, size, address = match.groups()
        parsed_size = int(size)
        parsed_address = int(address)
        if parsed_size == 0 or parsed_address == 0:
            continue
        sections.append(
            {"name": name, "size": parsed_size, "address": parsed_address}
        )
    if not sections:
        raise AdapterError("[NU54:E_RESOURCE_SECTIONS] ELF section 출력을 해석할 수 없습니다.")
    return sections


## @brief linker map의 FLASH/RAM 영역 시작과 크기를 읽습니다.
def parse_memory_regions(memory_map: str) -> dict[str, dict[str, int]]:
    regions: dict[str, dict[str, int]] = {}
    for name in ("FLASH", "RAM"):
        match = re.search(
            rf"^{name}\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+\S+\s*$",
            memory_map,
            re.MULTILINE,
        )
        if match is None:
            raise AdapterError(
                f"[NU54:E_RESOURCE_REGION] linker map에 {name} 영역이 없습니다."
            )
        origin, size = (int(value, 16) for value in match.groups())
        if size <= 0:
            raise AdapterError(f"[NU54:E_RESOURCE_REGION] {name} 영역 크기가 0입니다.")
        regions[name.lower()] = {
            "origin": origin,
            "size": size,
            "end": origin + size,
        }
    return regions


## @brief GNU nm의 크기순 symbol 중 RAM 영역에 실제 배치된 항목을 반환합니다.
def parse_ram_symbols(
    output: str, ram_origin: int, ram_size: int, *, limit: int = RESOURCE_TOP_RAM_SYMBOLS
) -> list[dict[str, int | str]]:
    ram_end = ram_origin + ram_size
    symbols: list[dict[str, int | str]] = []
    for line in output.splitlines():
        match = re.fullmatch(r"\s*(\d+)\s+(\d+)\s+(\S)\s+(.+?)\s*", line)
        if match is None:
            continue
        address_text, size_text, symbol_type, name = match.groups()
        address = int(address_text)
        size = int(size_text)
        if size <= 0 or address < ram_origin or address >= ram_end:
            continue
        symbols.append(
            {
                "name": name,
                "type": symbol_type,
                "address": address,
                "size": size,
            }
        )
    symbols.sort(key=lambda item: (-int(item["size"]), str(item["name"])))
    return symbols[:limit]


## @brief size 실행 파일과 같은 toolchain prefix의 nm 경로를 반환합니다.
def nm_tool_for_size(size_tool: Path) -> Path:
    executable_suffix = ".exe" if size_tool.suffix.casefold() == ".exe" else ""
    stem = size_tool.name[: -len(executable_suffix)] if executable_suffix else size_tool.name
    if not stem.endswith("size"):
        raise AdapterError(
            f"[NU54:E_RESOURCE_TOOL] size 실행 파일 이름을 해석할 수 없습니다: {size_tool}"
        )
    nm_tool = size_tool.with_name(stem[:-4] + "nm" + executable_suffix)
    if not nm_tool.is_file():
        raise AdapterError(f"[NU54:E_RESOURCE_TOOL] nm 실행 파일이 없습니다: {nm_tool}")
    return nm_tool


## @brief 비활성 BLE 기능의 전용 정적 저장소가 ELF에 남았는지 검사합니다.
def forbidden_resource_symbols(configuration: str, nm_output: str) -> list[str]:
    checks = (
        ("CONFIG_BT_OBSERVER=y", "scan_result_queue"),
        ("CONFIG_BT_PER_ADV_SYNC=y", "periodic_report_queue"),
        ("CONFIG_BT_PER_ADV_RSP=y", "pawr_response_queue"),
        ("CONFIG_NUCODE_BLE_NUS=y", "ble_rx_queue"),
        ("CONFIG_NUCODE_BLE_NUS=y", "ble_event_queue"),
        ("CONFIG_NUCODE_BLE_GATT=y", "gatt_event_queue"),
        (
            "CONFIG_NUCODE_BLE_L2CAP=y",
            "nucode::ble::internal::l2cap::(anonymous namespace)",
        ),
        ("CONFIG_BT_SMP=y", "security_event_queue"),
        (
            "CONFIG_BT_SMP=y",
            "nucode::ble::internal::security::(anonymous namespace)::state",
        ),
    )
    findings: set[str] = set()
    configuration_lines = set(configuration.splitlines())
    for required, symbol_fragment in checks:
        if required in configuration_lines:
            continue
        for line in nm_output.splitlines():
            if symbol_fragment in line:
                match = re.fullmatch(r"\s*\d+\s+\d+\s+(\S)\s+(.+?)\s*", line)
                if match is not None and match.group(1) in "BbDdGgSsCc":
                    findings.add(match.group(2))
    return sorted(findings)


## @brief RAM region 대비 정적 예약률을 pass·warning·fail로 판정합니다.
def resource_budget_status(used_bytes: int, region_bytes: int) -> str:
    if used_bytes < 0 or region_bytes <= 0:
        raise AdapterError("[NU54:E_RESOURCE_BUDGET] RAM 사용량 또는 영역 크기가 잘못됐습니다.")
    used_percent = 100.0 * used_bytes / region_bytes
    if used_percent >= RESOURCE_RAM_FAILURE_PERCENT:
        return "fail"
    if used_percent >= RESOURCE_RAM_WARNING_PERCENT:
        return "warning"
    return "pass"


## @brief 최종 config·DTS·ELF/map의 정적 자원 증거를 machine-readable record로 만듭니다.
def collect_resource_audit(
    zephyr_output: Path,
    size_tool: Path,
    environment: dict[str, str],
    *,
    enforce_budget: bool,
    source_manifest: Path,
    resolution_manifest: Path | None = None,
) -> dict[str, Any]:
    inputs = {
        "config": zephyr_output / ".config",
        "devicetree": zephyr_output / "zephyr.dts",
        "elf": zephyr_output / "zephyr.elf",
        "map": zephyr_output / "zephyr.map",
        "source_manifest": source_manifest,
    }
    if resolution_manifest is not None:
        inputs["capability_resolution"] = resolution_manifest
    for name, path in inputs.items():
        if not path.is_file():
            raise AdapterError(f"[NU54:E_RESOURCE_INPUT] {name} 입력이 없습니다: {path}")

    summary_result = run_checked(
        [size_tool, inputs["elf"]],
        cwd=zephyr_output,
        environment=environment,
        capture=True,
    )
    section_result = run_checked(
        [size_tool, "-A", "-d", inputs["elf"]],
        cwd=zephyr_output,
        environment=environment,
        capture=True,
    )
    nm_result = run_checked(
        [
            nm_tool_for_size(size_tool),
            "-S",
            "--size-sort",
            "--radix=d",
            "--demangle",
            inputs["elf"],
        ],
        cwd=zephyr_output,
        environment=environment,
        capture=True,
    )
    summary = parse_size_summary(summary_result.stdout.decode("utf-8", errors="replace"))
    sections = parse_section_sizes(section_result.stdout.decode("utf-8", errors="replace"))
    nm_output = nm_result.stdout.decode("utf-8", errors="replace")
    configuration = inputs["config"].read_text(encoding="utf-8")
    regions = parse_memory_regions(inputs["map"].read_text(encoding="utf-8"))
    ram_region = regions["ram"]
    flash_region = regions["flash"]
    raw_ram_percent = 100.0 * summary["ram"] / ram_region["size"]
    raw_flash_percent = 100.0 * summary["flash"] / flash_region["size"]
    ram_percent = round(raw_ram_percent, 4)
    flash_percent = round(raw_flash_percent, 4)
    budget_status = resource_budget_status(summary["ram"], ram_region["size"])
    forbidden_symbols = forbidden_resource_symbols(configuration, nm_output)
    if enforce_budget and budget_status == "fail":
        raise AdapterError(
            "[NU54:E_RESOURCE_BUDGET] adaptive image의 정적 RAM 예약이 실패 상한 이상입니다: "
            f"{summary['ram']}/{ram_region['size']} bytes ({ram_percent}%)"
        )
    if enforce_budget and budget_status == "warning":
        print(
            "nu54-builder: warning: adaptive image의 정적 RAM 예약이 경고 상한 이상입니다: "
            f"{summary['ram']}/{ram_region['size']} bytes ({ram_percent}%)",
            file=sys.stderr,
        )
    if enforce_budget and forbidden_symbols:
        raise AdapterError(
            "[NU54:E_RESOURCE_SYMBOL] 비활성 기능의 정적 symbol이 ELF에 남았습니다: "
            + ", ".join(forbidden_symbols)
        )
    return {
        "schema_version": RESOURCE_AUDIT_SCHEMA_VERSION,
        "budget": {
            "enforced": enforce_budget,
            "warning_percent": RESOURCE_RAM_WARNING_PERCENT,
            "failure_percent": RESOURCE_RAM_FAILURE_PERCENT,
            "status": budget_status,
        },
        "flash": {
            "text_bytes": summary["text"],
            "data_bytes": summary["data"],
            "used_bytes": summary["flash"],
            "region_bytes": flash_region["size"],
            "headroom_bytes": flash_region["size"] - summary["flash"],
            "used_percent": flash_percent,
        },
        "ram": {
            "data_bytes": summary["data"],
            "bss_bytes": summary["bss"],
            "used_bytes": summary["ram"],
            "region_bytes": ram_region["size"],
            "headroom_bytes": ram_region["size"] - summary["ram"],
            "used_percent": ram_percent,
        },
        "regions": regions,
        "sections": sections,
        "top_ram_symbols": parse_ram_symbols(
            nm_output, ram_region["origin"], ram_region["size"]
        ),
        "forbidden_symbols": forbidden_symbols,
        "inputs": {
            name: {"path": path.as_posix(), "sha256": file_sha256(path)}
            for name, path in inputs.items()
        },
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


## @brief sysbuild domain과 flash 순서가 bootloader 다음 application인지 검증합니다.
def validate_sysbuild_domains(zephyr_build: Path) -> tuple[Path, Path]:
    domains_path = zephyr_build / "domains.yaml"
    if not domains_path.is_file():
        raise AdapterError(
            f"[NU54:E_FLASH_SYSBUILD_DOMAINS] domains.yaml이 없습니다: {domains_path}"
        )
    try:
        import yaml

        document = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise AdapterError(
            f"[NU54:E_FLASH_SYSBUILD_DOMAINS] domains.yaml을 읽지 못했습니다: {error}"
        ) from error
    if not isinstance(document, dict):
        raise AdapterError("[NU54:E_FLASH_SYSBUILD_DOMAINS] domains.yaml root가 object가 아닙니다.")
    default_domain = document.get("default")
    domains = document.get("domains")
    flash_order = document.get("flash_order")
    if (
        not isinstance(default_domain, str)
        or default_domain == "mcuboot"
        or not isinstance(domains, list)
        or len(domains) != 2
        or flash_order != ["mcuboot", default_domain]
    ):
        raise AdapterError(
            "[NU54:E_FLASH_SYSBUILD_DOMAINS] bootloader/application flash 순서가 고정 계약과 다릅니다."
        )
    domain_builds: dict[str, Path] = {}
    for entry in domains:
        if not isinstance(entry, dict) or set(entry) != {"name", "build_dir"}:
            raise AdapterError(
                "[NU54:E_FLASH_SYSBUILD_DOMAINS] domain record 형식이 잘못되었습니다."
            )
        name = entry.get("name")
        build_dir = entry.get("build_dir")
        if not isinstance(name, str) or not isinstance(build_dir, str) or name in domain_builds:
            raise AdapterError(
                "[NU54:E_FLASH_SYSBUILD_DOMAINS] domain 이름 또는 build directory가 잘못되었습니다."
            )
        resolved = canonical_path(build_dir)
        if not is_within(resolved, zephyr_build) or path_key(resolved) != path_key(
            zephyr_build / name
        ):
            raise AdapterError(
                "[NU54:E_FLASH_SYSBUILD_DOMAINS] domain build directory가 sysbuild root와 다릅니다."
            )
        domain_builds[name] = resolved
    if set(domain_builds) != {"mcuboot", default_domain}:
        raise AdapterError(
            "[NU54:E_FLASH_SYSBUILD_DOMAINS] MCUboot 또는 application domain이 없습니다."
        )
    return domain_builds["mcuboot"], domain_builds[default_domain]


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
    sysbuild = manifest.get("sysbuild")
    if not isinstance(sysbuild, bool):
        raise AdapterError("[NU54:E_FLASH_SYSBUILD] manifest의 sysbuild 값이 boolean이 아닙니다.")

    context = manifest.get("context")
    if not isinstance(context, dict):
        raise AdapterError("[NU54:E_FLASH_CONTEXT] manifest에 build context가 없습니다.")
    if context.get("schema_version") != SESSION_CONTEXT_SCHEMA_VERSION:
        raise AdapterError("[NU54:E_FLASH_CONTEXT] 지원하지 않는 session context version입니다.")
    if context.get("state") != "built":
        raise AdapterError("[NU54:E_FLASH_CONTEXT] 마지막으로 완료된 build context가 아닙니다.")
    if context.get("sysbuild") is not sysbuild:
        raise AdapterError("[NU54:E_FLASH_CONTEXT] manifest와 context의 sysbuild 값이 다릅니다.")
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
    runner_builds = [zephyr_build]
    if sysbuild:
        boot_build, application_build = validate_sysbuild_domains(zephyr_build)
        runner_builds = [boot_build, application_build]
        exported_boot, boot_hash = validate_manifest_artifact(
            manifest, "boot.hex", build_path
        )
        validate_manifest_artifact(manifest, "update.bin", build_path)
        native_boot = boot_build / "zephyr" / "zephyr.hex"
        if not native_boot.is_file() or native_boot.stat().st_size == 0:
            raise AdapterError(
                f"[NU54:E_FLASH_ARTIFACT_MISSING] native boot HEX가 없습니다: {native_boot}"
            )
        if file_sha256(native_boot) != boot_hash:
            raise AdapterError(
                "[NU54:E_FLASH_ARTIFACT_HASH] native boot HEX와 export artifact가 다릅니다."
            )
        native_hex = application_build / "zephyr" / "zephyr.signed.hex"
        native_elf = application_build / "zephyr" / "zephyr.elf"
    else:
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
        "runner_builds": runner_builds,
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
