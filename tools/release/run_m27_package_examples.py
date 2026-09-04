#!/usr/bin/env python3
"""Compile every Arduino example from a staged v0.4.0-rc.1 package."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
BASE_RUNNER_PATH = Path(__file__).with_name("run_m22_package_examples.py")
LOCK_PATH = Path(__file__).with_name("m27-package-examples.lock.json")
VERSION = "0.4.0-rc.1"
FQBN = "nucode:zephyr:nu54dk"
EXPECTED_EXAMPLE_COUNT = 29


def load_base_runner() -> Any:
    specification = importlib.util.spec_from_file_location(
        "nu54_m27_package_examples_base", BASE_RUNNER_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load package example runner: {BASE_RUNNER_PATH}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


BASE = load_base_runner()
PackageExamplesFailure = BASE.PackageExamplesFailure


def load_example_lock(path: Path = LOCK_PATH) -> list[dict[str, str]]:
    document = BASE.strict_json(path)
    if (
        document.get("schema_version") != 1
        or document.get("release_version") != VERSION
        or document.get("fqbn") != FQBN
    ):
        raise PackageExamplesFailure("M27 example lock identity is invalid")
    records = document.get("examples")
    if not isinstance(records, list) or len(records) != EXPECTED_EXAMPLE_COUNT:
        raise PackageExamplesFailure(
            f"M27 example lock must contain exactly {EXPECTED_EXAMPLE_COUNT} records"
        )
    normalized: list[dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "example",
            "library",
            "library_directory",
            "profile",
        }:
            raise PackageExamplesFailure("M27 example lock record schema is invalid")
        if not all(isinstance(value, str) and value for value in record.values()):
            raise PackageExamplesFailure("M27 example lock contains an empty value")
        if record["profile"] not in {"standard", "ble"}:
            raise PackageExamplesFailure("M27 example profile is invalid")
        identity = (record["library"], record["example"])
        if identity in identities:
            raise PackageExamplesFailure(f"duplicate M27 example: {identity}")
        identities.add(identity)
        normalized.append({key: str(value) for key, value in record.items()})
    return normalized


def run_gate(args: argparse.Namespace) -> dict[str, Any]:
    cli = args.arduino_cli.resolve()
    config = args.config.resolve()
    platform_root = args.platform_root.resolve()
    build_root = args.build_root.resolve()
    evidence_path = args.evidence.resolve()
    if not cli.is_file() or not config.is_file() or not platform_root.is_dir():
        raise PackageExamplesFailure("Arduino CLI, config or staged platform is missing")
    if build_root.exists() and any(build_root.iterdir()):
        raise PackageExamplesFailure("M27 example build root must be empty")
    build_root.mkdir(parents=True, exist_ok=True)
    lock = load_example_lock(args.lock.resolve())
    code, output, _ = BASE.run_command(
        (
            cli,
            "--config-file",
            config,
            "lib",
            "examples",
            "--fqbn",
            FQBN,
            "--json",
        ),
        timeout_seconds=120,
    )
    if code != 0:
        raise PackageExamplesFailure("Arduino CLI example discovery failed")
    try:
        listing = json.loads(output, object_pairs_hook=BASE._unique_object)
    except (json.JSONDecodeError, PackageExamplesFailure) as error:
        raise PackageExamplesFailure("Arduino CLI example listing is invalid JSON") from error
    if not isinstance(listing, dict):
        raise PackageExamplesFailure("Arduino CLI example listing root is not an object")
    discovered = BASE.parse_installed_examples(
        listing, lock, platform_root, version=VERSION
    )
    forbidden_roots = tuple(path.resolve() for path in args.forbid_root)
    def compile_one(sequence: int, example: dict[str, str]) -> dict[str, Any]:
        identity = (example["library"], example["example"])
        sketch = discovered[identity]
        safe_name = re.sub(
            r"[^a-z0-9]+",
            "-",
            f"{example['library']}-{example['example']}".casefold(),
        ).strip("-")
        build = build_root / f"{sequence:02d}-{safe_name}"
        log_path = build_root / "logs" / f"{sequence:02d}-{safe_name}.log"
        command = (
            cli,
            "--config-file",
            config,
            "compile",
            "--clean",
            "--fqbn",
            FQBN,
            "--board-options",
            f"feature_set={example['profile']}",
            "--build-path",
            build,
            sketch,
        )
        code, compile_output, seconds = BASE.run_command(
            command, timeout_seconds=args.compile_timeout
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(compile_output, encoding="utf-8", errors="replace")
        if code != 0:
            raise PackageExamplesFailure(f"M27 package example failed: {identity}")
        manifest_path = build / f"{example['example']}.ino.nu54-build.json"
        identity_record = BASE.validate_build_manifest(
            manifest_path,
            example=example,
            sketch=sketch,
            build_root=build,
            platform_root=platform_root,
            ncs_root=args.ncs_root,
            toolchain_root=args.toolchain_root,
            cache_root=args.cache_root,
            forbidden_roots=forbidden_roots,
        )
        record = {
            "sequence": sequence,
            "library": example["library"],
            "example": example["example"],
            "installed_relative_path": sketch.relative_to(platform_root).as_posix(),
            "compile_seconds": round(seconds, 3),
            "compile_log_sha256": BASE.file_sha256(log_path),
            **identity_record,
        }
        print(
            f"M27_PACKAGE_EXAMPLE_PASS {sequence}/{EXPECTED_EXAMPLE_COUNT} "
            f"{example['library']}::{example['example']}",
            flush=True,
        )
        return record

    results: list[dict[str, Any]] = []
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(compile_one, sequence, example): (
                example["library"],
                example["example"],
            )
            for sequence, example in enumerate(lock, start=1)
        }
        for future in concurrent.futures.as_completed(futures):
            identity = futures[future]
            try:
                results.append(future.result())
            except Exception as error:  # noqa: BLE001 - collect every parallel result
                failures.append(f"{identity}: {error}")
    if failures:
        raise PackageExamplesFailure(
            "M27 package example failures: " + "; ".join(sorted(failures))
        )
    results.sort(key=lambda record: int(record["sequence"]))
    evidence = {
        "schema_version": 1,
        "milestone": "M27",
        "evidence_type": "staged-candidate-package-examples",
        "status": "passed",
        "release_version": VERSION,
        "fqbn": FQBN,
        "example_lock_sha256": BASE.file_sha256(args.lock.resolve()),
        "arduino_cli": BASE.cli_identity(cli, config),
        "discovered_count": len(discovered),
        "compiled_count": len(results),
        "all_sketches_from_staged_platform": True,
        "forbidden_path_leakage": False,
        "examples": results,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    BASE.write_json(evidence_path, evidence)
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile all examples from staged NU54DK v0.4.0-rc.1"
    )
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--platform-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--ncs-root", type=Path, required=True)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--forbid-root", type=Path, action="append", default=[])
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--compile-timeout", type=int, default=3600)
    parser.add_argument("--workers", type=int, default=4)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        parsed = build_parser().parse_args(arguments)
        if not 1 <= parsed.compile_timeout <= 86400:
            raise PackageExamplesFailure("compile timeout is outside 1..86400 seconds")
        if not 1 <= parsed.workers <= 8:
            raise PackageExamplesFailure("workers is outside 1..8")
        result = run_gate(parsed)
        print(f"M27_PACKAGE_EXAMPLES_PASS={result['compiled_count']}")
        return 0
    except PackageExamplesFailure as error:
        print(f"M27_PACKAGE_EXAMPLES_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
