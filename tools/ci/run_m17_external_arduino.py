#!/usr/bin/env python3
"""! @brief 고정한 외부 Adafruit sensor library의 NU54DK compile gate를 실행합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence
import urllib.parse
import urllib.error
import urllib.request
import zipfile


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = Path(__file__).with_name("m17-external-libraries.lock.json")
M17_CI_LOCK = Path(__file__).with_name("ncs-3.4.0.lock.json")
SMOKE_PATH = REPOSITORY / "tests" / "arduino-cli" / "run_smoke.py"
SKETCH = (
    REPOSITORY
    / "tests"
    / "arduino-cli"
    / "m17_adafruit_lsm6ds_compile"
)
FQBN = "nucode:zephyr:nu54dk"
EXPECTED_ARDUINO_CLI_VERSION = "1.5.1"
ALLOWED_HOSTS = {"github.com", "codeload.github.com"}
EXPECTED_LIBRARIES = {
    "Adafruit LSM6DS": (
        "Adafruit_LSM6DS",
        "4.7.4",
        "4.7.4",
        "379a5204c0bad71264c3d635de84d0f9679ab784",
        "BSD-3-Clause",
        "098107002a2ff47fe2f4c4bc79f398f42a47bee253eebe3395924887557486a9",
    ),
    "Adafruit BusIO": (
        "Adafruit_BusIO",
        "1.17.4",
        "1.17.4",
        "3b8364267c3ee6e16bad91bc2101aefbd5b5915f",
        "MIT",
        "e29b45a03874be4c054b04421073675efef5a950b2577b363cff8f17e90db26c",
    ),
    "Adafruit Unified Sensor": (
        "Adafruit_Unified_Sensor",
        "1.1.15",
        "1.1.15",
        "0a9127a1e886ff1adb4c1b6f5958b24108d55aa6",
        "Apache-2.0",
        "95556ec61cd92df3e15c450d8febed64284d0b5416ce3ac0891fab326130b3c7",
    ),
}


class ExternalArduinoFailure(RuntimeError):
    """! @brief 외부 Arduino library gate의 fail-closed 오류입니다. """


class DuplicateKeyError(ValueError):
    """! @brief JSON object의 중복 key 오류입니다. """


## @brief 중복 key를 거부하는 JSON object를 만듭니다.
def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise DuplicateKeyError(f"중복 JSON key입니다: {key}")
        document[key] = value
    return document


## @brief 외부 library lock을 exact allowlist와 함께 검증합니다.
def load_lock(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=strict_object
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as error:
        raise ExternalArduinoFailure(f"외부 library lock을 읽지 못했습니다: {error}") from error
    if set(document) != {"schema_version", "libraries"} or document.get("schema_version") != 1:
        raise ExternalArduinoFailure("외부 library lock root schema가 다릅니다.")
    libraries = document.get("libraries")
    if not isinstance(libraries, list) or len(libraries) != len(EXPECTED_LIBRARIES):
        raise ExternalArduinoFailure("외부 library lock의 library 수가 다릅니다.")
    allowed = {
        "name", "directory", "version", "tag", "commit", "license", "url", "sha256"
    }
    seen: set[str] = set()
    for record in libraries:
        if not isinstance(record, dict) or set(record) != allowed:
            raise ExternalArduinoFailure("외부 library record schema가 다릅니다.")
        if not all(isinstance(record[field], str) for field in allowed):
            raise ExternalArduinoFailure("외부 library record 값은 문자열이어야 합니다.")
        name = record["name"]
        expected = EXPECTED_LIBRARIES.get(name)
        if expected is None or name in seen:
            raise ExternalArduinoFailure(f"허용하지 않거나 중복된 외부 library입니다: {name}")
        seen.add(name)
        actual = tuple(record[field] for field in (
            "directory", "version", "tag", "commit", "license", "sha256"
        ))
        if actual != expected:
            raise ExternalArduinoFailure(f"외부 library pin이 exact allowlist와 다릅니다: {name}")
        if not re.fullmatch(r"[0-9a-f]{40}", record["commit"]) or not re.fullmatch(
            r"[0-9a-f]{64}", record["sha256"]
        ):
            raise ExternalArduinoFailure(f"외부 library hash 형식이 잘못되었습니다: {name}")
        parsed = urllib.parse.urlparse(record["url"])
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ExternalArduinoFailure(f"허용하지 않는 외부 archive URL입니다: {name}")
    if seen != set(EXPECTED_LIBRARIES):
        raise ExternalArduinoFailure("필수 외부 library pin이 누락됐습니다.")
    return document


## @brief URL의 archive를 내려받고 redirect 대상도 allowlist인지 확인합니다.
def download_archive(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "NUCODE-M17-CI/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in ALLOWED_HOSTS:
                raise ExternalArduinoFailure("외부 archive redirect가 allowlist를 벗어났습니다.")
            return response.read()
    except (OSError, urllib.error.URLError) as error:
        raise ExternalArduinoFailure(f"외부 archive download에 실패했습니다: {url}: {error}") from error


## @brief ZIP member가 단일 root 아래의 안전한 일반 파일인지 검사합니다.
def safe_members(archive: zipfile.ZipFile) -> tuple[str, list[zipfile.ZipInfo]]:
    members = archive.infolist()
    if not members:
        raise ExternalArduinoFailure("외부 archive가 비어 있습니다.")
    roots: set[str] = set()
    for member in members:
        name = member.filename
        raw_parts = name.split("/")
        if member.is_dir() and raw_parts and raw_parts[-1] == "":
            raw_parts = raw_parts[:-1]
        if (
            not name
            or "\\" in name
            or name.startswith("//")
            or re.match(r"^[A-Za-z]:", name)
            or any(part in {"", ".", ".."} for part in raw_parts)
            or any(":" in part for part in raw_parts)
            or any(any(ord(character) < 0x20 for character in part) for part in raw_parts)
        ):
            raise ExternalArduinoFailure(f"외부 archive 경로가 안전하지 않습니다: {member.filename}")
        path = PurePosixPath(name)
        if path.is_absolute() or not path.parts:
            raise ExternalArduinoFailure(f"외부 archive 경로가 안전하지 않습니다: {member.filename}")
        roots.add(path.parts[0])
        unix_mode = member.external_attr >> 16
        file_type = unix_mode & 0o170000
        if file_type == 0o120000:
            raise ExternalArduinoFailure(f"외부 archive symlink를 허용하지 않습니다: {member.filename}")
        if file_type not in {0, 0o040000, 0o100000}:
            raise ExternalArduinoFailure(f"외부 archive 특수 파일을 허용하지 않습니다: {member.filename}")
    if len(roots) != 1:
        raise ExternalArduinoFailure("외부 archive는 단일 root directory여야 합니다.")
    return next(iter(roots)), members


## @brief 추출 대상이 destination의 실제 경로 안에 있는지 fail-closed로 확인합니다.
def contained_target(destination: Path, relative: PurePosixPath) -> Path:
    base = destination.resolve()
    target = base.joinpath(*relative.parts).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise ExternalArduinoFailure(
            f"외부 archive 추출 대상이 destination을 벗어났습니다: {relative}"
        ) from error
    if target == base:
        raise ExternalArduinoFailure("외부 archive 파일 대상이 destination 자체입니다.")
    return target


## @brief 검증된 ZIP bytes를 격리된 Arduino library directory에 풉니다.
def extract_archive(content: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root, members = safe_members(archive)
        for member in members:
            relative = PurePosixPath(member.filename).relative_to(root)
            if not relative.parts:
                continue
            target = contained_target(destination, relative)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


## @brief repository helper module을 경로에서 안전하게 불러옵니다.
def load_smoke_module() -> Any:
    spec = importlib.util.spec_from_file_location("nu54_m17_smoke", SMOKE_PATH)
    if spec is None or spec.loader is None:
        raise ExternalArduinoFailure("Arduino smoke helper를 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


## @brief git revision을 exact 40자리 SHA로 읽습니다.
def git_revision(path: Path) -> str:
    result = subprocess.run(
        ("git", "-C", str(path), "rev-parse", "HEAD"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ExternalArduinoFailure(f"git revision을 읽지 못했습니다: {path}")
    return revision


## @brief Arduino CLI executable의 SHA-256을 계산합니다.
def executable_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ExternalArduinoFailure(
            f"Arduino CLI executable을 읽지 못했습니다: {path}: {error}"
        ) from error
    return digest.hexdigest()


## @brief Arduino CLI 1.5.1 executable의 version과 시작 SHA를 fail-closed로 검증합니다.
def validate_arduino_cli(cli: Path) -> dict[str, str]:
    cli = cli.resolve()
    if not cli.is_file():
        raise ExternalArduinoFailure("exact Arduino CLI executable이 없습니다.")
    initial_sha256 = executable_sha256(cli)
    try:
        result = subprocess.run(
            (str(cli), "version"),
            shell=False,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as error:
        raise ExternalArduinoFailure(f"Arduino CLI version 검사를 실행하지 못했습니다: {error}") from error
    output = result.stdout.strip()
    versions = re.findall(r"\bVersion:\s*([0-9]+\.[0-9]+\.[0-9]+)\b", output)
    if result.returncode != 0 or versions != [EXPECTED_ARDUINO_CLI_VERSION]:
        raise ExternalArduinoFailure(
            "Arduino CLI version이 exact pin과 다릅니다: "
            f"expected={EXPECTED_ARDUINO_CLI_VERSION}, output={output!r}"
        )
    return {
        "version": EXPECTED_ARDUINO_CLI_VERSION,
        "executable_sha256": initial_sha256,
    }


## @brief compile 종료 시 Arduino CLI executable이 교체되지 않았는지 확인합니다.
def verify_arduino_cli_unchanged(cli: Path, identity: dict[str, str]) -> None:
    actual_sha256 = executable_sha256(cli.resolve())
    if actual_sha256 != identity["executable_sha256"]:
        raise ExternalArduinoFailure(
            "compile 도중 Arduino CLI executable SHA-256이 변경됐습니다: "
            f"expected={identity['executable_sha256']}, actual={actual_sha256}"
        )


## @brief Git 명령의 UTF-8 출력을 반환하고 실패를 외부 gate 오류로 변환합니다.
def git_output(path: Path, arguments: Sequence[str], context: str) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(path), *arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as error:
        raise ExternalArduinoFailure(f"{context} Git 검사를 실행하지 못했습니다: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "Git이 세부 오류를 반환하지 않았습니다."
        raise ExternalArduinoFailure(f"{context} Git 검사에 실패했습니다: {detail}")
    return result.stdout


## @brief M17 CI lock에서 exact board revision을 읽습니다.
def expected_board_revision() -> str:
    try:
        document = json.loads(
            M17_CI_LOCK.read_text(encoding="utf-8"), object_pairs_hook=strict_object
        )
        revision = document["board"]["revision"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError, KeyError, TypeError) as error:
        raise ExternalArduinoFailure(f"M17 CI lock의 board revision을 읽지 못했습니다: {error}") from error
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ExternalArduinoFailure("M17 CI lock의 board revision 형식이 잘못됐습니다.")
    return revision


## @brief Core HEAD와 board gitlink·checkout이 모두 exact clean 상태인지 검증합니다.
def validate_exact_checkout(
    allowed_untracked_roots: Sequence[Path] = (),
) -> dict[str, str]:
    repository_root = Path(
        git_output(REPOSITORY, ("rev-parse", "--show-toplevel"), "Core 저장소 root").strip()
    ).resolve()
    if repository_root != REPOSITORY.resolve():
        raise ExternalArduinoFailure(f"Core Git root가 예상 경로와 다릅니다: {repository_root}")
    core_revision = git_revision(REPOSITORY)
    tracked_status = git_output(
        REPOSITORY,
        ("status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all"),
        "Core checkout",
    )
    if tracked_status.strip():
        raise ExternalArduinoFailure("Core checkout에 tracked 미커밋 변경이 있습니다.")
    repository_resolved = REPOSITORY.resolve()
    ci_output_root = (REPOSITORY / "m12-evidence").resolve()
    allowed: list[Path] = []
    for root in allowed_untracked_roots:
        resolved = root.resolve()
        try:
            resolved.relative_to(repository_resolved)
        except ValueError:
            ## @note 저장소 밖 output은 Git clean 판정에 없으므로 allowlist에서 제외합니다.
            continue
        if resolved == repository_resolved:
            raise ExternalArduinoFailure("Core 저장소 전체를 CI output 경로로 허용할 수 없습니다.")
        if resolved == ci_output_root or resolved.is_relative_to(ci_output_root):
            allowed.append(resolved)
    untracked_output = git_output(
        REPOSITORY,
        ("ls-files", "--others", "--exclude-standard", "-z"),
        "Core untracked checkout",
    )
    for relative in (item for item in untracked_output.split("\0") if item):
        candidate = (REPOSITORY / relative).resolve()
        if not any(
            candidate == root or candidate.is_relative_to(root)
            for root in allowed
        ):
            raise ExternalArduinoFailure(
                f"Core checkout에 허용하지 않은 untracked 파일이 있습니다: {relative}"
            )

    expected_board = expected_board_revision()
    gitlink_output = git_output(
        REPOSITORY,
        ("ls-tree", core_revision, "--", "board_package/NU54DK_Zephyr_DTS"),
        "Core board gitlink",
    )
    match = re.fullmatch(
        r"160000 commit ([0-9a-f]{40})\tboard_package/NU54DK_Zephyr_DTS\r?\n?",
        gitlink_output,
    )
    if match is None or match.group(1) != expected_board:
        actual = match.group(1) if match else "invalid-or-missing"
        raise ExternalArduinoFailure(
            "Core board gitlink가 M17 exact pin과 다릅니다: "
            f"expected={expected_board}, actual={actual}"
        )

    board_root = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
    actual_board_root = Path(
        git_output(board_root, ("rev-parse", "--show-toplevel"), "board 저장소 root").strip()
    ).resolve()
    if actual_board_root != board_root.resolve():
        raise ExternalArduinoFailure(f"board Git root가 예상 경로와 다릅니다: {actual_board_root}")
    board_revision = git_revision(board_root)
    if board_revision != expected_board:
        raise ExternalArduinoFailure(
            "board checkout이 Core gitlink와 다릅니다: "
            f"expected={expected_board}, actual={board_revision}"
        )
    board_status = git_output(
        board_root,
        ("status", "--porcelain", "--untracked-files=all"),
        "board checkout",
    )
    if board_status.strip():
        raise ExternalArduinoFailure("board checkout에 미커밋 변경이 있습니다.")
    return {"core_revision": core_revision, "board_revision": board_revision}


## @brief 지정 revision의 Git tree를 ZIP archive로 읽습니다.
def git_archive(path: Path, revision: str) -> bytes:
    try:
        result = subprocess.run(
            ("git", "-C", str(path), "archive", "--format=zip", revision),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise ExternalArduinoFailure(f"exact Git snapshot을 만들지 못했습니다: {path}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ExternalArduinoFailure(f"exact Git snapshot 생성에 실패했습니다: {path}: {detail}")
    return result.stdout


## @brief Core와 board의 commit tree만으로 독립 source snapshot을 만듭니다.
def materialize_exact_snapshot(destination: Path, identity: dict[str, str]) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(git_archive(REPOSITORY, identity["core_revision"]))) as archive:
        archive.extractall(destination)
    board_destination = destination / "board_package" / "NU54DK_Zephyr_DTS"
    board_destination.mkdir(parents=True, exist_ok=True)
    board_root = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
    with zipfile.ZipFile(io.BytesIO(git_archive(board_root, identity["board_revision"]))) as archive:
        archive.extractall(board_destination)


## @brief JSON evidence를 결정적인 UTF-8 형식으로 기록합니다.
def write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


## @brief exact 외부 library를 격리 설치하고 NU54DK compile을 실행합니다.
def run_gate(cli: Path, lock_path: Path, evidence_path: Path, log_path: Path) -> None:
    cli = cli.resolve()
    output_roots = (evidence_path.parent, log_path.parent)
    identity = validate_exact_checkout(output_roots)
    cli_identity = validate_arduino_cli(cli)
    lock = load_lock(lock_path)
    smoke = load_smoke_module()
    lock_bytes = lock_path.read_bytes()
    library_evidence: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="nu54-m17-external-") as temporary_name:
        temporary = Path(temporary_name)
        exact_source = temporary / "exact-source"
        materialize_exact_snapshot(exact_source, identity)
        user_root = temporary / "user"
        smoke.stage_platform(exact_source, user_root)
        config = temporary / "arduino-cli.yaml"
        smoke.write_cli_config(config, user_root, temporary / "data", temporary / "downloads")
        libraries_root = temporary / "external-libraries"
        libraries_root.mkdir()
        for record in lock["libraries"]:
            content = download_archive(record["url"])
            digest = hashlib.sha256(content).hexdigest()
            if digest != record["sha256"]:
                raise ExternalArduinoFailure(
                    f"외부 archive SHA-256이 다릅니다: {record['name']}: {digest}"
                )
            extract_archive(content, libraries_root / record["directory"])
            properties = libraries_root / record["directory"] / "library.properties"
            metadata = properties.read_text(encoding="utf-8") if properties.is_file() else ""
            if f"name={record['name']}" not in metadata or f"version={record['version']}" not in metadata:
                raise ExternalArduinoFailure(f"외부 library metadata가 pin과 다릅니다: {record['name']}")
            library_evidence.append({key: record[key] for key in (
                "name", "version", "tag", "commit", "license", "url", "sha256"
            )})

        build = temporary / "build"
        exact_sketch = exact_source / SKETCH.relative_to(REPOSITORY)
        command = smoke.compile_command(cli, config, build, exact_sketch, libraries_root)
        command.insert(2, "--verbose")
        return_code, output = smoke.run(command, expect_success=False)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8", newline="\n")
        if return_code != 0:
            raise ExternalArduinoFailure(f"Adafruit LSM6DS compile이 실패했습니다: {return_code}")
        context = smoke.assert_build(build, exact_sketch.name + ".ino")
        selected = {
            item.get("id")
            for item in context.get("selected_features", [])
            if isinstance(item, dict)
        }
        required = {"nucode.wire", "nucode.spi"}
        if not required.issubset(selected):
            raise ExternalArduinoFailure(
                f"외부 sensor compile이 Wire/SPI feature를 기록하지 않았습니다: {sorted(selected)}"
            )

    if validate_exact_checkout(output_roots) != identity:
        raise ExternalArduinoFailure("compile 도중 exact Core 또는 board checkout이 변경됐습니다.")
    verify_arduino_cli_unchanged(cli, cli_identity)

    evidence = {
        "schema_version": 1,
        "gate": "m17-external-adafruit-lsm6ds-compile",
        "status": "passed",
        "support_declaration": "build-only",
        "hil": "not-run",
        "fqbn": FQBN,
        "arduino_cli": cli_identity,
        "core_revision": identity["core_revision"],
        "board_revision": identity["board_revision"],
        "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "libraries": library_evidence,
        "selected_features": sorted(required),
        "log": {
            "name": log_path.name,
            "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
        },
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(evidence_path, evidence)


## @brief command line entry point입니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args(arguments)
    cli = args.arduino_cli.resolve()
    if not cli.is_file():
        raise ExternalArduinoFailure("exact Arduino CLI executable이 없습니다.")
    evidence = args.evidence.resolve()
    log = args.log.resolve() if args.log else evidence.with_suffix(".log")
    run_gate(cli, args.lock.resolve(), evidence, log)
    print(f"M17_EXTERNAL_ARDUINO_PASS={evidence}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExternalArduinoFailure as error:
        print(f"M17_EXTERNAL_ARDUINO_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
