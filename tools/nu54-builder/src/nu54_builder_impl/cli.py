"""! @brief 기존 CLI argument·diagnostic·exit dispatch을 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Sequence
import argparse
import sys
from .artifacts import verify_artifact
from .build import clean_build, link, prepare, print_size
from .cache import manage_cache
from .common import AdapterError, ChildCommandError, DEFAULT_BOARD, DEFAULT_PROFILE
from .frontend import create_archive, preprocess, record_source
from .upload import flash


## @brief 모든 subcommand에 Arduino recipe 공통 인자를 추가합니다.
def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform-root", required=True)
    parser.add_argument("--build-path", required=True)
    parser.add_argument("--sketch-root", required=True)
    parser.add_argument("--fqbn", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--board", default=DEFAULT_BOARD)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)


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

    flash_parser = subparsers.add_parser("flash")
    add_common_arguments(flash_parser)
    flash_parser.add_argument("--manifest", required=True)
    flash_parser.add_argument("--runner", choices=("pyocd", "jlink"), required=True)
    flash_parser.add_argument("--probe-id")
    flash_parser.add_argument("--verbose", action="store_true")

    clean_parser = subparsers.add_parser("clean-build")
    add_common_arguments(clean_parser)

    cache_parser = subparsers.add_parser("cache")
    cache_parser.add_argument(
        "cache_action", choices=("list", "inspect", "prune", "remove", "clear")
    )
    cache_parser.add_argument("key", nargs="?")
    cache_parser.add_argument("--cache-root")
    cache_parser.add_argument("--include-compiler", action="store_true")
    return parser


## @brief Arduino recipe가 의도적으로 전달하는 제한된 추가 인자만 허용합니다.
def validate_passthrough(command: str, values: Sequence[str]) -> None:
    if not values:
        return
    if command in {"preprocess", "record"}:
        index = 0
        while index < len(values):
            value = values[index]
            if value == "-I":
                if index + 1 >= len(values) or values[index + 1].startswith("-"):
                    raise AdapterError("-I 뒤에 include directory가 필요합니다.")
                index += 2
                continue
            if value.startswith("-I") and len(value) > 2:
                index += 1
                continue
            if command == "preprocess" and value in {"-MMD", "-MD", "-MP"}:
                index += 1
                continue
            if command == "preprocess" and value in {"-MF", "-MT", "-MQ"}:
                if index + 1 >= len(values) or values[index + 1].startswith("-"):
                    raise AdapterError(f"{value} 뒤에 dependency 값이 필요합니다.")
                index += 2
                continue
            if command == "preprocess" and value.startswith(("-D", "-U")) and len(value) > 2:
                index += 1
                continue
            raise AdapterError(f"허용되지 않은 {command} 추가 인자입니다: {value}")
        return
    if command == "link":
        for value in values:
            if value.startswith("-") or Path(value).suffix.casefold() not in {".o", ".obj"}:
                raise AdapterError(f"허용되지 않은 link object 인자입니다: {value}")
        return
    raise AdapterError(f"{command} command는 추가 인자를 허용하지 않습니다: {' '.join(values)}")


## @brief subcommand를 실행하고 안정적인 종료 code를 반환합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args, passthrough = parser.parse_known_args(arguments)
    try:
        validate_passthrough(args.command, passthrough)
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
        elif args.command == "flash":
            flash(args)
        elif args.command == "clean-build":
            clean_build(args)
        elif args.command == "cache":
            if args.cache_action in {"inspect", "remove"} and not args.key:
                parser.error(f"cache {args.cache_action}에는 key가 필요합니다")
            manage_cache(args)
        else:
            parser.error(f"알 수 없는 command입니다: {args.command}")
        return 0
    except ChildCommandError as error:
        print(f"nu54-builder: error: {error}", file=sys.stderr)
        return error.return_code
    except AdapterError as error:
        print(f"nu54-builder: error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("nu54-builder: interrupted", file=sys.stderr)
        return 130
