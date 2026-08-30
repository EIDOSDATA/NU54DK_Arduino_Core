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
SMOKE_PATH = REPOSITORY / "tests" / "arduino-cli" / "run_smoke.py"
SKETCH = (
    REPOSITORY
    / "tests"
    / "arduino-cli"
    / "m17_adafruit_lsm6ds_compile"
)
FQBN = "nucode:zephyr:nu54dk"
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
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ExternalArduinoFailure(f"외부 archive 경로가 안전하지 않습니다: {member.filename}")
        roots.add(path.parts[0])
        unix_mode = member.external_attr >> 16
        if unix_mode & 0o170000 == 0o120000:
            raise ExternalArduinoFailure(f"외부 archive symlink를 허용하지 않습니다: {member.filename}")
    if len(roots) != 1:
        raise ExternalArduinoFailure("외부 archive는 단일 root directory여야 합니다.")
    return next(iter(roots)), members


## @brief 검증된 ZIP bytes를 격리된 Arduino library directory에 풉니다.
def extract_archive(content: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root, members = safe_members(archive)
        for member in members:
            relative = PurePosixPath(member.filename).relative_to(root)
            if not relative.parts:
                continue
            target = destination.joinpath(*relative.parts)
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
    lock = load_lock(lock_path)
    smoke = load_smoke_module()
    lock_bytes = lock_path.read_bytes()
    library_evidence: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="nu54-m17-external-") as temporary_name:
        temporary = Path(temporary_name)
        user_root = temporary / "user"
        smoke.stage_platform(REPOSITORY, user_root)
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
        command = smoke.compile_command(cli, config, build, SKETCH, libraries_root)
        command.insert(2, "--verbose")
        return_code, output = smoke.run(command, expect_success=False)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8", newline="\n")
        if return_code != 0:
            raise ExternalArduinoFailure(f"Adafruit LSM6DS compile이 실패했습니다: {return_code}")
        context = smoke.assert_build(build, SKETCH.name + ".ino")
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

    evidence = {
        "schema_version": 1,
        "gate": "m17-external-adafruit-lsm6ds-compile",
        "status": "passed",
        "support_declaration": "build-only",
        "hil": "not-run",
        "fqbn": FQBN,
        "core_revision": git_revision(REPOSITORY),
        "board_revision": git_revision(REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"),
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
