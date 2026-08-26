#!/usr/bin/env python3
"""! @brief Arduino build graph를 NCS/Zephyr build로 연결하는 M5 adapter입니다. """

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator, Sequence


ADAPTER_VERSION = "0.1.0-dev"
NCS_VERSION = "v3.4.0"
DEFAULT_BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
CONTEXT_DIRECTORY = "nu54-zephyr"


class AdapterError(RuntimeError):
    """! @brief 사용자가 수정할 수 있는 Build Adapter 오류입니다. """


## @brief 경로를 존재 여부와 무관하게 절대 경로로 정규화합니다.
def canonical_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


## @brief Windows에서도 결정적인 비교가 가능한 경로 key를 반환합니다.
def path_key(value: str | Path) -> str:
    normalized = canonical_path(value).as_posix()
    return normalized.casefold() if os.name == "nt" else normalized


## @brief 같은 directory 안에서 임시 파일을 교체하여 bytes를 원자적으로 기록합니다.
def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


## @brief bytes 내용이 같으면 기존 파일과 timestamp를 보존합니다.
def atomic_write_bytes_if_changed(path: Path, content: bytes) -> bool:
    if path.exists() and path.read_bytes() == content:
        return False
    atomic_write_bytes(path, content)
    return True


## @brief UTF-8 text를 원자적으로 기록하며 내용이 같으면 timestamp를 보존합니다.
def atomic_write_text(path: Path, content: str) -> bool:
    encoded = content.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return False
    atomic_write_bytes(path, encoded)
    return True


## @brief JSON을 정렬된 UTF-8 형식으로 원자적으로 기록합니다.
def atomic_write_json(path: Path, value: Any) -> bool:
    return atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


## @brief 다른 adapter process와 build directory 갱신을 직렬화합니다.
@contextlib.contextmanager
def build_lock(build_path: Path, timeout_seconds: float = 120.0) -> Iterator[None]:
    lock_path = build_path / CONTEXT_DIRECTORY / ".adapter.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise AdapterError(f"build lock 대기 시간이 초과되었습니다: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


## @brief common argument에서 adapter의 고정 directory를 계산합니다.
def adapter_paths(args: argparse.Namespace) -> dict[str, Path]:
    platform_root = canonical_path(args.platform_root)
    build_path = canonical_path(args.build_path)
    state_root = build_path / CONTEXT_DIRECTORY
    workspace_key = hashlib.sha256(path_key(build_path).encode("utf-8")).hexdigest()[:16]
    short_workspace = canonical_path(Path(tempfile.gettempdir()) / "n54" / workspace_key)
    return {
        "platform_root": platform_root,
        "build_path": build_path,
        "sketch_root": canonical_path(args.sketch_root),
        "state_root": state_root,
        "context": state_root / "context.json",
        "workspace": short_workspace,
        "app": short_workspace / "app",
        "zephyr_build": short_workspace / "build",
        "records": state_root / "records",
    }


## @brief 고정 버전의 NCS root를 환경 또는 기본 설치 위치에서 찾습니다.
def discover_ncs_root() -> Path:
    configured = os.environ.get("NUCODE_NCS_ROOT")
    candidates: list[Path] = []
    if configured:
        candidates.append(canonical_path(configured))
    candidates.extend((Path("C:/ncs/v3.4.0"), Path.home() / "ncs" / "v3.4.0"))
    for candidate in candidates:
        if (candidate / "zephyr" / "CMakeLists.txt").is_file() and (candidate / "nrf" / "west.yml").is_file():
            return candidate.resolve()
    raise AdapterError(
        "nRF Connect SDK v3.4.0을 찾을 수 없습니다. NUCODE_NCS_ROOT를 설정하십시오."
    )


## @brief NCS version과 연결된 Toolchain Manager bundle identifier를 읽습니다.
def configured_bundle_id(ncs_root: Path) -> str | None:
    registry = ncs_root.parent / "toolchains" / "toolchains.json"
    if not registry.is_file():
        return None
    try:
        documents = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for document in documents if isinstance(documents, list) else []:
        for entry in document.get("toolchains", []):
            if NCS_VERSION in entry.get("ncs_versions", []):
                identifier = entry.get("identifier", {})
                bundle = identifier.get("bundle_id")
                if isinstance(bundle, str):
                    return bundle
    return None


