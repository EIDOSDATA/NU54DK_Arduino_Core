#!/usr/bin/env python3
"""! @brief 동일 Windows PC에서 M22 RC2를 경로 격리해 수명주기 검증합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import shlex
import stat
import subprocess
import sys
import urllib.request
from typing import Any, Iterable, Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REPOSITORY = Path(__file__).resolve().parents[2]
VERSION = "0.3.0-rc.2"
PREVIOUS_VERSION = "0.2.0"
FQBN = "nucode:zephyr:nu54dk"
TAG = f"v{VERSION}"
RC_INDEX_FILENAME = "package_nucode_nu54dk_rc_index.json"
RC_INDEX_URL = (
    f"https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/{TAG}/"
    f"{RC_INDEX_FILENAME}"
)
STABLE_INDEX_URL = (
    "https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/"
    "package_nucode_nu54dk_index.json"
)
ARDUINO_CLI_VERSION = "1.5.1"
ARDUINO_CLI_COMMIT = "01f3d4f2b"
ARDUINO_CLI_SHA256 = "65daefba1423010575d0874275734cb4a917faf5293609f01e9db6ed1c1c7e79"
RUN_ID_RE = re.compile(r"^m22-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_LOG_BYTES = 32 * 1024 * 1024
MARKER_NAME = ".nu54-m22-cleanroom.json"
CLEANROOM_RUNNER_PATH = "tools/release/m22_cleanroom.py"
LAYOUT_KEYS = {
    "root", "profile", "local", "roaming", "temp", "data", "downloads",
    "sketchbook", "build", "cache", "logs", "bin", "ncs_base", "ncs",
    "toolchain", "state",
}
SCAFFOLD_KEYS = LAYOUT_KEYS - {"ncs", "toolchain"}


class CleanroomFailure(RuntimeError):
    """! @brief 격리 또는 증적 계약을 보장할 수 없는 오류입니다. """


## @brief 파일 SHA-256을 bounded streaming 방식으로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


## @brief Windows 경로 비교용 canonical key를 반환합니다.
def path_key(path: str | Path) -> str:
    return str(path).replace("\\", "/").rstrip("/").casefold()


## @brief path가 link·junction·기타 reparse point인지 판별합니다.
def is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as error:
        raise CleanroomFailure(f"경로 상태를 읽지 못했습니다: {path}: {error}") from error
    attributes = getattr(info, "st_file_attributes", 0)
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


## @brief 중복 key를 거부해 JSON object를 읽습니다.
def strict_json(path: Path) -> dict[str, Any]:
    if (
        not path.is_file()
        or is_reparse(path)
        or path.stat().st_size > MAX_JSON_BYTES
    ):
        raise CleanroomFailure(f"JSON이 없거나 안전한 regular file이 아닙니다: {path}")

    ## @brief 같은 object의 중복 key를 즉시 거부합니다.
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise CleanroomFailure(f"JSON key가 중복되었습니다: {key}")
            value[key] = item
        return value

    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CleanroomFailure(f"JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise CleanroomFailure(f"JSON 최상위 값이 object가 아닙니다: {path}")
    return document


## @brief JSON을 UTF-8 LF와 key 정렬 형식으로 원자 기록합니다.
def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


## @brief 외부 증적에 probe UID와 원래 사용자 경로가 남지 않게 치환합니다.
def redact_text(text: str, secrets_to_hide: Iterable[str] = ()) -> str:
    result = text
    for secret in sorted({item for item in secrets_to_hide if item}, key=len, reverse=True):
        result = result.replace(secret, "<redacted-probe-id>")
    result = re.sub(
        r"(?i)(?:[A-Z]:[\\/])Users[\\/][^\\/\s\"']+",
        r"C:\\Users\\<redacted-user>",
        result,
    )
    return result


## @brief run root의 고정 directory layout을 반환합니다.
def layout(run_root: Path) -> dict[str, Path]:
    profile = run_root / "profile"
    local = profile / "AppData" / "Local"
    return {
        "root": run_root,
        "profile": profile,
        "local": local,
        "roaming": profile / "AppData" / "Roaming",
        "temp": run_root / "temp",
        "data": run_root / "arduino-data",
        "downloads": run_root / "arduino-downloads",
        "sketchbook": run_root / "sketchbook",
        "build": run_root / "build",
        "cache": run_root / "cache",
        "logs": run_root / "logs",
        "bin": run_root / "bin",
        "ncs_base": profile / "ncs",
        "ncs": profile / "ncs" / "v3.4.0",
        "toolchain": profile / "ncs" / "toolchains" / "dcbdc366a1",
        "state": local / "NUCODE" / "NU54DK_Arduino_Core" / "prerequisites",
    }


## @brief clean-room 실행에 필요한 상위·작업 directory만 미리 생성합니다.
def prepare_layout(paths: dict[str, Path]) -> None:
    """! @brief Nordic 설치 대상 leaf는 설치기가 직접 생성하도록 비워 둡니다. """

    if set(paths) != LAYOUT_KEYS:
        raise CleanroomFailure("clean-room layout key allowlist가 변경되었습니다.")
    for name in sorted(SCAFFOLD_KEYS):
        paths[name].mkdir(parents=True, exist_ok=True)
    if paths["ncs"].exists() or paths["toolchain"].exists():
        raise CleanroomFailure("Nordic installer 소유 leaf가 설치 전에 존재합니다.")


## @brief 원래 PC 경로를 상속하지 않는 최소 Windows child 환경을 만듭니다.
def isolated_environment(
    run_root: Path, inherited: dict[str, str] | None = None
) -> dict[str, str]:
    source = dict(os.environ if inherited is None else inherited)
    paths = layout(run_root.resolve())
    windows = source.get("SystemRoot") or source.get("WINDIR") or r"C:\Windows"
    environment: dict[str, str] = {
        "OS": "Windows_NT",
        "SystemRoot": windows,
        "WINDIR": windows,
        "ComSpec": str(Path(windows) / "System32" / "cmd.exe"),
        "PATHEXT": source.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
        "PROCESSOR_ARCHITECTURE": source.get("PROCESSOR_ARCHITECTURE", "AMD64"),
        "NUMBER_OF_PROCESSORS": source.get("NUMBER_OF_PROCESSORS", "1"),
        "USERPROFILE": str(paths["profile"]),
        "HOME": str(paths["profile"]),
        "HOMEDRIVE": paths["profile"].drive or "C:",
        "HOMEPATH": str(paths["profile"])[2:] if paths["profile"].drive else str(paths["profile"]),
        "LOCALAPPDATA": str(paths["local"]),
        "APPDATA": str(paths["roaming"]),
        "TEMP": str(paths["temp"]),
        "TMP": str(paths["temp"]),
        "PATH": os.pathsep.join(
            (
                str(Path(windows) / "System32"),
                str(Path(windows)),
                str(Path(windows) / "System32" / "WindowsPowerShell" / "v1.0"),
            )
        ),
        "NUCODE_NCS_ROOT": str(paths["ncs"]),
        "NUCODE_TOOLCHAIN_ROOT": str(paths["toolchain"]),
        "NUCODE_PREREQUISITE_STATE_ROOT": str(paths["state"]),
        "NUCODE_BUILD_CACHE_ROOT": str(paths["cache"]),
        "ARDUINO_DIRECTORIES_DATA": str(paths["data"]),
        "ARDUINO_DIRECTORIES_DOWNLOADS": str(paths["downloads"]),
        "ARDUINO_DIRECTORIES_USER": str(paths["sketchbook"]),
        "PYTHONUTF8": "1",
    }
    return environment


## @brief 원래 PC에서 절대 참조하면 안 되는 SDK·Arduino·NUCODE 경로 목록을 만듭니다.
def forbidden_roots(
    inherited: dict[str, str], run_root: Path
) -> tuple[Path, ...]:
    candidates = [Path(r"C:\ncs")]
    for variable, suffix in (
        ("USERPROFILE", "ncs"),
        ("LOCALAPPDATA", "Arduino15"),
        ("LOCALAPPDATA", "NUCODE"),
    ):
        if inherited.get(variable):
            candidates.append(Path(inherited[variable]) / suffix)
    for variable in (
        "NUCODE_NCS_ROOT",
        "NUCODE_TOOLCHAIN_ROOT",
        "NUCODE_PREREQUISITE_STATE_ROOT",
        "NUCODE_BUILD_CACHE_ROOT",
    ):
        if inherited.get(variable):
            candidates.append(Path(inherited[variable]))
    result: list[Path] = []
    run_key = path_key(run_root.resolve())
    for candidate in candidates:
        absolute = candidate.absolute()
        key = path_key(absolute)
        if key and not key.startswith(run_key + "/") and key not in {path_key(item) for item in result}:
            result.append(absolute)
    return tuple(result)


## @brief 기존 경로의 작은 변경 감시 anchor를 수집합니다.
def leakage_anchors(roots: Sequence[Path]) -> dict[str, dict[str, Any]]:
    anchors: dict[str, dict[str, Any]] = {}
    suffixes = (
        Path("v3.4.0/zephyr/VERSION"),
        Path("toolchains/dcbdc366a1/environment.json"),
        Path("NU54DK_Arduino_Core/prerequisites/ready.json"),
    )
    for root in roots:
        root_key = path_key(root)
        if root.exists() and root.is_dir() and not is_reparse(root):
            digest = hashlib.sha256()
            count = 0
            pending = [root]
            while pending:
                directory = pending.pop()
                try:
                    entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
                except OSError as error:
                    raise CleanroomFailure(f"기존 경로 metadata를 읽지 못했습니다: {directory}") from error
                for entry in entries:
                    count += 1
                    if count > 500000:
                        raise CleanroomFailure(f"기존 경로 metadata 항목 상한을 초과했습니다: {root}")
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    info = entry.stat(follow_symlinks=False)
                    kind = "reparse" if is_reparse(path) else "dir" if entry.is_dir(follow_symlinks=False) else "file"
                    digest.update(
                        f"{relative}\0{kind}\0{info.st_size}\0{info.st_mtime_ns}\n".encode(
                            "utf-8", errors="surrogatepass"
                        )
                    )
                    if kind == "dir":
                        pending.append(path)
            anchors[root_key] = {
                "exists": True,
                "tree_entry_count": count,
                "tree_metadata_sha256": digest.hexdigest(),
            }
        elif root_key not in anchors:
            anchors[root_key] = {"exists": root.exists()}
        for candidate in (root, *(root / suffix for suffix in suffixes)):
            key = path_key(candidate)
            if key in anchors and candidate == root:
                continue
            exists = candidate.exists()
            record: dict[str, Any] = {"exists": exists}
            if exists and candidate.is_file() and not is_reparse(candidate):
                record.update({"size": candidate.stat().st_size, "sha256": file_sha256(candidate)})
            anchors[key] = record
    return anchors


## @brief 기존 PC anchor가 격리 실행 전후로 같음을 확인합니다.
def assert_anchors_unchanged(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> None:
    if before != after:
        changed = sorted(set(before) | set(after))
        changed = [name for name in changed if before.get(name) != after.get(name)]
        raise CleanroomFailure(f"기존 PC 경로 변경이 감지되었습니다: {changed}")


## @brief run root와 외부 evidence 경로의 분리 및 marker identity를 검증합니다.
def validate_cleanup_target(
    parent: Path,
    run_root: Path,
    run_id: str,
    token: str,
    evidence_path: Path,
) -> dict[str, Any]:
    named_parent = parent.absolute()
    named_run_root = run_root.absolute()
    if (
        not named_parent.is_dir()
        or not named_run_root.is_dir()
        or is_reparse(named_parent)
        or is_reparse(named_run_root)
    ):
        raise CleanroomFailure("cleanup의 명명 parent/run root에 reparse point가 있습니다.")
    parent = named_parent.resolve()
    run_root = named_run_root.resolve()
    evidence_path = evidence_path.resolve()
    if not RUN_ID_RE.fullmatch(run_id) or run_root.name != run_id:
        raise CleanroomFailure("cleanup run ID가 고정 형식과 다릅니다.")
    if run_root.parent != parent or run_root in {Path(run_root.anchor), parent}:
        raise CleanroomFailure("cleanup 대상은 지정 parent의 exact run leaf여야 합니다.")
    if not parent.is_dir() or not run_root.is_dir() or is_reparse(parent) or is_reparse(run_root):
        raise CleanroomFailure("cleanup parent/run root가 일반 directory가 아닙니다.")
    if evidence_path == run_root or evidence_path.is_relative_to(run_root):
        raise CleanroomFailure("증적은 cleanup run root 밖에 있어야 합니다.")
    marker_path = run_root / MARKER_NAME
    marker = strict_json(marker_path)
    if (
        marker.get("schema_version") != 1
        or marker.get("run_id") != run_id
        or marker.get("cleanup_token") != token
        or marker.get("status") != "ready-to-clean"
        or path_key(marker.get("evidence_path", "")) != path_key(evidence_path)
        or marker.get("evidence_sha256") != file_sha256(evidence_path)
    ):
        raise CleanroomFailure("cleanup marker 또는 외부 evidence identity가 다릅니다.")
    return marker


## @brief tree를 따라가지 않고 모든 descendant의 reparse point를 거부합니다.
def assert_tree_has_no_reparse(root: Path) -> None:
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            raise CleanroomFailure(f"cleanup tree를 열거하지 못했습니다: {directory}") from error
        for entry in entries:
            path = Path(entry.path)
            if is_reparse(path):
                raise CleanroomFailure(f"cleanup tree에 reparse point가 있습니다: {path}")
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)


## @brief 검증된 exact run leaf 하나만 삭제합니다.
def safe_cleanup_run(
    parent: Path,
    run_root: Path,
    run_id: str,
    token: str,
    evidence_path: Path,
) -> None:
    validate_cleanup_target(parent, run_root, run_id, token, evidence_path)
    assert_tree_has_no_reparse(run_root)
    try:
        shutil.rmtree(run_root)
    except OSError as error:
        raise CleanroomFailure("검증된 run leaf를 삭제하지 못했습니다.") from error
    if run_root.exists():
        raise CleanroomFailure("검증된 run leaf cleanup이 완료되지 않았습니다.")


## @brief Arduino CLI 설정을 모든 data/download/user 경로가 격리되도록 작성합니다.
def write_cli_config(path: Path, paths: dict[str, Path]) -> None:
    path.write_text(
        "board_manager:\n"
        "  additional_urls:\n"
        f"    - {STABLE_INDEX_URL}\n"
        f"    - {RC_INDEX_URL}\n"
        "directories:\n"
        f"  data: {paths['data'].as_posix()}\n"
        f"  downloads: {paths['downloads'].as_posix()}\n"
        f"  user: {paths['sketchbook'].as_posix()}\n"
        "logging:\n"
        "  level: info\n",
        encoding="utf-8",
        newline="\n",
    )


## @brief RC index의 exact version/archive URL/hash/size를 확인합니다.
def validate_rc_index(
    document: dict[str, Any], *, archive_sha256: str, archive_size: int
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for package in document.get("packages", []):
        if not isinstance(package, dict) or package.get("name") != "nucode":
            continue
        for platform in package.get("platforms", []):
            if isinstance(platform, dict) and platform.get("version") == VERSION:
                matches.append(platform)
    if len(matches) != 1:
        raise CleanroomFailure("공개 RC index에 exact 0.3.0-rc.2 platform이 하나가 아닙니다.")
    platform = matches[0]
    expected_url = (
        f"https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/{TAG}/"
        f"nucode-nu54dk-zephyr-{VERSION}.zip"
    )
    if (
        platform.get("url") != expected_url
        or str(platform.get("checksum", "")).casefold() != f"sha-256:{archive_sha256}"
        or platform.get("size") != str(archive_size)
    ):
        raise CleanroomFailure("RC index archive URL/hash/size가 release plan과 다릅니다.")
    return platform


## @brief 네트워크·filesystem 변경 없이 실제 실행의 고정 계약을 구성합니다.
def dry_run_contract(
    *,
    parent: Path,
    run_id: str,
    index_sha256: str,
    archive_sha256: str,
    archive_size: int,
) -> dict[str, Any]:
    if not RUN_ID_RE.fullmatch(run_id):
        raise CleanroomFailure("dry-run run ID 형식이 잘못되었습니다.")
    if not SHA256_RE.fullmatch(index_sha256) or not SHA256_RE.fullmatch(archive_sha256):
        raise CleanroomFailure("dry-run index/archive SHA-256 형식이 잘못되었습니다.")
    if archive_size < 1:
        raise CleanroomFailure("dry-run archive size가 잘못되었습니다.")
    run_root = parent.absolute() / run_id
    paths = layout(run_root)
    mutable_names = (
        "profile", "local", "roaming", "temp", "data", "downloads", "sketchbook",
        "build", "cache", "logs", "bin", "ncs_base", "ncs", "toolchain", "state",
    )
    if any(
        not path.absolute().is_relative_to(run_root.absolute())
        for name, path in paths.items()
        if name in mutable_names
    ):
        raise CleanroomFailure("dry-run mutable root가 exact run leaf 밖입니다.")
    return {
        "schema_version": 1,
        "milestone": "M22",
        "contract_type": "same-pc-cleanroom-dry-run",
        "release_version": VERSION,
        "public_index": {"url": RC_INDEX_URL, "sha256": index_sha256},
        "archive": {"sha256": archive_sha256, "size": archive_size},
        "isolation": {
            "all_mutable_roots_under_exact_run_leaf": True,
            "inherited_arduino15_ncs_nucode_forbidden": True,
            "environment_rebuilt_from_minimum_windows_allowlist": True,
        },
        "probe": {"selection": "explicit-exact-uid", "uid_recorded": False},
        "lifecycle": [
            "cli-identity",
            "public-index-exact-byte",
            "update-index",
            "fresh-rc-install",
            "installed-29-examples",
            "installed-blink-exact-uid-upload",
            "downgrade-stable",
            "upgrade-rc",
            "uninstall-preserves-isolated-ncs",
            "reinstall-rc",
            "reinstall-example-discovery",
            "existing-path-anchor-unchanged",
        ],
        "cleanup": {
            "only_after_pass": True,
            "external_evidence_required": True,
            "marker_and_hash_required": True,
            "reparse_scan_required": True,
            "target": "exact-run-leaf-only",
        },
        "network_or_filesystem_mutation_performed": False,
    }


## @brief child 명령을 shell 없이 실행하고 redacted log를 누적합니다.
def run_child(
    argv: Sequence[str | Path],
    *,
    environment: dict[str, str],
    log_path: Path,
    label: str,
    timeout: int,
    secrets_to_hide: Sequence[str],
) -> str:
    try:
        result = subprocess.run(
            [str(item) for item in argv],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CleanroomFailure(f"격리 child 명령이 완료되지 않았습니다: {label}") from error
    output = redact_text(
        result.stdout[-MAX_LOG_BYTES:].decode("utf-8", errors="replace"),
        secrets_to_hide,
    )
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"[{label}] return_code={result.returncode}\n{output}\n")
    if result.returncode != 0:
        raise CleanroomFailure(f"격리 child 명령이 실패했습니다: {label}")
    return output


## @brief core list JSON에서 설치된 nucode:zephyr exact version을 강제합니다.
def assert_core_version(output: str, expected: str | None) -> None:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise CleanroomFailure("Arduino CLI core list가 JSON이 아닙니다.") from error
    records = value.get("platforms") if isinstance(value, dict) else value
    if not isinstance(records, list):
        raise CleanroomFailure("Arduino CLI core list schema가 잘못되었습니다.")
    versions: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        identifier = record.get("id") or record.get("ID")
        if identifier == "nucode:zephyr":
            versions.append(
                str(
                    record.get("installed_version")
                    or record.get("InstalledVersion")
                    or record.get("installed")
                    or record.get("Installed")
                    or ""
                )
            )
    expected_versions = [] if expected is None else [expected]
    if versions != expected_versions:
        raise CleanroomFailure(
            f"설치 core version이 exact lifecycle과 다릅니다: {versions} != {expected_versions}"
        )


## @brief 설치본 pyOCD upload log의 exact UID와 비파괴 option을 검증합니다.
def validate_flash_log(
    path: Path, *, probe_id: str, hex_path: Path
) -> dict[str, Any]:
    if (
        not path.is_file()
        or path.is_symlink()
        or not 1 <= path.stat().st_size <= MAX_LOG_BYTES
    ):
        raise CleanroomFailure("설치본 pyOCD flash log가 없습니다.")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CleanroomFailure("설치본 pyOCD flash log를 읽지 못했습니다.") from error
    lines = text.splitlines()
    commands = [line.removeprefix("command=") for line in lines if line.startswith("command=")]
    probes = [line.removeprefix("probe_id=") for line in lines if line.startswith("probe_id=")]
    required = {
        "runner=pyocd",
        f"hex={hex_path.resolve().as_posix()}",
        f"hex_sha256={file_sha256(hex_path)}",
        "smart_flash=false",
        "mass_erase_requested=false",
        "recover_requested=false",
        "exit_code=0",
    }
    if len(commands) != 1 or probes != [probe_id] or any(lines.count(item) != 1 for item in required):
        raise CleanroomFailure("설치본 flash log의 runner/UID/HEX/비파괴 계약이 다릅니다.")
    try:
        tokens = shlex.split(commands[0], posix=True)
    except ValueError as error:
        raise CleanroomFailure("설치본 flash command quoting이 잘못되었습니다.") from error
    uid_positions = [index for index, token in enumerate(tokens) if token == "--dev-id"]
    if (
        tokens.count("flash") != 1
        or tokens.count("--no-rebuild") != 1
        or tokens.count("--tool-opt=-Osmart_flash=false") != 1
        or len(uid_positions) != 1
        or uid_positions[0] + 1 >= len(tokens)
        or tokens[uid_positions[0] + 1] != probe_id
        or any(re.fullmatch(r"(?i)--(?:erase|recover)(?:=.*)?", token) for token in tokens)
    ):
        raise CleanroomFailure("설치본 flash command의 exact UID/비파괴 option이 잘못되었습니다.")
    return {
        "runner": "pyocd",
        "probe_selection": "explicit-exact-uid",
        "probe_id_recorded": False,
        "smart_flash": False,
        "mass_erase_requested": False,
        "recover_requested": False,
        "flash_log_sha256": file_sha256(path),
    }


## @brief clean-room runner byte를 release commit과 plan에 결합합니다.
def validate_runner_binding(
    *,
    runner_revision: str,
    core_revision: str,
    runner_sha256: str,
    plan_sha256: str,
    runner_path: Path | None = None,
) -> dict[str, str]:
    """! @brief 실행 중인 runner 자체가 plan에 기록된 byte인지 fail-closed로 확인합니다. """

    path = Path(__file__).resolve() if runner_path is None else runner_path.resolve()
    if (
        not COMMIT_RE.fullmatch(runner_revision)
        or runner_revision != core_revision
        or not SHA256_RE.fullmatch(runner_sha256)
        or not SHA256_RE.fullmatch(plan_sha256)
        or not path.is_file()
        or path.is_symlink()
        or file_sha256(path) != runner_sha256
    ):
        raise CleanroomFailure("clean-room runner revision/hash/plan 결합이 잘못되었습니다.")
    return {
        "repository_relative_path": CLEANROOM_RUNNER_PATH,
        "revision": runner_revision,
        "sha256": runner_sha256,
        "plan_sha256": plan_sha256,
    }


## @brief same-PC clean-room의 설치·29예제·업로드·down/up/uninstall/reinstall을 실행합니다.
def run_cleanroom(args: argparse.Namespace) -> dict[str, Any]:
    if os.name != "nt":
        raise CleanroomFailure("M22 same-PC clean-room은 Windows에서만 실행합니다.")
    if not SHA256_RE.fullmatch(args.index_sha256) or not SHA256_RE.fullmatch(args.archive_sha256):
        raise CleanroomFailure("index/archive SHA-256 형식이 잘못되었습니다.")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", args.core_revision)
        or not re.fullmatch(r"[0-9a-f]{40}", args.board_revision)
        or not SHA256_RE.fullmatch(args.runtime_payload_sha256)
        or not SHA256_RE.fullmatch(args.release_manifest_sha256)
    ):
        raise CleanroomFailure("release source/runtime/manifest identity 형식이 잘못되었습니다.")
    if args.archive_size < 1 or not args.probe_id.strip():
        raise CleanroomFailure("archive size 또는 exact probe UID가 없습니다.")
    runner_identity = validate_runner_binding(
        runner_revision=args.runner_revision,
        core_revision=args.core_revision,
        runner_sha256=args.runner_sha256,
        plan_sha256=args.plan_sha256,
    )
    named_parent = args.parent.absolute()
    if named_parent.exists() and is_reparse(named_parent):
        raise CleanroomFailure("clean-room의 명명 parent에 reparse point를 허용하지 않습니다.")
    parent = named_parent.resolve()
    evidence_path = args.evidence.resolve()
    public_log = args.log.resolve()
    if evidence_path == public_log:
        raise CleanroomFailure("evidence와 log 경로는 분리해야 합니다.")
    run_id = args.run_id or (
        "m22-"
        + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + secrets.token_hex(4)
    )
    if not RUN_ID_RE.fullmatch(run_id):
        raise CleanroomFailure("run ID 형식이 잘못되었습니다.")
    source_cli = args.arduino_cli.resolve()
    if not source_cli.is_file() or source_cli.is_symlink() or file_sha256(source_cli) != ARDUINO_CLI_SHA256:
        raise CleanroomFailure("Arduino CLI executable이 M22 고정 hash와 다릅니다.")
    parent.mkdir(parents=True, exist_ok=True)
    if is_reparse(parent):
        raise CleanroomFailure("clean-room parent에 reparse point를 허용하지 않습니다.")
    run_root = parent / run_id
    if run_root.exists():
        raise CleanroomFailure("clean-room run leaf는 새 경로여야 합니다.")
    paths = layout(run_root)
    inherited = dict(os.environ)
    forbidden = forbidden_roots(inherited, run_root)
    anchors_before = leakage_anchors(forbidden)
    prepare_layout(paths)
    token = secrets.token_hex(32)
    environment = isolated_environment(run_root, inherited)
    private_log = paths["logs"] / "cleanroom.log"
    private_log.write_text("", encoding="utf-8")
    cli = paths["bin"] / "arduino-cli.exe"
    shutil.copy2(source_cli, cli)
    config = run_root / "arduino-cli.yaml"
    write_cli_config(config, paths)
    secrets_to_hide = (args.probe_id,)
    steps: list[dict[str, Any]] = []
    example_evidence: dict[str, Any] | None = None
    installed_release: dict[str, Any] | None = None
    upload_evidence: dict[str, Any] | None = None

    ## @brief 고정 단계 실행 결과를 증적 목록에 추가합니다.
    def step(label: str, argv: Sequence[str | Path], timeout: int) -> str:
        output = run_child(
            argv,
            environment=environment,
            log_path=private_log,
            label=label,
            timeout=timeout,
            secrets_to_hide=secrets_to_hide,
        )
        steps.append({"name": label, "status": "passed"})
        return output

    status = "failed"
    try:
        identity = step("cli-identity", (cli, "version", "--json"), 120)
        try:
            cli_json = json.loads(identity)
        except json.JSONDecodeError as error:
            raise CleanroomFailure("Arduino CLI identity가 JSON이 아닙니다.") from error
        if (
            cli_json.get("Application") != "arduino-cli"
            or cli_json.get("VersionString") != ARDUINO_CLI_VERSION
            or cli_json.get("Commit") != ARDUINO_CLI_COMMIT
        ):
            raise CleanroomFailure("Arduino CLI version/commit identity가 다릅니다.")
        downloaded_index = run_root / "downloaded-rc-index.json"
        try:
            with urllib.request.urlopen(RC_INDEX_URL, timeout=120) as response:
                data = response.read(MAX_JSON_BYTES + 1)
        except Exception as error:
            raise CleanroomFailure("공개 RC index 다운로드가 실패했습니다.") from error
        if len(data) > MAX_JSON_BYTES or hashlib.sha256(data).hexdigest() != args.index_sha256:
            raise CleanroomFailure("공개 RC index byte가 기대 hash와 다릅니다.")
        downloaded_index.write_bytes(data)
        validate_rc_index(
            strict_json(downloaded_index),
            archive_sha256=args.archive_sha256,
            archive_size=args.archive_size,
        )
        steps.append({"name": "public-index-exact-byte", "status": "passed"})
        step("update-index", (cli, "--config-file", config, "core", "update-index"), 900)
        cached_indexes = [
            path
            for path in paths["data"].rglob(RC_INDEX_FILENAME)
            if path.is_file() and not is_reparse(path)
        ]
        if len(cached_indexes) != 1 or file_sha256(cached_indexes[0]) != args.index_sha256:
            raise CleanroomFailure("Arduino CLI cached RC index가 공개 exact byte와 다릅니다.")
        steps.append({"name": "cached-index-exact-byte", "status": "passed"})

        ## @brief 지정 version을 설치하고 exact core list로 확인합니다.
        def install(version: str, label: str) -> None:
            step(
                label,
                (
                    cli,
                    "--config-file",
                    config,
                    "core",
                    "install",
                    f"nucode:zephyr@{version}",
                    "--run-post-install",
                ),
                args.install_timeout,
            )
            listed = step(
                f"{label}-list", (cli, "--config-file", config, "core", "list", "--json"), 120
            )
            assert_core_version(listed, version)

        install(VERSION, "fresh-rc-install")
        platform = paths["data"] / "packages" / "nucode" / "hardware" / "zephyr" / VERSION
        if not platform.is_dir() or not platform.resolve().is_relative_to(run_root.resolve()):
            raise CleanroomFailure("RC platform이 격리 data root에 설치되지 않았습니다.")
        release_manifest_path = platform / "release-manifest.json"
        installed_release = strict_json(release_manifest_path)
        if (
            file_sha256(release_manifest_path) != args.release_manifest_sha256
            or installed_release.get("version") != VERSION
            or installed_release.get("core_revision") != args.core_revision
            or installed_release.get("board_revision") != args.board_revision
            or installed_release.get("runtime_payload_sha256") != args.runtime_payload_sha256
        ):
            raise CleanroomFailure("설치 RC release manifest가 plan exact identity와 다릅니다.")
        ready = strict_json(paths["state"] / "ready.json")
        if (
            ready.get("status") != "ready"
            or path_key(ready.get("ncs_root", "")) != path_key(paths["ncs_base"])
            or path_key(ready.get("toolchain_root", "")) != path_key(paths["toolchain"])
            or ready.get("ncs_version") != "v3.4.0"
            or ready.get("toolchain_bundle_id") != "dcbdc366a1"
        ):
            raise CleanroomFailure("Nordic ready marker가 격리 NCS/toolchain root와 다릅니다.")
        steps.append({"name": "installed-release-exact-identity", "status": "passed"})
        detail_examples = run_root / "m22-package-examples.json"
        example_argv: list[str | Path] = [
            Path(sys.executable).resolve(),
            REPOSITORY / "tools" / "release" / "run_m22_package_examples.py",
            "--arduino-cli",
            cli,
            "--config",
            config,
            "--platform-root",
            platform,
            "--build-root",
            paths["build"] / "examples",
            "--ncs-root",
            paths["ncs"],
            "--toolchain-root",
            paths["toolchain"],
            "--cache-root",
            paths["cache"],
            "--evidence",
            detail_examples,
        ]
        for root in forbidden:
            example_argv.extend(("--forbid-root", root))
        step("installed-29-examples", example_argv, args.examples_timeout)
        example_evidence = strict_json(detail_examples)
        if example_evidence.get("status") != "passed" or example_evidence.get("compiled_count") != 29:
            raise CleanroomFailure("설치본 29개 예제 evidence가 PASS가 아닙니다.")

        blink = platform / "libraries" / "NUCODE_NU54DK" / "examples" / "Blink"
        upload_build = paths["build"] / "installed-blink-upload"
        step(
            "installed-blink-compile",
            (
                cli,
                "--config-file",
                config,
                "compile",
                "--clean",
                "--fqbn",
                FQBN,
                "--board-options",
                "feature_set=standard",
                "--board-options",
                "upload_probe=pyocd_uid",
                "--build-path",
                upload_build,
                blink,
            ),
            args.compile_timeout,
        )
        upload_output = step(
            "installed-blink-exact-uid-upload",
            (
                cli,
                "--config-file",
                config,
                "upload",
                "--fqbn",
                FQBN,
                "--board-options",
                "feature_set=standard",
                "--board-options",
                "upload_probe=pyocd_uid",
                "--upload-field",
                f"probe_id={args.probe_id}",
                "--build-path",
                upload_build,
                blink,
            ),
            args.upload_timeout,
        )
        if "NU54_UPLOAD_PASS runner=pyocd" not in upload_output:
            raise CleanroomFailure("설치본 exact UID pyOCD upload PASS marker가 없습니다.")
        manifests = list(upload_build.glob("*.nu54-build.json"))
        hex_files = list(upload_build.glob("*.hex"))
        flash_log = upload_build / "nu54-zephyr" / "logs" / "flash.log"
        if len(manifests) != 1 or len(hex_files) != 1 or not flash_log.is_file():
            raise CleanroomFailure("설치본 upload manifest/HEX/flash log가 정확히 하나가 아닙니다.")
        upload_manifest = strict_json(manifests[0])
        context = upload_manifest.get("context", {})
        if (
            context.get("profile") != "standard"
            or path_key(context.get("platform_root", "")) != path_key(platform)
            or path_key(context.get("ncs_root", "")) != path_key(paths["ncs"])
            or path_key(context.get("toolchain_root", "")) != path_key(paths["toolchain"])
            or path_key(context.get("cache_root", "")) != path_key(paths["cache"])
        ):
            raise CleanroomFailure("설치본 upload manifest에 격리 root 누출이 있습니다.")
        upload_evidence = {
            **validate_flash_log(
                flash_log, probe_id=args.probe_id, hex_path=hex_files[0]
            ),
            "manifest_sha256": file_sha256(manifests[0]),
            "hex_sha256": file_sha256(hex_files[0]),
        }

        install(PREVIOUS_VERSION, "downgrade-stable")
        install(VERSION, "upgrade-rc")
        ready = paths["state"] / "ready.json"
        ncs_anchor = paths["ncs"] / "zephyr" / "VERSION"
        if not ready.is_file() or not ncs_anchor.is_file():
            raise CleanroomFailure("uninstall 보존 검증 anchor가 없습니다.")
        preservation = {str(path): file_sha256(path) for path in (ready, ncs_anchor)}
        step("uninstall-rc", (cli, "--config-file", config, "core", "uninstall", "nucode:zephyr"), 900)
        listed = step("uninstall-list", (cli, "--config-file", config, "core", "list", "--json"), 120)
        assert_core_version(listed, None)
        if any(not Path(name).is_file() or file_sha256(Path(name)) != digest for name, digest in preservation.items()):
            raise CleanroomFailure("core uninstall이 격리 NCS 또는 ready marker를 변경했습니다.")
        install(VERSION, "reinstall-rc")
        final_listing = step(
            "reinstall-example-discovery",
            (cli, "--config-file", config, "lib", "examples", "--fqbn", FQBN, "--json"),
            120,
        )
        try:
            final_examples = json.loads(final_listing).get("examples", [])
        except (json.JSONDecodeError, AttributeError) as error:
            raise CleanroomFailure("reinstall example discovery가 JSON object가 아닙니다.") from error
        if len(final_examples) < 1:
            raise CleanroomFailure("reinstall 뒤 library example discovery가 비었습니다.")
        anchors_after = leakage_anchors(forbidden)
        assert_anchors_unchanged(anchors_before, anchors_after)
        private_text = private_log.read_text(encoding="utf-8")
        if args.probe_id in private_text:
            raise CleanroomFailure("redacted log에 probe UID가 남았습니다.")
        status = "passed"
    except Exception:
        anchors_after = leakage_anchors(forbidden)
        if anchors_before != anchors_after:
            steps.append({"name": "existing-path-leakage", "status": "failed"})
        raise
    finally:
        public_log.parent.mkdir(parents=True, exist_ok=True)
        if private_log.exists():
            public_log.write_text(
                redact_text(private_log.read_text(encoding="utf-8"), secrets_to_hide),
                encoding="utf-8",
                newline="\n",
            )
        evidence = {
            "schema_version": 1,
            "milestone": "M22",
            "evidence_type": "same-pc-isolated-cleanroom",
            "status": status,
            "release_version": VERSION,
            "public_index": {"url": RC_INDEX_URL, "sha256": args.index_sha256},
            "archive": {"sha256": args.archive_sha256, "size": args.archive_size},
            "arduino_cli": {
                "version": ARDUINO_CLI_VERSION,
                "commit": ARDUINO_CLI_COMMIT,
                "sha256": ARDUINO_CLI_SHA256,
            },
            "runner": runner_identity,
            "isolation": {
                "all_mutable_roots_under_run_leaf": True,
                "existing_path_leakage": False if status == "passed" else None,
                "probe_id_recorded": False,
                "forbidden_root_count": len(forbidden),
            },
            "lifecycle": steps,
            "installed_release": {
                "core_revision": installed_release.get("core_revision"),
                "board_revision": installed_release.get("board_revision"),
                "runtime_payload_sha256": installed_release.get("runtime_payload_sha256"),
                "manifest_sha256": args.release_manifest_sha256,
            } if installed_release else None,
            "installed_package_examples": example_evidence,
            "installed_upload": upload_evidence,
            "log": {
                "file_name": public_log.name,
                "sha256": file_sha256(public_log) if public_log.is_file() else None,
                "redacted": True,
            },
            "cleanup": {"status": "pending" if status == "passed" else "preserved-for-failure"},
            "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        write_json(evidence_path, evidence)

    marker = {
        "schema_version": 1,
        "run_id": run_id,
        "cleanup_token": token,
        "status": "ready-to-clean",
        "evidence_path": str(evidence_path),
        "evidence_sha256": file_sha256(evidence_path),
    }
    write_json(run_root / MARKER_NAME, marker)
    safe_cleanup_run(parent, run_root, run_id, token, evidence_path)
    evidence["cleanup"] = {
        "status": "passed",
        "exact_run_leaf_removed": True,
        "external_evidence_preserved": True,
        "reparse_scan_passed": True,
        "marker_verified": True,
    }
    write_json(evidence_path, evidence)
    return evidence


## @brief 실제 공개 RC URL만 받는 clean-room parser를 구성합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M22 same-PC isolated Windows clean-room")
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--index-url", choices=(RC_INDEX_URL,), default=RC_INDEX_URL)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--archive-size", type=int, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--board-revision", required=True)
    parser.add_argument("--runtime-payload-sha256", required=True)
    parser.add_argument("--release-manifest-sha256", required=True)
    parser.add_argument("--runner-revision", required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--parent", type=Path, default=Path(r"C:\NU54CI\M22"))
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--install-timeout", type=int, default=14400)
    parser.add_argument("--examples-timeout", type=int, default=21600)
    parser.add_argument("--compile-timeout", type=int, default=3600)
    parser.add_argument("--upload-timeout", type=int, default=600)
    return parser


## @brief clean-room 진입점입니다.
def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if any(
            not 1 <= value <= 86400
            for value in (
                args.install_timeout,
                args.examples_timeout,
                args.compile_timeout,
                args.upload_timeout,
            )
        ):
            raise CleanroomFailure("timeout 범위가 잘못되었습니다.")
        if args.dry_run:
            run_id = args.run_id or "m22-20990101T000000Z-00000000"
            contract = dry_run_contract(
                parent=args.parent,
                run_id=run_id,
                index_sha256=args.index_sha256,
                archive_sha256=args.archive_sha256,
                archive_size=args.archive_size,
            )
            print(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            run_cleanroom(args)
        return 0
    except CleanroomFailure as error:
        print(f"M22_CLEANROOM_FAIL: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(
            f"M22_CLEANROOM_FAIL: 예상하지 못한 내부 오류({type(error).__name__})",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
