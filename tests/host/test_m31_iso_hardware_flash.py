#!/usr/bin/env python3
"""! @brief M31 ISO의 sector programming과 비파괴 hardware reset 분리를 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HIL = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import ble_pair_hil_common as common  # noqa: E402


class M31IsoHardwareFlashTests(unittest.TestCase):
    """! @brief flash 완료와 app 재시작을 서로 독립적인 성공 조건으로 검사합니다. """

    def test_sector_flash_requires_explicit_hardware_reset(self) -> None:
        """! @brief UID sector flash 뒤 CMSIS-DAP hardware reset 성공을 확인합니다. """
        flash = SimpleNamespace(returncode=0, stdout=b"programmed 274432 bytes", stderr=b"")
        reset = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        with patch.object(common.subprocess, "run", side_effect=(flash, reset)) as run:
            mode, byte_count = common.flash_image_pyocd(
                "central", "a" * 32, Path("image.hex"), 120.0, hardware_reset=True
            )
        self.assertEqual(("pyocd-sector-hw-reset", "274432"), (mode, byte_count))
        self.assertEqual(2, run.call_count)
        flash_command = run.call_args_list[0].args[0]
        reset_command = run.call_args_list[1].args[0]
        self.assertEqual("flash", flash_command[flash_command.index("pyocd") + 1])
        self.assertEqual("sector", flash_command[flash_command.index("--erase") + 1])
        self.assertIn("--no-reset", flash_command)
        self.assertNotIn("chip", flash_command)
        self.assertEqual("reset", reset_command[reset_command.index("pyocd") + 1])
        self.assertEqual("hw", reset_command[reset_command.index("--method") + 1])
        self.assertNotIn("--erase", reset_command)
        self.assertEqual("a" * 32, reset_command[reset_command.index("--uid") + 1])

    def test_programming_does_not_hide_hardware_reset_failure(self) -> None:
        """! @brief byte program 성공 뒤 reset 실패를 HIL PASS로 올리지 않습니다. """
        flash = SimpleNamespace(returncode=0, stdout=b"programmed 274432 bytes", stderr=b"")
        reset = SimpleNamespace(returncode=1, stdout=b"", stderr=b"No ACK")
        with patch.object(common.subprocess, "run", side_effect=(flash, reset)):
            with self.assertRaisesRegex(common.BlePairHilFailure, "hardware reset 실패"):
                common.flash_image_pyocd(
                    "central", "a" * 32, Path("image.hex"), 120.0, hardware_reset=True
                )


if __name__ == "__main__":
    unittest.main()
