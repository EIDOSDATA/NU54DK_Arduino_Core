#!/usr/bin/env python3
"""! @brief M12 NCS·Toolchain·보드 고정 계약을 검증합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
LOCK_PATH = Path(__file__).with_name("ncs-3.4.0.lock.json")
PINS_PATH = REPOSITORY / "tools" / "nu54-prerequisites" / "pins.json"
PACKAGE_MODULE = REPOSITORY / "packaging" / "boards-manager" / "nu54_package.py"


class LockFailure(RuntimeError):
    """! @brief 재현 build 고정 계약 위반을 나타냅니다. """


## @brief 중복 key를 거부하며 JSON object를 읽습니다.
def strict_json_object(path: Path) -> dict[str, Any]:
    ## @brief 같은 object 안의 중복 key를 즉시 거부합니다.
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise LockFailure(f"JSON key가 중복됩니다: {path}: {key}")
            document[key] = value
        return document

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LockFailure(f"고정 JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise LockFailure(f"고정 JSON 최상위 값이 object가 아닙니다: {path}")
    return document


## @brief Git repository의 exact HEAD를 소문자 40자리 SHA로 반환합니다.
def git_revision(path: Path) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(path), "rev-parse", "HEAD"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise LockFailure(f"Git revision을 읽지 못했습니다: {path}: {error}") from error
    revision = result.stdout.strip().lower()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise LockFailure(f"유효한 Git checkout이 아닙니다: {path}")
    return revision


## @brief Python source의 단순 문자열 상수를 exact 값으로 읽습니다.
def source_constant(source: str, name: str) -> str:
    match = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]+)"\s*$', source, re.MULTILINE)
    if match is None:
        raise LockFailure(f"package source에서 {name} 상수를 찾지 못했습니다.")
    return match.group(1)


## @brief lock 내용과 저장소의 기존 prerequisite·package 계약을 대조합니다.
def validate_lock(lock: dict[str, Any]) -> None:
    if lock.get("schema_version") != 1:
        raise LockFailure("지원하지 않는 M12 lock schema입니다.")
    ncs = lock.get("ncs")
    zephyr = lock.get("zephyr")
    board = lock.get("board")
    linux = lock.get("linux_toolchain_container")
    windows = lock.get("windows_toolchain")
    arduino_cli = lock.get("arduino_cli")
    if not all(
        isinstance(item, dict)
        for item in (ncs, zephyr, board, linux, windows, arduino_cli)
    ):
        raise LockFailure("M12 lock의 필수 object가 없습니다.")

    assert isinstance(ncs, dict)
    assert isinstance(zephyr, dict)
    assert isinstance(board, dict)
    assert isinstance(linux, dict)
    assert isinstance(windows, dict)
    assert isinstance(arduino_cli, dict)
    for label, revision in (
        ("NCS", ncs.get("revision")),
        ("Zephyr", zephyr.get("revision")),
        ("board", board.get("revision")),
    ):
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise LockFailure(f"{label} revision이 exact 40자리 SHA가 아닙니다.")
    digest = linux.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise LockFailure("Linux toolchain container digest가 exact SHA-256이 아닙니다.")
    if (
        linux.get("image") != "ghcr.io/nrfconnect/sdk-nrf-toolchain"
        or linux.get("tag") != "v3.4.0"
        or linux.get("platform") != "linux/amd64"
        or not re.fullmatch(r"[0-9a-f]{10}", str(linux.get("toolchain_id", "")))
    ):
        raise LockFailure("공식 Linux toolchain container identity가 유효하지 않습니다.")
    if (
        linux.get("distribution") != "external-not-redistributed"
        or linux.get("license_expression") != "NOASSERTION"
        or windows.get("distribution") != "external-not-redistributed"
        or windows.get("license_expression") != "NOASSERTION"
    ):
        raise LockFailure("외부 Toolchain은 재배포 또는 단일 license로 오표기할 수 없습니다.")
    if ncs.get("license_expression") != "LicenseRef-Nordic-5-Clause":
        raise LockFailure("NCS manifest repository license 표기가 고정 계약과 다릅니다.")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(arduino_cli.get("version", ""))):
        raise LockFailure("Arduino CLI version이 exact SemVer가 아닙니다.")

    pins = strict_json_object(PINS_PATH)
    expected_pairs = (
        (ncs.get("tag"), pins.get("ncs", {}).get("version"), "NCS version"),
        (ncs.get("revision"), pins.get("ncs", {}).get("revision"), "NCS revision"),
        (zephyr.get("revision"), pins.get("zephyr", {}).get("revision"), "Zephyr revision"),
        (windows.get("bundle_id"), pins.get("toolchain", {}).get("bundle_id"), "Windows toolchain"),
    )
    for actual, expected, label in expected_pairs:
        if actual != expected:
            raise LockFailure(f"{label}가 prerequisite pins와 다릅니다: {actual} != {expected}")

    try:
        package_source = PACKAGE_MODULE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LockFailure(f"package source를 읽지 못했습니다: {error}") from error
    for name, expected in (
        ("NCS_VERSION", str(ncs["tag"])),
        ("NCS_REVISION", str(ncs["revision"])),
        ("ZEPHYR_VERSION", str(zephyr["version"])),
        ("ZEPHYR_REVISION", str(zephyr["revision"])),
    ):
        if source_constant(package_source, name) != expected:
            raise LockFailure(f"{name}이 M12 lock과 다릅니다.")

    gitlink = subprocess.run(
        ("git", "-C", str(REPOSITORY), "ls-tree", "HEAD", "board_package/NU54DK_Zephyr_DTS"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    match = re.search(r"\b([0-9a-f]{40})\tboard_package/NU54DK_Zephyr_DTS$", gitlink.stdout)
    if gitlink.returncode != 0 or match is None or match.group(1) != board["revision"]:
        raise LockFailure("부모 저장소의 board gitlink가 M12 lock과 다릅니다.")


## @brief lock의 exact identity를 포함한 GitHub Actions cache key를 만듭니다.
def cache_keys(lock: dict[str, Any]) -> dict[str, str]:
    ncs = lock["ncs"]["revision"]
    zephyr = lock["zephyr"]["revision"]
    linux = lock["linux_toolchain_container"]
    windows = lock["windows_toolchain"]
    digest = linux["digest"].removeprefix("sha256:")
    return {
        "linux_cache_key": (
            f"ncs-linux-amd64-{ncs}-{zephyr}-tc-{linux['toolchain_id']}-img-{digest}"
        ),
        "windows_cache_key": (
            f"ncs-windows-x64-{ncs}-{zephyr}-tc-{windows['bundle_id']}"
        ),
    }


## @brief 선택한 NCS workspace가 lock의 exact source revision인지 검증합니다.
def validate_workspace(workspace: Path, lock: dict[str, Any]) -> None:
    expected = (
        (workspace / "nrf", lock["ncs"]["revision"], "NCS"),
        (workspace / "zephyr", lock["zephyr"]["revision"], "Zephyr"),
    )
    for path, revision, label in expected:
        actual = git_revision(path)
        if actual != revision:
            raise LockFailure(f"{label} workspace revision이 lock과 다릅니다: {actual}")


## @brief GitHub Actions output file에 cache key를 기록합니다.
def write_github_outputs(outputs: dict[str, str]) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    if not destination:
        raise LockFailure("--github-output을 사용했지만 GITHUB_OUTPUT이 없습니다.")
    with Path(destination).open("a", encoding="utf-8", newline="\n") as stream:
        for name, value in outputs.items():
            stream.write(f"{name}={value}\n")


## @brief CLI 인자를 해석하고 고정 계약 검증 결과를 출력합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(arguments)
    lock = strict_json_object(args.lock.resolve())
    validate_lock(lock)
    if args.workspace is not None:
        validate_workspace(args.workspace.resolve(), lock)
    outputs = cache_keys(lock)
    if args.github_output:
        write_github_outputs(outputs)
    evidence = {
        "lock_sha256": hashlib.sha256(args.lock.resolve().read_bytes()).hexdigest(),
        "ncs_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "container": (
            f"{lock['linux_toolchain_container']['image']}@"
            f"{lock['linux_toolchain_container']['digest']}"
        ),
        **outputs,
    }
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LockFailure as error:
        print(f"M12_LOCK_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
