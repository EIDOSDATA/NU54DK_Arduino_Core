"""! @brief 패키저의 기존 인자·진단·종료 코드 책임입니다. """
from __future__ import annotations
from . import model
from pathlib import Path, PurePosixPath
import argparse
import sys
from .build import (
    build_package,
)
from .channels import (
    archive_filename,
    release_channel,
)
from .index import (
    generate_index,
    validate_index,
)
from .model import (
    PackageError,
)
from .validation import (
    validate_archive,
)


## @brief CLI 인자를 정의합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NU54DK Boards Manager package builder/validator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="exact Git commit에서 재현 가능한 package를 생성합니다.")
    build.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--version", choices=model.PACKAGE_VERSIONS, required=True)
    build.add_argument("--commit", default="HEAD")
    build.add_argument("--update-index", action="store_true")

    validate = subparsers.add_parser("validate", help="package archive를 엄격하게 검증합니다.")
    validate.add_argument("--archive", type=Path, required=True)
    validate.add_argument("--expected-version", choices=model.PACKAGE_VERSIONS)
    validate.add_argument("--expected-commit")

    index = subparsers.add_parser("index", help="로컬 archive로 package index를 생성합니다.")
    index.add_argument("--output-dir", type=Path, required=True)
    index.add_argument("--versions", nargs="+", choices=model.PACKAGE_VERSIONS, required=True)
    index.add_argument("--output", type=Path)

    validate_index_parser = subparsers.add_parser("validate-index", help="package index를 검증합니다.")
    validate_index_parser.add_argument("--index", type=Path, required=True)
    validate_index_parser.add_argument("--artifact-dir", type=Path)
    return parser


## @brief CLI 진입점입니다.
def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "build":
            paths = build_package(
                arguments.repo_root, arguments.output_dir, arguments.version, arguments.commit
            )
            if arguments.update_index:
                requested_channel = release_channel(arguments.version)
                available = [
                    version
                    for version in model.PACKAGE_VERSIONS
                    if release_channel(version) == requested_channel
                    and (arguments.output_dir / archive_filename(version)).is_file()
                ]
                paths["index"] = generate_index(arguments.output_dir, available)
            for name, path in paths.items():
                print(f"NU54_PACKAGE_{name.upper()}={path}")
        elif arguments.command == "validate":
            manifest = validate_archive(
                arguments.archive,
                expected_version=arguments.expected_version,
                expected_commit=arguments.expected_commit,
            )
            print(f"NU54_PACKAGE_VALID={manifest['version']}:{manifest['core_revision']}")
        elif arguments.command == "index":
            path = generate_index(arguments.output_dir, arguments.versions, arguments.output)
            print(f"NU54_PACKAGE_INDEX={path}")
        elif arguments.command == "validate-index":
            document = validate_index(arguments.index, artifact_dir=arguments.artifact_dir)
            print(f"NU54_PACKAGE_INDEX_VALID={len(document['packages'][0]['platforms'])}")
        return 0
    except PackageError as error:
        print(f"NU54_PACKAGE_ERROR={error}", file=sys.stderr)
        return 2
