#!/usr/bin/env python3
"""! @brief M8 upload manifest, runner와 probe 안전 계약을 host에서 검증합니다. """

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "nu54-builder"
    / "src"
    / "nu54_builder.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("nu54_builder_m8", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"nu54-builder module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


class M8FlashContractTests(unittest.TestCase):
    """! @brief M8 일반 upload가 artifact와 probe를 안전하게 선택하는지 검증합니다. """

    def setUp(self) -> None:
        """! @brief non-sysbuild Full Zephyr upload fixture를 생성합니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="n54-m8-host-")
        self.root = Path(self.temporary.name)
        self.platform = self.root / "platform"
        self.build = self.root / "arduino-build"
        self.zephyr_build = self.root / "zephyr-build"
        self.platform.mkdir()
        self.build.mkdir()
        (self.zephyr_build / "zephyr").mkdir(parents=True)
        (self.zephyr_build / "CMakeCache.txt").write_text("fixture\n", encoding="utf-8")
        (self.zephyr_build / "build.ninja").write_text("fixture\n", encoding="utf-8")
        self.hex_content = b":020000040000FA\n:00000001FF\n"
        self.elf_content = b"ELF-M8-FIXTURE"
        self.exported_hex = self.build / "Blink.ino.hex"
        self.exported_elf = self.build / "Blink.ino.elf"
        self.exported_hex.write_bytes(self.hex_content)
        self.exported_elf.write_bytes(self.elf_content)
        (self.zephyr_build / "zephyr" / "zephyr.hex").write_bytes(self.hex_content)
        (self.zephyr_build / "zephyr" / "zephyr.elf").write_bytes(self.elf_content)
        (self.zephyr_build / "zephyr" / "runners.yaml").write_text(
            "runners:\n"
            "- nrfutil\n"
            "- jlink\n"
            "- pyocd\n"
            "flash-runner: pyocd\n"
            "debug-runner: pyocd\n"
            "args:\n"
            "  jlink:\n"
            "    - --dt-flash=y\n"
            "    - --device=nRF54L15_M33\n"
            "    - --speed=4000\n"
            "  pyocd:\n"
            "    - --dt-flash=y\n"
            "    - --target=nrf54l\n",
            encoding="utf-8",
        )
        self.manifest_path = self.build / "Blink.ino.nu54-build.json"
        self.manifest = {
            "schema_version": 1,
            "adapter_version": MODULE.ADAPTER_VERSION,
            "fqbn": "nucode:zephyr:nu54dk",
            "board": MODULE.DEFAULT_BOARD,
            "sysbuild": False,
            "context": {
                "fqbn": "nucode:zephyr:nu54dk",
                "board": MODULE.DEFAULT_BOARD,
                "build_path": self.build.as_posix(),
                "platform_root": self.platform.as_posix(),
                "zephyr_build_dir": self.zephyr_build.as_posix(),
            },
            "artifacts": {
                "hex": self.artifact_record(self.exported_hex),
                "elf": self.artifact_record(self.exported_elf),
            },
        }
        self.write_manifest()
        self.args = argparse.Namespace(
            platform_root=str(self.platform),
            build_path=str(self.build),
            sketch_root=str(self.root / "sketch"),
            fqbn="nucode:zephyr:nu54dk",
            project_name="Blink.ino",
            board=MODULE.DEFAULT_BOARD,
            manifest=str(self.manifest_path),
            runner="pyocd",
            probe_id=None,
            verbose=False,
        )

    def tearDown(self) -> None:
        """! @brief 각 시험의 임시 fixture를 제거합니다. """

        self.temporary.cleanup()

    def artifact_record(self, path: Path) -> dict[str, object]:
        """! @brief fixture artifact의 manifest record를 반환합니다. """

        return {
            "path": path.as_posix(),
            "sha256": MODULE.file_sha256(path),
            "size": path.stat().st_size,
        }

    def write_manifest(self) -> None:
        """! @brief 현재 fixture manifest를 UTF-8 JSON으로 기록합니다. """

        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_accepts_matching_non_sysbuild_artifacts(self) -> None:
        """! @brief export와 native artifact가 같을 때 upload 입력을 승인합니다. """

        result = MODULE.validate_flash_manifest(self.args)
        self.assertEqual(result["zephyr_build"], self.zephyr_build)
        self.assertEqual(result["hex_sha256"], MODULE.file_sha256(self.exported_hex))

    def test_rejects_exported_hex_hash_mismatch(self) -> None:
        """! @brief build 후 변경된 export HEX를 거부합니다. """

        self.exported_hex.write_bytes(self.hex_content + b"changed")
        with self.assertRaisesRegex(MODULE.AdapterError, "E_FLASH_ARTIFACT_HASH"):
            MODULE.validate_flash_manifest(self.args)

    def test_rejects_native_hex_mismatch(self) -> None:
        """! @brief west가 기록할 native HEX와 export HEX가 다르면 거부합니다. """

        (self.zephyr_build / "zephyr" / "zephyr.hex").write_bytes(b"different")
        with self.assertRaisesRegex(MODULE.AdapterError, "E_FLASH_ARTIFACT_HASH"):
            MODULE.validate_flash_manifest(self.args)

    def test_rejects_board_mismatch(self) -> None:
        """! @brief 다른 board로 생성된 manifest를 거부합니다. """

        self.manifest["board"] = "different/board"
        self.write_manifest()
        with self.assertRaisesRegex(MODULE.AdapterError, "E_FLASH_BOARD_MISMATCH"):
            MODULE.validate_flash_manifest(self.args)

    def test_rejects_sysbuild_manifest(self) -> None:
        """! @brief 아직 지원하지 않는 merged sysbuild artifact를 명확히 거부합니다. """

        self.manifest["sysbuild"] = True
        self.write_manifest()
        with self.assertRaisesRegex(MODULE.AdapterError, "E_FLASH_SYSBUILD_UNSUPPORTED"):
            MODULE.validate_flash_manifest(self.args)

    def test_validates_both_runner_contracts(self) -> None:
        """! @brief pyOCD와 J-Link 고정 target argument를 YAML에서 확인합니다. """

        for runner in ("pyocd", "jlink"):
            path = MODULE.validate_runner_configuration(self.zephyr_build, runner)
            self.assertEqual(path.name, "runners.yaml")

    def test_rejects_missing_runner(self) -> None:
        """! @brief build에 등록되지 않은 runner를 거부합니다. """

        with self.assertRaisesRegex(MODULE.AdapterError, "E_RUNNER_UNAVAILABLE"):
            MODULE.validate_runner_configuration(self.zephyr_build, "openocd")

    def test_selects_one_or_explicit_pyocd_probe(self) -> None:
        """! @brief 단일 probe 자동 선택과 명시 UID 선택을 검증합니다. """

        self.assertEqual(MODULE.select_pyocd_probe(None, ["ABC123"]), "ABC123")
        self.assertEqual(MODULE.select_pyocd_probe("abc123", ["ABC123"]), "ABC123")

    def test_rejects_missing_or_ambiguous_pyocd_probe(self) -> None:
        """! @brief probe 없음과 다중 probe 무지정 상태를 구분해 거부합니다. """

        with self.assertRaisesRegex(MODULE.AdapterError, "E_PROBE_NOT_FOUND"):
            MODULE.select_pyocd_probe(None, [])
        with self.assertRaisesRegex(MODULE.AdapterError, "E_PROBE_AMBIGUOUS"):
            MODULE.select_pyocd_probe(None, ["A", "B"])

    def test_flash_command_has_no_destructive_option(self) -> None:
        """! @brief 일반 upload 명령에 erase 또는 recover가 없는지 검증합니다. """

        tools = {
            "west": Path("C:/toolchain/west.exe"),
            "zephyr_base": Path("C:/ncs/zephyr"),
        }
        command = [str(value) for value in MODULE.build_flash_command(
            tools, self.zephyr_build, "pyocd", "ABC123"
        )]
        self.assertIn("--no-rebuild", command)
        self.assertIn("--tool-opt=-Osmart_flash=false", command)
        self.assertEqual(command[-3:-1], ["--dev-id", "ABC123"])
        self.assertNotIn("--erase", command)
        self.assertNotIn("--recover", command)


if __name__ == "__main__":
    unittest.main()
