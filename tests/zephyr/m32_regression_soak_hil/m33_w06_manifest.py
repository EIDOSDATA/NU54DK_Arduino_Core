#!/usr/bin/env python3
"""! @brief M33 W06 build source manifest와 CMake 변수를 하나의 규칙으로 생성합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


BUILD_SUFFIXES = frozenset({
    ".asm", ".c", ".cc", ".cmake", ".conf", ".cpp", ".cxx", ".dts", ".dtsi",
    ".h", ".hh", ".hpp", ".impl", ".inc", ".inl", ".ld", ".overlay", ".s",
    ".py", ".yaml", ".yml",
})
MANIFEST_FIELDS = (
    "core_revision", "board_revision", "ncs_revision", "zephyr_revision",
    "core_source_sha256", "application_source_sha256", "board_source_sha256",
    "firmware_source_sha256", "application_cmake_sha256",
    "application_config_sha256",
)
REVISION = re.compile(r"[0-9a-f]{40}\Z")
ROLE = re.compile(r"(?:peripheral|mixed|central)\Z")


def file_sha256(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_build_input(path: Path) -> bool:
    """! @brief firmware 생성에 영향을 주는 파일만 선택합니다. """
    name = path.name.casefold()
    return (name in ("cmakelists.txt", "library.properties", "platform.txt", "kconfig") or
            name.startswith("kconfig.") or path.suffix.casefold() in BUILD_SUFFIXES)


def source_files(base: Path, scopes: tuple[Path, ...]) -> tuple[Path, ...]:
    """! @brief path/hash manifest에 포함할 파일을 고정 순서로 나열합니다. """
    files = []
    for scope in scopes:
        if scope.is_file() and is_build_input(scope):
            files.append(scope.resolve())
        elif scope.is_dir():
            files.extend(path.resolve() for path in scope.rglob("*")
                         if path.is_file() and is_build_input(path))
    result = tuple(sorted(set(files), key=lambda path: path.relative_to(base).as_posix()))
    if not result:
        raise ValueError(f"source digest input empty: {base}")
    return result


def source_files_digest(base: Path, scopes: tuple[Path, ...]) -> str:
    """! @brief 정렬된 relative-path:file-hash 직렬화의 digest를 계산합니다. """
    value = "".join(
        f"{path.relative_to(base).as_posix()}:{file_sha256(path)}\n"
        for path in source_files(base, scopes)
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def current_source_digests(core: Path, board: Path, application: Path,
                           application_additional: tuple[Path, ...] = ()) -> dict[str, str]:
    """! @brief CMake과 Host validator가 공유하는 세 source tree digest입니다. """
    core_scopes = tuple(core / value for value in (
        "cores/arduino", "dts", "libraries", "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml", "platform.txt", "variants/nu54dk",
        "zephyr",
    ))
    board_scope = board / "boards/nucode/nu54dk"
    application_base = application.parent if application_additional else application
    return {
        "core_source_sha256": source_files_digest(core, core_scopes),
        "application_source_sha256": source_files_digest(
            application_base, (application, *application_additional)
        ),
        "board_source_sha256": source_files_digest(board, (board_scope,)),
    }


def generate_record(core: Path, board: Path, application: Path, firmware: Path,
                    revisions: dict[str, str], role: str) -> dict[str, object]:
    """! @brief source digest와 full revision을 같은 원본 record에 결합합니다. """
    if set(revisions) != {"core", "board", "ncs", "zephyr"} or not all(
            REVISION.fullmatch(value) for value in revisions.values()):
        raise ValueError("full source revisions required")
    if ROLE.fullmatch(role) is None:
        raise ValueError("invalid W06 role")
    manifest = {
        "core_revision": revisions["core"],
        "board_revision": revisions["board"],
        "ncs_revision": revisions["ncs"],
        "zephyr_revision": revisions["zephyr"],
        **current_source_digests(core, board, application),
        "firmware_source_sha256": file_sha256(firmware),
        "application_cmake_sha256": file_sha256(application / "CMakeLists.txt"),
        "application_config_sha256": file_sha256(application / "prj.conf"),
    }
    encoded = "\n".join(f"{key}={manifest[key]}" for key in MANIFEST_FIELDS)
    manifest["source_manifest_sha256"] = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    return {"schema_version": 1, "kind": "m33-w06-original-build-record",
            "role": role, **manifest}


def write_outputs(record: dict[str, object], json_output: Path,
                  cmake_output: Path) -> None:
    """! @brief JSON build record와 compile definition용 CMake 변수를 동시에 씁니다. """
    json_output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    lines = []
    for field in (*MANIFEST_FIELDS, "source_manifest_sha256"):
        variable = "M32_W11_" + field.upper()
        lines.append(f'set({variable} "{record[field]}")')
    cmake_output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """! @brief CMake configure에서 호출할 manifest generator 진입점입니다. """
    parser = argparse.ArgumentParser()
    for value in ("core", "board", "application", "firmware", "json-output",
                  "cmake-output"):
        parser.add_argument(f"--{value}", required=True, type=Path)
    for value in ("core-revision", "board-revision", "ncs-revision", "zephyr-revision",
                  "role"):
        parser.add_argument(f"--{value}", required=True)
    args = parser.parse_args()
    record = generate_record(
        args.core.resolve(), args.board.resolve(), args.application.resolve(),
        args.firmware.resolve(),
        {name: getattr(args, f"{name}_revision")
         for name in ("core", "board", "ncs", "zephyr")},
        args.role,
    )
    write_outputs(record, args.json_output.resolve(), args.cmake_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
