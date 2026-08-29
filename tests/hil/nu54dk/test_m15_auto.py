#!/usr/bin/env python3
"""! @brief M15 비버튼 자동 HIL runner와 parser의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("m15_auto.py")
SPEC = importlib.util.spec_from_file_location("nu54_m15_auto", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

NONCE = b"0123456789abcdef0123456789abcdef"


## @brief 유효한 전체 reset 경계 protocol fixture를 반환합니다.
def valid_transcript() -> bytes:
    return b"\n".join(
        (
            b"NUCODE_M15_AUTO_BOOT:schema=1:stage=idle:cause=1:supported=4095:uptime_ms=8",
            b"NUCODE_M15_AUTO_STATE:schema=1:stage=idle:nonce=none",
            b"NUCODE_M15_AUTO_START:PASS:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_IDENTITY:PASS:model=NUCODE NU54DK nRF54L15 Application MCU:"
            b"target=nrf54l15dk/nrf54l15/cpuapp/nu54dk:soc=nrf54l15:"
            b"device_id=0123456789abcdef",
            b"NUCODE_M15_AUTO_RESET:PASS:phase=initial:cause=1:supported=4095",
            b"NUCODE_M15_AUTO_UPTIME:PASS:before=10:after=35",
            b"NUCODE_M15_AUTO_GRTC:PASS:frequency=32768:before=100:scheduled=6654:"
            b"after=6655:callbacks=1",
            b"NUCODE_M15_AUTO_SETTINGS:SAVED:length=8",
            b"NUCODE_M15_AUTO_TRANSITION:next=soft_reset:method=software",
            b"NUCODE_M15_AUTO_BOOT:schema=1:stage=soft_reset:cause=2:supported=4095:uptime_ms=7",
            b"NUCODE_M15_AUTO_STATE:schema=1:stage=soft_reset:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=soft_reset:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_RESET:PASS:phase=software:cause=2:supported=4095",
            b"NUCODE_M15_AUTO_SETTINGS:LOAD_DELETE:PASS:length=8",
            b"NUCODE_M15_AUTO_WDT:STOP:PASS:feeds=3:survival_ms=2300",
            b"NUCODE_M15_AUTO_TRANSITION:next=watchdog_arm:method=software",
            b"NUCODE_M15_AUTO_BOOT:schema=1:stage=watchdog_arm:cause=2:supported=4095:uptime_ms=6",
            b"NUCODE_M15_AUTO_STATE:schema=1:stage=watchdog_arm:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=watchdog_arm:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_RESET:PASS:phase=watchdog_arm_software:cause=2:supported=4095",
            b"NUCODE_M15_AUTO_WDT:EXPIRY_ARMED:timeout_ms=1500:feeds=1",
            b"NUCODE_M15_AUTO_BOOT:schema=1:stage=watchdog_wait:cause=16:supported=4095:uptime_ms=5",
            b"NUCODE_M15_AUTO_STATE:schema=1:stage=watchdog_wait:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=watchdog_wait:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_RESET:PASS:phase=watchdog:cause=16:supported=4095",
            b"NUCODE_M15_AUTO_SYSTEM_OFF:REQUESTED:duration_us=2000000",
            b"NUCODE_M15_AUTO_SYSTEM_OFF:ENTERING",
            b"NUCODE_M15_AUTO_BOOT:schema=1:stage=timed_wake_wait:cause=2048:"
            b"supported=4095:uptime_ms=4",
            b"NUCODE_M15_AUTO_STATE:schema=1:stage=timed_wake_wait:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=timed_wake_wait:nonce=" + NONCE,
            b"NUCODE_M15_AUTO_RESET:PASS:phase=timed_wake:cause=2048:supported=4095",
            b"NUCODE_M15_AUTO_SYSTEM_OFF:WAKE:PASS:duration_us=2000000:cause=2048",
            b"NUCODE_M15_AUTO_FINAL:PASS:nonce=" + NONCE,
        )
    ) + b"\n"


class FakeSerialPort:
    """! @brief execute_protocol을 실제 UART 없이 구동하는 byte stream입니다. """

    def __init__(self, transcript: bytes) -> None:
        """! @brief 읽을 protocol과 기록할 command buffer를 초기화합니다. """

        self.input = bytearray(transcript)
        self.output = bytearray()

    def __enter__(self) -> "FakeSerialPort":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @property
    def in_waiting(self) -> int:
        return len(self.input)

    def read(self, size: int) -> bytes:
        actual = min(size, len(self.input))
        result = bytes(self.input[:actual])
        del self.input[:actual]
        return result

    def write(self, data: bytes) -> int:
        self.output.extend(data)
        return len(data)

    def flush(self) -> None:
        return None

    def reset_input_buffer(self) -> None:
        return None


class FakeSerialModule:
    """! @brief pySerial 상수와 단일 fake port를 제공합니다. """

    EIGHTBITS = 8
    PARITY_NONE = "N"
    STOPBITS_ONE = 1

    def __init__(self, transcript: bytes) -> None:
        self.port = FakeSerialPort(transcript)

    def Serial(self, **_kwargs: object) -> FakeSerialPort:  # noqa: N802
        """! @brief execute_protocol이 열 단일 fake port를 반환합니다. """

        return self.port


class M15AutoHilTests(unittest.TestCase):
    """! @brief M15 자동 HIL의 parser, 상태 순서와 복구 안전성을 검증합니다. """

    def test_clean_linux_producer_matches_clean_crlf_consumer(self) -> None:
        """! @brief Ubuntu CI source digest를 clean Windows checkout에서 재현합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-digest-") as temporary:
            temporary_root = Path(temporary)
            origin = temporary_root / "origin"
            source_root = origin / "source"
            source_root.mkdir(parents=True)
            (origin / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
            source = source_root / "fixture.cpp"
            committed = b"first\nsecond\n"
            source.write_bytes(committed)
            for command in (
                ("git", "init", "--quiet"),
                ("git", "add", "."),
                (
                    "git",
                    "-c",
                    "user.name=NUCODE Test",
                    "-c",
                    "user.email=test@nucode.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ),
            ):
                subprocess.run(command, cwd=origin, check=True, capture_output=True)

            producer_line = (
                "fixture.cpp:" + hashlib.sha256(committed).hexdigest() + "\n"
            )
            producer_digest = hashlib.sha256(
                producer_line.encode("utf-8")
            ).hexdigest()
            repository = temporary_root / "windows-consumer"
            subprocess.run(
                (
                    "git",
                    "clone",
                    "--quiet",
                    "-c",
                    "core.autocrlf=true",
                    str(origin),
                    str(repository),
                ),
                check=True,
                capture_output=True,
            )
            source_root = repository / "source"
            consumer_bytes = (source_root / "fixture.cpp").read_bytes()
            self.assertEqual(consumer_bytes, committed.replace(b"\n", b"\r\n"))
            status = subprocess.run(
                ("git", "status", "--porcelain=v1", "--", "source"),
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.stdout, "")
            consumer_raw_line = (
                "fixture.cpp:" + hashlib.sha256(consumer_bytes).hexdigest() + "\n"
            )
            self.assertNotEqual(
                hashlib.sha256(consumer_raw_line.encode("utf-8")).hexdigest(),
                producer_digest,
            )
            self.assertEqual(
                MODULE.git_committed_files_digest(
                    repository, source_root, (source_root,)
                ),
                producer_digest,
            )

    def test_board_id_is_required(self) -> None:
        """! @brief 실제 probe를 암묵적 기본값으로 선택하지 않습니다. """

        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            MODULE.parse_arguments([])
        arguments = MODULE.parse_arguments(["--board-id", "fixture", "--discover-only"])
        self.assertEqual(arguments.board_id, "fixture")
        exact = MODULE.parse_arguments(
            [
                "--board-id",
                "fixture",
                "--discover-only",
                "--expected-core-revision",
                "a" * 40,
            ]
        )
        self.assertEqual(exact.expected_core_revision, "a" * 40)

    def test_accepts_complete_reset_storage_wdt_and_timed_wake_protocol(self) -> None:
        """! @brief 모든 자동 단계와 reset cause를 만족한 transcript만 PASS입니다. """

        result = MODULE.parse_transcript(valid_transcript(), 1.55, 2.08)
        self.assertEqual(result.nonce, NONCE.decode("ascii"))
        self.assertEqual(result.device_id, "0123456789abcdef")
        self.assertEqual(result.software_reset_cause, MODULE.RESET_SOFTWARE)
        self.assertEqual(result.watchdog_reset_cause, MODULE.RESET_WATCHDOG)
        self.assertEqual(result.timed_wake_reset_cause, MODULE.RESET_CLOCK)
        self.assertEqual(result.grtc_frequency_hz, 32768)

    def test_rejects_missing_or_reordered_protocol(self) -> None:
        """! @brief settings delete나 WDT stop 증거가 빠지면 최종 PASS도 거부합니다. """

        missing = valid_transcript().replace(
            b"NUCODE_M15_AUTO_SETTINGS:LOAD_DELETE:PASS:length=8\n", b""
        )
        with self.assertRaisesRegex(MODULE.AutoHilFailure, "순서|형식"):
            MODULE.parse_transcript(missing, 1.55, 2.08)

    def test_rejects_wrong_reset_cause_and_timing(self) -> None:
        """! @brief 합성 token이라도 실제 reset bit와 시간 경계를 우회하지 못합니다. """

        wrong_cause = valid_transcript().replace(
            b"stage=watchdog_wait:cause=16", b"stage=watchdog_wait:cause=2"
        )
        with self.assertRaisesRegex(MODULE.AutoHilFailure, "watchdog reset"):
            MODULE.parse_transcript(wrong_cause, 1.55, 2.08)
        with self.assertRaisesRegex(MODULE.AutoHilFailure, "System OFF wake 시간"):
            MODULE.parse_transcript(valid_transcript(), 1.55, 0.2)

    def test_target_source_excludes_button_and_pmic_mutation(self) -> None:
        """! @brief 자동 image에서 버튼 wake와 PMIC 접근을 정적으로 차단합니다. """

        source = (
            MODULE.REPOSITORY / "tests" / "zephyr" / "m15_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        self.assertNotIn("prepareButtonWake", source)
        self.assertNotIn("pmicBegin", source)
        self.assertNotIn("pmicSet", source)
        self.assertNotIn("pmicEnter", source)

    def test_target_fail_or_token_after_final_is_rejected(self) -> None:
        """! @brief target FAIL과 최종 token 뒤 위조 성공 line을 허용하지 않습니다. """

        with self.assertRaisesRegex(MODULE.AutoHilFailure, "FAIL"):
            MODULE.parse_transcript(
                valid_transcript() + b"NUCODE_M15_AUTO_FAIL:stage=late\n", 1.55, 2.08
            )
        with self.assertRaisesRegex(MODULE.AutoHilFailure, "예상하지 않은"):
            MODULE.parse_transcript(
                valid_transcript() + b"NUCODE_M15_AUTO_CLEAR:PASS\n", 1.55, 2.08
            )

    def test_runner_sends_start_and_exact_four_continue_commands(self) -> None:
        """! @brief host 상태 머신이 각 재부팅에서 정확히 한 번만 진행을 승인합니다. """

        serial = FakeSerialModule(valid_transcript())
        with mock.patch.object(MODULE.secrets, "token_hex", return_value=NONCE.decode()), \
             mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            execution = MODULE.execute_protocol(
                serial_module=serial,
                port_name="COM9",
                baud_rate=115200,
                result_timeout_seconds=30.0,
                flash_callback=lambda: ("42", "1234"),
            )
        commands = [line for line in bytes(serial.port.output).split(b"\r\n") if line]
        self.assertEqual(commands[0], MODULE.START_COMMAND + NONCE)
        self.assertEqual(len(commands), 5)
        self.assertTrue(all(command.endswith(NONCE) for command in commands))
        self.assertIn(MODULE.FINAL_PREFIX + NONCE, execution.scenario_transcript)

    def test_execution_failure_saves_exact_partial_uart_companion(self) -> None:
        """! @brief 중간 FAIL과 미완성 tail까지 companion transcript에 보존합니다. """

        partial = (
            b"boot diagnostic\r\n"
            b"NUCODE_M15_AUTO_BOOT:schema=1:stage=idle:cause=1:"
            b"supported=4095:uptime_ms=8\r\n"
            b"NUCODE_M15_AUTO_FAIL:stage=fixture:error=11:driver_error=-5\r\n"
            b"unprocessed-tail"
        )
        serial = FakeSerialModule(partial)
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()), \
             self.assertRaises(MODULE.ProtocolExecutionFailure) as raised:
            MODULE.execute_protocol(
                serial_module=serial,
                port_name="COM9",
                baud_rate=115200,
                result_timeout_seconds=30.0,
                flash_callback=lambda: ("42", "1234"),
            )
        self.assertEqual(raised.exception.transcript, partial)

        with tempfile.TemporaryDirectory(prefix="nu54-m15-partial-") as temporary:
            companion = Path(temporary) / "m15.transcript.log"
            self.assertTrue(
                MODULE.save_failure_transcript(companion, raised.exception, None)
            )
            self.assertEqual(companion.read_bytes(), partial)

    def test_non_protocol_failure_does_not_fabricate_transcript(self) -> None:
        """! @brief UART 실행 전 오류에는 합성 companion 내용을 만들지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-no-partial-") as temporary:
            companion = Path(temporary) / "m15.transcript.log"
            self.assertFalse(
                MODULE.save_failure_transcript(
                    companion, MODULE.AutoHilFailure("preflight"), None
                )
            )
            self.assertFalse(companion.exists())

    def test_recovery_is_uid_scoped_and_never_requests_mass_erase(self) -> None:
        """! @brief pyOCD reset/reflash가 명시 UID와 image만 사용합니다. """

        reset = MODULE.recovery_command("reset", "probe-uid", None)
        image = Path("C:/fixture/safe.hex")
        reflash = MODULE.recovery_command("reflash", "probe-uid", image)
        for command in (reset, reflash):
            joined = " ".join(command).lower()
            self.assertIn("probe-uid", command)
            self.assertNotIn("--erase", joined)
            self.assertNotIn("--recover", joined)
        self.assertEqual(reflash[-1], str(image))

    def test_recovery_forces_utf8_for_windows_pyocd_output(self) -> None:
        """! @brief CP949 console에서도 pyOCD 진단 문자가 복구를 깨지 않습니다. """

        completed = MODULE.subprocess.CompletedProcess(
            args=["pyocd"], returncode=0, stdout="", stderr=""
        )
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            self.assertEqual(MODULE.recover_target("reset", "probe-uid", None), "passed")
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["PYTHONUTF8"], "1")
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")

    def test_existing_evidence_requires_explicit_overwrite(self) -> None:
        """! @brief 이전 PASS 증적을 자동으로 교체하지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-auto-") as temporary:
            evidence = Path(temporary) / "m15.json"
            evidence.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.AutoHilFailure, "자동 덮어쓰지"):
                MODULE.prepare_output_paths(str(evidence), False)
            actual, transcript = MODULE.prepare_output_paths(str(evidence), True)
            self.assertEqual(actual, evidence.resolve())
            self.assertEqual(transcript.name, "m15.transcript.log")
            self.assertFalse(evidence.exists())

    def test_build_record_binds_exact_revision_target_and_source_digests(self) -> None:
        """! @brief adjacent build record와 현재 source byte가 모두 같아야 합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-record-") as temporary:
            build = Path(temporary) / "m15_hil"
            image = build / "zephyr" / "zephyr.hex"
            image.parent.mkdir(parents=True)
            image.write_bytes(b":00000001FF\n")
            core_revision = "a" * 40
            board_revision = "b" * 40
            source_digests = {
                "core_source_sha256": "1" * 64,
                "application_source_sha256": "2" * 64,
                "board_source_sha256": "3" * 64,
            }
            record = build / "nucode_arduino_core_build.yml"
            record.write_text(
                "nucode_arduino_core:\n"
                f"  core_revision: '{core_revision[:12]}'\n"
                f"  core_source_sha256: '{source_digests['core_source_sha256']}'\n"
                f"  application_source_sha256: '{source_digests['application_source_sha256']}'\n"
                f"  board_revision: '{board_revision[:12]}'\n"
                f"  board_source_sha256: '{source_digests['board_source_sha256']}'\n"
                "  ncs_revision: '99553055607b'\n"
                "  zephyr_revision: 'bf801e4e3d19'\n"
                "  board: 'nrf54l15dk'\n"
                "  board_qualifiers: 'nrf54l15/cpuapp/nu54dk'\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                MODULE, "current_source_digests", return_value=source_digests
            ):
                result = MODULE.validate_build_record(
                    image, core_revision, board_revision
                )
            self.assertEqual(result["record_name"], record.name)
            self.assertEqual(result["record_sha256"], MODULE.file_sha256(record))

            clean_record = record.read_text(encoding="utf-8")
            record.write_text(
                clean_record.replace(core_revision[:12], f"{core_revision[:12]}-dirty"),
                encoding="utf-8",
            )
            with mock.patch.object(
                MODULE, "current_source_digests", return_value=source_digests
            ), self.assertRaisesRegex(MODULE.AutoHilFailure, "exact M15"):
                MODULE.validate_build_record(image, core_revision, board_revision)

            record.write_text(
                clean_record.replace(board_revision[:12], "c" * 12),
                encoding="utf-8",
            )
            with mock.patch.object(
                MODULE, "current_source_digests", return_value=source_digests
            ), self.assertRaisesRegex(MODULE.AutoHilFailure, "board_revision"):
                MODULE.validate_build_record(image, core_revision, board_revision)

            record.write_text(
                clean_record.replace("1" * 64, "4" * 64), encoding="utf-8"
            )
            with mock.patch.object(
                MODULE, "current_source_digests", return_value=source_digests
            ), self.assertRaisesRegex(MODULE.AutoHilFailure, "현재 exact source"):
                MODULE.validate_build_record(image, core_revision, board_revision)

    def test_dirty_core_or_board_source_is_rejected(self) -> None:
        """! @brief commit 밖 source와 dirty board submodule로 HIL을 시작하지 않습니다. """

        clean = MODULE.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="", stderr=""
        )
        dirty = MODULE.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="?? tests/zephyr/m15_hil/new\n", stderr=""
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
            ), self.assertRaisesRegex(MODULE.AutoHilFailure, "commit되지 않은"):
                MODULE.validate_source_clean()
        with mock.patch.object(MODULE.subprocess, "run", side_effect=(dirty, clean)), \
             self.assertRaisesRegex(MODULE.AutoHilFailure, "commit되지 않은"):
            MODULE.validate_source_clean()
        with mock.patch.object(MODULE.subprocess, "run", side_effect=(clean, dirty)), \
             self.assertRaisesRegex(MODULE.AutoHilFailure, "submodule"):
            MODULE.validate_source_clean()

    def test_hex_digest_change_rejects_stale_or_replaced_image(self) -> None:
        """! @brief 같은 크기로 바꾼 HEX도 pre-flash digest와 다르면 거부합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-image-") as temporary:
            image = Path(temporary) / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            size = image.stat().st_size
            digest = MODULE.file_sha256(image)
            MODULE.validate_image_unchanged(image, size, digest)
            image.write_bytes(b":00000002FE\n")
            self.assertEqual(image.stat().st_size, size)
            with self.assertRaisesRegex(MODULE.AutoHilFailure, "HEX byte"):
                MODULE.validate_image_unchanged(image, size, digest)

    def test_evidence_contains_revision_build_record_and_exact_image_digest(self) -> None:
        """! @brief PASS JSON이 checkout, build record와 HEX byte를 함께 고정합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m15-evidence-") as temporary:
            root = Path(temporary)
            image = root / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            transcript = valid_transcript()
            execution = MODULE.ExecutionResult(
                flash_sequence="42",
                flash_bytes="1234",
                transcript=transcript,
                scenario_transcript=transcript,
                watchdog_interval_seconds=1.55,
                system_off_interval_seconds=2.08,
            )
            result = MODULE.parse_transcript(transcript, 1.55, 2.08)
            evidence = MODULE.build_evidence(
                core_revision="a" * 40,
                board_revision="b" * 40,
                board_id="fixture-board",
                volume=MODULE.DaplinkVolume(
                    root=Path("E:/"), details="Target Detect: nRF54L15\n"
                ),
                port_name="COM9",
                image=image,
                image_size=image.stat().st_size,
                image_sha256=MODULE.file_sha256(image),
                transcript_path=root / "m15.transcript.log",
                execution=execution,
                result=result,
                build_record={
                    "record_name": "nucode_arduino_core_build.yml",
                    "record_sha256": "c" * 64,
                },
            )
            self.assertEqual(evidence["core_revision"], "a" * 40)
            self.assertEqual(evidence["board_revision"], "b" * 40)
            self.assertEqual(evidence["image"]["sha256"], MODULE.file_sha256(image))
            self.assertEqual(
                evidence["build_record"]["record_sha256"], "c" * 64
            )


if __name__ == "__main__":
    unittest.main()
