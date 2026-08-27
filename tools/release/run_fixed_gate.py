#!/usr/bin/env python3
"""! @brief M11에서 허용하는 저장소 소유 고정 검증 게이트만 실행합니다. """

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REPOSITORY = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "0.1.0-rc.1"
ARDUINO_CLI_VERSION = "1.5.2-rc.1"
ARDUINO_CLI_COMMIT = "fef6e48df"
ARDUINO_CLI_SHA256 = "ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538"
BOARD_TARGET = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
METADATA_FILES = (
    "release-manifest.json",
    "sbom.spdx.json",
    "license-inventory.json",
    "THIRD_PARTY_NOTICES.md",
    "CHECKSUMS.sha256",
)
SMOKE_TESTS = (
    "blink",
    "library",
    "config",
    "error",
    "parallel",
    "incremental",
    "m6",
    "m7",
    "m8",
    "m9",
    "m11",
)
ZEPHYR_SUITES = (
    ("m3_runtime", "nucode.m3.runtime"),
    ("m4_api_contract", "nucode.m4.api_contract"),
    ("m6_core_api", "nucode.m6.core_api"),
    ("m7_core_api", "nucode.m7.core_api"),
)
MAX_JSON_SIZE = 32 * 1024 * 1024
MAX_PAYLOAD_FILES = 10000
MAX_PAYLOAD_FILE_SIZE = 32 * 1024 * 1024
MAX_PAYLOAD_TOTAL_SIZE = 128 * 1024 * 1024


class FixedGateFailure(RuntimeError):
    """! @brief 고정 gate 계약을 안전하게 계속할 수 없는 오류입니다. """


## @brief byte 배열의 SHA-256을 소문자 16진수로 반환합니다.
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


## @brief 파일 전체 byte의 SHA-256을 chunk 단위로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise FixedGateFailure(f"파일 SHA-256을 계산하지 못했습니다: {path}: {error}") from error
    return digest.hexdigest()


