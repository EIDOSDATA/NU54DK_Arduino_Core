#!/usr/bin/env python3
"""! @brief M17 외부 Adafruit library compile runner 계약을 검증합니다. """

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tools" / "ci" / "run_m17_external_arduino.py"
SPEC = importlib.util.spec_from_file_location("nu54_m17_external", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M17ExternalArduinoTests(unittest.TestCase):
    """! @brief 외부 archive pin과 안전한 압축 해제를 검증합니다. """

    def test_repository_lock_is_exact(self) -> None:
        """! @brief 저장소 lock이 승인한 세 tag·commit·SHA만 포함하는지 확인합니다. """
        document = MODULE.load_lock(MODULE.DEFAULT_LOCK)
        self.assertEqual(len(document["libraries"]), 3)
        self.assertEqual(
            {record["name"] for record in document["libraries"]},
            set(MODULE.EXPECTED_LIBRARIES),
        )

    def test_lock_rejects_changed_checksum_and_duplicate_key(self) -> None:
        """! @brief checksum 변경과 중복 JSON key를 fail-closed로 거부합니다. """
        original = json.loads(MODULE.DEFAULT_LOCK.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="nu54-m17-lock-") as temporary_name:
            path = Path(temporary_name) / "lock.json"
            original["libraries"][0]["sha256"] = "0" * 64
            path.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "exact allowlist"):
                MODULE.load_lock(path)
            path.write_text('{"schema_version":1,"schema_version":1,"libraries":[]}', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "중복 JSON key"):
                MODULE.load_lock(path)

    def test_safe_extract_accepts_single_root(self) -> None:
        """! @brief 정상 archive에서 root를 제거한 library tree만 생성합니다. """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("library-tag/library.properties", "name=Fixture\nversion=1.0.0\n")
            archive.writestr("library-tag/src/Fixture.cpp", "int fixture;\n")
        with tempfile.TemporaryDirectory(prefix="nu54-m17-zip-") as temporary_name:
            destination = Path(temporary_name) / "Fixture"
            MODULE.extract_archive(buffer.getvalue(), destination)
            self.assertTrue((destination / "library.properties").is_file())
            self.assertTrue((destination / "src" / "Fixture.cpp").is_file())

    def test_safe_extract_rejects_traversal(self) -> None:
        """! @brief 상위 경로를 쓰는 ZIP member를 거부합니다. """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("library-tag/../../escape.txt", "escape")
        with tempfile.TemporaryDirectory(prefix="nu54-m17-zip-") as temporary_name:
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "안전하지"):
                MODULE.extract_archive(buffer.getvalue(), Path(temporary_name) / "Fixture")

    def test_download_checksum_contract_matches_lock(self) -> None:
        """! @brief lock SHA가 64자리이며 evidence에 사용할 수 있는 digest인지 확인합니다. """
        document = MODULE.load_lock(MODULE.DEFAULT_LOCK)
        encoded = MODULE.DEFAULT_LOCK.read_bytes()
        self.assertRegex(hashlib.sha256(encoded).hexdigest(), r"^[0-9a-f]{64}$")
        for record in document["libraries"]:
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")

    def test_arduino_library_compatibility_contract_is_present(self) -> None:
        """! @brief 외부 Arduino library가 요구하는 macro, Print와 정수 GPIO overload를 고정합니다. """
        template = (
            REPOSITORY / "tools" / "nu54-builder" / "templates" / "zephyr-app" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        print_header = (REPOSITORY / "cores" / "arduino" / "Print.h").read_text(
            encoding="utf-8"
        )
        arduino_header = (REPOSITORY / "cores" / "arduino" / "Arduino.h").read_text(
            encoding="utf-8"
        )
        for definition in ("ARDUINO=10607", "ARDUINO_ARCH_ZEPHYR", "ARDUINO_NUCODE_NU54DK"):
            self.assertIn(definition, template)
        self.assertIn("#include <api/Print.h>", print_header)
        self.assertIn("using arduino::Print;", print_header)
        self.assertIn("using arduino::digitalWrite;", arduino_header)
        self.assertIn("using arduino::pinMode;", arduino_header)

    def test_compile_sketch_targets_lsm6ds3trc(self) -> None:
        """! @brief compile gate가 NU54DK 검증 대상 LSM6DS3TR-C를 직접 사용하는지 확인합니다. """
        sketch = (MODULE.SKETCH / "m17_adafruit_lsm6ds_compile.ino").read_text(
            encoding="utf-8"
        )
        self.assertIn("#include <Adafruit_LSM6DS3TRC.h>", sketch)
        self.assertIn("Adafruit_LSM6DS3TRC sensor;", sketch)


if __name__ == "__main__":
    unittest.main()
