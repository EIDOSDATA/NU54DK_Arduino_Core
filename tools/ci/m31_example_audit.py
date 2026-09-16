#!/usr/bin/env python3
"""! @brief 설치 라이브러리의 예제 누락과 include-only backend를 전수 점검합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
ISO_SOURCES = {
    "NUCODE_ISO_CIS_Program.h": "m31_iso_cis_hil",
    "NUCODE_ISO_BIS_Program.h": "m31_iso_bis_hil",
    "NUCODE_ISO_Combined_Program.h": "m31_iso_combined_hil",
}
HEADER_PREFIX = b"#pragma once\n#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)\n"
HEADER_SUFFIX = b"\n#endif\n"


## @brief 입출력 예제마다 직접 코드 또는 검증 source와 byte 동일한 backend를 확인합니다.
def inspect_sketch(library: Path, sketch: Path) -> dict[str, object]:
    text = sketch.read_text(encoding="utf-8")
    has_setup = re.search(r"\bvoid\s+setup\s*\(", text) is not None
    has_loop = re.search(r"\bvoid\s+loop\s*\(", text) is not None
    code_lines = sum(
        bool(line.strip()) and not line.lstrip().startswith(("//", "*", "/*", "*/"))
        for line in text.splitlines()
    )
    row: dict[str, object] = {
        "name": sketch.parent.name,
        "path": sketch.relative_to(ROOT).as_posix(),
        "sketch_code_lines": code_lines,
        "visible_setup_loop": has_setup and has_loop,
        "backend": None,
        "status": "VISIBLE_CODE" if has_setup and has_loop else "MISSING_ENTRYPOINT",
    }
    if has_setup and has_loop:
        return row
    if library.name != "NUCODE_BLE_ISO":
        return row
    included = re.findall(r"^#include\s*<([^>]+)>\s*$", text, flags=re.MULTILINE)
    matched = [name for name in included if name in ISO_SOURCES]
    if len(matched) != 1:
        return row
    header_name = matched[0]
    backend = library / "src" / header_name
    source = ROOT / "tests" / "zephyr" / ISO_SOURCES[header_name] / "src" / "main.cpp"
    if not backend.is_file() or not source.is_file():
        return row
    source_bytes = source.read_bytes().replace(b"\r\n", b"\n")
    if backend.read_bytes() != HEADER_PREFIX + source_bytes + HEADER_SUFFIX:
        row["status"] = "BACKEND_SOURCE_MISMATCH"
        return row
    if re.search(rb"\bvoid\s+setup\s*\(", source_bytes) is None or (
        re.search(rb"\bvoid\s+loop\s*\(", source_bytes) is None
    ):
        return row
    if not (sketch.parent / "prj.conf").is_file():
        row["status"] = "ROLE_CONFIGURATION_MISSING"
        return row
    row["backend"] = {
        "path": backend.relative_to(ROOT).as_posix(),
        "verified_source": source.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    row["status"] = "VERIFIED_BACKEND"
    return row


## @brief 설치 대상 library.properties의 전체 예제를 누락 없이 원장으로 만듭니다.
def audit() -> dict[str, object]:
    rows = []
    for library in sorted((ROOT / "libraries").iterdir()):
        if not library.is_dir() or not (library / "library.properties").is_file():
            continue
        sketches = sorted((library / "examples").glob("*/*.ino"))
        rows.append({
            "library": library.name,
            "examples": [inspect_sketch(library, sketch) for sketch in sketches],
            "status": "HAS_EXAMPLES" if sketches else "NO_EXAMPLES",
        })
    sketches = [example for library in rows for example in library["examples"]]
    issues = [
        library["library"] for library in rows if library["status"] != "HAS_EXAMPLES"
    ] + [
        str(example["path"]) for example in sketches
        if example["status"] not in ("VISIBLE_CODE", "VERIFIED_BACKEND")
    ]
    revision = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=ROOT, text=True
    ).strip()
    return {
        "schema_version": 1,
        "core_revision": revision,
        "source_clean": not bool(dirty),
        "library_count": len(rows),
        "example_count": len(sketches),
        "visible_code_count": sum(example["status"] == "VISIBLE_CODE" for example in sketches),
        "verified_backend_count": sum(example["status"] == "VERIFIED_BACKEND" for example in sketches),
        "issues": issues,
        "libraries": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    document = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"M31_EXAMPLE_AUDIT=LIBRARIES={document['library_count']};"
        f"EXAMPLES={document['example_count']};ISSUES={len(document['issues'])}"
    )
    if document["issues"]:
        print("M31_EXAMPLE_AUDIT_ISSUES=" + ",".join(document["issues"]), file=sys.stderr)
        raise SystemExit(1)
