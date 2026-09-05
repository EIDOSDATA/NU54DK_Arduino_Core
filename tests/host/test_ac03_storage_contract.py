#!/usr/bin/env python3
"""! @brief AC-03 loaderless partition, EEPROM, LittleFS 공개 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
SPEC = importlib.util.spec_from_file_location("nu54_builder_ac03", BUILDER_PATH)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class AC03StorageContractTests(unittest.TestCase):
    """! @brief AC-03 production 입력의 fail-closed 정적 계약입니다. """

    def test_partition_is_common_exact_and_non_overlapping(self) -> None:
        """! @brief 두 profile이 같은 loaderless flash 분할과 linker 설정을 포함하는지 검증합니다. """

        partition = ROOT / "dts" / "nucode" / "nu54dk-arduino-storage.dtsi"
        source = partition.read_text(encoding="utf-8")
        expected = {
            "slot0_partition": (0x000000, 0x16C000),
            "arduino_fs_partition": (0x16C000, 0x008000),
            "storage_partition": (0x174000, 0x009000),
        }
        actual: dict[str, tuple[int, int]] = {}
        for label, address, size in re.findall(
            r"(\w+):\s+partition@[0-9a-f]+\s*\{.*?reg\s*=\s*"
            r"<0x([0-9a-f]+)\s+0x([0-9a-f]+)>;",
            source,
            re.DOTALL,
        ):
            actual[label] = (int(address, 16), int(size, 16))
        self.assertEqual(actual, expected)
        ordered = sorted(actual.values())
        for previous, current in zip(ordered, ordered[1:]):
            self.assertLessEqual(previous[0] + previous[1], current[0])
        self.assertEqual(actual["slot0_partition"], (0, 1456 * 1024))
        self.assertEqual(actual["arduino_fs_partition"][0] + actual["arduino_fs_partition"][1], 0x174000)
        self.assertEqual(actual["storage_partition"], (0x174000, 0x9000))
        self.assertEqual(actual["storage_partition"][0] + actual["storage_partition"][1], 1524 * 1024)
        self.assertNotIn("boot_partition", source)
        self.assertNotIn("slot1_partition", source)
        boards = (ROOT / "boards.txt").read_text(encoding="utf-8")
        self.assertIn("nu54dk.upload.maximum_size=1490944", boards)

        include = "#include <nucode/nu54dk-arduino-storage.dtsi>"
        for profile in ("standard", "ble"):
            profile_root = ROOT / "variants" / "nu54dk" / "profiles" / profile
            self.assertIn(include, (profile_root / "app.overlay").read_text(encoding="utf-8"))
            self.assertIn(
                "CONFIG_USE_DT_CODE_PARTITION=y",
                (profile_root / "prj.conf").read_text(encoding="utf-8"),
            )
            document = json.loads((profile_root / "profile.json").read_text(encoding="utf-8"))
            self.assertIn("storage", document["features"])
            self.assertIn("storage", document["requires_hil"])

    def test_feature_manifests_are_allowlisted_and_profile_compatible(self) -> None:
        """! @brief EEPROM과 LittleFS의 선언형 build 입력을 검증합니다. """

        profile = BUILDER.load_configuration_profile(ROOT, "standard")
        resolved = BUILDER.resolve_library_features(ROOT, profile, ["LittleFS", "EEPROM"])
        self.assertEqual([item["id"] for item in resolved], ["nucode.eeprom", "nucode.littlefs"])
        self.assertEqual(BUILDER.FEATURE_ALLOWLIST["EEPROM"], "nucode.eeprom")
        self.assertEqual(BUILDER.FEATURE_ALLOWLIST["LittleFS"], "nucode.littlefs")
        for feature in resolved:
            self.assertEqual(feature["requires"], ["storage"])
            self.assertEqual(feature["compatible_profiles"], ["standard", "ble"])

    def test_builder_validates_the_effective_linker_partition(self) -> None:
        """! @brief generated DTS와 linker map의 일치를 산출물 공개 전에 검증합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-ac03-layout-") as temporary:
            zephyr = Path(temporary)
            (zephyr / ".config").write_text(
                "CONFIG_USE_DT_CODE_PARTITION=y\n"
                "CONFIG_FLASH_USES_MAPPED_PARTITION=y\n",
                encoding="utf-8",
            )
            (zephyr / "zephyr.dts").write_text(
                """
/ {
    chosen { zephyr,code-partition = &slot0_partition; };
    slot0_partition: partition@0 {
        compatible = "zephyr,mapped-partition";
        label = "image-0";
        reg = < 0x0 0x16c000 >;
    };
    arduino_fs_partition: partition@16c000 {
        compatible = "zephyr,mapped-partition";
        label = "arduino-fs";
        reg = < 0x16c000 0x8000 >;
    };
    storage_partition: partition@174000 {
        compatible = "zephyr,mapped-partition";
        label = "storage";
        reg = < 0x174000 0x9000 >;
    };
};
""".lstrip(),
                encoding="utf-8",
            )
            (zephyr / "zephyr.map").write_text(
                "Memory Configuration\n\n"
                "Name             Origin             Length             Attributes\n"
                "FLASH            0x0000000000000000 0x000000000016c000 xr\n",
                encoding="utf-8",
            )

            self.assertEqual(
                BUILDER.validate_linked_code_partition(zephyr),
                {
                    "code_partition": "slot0_partition",
                    "flash_origin": 0,
                    "flash_size": 0x16C000,
                    "flash_end": 0x16C000,
                },
            )

            (zephyr / "zephyr.map").write_text(
                "FLASH 0x0000000000000000 0x000000000017d000 xr\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(BUILDER.AdapterError, "E_MEMORY_LAYOUT"):
                BUILDER.validate_linked_code_partition(zephyr)

    def test_eeprom_record_and_explicit_commit_contract(self) -> None:
        """! @brief EEPROM의 mirror, CRC, bounds, 명시적 commit 계약을 검증합니다. """

        header = (ROOT / "libraries" / "EEPROM" / "src" / "EEPROM.h").read_text(encoding="utf-8")
        base = ROOT / "libraries" / "EEPROM" / "src"
        source = "\n".join((base / name).read_text(encoding="utf-8") for name in (
            "internal/EEPROMRecord.h", "internal/EEPROMRecord.cpp",
            "internal/EEPROMSettings.cpp", "EEPROM.cpp",
        ))
        self.assertIn("maximum_size = 1024U", header)
        self.assertRegex(header, r"bool\s+commit\s*\(\s*\)")
        self.assertRegex(header, r"bool\s+reset\s*\(")
        for marker in ("record_magic", "record_version", "crc32", '"arduino/eeprom"'):
            self.assertIn(marker, source)
        self.assertIn("settings_save_one", source)
        self.assertNotIn("settings_save_one", source[source.index("void EEPROMClass::write"):source.index("bool EEPROMClass::commit")])
        self.assertIn("EEPROMError::out_of_bounds", source)
        self.assertIn("k_is_in_isr", source)
        self.assertNotIn("SETTINGS_ZMS_FORCE_MOUNT=y", (ROOT / "libraries" / "EEPROM" / "zephyr" / "eeprom.conf").read_text(encoding="utf-8"))

    def test_littlefs_default_mount_cannot_format(self) -> None:
        """! @brief 기본 mount와 명시적 format 경계를 검증합니다. """

        header = (ROOT / "libraries" / "LittleFS" / "src" / "LittleFS.h").read_text(encoding="utf-8")
        source = (ROOT / "libraries" / "LittleFS" / "src" / "LittleFS.cpp").read_text(encoding="utf-8")
        self.assertIn("format_on_fail = false", header)
        self.assertIn("FS_MOUNT_FLAG_NO_FORMAT", source)
        begin_body = source[source.index("bool LittleFSClass::begin"):source.index("bool LittleFSClass::end")]
        self.assertIn("if (result < 0 && format_on_fail)", begin_body)
        self.assertEqual(begin_body.count("formatLocked()"), 1)
        self.assertIn("arduino_fs_partition", source)
        self.assertIn("0x16c000", source)
        self.assertIn("0x8000", source)

    def test_approved_legacy_headers_and_examples_exist(self) -> None:
        """! @brief 대표 Arduino include와 세 공개 예제를 검증합니다. """

        for name in ("WString.h", "HardwareSerial.h", "Stream.h", "Printable.h"):
            self.assertTrue((ROOT / "cores" / "arduino" / name).is_file(), name)
        examples = {
            "Servo": "Sweep",
            "EEPROM": "EEPROMPersistence",
            "LittleFS": "LittleFSPersistence",
        }
        for library, example in examples.items():
            sketch = ROOT / "libraries" / library / "examples" / example / f"{example}.ino"
            self.assertTrue(sketch.is_file(), sketch)


if __name__ == "__main__":
    unittest.main()
