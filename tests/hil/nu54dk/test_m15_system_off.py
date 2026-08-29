#!/usr/bin/env python3
"""! @brief M15 schema 2 System OFF HIL을 장치 없이 회귀 검증합니다. """

from __future__ import annotations

from contextlib import redirect_stderr
from datetime import datetime, timezone
import importlib.util
import io
import json
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

FIXED_NONCE = "0123456789abcdef0123456789abcdef"
SUPPORTED_RESET_CAUSES = 131071


## @brief 동일 nonce의 timed GRTC→SW0 성공 transcript를 생성합니다.
def valid_transcript(
    nonce: str = FIXED_NONCE,
    *,
    timed_cause: int = MODULE.RESET_CLOCK,
    timed_supported: int = SUPPORTED_RESET_CAUSES,
    button_cause: int = MODULE.RESET_LOW_POWER_WAKE,
    button_supported: int = SUPPORTED_RESET_CAUSES,
) -> bytes:
    lines = (
        MODULE.TIMED_READY_TOKEN,
        (
            "NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=TIMED:"
            f"nonce={nonce}:duration_us=2000000"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=TIMED:"
            f"nonce={nonce}:mode=GRTC_WAKE"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=TIMED_WAKE:"
            f"nonce={nonce}:cause={timed_cause}:supported={timed_supported}"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=TIMED:"
            f"nonce={nonce}:source=GRTC:cause=2048"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=BUTTON:"
            f"command=ARM_BUTTON:nonce={nonce}:wake=SW0:gpio=P1.13:active=LOW"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=BUTTON:"
            f"nonce={nonce}:wake=SW0:gpio=P1.13:active=LOW"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_ACTION:schema=2:phase=BUTTON:"
            f"nonce={nonce}:expected=PRESS_LOW:host_wait_ms=2000"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=BUTTON:"
            f"nonce={nonce}:mode=GPIO_WAKE"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=BUTTON_WAKE:"
            f"nonce={nonce}:cause={button_cause}:supported={button_supported}"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=BUTTON:"
            f"nonce={nonce}:source=SW0:gpio=P1.13:active=LOW:cause=128"
        ).encode("ascii"),
        (
            "NUCODE_M15_SYSTEM_OFF_PASS:schema=2:"
            f"nonce={nonce}:timed=PASS:button=PASS"
        ).encode("ascii"),
    )
    return b"Zephyr boot log\r\n" + b"\r\n".join(lines) + b"\r\n"


## @brief 성공 transcript를 capture용 개별 UART chunk로 나눕니다.
def successful_chunks() -> list[bytes]:
    lines = valid_transcript().replace(b"\r", b"").split(b"\n")
    protocol = [line for line in lines if line.startswith(MODULE.PROTOCOL_PREFIX)]
    chunks: list[bytes] = []
    for line in protocol:
        chunks.append(line + b"\r\n")
        if MODULE.TIMED_ENTERING_PATTERN.fullmatch(line):
            chunks.extend([b""] * 4)
        if MODULE.BUTTON_ENTERING_PATTERN.fullmatch(line):
            chunks.extend([b""] * 4)
    return chunks


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

    def __init__(self, step: float = 0.5) -> None:
        """! @brief 초기 시각과 호출 간격을 설정합니다. """

        self.value = -step
        self.step = step

    def __call__(self) -> float:
        """! @brief 다음 단조 증가 시각을 반환합니다. """

        self.value += self.step
        return self.value


