#!/usr/bin/env python3
"""! @brief 설치된 v0.3.0 RC package의 Arduino 예제를 전부 빌드합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


FQBN = "nucode:zephyr:nu54dk"
VERSION = "0.3.0-rc.1"
EXPECTED_EXAMPLE_COUNT = 29
LOCK_PATH = Path(__file__).with_name("m22-package-examples.lock.json")
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PackageExamplesFailure(RuntimeError):
    """! @brief 설치 package 예제 gate를 계속할 수 없는 오류입니다. """


## @brief 중복 key를 허용하지 않는 JSON object hook입니다.
def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackageExamplesFailure(f"JSON key가 중복되었습니다: {key}")
        result[key] = value
    return result


## @brief JSON 파일을 크기와 최상위 object 계약까지 검증해 읽습니다.
def strict_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_OUTPUT_BYTES:
        raise PackageExamplesFailure(f"JSON 파일이 없거나 허용 크기를 초과합니다: {path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageExamplesFailure(f"JSON 파일을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(value, dict):
        raise PackageExamplesFailure(f"JSON 최상위 값이 object가 아닙니다: {path}")
    return value


## @brief byte 배열의 SHA-256을 반환합니다.
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


## @brief 파일의 SHA-256을 bounded streaming 방식으로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


## @brief Windows 경로 비교를 위해 slash와 대소문자를 정규화합니다.
def path_key(value: str | Path) -> str:
    return str(value).replace("\\", "/").rstrip("/").casefold()


## @brief Windows 8.3 별칭까지 해소한 절대 경로 비교 key를 반환합니다.
def resolved_path_key(value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        return ""
    return path_key(path.resolve())


## @brief child command를 shell 없이 실행하고 bounded UTF-8 출력을 반환합니다.
def run_command(
    argv: Sequence[str | Path], *, timeout_seconds: int
) -> tuple[int, str, float]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            [str(value) for value in argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise PackageExamplesFailure(
            f"명령이 {timeout_seconds}초 안에 끝나지 않았습니다: {argv[0]}"
        ) from error
    data = result.stdout[-MAX_OUTPUT_BYTES:]
    return result.returncode, data.decode("utf-8", errors="replace"), time.monotonic() - started


## @brief evidence JSON을 UTF-8 LF와 결정적 key 순서로 원자 기록합니다.
def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


## @brief lock file의 모든 29개 예제와 profile 계약을 읽습니다.
def load_example_lock(path: Path = LOCK_PATH) -> list[dict[str, str]]:
    document = strict_json(path)
    if (
        document.get("schema_version") != 1
        or document.get("release_version") != VERSION
        or document.get("fqbn") != FQBN
    ):
        raise PackageExamplesFailure("M22 예제 lock identity가 다릅니다.")
    records = document.get("examples")
    if not isinstance(records, list) or len(records) != EXPECTED_EXAMPLE_COUNT:
        raise PackageExamplesFailure(
            f"M22 package 예제 lock은 정확히 {EXPECTED_EXAMPLE_COUNT}개여야 합니다."
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
            raise PackageExamplesFailure("M22 예제 lock record schema가 잘못되었습니다.")
        if not all(isinstance(value, str) and value for value in record.values()):
            raise PackageExamplesFailure("M22 예제 lock 문자열이 비어 있습니다.")
        if record["profile"] not in {"standard", "ble"}:
            raise PackageExamplesFailure("M22 예제 profile이 허용목록 밖입니다.")
        identity = (record["library"], record["example"])
        if identity in identities:
            raise PackageExamplesFailure(f"M22 예제가 중복되었습니다: {identity}")
        identities.add(identity)
        normalized.append({key: str(value) for key, value in record.items()})
    return normalized


## @brief Arduino CLI discovery JSON에서 설치 package 예제만 exact lock과 대조합니다.
def parse_installed_examples(
    document: dict[str, Any],
    lock: list[dict[str, str]],
    platform_root: Path,
    version: str = VERSION,
) -> dict[tuple[str, str], Path]:
    records = document.get("examples")
    if not isinstance(records, list):
        raise PackageExamplesFailure("Arduino CLI example listing에 examples 배열이 없습니다.")
    expected = {(item["library"], item["example"]): item for item in lock}
    discovered: dict[tuple[str, str], Path] = {}
    resolved_platform = platform_root.resolve()
    for record in records:
        if not isinstance(record, dict):
            raise PackageExamplesFailure("Arduino CLI example record가 object가 아닙니다.")
        library = record.get("library")
        paths = record.get("examples")
        if not isinstance(library, dict) or not isinstance(paths, list):
            raise PackageExamplesFailure("Arduino CLI library example schema가 잘못되었습니다.")
        library_name = library.get("name")
        if not isinstance(library_name, str):
            raise PackageExamplesFailure("Arduino CLI library 이름이 없습니다.")
        relevant = [item for item in lock if item["library"] == library_name]
        if not relevant:
            install_dir = library.get("install_dir")
            belongs_to_platform = (
                library.get("location") == "platform"
                and library.get("container_platform") == f"nucode:zephyr@{version}"
                and isinstance(install_dir, str)
                and (
                    resolved_path_key(install_dir)
                    == resolved_path_key(resolved_platform / "libraries")
                    or resolved_path_key(install_dir).startswith(
                        resolved_path_key(resolved_platform / "libraries") + "/"
                    )
                )
            )
            if belongs_to_platform and paths:
                raise PackageExamplesFailure(
                    f"lock에 없는 설치 package library 예제가 있습니다: {library_name}"
                )
            continue
        install_dir = library.get("install_dir")
        if (
            library.get("location") != "platform"
            or library.get("container_platform") != f"nucode:zephyr@{version}"
            or not isinstance(install_dir, str)
        ):
            raise PackageExamplesFailure(f"설치 library identity가 잘못되었습니다: {library_name}")
        expected_library_root = (
            resolved_platform / "libraries" / relevant[0]["library_directory"]
        ).resolve()
        if resolved_path_key(install_dir) != resolved_path_key(expected_library_root):
            raise PackageExamplesFailure(f"설치 library 경로가 package 밖입니다: {library_name}")
        for value in paths:
            if not isinstance(value, str):
                raise PackageExamplesFailure("Arduino CLI example 경로가 문자열이 아닙니다.")
            path = Path(value)
            identity = (library_name, path.name)
            if identity not in expected:
                raise PackageExamplesFailure(f"예상하지 않은 package 예제입니다: {identity}")
            expected_path = (
                expected_library_root / "examples" / expected[identity]["example"]
            ).resolve()
            if (
                path.resolve() != expected_path
                or not path.is_dir()
                or path.is_symlink()
                or not (path / f"{path.name}.ino").is_file()
            ):
                raise PackageExamplesFailure(f"설치 예제 경로가 유효하지 않습니다: {identity}")
            if identity in discovered:
                raise PackageExamplesFailure(f"설치 예제가 중복 열거되었습니다: {identity}")
            discovered[identity] = path.resolve()
    if set(discovered) != set(expected):
        missing = sorted(set(expected).difference(discovered))
        raise PackageExamplesFailure(f"설치 package 예제 집합이 lock과 다릅니다: missing={missing}")
    return discovered


## @brief JSON 전체 문자열에서 기존 host 경로 누출을 검사합니다.
def assert_no_forbidden_values(value: Any, forbidden_roots: Sequence[Path]) -> None:
    forbidden = [path_key(root) for root in forbidden_roots if str(root)]

    def visit(item: Any) -> None:
        if isinstance(item, str):
            normalized = path_key(item)
            for root in forbidden:
                if normalized == root or normalized.startswith(root + "/"):
                    raise PackageExamplesFailure("build evidence에 기존 host 경로가 누출되었습니다.")
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)

    visit(value)


## @brief 한 예제의 build manifest가 격리 package·SDK·cache만 사용했는지 검증합니다.
def validate_build_manifest(
    manifest_path: Path,
    *,
    example: dict[str, str],
    sketch: Path,
    build_root: Path,
    platform_root: Path,
    ncs_root: Path,
    toolchain_root: Path,
    cache_root: Path,
    forbidden_roots: Sequence[Path],
) -> dict[str, Any]:
    manifest = strict_json(manifest_path)
    context = manifest.get("context")
    artifacts = manifest.get("artifacts")
    if manifest.get("schema_version") != 2 or not isinstance(context, dict) or not isinstance(artifacts, dict):
        raise PackageExamplesFailure("Arduino build manifest schema가 잘못되었습니다.")
    expected_paths = {
        "build_path": build_root.resolve(),
        "platform_root": platform_root.resolve(),
        "sketch_root": sketch.resolve(),
        "ncs_root": ncs_root.resolve(),
        "toolchain_root": toolchain_root.resolve(),
        "cache_root": cache_root.resolve(),
    }
    for field, expected in expected_paths.items():
        actual = context.get(field)
        if (
            not isinstance(actual, str)
            or resolved_path_key(actual) != resolved_path_key(expected)
        ):
            raise PackageExamplesFailure(f"build context의 {field}가 격리 경로와 다릅니다.")
    if context.get("profile") != example["profile"] or context.get("state") != "built":
        raise PackageExamplesFailure("build context의 profile 또는 상태가 다릅니다.")
    fqbn = context.get("fqbn")
    if not isinstance(fqbn, str) or f"feature_set={example['profile']}" not in fqbn:
        raise PackageExamplesFailure("build FQBN에 요청 profile이 기록되지 않았습니다.")
    hex_record = artifacts.get("hex")
    if not isinstance(hex_record, dict):
        raise PackageExamplesFailure("build manifest에 HEX artifact가 없습니다.")
    hex_path = Path(str(hex_record.get("path", "")))
    digest = hex_record.get("sha256")
    size = hex_record.get("size")
    if (
        not hex_path.is_absolute()
        or not hex_path.is_file()
        or not hex_path.resolve().is_relative_to(build_root.resolve())
        or not isinstance(digest, str)
        or not SHA256_RE.fullmatch(digest)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 1
        or hex_path.stat().st_size != size
        or file_sha256(hex_path) != digest
    ):
        raise PackageExamplesFailure("HEX artifact identity가 잘못되었습니다.")
    assert_no_forbidden_values(manifest, forbidden_roots)
    return {
        "manifest_sha256": file_sha256(manifest_path),
        "hex_sha256": digest,
        "hex_size": size,
        "profile": example["profile"],
        "cache_reused": bool(context.get("cache_reused")),
    }


## @brief CLI identity를 version·commit·실행 파일 hash로 수집합니다.
def cli_identity(cli: Path, config: Path) -> dict[str, str]:
    code, output, _ = run_command(
        (cli, "--config-file", config, "version", "--json"), timeout_seconds=120
    )
    if code != 0:
        raise PackageExamplesFailure("Arduino CLI identity 조회가 실패했습니다.")
    try:
        document = json.loads(output, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, PackageExamplesFailure) as error:
        raise PackageExamplesFailure("Arduino CLI identity가 JSON이 아닙니다.") from error
    version = document.get("VersionString")
    commit = document.get("Commit")
    if document.get("Application") != "arduino-cli" or not isinstance(version, str) or not isinstance(commit, str):
        raise PackageExamplesFailure("Arduino CLI identity field가 잘못되었습니다.")
    return {"version": version, "commit": commit, "sha256": file_sha256(cli)}


## @brief 설치본 example discovery와 29개 compile gate를 실행합니다.
def run_gate(args: argparse.Namespace) -> dict[str, Any]:
    cli = args.arduino_cli.resolve()
    config = args.config.resolve()
    platform_root = args.platform_root.resolve()
    build_root = args.build_root.resolve()
    evidence_path = args.evidence.resolve()
    if not cli.is_file() or not config.is_file() or not platform_root.is_dir():
        raise PackageExamplesFailure("Arduino CLI, config 또는 설치 platform이 없습니다.")
    if build_root.exists() and any(build_root.iterdir()):
        raise PackageExamplesFailure("M22 example build root는 비어 있어야 합니다.")
    build_root.mkdir(parents=True, exist_ok=True)
    lock = load_example_lock(args.lock.resolve())
    code, output, _ = run_command(
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
        raise PackageExamplesFailure("Arduino CLI example discovery가 실패했습니다.")
    try:
        listing = json.loads(output, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, PackageExamplesFailure) as error:
        raise PackageExamplesFailure("Arduino CLI example listing이 JSON이 아닙니다.") from error
    if not isinstance(listing, dict):
        raise PackageExamplesFailure("Arduino CLI example listing root가 object가 아닙니다.")
    discovered = parse_installed_examples(listing, lock, platform_root)
    forbidden_roots = tuple(path.resolve() for path in args.forbid_root)
    results: list[dict[str, Any]] = []
    for sequence, example in enumerate(lock, start=1):
        identity = (example["library"], example["example"])
        sketch = discovered[identity]
        safe_name = re.sub(
            r"[^a-z0-9]+", "-", f"{example['library']}-{example['example']}".casefold()
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
        code, compile_output, seconds = run_command(
            command, timeout_seconds=args.compile_timeout
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(compile_output, encoding="utf-8", errors="replace")
        if code != 0:
            raise PackageExamplesFailure(
                f"설치 package 예제 compile이 실패했습니다: {identity}"
            )
        manifest_path = build / f"{example['example']}.ino.nu54-build.json"
        identity_record = validate_build_manifest(
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
        results.append(
            {
                "sequence": sequence,
                "library": example["library"],
                "example": example["example"],
                "installed_relative_path": sketch.relative_to(platform_root).as_posix(),
                "compile_seconds": round(seconds, 3),
                "compile_log_sha256": file_sha256(log_path),
                **identity_record,
            }
        )
        print(
            f"M22_PACKAGE_EXAMPLE_PASS {sequence}/{EXPECTED_EXAMPLE_COUNT} "
            f"{example['library']}::{example['example']}"
        )
    evidence = {
        "schema_version": 1,
        "milestone": "M22",
        "evidence_type": "installed-package-examples",
        "status": "passed",
        "release_version": VERSION,
        "fqbn": FQBN,
        "example_lock_sha256": file_sha256(args.lock.resolve()),
        "arduino_cli": cli_identity(cli, config),
        "discovered_count": len(discovered),
        "compiled_count": len(results),
        "all_sketches_from_installed_platform": True,
        "forbidden_path_leakage": False,
        "examples": results,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(evidence_path, evidence)
    return evidence


## @brief 명령행 parser를 구성합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="설치된 NU54DK v0.3.0 RC package 예제 29개 compile gate"
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
    return parser


## @brief CLI 진입점입니다.
def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        if not 1 <= arguments.compile_timeout <= 86400:
            raise PackageExamplesFailure("compile timeout 범위가 잘못되었습니다.")
        run_gate(arguments)
        return 0
    except PackageExamplesFailure as error:
        print(f"M22_PACKAGE_EXAMPLES_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
