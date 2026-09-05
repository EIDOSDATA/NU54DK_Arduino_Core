"""! @brief Arduino preprocessing·record·archive recipe을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Sequence
import argparse
import re
import sys
import tempfile
from .build import load_context
from .common import (
    AdapterError,
    SOURCE_RECORD_SCHEMA_VERSION,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    canonical_path,
    is_within,
    path_key,
    run_checked,
)
from .environment import tool_environment
from .paths import adapter_paths, record_path


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


## @brief Arduino prototype 전처리에서 직접 Zephyr/NCS header를 보류할지 확인합니다.
def has_direct_zephyr_include(source: Path) -> bool:
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AdapterError(f"Zephyr/NCS include 탐색용 source를 읽지 못했습니다: {error}") from error
    return re.search(
        r'^\s*#\s*include\s*[<\"](?:zephyr|bluetooth)/', content, re.MULTILINE
    ) is not None


## @brief 직접 Zephyr/NCS include만 같은 줄 수의 Doxygen 주석으로 치환합니다.
def stage_prototype_source(source: Path, temporary_root: Path) -> Path:
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AdapterError(f"Zephyr/NCS include 보류용 source를 읽지 못했습니다: {error}") from error
    pattern = re.compile(
        r'^(?P<indent>\s*)#\s*include\s*[<\"](?:zephyr|bluetooth)/[^>\"]*[>\"].*$',
        re.MULTILINE,
    )
    staged_content, replacements = pattern.subn(
        r'\g<indent>/** @brief Arduino prototype 단계에서는 Zephyr/NCS header 해석을 최종 컴파일까지 보류합니다. */',
        content,
    )
    if replacements == 0:
        return source
    staged = temporary_root / source.name
    atomic_write_text(staged, staged_content)
    return staged


## @brief NCS compiler를 전처리기로 호출하여 Arduino discovery 출력을 만듭니다.
def preprocess(args: argparse.Namespace, passthrough: Sequence[str]) -> None:
    context = load_context(args)
    tools = tool_environment(canonical_path(context["platform_root"]))
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
    dependencies = dependency_arguments(passthrough)
    if args.mode == "includes":
        command.extend(("-M", "-MG", "-MP", source))
        result = run_checked(command, cwd=canonical_path(context["sketch_root"]), environment=tools["environment"], capture=True)
        sys.stdout.buffer.write(result.stdout)
        return
    if not args.output:
        raise AdapterError("macros 전처리에는 --output이 필요합니다.")
    with tempfile.TemporaryDirectory(prefix="n54-pp-") as temporary:
        prototype_source = source
        if has_direct_zephyr_include(source):
            prototype_source = stage_prototype_source(source, Path(temporary))
            command.extend(("-iquote", source.parent))
        command.extend(dependencies)
        command.extend(("-E", "-CC", prototype_source))
        result = run_checked(
            command,
            cwd=canonical_path(context["sketch_root"]),
            environment=tools["environment"],
            capture=True,
        )
    if args.output.casefold() not in {"nul", "/dev/null"}:
        atomic_write_bytes(canonical_path(args.output), result.stdout)


## @brief source graph record와 placeholder object/dependency를 원자적으로 생성합니다.
def record_source(args: argparse.Namespace, passthrough: Sequence[str]) -> None:
    paths = adapter_paths(args)
    context = load_context(args)
    source = canonical_path(args.source)
    object_path = canonical_path(args.object)
    if not source.is_file():
        raise AdapterError(f"기록할 source가 없습니다: {source}")
    if not is_within(object_path, paths["build_path"]):
        raise AdapterError(f"object가 Arduino build directory 밖에 있습니다: {object_path}")
    include_dirs = parse_include_arguments(passthrough)
    include_dirs.append(source.parent)
    unique = {path_key(path): path for path in include_dirs}
    record = {
        "schema_version": SOURCE_RECORD_SCHEMA_VERSION,
        "source": source.as_posix(),
        "object": object_path.as_posix(),
        "language": args.language,
        "include_dirs": [path.as_posix() for path in unique.values()],
        "platform_root": context["platform_root"],
        "cache_key": context["cache_key"],
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
