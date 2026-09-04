#!/usr/bin/env python3
"""Stage a private M27 package and compile every packaged Arduino example."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
from typing import Any, Sequence
import zipfile


REPOSITORY = Path(__file__).resolve().parents[2]
VERSION = "0.4.0-rc.1"
ARCHIVE_ROOT = f"nucode-nu54dk-zephyr-{VERSION}"
EXAMPLE_RUNNER = Path(__file__).with_name("run_m27_package_examples.py")
M27_RELEASE = Path(__file__).with_name("m27_release.py")
MAX_ARCHIVE_FILES = 4096
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


class StagedCandidateFailure(RuntimeError):
    """The private staged-candidate gate could not prove its contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def load_module(name: str, path: Path) -> Any:
    import importlib.util

    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise StagedCandidateFailure(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def validate_zip_members(archive: Path) -> list[zipfile.ZipInfo]:
    try:
        with zipfile.ZipFile(archive) as package:
            members = package.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        raise StagedCandidateFailure(f"invalid package archive: {archive}") from error
    if not members or len(members) > MAX_ARCHIVE_FILES:
        raise StagedCandidateFailure("package archive file count is outside the safe range")
    total = 0
    for member in members:
        path = PurePosixPath(member.filename)
        if (
            not member.filename
            or "\\" in member.filename
            or path.is_absolute()
            or not path.parts
            or path.parts[0] != ARCHIVE_ROOT
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise StagedCandidateFailure(f"unsafe archive member: {member.filename!r}")
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise StagedCandidateFailure(f"archive symlink is forbidden: {member.filename}")
        total += member.file_size
        if total > MAX_ARCHIVE_BYTES:
            raise StagedCandidateFailure("package archive expands beyond the safe size")
    return members


def write_cli_config(path: Path, *, data: Path, downloads: Path, user: Path) -> None:
    path.write_text(
        "directories:\n"
        f"  data: {data.as_posix()}\n"
        f"  downloads: {downloads.as_posix()}\n"
        f"  user: {user.as_posix()}\n"
        "logging:\n"
        "  level: info\n",
        encoding="utf-8",
        newline="\n",
    )


def stage_archive(archive: Path, workspace: Path) -> Path:
    if workspace.exists() and any(workspace.iterdir()):
        raise StagedCandidateFailure(f"workspace must be empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    members = validate_zip_members(archive)
    extraction = workspace / "extract"
    extraction.mkdir()
    with zipfile.ZipFile(archive) as package:
        package.extractall(extraction, members=members)
    extracted_root = extraction / ARCHIVE_ROOT
    if not extracted_root.is_dir() or extracted_root.is_symlink():
        raise StagedCandidateFailure("archive root was not extracted as a regular directory")
    platform = (
        workspace
        / "data"
        / "packages"
        / "nucode"
        / "hardware"
        / "zephyr"
        / VERSION
    )
    platform.parent.mkdir(parents=True, exist_ok=True)
    extracted_root.rename(platform)
    extraction.rmdir()
    return platform


def run_gate(args: argparse.Namespace) -> Path:
    archive = args.archive.resolve()
    workspace = args.workspace.resolve()
    cli = args.arduino_cli.resolve()
    ncs = args.ncs_root.resolve()
    toolchain = args.toolchain_root.resolve()
    prerequisite_state = args.prerequisite_state_root.resolve()
    if not archive.is_file() or archive.is_symlink():
        raise StagedCandidateFailure(f"package archive is missing: {archive}")
    if not cli.is_file() or cli.is_symlink():
        raise StagedCandidateFailure(f"Arduino CLI is missing: {cli}")
    if not (ncs / "zephyr" / "CMakeLists.txt").is_file():
        raise StagedCandidateFailure(f"NCS root is invalid: {ncs}")
    if not (toolchain / "environment.json").is_file():
        raise StagedCandidateFailure(f"toolchain root is invalid: {toolchain}")
    if not (prerequisite_state / "ready.json").is_file():
        raise StagedCandidateFailure("prerequisite ready marker is missing")

    release = load_module("nu54_m27_staged_release", M27_RELEASE)
    package = release.load_package_module()
    release.configure_v04_candidate(package)
    try:
        manifest = package.validate_archive(archive, expected_version=VERSION)
    except package.PackageError as error:
        raise StagedCandidateFailure(str(error)) from error

    platform = stage_archive(archive, workspace)
    data = workspace / "data"
    downloads = workspace / "downloads"
    user = workspace / "sketchbook"
    build = workspace / "build"
    cache = workspace / "cache"
    for directory in (downloads, user, cache):
        directory.mkdir(parents=True, exist_ok=True)
    config = workspace / "arduino-cli.yaml"
    write_cli_config(config, data=data, downloads=downloads, user=user)
    examples_evidence = workspace / "m27-package-examples.json"
    command: list[str] = [
        str(sys.executable),
        str(EXAMPLE_RUNNER),
        "--arduino-cli",
        str(cli),
        "--config",
        str(config),
        "--platform-root",
        str(platform),
        "--build-root",
        str(build),
        "--ncs-root",
        str(ncs),
        "--toolchain-root",
        str(toolchain),
        "--cache-root",
        str(cache),
        "--forbid-root",
        str(REPOSITORY.resolve()),
        "--evidence",
        str(examples_evidence),
        "--compile-timeout",
        str(args.compile_timeout),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "NUCODE_NCS_ROOT": str(ncs),
            "NUCODE_TOOLCHAIN_ROOT": str(toolchain),
            "NUCODE_PREREQUISITE_STATE_ROOT": str(prerequisite_state),
            "NUCODE_BUILD_CACHE_ROOT": str(cache),
            "PYTHONUTF8": "1",
        }
    )
    result = subprocess.run(command, env=environment, check=False)
    if result.returncode != 0:
        raise StagedCandidateFailure("staged package example gate failed")
    try:
        example_result = json.loads(examples_evidence.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StagedCandidateFailure("staged example evidence is invalid") from error
    if example_result.get("status") != "passed" or example_result.get(
        "compiled_count"
    ) != 29:
        raise StagedCandidateFailure("staged example evidence did not pass 29 examples")
    evidence = {
        "schema_version": 1,
        "milestone": "M27",
        "evidence_type": "private-staged-candidate",
        "status": "passed",
        "release_version": VERSION,
        "archive": {
            "path": str(archive),
            "size": archive.stat().st_size,
            "sha256": sha256_file(archive),
        },
        "source_revision": manifest["core_revision"],
        "runtime_payload_sha256": manifest["runtime_payload_sha256"],
        "platform_root": str(platform),
        "arduino_data_isolated": True,
        "public_installation_modified": False,
        "compiled_examples": 29,
        "example_evidence_sha256": sha256_file(examples_evidence),
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    evidence_path = workspace / "m27-staged-candidate.json"
    write_json(evidence_path, evidence)
    return evidence_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage private v0.4.0-rc.1 and compile all packaged examples"
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--ncs-root", type=Path, required=True)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--prerequisite-state-root", type=Path, required=True)
    parser.add_argument("--compile-timeout", type=int, default=3600)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(arguments)
        if not 1 <= args.compile_timeout <= 86400:
            raise StagedCandidateFailure("compile timeout is outside 1..86400 seconds")
        evidence = run_gate(args)
        print(f"M27_STAGED_CANDIDATE_PASS=29;EVIDENCE={evidence}")
        return 0
    except StagedCandidateFailure as error:
        print(f"M27_STAGED_CANDIDATE_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
