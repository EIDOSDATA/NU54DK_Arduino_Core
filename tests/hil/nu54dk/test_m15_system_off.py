#!/usr/bin/env python3
"""! @brief M15 System OFF HIL protocol과 evidence를 장치 없이 회귀 검증합니다. """

from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("m15_system_off.py")
MODULE_SPEC = importlib.util.spec_from_file_location("m15_system_off", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"M15 System OFF HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)


## @brief 정확한 ARM 요청·System OFF·SW0 wake 성공 transcript를 생성합니다.
def valid_transcript() -> bytes:
    lines = (
        MODULE.READY_TOKEN,
        MODULE.REQUEST_TOKEN,
        MODULE.ACTION_TOKEN,
        MODULE.ENTERING_TOKEN,
        MODULE.WAKE_BOOT_TOKEN,
        MODULE.WAKE_TOKEN,
        MODULE.FINAL_PASS_TOKEN,
    )
    return b"Zephyr boot log\r\n" + b"\r\n".join(lines) + b"\r\n"


class ScriptedSerial:
    """! @brief capture_protocol 시험용 고정 UART입니다. """

    def __init__(self, chunks: list[bytes]) -> None:
        """! @brief 순서대로 반환할 RX chunk를 저장합니다. """

        self.chunks = list(chunks)
        self.writes: list[bytes] = []
        self.flush_count = 0

    @property
    def in_waiting(self) -> int:
        """! @brief 다음 RX chunk의 byte 수를 반환합니다. """

        return len(self.chunks[0]) if self.chunks else 0

    def read(self, _size: int) -> bytes:
        """! @brief 다음 RX chunk 하나를 반환합니다. """

        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data: bytes) -> int:
        """! @brief runner가 target에 보낸 byte를 기록합니다. """

        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        """! @brief 명시적 ARM flush 횟수를 기록합니다. """

        self.flush_count += 1


class StepClock:
    """! @brief 매 호출마다 고정 간격으로 증가하는 monotonic clock입니다. """

    def __init__(self, step: float = 0.25) -> None:
        """! @brief 초기 시각과 호출 간격을 설정합니다. """

        self.value = -step
        self.step = step

    def __call__(self) -> float:
        """! @brief 다음 단조 증가 시각을 반환합니다. """

        self.value += self.step
        return self.value

