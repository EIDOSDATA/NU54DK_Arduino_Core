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

HIL_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "hil" / "nu54dk" / "m8_upload.py"
)
HIL_MODULE_SPEC = importlib.util.spec_from_file_location(
    "nu54_m8_upload_hil", HIL_MODULE_PATH
)
if HIL_MODULE_SPEC is None or HIL_MODULE_SPEC.loader is None:
    raise RuntimeError(f"M8 upload HIL module을 불러올 수 없습니다: {HIL_MODULE_PATH}")
HIL_MODULE = importlib.util.module_from_spec(HIL_MODULE_SPEC)
HIL_MODULE_SPEC.loader.exec_module(HIL_MODULE)


class M8FlashContractTests(unittest.TestCase):
    """! @brief M8 일반 upload가 artifact와 probe를 안전하게 선택하는지 검증합니다. """

    def setUp(self) -> None:
        """! @brief non-sysbuild Full Zephyr upload fixture를 생성합니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="n54-m8-host-")
        self.root = Path(self.temporary.name)
        self.platform = self.root / "platform"
        self.build = self.root / "arduino-build"
        self.cache_root = self.root / "cache"
        self.input_manifest = {"schema_version": MODULE.CACHE_SCHEMA_VERSION, "fixture": "m8"}
        self.cache_key = MODULE.cache_key_for_manifest(self.input_manifest)
        self.workspace = MODULE.cache_workspace(self.cache_key, root=self.cache_root)
        self.zephyr_build = self.workspace / "build"
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
        (self.workspace / "input-manifest.json").write_text(
            json.dumps(self.input_manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.workspace / "state.json").write_text(
            json.dumps(
                {
                    "schema_version": MODULE.CACHE_SCHEMA_VERSION,
                    "cache_key": self.cache_key,
                    "state": "ready",
                    "first_configure_complete": True,
                    "last_build_result": "success",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.manifest = {
            "schema_version": MODULE.ARTIFACT_MANIFEST_SCHEMA_VERSION,
            "adapter_version": MODULE.ADAPTER_VERSION,
            "fqbn": "nucode:zephyr:nu54dk",
            "board": MODULE.DEFAULT_BOARD,
            "sysbuild": False,
            "context": {
                "schema_version": MODULE.SESSION_CONTEXT_SCHEMA_VERSION,
                "adapter_version": MODULE.ADAPTER_VERSION,
                "state": "built",
                "fqbn": "nucode:zephyr:nu54dk",
                "board": MODULE.DEFAULT_BOARD,
                "build_path": self.build.as_posix(),
                "platform_root": self.platform.as_posix(),
                "cache_root": self.cache_root.as_posix(),
                "cache_key": self.cache_key,
                "cache_dir": self.workspace.as_posix(),
                "zephyr_build_dir": self.zephyr_build.as_posix(),
            },
            "cache": {
                "schema_version": MODULE.CACHE_SCHEMA_VERSION,
                "key": self.cache_key,
                "input_manifest": self.input_manifest,
                "cache_dir": self.workspace.as_posix(),
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

    def test_rejects_destructive_runner_metadata(self) -> None:
        """! @brief runners.yaml에 숨은 erase/recover option도 일반 upload에서 거부합니다. """

        runners = self.zephyr_build / "zephyr" / "runners.yaml"
        runners.write_text(
            runners.read_text(encoding="utf-8").replace(
                "    - --target=nrf54l\n", "    - --target=nrf54l\n    - --erase\n"
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.AdapterError, "E_FLASH_UNSAFE_OPTION"):
            MODULE.validate_runner_configuration(self.zephyr_build, "pyocd")

    def test_selects_one_or_explicit_pyocd_probe(self) -> None:
        """! @brief 단일 probe 자동 선택과 명시 UID 선택을 검증합니다. """

        self.assertEqual(MODULE.select_pyocd_probe(None, ["ABC123"]), "ABC123")
        self.assertEqual(MODULE.select_pyocd_probe("   ", ["ABC123"]), "ABC123")
        self.assertEqual(MODULE.select_pyocd_probe("abc123", ["ABC123"]), "ABC123")

    def test_selects_noninteractive_or_explicit_uid_upload_tool(self) -> None:
        """! @brief 기본 pyOCD와 명시 UID 전용 메뉴가 분리되는지 검증합니다. """

        self.assertEqual(HIL_MODULE.select_upload_probe_option("pyocd", ""), "pyocd")
        self.assertEqual(
            HIL_MODULE.select_upload_probe_option("pyocd", "ABC123"),
            "pyocd_uid",
        )
        self.assertEqual(HIL_MODULE.select_upload_probe_option("jlink", "ABC123"), "jlink")

    def test_redacts_explicit_probe_identity_without_losing_selection_mode(self) -> None:
        """! @brief 결과 JSON이 UID를 숨기면서 선택 방식과 메뉴를 보존하는지 검증합니다. """

        explicit = HIL_MODULE.probe_selection_summary("pyocd_uid", "ABC123")
        self.assertEqual(
            explicit,
            {
                "probe_id": "redacted",
                "probe_selection_mode": "explicit",
                "upload_probe": "pyocd_uid",
            },
        )
        self.assertNotIn("ABC123", explicit.values())
        automatic = HIL_MODULE.probe_selection_summary("pyocd", "")
        self.assertEqual(automatic["probe_id"], "auto-single")
        self.assertEqual(automatic["probe_selection_mode"], "auto-single")
        self.assertEqual(automatic["upload_probe"], "pyocd")

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
