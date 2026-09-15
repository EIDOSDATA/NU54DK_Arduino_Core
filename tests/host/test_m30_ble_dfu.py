#!/usr/bin/env python3
"""! @brief M30 secure BLE DFU profile과 공개 facade 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
PROFILE = REPOSITORY / "variants/nu54dk/profiles/secure_ble_dfu/prj.conf"
LIBRARY = REPOSITORY / "libraries/NUCODE_BLE_DFU"
HIL_TARGET = REPOSITORY / "tests/zephyr/m30_ble_dfu_hil"
HIL_RUNNER_PATH = REPOSITORY / "tests/hil/nu54dk/m30_ble_dfu.py"
HIL_SPEC = importlib.util.spec_from_file_location("m30_ble_dfu_hil_runner", HIL_RUNNER_PATH)
if HIL_SPEC is None or HIL_SPEC.loader is None:
    raise RuntimeError(f"M30 BLE DFU HIL runner를 불러올 수 없습니다: {HIL_RUNNER_PATH}")
HIL_RUNNER = importlib.util.module_from_spec(HIL_SPEC)
sys.modules[HIL_SPEC.name] = HIL_RUNNER
HIL_SPEC.loader.exec_module(HIL_RUNNER)


class M30SecureBleDfuTests(unittest.TestCase):
    """! @brief 인증 transport·명시적 confirm·profile 격리를 검사합니다. """

    def test_profile_requires_authenticated_reassembled_smp(self) -> None:
        """! @brief secure profile이 인증 BLE SMP와 bounded buffer를 고정합니다. """

        configuration = PROFILE.read_text(encoding="utf-8")
        for token in (
            "CONFIG_MCUMGR=y",
            "CONFIG_MCUMGR_GRP_IMG=y",
            "CONFIG_MCUMGR_GRP_OS=y",
            "CONFIG_MCUMGR_TRANSPORT_BT=y",
            "CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW_AUTHEN=y",
            "CONFIG_MCUMGR_TRANSPORT_BT_REASSEMBLY=y",
            "CONFIG_MCUMGR_TRANSPORT_NETBUF_SIZE=1024",
            "CONFIG_IMG_ENABLE_IMAGE_CHECK=y",
        ):
            self.assertIn(token, configuration)
        self.assertNotIn("CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW=y", configuration)

    def test_dfu_feature_is_secure_profile_only(self) -> None:
        """! @brief DFU feature가 loaderless profile에 유입되지 않는지 검사합니다. """

        feature = json.loads(
            (LIBRARY / "zephyr/feature.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(feature["id"], "nucode.ble.dfu")
        self.assertEqual(feature["compatible_profiles"], ["secure_ble_dfu"])
        self.assertIn("nucode.ble.security", feature["requires"])

    def test_facade_requires_explicit_confirm_after_begin(self) -> None:
        """! @brief begin과 confirm이 분리되고 current header를 읽는지 검사합니다. """

        header = (LIBRARY / "src/NUCODE_BLE_DFU.h").read_text(encoding="utf-8")
        source = (LIBRARY / "src/NUCODE_BLE_DFU.cpp").read_text(encoding="utf-8")
        self.assertIn("bool begin() noexcept", header)
        self.assertIn("bool confirm() noexcept", header)
        self.assertIn("boot_read_bank_header(", source)
        self.assertIn("boot_write_img_confirmed()", source)
        self.assertNotIn("boot_write_img_confirmed()", source.split("bool SecureDfuManager::begin", 1)[1].split("bool SecureDfuManager::confirm", 1)[0])
        self.assertIn("8d53dc1d-1db7-4cd3-868b-8a527460aa84", source)

    def test_hil_target_requires_l4_mtu_and_explicit_boot_state(self) -> None:
        """! @brief 두 보드 relay가 L4·MTU 247·재부팅 동기화를 고정합니다. """

        configuration = (HIL_TARGET / "prj.conf").read_text(encoding="utf-8")
        source = (HIL_TARGET / "src/main.cpp").read_text(encoding="utf-8")
        for token in (
            "CONFIG_BT_SMP_SC_PAIR_ONLY=y",
            "CONFIG_BT_SMP_MIN_ENC_KEY_SIZE=16",
            "CONFIG_BT_L2CAP_TX_MTU=247",
            "CONFIG_BT_BUF_ACL_RX_SIZE=251",
        ):
            self.assertIn(token, configuration)
        for token in (
            "BLEConnection.requestMtu(connection_handle)",
            "BLESecurity.lastError() != nucode::ble::SecurityError::busy",
            'Serial.print("|LINK|role=central|level=4|key_size=16|mtu=247|smp=1")',
            'Serial.print("|BOOT|role=peripheral|active_area_id=")',
            'Serial.print("|UNLINK|role=central")',
            '::strcmp(line, "M30DFU|1|READY?")',
            'constexpr char rescan_marker[] = "M30DFU|1|RESCAN|"',
            "restartCentralScan()",
            "NUCODE_M30_DFU_AUTO_CONFIRM",
        ):
            self.assertIn(token, source)
        self.assertEqual(HIL_RUNNER.PRIMARY_FLASH_AREA_ID, 1)
        self.assertNotIn("power_cut", source.casefold())

    def test_hil_runner_waits_for_disconnect_before_restarting_peripheral(self) -> None:
        """! @brief reset 응답 직후 이전 application에 START를 보내는 경쟁을 방지합니다. """

        source = HIL_RUNNER_PATH.read_text(encoding="utf-8")
        reset_body = source.split("def reset_and_reconnect", 1)[1].split(
            "def validate_boot", 1
        )[0]
        self.assertLess(
            reset_body.index("self.wait_unlink(deadline)"),
            reset_body.index("self.reconnect(deadline)"),
        )
        reconnect_body = source.split("def reconnect", 1)[1].split(
            "def wait_rx", 1
        )[0]
        self.assertLess(
            reconnect_body.index("self.start_peripheral(deadline)"),
            reconnect_body.index("self.restart_central_scan(deadline)"),
        )
        self.assertLess(
            reconnect_body.index("self.restart_central_scan(deadline)"),
            reconnect_body.index('self.wait_link("central", deadline)'),
        )

    def test_hil_runner_cbor_round_trip_is_strict(self) -> None:
        """! @brief SMP map·array·byte·bool을 보존하고 trailing byte를 거부합니다. """

        value = {
            "image": 0,
            "off": 216,
            "data": b"\x00\x01\xff",
            "flags": [True, False],
            "err": {"group": 1, "rc": 7},
        }
        encoded = HIL_RUNNER.cbor_encode(value)
        self.assertEqual(HIL_RUNNER.cbor_decode(encoded), value)
        with self.assertRaisesRegex(HIL_RUNNER.M30DfuFailure, "trailing"):
            HIL_RUNNER.cbor_decode(encoded + b"\x00")

    def test_hil_runner_parses_exact_mcuboot_hash_tlv(self) -> None:
        """! @brief version과 SHA-256 TLV를 header 경계에서 읽습니다. """

        with tempfile.TemporaryDirectory(prefix="n54-m30-dfu-image-") as directory:
            path = Path(directory) / "fixture.bin"
            header = bytearray(b"\x00" * 0x800)
            struct.pack_into("<IIHHII", header, 0, HIL_RUNNER.MCUBOOT_MAGIC, 0, 0x800, 0, 16, 0)
            struct.pack_into("<BBHI", header, 20, 3, 2, 1, 4)
            image_hash = bytes(range(32))
            tlv = struct.pack("<HHBBH", HIL_RUNNER.MCUBOOT_TLV_INFO_MAGIC, 40, HIL_RUNNER.MCUBOOT_HASH_TLV, 0, 32)
            path.write_bytes(header + b"P" * 16 + tlv + image_hash)
            artifact = HIL_RUNNER.parse_mcuboot_image(path)
            self.assertEqual(artifact.version, (3, 2, 1, 4))
            self.assertEqual(artifact.image_hash, image_hash)

    def test_hil_runner_fixes_quantities_and_non_power_scope(self) -> None:
        """! @brief update·negative 수량과 sector-only·비전원 범위를 고정합니다. """

        source = HIL_RUNNER_PATH.read_text(encoding="utf-8")
        self.assertEqual(HIL_RUNNER.POSITIVE_UPDATES, 10)
        self.assertEqual(HIL_RUNNER.NEGATIVE_ATTEMPTS, 20)
        for name in ("unsigned", "wrong_key", "corrupt", "truncated", "downgrade"):
            self.assertIn(f'"{name}"', source)
        self.assertIn('"power_cut_injected": False', source)
        self.assertIn('"mass_erase_or_recover": False', source)
        self.assertNotIn('"--mass"', source)
        self.assertNotIn('"--chip"', source)

    def test_central_build_requires_sysbuild_bootloader_and_signed_primary(self) -> None:
        """! @brief Central도 보드 계약대로 MCUboot와 서명 primary를 사용합니다. """

        with tempfile.TemporaryDirectory(prefix="n54-m30-central-") as directory:
            root = Path(directory)
            app = root / HIL_RUNNER.APPLICATION_DOMAIN
            boot = root / HIL_RUNNER.BOOT_DOMAIN
            (app / "zephyr").mkdir(parents=True)
            (boot / "zephyr").mkdir(parents=True)
            core_revision = "a" * 40
            trust_key = root / "trust.pem"
            trust_key.write_text("test-key\n", encoding="ascii")
            (root / "domains.yaml").write_text(
                "default: m30_ble_dfu_hil\n"
                f"build_dir: {root.as_posix()}\n"
                "domains:\n"
                "  - name: m30_ble_dfu_hil\n"
                f"    build_dir: {app.as_posix()}\n"
                "  - name: mcuboot\n"
                f"    build_dir: {boot.as_posix()}\n"
                "flash_order:\n"
                "  - mcuboot\n"
                "  - m30_ble_dfu_hil\n",
                encoding="utf-8",
            )
            (app / "zephyr/.config").write_text(
                "CONFIG_BOOTLOADER_MCUBOOT=y\n"
                "CONFIG_BT_SMP_SC_PAIR_ONLY=y\n"
                "CONFIG_BT_SMP_MIN_ENC_KEY_SIZE=16\n"
                "CONFIG_BT_L2CAP_TX_MTU=247\n",
                encoding="utf-8",
            )
            (boot / "zephyr/.config").write_text(
                "CONFIG_FLASH=y\n"
                "CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y\n"
                "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION=y\n"
                "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION_SECURITY_COUNTER=y\n"
                f'CONFIG_BOOT_SIGNATURE_KEY_FILE="{trust_key.as_posix()}"\n',
                encoding="utf-8",
            )
            (app / "build.ninja").write_text(
                f'M30_DFU_CORE_REVISION=\\"{core_revision}\\"\n',
                encoding="utf-8",
            )
            boot_hex = boot / "zephyr/zephyr.hex"
            signed_hex = app / "zephyr/zephyr.signed.hex"
            boot_hex.write_text(":00000001FF\n", encoding="ascii")
            signed_hex.write_text(":00000001FF\n", encoding="ascii")
            with mock.patch.object(
                HIL_RUNNER, "validate_build_record", return_value={}
            ), mock.patch.object(HIL_RUNNER, "git_revision", return_value="b" * 40):
                build = HIL_RUNNER.collect_central_build(
                    str(root), core_revision, trust_key.resolve()
                )
            self.assertEqual(build.boot_hex, boot_hex)
            self.assertEqual(build.signed_hex, signed_hex)
            self.assertIn("bootloader_config_sha256", build.record)
            self.assertIn("domains_sha256", build.record)

    def test_build_record_pins_the_bundled_gnu_compiler_identity(self) -> None:
        """! @brief build record의 compiler ID·version과 Toolchain bundle을 함께 고정합니다. """

        with tempfile.TemporaryDirectory(prefix="n54-m30-build-record-") as directory:
            root = Path(directory)
            image = root / "zephyr" / "zephyr.hex"
            image.parent.mkdir()
            image.write_text(":00000001FF\n", encoding="ascii")
            digest = "1" * 64
            record = root / "nucode_arduino_core_build.yml"
            record.write_text(
                "nucode_arduino_core:\n"
                "  core_revision: 'aabbccddeeff'\n"
                f"  core_source_sha256: '{digest}'\n"
                f"  application_source_sha256: '{digest}'\n"
                "  board_revision: '112233445566'\n"
                f"  board_source_sha256: '{digest}'\n"
                "  ncs_revision: '99553055607b'\n"
                "  zephyr_revision: 'bf801e4e3d19'\n"
                "  board: 'nrf54l15dk'\n"
                "  board_qualifiers: 'nrf54l15/cpuapp/nu54dk'\n"
                "  toolchain_variant: 'zephyr'\n"
                "  toolchain_path: 'C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk'\n"
                "  cxx_compiler: 'GNU 14.3.0'\n",
                encoding="utf-8",
            )
            expected_digests = {
                "core_source_sha256": digest,
                "application_source_sha256": digest,
                "board_source_sha256": digest,
            }
            with mock.patch(
                "ble_pair_hil_common.current_source_digests",
                return_value=expected_digests,
            ):
                values = HIL_RUNNER.validate_build_record(
                    image,
                    "aabbccddeeff" + "0" * 28,
                    "112233445566" + "0" * 28,
                    HIL_TARGET,
                )
                self.assertEqual(values["cxx_compiler"], "GNU 14.3.0")
                record.write_text(
                    record.read_text(encoding="utf-8").replace(
                        "GNU 14.3.0", "GNU 14.2.0"
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    HIL_RUNNER.BlePairHilFailure, "C\\+\\+ compiler"
                ):
                    HIL_RUNNER.validate_build_record(
                        image,
                        "aabbccddeeff" + "0" * 28,
                        "112233445566" + "0" * 28,
                        HIL_TARGET,
                    )


if __name__ == "__main__":
    unittest.main()
