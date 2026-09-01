#!/usr/bin/env python3
"""! @brief AC-03 두 보드 HIL runner/parser의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("ac03_storage.py")
SPEC = importlib.util.spec_from_file_location("nu54_ac03_storage", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
NONCE = b"0123456789abcdef0123456789abcdef"


def valid_transcript() -> bytes:
    """! @brief reset 세 번과 정리를 포함한 유효 protocol을 반환합니다. """

    return b"\n".join(
        (
            b"NUCODE_AC03_BOOT:schema=1:stage=verify_corruption:nonce=" + b"f" * 32,
            b"NUCODE_AC03_CLEARED:PASS",
            b"NUCODE_AC03_BOOT:schema=1:stage=idle:nonce=none",
            MODULE.SEED_TOKEN,
            b"NUCODE_AC03_BOOT:schema=1:stage=verify_persistence:nonce=" + NONCE,
            MODULE.PERSISTENCE_TOKEN,
            MODULE.CORRUPTION_TOKEN,
            b"NUCODE_AC03_BOOT:schema=1:stage=verify_corruption:nonce=" + NONCE,
            MODULE.RECOVERY_TOKEN,
            b"NUCODE_AC03_BOOT:schema=1:stage=verify_recovery:nonce=" + NONCE,
            b"NUCODE_AC03_FINAL:PASS:nonce=" + NONCE
            + b":reset_persistence=1:corruption_recovery=1:cleanup=1",
        )
    ) + b"\n"


class AC03StorageHilTests(unittest.TestCase):
    """! @brief parser, 두 UID 선택과 파괴 승인 경계를 검증합니다. """

    def test_accepts_complete_reset_and_recovery_protocol(self) -> None:
        """! @brief 영속성·손상·명시 복구·정리가 모두 있을 때만 PASS입니다. """

        MODULE.parse_transcript(valid_transcript(), NONCE.decode("ascii"))

    def test_rejects_missing_reordered_or_failed_phase(self) -> None:
        """! @brief 빠진 단계, 순서 변경과 target FAIL을 모두 거부합니다. """

        with self.assertRaises(MODULE.AC03HilFailure):
            MODULE.parse_transcript(
                valid_transcript().replace(MODULE.RECOVERY_TOKEN + b"\n", b""),
                NONCE.decode("ascii"),
            )
        reordered = valid_transcript().replace(
            MODULE.PERSISTENCE_TOKEN + b"\n" + MODULE.CORRUPTION_TOKEN,
            MODULE.CORRUPTION_TOKEN + b"\n" + MODULE.PERSISTENCE_TOKEN,
        )
        with self.assertRaises(MODULE.AC03HilFailure):
            MODULE.parse_transcript(reordered, NONCE.decode("ascii"))
        with self.assertRaisesRegex(MODULE.AC03HilFailure, "FAIL"):
            MODULE.parse_transcript(
                valid_transcript() + b"NUCODE_AC03_FAIL:phase=late:error=-5\n",
                NONCE.decode("ascii"),
            )

    def test_rejects_wrong_final_nonce_and_trailing_token(self) -> None:
        """! @brief 다른 실행의 final과 final 뒤 위조 token을 거부합니다. """

        wrong = valid_transcript().replace(
            b"NUCODE_AC03_FINAL:PASS:nonce=" + NONCE,
            b"NUCODE_AC03_FINAL:PASS:nonce=" + b"a" * 32,
        )
        with self.assertRaises(MODULE.AC03HilFailure):
            MODULE.parse_transcript(wrong, NONCE.decode("ascii"))
        with self.assertRaisesRegex(MODULE.AC03HilFailure, "뒤"):
            MODULE.parse_transcript(
                valid_transcript() + b"NUCODE_AC03_CLEARED:PASS\n",
                NONCE.decode("ascii"),
            )

    def test_requires_two_distinct_board_ids(self) -> None:
        """! @brief runner가 한 보드 또는 같은 UID 두 번을 허용하지 않습니다. """

        fake_serial = (mock.Mock(), mock.Mock())
        with mock.patch.object(MODULE, "import_pyserial", return_value=fake_serial):
            with self.assertRaisesRegex(MODULE.AC03HilFailure, "두 번"):
                MODULE.main(["--board-id", "one", "--discover-only"])
            with self.assertRaisesRegex(MODULE.AC03HilFailure, "서로 다른"):
                MODULE.main(
                    ["--board-id", "same", "--board-id", "same", "--discover-only"]
                )

    def test_requires_explicit_destructive_approval_before_image_access(self) -> None:
        """! @brief 승인 없이는 HEX 확인이나 flash보다 먼저 중단합니다. """

        fake_serial = (mock.Mock(), mock.Mock())
        with mock.patch.object(MODULE, "import_pyserial", return_value=fake_serial), \
             mock.patch.object(MODULE, "validate_hex_image") as validate:
            with self.assertRaisesRegex(MODULE.AC03HilFailure, "승인"):
                MODULE.main(
                    [
                        "--board-id", "one",
                        "--board-id", "two",
                        "--hex", "missing.hex",
                    ]
                )
            validate.assert_not_called()

    def test_target_source_performs_real_corruption_and_cleanup(self) -> None:
        """! @brief HIL image가 합성 token이 아닌 raw 손상과 실제 reset을 수행합니다. """

        source = (
            MODULE_PATH.parents[2]
            / "zephyr"
            / "ac03_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for marker in (
            'settings_save_one(eeprom_key, malformed',
            "EEPROMError::corrupt",
            "EEPROM.reset",
            "flash_area_erase",
            "LittleFS.begin(false)",
            "LittleFS.format()",
            "sys_reboot(SYS_REBOOT_COLD)",
            "LittleFS.remove(filesystem_path)",
            "settings_delete(state_key)",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    with mock.patch("sys.stderr", io.StringIO()):
        unittest.main()
