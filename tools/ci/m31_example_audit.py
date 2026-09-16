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
ISO_BACKENDS = {
    "CIS": ("NUCODE_ISO_CIS_Impl.inc", "m31_iso_cis_hil"),
    "BIS": ("NUCODE_ISO_BIS_Impl.inc", "m31_iso_bis_hil"),
    "Combined": ("NUCODE_ISO_Combined_Impl.inc", "m31_iso_combined_hil"),
}
ISO_ROLE_BACKEND = {
    "CIS_CENTRAL": "CIS",
    "CIS_PERIPHERAL": "CIS",
    "CIS_TO_BIS_PEER": "CIS",
    "BIS_SOURCE": "BIS",
    "BIS_RECEIVER": "BIS",
    "BIS_ENCRYPTED_SOURCE": "BIS",
    "BIS_ENCRYPTED_RECEIVER": "BIS",
    "BIS_TIME_SOURCE": "BIS",
    "BIS_TIME_RECEIVER": "BIS",
    "CIS_TO_BIS_RECEIVER": "BIS",
    "CIS_TO_BIS_BRIDGE": "Combined",
}
BACKEND_PREFIX = b"#define NUCODE_BLE_ISO_LIBRARY_BACKEND\n"
MILESTONE_IDENTIFIER = re.compile(r"\bM[0-9]{2}[A-Za-z0-9_]*")
ZEPHYR_DIRECT_USE = re.compile(
    r"#\s*include\s*[<\"]zephyr/|\b(?:bt|k|device)_[A-Za-z0-9_]+\s*\("
)


## @brief 입출력 예제마다 직접 코드 또는 검증 source와 byte 동일한 backend를 확인합니다.
def inspect_sketch(library: Path, sketch: Path) -> dict[str, object]:
    text = sketch.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.DOTALL)
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
    if MILESTONE_IDENTIFIER.search(text):
        row["status"] = "PUBLIC_MILESTONE_IDENTIFIER"
        return row
    if ZEPHYR_DIRECT_USE.search(text):
        row["status"] = "PUBLIC_ZEPHYR_DIRECT_USE"
        return row
    if not has_setup or not has_loop or code_lines < 10:
        row["status"] = "PUBLIC_API_FLOW_MISSING"
        return row
    if library.name == "NUCODE_BLE_Audio":
        required = (
            "#include <NUCODE_BLE_Audio.h>", "Lc3Codec", ".begin(",
            ".encode(", ".decode(",
        )
        if any(token not in code for token in required):
            row["status"] = "PUBLIC_AUDIO_API_FLOW_MISSING"
        return row
    if library.name == "NUCODE_BLE_DirectionFinding":
        configuration = sketch.parent / "prj.conf"
        if sketch.parent.name == "ConnectedCteResponder":
            required = (
                "#include <NUCODE_BLE.h>",
                "#include <NUCODE_BLE_DirectionFinding.h>",
                "ConnectedResponder", "BLEDevice.onEventInfo(",
                ".begin(", ".start(", ".stop(",
            )
            option = "CONFIG_NUCODE_BLE_DF_RESPONDER=y"
        else:
            required = (
                "#include <NUCODE_BLE_DirectionFinding.h>",
                "Beacon", ".begin(", ".start(", ".stop(",
            )
            option = "CONFIG_NUCODE_BLE_DF_BEACON=y"
        if (any(token not in code for token in required) or not configuration.is_file() or
            option not in configuration.read_text(encoding="utf-8")):
            row["status"] = "PUBLIC_DF_API_FLOW_MISSING"
        return row
    if library.name != "NUCODE_BLE_ISO":
        return row
    included = re.findall(r"^#include\s*<([^>]+)>\s*$", text, flags=re.MULTILINE)
    if included.count("NUCODE_BLE_ISO.h") != 1:
        return row
    configuration = sketch.parent / "prj.conf"
    if not configuration.is_file():
        row["status"] = "ROLE_CONFIGURATION_MISSING"
        return row
    configuration_text = configuration.read_text(encoding="utf-8")
    selected_roles = [
        role for role in ISO_ROLE_BACKEND
        if f"CONFIG_NUCODE_BLE_ISO_MODE_{role}=y" in configuration_text
    ]
    if len(selected_roles) != 1 or "CONFIG_NUCODE_BLE_ISO=y" not in configuration_text:
        row["status"] = "ROLE_CONFIGURATION_INVALID"
        return row
    expected_role = selected_roles[0].lower()
    if (re.search(rf"\bProgram\s+\w+\s*\(\s*Role::{expected_role}\s*\)", code) is None or
        re.search(r"\b\w+\.begin\s*\(", code) is None or
        re.search(r"\b\w+\.poll\s*\(", code) is None):
        row["status"] = "PUBLIC_ISO_API_FLOW_MISSING"
        return row
    kind = ISO_ROLE_BACKEND[selected_roles[0]]
    backend_name, target = ISO_BACKENDS[kind]
    backend = library / "src" / "internal" / backend_name
    source = ROOT / "tests" / "zephyr" / target / "src" / "main.cpp"
    if not backend.is_file() or not source.is_file():
        return row
    source_bytes = source.read_bytes().replace(b"\r\n", b"\n")
    if backend.read_bytes() != BACKEND_PREFIX + source_bytes:
        row["status"] = "BACKEND_SOURCE_MISMATCH"
        return row
    if re.search(rb"\bvoid\s+setup\s*\(", source_bytes) is None or (
        re.search(rb"\bvoid\s+loop\s*\(", source_bytes) is None
    ):
        return row
    row["backend"] = {
        "path": backend.relative_to(ROOT).as_posix(),
        "verified_source": source.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    row["status"] = "VISIBLE_VERIFIED_BACKEND" if has_setup and has_loop else "VERIFIED_BACKEND"
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
    public_surface_issues = []
    for library in sorted((ROOT / "libraries").iterdir()):
        if not library.is_dir() or not (library / "library.properties").is_file():
            continue
        candidates = list((library / "examples").rglob("*.ino"))
        candidates.extend((library / "examples").glob("*.md"))
        public_headers = []
        for suffix in ("*.h", "*.hh", "*.hpp", "*.hxx"):
            public_headers.extend(
                candidate for candidate in (library / "src").rglob(suffix)
                if "internal" not in candidate.relative_to(library / "src").parts
            )
        candidates.extend(public_headers)
        candidates.append(library / "library.properties")
        for candidate in candidates:
            candidate_text = candidate.read_text(encoding="utf-8")
            if MILESTONE_IDENTIFIER.search(candidate_text) or (
                candidate in public_headers and ZEPHYR_DIRECT_USE.search(candidate_text)
            ):
                public_surface_issues.append(candidate.relative_to(ROOT).as_posix())
    issues = [
        library["library"] for library in rows if library["status"] != "HAS_EXAMPLES"
    ] + [
        str(example["path"]) for example in sketches
        if example["status"] not in ("VISIBLE_CODE", "VERIFIED_BACKEND", "VISIBLE_VERIFIED_BACKEND")
    ] + public_surface_issues
    issues = sorted(set(issues), key=str.casefold)
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
        "verified_backend_count": sum(
            example["status"] in ("VERIFIED_BACKEND", "VISIBLE_VERIFIED_BACKEND")
            for example in sketches
        ),
        "issues": issues,
        "public_surface_issues": public_surface_issues,
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