## @brief NCS v3.4.0에 대응하는 environment.json bundle을 찾습니다.
def discover_toolchain_root(ncs_root: Path) -> Path:
    configured = os.environ.get("NUCODE_TOOLCHAIN_ROOT")
    candidates: list[Path] = []
    if configured:
        candidates.append(canonical_path(configured))
    bundle = configured_bundle_id(ncs_root)
    if bundle:
        candidates.append(ncs_root.parent / "toolchains" / bundle)
    toolchains_root = ncs_root.parent / "toolchains"
    if toolchains_root.is_dir():
        candidates.extend(sorted(path for path in toolchains_root.iterdir() if path.is_dir()))
    visited: set[str] = set()
    for candidate in candidates:
        key = path_key(candidate)
        if key in visited:
            continue
        visited.add(key)
        if (candidate / "environment.json").is_file() and (candidate / "opt" / "bin" / "python.exe").is_file():
            return candidate.resolve()
    raise AdapterError(
        "NCS toolchain environment.json을 찾을 수 없습니다. NUCODE_TOOLCHAIN_ROOT를 설정하십시오."
    )


## @brief Toolchain Manager environment.json을 현재 child process 환경에 적용합니다.
def apply_toolchain_environment(toolchain_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    document_path = toolchain_root / "environment.json"
    try:
        document = json.loads(document_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"toolchain environment.json을 읽지 못했습니다: {error}") from error

    for entry in document.get("env_vars", []):
        key = entry.get("key")
        if not isinstance(key, str):
            continue
        entry_type = entry.get("type")
        if entry_type == "relative_paths":
            values = [str((toolchain_root / value).resolve()) for value in entry.get("values", [])]
            treatment = entry.get("existing_value_treatment", "overwrite")
            if treatment == "prepend_to" and environment.get(key):
                values.append(environment[key])
            environment[key] = os.pathsep.join(values)
        elif entry_type == "string":
            environment[key] = str(entry.get("value", ""))
    return environment


## @brief west와 compiler에 필요한 실행 환경 및 절대 경로를 구성합니다.
def tool_environment() -> dict[str, Any]:
    ncs_root = discover_ncs_root()
    toolchain_root = discover_toolchain_root(ncs_root)
    environment = apply_toolchain_environment(toolchain_root)
    zephyr_base = ncs_root / "zephyr"
    environment["ZEPHYR_BASE"] = str(zephyr_base)
    west = toolchain_root / "opt" / "bin" / "Scripts" / "west.exe"
    compiler = (
        toolchain_root
        / "opt"
        / "zephyr-sdk"
        / "gnu"
        / "arm-zephyr-eabi"
        / "bin"
        / "arm-zephyr-eabi-g++.exe"
    )
    size_tool = compiler.with_name("arm-zephyr-eabi-size.exe")
    for executable in (west, compiler, size_tool):
        if not executable.is_file():
            raise AdapterError(f"NCS toolchain 실행 파일이 없습니다: {executable}")
    return {
        "ncs_root": ncs_root,
        "toolchain_root": toolchain_root,
        "zephyr_base": zephyr_base,
        "environment": environment,
        "west": west,
        "compiler": compiler,
        "size": size_tool,
    }


## @brief command를 shell 없이 실행하고 실패 code를 그대로 오류로 변환합니다.
def run_checked(command: Sequence[str | Path], *, cwd: Path, environment: dict[str, str], capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    normalized = [str(item) for item in command]
    result = subprocess.run(
        normalized,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode != 0:
        if capture:
            if result.stdout:
                sys.stdout.buffer.write(result.stdout)
            if result.stderr:
                sys.stderr.buffer.write(result.stderr)
        raise AdapterError(f"명령이 종료 코드 {result.returncode}로 실패했습니다: {shlex.join(normalized)}")
    return result


## @brief 파일의 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief 설정 입력을 hashing하여 configure context 변경을 추적합니다.
def configuration_fingerprint(platform_root: Path, sketch_root: Path, board: str) -> str:
    digest = hashlib.sha256()
    digest.update(ADAPTER_VERSION.encode("utf-8"))
    digest.update(board.encode("utf-8"))
    inputs = [
        platform_root / "platform.txt",
        platform_root / "tools" / "nu54-builder" / "src" / "nu54_builder.py",
        platform_root / "tools" / "nu54-builder" / "templates" / "zephyr-app" / "CMakeLists.txt",
        platform_root / "tools" / "nu54-builder" / "templates" / "zephyr-app" / "prj.conf",
        platform_root / "tools" / "nu54-builder" / "templates" / "zephyr-app" / "src" / "bootstrap.cpp",
        sketch_root / "prj.conf",
        sketch_root / "app.overlay",
    ]
    for source in inputs:
        digest.update(path_key(source).encode("utf-8"))
        if source.is_file():
            digest.update(source.read_bytes())
    return f"sha256:{digest.hexdigest()}"


## @brief Zephyr application template과 사용자 config/overlay를 materialize합니다.
def materialize_application(paths: dict[str, Path]) -> None:
    platform_root = paths["platform_root"]
    sketch_root = paths["sketch_root"]
    app_root = paths["app"]
    template = platform_root / "tools" / "nu54-builder" / "templates" / "zephyr-app"
    for required in ("CMakeLists.txt", "prj.conf", "sources.cmake", "src/bootstrap.cpp"):
        if not (template / required).is_file():
            raise AdapterError(f"Zephyr application template이 불완전합니다: {template / required}")
    app_root.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes_if_changed(app_root / "CMakeLists.txt", (template / "CMakeLists.txt").read_bytes())
    atomic_write_bytes_if_changed(app_root / "src" / "bootstrap.cpp", (template / "src" / "bootstrap.cpp").read_bytes())
    sources = app_root / "sources.cmake"
    if not sources.exists():
        atomic_write_bytes(sources, (template / "sources.cmake").read_bytes())

    base_config = (template / "prj.conf").read_text(encoding="utf-8").rstrip() + "\n"
    sketch_config = sketch_root / "prj.conf"
    if sketch_config.is_file():
        base_config += "\n# Sketch prj.conf\n" + sketch_config.read_text(encoding="utf-8").rstrip() + "\n"
    atomic_write_text(app_root / "prj.conf", base_config)

    generated_overlay = app_root / "app.overlay"
    sketch_overlay = sketch_root / "app.overlay"
    if sketch_overlay.is_file():
        atomic_write_bytes_if_changed(generated_overlay, sketch_overlay.read_bytes())
    elif generated_overlay.exists():
        generated_overlay.unlink()


## @brief 현재 고정 입력으로 Zephyr configure-only를 수행하고 context를 기록합니다.
def prepare(args: argparse.Namespace) -> dict[str, Any]:
    paths = adapter_paths(args)
    platform_root = paths["platform_root"]
    board_root = platform_root / "board_package" / "NU54DK_Zephyr_DTS"
    if not (board_root / "boards" / "nucode" / "nu54dk" / "board.yml").is_file():
        raise AdapterError(f"NU54DK board package를 찾을 수 없습니다: {board_root}")
    tools = tool_environment()
    paths["build_path"].mkdir(parents=True, exist_ok=True)

    with build_lock(paths["build_path"]):
        materialize_application(paths)
        previous: dict[str, Any] = {}
        if paths["context"].is_file():
            try:
                previous = json.loads(paths["context"].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                previous = {}
        cache_exists = (paths["zephyr_build"] / "CMakeCache.txt").is_file()
        build_graph_exists = (paths["zephyr_build"] / "build.ninja").is_file()
        first_configure = not cache_exists or not build_graph_exists
        fingerprint = configuration_fingerprint(platform_root, paths["sketch_root"], args.board)
        configuration_changed = (
            previous.get("configuration_fingerprint") != fingerprint
            or previous.get("board") != args.board
            or previous.get("fqbn") != args.fqbn
            or previous.get("platform_root") != platform_root.as_posix()
        )
        command: list[str | Path] = [
            tools["west"],
            "-z",
            tools["zephyr_base"],
            "build",
            "--cmake-only",
            "--no-sysbuild",
            "-b",
            args.board,
            "-d",
            paths["zephyr_build"],
            paths["app"],
            "--",
            "-UCONFIG_*",
            f"-DBOARD_ROOT={board_root.as_posix()}",
            f"-DEXTRA_ZEPHYR_MODULES={platform_root.as_posix()}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ]
        if cache_exists and not build_graph_exists:
            command.insert(command.index("-b"), "--pristine=always")
        overlay = paths["app"] / "app.overlay"
        if overlay.is_file():
            command.append(f"-DDTC_OVERLAY_FILE={overlay.as_posix()}")
        if first_configure or configuration_changed:
            run_checked(command, cwd=tools["ncs_root"], environment=tools["environment"])
        context = {
            "schema_version": 1,
            "adapter_version": ADAPTER_VERSION,
            "state": "configured",
            "fqbn": args.fqbn,
            "board": args.board,
            "sysbuild": False,
            "ncs_version": NCS_VERSION,
            "zephyr_version": "4.4.0",
            "platform_root": platform_root.as_posix(),
            "board_root": board_root.resolve().as_posix(),
            "sketch_root": paths["sketch_root"].as_posix(),
            "build_path": paths["build_path"].as_posix(),
            "app_dir": paths["app"].as_posix(),
            "zephyr_build_dir": paths["zephyr_build"].as_posix(),
            "ncs_root": tools["ncs_root"].as_posix(),
            "toolchain_root": tools["toolchain_root"].as_posix(),
            "cxx_compiler": tools["compiler"].as_posix(),
            "size_tool": tools["size"].as_posix(),
            "configuration_fingerprint": fingerprint,
            "configure_mode": "cmake-only",
            "configure_skipped": not (first_configure or configuration_changed),
            "pristine_configure_count": int(previous.get("pristine_configure_count", 0)) + (1 if first_configure else 0),
            "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        atomic_write_json(paths["context"], context)
        return context


## @brief context가 없으면 preprocessor 단계에서도 안전하게 최초 configure를 수행합니다.
def load_context(args: argparse.Namespace, create: bool = True) -> dict[str, Any]:
    path = adapter_paths(args)["context"]
    if not path.is_file():
        if not create:
            raise AdapterError(f"configure context가 없습니다: {path}")
        return prepare(args)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"configure context를 읽지 못했습니다: {error}") from error


## @brief Arduino recipe가 전달한 -I include argument를 directory 목록으로 바꿉니다.
def parse_include_arguments(arguments: Sequence[str]) -> list[Path]:
    includes: list[Path] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        value: str | None = None
        if argument == "-I" and index + 1 < len(arguments):
            index += 1
            value = arguments[index]
        elif argument.startswith("-I") and len(argument) > 2:
            value = argument[2:]
        if value:
            includes.append(canonical_path(value.strip('"')))
        index += 1
    unique: dict[str, Path] = {}
    for include in includes:
        unique[path_key(include)] = include
    return list(unique.values())


## @brief Arduino CLI가 뒤에 붙인 dependency 생성 option만 안전하게 전달합니다.
def dependency_arguments(arguments: Sequence[str]) -> list[str]:
    forwarded: list[str] = []
    index = 0
    flags_with_value = {"-MF", "-MT", "-MQ"}
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"-MMD", "-MD", "-MP"}:
            forwarded.append(argument)
        elif argument in flags_with_value and index + 1 < len(arguments):
            forwarded.extend((argument, arguments[index + 1]))
            index += 1
        elif argument.startswith(("-D", "-U")):
            forwarded.append(argument)
        index += 1
    return forwarded


## @brief NCS compiler를 전처리기로 호출하여 Arduino discovery 출력을 만듭니다.
def preprocess(args: argparse.Namespace, passthrough: Sequence[str]) -> None:
    context = load_context(args)
    tools = tool_environment()
    source = canonical_path(args.source)
    if not source.is_file():
        raise AdapterError(f"전처리할 source가 없습니다: {source}")
    platform_root = canonical_path(context["platform_root"])
    include_dirs = [
        platform_root / "cores" / "arduino",
        platform_root / "variants" / "nu54dk",
        platform_root / "third_party" / "ArduinoCore-API",
    ]
    include_dirs.extend(parse_include_arguments(passthrough))
    command: list[str | Path] = [
        context["cxx_compiler"],
        "-w",
        "-x",
        "c++",
        "-std=gnu++17",
        f"-DARDUINO={args.arduino_version}",
        "-DARDUINO_ARCH_ZEPHYR",
        "-DARDUINO_NUCODE_NU54DK",
        f"-DARDUINO_LIBRARY_DISCOVERY_PHASE={args.discovery_phase}",
    ]
    for include in include_dirs:
        command.extend(("-I", include))
    command.extend(dependency_arguments(passthrough))
    if args.mode == "includes":
        command.extend(("-M", "-MG", "-MP", source))
        result = run_checked(command, cwd=canonical_path(context["sketch_root"]), environment=tools["environment"], capture=True)
        sys.stdout.buffer.write(result.stdout)
        return
    if not args.output:
        raise AdapterError("macros 전처리에는 --output이 필요합니다.")
    command.extend(("-E", "-CC", source))
    result = run_checked(command, cwd=canonical_path(context["sketch_root"]), environment=tools["environment"], capture=True)
    if args.output.casefold() not in {"nul", "/dev/null"}:
        atomic_write_bytes(canonical_path(args.output), result.stdout)


## @brief object path와 일대일로 대응하는 record file 경로를 계산합니다.
def record_path(records_root: Path, object_path: Path) -> Path:
    digest = hashlib.sha256(path_key(object_path).encode("utf-8")).hexdigest()
    return records_root / f"{digest}.json"


## @brief source graph record와 placeholder object/dependency를 원자적으로 생성합니다.
def record_source(args: argparse.Namespace, passthrough: Sequence[str]) -> None:
    paths = adapter_paths(args)
    context = load_context(args)
    source = canonical_path(args.source)
    object_path = canonical_path(args.object)
    if not source.is_file():
        raise AdapterError(f"기록할 source가 없습니다: {source}")
    include_dirs = parse_include_arguments(passthrough)
    include_dirs.append(source.parent)
    unique = {path_key(path): path for path in include_dirs}
    record = {
        "schema_version": 1,
        "source": source.as_posix(),
        "object": object_path.as_posix(),
        "language": args.language,
        "include_dirs": [path.as_posix() for path in unique.values()],
        "platform_root": context["platform_root"],
    }
    atomic_write_json(record_path(paths["records"], object_path), record)
    atomic_write_bytes(object_path, b"")
    dependency = object_path.with_suffix(".d")
    escaped_object = object_path.as_posix().replace(" ", "\\ ")
    escaped_source = source.as_posix().replace(" ", "\\ ")
    atomic_write_text(dependency, f"{escaped_object}: {escaped_source}\n")


## @brief Arduino core archive lifecycle을 만족하는 placeholder archive를 생성합니다.
def create_archive(args: argparse.Namespace) -> None:
    load_context(args)
    archive = canonical_path(args.archive)
    if not archive.exists():
        atomic_write_bytes(archive, b"")


## @brief path가 지정 directory 내부인지 판정합니다.
def is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


## @brief link recipe object 목록에 대응하는 sketch/library record를 읽습니다.
def records_for_objects(paths: dict[str, Path], objects: Sequence[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for object_name in objects:
        if not object_name:
            continue
        object_path = canonical_path(object_name)
        record_file = record_path(paths["records"], object_path)
        if not record_file.is_file():
            if object_path.suffix.lower() in {".a", ".ar"}:
                raise AdapterError(f"M5는 precompiled Arduino library를 지원하지 않습니다: {object_path}")
            missing.append(object_path.as_posix())
            continue
        try:
            records.append(json.loads(record_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise AdapterError(f"source record가 손상되었습니다: {record_file}: {error}") from error
    if missing:
        raise AdapterError("object에 대응하는 source record가 없습니다: " + ", ".join(missing))
    return records


## @brief CMake string literal에 사용할 path를 escape합니다.
def cmake_quote(path: Path) -> str:
    return path.as_posix().replace("\\", "/").replace("\"", "\\\"").replace(";", "\\;")


## @brief source record를 결정적인 sources.cmake manifest로 변환합니다.
def write_source_manifest(paths: dict[str, Path], records: Sequence[dict[str, Any]]) -> tuple[list[Path], bool]:
    core_root = paths["platform_root"] / "cores"
    variant_root = paths["platform_root"] / "variants"
    sources: dict[str, Path] = {}
    includes: dict[str, Path] = {}
    for record in records:
        source = canonical_path(record["source"])
        if is_within(source, core_root) or is_within(source, variant_root):
            continue
        if not source.is_file():
            raise AdapterError(f"Arduino source가 사라졌습니다: {source}")
        sources[path_key(source)] = source
        if not is_within(source.parent, paths["build_path"]):
            includes[path_key(source.parent)] = source.parent
        for value in record.get("include_dirs", []):
            include = canonical_path(value)
            if include.is_dir() and not is_within(include, paths["build_path"]):
                includes[path_key(include)] = include
    ordered_sources = [sources[key] for key in sorted(sources)]
    mirrored_sources: list[Path] = []
    mirror_root = paths["app"] / "generated-sources"
    for source in ordered_sources:
        digest = hashlib.sha256(path_key(source).encode("utf-8")).hexdigest()[:12]
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", source.name)
        mirror = mirror_root / f"{digest}_{safe_name}"
        atomic_write_bytes_if_changed(mirror, source.read_bytes())
        mirrored_sources.append(mirror)
        includes[path_key(mirror.parent)] = mirror.parent
    ordered_includes = [includes[key] for key in sorted(includes)]
    lines = ["# nu54-builder가 원자적으로 생성한 source manifest입니다.", "set(NUCODE_ARDUINO_SKETCH_SOURCES"]
    lines.extend(f'  "{cmake_quote(path)}"' for path in mirrored_sources)
    lines.append(")")
    lines.append("set(NUCODE_ARDUINO_INCLUDE_DIRS")
    lines.extend(f'  "{cmake_quote(path)}"' for path in ordered_includes)
    lines.extend((")", ""))
    changed = atomic_write_text(paths["app"] / "sources.cmake", "\n".join(lines))
    return ordered_sources, changed


## @brief Zephyr artifact를 Arduino build path로 원자적으로 복사합니다.
def copy_artifact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise AdapterError(f"Zephyr artifact가 없습니다: {source}")
    atomic_write_bytes(destination, source.read_bytes())


## @brief source manifest를 갱신하고 Full Zephyr image를 build/export합니다.
def link(args: argparse.Namespace) -> None:
    paths = adapter_paths(args)
    context = load_context(args, create=False)
    tools = tool_environment()
    with build_lock(paths["build_path"]):
        records = records_for_objects(paths, args.objects)
        sources, manifest_changed = write_source_manifest(paths, records)
        if not sources:
            raise AdapterError("최종 Zephyr build에 전달할 sketch/library source가 없습니다.")
        configure_command: list[str | Path] = [
            tools["west"],
            "-z",
            tools["zephyr_base"],
            "build",
            "--cmake-only",
            "--no-sysbuild",
            "-b",
            args.board,
            "-d",
            paths["zephyr_build"],
            paths["app"],
            "--",
            "-UCONFIG_*",
            f"-DBOARD_ROOT={context['board_root']}",
            f"-DEXTRA_ZEPHYR_MODULES={context['platform_root']}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ]
        overlay = paths["app"] / "app.overlay"
        if overlay.is_file():
            configure_command.append(f"-DDTC_OVERLAY_FILE={overlay.as_posix()}")
        if manifest_changed:
            run_checked(configure_command, cwd=tools["ncs_root"], environment=tools["environment"])
        run_checked(
            [tools["west"], "-z", tools["zephyr_base"], "build", "-d", paths["zephyr_build"]],
            cwd=tools["ncs_root"],
            environment=tools["environment"],
        )
        zephyr_output = paths["zephyr_build"] / "zephyr"
        artifacts = {
            "elf": zephyr_output / "zephyr.elf",
            "hex": zephyr_output / "zephyr.hex",
            "bin": zephyr_output / "zephyr.bin",
            "map": zephyr_output / "zephyr.map",
        }
        exported: dict[str, Any] = {}
        for extension, source in artifacts.items():
            destination = paths["build_path"] / f"{args.project_name}.{extension}"
            copy_artifact(source, destination)
            exported[extension] = {
                "path": destination.as_posix(),
                "sha256": file_sha256(destination),
                "size": destination.stat().st_size,
            }
        manifest = {
            "schema_version": 1,
            "adapter_version": ADAPTER_VERSION,
            "fqbn": args.fqbn,
            "board": args.board,
            "sysbuild": False,
            "context": context,
            "sources": [path.as_posix() for path in sources],
            "artifacts": exported,
            "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        atomic_write_json(paths["build_path"] / f"{args.project_name}.nu54-build.json", manifest)


## @brief 이미 export된 artifact가 존재하는지 검증합니다.
def verify_artifact(args: argparse.Namespace) -> None:
    artifact = canonical_path(args.artifact)
    if not artifact.is_file() or artifact.stat().st_size == 0:
        raise AdapterError(f"export artifact가 없거나 비어 있습니다: {artifact}")


## @brief Arduino IDE가 parsing할 수 있는 FLASH/RAM 사용량을 출력합니다.
def print_size(args: argparse.Namespace) -> None:
    context = load_context(args, create=False)
    tools = tool_environment()
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


## @brief 모든 subcommand에 Arduino recipe 공통 인자를 추가합니다.
def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform-root", required=True)
    parser.add_argument("--build-path", required=True)
    parser.add_argument("--sketch-root", required=True)
    parser.add_argument("--fqbn", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--board", default=DEFAULT_BOARD)


## @brief Build Adapter command line parser를 구성합니다.
def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nu54-builder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    add_common_arguments(prepare_parser)

    preprocess_parser = subparsers.add_parser("preprocess")
    add_common_arguments(preprocess_parser)
    preprocess_parser.add_argument("--mode", choices=("includes", "macros"), required=True)
    preprocess_parser.add_argument("--arduino-version", default="10607")
    preprocess_parser.add_argument("--discovery-phase", default="1")
    preprocess_parser.add_argument("--source", required=True)
    preprocess_parser.add_argument("--output")

    record_parser = subparsers.add_parser("record")
    add_common_arguments(record_parser)
    record_parser.add_argument("--language", choices=("c", "cxx", "asm"), required=True)
    record_parser.add_argument("--source", required=True)
    record_parser.add_argument("--object", required=True)

    archive_parser = subparsers.add_parser("archive")
    add_common_arguments(archive_parser)
    archive_parser.add_argument("--archive", required=True)
    archive_parser.add_argument("--object", required=True)

    link_parser = subparsers.add_parser("link")
    add_common_arguments(link_parser)
    link_parser.add_argument("--archive", required=True)
    link_parser.add_argument("--objects", nargs="*", default=[])

    verify_parser = subparsers.add_parser("verify-artifact")
    add_common_arguments(verify_parser)
    verify_parser.add_argument("--artifact", required=True)

    size_parser = subparsers.add_parser("size")
    add_common_arguments(size_parser)
    return parser


## @brief subcommand를 실행하고 안정적인 종료 code를 반환합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args, passthrough = parser.parse_known_args(arguments)
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "preprocess":
            preprocess(args, passthrough)
        elif args.command == "record":
            record_source(args, passthrough)
        elif args.command == "archive":
            create_archive(args)
        elif args.command == "link":
            if passthrough:
                args.objects.extend(passthrough)
            link(args)
        elif args.command == "verify-artifact":
            verify_artifact(args)
        elif args.command == "size":
            print_size(args)
        else:
            parser.error(f"알 수 없는 command입니다: {args.command}")
        return 0
    except AdapterError as error:
        print(f"nu54-builder: error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("nu54-builder: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
