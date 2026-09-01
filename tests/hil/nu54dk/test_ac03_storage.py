#!/usr/bin/env python3
"""! @brief AC-03 두 보드 HIL runner/parser의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("ac03_storage.py")
SPEC = importlib.util.spec_from_file_location("nu54_ac03_storage", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
NONCE = b"0123456789abcdef0123456789abcdef"


class ScriptedSerialPort:
    """! @brief 지정 chunk를 순서대로 반환하는 최소 UART 대역입니다. """

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.writes: list[bytes] = []
        self.read_count = 0

    def __enter__(self) -> "ScriptedSerialPort":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    @property
    def in_waiting(self) -> int:
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, _: int) -> bytes:
        self.read_count += 1
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, value: bytes) -> int:
        self.writes.append(value)
        return len(value)

    def flush(self) -> None:
        return None


class ScriptedSerialModule:
    """! @brief execute_protocol에 필요한 pyserial 상수와 port를 제공합니다. """

    EIGHTBITS = 8
    PARITY_NONE = "N"
    STOPBITS_ONE = 1

    def __init__(self, port: ScriptedSerialPort) -> None:
        self.port = port

    def Serial(self, **_: object) -> ScriptedSerialPort:
        return self.port


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

    def test_final_prefix_is_not_accepted_until_complete_newline(self) -> None:
        """! @brief FINAL 본문이 모두 와도 개행 전에는 완료 line으로 보지 않습니다. """

        incomplete = valid_transcript()[:-1]
        self.assertNotIn(
            b"NUCODE_AC03_FINAL:PASS:nonce=" + NONCE,
            MODULE._protocol_lines(incomplete),
        )
        with self.assertRaisesRegex(MODULE.AC03HilFailure, "최종 PASS"):
            MODULE.parse_transcript(incomplete, NONCE.decode("ascii"))

        port = ScriptedSerialPort([incomplete, b"\n"])
        serial_module = ScriptedSerialModule(port)
        observed = MODULE.execute_protocol(
            serial_module,
            "COM_TEST",
            115200,
            NONCE.decode("ascii"),
            1.0,
        )
        self.assertTrue(observed.endswith(b"\n"))
        self.assertGreaterEqual(port.read_count, 2)

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

    def test_requires_new_evidence_before_exact_input_or_flash(self) -> None:
        """! @brief evidence 누락·기존 파일은 HEX 검증과 물리 실행보다 먼저 거부합니다. """

        fake_serial = (mock.Mock(), mock.Mock())
        base = [
            "--board-id", "one",
            "--board-id", "two",
            "--hex", "input.hex",
            "--expected-core-revision", "a" * 40,
            "--allow-destructive-storage",
        ]
        with mock.patch.object(MODULE, "import_pyserial", return_value=fake_serial), \
             mock.patch.object(MODULE, "validate_exact_inputs") as exact:
            with self.assertRaisesRegex(MODULE.AC03HilFailure, "--evidence"):
                MODULE.main(base)
            exact.assert_not_called()

        with tempfile.TemporaryDirectory(prefix="nu54-ac03-evidence-") as temporary:
            evidence = Path(temporary) / "existing.json"
            evidence.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(MODULE, "import_pyserial", return_value=fake_serial), \
                 mock.patch.object(MODULE, "validate_exact_inputs") as exact:
                with self.assertRaisesRegex(MODULE.AC03HilFailure, "덮어쓰지"):
                    MODULE.main(base + ["--evidence", str(evidence)])
                exact.assert_not_called()

    def test_exact_input_binds_commit_gitlink_record_digest_and_hex(self) -> None:
        """! @brief exact 입력 검사가 revision·board·record·source digest를 모두 묶습니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-ac03-input-") as temporary:
            image = Path(temporary) / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            core_revision = "a" * 40
            board_revision = "b" * 40
            record = {
                "core_source_sha256": "c" * 64,
                "application_source_sha256": "d" * 64,
                "board_source_sha256": "e" * 64,
                "record_sha256": "f" * 64,
            }
            digests = {
                key: record[key]
                for key in (
                    "core_source_sha256",
                    "application_source_sha256",
                    "board_source_sha256",
                )
            }
            with mock.patch.object(MODULE, "validate_hex_image", return_value=image), \
                 mock.patch.object(
                     MODULE,
                     "common_git_revision",
                     side_effect=(core_revision, board_revision),
                 ) as revision, \
                 mock.patch.object(MODULE, "common_validate_board_revision") as board, \
                 mock.patch.object(MODULE, "validate_source_clean") as clean, \
                 mock.patch.object(
                     MODULE, "common_validate_build_record", return_value=record
                 ) as build_record, \
                 mock.patch.object(
                     MODULE, "common_current_source_digests", return_value=digests
                 ):
                validated = MODULE.validate_exact_inputs(
                    str(image), core_revision
                )

            self.assertEqual(validated[1:5], (core_revision, board_revision, record, digests))
            self.assertEqual(validated[5], image.stat().st_size)
            self.assertEqual(validated[6], MODULE.file_sha256(image))
            self.assertEqual(revision.call_count, 2)
            board.assert_called_once_with(board_revision)
            clean.assert_called_once_with()
            build_record.assert_called_once_with(
                image,
                core_revision,
                board_revision,
                MODULE.APPLICATION_SOURCE_ROOT,
            )

    def test_failure_recovery_preserves_original_error_and_no_evidence(self) -> None:
        """! @brief 물리 실패 뒤 CLEAR를 시도하되 원래 오류와 FAIL 상태를 유지합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-ac03-failure-") as temporary:
            root = Path(temporary)
            image = root / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            evidence = root / "evidence.json"
            exact = (
                image,
                "a" * 40,
                "b" * 40,
                {"record_sha256": "c" * 64},
                {
                    "core_source_sha256": "d" * 64,
                    "application_source_sha256": "e" * 64,
                    "board_source_sha256": "f" * 64,
                },
                image.stat().st_size,
                MODULE.file_sha256(image),
            )
            endpoints = [("one", "COM1", "E:\\"), ("two", "COM2", "F:\\")]
            with mock.patch.object(
                MODULE, "import_pyserial", return_value=(mock.Mock(), mock.Mock())
            ), mock.patch.object(MODULE, "validate_exact_inputs", return_value=exact), \
                 mock.patch.object(MODULE, "resolve_endpoints", return_value=endpoints), \
                 mock.patch.object(
                     MODULE, "run_board", side_effect=RuntimeError("primary-failure")
                 ), mock.patch.object(
                     MODULE,
                     "recover_touched_boards",
                     return_value=["one=cleared(sequence=7)"],
                 ) as recover:
                with self.assertRaisesRegex(
                    MODULE.AC03HilFailure,
                    "RuntimeError: primary-failure.*one=cleared",
                ):
                    MODULE.main(
                        [
                            "--board-id", "one",
                            "--board-id", "two",
                            "--hex", str(image),
                            "--expected-core-revision", "a" * 40,
                            "--evidence", str(evidence),
                            "--allow-destructive-storage",
                        ]
                    )
            self.assertFalse(evidence.exists())
            self.assertEqual(recover.call_args.kwargs["touched"], [endpoints[0]])

    def test_recovery_continues_after_one_board_cleanup_failure(self) -> None:
        """! @brief 한 보드 CLEAR 실패가 다른 접촉 보드 복구를 막지 않습니다. """

        with mock.patch.object(
            MODULE,
            "best_effort_recover_board",
            side_effect=(RuntimeError("clear-failed"), "22"),
        ) as recover:
            reports = MODULE.recover_touched_boards(
                touched=(("one", "COM1", "E:\\"), ("two", "COM2", "F:\\")),
                image=Path("image.hex"),
                serial_module=mock.Mock(),
                list_ports=mock.Mock(),
                baud=115200,
                flash_timeout=45.0,
                result_timeout=120.0,
                image_size=1,
                image_sha256="a" * 64,
            )
        self.assertEqual(recover.call_count, 2)
        self.assertIn("two=recovery-failed(RuntimeError: clear-failed)", reports)
        self.assertIn("one=cleared(sequence=22)", reports)

    def test_pass_evidence_contains_revisions_and_source_digests(self) -> None:
        """! @brief PASS JSON에 exact Core·board·source·build·HEX identity를 기록합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-ac03-pass-") as temporary:
            root = Path(temporary)
            image = root / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            evidence = root / "evidence.json"
            source_digests = {
                "core_source_sha256": "c" * 64,
                "application_source_sha256": "d" * 64,
                "board_source_sha256": "e" * 64,
            }
            build_record = {**source_digests, "record_sha256": "f" * 64}
            exact = (
                image,
                "a" * 40,
                "b" * 40,
                build_record,
                source_digests,
                image.stat().st_size,
                MODULE.file_sha256(image),
            )
            endpoints = [("one", "COM1", "E:\\"), ("two", "COM2", "F:\\")]

            def successful_board(**kwargs: object) -> tuple[object, bytes]:
                board_id = str(kwargs["board_id"])
                return (
                    MODULE.BoardResult(
                        board_id,
                        str(kwargs["port"]),
                        "1" * 32,
                        "9",
                        "1024",
                        3,
                        True,
                        True,
                        True,
                        True,
                    ),
                    b"NUCODE_AC03_FINAL:PASS\n",
                )

            with mock.patch.object(
                MODULE, "import_pyserial", return_value=(mock.Mock(), mock.Mock())
            ), mock.patch.object(MODULE, "validate_exact_inputs", return_value=exact), \
                 mock.patch.object(MODULE, "resolve_endpoints", return_value=endpoints), \
                 mock.patch.object(MODULE, "run_board", side_effect=successful_board), \
                 mock.patch.object(MODULE, "validate_image_unchanged"):
                self.assertEqual(
                    MODULE.main(
                        [
                            "--board-id", "one",
                            "--board-id", "two",
                            "--hex", str(image),
                            "--expected-core-revision", "a" * 40,
                            "--evidence", str(evidence),
                            "--allow-destructive-storage",
                        ]
                    ),
                    0,
                )

            value = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(value["schema_version"], MODULE.EVIDENCE_SCHEMA)
            self.assertEqual(value["core_revision"], "a" * 40)
            self.assertEqual(value["board_revision"], "b" * 40)
            self.assertEqual(value["source_digests"], source_digests)
            self.assertEqual(value["image"]["build_record"], build_record)
            self.assertEqual(value["image"]["sha256"], MODULE.file_sha256(image))

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
