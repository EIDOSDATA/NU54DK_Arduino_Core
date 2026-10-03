#!/usr/bin/env python3
"""! @brief exact profile HIL build 산출물에서 fail-closed record를 생성합니다. """
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from ble_pair_hil_common import git_revision

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "nucode-m33-profile-build-v1"
SOURCE_ROOTS = (ROOT / "libraries/NUCODE_BLE_Profiles", ROOT / "tests/zephyr/m33_profile_hil")
SOURCE_FILES = (ROOT / "libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp",)


def digest(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def owned_source_hashes() -> dict[str, str]:
    """! @brief W02가 소유하는 profile·fixture·공통 GATT source를 모두 열거합니다. """
    files = list(SOURCE_FILES)
    for source_root in SOURCE_ROOTS:
        files.extend(path for path in source_root.rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix not in (".pyc", ".pyo"))
    if any(not path.is_file() or not path.resolve().is_relative_to(ROOT) for path in files):
        raise ValueError("W02 owned source set is incomplete")
    names = [path.relative_to(ROOT).as_posix() for path in files]
    if len(names) != len(set(names)):
        raise ValueError("W02 owned source set contains duplicates")
    return {name: digest(ROOT / name) for name in sorted(names)}


def command_text(entry: dict) -> str:
    """! @brief compile_commands 항목을 비교 가능한 문자열로 만듭니다. """
    if isinstance(entry.get("command"), str):
        return entry["command"]
    arguments = entry.get("arguments")
    if isinstance(arguments, list) and all(isinstance(value, str) for value in arguments):
        return " ".join(arguments)
    raise ValueError("compile command text missing")


def has_quoted_define(command: str, name: str, value: str) -> bool:
    """! @brief shell quoting 차이를 허용하며 문자열 compile define을 확인합니다. """
    pattern = rf"(?:^|\s)-D{re.escape(name)}=\\?\"{re.escape(value)}\\?\"(?:\s|$)"
    return re.search(pattern, command) is not None


def validate_compile_identity(path: Path, family: str, role: str,
                              revision: str, root: Path = ROOT) -> str:
    """! @brief 실제 main.cpp compile command의 role/family/revision을 검증합니다. """
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("compile_commands root must be a list")
    wanted = (root / "tests/zephyr/m33_profile_hil/src/main.cpp").resolve()
    matches = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            continue
        if Path(entry["file"]).resolve() == wanted:
            matches.append(command_text(entry))
    if len(matches) != 1:
        raise ValueError("exact profile main.cpp compile command missing")
    command = matches[0]
    if (not has_quoted_define(command, "M33_PROFILE_ROLE", role)
            or not has_quoted_define(command, "M33_PROFILE_CORE_REVISION", revision)):
        raise ValueError("compiled role/revision mismatch")
    native = re.search(r"(?:^|\s)-DM33_PROFILE_NATIVE=1(?:\s|$)", command) is not None
    if native != (family == "native"):
        raise ValueError("compiled family mismatch")
    role_macros = {name: re.search(rf"(?:^|\s)-DM33_PROFILE_{name.upper()}=1(?:\s|$)", command) is not None
                   for name in ("server", "watcher")}
    expected = {"server": role == "server", "watcher": role == "watcher"}
    if role_macros != expected:
        raise ValueError("compiled role macro mismatch")
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def generate(args: argparse.Namespace) -> dict:
    """! @brief build tree를 검증한 뒤 새 디렉터리에 immutable 입력을 복사합니다. """
    build = args.build_dir.resolve()
    app = build / "m33_profile_hil"
    inputs = {
        "image": app / "zephyr/zephyr.hex",
        "elf": app / "zephyr/zephyr.elf",
        "config": app / "zephyr/.config",
        "sysbuild": build / "zephyr/.config",
        "compile_commands": app / "compile_commands.json",
        "build_info": build / "build_info.yml",
    }
    if any(not path.is_file() for path in inputs.values()):
        raise ValueError("complete profile sysbuild artifacts are required")
    if args.family == "native" and args.role == "watcher":
        raise ValueError("native watcher build is not a supported fixture")
    revision = git_revision(ROOT)
    command_sha256 = validate_compile_identity(
        inputs["compile_commands"], args.family, args.role, revision)
    config = inputs["config"].read_text(encoding="utf-8")
    sysbuild = inputs["sysbuild"].read_text(encoding="utf-8")
    if (not re.search(r"^CONFIG_SOC_NRF54L15_CPUAPP=y\r?$", config, re.MULTILINE)
            or re.findall(r"^(SB_CONFIG_FLPRCORE_\w+)=y\r?$", sysbuild, re.MULTILINE)
               != ["SB_CONFIG_FLPRCORE_NONE"]):
        raise ValueError("profile build target/sysbuild configuration mismatch")
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
                           capture_output=True, text=True, check=True).stdout
    if dirty and not args.development:
        raise ValueError("dirty source requires --development build record")
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError("new isolated build record directory required")
    sources = owned_source_hashes()
    latest_source_time = max((ROOT / name).stat().st_mtime_ns for name in sources)
    if inputs["image"].stat().st_mtime_ns < latest_source_time:
        raise ValueError("W02 source changed after the selected build")
    input_hashes = {key: digest(path) for key, path in inputs.items()}
    output.mkdir(parents=True)
    names = {"image": "image.hex", "elf": "image.elf", "config": "config.txt",
             "sysbuild": "sysbuild.txt", "compile_commands": "compile_commands.json",
             "build_info": "build_info.yml"}
    copied = {}
    for key, name in names.items():
        target = output / name
        shutil.copy2(inputs[key], target)
        copied[key] = {"path": str(target), "sha256": digest(target)}
        if copied[key]["sha256"] != input_hashes[key]:
            raise ValueError("build artifact changed while creating record: " + key)
    if owned_source_hashes() != sources:
        raise ValueError("W02 source changed while creating build record")
    record = {
        "schema": SCHEMA, "family": args.family, "role": args.role,
        "source_revision": revision, "development": bool(dirty),
        "sha256": copied["image"]["sha256"], "image": copied["image"]["path"],
        "owned_source_sha256": sources,
        "command_identity": {"sha256": command_sha256,
                             "compile_commands_sha256": copied["compile_commands"]["sha256"],
                             "build_info_sha256": copied["build_info"]["sha256"]},
        "artifacts": {key: copied[key] for key in ("elf", "config", "sysbuild")},
        "provenance": {key: copied[key] for key in ("compile_commands", "build_info")},
    }
    record_path = output / "build-record.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"status": "DEVELOPMENT_RECORD" if dirty else "PASS",
            "record": str(record_path), "record_sha256": digest(record_path),
            "image": copied["image"]}


def main() -> int:
    """! @brief exact build record 생성 CLI입니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=("standard", "native"), required=True)
    parser.add_argument("--role", choices=("server", "client", "watcher"), required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--development", action="store_true")
    try:
        result = generate(parser.parse_args())
    except (json.JSONDecodeError, OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print("M33 profile build record FAIL: " + str(error))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
