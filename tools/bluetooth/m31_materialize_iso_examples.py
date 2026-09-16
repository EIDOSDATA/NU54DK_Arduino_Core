#!/usr/bin/env python3
"""! @brief 검증된 ISO target을 Arduino 공개 API backend와 역할 예제로 고정합니다. """

from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries" / "NUCODE_BLE_ISO"
CASES = (
    ("CISCentral", "cis_central", "CIS", "m31_iso_cis_hil", "", "CIS_CENTRAL"),
    ("CISPeripheral", "cis_peripheral", "CIS", "m31_iso_cis_hil", "", "CIS_PERIPHERAL"),
    ("BISSource", "bis_source", "BIS", "m31_iso_bis_hil", "source", "BIS_SOURCE"),
    ("BISReceiver", "bis_receiver", "BIS", "m31_iso_bis_hil", "receiver", "BIS_RECEIVER"),
    ("BISEncryptedSource", "bis_encrypted_source", "BIS", "m31_iso_bis_hil", "source", "BIS_ENCRYPTED_SOURCE"),
    ("BISEncryptedReceiver", "bis_encrypted_receiver", "BIS", "m31_iso_bis_hil", "receiver", "BIS_ENCRYPTED_RECEIVER"),
    ("BISTimeSource", "bis_time_source", "BIS", "m31_iso_bis_hil", "source", "BIS_TIME_SOURCE"),
    ("BISTimeReceiver", "bis_time_receiver", "BIS", "m31_iso_bis_hil", "receiver", "BIS_TIME_RECEIVER"),
    ("CISToBISBridge", "cis_to_bis_bridge", "Combined", "m31_iso_combined_hil", "", "CIS_TO_BIS_BRIDGE"),
    ("CISToBISPeer", "cis_to_bis_peer", "CIS", "m31_iso_cis_hil", "", "CIS_TO_BIS_PEER"),
    ("CISToBISReceiver", "cis_to_bis_receiver", "BIS", "m31_iso_bis_hil", "receiver", "CIS_TO_BIS_RECEIVER"),
)
BACKENDS = {
    "CIS": ("NUCODE_ISO_CIS_Impl.inc", "m31_iso_cis_hil"),
    "BIS": ("NUCODE_ISO_BIS_Impl.inc", "m31_iso_bis_hil"),
    "Combined": ("NUCODE_ISO_Combined_Impl.inc", "m31_iso_combined_hil"),
}
BACKEND_PREFIX = b"#define NUCODE_BLE_ISO_LIBRARY_BACKEND\n"
OLD_HEADERS = (
    "NUCODE_ISO_CIS_Program.h",
    "NUCODE_ISO_BIS_Program.h",
    "NUCODE_ISO_Combined_Program.h",
)


## @brief private backend가 검증 source와 byte 동일한지 확인한 뒤 갱신합니다.
def source_parity() -> dict[str, str]:
    values: dict[str, str] = {}
    internal = LIBRARY / "src" / "internal"
    internal.mkdir(parents=True, exist_ok=True)
    for kind, (backend_name, target) in BACKENDS.items():
        source = ROOT / "tests" / "zephyr" / target / "src" / "main.cpp"
        backend = internal / backend_name
        source_bytes = source.read_bytes().replace(b"\r\n", b"\n")
        installed = BACKEND_PREFIX + source_bytes
        if backend.is_file() and backend.read_bytes() != installed:
            relative = backend.relative_to(ROOT).as_posix()
            committed = subprocess.run(
                ("git", "show", f"HEAD:{relative}"), cwd=ROOT,
                capture_output=True, check=False,
            )
            if committed.returncode != 0 or backend.read_bytes() != committed.stdout:
                raise ValueError(f"{backend}와 검증 source의 bytes가 다릅니다")
        backend.write_bytes(installed)
        values[kind] = hashlib.sha256(source_bytes).hexdigest()
    for old_name in OLD_HEADERS:
        old_header = LIBRARY / "src" / old_name
        if old_header.exists():
            old_header.unlink()
    return values


## @brief 역할별 공개 API 호출과 Kconfig를 예제 폴더에 생성합니다.
def materialize() -> dict[str, str]:
    values = source_parity()
    for name, role, _kind, target, mode, config_role in CASES:
        sketch = LIBRARY / "examples" / name
        sketch.mkdir(parents=True, exist_ok=True)
        text = (
            "/**\n"
            f" * @file {name}.ino\n"
            f" * @brief NU54DK {name} 역할을 NUCODE BLE ISO API로 실행합니다.\n"
            " * SPDX-License-Identifier: MIT\n"
            " */\n\n"
            "#include <NUCODE_BLE_ISO.h>\n\n"
            "using nucode::ble::iso::Error;\n"
            "using nucode::ble::iso::Program;\n"
            "using nucode::ble::iso::Role;\n\n"
            f"Program isoProgram(Role::{role});\n"
            "bool isoReady = false;\n\n"
            "/** @brief 역할별 ISO 프로그램을 초기화합니다. */\n"
            "void setup()\n"
            "{\n"
            "    isoReady = isoProgram.begin() == Error::none;\n"
            "    if (!isoReady)\n"
            "    {\n"
            "        Serial.println(\"ISO initialization failed\");\n"
            "    }\n"
            "}\n\n"
            "/** @brief ISO callback 뒤의 main-thread 작업을 계속 처리합니다. */\n"
            "void loop()\n"
            "{\n"
            "    if (isoReady)\n"
            "    {\n"
            "        isoProgram.poll();\n"
            "    }\n"
            "    delay(1);\n"
            "}\n"
        )
        (sketch / f"{name}.ino").write_text(text, encoding="utf-8", newline="\n")
        native_conf = (ROOT / "tests" / "zephyr" / target / "prj.conf").read_text(encoding="utf-8")
        conf = "\n".join(
            line for line in native_conf.splitlines()
            if not (line.startswith("CONFIG_NUCODE_ARDUINO_") and line.endswith("=n"))
        ) + "\n"
        if mode:
            conf += "\n" + (ROOT / "tests" / "zephyr" / target / f"{mode}.conf").read_text(encoding="utf-8")
        conf += (
            "\nCONFIG_NUCODE_BLE_ISO=y\n"
            f"CONFIG_NUCODE_BLE_ISO_MODE_{config_role}=y\n"
        )
        (sketch / "prj.conf").write_text(conf, encoding="utf-8", newline="\n")
    return values


if __name__ == "__main__":
    for role, digest in materialize().items():
        print(f"M31_ISO_SOURCE_PARITY={role};SHA256={digest}")
    print(f"M31_ISO_ROLE_SKETCHES={len(CASES)}")
