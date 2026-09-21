"""! @brief source record를 compiler-assisted capability probe로 연결합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Sequence
import hashlib
import os

from .capabilities import capabilities_for_probe_symbols, parse_undefined_symbols
from .common import (
    AdapterError,
    CAPABILITY_PROBE_SCHEMA_VERSION,
    atomic_write_json,
    canonical_path,
    file_sha256,
    is_within,
    path_key,
    run_checked,
)
from .source_graph import source_logical_identity


## @brief C++ compiler와 같은 target prefix의 고정 보조 도구를 검증합니다.
def _toolchain_sibling(compiler: Path, program: str, toolchain_root: Path) -> Path:
    suffix = compiler.suffix
    stem = compiler.stem
    if not stem.endswith("g++"):
        raise AdapterError(
            f"[NU54:E_CAPABILITY_PROBE_TOOL] GCC C++ compiler 이름이 아닙니다: {compiler}"
        )
    prefix = stem[: -len("g++")]
    candidate = canonical_path(compiler.with_name(prefix + program + suffix))
    if not is_within(candidate, toolchain_root) or not candidate.is_file():
        raise AdapterError(
            f"[NU54:E_CAPABILITY_PROBE_TOOL] {program} 실행 파일을 찾을 수 없습니다: {candidate}"
        )
    if os.name != "nt" and not os.access(candidate, os.X_OK):
        raise AdapterError(
            f"[NU54:E_CAPABILITY_PROBE_TOOL] {program} 실행 권한이 없습니다: {candidate}"
        )
    return candidate


## @brief nm POSIX 출력에서 정의된 symbol 이름을 반환합니다.
def _defined_symbols(output: str) -> set[str]:
    symbols: set[str] = set()
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[1] not in {"U", "w", "v"}:
            symbols.add(fields[0])
    return symbols


## @brief probe에 포함할 sketch와 외부 library source만 결정적으로 선택합니다.
def _probe_records(
    paths: dict[str, Path], records: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    excluded_roots = (
        paths["platform_root"] / "cores",
        paths["platform_root"] / "variants",
        paths["platform_root"] / "libraries",
    )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        source = canonical_path(record["source"])
        if any(is_within(source, root) for root in excluded_roots):
            continue
        key = path_key(source)
        if key in seen:
            continue
        if record.get("language") == "asm":
            raise AdapterError(
                "[NU54:E_CAPABILITY_PROBE_ASM] 외부 assembly source의 capability를 "
                "판정할 수 없습니다. library feature manifest에 요구 기능을 선언하십시오: "
                f"{source}"
            )
        if record.get("language") not in {"c", "cxx"}:
            raise AdapterError(
                f"[NU54:E_CAPABILITY_PROBE_LANGUAGE] 지원하지 않는 source 언어입니다: {source}"
            )
        if not source.is_file():
            raise AdapterError(f"[NU54:E_CAPABILITY_PROBE_SOURCE] source가 없습니다: {source}")
        seen.add(key)
        selected.append(record)
    return sorted(
        selected,
        key=lambda item: source_logical_identity(canonical_path(item["source"]), paths),
    )


## @brief 같은 compiler의 executable section GC link로 도달 가능한 API 참조를 남깁니다.
def run_capability_probe(
    paths: dict[str, Path],
    records: Sequence[dict[str, Any]],
    tools: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    compiler = canonical_path(tools["compiler"])
    toolchain_root = canonical_path(tools["toolchain_root"])
    gcc = _toolchain_sibling(compiler, "gcc", toolchain_root)
    nm = _toolchain_sibling(compiler, "nm", toolchain_root)
    environment = tools["environment"]
    probe_root = canonical_path(paths["state_root"] / "capability-probe")
    if not is_within(probe_root, paths["build_path"]):
        raise AdapterError(
            f"[NU54:E_CAPABILITY_PROBE_PATH] probe directory가 build path 밖입니다: {probe_root}"
        )
    object_root = probe_root / "objects"
    object_root.mkdir(parents=True, exist_ok=True)

    selected = _probe_records(paths, records)
    if not selected:
        raise AdapterError(
            "[NU54:E_CAPABILITY_PROBE_SOURCE] probe할 sketch/library source가 없습니다."
        )
    include_dirs: dict[str, Path] = {}
    for include in (
        paths["platform_root"] / "cores" / "arduino",
        paths["platform_root"] / "variants" / "nu54dk",
        paths["platform_root"] / "third_party" / "ArduinoCore-API",
        paths["sketch_root"],
    ):
        if include.is_dir():
            include_dirs[path_key(include)] = canonical_path(include)
    for record in selected:
        for value in record.get("include_dirs", []):
            include = canonical_path(value)
            if include.is_dir():
                include_dirs[path_key(include)] = include

    common: list[str | Path] = [
        "-mcpu=cortex-m33",
        "-mthumb",
        "-ffunction-sections",
        "-fdata-sections",
        "-fno-lto",
        "-fno-common",
        "-DARDUINO=10607",
        "-DARDUINO_ARCH_ZEPHYR",
        "-DARDUINO_NUCODE_NU54DK",
        "-DNUCODE_CAPABILITY_PROBE=1",
    ]
    for include in include_dirs.values():
        common.extend(("-I", include))

    objects: list[Path] = []
    source_manifest: list[dict[str, str]] = []
    for record in selected:
        source = canonical_path(record["source"])
        identity = source_logical_identity(source, paths)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        object_path = object_root / f"{digest}.o"
        language = record["language"]
        command: list[str | Path] = [gcc if language == "c" else compiler]
        command.extend(common)
        if language == "c":
            command.extend(("-x", "c", "-std=gnu11"))
        else:
            command.extend(("-x", "c++", "-std=gnu++17", "-fno-exceptions", "-fno-rtti"))
        command.extend(("-c", source, "-o", object_path))
        try:
            run_checked(command, cwd=paths["sketch_root"], environment=environment)
        except AdapterError as error:
            raise AdapterError(
                "[NU54:E_CAPABILITY_PROBE_COMPILE] capability probe compile에 실패했습니다. "
                "직접 Zephyr API 또는 판정 불가능한 외부 library는 feature manifest에 "
                f"capability를 선언하십시오: {source}: {error}"
            ) from error
        objects.append(object_path)
        source_manifest.append(
            {
                "logical_identity": identity,
                "path": source.as_posix(),
                "sha256": file_sha256(source),
                "language": language,
            }
        )

    linked = probe_root / "capability-probe.elf"
    map_path = probe_root / "capability-probe.map"
    link_command: list[str | Path] = [
        compiler,
        "-mcpu=cortex-m33",
        "-mthumb",
        "-nostdlib",
        "-Wl,--gc-sections",
        "-Wl,-e,setup",
        "-Wl,-u,setup",
        "-Wl,-u,loop",
        "-Wl,--unresolved-symbols=ignore-all",
        f"-Wl,-Map={map_path.as_posix()}",
        "-o",
        linked,
        *objects,
    ]
    try:
        run_checked(
            link_command,
            cwd=probe_root,
            environment=environment,
        )
    except AdapterError as error:
        raise AdapterError(
            f"[NU54:E_CAPABILITY_PROBE_LINK] capability probe link에 실패했습니다: {error}"
        ) from error

    undefined_result = run_checked(
        [nm, "--format=posix", "--undefined-only", linked],
        cwd=probe_root,
        environment=environment,
        capture=True,
    )
    defined_result = run_checked(
        [nm, "--format=posix", "--defined-only", linked],
        cwd=probe_root,
        environment=environment,
        capture=True,
    )
    undefined_output = undefined_result.stdout.decode("utf-8", errors="strict")
    defined_output = defined_result.stdout.decode("utf-8", errors="strict")
    undefined_symbols = parse_undefined_symbols(undefined_output)
    defined_symbols = _defined_symbols(defined_output)
    missing_roots = sorted({"setup", "loop"} - defined_symbols)
    if missing_roots:
        raise AdapterError(
            f"[NU54:E_CAPABILITY_PROBE_ROOT] sketch root가 정의되지 않았습니다: {missing_roots}"
        )
    detected = capabilities_for_probe_symbols(registry, undefined_symbols)
    result = {
        "schema_version": CAPABILITY_PROBE_SCHEMA_VERSION,
        "probe_mapping_version": registry["probe_mapping_version"],
        "compiler": compiler.as_posix(),
        "link_mode": "executable-section-gc",
        "roots": ["setup", "loop", "global-constructors"],
        "sources": source_manifest,
        "undefined_symbols": undefined_symbols,
        "capabilities": detected,
        "object": linked.as_posix(),
        "map": map_path.as_posix(),
    }
    atomic_write_json(probe_root / "capability-probe.json", result)
    return result