## @brief JSON object를 중복 key와 비정상 UTF-8을 거부하며 읽습니다.
def strict_json_object(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON_SIZE:
            raise FixedGateFailure(f"JSON 파일이 허용 크기를 초과합니다: {path}")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise FixedGateFailure(f"UTF-8 JSON을 읽지 못했습니다: {path}: {error}") from error

    ## @brief object 내부의 중복 key를 즉시 거부합니다.
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise FixedGateFailure(f"JSON key가 중복됩니다: {path}: {key}")
            document[key] = value
        return document

    try:
        document = json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as error:
        raise FixedGateFailure(f"유효한 JSON이 아닙니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise FixedGateFailure(f"JSON 최상위 값이 object가 아닙니다: {path}")
    return document


## @brief JSON을 패키지 fingerprint와 같은 canonical UTF-8 byte로 만듭니다.
def canonical_json(document: Any) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


## @brief 패키지 내부 상대 경로가 Windows에서도 안전한지 검증합니다.
def ensure_safe_relative_path(path: str) -> str:
    if not path or "\\" in path or "\0" in path or re.match(r"^[A-Za-z]:", path):
        raise FixedGateFailure(f"안전하지 않은 패키지 상대 경로입니다: {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise FixedGateFailure(f"안전하지 않은 패키지 상대 경로입니다: {path!r}")
    for part in pure.parts:
        if part.casefold() in {".git", ".hg", ".svn", "__pycache__"}:
            raise FixedGateFailure(f"배포 금지 경로가 포함되었습니다: {path}")
    return pure.as_posix()


## @brief symlink와 추가 directory를 포함해 추출된 platform tree를 엄격히 열거합니다.
def enumerate_platform_files(platform_root: Path) -> dict[str, Path]:
    root = platform_root.resolve()
    root_is_junction = bool(getattr(platform_root, "is_junction", lambda: False)())
    if not root.is_dir() or platform_root.is_symlink() or root_is_junction:
        raise FixedGateFailure(f"추출된 platform root가 일반 directory가 아닙니다: {platform_root}")
    files: dict[str, Path] = {}
    directories: set[str] = set()
    total_size = 0
    try:
        entries = list(root.rglob("*"))
    except OSError as error:
        raise FixedGateFailure(f"platform tree를 열거하지 못했습니다: {root}: {error}") from error
    for entry in entries:
        relative = ensure_safe_relative_path(entry.relative_to(root).as_posix())
        is_junction = bool(getattr(entry, "is_junction", lambda: False)())
        if entry.is_symlink() or is_junction:
            raise FixedGateFailure(f"platform tree에 link 또는 junction이 있습니다: {relative}")
        if entry.is_dir():
            directories.add(relative)
            continue
        if not entry.is_file():
            raise FixedGateFailure(f"platform tree에 일반 파일이 아닌 항목이 있습니다: {relative}")
        if len(files) >= MAX_PAYLOAD_FILES + len(METADATA_FILES):
            raise FixedGateFailure("platform tree의 파일 개수가 허용 범위를 초과합니다.")
        try:
            size = entry.stat().st_size
        except OSError as error:
            raise FixedGateFailure(f"platform 파일 크기를 읽지 못했습니다: {relative}") from error
        if size > MAX_PAYLOAD_FILE_SIZE:
            raise FixedGateFailure(f"platform 파일이 허용 크기를 초과합니다: {relative}")
        total_size += size
        if total_size > MAX_PAYLOAD_TOTAL_SIZE + MAX_JSON_SIZE:
            raise FixedGateFailure("platform tree 전체 크기가 허용 범위를 초과합니다.")
        files[relative] = entry
    expected_directories = {
        PurePosixPath(path).parents[index].as_posix()
        for path in files
        for index in range(len(PurePosixPath(path).parents) - 1)
        if PurePosixPath(path).parents[index].as_posix() != "."
    }
    if directories != expected_directories:
        extras = sorted(directories.difference(expected_directories))
        missing = sorted(expected_directories.difference(directories))
        raise FixedGateFailure(
            "platform directory tree가 파일 manifest에서 유도한 구조와 다릅니다: "
            f"extra={extras}, missing={missing}"
        )
    return files


## @brief platform.txt의 배포 버전만 version 독립 sentinel로 치환합니다.
def normalize_runtime_payload_bytes(path: str, data: bytes) -> bytes:
    if path != "platform.txt":
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FixedGateFailure("platform.txt가 UTF-8이 아닙니다.") from error
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith("version=")]
    if len(matches) != 1:
        raise FixedGateFailure("platform.txt에는 version= 항목이 정확히 하나 있어야 합니다.")
    index = matches[0]
    ending = (
        "\r\n"
        if lines[index].endswith("\r\n")
        else "\n"
        if lines[index].endswith("\n")
        else ""
    )
    lines[index] = f"version=@NU54_PACKAGE_VERSION@{ending}"
    return "".join(lines).encode("utf-8")


## @brief 실제 payload byte와 manifest mode로 version 독립 fingerprint를 계산합니다.
def runtime_payload_sha256(files: Iterable[tuple[str, bytes, int]]) -> str:
    records: list[dict[str, Any]] = []
    for path, data, mode in sorted(files, key=lambda item: item[0].encode("utf-8")):
        normalized = normalize_runtime_payload_bytes(path, data)
        records.append(
            {
                "mode": f"{mode:04o}",
                "path": path,
                "sha256": sha256_bytes(normalized),
                "size": len(normalized),
            }
        )
    return sha256_bytes(
        canonical_json(
            {
                "normalization": "platform-version-sentinel-v1",
                "records": records,
                "schema_version": 1,
            }
        )
    )


## @brief CHECKSUMS.sha256를 결정적 순서와 중복 경로까지 검증해 읽습니다.
def parse_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise FixedGateFailure(f"CHECKSUMS.sha256를 읽지 못했습니다: {error}") from error
    checksums: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if match is None:
            raise FixedGateFailure(f"CHECKSUMS.sha256 record가 유효하지 않습니다: {line!r}")
        digest, relative = match.groups()
        relative = ensure_safe_relative_path(relative)
        if relative in checksums:
            raise FixedGateFailure(f"CHECKSUMS.sha256 경로가 중복됩니다: {relative}")
        checksums[relative] = digest
    if list(checksums) != sorted(checksums, key=lambda value: value.encode("utf-8")):
        raise FixedGateFailure("CHECKSUMS.sha256 경로 순서가 결정적이지 않습니다.")
    return checksums


## @brief 추출된 RC package와 CLI로 받은 외부 expected identity를 byte 단위로 대조합니다.
def validate_platform(
    platform_root: Path,
    *,
    expected_version: str,
    expected_core_revision: str,
    expected_board_revision: str,
    expected_runtime_payload_sha256: str,
    expected_release_manifest_sha256: str,
) -> dict[str, Any]:
    expected_patterns = {
        "core revision": (expected_core_revision, r"[0-9a-f]{40}"),
        "board revision": (expected_board_revision, r"[0-9a-f]{40}"),
        "runtime payload SHA-256": (expected_runtime_payload_sha256, r"[0-9a-f]{64}"),
        "release manifest SHA-256": (expected_release_manifest_sha256, r"[0-9a-f]{64}"),
    }
    if expected_version != RELEASE_VERSION:
        raise FixedGateFailure(f"고정 RC version이 아닙니다: {expected_version!r}")
    for label, (value, pattern) in expected_patterns.items():
        if re.fullmatch(pattern, value) is None:
            raise FixedGateFailure(f"expected {label} 형식이 유효하지 않습니다: {value!r}")

    root = platform_root.resolve()
    files = enumerate_platform_files(platform_root)
    if set(METADATA_FILES).difference(files):
        missing = sorted(set(METADATA_FILES).difference(files))
        raise FixedGateFailure(f"필수 package metadata가 없습니다: {', '.join(missing)}")
    manifest_path = files["release-manifest.json"]
    if file_sha256(manifest_path) != expected_release_manifest_sha256:
        raise FixedGateFailure("release-manifest.json byte hash가 expected 값과 다릅니다.")
    manifest = strict_json_object(manifest_path)
    expected_identity = {
        "schema_version": 1,
        "version": expected_version,
        "core_revision": expected_core_revision,
        "board_revision": expected_board_revision,
        "runtime_payload_sha256": expected_runtime_payload_sha256,
        "archive_root": f"nucode-nu54dk-zephyr-{expected_version}",
        "generated_metadata": list(METADATA_FILES),
    }
    for field, expected in expected_identity.items():
        if manifest.get(field) != expected:
            raise FixedGateFailure(
                f"release-manifest {field} 값이 expected identity와 다릅니다."
            )
    if root.name != expected_identity["archive_root"]:
        raise FixedGateFailure("추출된 platform root 이름이 release-manifest와 다릅니다.")

    records = manifest.get("files")
    file_hashes = manifest.get("file_hashes")
    if not isinstance(records, list) or not isinstance(file_hashes, dict):
        raise FixedGateFailure("release-manifest payload record 구조가 유효하지 않습니다.")
    if len(records) > MAX_PAYLOAD_FILES:
        raise FixedGateFailure("release-manifest payload 파일 수가 허용 범위를 초과합니다.")
    payload: list[tuple[str, bytes, int]] = []
    record_paths: list[str] = []
    total_size = 0
    allowed_record_fields = {
        "git_object",
        "mode",
        "origin",
        "path",
        "sha256",
        "size",
        "transformation",
    }
    for record in records:
        required_fields = {"git_object", "mode", "origin", "path", "sha256", "size"}
        if (
            not isinstance(record, dict)
            or not required_fields.issubset(record)
            or set(record).difference(allowed_record_fields)
        ):
            raise FixedGateFailure("release-manifest payload record field 계약이 다릅니다.")
        relative = ensure_safe_relative_path(str(record["path"]))
        if relative in record_paths:
            raise FixedGateFailure(f"payload record 경로가 중복됩니다: {relative}")
        digest = record.get("sha256")
        size = record.get("size")
        mode_text = record.get("mode")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 <= size <= MAX_PAYLOAD_FILE_SIZE
            or not isinstance(mode_text, str)
            or re.fullmatch(r"0(?:644|755)", mode_text) is None
            or relative not in files
            or file_hashes.get(relative) != digest
            or not isinstance(record.get("git_object"), str)
            or re.fullmatch(r"[0-9a-f]{40}", record["git_object"]) is None
            or record.get("origin") not in {"core", "board"}
            or (
                "transformation" in record
                and not isinstance(record.get("transformation"), str)
            )
        ):
            raise FixedGateFailure(f"payload record identity가 유효하지 않습니다: {relative}")
        try:
            actual_size = files[relative].stat().st_size
        except OSError as error:
            raise FixedGateFailure(f"payload 파일 크기를 읽지 못했습니다: {relative}") from error
        if actual_size != size:
            raise FixedGateFailure(f"payload 파일 크기가 release-manifest와 다릅니다: {relative}")
        try:
            data = files[relative].read_bytes()
        except OSError as error:
            raise FixedGateFailure(f"payload byte를 읽지 못했습니다: {relative}") from error
        if sha256_bytes(data) != digest:
            raise FixedGateFailure(f"payload byte가 release-manifest와 다릅니다: {relative}")
        record_paths.append(relative)
        total_size += size
        if total_size > MAX_PAYLOAD_TOTAL_SIZE:
            raise FixedGateFailure("package payload 전체 크기가 허용 범위를 초과합니다.")
        payload.append((relative, data, int(mode_text, 8)))
    sorted_paths = sorted(record_paths, key=lambda value: value.encode("utf-8"))
    if record_paths != sorted_paths or list(file_hashes) != sorted_paths:
        raise FixedGateFailure("release-manifest payload 경로 순서 또는 file_hashes가 다릅니다.")
    if set(files) != set(record_paths) | set(METADATA_FILES):
        raise FixedGateFailure("추출된 platform에 manifest 허용목록 밖의 파일이 있습니다.")
    if manifest.get("file_count") != len(records) or manifest.get("total_size") != total_size:
        raise FixedGateFailure("release-manifest payload 개수 또는 전체 크기가 다릅니다.")

    checksums = parse_checksums(files["CHECKSUMS.sha256"])
    checksum_paths = sorted(
        set(files).difference({"CHECKSUMS.sha256"}), key=lambda value: value.encode("utf-8")
    )
    if list(checksums) != checksum_paths:
        raise FixedGateFailure("CHECKSUMS.sha256 경로 집합이 추출된 package와 다릅니다.")
    for relative in checksum_paths:
        if checksums[relative] != file_sha256(files[relative]):
            raise FixedGateFailure(f"package metadata checksum이 다릅니다: {relative}")
    actual_runtime_payload = runtime_payload_sha256(payload)
    if actual_runtime_payload != expected_runtime_payload_sha256:
        raise FixedGateFailure("실제 package runtime payload fingerprint가 expected 값과 다릅니다.")
    return {
        "version": expected_version,
        "core_revision": expected_core_revision,
        "board_revision": expected_board_revision,
        "runtime_payload_sha256": actual_runtime_payload,
        "release_manifest_sha256": expected_release_manifest_sha256,
        "platform_root": root.as_posix(),
    }


## @brief 저장소 HEAD와 gate fixture의 worktree byte가 expected core revision과 같은지 확인합니다.
def validate_repository_fixtures(expected_core_revision: str, scopes: Sequence[str]) -> None:
    try:
        head = subprocess.run(
            ("git", "rev-parse", "--verify", "HEAD^{commit}"),
            cwd=REPOSITORY,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise FixedGateFailure("gate fixture 저장소의 HEAD를 확인하지 못했습니다.") from error
    if head != expected_core_revision:
        raise FixedGateFailure("gate fixture 저장소 HEAD가 package core revision과 다릅니다.")
    tracked = subprocess.run(
        ("git", "diff", "--quiet", "HEAD", "--", *scopes),
        cwd=REPOSITORY,
        check=False,
    )
    if tracked.returncode != 0:
        raise FixedGateFailure("gate fixture에 commit되지 않은 tracked 변경이 있습니다.")
    try:
        untracked = subprocess.run(
            ("git", "ls-files", "--others", "--exclude-standard", "--", *scopes),
            cwd=REPOSITORY,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as error:
        raise FixedGateFailure("gate fixture의 untracked 파일을 확인하지 못했습니다.") from error
    if untracked:
        raise FixedGateFailure(f"gate fixture에 untracked 파일이 있습니다: {untracked}")


## @brief 외부 명령을 shell 없이 실행하고 0 이외 종료를 gate 실패로 변환합니다.
def run_checked(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> None:
    normalized = [str(value) for value in command]
    print(f"[NU54-FIXED-GATE] exec: {subprocess.list2cmdline(normalized)}", flush=True)
    try:
        result = subprocess.run(normalized, cwd=cwd, env=environment, check=False)
    except OSError as error:
        raise FixedGateFailure(f"gate 명령을 시작하지 못했습니다: {normalized[0]}: {error}") from error
    if result.returncode != 0:
        raise FixedGateFailure(
            f"gate 명령이 종료 코드 {result.returncode}로 실패했습니다: {normalized[0]}"
        )


## @brief 고정 SHA-256 Arduino CLI의 version과 commit 출력까지 대조합니다.
def validate_arduino_cli(cli_path: Path) -> Path:
    cli = cli_path.resolve()
    if not cli.is_file() or cli_path.is_symlink():
        raise FixedGateFailure(f"Arduino CLI가 일반 파일이 아닙니다: {cli_path}")
    if file_sha256(cli) != ARDUINO_CLI_SHA256:
        raise FixedGateFailure("Arduino CLI executable SHA-256이 고정값과 다릅니다.")
    try:
        result = subprocess.run(
            (str(cli), "version"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise FixedGateFailure(f"Arduino CLI version을 실행하지 못했습니다: {error}") from error
    identity = re.search(r"\bVersion:\s*(\S+)\s+Commit:\s*(\S+)", result.stdout)
    if (
        result.returncode != 0
        or identity is None
        or identity.group(1) != ARDUINO_CLI_VERSION
        or identity.group(2) != ARDUINO_CLI_COMMIT
    ):
        raise FixedGateFailure("Arduino CLI version/commit 출력이 고정 identity와 다릅니다.")
    return cli


## @brief 패키지 안의 Build Adapter를 검증된 byte에서 동적으로 읽습니다.
def load_packaged_builder(platform_root: Path) -> Any:
    module_path = platform_root / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
    if not module_path.is_file():
        raise FixedGateFailure(f"package Build Adapter를 찾지 못했습니다: {module_path}")
    specification = importlib.util.spec_from_file_location("nu54_fixed_gate_builder", module_path)
    if specification is None or specification.loader is None:
        raise FixedGateFailure(f"package Build Adapter를 읽을 수 없습니다: {module_path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        raise FixedGateFailure(f"package Build Adapter를 적재하지 못했습니다: {error}") from error
    return module


## @brief host regression의 유일하게 허용된 unittest discovery 계약을 실행합니다.
def run_host_gate() -> None:
    run_checked(
        (
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(REPOSITORY / "tests" / "host"),
            "-p",
            "test_*.py",
        ),
        cwd=REPOSITORY,
    )


## @brief 추출 RC package로 전체 Arduino CLI smoke scenario를 정확히 한 번 실행합니다.
def run_arduino_gate(args: argparse.Namespace) -> None:
    identity = validate_platform_from_arguments(args)
    validate_repository_fixtures(
        identity["core_revision"],
        ("examples", "tests/arduino-cli", "tools/release/run_fixed_gate.py"),
    )
    cli = validate_arduino_cli(args.arduino_cli)
    smoke = REPOSITORY / "tests" / "arduino-cli" / "run_smoke.py"
    run_checked(
        (
            sys.executable,
            smoke,
            "--cli",
            cli,
            "--platform-root",
            args.platform_root.resolve(),
            "--tests",
            *SMOKE_TESTS,
        ),
        cwd=REPOSITORY,
    )
    print(json.dumps({"gate": "arduino", "package": identity}, sort_keys=True))


## @brief 고정된 네 target suite만 package runtime과 함께 임시 tree에 배치합니다.
def stage_zephyr_gate_tree(platform_root: Path, destination: Path) -> Path:
    staged = destination / platform_root.name
    shutil.copytree(platform_root, staged)
    test_root = staged / "tests" / "zephyr"
    test_root.mkdir(parents=True)
    source_root = REPOSITORY / "tests" / "zephyr"
    for directory, _scenario in ZEPHYR_SUITES:
        source = source_root / directory
        if not (source / "testcase.yaml").is_file() or not (source / "CMakeLists.txt").is_file():
            raise FixedGateFailure(f"고정 Zephyr suite가 완전하지 않습니다: {source}")
        shutil.copytree(source, test_root / directory)
    return staged


## @brief Twister JSON이 정확한 target/suite 집합의 build PASS인지 확인합니다.
def validate_twister_result(report_path: Path) -> None:
    report = strict_json_object(report_path)
    environment = report.get("environment")
    suites = report.get("testsuites")
    if not isinstance(environment, dict) or not isinstance(suites, list):
        raise FixedGateFailure("Twister report 구조가 유효하지 않습니다.")
    if environment.get("zephyr_version") != "ncs-v3.4.0":
        raise FixedGateFailure("Twister가 고정 NCS Zephyr version을 사용하지 않았습니다.")
    expected_names = {scenario for _directory, scenario in ZEPHYR_SUITES}
    actual_names: set[str] = set()
    for suite in suites:
        if not isinstance(suite, dict):
            raise FixedGateFailure("Twister testsuite record가 object가 아닙니다.")
        name = suite.get("name")
        if not isinstance(name, str) or name in actual_names:
            raise FixedGateFailure("Twister testsuite 이름이 없거나 중복됩니다.")
        actual_names.add(name)
        if (
            suite.get("platform") != BOARD_TARGET
            or suite.get("arch") != "arm"
            or suite.get("status") != "passed"
        ):
            raise FixedGateFailure(f"Twister target build가 PASS가 아닙니다: {name}")
    if actual_names != expected_names:
        raise FixedGateFailure(
            f"Twister suite 집합이 고정 계약과 다릅니다: {sorted(actual_names)}"
        )


## @brief 추출 RC package와 고정 prerequisite로 정확한 target Twister scope를 빌드합니다.
def run_zephyr_gate(args: argparse.Namespace) -> None:
    identity = validate_platform_from_arguments(args)
    validate_repository_fixtures(
        identity["core_revision"],
        ("tests/zephyr", "tools/release/run_fixed_gate.py"),
    )
    outdir = args.outdir.resolve()
    if outdir.exists() or outdir.parent == outdir:
        raise FixedGateFailure("Twister outdir는 아직 존재하지 않는 안전한 하위 경로여야 합니다.")
    outdir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="n54zg-") as temporary_name:
        staged = stage_zephyr_gate_tree(args.platform_root.resolve(), Path(temporary_name))
        builder = load_packaged_builder(staged)
        try:
            tools = builder.tool_environment(staged)
        except Exception as error:
            raise FixedGateFailure(f"고정 NCS/toolchain prerequisite 검증에 실패했습니다: {error}") from error
        toolchain_root = Path(tools["toolchain_root"])
        python = toolchain_root / "opt" / "bin" / "python.exe"
        twister = Path(tools["zephyr_base"]) / "scripts" / "twister"
        if not python.is_file() or not twister.is_file():
            raise FixedGateFailure("고정 toolchain Python 또는 Twister를 찾지 못했습니다.")
        test_root = staged / "tests" / "zephyr"
        board_root = staged / "board_package" / "NU54DK_Zephyr_DTS"
        command: list[str | Path] = [
            python,
            twister,
            "--testsuite-root",
            test_root,
            "--platform",
            BOARD_TARGET,
            "--board-root",
            board_root / "boards",
            "--build-only",
            "--short-build-path",
            "--outdir",
            outdir,
            "--extra-args",
            f"BOARD_ROOT={board_root.as_posix()}",
            "--extra-args",
            f"EXTRA_ZEPHYR_MODULES={staged.as_posix()}",
        ]
        for _directory, scenario in ZEPHYR_SUITES:
            command.extend(("--scenario", scenario))
        run_checked(command, cwd=staged, environment=dict(tools["environment"]))
    validate_twister_result(outdir / "twister.json")
    print(json.dumps({"gate": "zephyr", "package": identity}, sort_keys=True))


## @brief package 공통 CLI expected 값을 추출해 단일 validator에 전달합니다.
def validate_platform_from_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return validate_platform(
        args.platform_root,
        expected_version=args.expected_version,
        expected_core_revision=args.expected_core_revision,
        expected_board_revision=args.expected_board_revision,
        expected_runtime_payload_sha256=args.expected_runtime_payload_sha256,
        expected_release_manifest_sha256=args.expected_release_manifest_sha256,
    )


## @brief package 검증 subcommand에 필수 expected identity 인자를 추가합니다.
def add_package_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform-root", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-core-revision", required=True)
    parser.add_argument("--expected-board-revision", required=True)
    parser.add_argument("--expected-runtime-payload-sha256", required=True)
    parser.add_argument("--expected-release-manifest-sha256", required=True)


## @brief 임의 command를 받지 않는 고정 gate CLI parser를 구성합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NU54DK M11 repository-owned fixed gate runner"
    )
    subparsers = parser.add_subparsers(dest="gate", required=True)
    host = subparsers.add_parser("host", help="정확한 tests/host unittest discovery 실행")
    host.add_argument("--repo-root", type=Path, required=True)
    arduino = subparsers.add_parser(
        "arduino", help="정확한 Arduino CLI와 전체 fixed-package smoke 실행"
    )
    arduino.add_argument("--repo-root", type=Path, required=True)
    add_package_arguments(arduino)
    arduino.add_argument("--arduino-cli", type=Path, required=True)
    zephyr = subparsers.add_parser(
        "zephyr", help="고정 NCS/toolchain으로 정확한 target Twister scope 실행"
    )
    zephyr.add_argument("--repo-root", type=Path, required=True)
    add_package_arguments(zephyr)
    zephyr.add_argument("--outdir", type=Path, required=True)
    return parser


## @brief 선택한 고정 gate만 실행하고 계약 위반 시 fail-closed 종료합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    if args.repo_root.resolve() != REPOSITORY:
        raise FixedGateFailure(
            "--repo-root는 실행 중인 고정 gate runner를 소유한 저장소 root여야 합니다."
        )
    if args.gate == "host":
        run_host_gate()
    elif args.gate == "arduino":
        run_arduino_gate(args)
    elif args.gate == "zephyr":
        run_zephyr_gate(args)
    else:
        raise FixedGateFailure(f"지원하지 않는 고정 gate입니다: {args.gate}")
    print(f"[NU54-FIXED-GATE] PASS: {args.gate}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FixedGateFailure as error:
        print(f"[NU54-FIXED-GATE] FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
