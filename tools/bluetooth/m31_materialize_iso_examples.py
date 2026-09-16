#!/usr/bin/env python3
"""! @brief 검증된 W02 target 앱을 설치 가능한 Arduino 역할 예제로 고정합니다. """

from __future__ import annotations

from pathlib import Path
import hashlib


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries" / "NUCODE_BLE_ISO"
CASES = (
    ("CISCentral", "CIS", 'M31_ISO_ROLE "central"', "m31_iso_cis_hil", ""),
    ("CISPeripheral", "CIS", 'M31_ISO_ROLE "peripheral"', "m31_iso_cis_hil", ""),
    ("BISSource", "BIS", 'M31_BIS_ROLE "source"', "m31_iso_bis_hil", "source"),
    ("BISReceiver", "BIS", 'M31_BIS_ROLE "receiver"', "m31_iso_bis_hil", "receiver"),
    ("BISEncryptedSource", "BIS", 'M31_BIS_ROLE "source"\nM31_BIS_ENCRYPTED', "m31_iso_bis_hil", "source"),
    ("BISEncryptedReceiver", "BIS", 'M31_BIS_ROLE "receiver"\nM31_BIS_ENCRYPTED', "m31_iso_bis_hil", "receiver"),
    ("BISTimeSource", "BIS", 'M31_BIS_ROLE "source"\nM31_BIS_TIME_SYNC', "m31_iso_bis_hil", "source"),
    ("BISTimeReceiver", "BIS", 'M31_BIS_ROLE "receiver"\nM31_BIS_TIME_SYNC', "m31_iso_bis_hil", "receiver"),
    ("CISToBISBridge", "Combined", "", "m31_iso_combined_hil", ""),
    ("CISToBISPeer", "CIS", 'M31_ISO_ROLE "peripheral"\nM31_ISO_COMBINED_PEER', "m31_iso_cis_hil", ""),
    ("CISToBISReceiver", "BIS", 'M31_BIS_ROLE "receiver"', "m31_iso_bis_hil", "receiver"),
)
HEADERS = {
    "CIS": "NUCODE_ISO_CIS_Program.h",
    "BIS": "NUCODE_ISO_BIS_Program.h",
    "Combined": "NUCODE_ISO_Combined_Program.h",
}
HEADER_PREFIX = b"#pragma once\n#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)\n"
HEADER_SUFFIX = b"\n#endif\n"


## @brief Arduino 탐색 가드 안의 기능 코드가 검증 source와 byte 동일한지 확인합니다.
def source_parity() -> dict[str, str]:
    values: dict[str, str] = {}
    for kind, target in (("CIS", "m31_iso_cis_hil"), ("BIS", "m31_iso_bis_hil"), ("Combined", "m31_iso_combined_hil")):
        source = ROOT / "tests" / "zephyr" / target / "src" / "main.cpp"
        header = LIBRARY / "src" / HEADERS[kind]
        source_bytes = source.read_bytes()
        original = source_bytes.replace(b"\r\n", b"\n")
        installed = HEADER_PREFIX + original + HEADER_SUFFIX
        if header.is_file() and header.read_bytes() not in (source_bytes, original, installed):
            raise ValueError(f"{header}와 검증 source의 bytes가 다릅니다")
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_bytes(installed)
        values[kind] = hashlib.sha256(original).hexdigest()
    return values


## @brief role별 compile-time 선택과 Kconfig를 예제 폴더에 생성합니다.
def materialize() -> dict[str, str]:
    values = source_parity()
    for name, kind, definitions, target, mode in CASES:
        sketch = LIBRARY / "examples" / name
        sketch.mkdir(parents=True, exist_ok=True)
        macro_lines = "\n".join(f"#define {line}" for line in definitions.splitlines())
        text = (
            "/**\n"
            f" * @file {name}.ino\n"
            f" * @brief NU54DK {name} 역할의 실제 raw ISO 경로를 실행합니다.\n"
            " * SPDX-License-Identifier: MIT\n"
            " */\n\n"
            + (macro_lines + "\n" if macro_lines else "")
            + f"#include <{HEADERS[kind]}>\n"
        )
        (sketch / f"{name}.ino").write_text(text, encoding="utf-8", newline="\n")
        native_conf = (ROOT / "tests" / "zephyr" / target / "prj.conf").read_text(encoding="utf-8")
        conf = "\n".join(
            line for line in native_conf.splitlines()
            if not (line.startswith("CONFIG_NUCODE_ARDUINO_") and line.endswith("=n"))
        ) + "\n"
        if mode:
            conf += "\n" + (ROOT / "tests" / "zephyr" / target / f"{mode}.conf").read_text(encoding="utf-8")
        (sketch / "prj.conf").write_text(conf, encoding="utf-8", newline="\n")
    return values


if __name__ == "__main__":
    for role, digest in materialize().items():
        print(f"M31_ISO_SOURCE_PARITY={role};SHA256={digest}")
    print(f"M31_ISO_ROLE_SKETCHES={len(CASES)}")
