#!/usr/bin/env python3
"""! @brief Git 변경을 RC2 Fast/Full build 영향 범주로 보수적으로 분류합니다. """

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
PROFILE_BY_LIBRARY = {
    "NUCODE_BLE": "ble",
    "NUCODE_BLE_Audio": "ble",
    "NUCODE_BLE_ChannelSounding": "ble",
    "NUCODE_BLE_DFU": "secure_ble_dfu",
    "NUCODE_BLE_DirectionFinding": "ble",
    "NUCODE_BLE_EATT": "ble",
    "NUCODE_BLE_ISO": "ble",
    "NUCODE_BLE_LegacySigning": "ble",
    "NUCODE_BLE_Security": "ble",
    "NUCODE_Peripheral_Fabric": "fabric",
}
ALL_PROFILES = (
    "standard",
    "ble",
    "adaptive",
    "fabric",
    "secure_ble_dfu",
    "ble_audio_io",
)


class ChangeClassifierFailure(RuntimeError):
    """! @brief Git 범위 또는 변경 경로가 안전하게 분류되지 않았음을 나타냅니다. """


## @brief Git diff에서 rename 양쪽을 포함한 변경 경로를 읽습니다.
def changed_paths(repository: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        (
            "git",
            "-C",
            str(repository),
            "diff",
            "--name-only",
            "--diff-filter=ACDMRTUXB",
            "-z",
            base,
            head,
            "--",
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ChangeClassifierFailure(
            "Git 변경 범위를 읽지 못했습니다: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    try:
        values = result.stdout.decode("utf-8", errors="strict").split("\0")
    except UnicodeDecodeError as error:
        raise ChangeClassifierFailure("Git 변경 경로가 UTF-8이 아닙니다") from error
    return sorted({value.replace("\\", "/") for value in values if value})


## @brief 경로 집합을 문서·계약·build 영향과 필요한 profile로 분류합니다.
def classify(paths: Sequence[str]) -> dict[str, object]:
    normalized = sorted({
        PurePosixPath(value[2:] if value.startswith("./") else value).as_posix()
        for value in paths
    })
    categories: set[str] = set()
    profiles: set[str] = set()
    affected_examples: set[str] = set()
    run_all_examples = False
    release_sensitive = False
    for value in normalized:
        parts = PurePosixPath(value).parts
        suffix = PurePosixPath(value).suffix.casefold()
        if value.startswith("00_Docs/") or value in {"README.md", "AGENTS.md"}:
            categories.add("documentation")
            continue
        if value.startswith(("tests/", "tools/ci/", ".github/workflows/")):
            categories.add("contract")
            if value.startswith("tests/arduino-cli/"):
                profiles.update(ALL_PROFILES)
            continue
        if value.startswith("board_package/") or value == ".gitmodules":
            categories.add("board")
            profiles.update(ALL_PROFILES)
            run_all_examples = True
            release_sensitive = True
            continue
        if value.startswith("variants/"):
            categories.add("profile")
            profiles.update(ALL_PROFILES)
            run_all_examples = True
            release_sensitive = True
            continue
        if value.startswith("cores/"):
            categories.add("core")
            profiles.update(ALL_PROFILES)
            run_all_examples = True
            release_sensitive = True
            continue
        if value.startswith("tools/nu54-builder/") or value in {"platform.txt", "boards.txt"}:
            categories.add("builder")
            profiles.update(ALL_PROFILES)
            run_all_examples = True
            release_sensitive = True
            continue
        if value.startswith("tools/release/") or value.startswith("package/"):
            categories.add("package")
            profiles.update(ALL_PROFILES)
            release_sensitive = True
            continue
        if len(parts) >= 2 and parts[0] == "libraries":
            library = parts[1]
            categories.add("library")
            profiles.add(PROFILE_BY_LIBRARY.get(library, "standard"))
            if "examples" in parts:
                position = parts.index("examples")
                if len(parts) > position + 1:
                    affected_examples.add(f"{library}/{parts[position + 1]}")
            else:
                run_all_examples = True
            release_sensitive = release_sensitive or suffix in {
                ".c", ".cc", ".cpp", ".h", ".hpp", ".json"
            }
            continue
        categories.add("unknown")
        profiles.update(ALL_PROFILES)
        run_all_examples = True
        release_sensitive = True
    docs_only = bool(normalized) and categories == {"documentation"}
    if not normalized:
        categories.add("none")
    return {
        "schema_version": 1,
        "paths": normalized,
        "categories": sorted(categories),
        "docs_only": docs_only,
        "run_contract": True,
        "run_six_profiles": bool(profiles) and not docs_only,
        "run_all_examples": run_all_examples,
        "release_sensitive": release_sensitive,
        "profiles": [profile for profile in ALL_PROFILES if profile in profiles],
        "affected_examples": sorted(affected_examples),
    }


## @brief GitHub output boolean과 JSON 결과를 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(arguments)
    if args.path and args.base:
        parser.error("--path와 --base를 함께 사용할 수 없습니다")
    if not args.path and not args.base:
        parser.error("--base 또는 하나 이상의 --path가 필요합니다")
    paths = args.path or changed_paths(args.repository.resolve(), args.base, args.head)
    result = classify(paths)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    if args.github_output is not None:
        lines = [
            f"docs_only={str(result['docs_only']).lower()}",
            f"run_six_profiles={str(result['run_six_profiles']).lower()}",
            f"run_all_examples={str(result['run_all_examples']).lower()}",
            f"release_sensitive={str(result['release_sensitive']).lower()}",
            "profiles=" + json.dumps(result["profiles"], separators=(",", ":")),
        ]
        with args.github_output.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ChangeClassifierFailure as error:
        print(f"RC2_CHANGE_CLASSIFIER_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
