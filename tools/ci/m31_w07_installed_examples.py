#!/usr/bin/env python3
"""! @brief M31 W07 설치본 예제를 발견하고 현재 소스와 대조해 전수 빌드합니다. """

from __future__ import annotations

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import subprocess
import sys
import time


FLASH = re.compile(r"Sketch uses (\d+) bytes")
RAM = re.compile(r"Global variables use (\d+) bytes")


## @brief 파일 이름과 내용을 포함한 tree 지문을 계산합니다.
def tree_fingerprint(directory: Path) -> tuple[int, str]:
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(directory).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return len(files), digest.hexdigest()


## @brief readiness에서 실제 설치·빌드 대상 sketch를 중복 없이 추출합니다.
def expected_sketches(readiness: dict) -> list[str]:
    paths: set[str] = set()
    for role in readiness["example_roles"]:
        actual = role.get("actual_sketch")
        if actual:
            paths.add(actual)
        paths.update(role.get("related_sketches", []))
    return sorted(paths, key=str.casefold)


## @brief 설치된 library의 example 목록과 source tree 동일성을 검사합니다.
def discover_library(cli: Path, config: Path, repository: Path,
                     library_directory: str) -> dict:
    properties = repository / "libraries" / library_directory / "library.properties"
    name_match = re.search(
        r"^name=(.+?)\s*$",
        properties.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if name_match is None:
        raise RuntimeError(f"library name이 없습니다: {library_directory}")
    library_name = name_match.group(1)
    listing = subprocess.run(
        (
            str(cli), "lib", "examples", library_name, "--json",
            "--config-file", str(config),
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )
    entries = json.loads(listing.stdout)["examples"]
    if len(entries) != 1 or entries[0]["library"]["name"] != library_name:
        raise RuntimeError(f"설치 library가 정확히 하나가 아닙니다: {library_name}")
    installed = Path(entries[0]["library"]["install_dir"]).resolve()
    source = (repository / "libraries" / library_directory).resolve()
    source_count, source_hash = tree_fingerprint(source)
    installed_count, installed_hash = tree_fingerprint(installed)
    if installed.is_relative_to(repository):
        raise RuntimeError(f"설치 library가 저장소를 직접 가리킵니다: {library_name}")
    if source_count != installed_count or source_hash != installed_hash:
        raise RuntimeError(f"설치 library가 현재 소스와 다릅니다: {library_name}")
    return {
        "directory": library_directory,
        "name": library_name,
        "installed": installed,
        "container_platform": entries[0]["library"]["container_platform"],
        "discovered": sorted(
            Path(value).resolve().relative_to(installed).as_posix()
            for value in entries[0]["examples"]
        ),
        "file_count": source_count,
        "tree_sha256": source_hash,
    }


## @brief 한 설치 예제를 독립 build path에서 빌드하고 hash·크기를 기록합니다.
def build_example(cli: Path, config: Path, fqbn: str, sketch: Path,
                  build_path: Path, log_path: Path, relative: str) -> dict:
    started = time.monotonic()
    build_path.mkdir(parents=True)
    completed = subprocess.run(
        (
            str(cli), "compile", "--config-file", str(config),
            "--fqbn", fqbn, "--build-path", str(build_path), str(sketch),
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1200,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    log_path.write_text(combined, encoding="utf-8")
    images = list(build_path.glob("*.ino.hex"))
    flash = FLASH.search(combined)
    ram = RAM.search(combined)
    passed = (
        completed.returncode == 0
        and len(images) == 1
        and flash is not None
        and ram is not None
    )
    return {
        "sketch": relative,
        "status": "PASS" if passed else "FAIL",
        "exit_code": completed.returncode,
        "elapsed_s": round(time.monotonic() - started, 3),
        "sketch_sha256": hashlib.sha256(sketch.read_bytes()).hexdigest(),
        "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
        "hex_sha256": (
            hashlib.sha256(images[0].read_bytes()).hexdigest()
            if len(images) == 1 else None
        ),
        "program_bytes": int(flash.group(1)) if flash else None,
        "ram_bytes": int(ram.group(1)) if ram else None,
        "failure_tail": combined.splitlines()[-20:] if not passed else [],
    }


## @brief 설치본 49개 채택 예제를 병렬 2개 이하로 빌드합니다.
def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--arduino-cli", required=True, type=Path)
    parser.add_argument("--config-file", required=True, type=Path)
    parser.add_argument("--readiness", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument(
        "--fqbn", default="nucode:zephyr:nu54dk:feature_set=ble"
    )
    arguments = parser.parse_args()
    repository = arguments.repository.resolve()
    cli = arguments.arduino_cli.resolve()
    config = arguments.config_file.resolve()
    readiness_path = arguments.readiness.resolve()
    build_root = arguments.build_root.resolve()
    output = arguments.output.resolve()
    if arguments.jobs < 1 or arguments.jobs > 2:
        parser.error("--jobs는 1 또는 2여야 합니다")
    if build_root.exists() or output.exists():
        parser.error("기존 build root나 evidence를 덮어쓰지 않습니다")
    if build_root.is_relative_to(repository) or output.is_relative_to(repository):
        parser.error("build root와 실행 중 evidence는 저장소 밖이어야 합니다")
    dirty = subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=repository, text=True
    ).strip()
    if dirty:
        parser.error("exact 설치본 build에는 clean source가 필요합니다")
    revision = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=repository, text=True
    ).strip()
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    expected = expected_sketches(readiness)
    if len(expected) != 49:
        raise RuntimeError(f"채택 sketch 분모가 49가 아닙니다: {len(expected)}")
    library_directories = sorted(
        {PurePosixPath(path).parts[1] for path in expected},
        key=str.casefold,
    )
    libraries = {
        item["directory"]: item
        for item in (
            discover_library(cli, config, repository, directory)
            for directory in library_directories
        )
    }
    missing = []
    build_inputs = []
    for relative in expected:
        parts = PurePosixPath(relative).parts
        directory = parts[1]
        example = parts[3]
        installed_root = libraries[directory]["installed"]
        installed_sketch = installed_root / "examples" / example / f"{example}.ino"
        discovered = f"examples/{example}"
        if discovered not in libraries[directory]["discovered"] or not installed_sketch.is_file():
            missing.append(relative)
            continue
        key = f"{directory}__{example}"
        build_inputs.append((relative, installed_sketch, key))
    if missing:
        raise RuntimeError("설치본 discovery 누락: " + ", ".join(missing))
    build_root.mkdir(parents=True)
    log_root = build_root / "logs"
    log_root.mkdir()
    result = {
        "schema_version": 1,
        "status": "IN_PROGRESS",
        "test": "m31_w07_installed_adopted_examples",
        "core_revision": revision,
        "source_clean": True,
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "fqbn": arguments.fqbn,
        "jobs": arguments.jobs,
        "cli_sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "readiness_sha256": hashlib.sha256(readiness_path.read_bytes()).hexdigest(),
        "role_denominator": len(readiness["example_roles"]),
        "applicable_role_count": sum(
            item["build_status"] == "PASS" for item in readiness["example_roles"]
        ),
        "not_run_role_count": sum(
            item["build_status"] == "NOT_RUN" for item in readiness["example_roles"]
        ),
        "unsupported_role_count": sum(
            item["build_status"] == "UNSUPPORTED" for item in readiness["example_roles"]
        ),
        "adopted_unique_sketches": len(expected),
        "libraries": [
            {
                key: value
                for key, value in item.items()
                if key != "installed"
            }
            for item in libraries.values()
        ],
        "builds": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with ThreadPoolExecutor(max_workers=arguments.jobs) as executor:
        futures = {
            executor.submit(
                build_example,
                cli,
                config,
                arguments.fqbn,
                sketch,
                build_root / key,
                log_root / f"{key}.log",
                relative,
            ): relative
            for relative, sketch, key in build_inputs
        }
        for future in as_completed(futures):
            row = future.result()
            result["builds"].append(row)
            result["builds"].sort(key=lambda item: item["sketch"].casefold())
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"{row['sketch']}: {row['status']}", flush=True)
    failures = [row for row in result["builds"] if row["status"] != "PASS"]
    source_clean_after = not bool(subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=repository, text=True
    ).strip())
    result["status"] = "PASS" if not failures and source_clean_after else "FAIL"
    result["source_clean_after"] = source_clean_after
    result["built"] = sum(row["status"] == "PASS" for row in result["builds"])
    result["failed"] = len(failures)
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"M31_W07_INSTALLED_EXAMPLES={result['status']};"
        f"BUILDS={result['built']}/{len(expected)}"
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