class M15SystemOffHilTests(unittest.TestCase):
    """! @brief nonce, reset cause, 수동 gate와 안전 증적을 검증합니다. """

    def test_accepts_exact_schema_two_timed_then_button_sequence(self) -> None:
        """! @brief CLOCK과 LOW_POWER_WAKE 단일 원인을 모두 요구합니다. """

        result = MODULE.parse_transcript(valid_transcript())
        self.assertEqual(result.nonce, FIXED_NONCE)
        self.assertEqual(result.timed_reset_cause, MODULE.RESET_CLOCK)
        self.assertEqual(result.button_reset_cause, MODULE.RESET_LOW_POWER_WAKE)
        self.assertEqual((result.wake_source, result.gpio), ("SW0", "P1.13"))

    def test_rejects_failure_missing_line_and_trailing_protocol(self) -> None:
        """! @brief FAIL, 누락과 최종 PASS 뒤 추가 protocol을 거부합니다. """

        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "실패"):
            MODULE.parse_transcript(b"NUCODE_M15_SYSTEM_OFF_FAIL:stage=TIMED_RESET\n")

        missing = valid_transcript().replace(
            (
                "NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=TIMED:"
                f"nonce={FIXED_NONCE}:source=GRTC:cause=2048\r\n"
            ).encode("ascii"),
            b"",
        )
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "순서/값"):
            MODULE.parse_transcript(missing)

        trailing = valid_transcript() + MODULE.TIMED_READY_TOKEN + b"\n"
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "예상하지 않은"):
            MODULE.parse_transcript(trailing)

    def test_rejects_nonce_mismatch(self) -> None:
        """! @brief 재부팅 경계를 다른 실행의 token으로 조합하지 않습니다. """

        other = "fedcba9876543210fedcba9876543210"
        mismatched = valid_transcript().replace(
            f"nonce={FIXED_NONCE}:mode=GPIO_WAKE".encode("ascii"),
            f"nonce={other}:mode=GPIO_WAKE".encode("ascii"),
        )
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "nonce"):
            MODULE.parse_transcript(mismatched)

    def test_reset_cause_is_exact_supported_and_never_debug(self) -> None:
        """! @brief CLOCK·LOW_POWER_WAKE 외 원인과 RESET_DEBUG 혼합을 거부합니다. """

        for timed_cause in (MODULE.RESET_DEBUG, MODULE.RESET_CLOCK | MODULE.RESET_DEBUG):
            with self.subTest(timed_cause=timed_cause), self.assertRaisesRegex(
                MODULE.SystemOffHilFailure, "RESET_DEBUG"
            ):
                MODULE.parse_transcript(valid_transcript(timed_cause=timed_cause))

        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "단일 기대값"):
            MODULE.parse_transcript(valid_transcript(button_cause=16))
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "supported mask"):
            MODULE.parse_transcript(valid_transcript(timed_supported=0))

    def test_capture_requires_two_confirmations_and_sends_bound_nonce(self) -> None:
        """! @brief SWD 격리 뒤 timed ARM, SW0 release 뒤 button ARM만 보냅니다. """

        serial = ScriptedSerial(successful_chunks())
        prompts: list[str] = []

        def confirm(prompt: str) -> str:
            prompts.append(prompt)
            return "DISABLE_SWD_ONLY" if len(prompts) == 1 else "SW0_RELEASED"

        fixed_time = datetime(2026, 8, 30, tzinfo=timezone.utc)
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            capture = MODULE.capture_protocol(
                serial,
                30.0,
                monotonic=StepClock(),
                confirm=confirm,
                nonce_factory=lambda count: FIXED_NONCE if count == 16 else "",
                utc_now=lambda: fixed_time,
            )
        self.assertEqual(
            serial.writes,
            [
                f"ARM_TIMED:{FIXED_NONCE}\n".encode("ascii"),
                f"ARM_BUTTON:{FIXED_NONCE}\n".encode("ascii"),
            ],
        )
        self.assertEqual(serial.flush_count, 2)
        self.assertEqual(len(prompts), 2)
        self.assertIn("DISABLE_UART", prompts[0])
        self.assertIn("SW0(P1.13)", prompts[1])
        self.assertGreaterEqual(
            capture.timed_entering_to_wake_ms, MODULE.MINIMUM_TIMED_WAKE_MS
        )
        self.assertGreaterEqual(
            capture.button_entering_to_wake_ms, MODULE.MINIMUM_BUTTON_PROMPT_MS
        )
        self.assertEqual(capture.nonce, FIXED_NONCE)

    def test_wrong_swd_confirmation_stops_before_any_arm(self) -> None:
        """! @brief 모호한 switch 상태에서는 UART ARM조차 전송하지 않습니다. """

        serial = ScriptedSerial([MODULE.TIMED_READY_TOKEN + b"\n"])
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "DISABLE_SWD_ONLY"):
                MODULE.capture_protocol(
                    serial,
                    30.0,
                    monotonic=StepClock(),
                    confirm=lambda _prompt: "yes",
                )
        self.assertEqual(serial.writes, [])

    def test_eof_and_uart_failure_preserve_partial_transcript(self) -> None:
        """! @brief 격리 확인 EOF와 후속 UART 단절도 수집 byte를 보존합니다. """

        ready = MODULE.TIMED_READY_TOKEN + b"\r\n"
        eof_serial = ScriptedSerial([ready])

        def raise_eof(_prompt: str) -> str:
            raise EOFError("stdin closed")

        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            with self.assertRaises(MODULE.TranscriptFailure) as caught:
                MODULE.capture_protocol(
                    eof_serial,
                    30.0,
                    monotonic=StepClock(),
                    confirm=raise_eof,
                )
        self.assertEqual(caught.exception.transcript, ready)
        self.assertEqual(eof_serial.writes, [])

        class FailingAfterReadySerial(ScriptedSerial):
            """! @brief READY 처리 뒤 UART RX 단절을 발생시킵니다. """

            @property
            def in_waiting(self) -> int:
                if not self.chunks:
                    raise OSError("UART disconnected")
                return super().in_waiting

        failed_serial = FailingAfterReadySerial([ready])
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            with self.assertRaises(MODULE.TranscriptFailure) as caught:
                MODULE.capture_protocol(
                    failed_serial,
                    30.0,
                    monotonic=StepClock(),
                    confirm=lambda _prompt: "DISABLE_SWD_ONLY",
                    nonce_factory=lambda count: FIXED_NONCE if count == 16 else "",
                )
        self.assertEqual(caught.exception.transcript, ready)
        self.assertEqual(
            failed_serial.writes,
            [f"ARM_TIMED:{FIXED_NONCE}\n".encode("ascii")],
        )

        class FailingWriteSerial(ScriptedSerial):
            """! @brief SWD 격리 뒤 UART TX 단절을 발생시킵니다. """

            def write(self, _data: bytes) -> int:
                raise OSError("UART write failed")

        write_failed_serial = FailingWriteSerial([ready])
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            with self.assertRaises(MODULE.TranscriptFailure) as caught:
                MODULE.capture_protocol(
                    write_failed_serial,
                    30.0,
                    monotonic=StepClock(),
                    confirm=lambda _prompt: "DISABLE_SWD_ONLY",
                    nonce_factory=lambda count: FIXED_NONCE if count == 16 else "",
                )
        self.assertEqual(caught.exception.transcript, ready)

    def test_wake_timing_is_fail_closed(self) -> None:
        """! @brief 너무 빠르거나 느린 timed wake와 이른 SW0 wake를 거부합니다. """

        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "허용 범위"):
            MODULE.validate_timed_interval(10.0, 11.0)
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "허용 범위"):
            MODULE.validate_timed_interval(10.0, 20.001)
        self.assertEqual(MODULE.validate_timed_interval(10.0, 12.0), 2000)
        with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "너무 빠"):
            MODULE.validate_button_interval(10.0, 11.999)
        self.assertEqual(MODULE.validate_button_interval(10.0, 12.0), 2000)

    def test_acknowledgements_and_timeout_are_explicit(self) -> None:
        """! @brief interface switch와 버튼 승인을 서로 독립적으로 요구합니다. """

        defaults = MODULE.parse_arguments(["--board-id", "abc123"])
        acknowledged = MODULE.parse_arguments(
            [
                "--board-id",
                "abc123",
                "--acknowledge-interface-switch",
                "--acknowledge-button-wake",
            ]
        )
        self.assertFalse(defaults.acknowledge_interface_switch)
        self.assertFalse(defaults.acknowledge_button_wake)
        self.assertTrue(acknowledged.acknowledge_interface_switch)
        self.assertTrue(acknowledged.acknowledge_button_wake)
        self.assertEqual(defaults.result_timeout, 240.0)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.parse_arguments([])

    def test_flash_occurs_before_capture_and_only_once(self) -> None:
        """! @brief SWD 격리 prompt가 가능한 capture보다 flash가 먼저 한 번 실행됩니다. """

        events: list[str] = []

        class ContextSerial:
            """! @brief verify_system_off의 serial context를 흉내 냅니다. """

            def __enter__(self) -> "ContextSerial":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def reset_input_buffer(self) -> None:
                events.append("reset-input")

        serial_module = mock.Mock(
            EIGHTBITS=8,
            PARITY_NONE="N",
            STOPBITS_ONE=1,
            Serial=mock.Mock(return_value=ContextSerial()),
        )
        capture = MODULE.CaptureResult(
            valid_transcript(),
            FIXED_NONCE,
            2000,
            2500,
            "2026-08-30T00:00:00+00:00",
            "2026-08-30T00:00:01+00:00",
        )

        def flash() -> tuple[str, str]:
            events.append("flash")
            return "7", "1234"

        def fake_capture(*_args: object, **_kwargs: object) -> object:
            events.append("capture")
            return capture

        with mock.patch.object(MODULE, "capture_protocol", side_effect=fake_capture):
            sequence, byte_count, _, result = MODULE.verify_system_off(
                serial_module, "COM9", MODULE.DEFAULT_BAUD_RATE, flash, 30.0
            )
        self.assertEqual(events, ["reset-input", "flash", "capture"])
        self.assertEqual((sequence, byte_count), ("7", "1234"))
        self.assertEqual(result.nonce, FIXED_NONCE)

    def test_evidence_records_schema_two_switch_and_no_post_isolation_probe(self) -> None:
        """! @brief 증적이 switch 방향을 추측하지 않고 금지 동작을 false로 기록합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-system-off-") as temporary:
            root = Path(temporary)
            image = root / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            transcript = valid_transcript()
            capture = MODULE.CaptureResult(
                transcript,
                FIXED_NONCE,
                2000,
                2500,
                "2026-08-30T00:00:00+00:00",
                "2026-08-30T00:00:01+00:00",
            )
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
                transcript_path=root / "result.transcript.log",
                capture=capture,
                result=MODULE.parse_transcript(transcript),
                build_record={"record_name": "nucode_arduino_core_build.yml"},
            )
            encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            self.assertEqual(evidence["schema_version"], 2)
            self.assertTrue(evidence["manual_fixture"]["disable_swd_isolated"])
            self.assertFalse(evidence["manual_fixture"]["disable_uart_isolated"])
            self.assertFalse(evidence["manual_fixture"]["switch_direction_assumed"])
            self.assertFalse(evidence["safety"]["debug_access_after_isolation"])
            self.assertFalse(evidence["safety"]["flash_after_isolation"])
            self.assertEqual(
                evidence["result"]["timed"]["reset_cause_raw"], MODULE.RESET_CLOCK
            )
            self.assertEqual(
                evidence["result"]["button"]["reset_cause_raw"],
                MODULE.RESET_LOW_POWER_WAKE,
            )
            self.assertNotIn(str(root), encoded)

    def test_existing_evidence_is_preserved_until_atomic_pass_replace(self) -> None:
        """! @brief 실패한 재시험이 이전 PASS를 파괴하지 않는지 확인합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-evidence-") as temporary:
            evidence = Path(temporary) / "m15.json"
            previous = b'{"status":"previous-pass"}\n'
            evidence.write_bytes(previous)
            with self.assertRaisesRegex(MODULE.SystemOffHilFailure, "자동 덮어쓰지"):
                MODULE.prepare_output_paths(str(evidence), False)
            actual, transcript = MODULE.prepare_output_paths(str(evidence), True)
            self.assertEqual(actual, evidence.resolve())
            self.assertRegex(
                transcript.name,
                r"^m15\.attempt-[0-9a-f]{16}\.transcript\.log$",
            )
            self.assertEqual(evidence.read_bytes(), previous)
            self.assertFalse(transcript.exists())

            real_atomic_write = MODULE.atomic_write_bytes

            def fail_evidence_write(path: Path, payload: bytes) -> None:
                if path == evidence:
                    raise OSError("evidence replace failed")
                real_atomic_write(path, payload)

            replacement = {"schema_version": 2, "status": "passed"}
            with mock.patch.object(
                MODULE, "atomic_write_bytes", side_effect=fail_evidence_write
            ), self.assertRaisesRegex(OSError, "replace failed"):
                MODULE.write_pass_outputs(
                    evidence,
                    transcript,
                    b"new transcript\n",
                    replacement,
                )
            self.assertEqual(evidence.read_bytes(), previous)
            self.assertEqual(transcript.read_bytes(), b"new transcript\n")

            MODULE.write_pass_outputs(
                evidence,
                transcript,
                b"new transcript\n",
                replacement,
            )
            self.assertEqual(json.loads(evidence.read_text(encoding="utf-8")), replacement)

    def test_dirty_imported_helper_or_board_source_is_rejected(self) -> None:
        """! @brief 공용 helper나 board 변경을 실제 flash 전에 거부합니다. """

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

        dirty_helper = MODULE.subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=" M tests/hil/nu54dk/m6_serial_echo.py\n",
            stderr="",
        )
        with mock.patch.object(
            MODULE.subprocess, "run", side_effect=(dirty_helper, clean)
        ), self.assertRaisesRegex(MODULE.SystemOffHilFailure, "commit되지 않은"):
            MODULE.validate_source_clean()

        dirty_board = MODULE.subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=" M boards/nucode/nu54dk/board.yml\n",
            stderr="",
        )
        with mock.patch.object(
            MODULE.subprocess, "run", side_effect=(clean, dirty_board)
        ), self.assertRaisesRegex(MODULE.SystemOffHilFailure, "submodule"):
            MODULE.validate_source_clean()


if __name__ == "__main__":
    unittest.main()
