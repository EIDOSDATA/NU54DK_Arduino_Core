#!/usr/bin/env python3
"""! @brief AC-01 loopback HIL parser와 fail-closed 경계를 장치 없이 검증합니다. """

from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("ac01_gpio_hil.py")
MODULE_SPEC = importlib.util.spec_from_file_location("ac01_gpio_hil", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"AC-01 HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)


## @brief exact AC-01 성공 transcript를 생성합니다.
def valid_transcript() -> bytes:
    lines = (
        MODULE.READY_TOKEN,
        MODULE.OPEN_DRAIN_TOKEN,
        MODULE.LOW_LEVEL_TOKEN,
        MODULE.HIGH_LEVEL_TOKEN,
        b"NUCODE_AC01_PULSE:PASS:short_us=1492:long_us=20014:timeout_us=0",
        MODULE.SHIFT_TOKEN,
        b"NUCODE_AC01_INTERRUPT_MASK:PASS:masked=0:nested=0:restored=1:"
        b"heartbeat_delta=9",
        MODULE.FINAL_PASS_TOKEN,
    )
    return b"Zephyr boot log\r\n" + b"\r\n".join(lines) + b"\r\n"


class Ac01GpioHilTests(unittest.TestCase):
    """! @brief AC-01 token 순서, 값 범위와 명시적 fixture를 고정합니다. """

    def test_accepts_exact_complete_protocol(self) -> None:
        """! @brief 완전한 8-line protocol의 계측값을 승인합니다. """

        result = MODULE.parse_transcript(valid_transcript())
        self.assertEqual(result.short_pulse_us, 1492)
        self.assertEqual(result.long_pulse_us, 20014)
        self.assertEqual(result.heartbeat_delta, 9)

    def test_rejects_target_failure_missing_and_duplicate_tokens(self) -> None:
        """! @brief target FAIL, 누락과 최종 PASS 중복을 모두 거부합니다. """

        with self.assertRaisesRegex(MODULE.Ac01HilFailure, "실패"):
            MODULE.parse_transcript(
                b"NUCODE_AC01_GPIO_HIL_FAIL:stage=LOW_ATTACH:gpio_error=1\n"
            )
        with self.assertRaisesRegex(MODULE.Ac01HilFailure, "line 수"):
            MODULE.parse_transcript(valid_transcript().replace(MODULE.SHIFT_TOKEN, b""))
        with self.assertRaisesRegex(MODULE.Ac01HilFailure, "line 수"):
            MODULE.parse_transcript(valid_transcript() + MODULE.FINAL_PASS_TOKEN + b"\n")

    def test_rejects_reordered_level_contract(self) -> None:
        """! @brief LOW/HIGH level 검증 순서가 바뀐 transcript를 거부합니다. """

        transcript = valid_transcript().replace(MODULE.LOW_LEVEL_TOKEN, b"TEMP", 1)
        transcript = transcript.replace(MODULE.HIGH_LEVEL_TOKEN, MODULE.LOW_LEVEL_TOKEN, 1)
        transcript = transcript.replace(b"TEMP", MODULE.HIGH_LEVEL_TOKEN, 1)
        with self.assertRaisesRegex(MODULE.Ac01HilFailure, "순서"):
            MODULE.parse_transcript(transcript)

    def test_rejects_pulse_range_and_stopped_scheduler(self) -> None:
        """! @brief target token이 있더라도 pulse 범위와 heartbeat 0을 재검증합니다. """

        bad_pulse = valid_transcript().replace(b"short_us=1492", b"short_us=1")
        with self.assertRaisesRegex(MODULE.Ac01HilFailure, "short pulse"):
            MODULE.parse_transcript(bad_pulse)
        stopped = valid_transcript().replace(b"heartbeat_delta=9", b"heartbeat_delta=0")
        with self.assertRaisesRegex(MODULE.Ac01HilFailure, "scheduler"):
            MODULE.parse_transcript(stopped)

    def test_board_identity_and_loopback_acknowledgement_are_explicit(self) -> None:
        """! @brief 두 보드 환경에서 UID와 물리 점퍼 승인을 생략할 수 없게 고정합니다. """

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.parse_arguments([])
        defaults = MODULE.parse_arguments(["--board-id", "fixture"])
        acknowledged = MODULE.parse_arguments(
            ["--board-id", "fixture", "--acknowledge-loopback"]
        )
        self.assertFalse(defaults.acknowledge_loopback)
        self.assertTrue(acknowledged.acknowledge_loopback)
        self.assertEqual(defaults.result_timeout, 45.0)


if __name__ == "__main__":
    unittest.main()