class M15SystemOffHilTests(unittest.TestCase):
    """! @brief 명령 gate, protocol, 무응답 시간과 증적 경계를 검증합니다. """

    def test_accepts_only_exact_sw0_low_power_wake_sequence(self) -> None:
        """! @brief SW0/P1.13와 LOW_POWER_WAKE 전체 순서만 승인합니다. """

        result = MODULE.parse_transcript(valid_transcript())
        self.assertEqual(result.wake_source, "SW0")
        self.assertEqual(result.gpio, "P1.13")
        self.assertEqual(result.reset_cause, "LOW_POWER_WAKE")

    def test_rejects_target_failure_missing_wake_and_trailing_token(self) -> None:
        """! @brief FAIL, wake 누락과 PASS 뒤 위조 token을 모두 거부합니다. """

        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "실패"):
            MODULE.parse_transcript(
                b"NUCODE_M15_SYSTEM_OFF_FAIL:stage=ENTER_SYSTEM_OFF_BUTTON\n"
            )

        missing = valid_transcript().replace(MODULE.WAKE_TOKEN + b"\r\n", b"")
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "순서/값"):
            MODULE.parse_transcript(missing)

        trailing = valid_transcript() + MODULE.FINAL_PASS_TOKEN + b"\n"
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "순서/값"):
            MODULE.parse_transcript(trailing)

    def test_rejects_wrong_button_gpio_and_reset_cause(self) -> None:
        """! @brief 다른 wake source나 합성 reset 원인을 PASS로 승격하지 않습니다. """

        wrong_gpio = valid_transcript().replace(b"gpio=P1.13", b"gpio=P1.09", 1)
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "순서/값"):
            MODULE.parse_transcript(wrong_gpio)

        wrong_reset = valid_transcript().replace(
            b"reset=LOW_POWER_WAKE", b"reset=SOFTWARE"
        )
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "순서/값"):
            MODULE.parse_transcript(wrong_reset)

    def test_no_pass_is_claimed_before_observed_wake(self) -> None:
        """! @brief 원자적 진입 요청을 실제 wake 전에 PASS로 표시하지 않습니다. """

        lines = valid_transcript().replace(b"\r", b"").split(b"\n")
        wake_index = lines.index(MODULE.WAKE_BOOT_TOKEN)
        self.assertNotIn(b":PASS", b"\n".join(lines[:wake_index]))

    def test_capture_sends_arm_once_and_waits_before_button_prompt(self) -> None:
        """! @brief READY 뒤 ARM 한 번을 보내고 실제 wake 뒤에만 PASS합니다. """

        chunks = [line + b"\r\n" for line in (
            MODULE.READY_TOKEN,
            MODULE.REQUEST_TOKEN,
            MODULE.ACTION_TOKEN,
            MODULE.ENTERING_TOKEN,
            b"",
            b"",
            b"",
            b"",
            MODULE.WAKE_BOOT_TOKEN,
            MODULE.WAKE_TOKEN,
            MODULE.FINAL_PASS_TOKEN,
        )]
        serial = ScriptedSerial(chunks)
        clock = StepClock(step=0.5)
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            capture = MODULE.capture_protocol(
                serial,
                30.0,
                monotonic=clock,
            )
        self.assertEqual(serial.writes, [b"ARM\n"])
        self.assertEqual(serial.flush_count, 1)
        self.assertGreaterEqual(
            capture.entering_to_wake_ms, MODULE.MINIMUM_ENTERING_TO_PROMPT_MS
        )
        MODULE.parse_transcript(capture.transcript)

    def test_minimum_entering_to_wake_interval_is_fail_closed(self) -> None:
        """! @brief 2초보다 짧은 ENTERING 요청·wake 간격을 승인하지 않습니다. """

        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "너무 짧"):
            MODULE.validate_entering_to_wake_interval(10.0, 11.999)
        self.assertEqual(
            MODULE.validate_entering_to_wake_interval(10.0, 12.0), 2000
        )

    def test_capture_rejects_wake_before_press_now_prompt(self) -> None:
        """! @brief 2초 안내 대기 중 깨어난 target을 buffered UART로 오인하지 않습니다. """

        chunks = [
            line + b"\r\n"
            for line in (
                MODULE.READY_TOKEN,
                MODULE.REQUEST_TOKEN,
                MODULE.ACTION_TOKEN,
                MODULE.ENTERING_TOKEN,
                MODULE.WAKE_BOOT_TOKEN,
                MODULE.WAKE_TOKEN,
                MODULE.FINAL_PASS_TOKEN,
            )
        ]
        serial = ScriptedSerial(chunks)
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            with self.assertRaisesRegex(MODULE.TranscriptFailure, "PRESS NOW|너무 짧"):
                MODULE.capture_protocol(serial, 30.0, monotonic=StepClock(step=0.1))

    def test_board_id_acknowledgement_and_timeout_are_explicit(self) -> None:
        """! @brief 다중 보드 오선택과 암묵적 수동 시험을 기본값에서 차단합니다. """

        defaults = MODULE.parse_arguments(["--board-id", "abc123"])
        acknowledged = MODULE.parse_arguments(
            ["--board-id", "abc123", "--acknowledge-button-wake"]
        )
        self.assertEqual(defaults.board_id, "abc123")
        self.assertFalse(defaults.acknowledge_button_wake)
        self.assertTrue(acknowledged.acknowledge_button_wake)
        self.assertEqual(defaults.result_timeout, 240.0)

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.parse_arguments([])

    def test_evidence_binds_image_transcript_probe_and_manual_action(self) -> None:
        """! @brief PASS JSON이 exact byte와 유일한 SW0 사용자 동작을 기록합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-system-off-") as temporary:
            root = Path(temporary)
            image = root / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            transcript = valid_transcript()
            capture = MODULE.CaptureResult(transcript, 2345)
            transcript_path = root / "result.transcript.log"
            evidence = MODULE.build_evidence(
                core_revision="a" * 40,
                board_revision="b" * 40,
                board_id="fixture-board",
                image=image,
                image_size=image.stat().st_size,
                image_sha256=MODULE.file_sha256(image),
                flash_sequence="42",
                flash_byte_count="1234",
                port_name="COM9",
                transcript_path=transcript_path,
                capture=capture,
                result=MODULE.parse_transcript(transcript),
                build_record={"record_name": "nucode_arduino_core_build.yml"},
            )
            encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            self.assertEqual(evidence["status"], "passed")
            self.assertEqual(evidence["manual_fixture"]["logical_button"], "SW0")
            self.assertEqual(
                evidence["result"]["observed_entering_to_wake_ms"], 2345
            )
            self.assertEqual(evidence["image"]["sha256"], MODULE.file_sha256(image))
            self.assertNotIn(str(root), encoded)

    def test_existing_evidence_requires_explicit_overwrite(self) -> None:
        """! @brief 이전 PASS 증적을 자동 덮어쓰지 않는지 확인합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-evidence-") as temporary:
            evidence = Path(temporary) / "m15.json"
            evidence.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "자동 덮어쓰지"):
                MODULE.prepare_output_paths(str(evidence), False)
            actual, transcript = MODULE.prepare_output_paths(str(evidence), True)
            self.assertEqual(actual, evidence.resolve())
            self.assertEqual(transcript.name, "m15.transcript.log")
            self.assertFalse(evidence.exists())

    def test_dirty_imported_helper_or_board_source_is_rejected(self) -> None:
        """! @brief 공용 digest/probe helper 변경을 System OFF 실행 전에 거부합니다. """

        clean = MODULE.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="", stderr=""
        )
        with mock.patch.object(
            MODULE.subprocess, "run", side_effect=(clean, clean)
        ) as run:
            MODULE.validate_source_clean()
        core_command = run.call_args_list[0].args[0]
        self.assertIn("tests/hil/nu54dk/m14_pin_hil.py", core_command)
        self.assertIn("tests/hil/nu54dk/m6_serial_echo.py", core_command)

        for helper_path in (
            "tests/hil/nu54dk/m14_pin_hil.py",
            "tests/hil/nu54dk/m6_serial_echo.py",
        ):
            dirty_helper = MODULE.subprocess.CompletedProcess(
                args=["git"],
                returncode=0,
                stdout=f" M {helper_path}\n",
                stderr="",
            )
            with mock.patch.object(
                MODULE.subprocess, "run", side_effect=(dirty_helper, clean)
            ), self.assertRaisesRegex(
                MODULE.SystemOffHilFailure, "commit되지 않은"
            ):
                MODULE.validate_source_clean()

        dirty_board = MODULE.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout=" M boards/nucode/nu54dk/board.yml\n", stderr=""
        )
        with mock.patch.object(
            MODULE.subprocess, "run", side_effect=(clean, dirty_board)
        ), self.assertRaisesRegex(MODULE.SystemOffHilFailure, "submodule"):
            MODULE.validate_source_clean()


if __name__ == "__main__":
    unittest.main()
