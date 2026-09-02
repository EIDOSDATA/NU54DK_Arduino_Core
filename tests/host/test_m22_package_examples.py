#!/usr/bin/env python3
"""! @brief M22 설치 package 전체 예제 runner 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tools" / "release" / "run_m22_package_examples.py"
SPEC = importlib.util.spec_from_file_location("run_m22_package_examples", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"M22 package example runner를 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M22PackageExamplesTests(unittest.TestCase):
    """! @brief 설치 경로·29개 lock·manifest 누출 차단을 시험합니다. """

    def setUp(self) -> None:
        """! @brief 각 시험용 격리 platform fixture를 만듭니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m22-examples-")
        self.root = Path(self.temporary.name)
        self.platform = self.root / "data" / "packages" / "nucode" / "hardware" / "zephyr" / MODULE.VERSION
        self.platform.mkdir(parents=True)
        self.lock = MODULE.load_example_lock()
        grouped: dict[tuple[str, str], list[Path]] = {}
        for record in self.lock:
            sketch = (
                self.platform
                / "libraries"
                / record["library_directory"]
                / "examples"
                / record["example"]
            )
            sketch.mkdir(parents=True, exist_ok=True)
            (sketch / f"{record['example']}.ino").write_text(
                "void setup() {}\nvoid loop() {}\n", encoding="utf-8"
            )
            grouped.setdefault(
                (record["library"], record["library_directory"]), []
            ).append(sketch)
        self.listing = {
            "examples": [
                {
                    "library": {
                        "name": name,
                        "install_dir": str(self.platform / "libraries" / directory),
                        "container_platform": f"nucode:zephyr@{MODULE.VERSION}",
                        "location": "platform",
                    },
                    "examples": [str(path) for path in paths],
                }
                for (name, directory), paths in grouped.items()
            ]
        }

    def tearDown(self) -> None:
        """! @brief 임시 fixture를 폐기합니다. """

        self.temporary.cleanup()

    def test_lock_contains_every_29_profiled_examples(self) -> None:
        """! @brief 공개 package 예제 집합과 BLE profile 구분을 고정합니다. """

        self.assertEqual(len(self.lock), 29)
        self.assertEqual(
            sum(record["profile"] == "ble" for record in self.lock), 7
        )
        self.assertEqual(
            len({(record["library"], record["example"]) for record in self.lock}),
            29,
        )
        self.assertIn(("EEPROM", "EEPROMPersistence"), {
            (record["library"], record["example"]) for record in self.lock
        })
        self.assertIn(("LittleFS", "LittleFSPersistence"), {
            (record["library"], record["example"]) for record in self.lock
        })

    def test_lock_matches_every_repository_library_example(self) -> None:
        """! @brief package source에 추가된 Arduino 예제가 lock 밖으로 빠지지 않습니다. """

        source_examples = {
            (
                sketch.relative_to(REPOSITORY / "libraries").parts[0],
                sketch.parent.name,
            )
            for sketch in (REPOSITORY / "libraries").glob(
                "*/examples/*/*.ino"
            )
        }
        locked_examples = {
            (record["library_directory"], record["example"])
            for record in self.lock
        }
        self.assertEqual(source_examples, locked_examples)

    def test_discovery_accepts_only_installed_platform_paths(self) -> None:
        """! @brief Arduino CLI가 설치본에서 열거한 exact 29개만 승인합니다. """

        discovered = MODULE.parse_installed_examples(
            self.listing, self.lock, self.platform
        )
        self.assertEqual(len(discovered), 29)
        platform_key = MODULE.resolved_path_key(self.platform)
        self.assertTrue(
            all(
                MODULE.resolved_path_key(path).startswith(platform_key + "/")
                for path in discovered.values()
            )
        )

    def test_discovery_rejects_source_checkout_substitution(self) -> None:
        """! @brief 저장소 source 예제를 설치본으로 가장하면 실패합니다. """

        source = self.root / "source" / "libraries" / "NUCODE_NU54DK" / "examples" / "Blink"
        source.mkdir(parents=True)
        (source / "Blink.ino").write_text("void setup() {}\n", encoding="utf-8")
        for record in self.listing["examples"]:
            if record["library"]["name"] == "NUCODE NU54DK":
                record["examples"] = [
                    str(source) if Path(value).name == "Blink" else value
                    for value in record["examples"]
                ]
        with self.assertRaisesRegex(MODULE.PackageExamplesFailure, "설치 예제 경로"):
            MODULE.parse_installed_examples(self.listing, self.lock, self.platform)

    def test_discovery_rejects_unlocked_installed_package_example(self) -> None:
        """! @brief 새 package 예제를 lock/compile 대상에서 빠뜨릴 수 없습니다. """

        library = self.platform / "libraries" / "Unexpected"
        sketch = library / "examples" / "MissedExample"
        sketch.mkdir(parents=True)
        (sketch / "MissedExample.ino").write_text("void setup() {}\n", encoding="utf-8")
        self.listing["examples"].append({
            "library": {
                "name": "Unexpected",
                "install_dir": str(library),
                "container_platform": f"nucode:zephyr@{MODULE.VERSION}",
                "location": "platform",
            },
            "examples": [str(sketch)],
        })
        with self.assertRaisesRegex(MODULE.PackageExamplesFailure, "lock에 없는"):
            MODULE.parse_installed_examples(self.listing, self.lock, self.platform)

    def test_manifest_binds_isolated_package_sdk_toolchain_and_cache(self) -> None:
        """! @brief build identity가 모든 격리 root와 HEX byte에 묶입니다. """

        example = next(record for record in self.lock if record["example"] == "Blink")
        sketch = (
            self.platform
            / "libraries"
            / example["library_directory"]
            / "examples"
            / example["example"]
        )
        build = self.root / "build" / "blink"
        build.mkdir(parents=True)
        ncs = self.root / "profile" / "ncs" / "v3.4.0"
        toolchain = self.root / "profile" / "ncs" / "toolchains" / "dcbdc366a1"
        cache = self.root / "cache"
        for directory in (ncs, toolchain, cache):
            directory.mkdir(parents=True, exist_ok=True)
        hex_path = build / "Blink.ino.hex"
        hex_path.write_bytes(b":00000001FF\n")
        manifest = {
            "schema_version": 2,
            "fqbn": f"{MODULE.FQBN}:feature_set=standard,upload_probe=pyocd",
            "context": {
                "state": "built",
                "profile": "standard",
                "fqbn": f"{MODULE.FQBN}:feature_set=standard,upload_probe=pyocd",
                "build_path": str(build),
                "platform_root": str(self.platform),
                "sketch_root": str(sketch),
                "ncs_root": str(ncs),
                "toolchain_root": str(toolchain),
                "cache_root": str(cache),
                "cache_reused": False,
            },
            "artifacts": {
                "hex": {
                    "path": str(hex_path),
                    "sha256": MODULE.file_sha256(hex_path),
                    "size": hex_path.stat().st_size,
                }
            },
        }
        manifest_path = build / "Blink.ino.nu54-build.json"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        result = MODULE.validate_build_manifest(
            manifest_path,
            example=example,
            sketch=sketch,
            build_root=build,
            platform_root=self.platform,
            ncs_root=ncs,
            toolchain_root=toolchain,
            cache_root=cache,
            forbidden_roots=(self.root / "forbidden",),
        )
        self.assertEqual(result["hex_sha256"], MODULE.file_sha256(hex_path))

        manifest["context"]["ncs_root"] = "C:/ncs/v3.4.0"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.PackageExamplesFailure, "ncs_root"):
            MODULE.validate_build_manifest(
                manifest_path,
                example=example,
                sketch=sketch,
                build_root=build,
                platform_root=self.platform,
                ncs_root=ncs,
                toolchain_root=toolchain,
                cache_root=cache,
                forbidden_roots=(Path("C:/ncs"),),
            )

    def test_deep_forbidden_path_scan_is_fail_closed(self) -> None:
        """! @brief 중첩 manifest 문자열의 기존 Arduino15 경로도 거부합니다. """

        with self.assertRaisesRegex(MODULE.PackageExamplesFailure, "누출"):
            MODULE.assert_no_forbidden_values(
                {"nested": [{"path": "C:/Users/test/AppData/Local/Arduino15/packages"}]},
                (Path("C:/Users/test/AppData/Local/Arduino15"),),
            )


if __name__ == "__main__":
    unittest.main()
