#!/usr/bin/env python3
"""! @brief M30 MCUboot layout·서명·builder 계약을 host에서 검증합니다. """

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPOSITORY / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("nu54_builder_m30", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"nu54-builder module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)

HIL_MODULE_PATH = REPOSITORY / "tests" / "hil" / "nu54dk" / "m30_mcuboot.py"
HIL_MODULE_SPEC = importlib.util.spec_from_file_location(
    "m30_mcuboot_hil_runner", HIL_MODULE_PATH
)
if HIL_MODULE_SPEC is None or HIL_MODULE_SPEC.loader is None:
    raise RuntimeError(f"M30 MCUboot HIL runner를 불러올 수 없습니다: {HIL_MODULE_PATH}")
HIL_MODULE = importlib.util.module_from_spec(HIL_MODULE_SPEC)
sys.modules[HIL_MODULE_SPEC.name] = HIL_MODULE
HIL_MODULE_SPEC.loader.exec_module(HIL_MODULE)


class M30McubootContractTests(unittest.TestCase):
    """! @brief 기본 loaderless와 분리된 secure DFU profile을 검증합니다. """

    def profile(self, profile_id: str) -> dict[str, object]:
        """! @brief 실제 NU54DK profile을 엄격한 loader로 읽습니다. """

        return MODULE.load_configuration_profile(
            REPOSITORY,
            profile_id,
            fqbn="nucode:zephyr:nu54dk",
            zephyr_board=MODULE.DEFAULT_BOARD,
        )

    def test_loaderless_defaults_and_secure_sysbuild_are_separate(self) -> None:
        """! @brief 기존 세 profile은 loaderless이고 secure DFU만 sysbuild입니다. """

        for profile_id in ("standard", "ble", "fabric"):
            profile = self.profile(profile_id)
            self.assertFalse(profile["sysbuild"], profile_id)
            self.assertEqual(profile["sysbuild_files"], [], profile_id)
            self.assertIsNone(profile["signing_key_env"], profile_id)
        secure = self.profile("secure_ble_dfu")
        self.assertTrue(secure["sysbuild"])
        self.assertEqual(secure["signing_key_env"], "NUCODE_DFU_SIGNING_KEY")
        self.assertEqual(
            secure["sysbuild_files"],
            ["sysbuild.conf", "sysbuild/mcuboot.conf", "sysbuild/mcuboot.overlay"],
        )
        boards = (REPOSITORY / "boards.txt").read_text(encoding="utf-8")
        self.assertIn("nu54dk.menu.feature_set.secure_ble_dfu.build.sysbuild=true", boards)
        self.assertIn("nu54dk.menu.feature_set.secure_ble_dfu.upload.maximum_size=729088", boards)

    def test_configure_command_selects_profile_sysbuild_mode(self) -> None:
        """! @brief profile 선택이 west의 sysbuild mode와 서명 fragment를 결정합니다. """

        paths = {
            "platform_root": REPOSITORY,
            "app": Path("C:/cache/app"),
            "zephyr_build": Path("C:/cache/build"),
        }
        tools = {"west": Path("C:/tools/west.exe"), "zephyr_base": Path("C:/ncs/zephyr")}
        common = {
            "fqbn": "nucode:zephyr:nu54dk",
            "board": MODULE.DEFAULT_BOARD,
        }
        secure = MODULE.configure_command(
            paths,
            argparse.Namespace(**common, profile="secure_ble_dfu"),
            tools,
            REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS",
            pristine=True,
        )
        standard = MODULE.configure_command(
            paths,
            argparse.Namespace(**common, profile="standard"),
            tools,
            REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS",
            pristine=True,
        )
        secure_text = [str(value) for value in secure]
        standard_text = [str(value) for value in standard]
        self.assertIn("--sysbuild", secure_text)
        self.assertNotIn("--no-sysbuild", secure_text)
        self.assertIn("-DSB_EXTRA_CONF_FILE=C:/cache/app/sysbuild/signing-key.conf", secure_text)
        self.assertIn("--no-sysbuild", standard_text)
        self.assertNotIn("--sysbuild", standard_text)

    def test_signing_key_is_required_outside_repository(self) -> None:
        """! @brief 서명 private key 누락·저장소 내부 배치를 fail-closed로 거부합니다. """

        secure = self.profile("secure_ble_dfu")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(MODULE.AdapterError, "E_DFU_SIGNING_KEY"):
                MODULE.resolve_profile_signing_key(REPOSITORY, secure)
        with tempfile.TemporaryDirectory(prefix="n54-m30-key-") as directory:
            platform = Path(directory)
            key = platform / "inside.pem"
            key.write_text(
                "-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----\n",
                encoding="ascii",
            )
            with mock.patch.dict(
                os.environ, {"NUCODE_DFU_SIGNING_KEY": str(key)}, clear=True
            ):
                with self.assertRaisesRegex(
                    MODULE.AdapterError, "E_DFU_SIGNING_KEY_REPOSITORY"
                ):
                    MODULE.resolve_profile_signing_key(platform, secure)

    def test_repository_contains_no_private_signing_key(self) -> None:
        """! @brief 저장소에 PEM private key와 private key body가 없음을 검사합니다. """

        tracked = subprocess.run(
            ["git", "ls-files", "*.pem"],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(tracked.stdout.splitlines(), [])

    def test_layout_signature_and_rollback_controls_are_explicit(self) -> None:
        """! @brief vendor dual-slot include와 P-256·move·rollback 방지를 고정합니다. """

        board = (
            REPOSITORY
            / "board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk"
            / "nrf54l15dk_nrf54l15_cpuapp_nu54dk.dts"
        ).read_text(encoding="utf-8")
        self.assertIn("<vendor/nordic/nrf54l15_cpuapp_partition.dtsi>", board)
        sysbuild = (
            REPOSITORY / "variants/nu54dk/profiles/secure_ble_dfu/sysbuild.conf"
        ).read_text(encoding="utf-8")
        boot = (
            REPOSITORY / "variants/nu54dk/profiles/secure_ble_dfu/sysbuild/mcuboot.conf"
        ).read_text(encoding="utf-8")
        for token in (
            "SB_CONFIG_BOOTLOADER_MCUBOOT=y",
            "SB_CONFIG_MCUBOOT_MODE_SWAP_USING_MOVE=y",
            "SB_CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y",
        ):
            self.assertIn(token, sysbuild)
        for token in (
            "CONFIG_FLASH=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION_SECURITY_COUNTER=y",
            "CONFIG_FPROTECT=y",
        ):
            self.assertIn(token, boot)

    def test_hil_target_exposes_finite_boot_protocol(self) -> None:
        """! @brief target이 confirm·warm reboot·test upgrade 명령만 제공함을 검증합니다. """

        target = (
            REPOSITORY / "tests/zephyr/m30_mcuboot_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "boot_write_img_confirmed()",
            "boot_fetch_active_slot()",
            "boot_read_bank_header(",
            "boot_request_upgrade(BOOT_UPGRADE_TEST)",
            "sys_reboot(SYS_REBOOT_WARM)",
            '::strcmp(line, "M30BOOT|1|REBOOT")',
            'Serial.print("|version=")',
        ):
            self.assertIn(token, target)
        self.assertNotIn("power_cut", target.casefold())

    def test_hil_runner_parses_signed_header_and_ready_identity(self) -> None:
        """! @brief header version과 exact Core READY만 구조화합니다. """

        with tempfile.TemporaryDirectory(prefix="n54-m30-header-") as directory:
            signed = Path(directory) / "signed.bin"
            header = bytearray(b"\xff" * 0x800)
            struct.pack_into("<I", header, 0, HIL_MODULE.MCUBOOT_MAGIC)
            struct.pack_into("<H", header, 8, 0x800)
            struct.pack_into("<BBHI", header, 20, 9, 0, 0, 0)
            signed.write_bytes(header)
            self.assertEqual(
                HIL_MODULE.parse_mcuboot_version(signed),
                HIL_MODULE.WRONG_KEY_VERSION,
            )
        core = "a" * 40
        ready = HIL_MODULE.parse_ready(
            (
                "M30BOOT|1|READY|active_slot=1|confirmed=1|confirm_rc=0"
                f"|version=0.0.0+0|core={core}"
            ).encode("ascii")
        )
        self.assertEqual(ready.version, HIL_MODULE.PRIMARY_VERSION)
        self.assertEqual(ready.core_revision, core)

    def test_hil_runner_rejects_bad_headers_and_protocol(self) -> None:
        """! @brief 잘못된 header 크기와 느슨한 READY를 거부합니다. """

        with tempfile.TemporaryDirectory(prefix="n54-m30-header-") as directory:
            bad = Path(directory) / "bad.bin"
            header = bytearray(b"\xff" * 32)
            struct.pack_into("<I", header, 0, HIL_MODULE.MCUBOOT_MAGIC)
            struct.pack_into("<H", header, 8, 0x400)
            bad.write_bytes(header)
            with self.assertRaisesRegex(HIL_MODULE.M30BootFailure, "0x800"):
                HIL_MODULE.parse_mcuboot_version(bad)
        with self.assertRaisesRegex(HIL_MODULE.M30BootFailure, "READY"):
            HIL_MODULE.parse_ready(b"M30BOOT|1|READY|confirmed=1")

    def test_hil_runner_uses_only_exact_sector_operations(self) -> None:
        """! @brief secondary 범위와 no-auto-unlock 정책을 고정합니다. """

        source = HIL_MODULE_PATH.read_text(encoding="utf-8")
        self.assertEqual(HIL_MODULE.SLOT1_OFFSET, 794624)
        self.assertEqual(HIL_MODULE.SLOT1_SIZE, 729088)
        self.assertEqual(HIL_MODULE.SIGNED_BOOTS, 20)
        self.assertIn('"auto_unlock=false"', source)
        self.assertIn('"--erase",\n        "sector"', source)
        self.assertNotIn('"--mass"', source)
        self.assertNotIn('"--chip"', source)
        self.assertIn('"physical_power_loss_claim": False', source)

    def test_imgtool_environment_is_scoped_to_child_process(self) -> None:
        """! @brief NCS Python 환경을 현재 host Python에 섞지 않습니다. """

        python = Path("C:/ncs/toolchains/dcbdc366a1/opt/bin/python.exe")
        if not python.is_file():
            self.skipTest("고정 NCS toolchain Python이 없습니다.")
        previous = os.environ.get("PYTHONPATH")
        child = HIL_MODULE.imgtool_environment(python)
        self.assertIn("PYTHONPATH", child)
        self.assertEqual(os.environ.get("PYTHONPATH"), previous)
        self.assertEqual(child["ZEPHYR_TOOLCHAIN_VARIANT"], "zephyr/gnu")


if __name__ == "__main__":
    unittest.main()
