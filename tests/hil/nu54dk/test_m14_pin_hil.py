#!/usr/bin/env python3
"""! @brief M14 신규 핀 HIL protocol과 evidence를 실제 장치 없이 회귀 검증합니다. """

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("m14_pin_hil.py")
MODULE_SPEC = importlib.util.spec_from_file_location("m14_pin_hil", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"M14 pin HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)


## @brief 정확한 M14 pin HIL 성공 transcript를 생성합니다.
def valid_transcript() -> bytes:
    lines = [
        "NUCODE_M14_PIN_HIL_READY:schema=1:action_timeout_ms=30000",
        "NUCODE_M14_PIN_HIL_EXCLUDED:pin=PIN_LED1:id=4:owner=PIN_PWM0:"
        "evidence=M7_PWM_DRIVER",
        "NUCODE_M14_PIN_HIL_LED:PASS:pin=PIN_LED2:id=5:low_read=LOW:"
        "high_read=HIGH:final=LOW",
        "NUCODE_M14_PIN_HIL_LED:PASS:pin=PIN_LED3:id=6:low_read=LOW:"
        "high_read=HIGH:final=LOW",
    ]
    for name, logical_id in (
        ("PIN_BUTTON1", 7),
        ("PIN_BUTTON2", 8),
        ("PIN_BUTTON3", 9),
    ):
        lines.extend(
            [
                f"NUCODE_M14_PIN_HIL_ACTION:pin={name}:id={logical_id}:"
                "mode=INPUT_PULLUP:expected=RELEASE_HIGH:timeout_ms=30000",
                f"NUCODE_M14_PIN_HIL_INPUT:PASS:pin={name}:id={logical_id}:"
                "mode=INPUT_PULLUP:released=HIGH",
                f"NUCODE_M14_PIN_HIL_ACTION:pin={name}:id={logical_id}:"
                "mode=FALLING:expected=PRESS_LOW:timeout_ms=30000",
                f"NUCODE_M14_PIN_HIL_EDGE:PASS:pin={name}:id={logical_id}:"
                "mode=FALLING:state=LOW:count=2",
                f"NUCODE_M14_PIN_HIL_ACTION:pin={name}:id={logical_id}:"
                "mode=RISING:expected=RELEASE_HIGH:timeout_ms=30000",
                f"NUCODE_M14_PIN_HIL_EDGE:PASS:pin={name}:id={logical_id}:"
                "mode=RISING:state=HIGH:count=1",
                f"NUCODE_M14_PIN_HIL_ACTION:pin={name}:id={logical_id}:"
                "mode=CHANGE_PRESS:expected=PRESS_LOW:timeout_ms=30000",
                f"NUCODE_M14_PIN_HIL_EDGE:PASS:pin={name}:id={logical_id}:"
                "mode=CHANGE_PRESS:state=LOW:count=3",
                f"NUCODE_M14_PIN_HIL_ACTION:pin={name}:id={logical_id}:"
                "mode=CHANGE_RELEASE:expected=RELEASE_HIGH:timeout_ms=30000",
                f"NUCODE_M14_PIN_HIL_EDGE:PASS:pin={name}:id={logical_id}:"
                "mode=CHANGE_RELEASE:state=HIGH:count=5",
                f"NUCODE_M14_PIN_HIL_BUTTON:PASS:pin={name}:id={logical_id}:"
                "released=HIGH:pressed=LOW:modes=FALLING,RISING,CHANGE",
            ]
        )
    lines.append("NUCODE_M14_PIN_HIL_PASS")
    return ("Zephyr boot log\r\n" + "\r\n".join(lines) + "\r\n").encode("ascii")


class ChunkSerial:
    """! @brief read_transcript 단위 시험용 고정 chunk serial입니다. """

    def __init__(self, chunks: list[bytes]) -> None:
        """! @brief 순서대로 반환할 UART chunk를 저장합니다. """

        self.chunks = list(chunks)

    @property
    def in_waiting(self) -> int:
        """! @brief 다음 chunk의 byte 수를 반환합니다. """

        return len(self.chunks[0]) if self.chunks else 0

    def read(self, _size: int) -> bytes:
        """! @brief 다음 UART chunk 하나를 반환합니다. """

        return self.chunks.pop(0) if self.chunks else b""


class M14PinHilTests(unittest.TestCase):
    """! @brief pin identity, 동작 순서, timeout과 증적 경계를 검증합니다. """

    def test_m14_keeps_live_worktree_digest_contract(self) -> None:
        """! @brief M14 local build 검증이 CI canonical helper로 바뀌지 않게 고정합니다. """

        with mock.patch.object(
            MODULE, "files_digest", side_effect=("1" * 64, "2" * 64, "3" * 64)
        ) as live_digest, mock.patch.object(
            MODULE,
            "git_committed_files_digest",
            side_effect=AssertionError("M14는 canonical helper를 사용하면 안 됩니다."),
        ):
            self.assertEqual(
                MODULE.current_source_digests(),
                {
                    "core_source_sha256": "1" * 64,
                    "application_source_sha256": "2" * 64,
                    "board_source_sha256": "3" * 64,
                },
            )
        self.assertEqual(live_digest.call_count, 3)

    def test_accepts_exact_led_button_and_edge_contract(self) -> None:
        """! @brief LED 2개와 버튼 3개의 완전한 protocol만 승인합니다. """

        result = MODULE.parse_transcript(valid_transcript())
        self.assertEqual([item.logical_id for item in result.leds], [5, 6])
        self.assertEqual([item.logical_id for item in result.buttons], [7, 8, 9])
        self.assertEqual(result.buttons[0].falling_edges, 2)
        self.assertEqual(result.buttons[0].change_release_edges, 5)

    def test_rejects_target_failure_and_missing_pin(self) -> None:
        """! @brief target FAIL 또는 신규 핀 누락을 PASS로 승격하지 않습니다. """

        with self.assertRaisesRegex(MODULE.PinHilFailure, "실패"):
            MODULE.parse_transcript(
                b"NUCODE_M14_PIN_HIL_FAIL:stage=LED_PINMODE:pin=PIN_LED2\r\n"
            )
        missing = valid_transcript().replace(
            b"NUCODE_M14_PIN_HIL_LED:PASS:pin=PIN_LED3:id=6:low_read=LOW:"
            b"high_read=HIGH:final=LOW\r\n",
            b"",
        )
        with self.assertRaisesRegex(MODULE.PinHilFailure, "형식|중간|순서"):
            MODULE.parse_transcript(missing)

    def test_rejects_wrong_logical_id_and_action_order(self) -> None:
        """! @brief 이름/ID 불일치와 안내보다 앞선 물리 동작 결과를 거부합니다. """

        wrong_id = valid_transcript().replace(
            b"pin=PIN_BUTTON2:id=8", b"pin=PIN_BUTTON2:id=18", 1
        )
        with self.assertRaisesRegex(MODULE.PinHilFailure, "identity"):
            MODULE.parse_transcript(wrong_id)

        wrong_action = valid_transcript().replace(
            b"mode=FALLING:expected=PRESS_LOW",
            b"mode=RISING:expected=RELEASE_HIGH",
            1,
        )
        with self.assertRaisesRegex(MODULE.PinHilFailure, "FALLING 사용자 동작"):
            MODULE.parse_transcript(wrong_action)

    def test_rejects_missing_edge_and_incomplete_change_pair(self) -> None:
        """! @brief edge 0회와 CHANGE release 추가 edge 부재를 모두 거부합니다. """

        no_falling = valid_transcript().replace(
            b"mode=FALLING:state=LOW:count=2",
            b"mode=FALLING:state=LOW:count=0",
            1,
        )
        with self.assertRaisesRegex(MODULE.PinHilFailure, "관찰되지"):
            MODULE.parse_transcript(no_falling)

        no_release_edge = valid_transcript().replace(
            b"mode=CHANGE_RELEASE:state=HIGH:count=5",
            b"mode=CHANGE_RELEASE:state=HIGH:count=3",
            1,
        )
        with self.assertRaisesRegex(MODULE.PinHilFailure, "추가 edge"):
            MODULE.parse_transcript(no_release_edge)

    def test_rejects_duplicate_protocol_after_final_pass(self) -> None:
        """! @brief 최종 PASS 뒤 중복 또는 위조 protocol token을 거부합니다. """

        transcript = valid_transcript() + MODULE.FINAL_PASS_TOKEN + b"\n"
        with self.assertRaisesRegex(MODULE.PinHilFailure, "예상하지 않은"):
            MODULE.parse_transcript(transcript)

    def test_uart_waits_for_complete_terminal_line(self) -> None:
        """! @brief FAIL prefix만 보고 조기 종료하지 않고 진단 line 전체를 보존합니다. """

        serial = ChunkSerial(
            [
                b"NUCODE_M14_PIN_HIL_FAIL:",
                b"stage=ATTACH_FALLING:pin=PIN_BUTTON1\r\n",
            ]
        )
        with mock.patch.object(MODULE.sys, "stdout", io.StringIO()):
            transcript = MODULE.read_transcript(serial, 60.0)
        self.assertIn(b"stage=ATTACH_FALLING", transcript)

    def test_manual_acknowledgement_and_timeout_are_explicit(self) -> None:
        """! @brief 실제 실행 기본값은 수동 동작을 암묵적으로 승인하지 않습니다. """

        defaults = MODULE.parse_arguments([])
        acknowledged = MODULE.parse_arguments(["--acknowledge-manual-actions"])
        self.assertFalse(defaults.acknowledge_manual_actions)
        self.assertTrue(acknowledged.acknowledge_manual_actions)
        self.assertEqual(defaults.result_timeout, 520.0)

    def test_evidence_binds_revisions_image_transcript_and_exclusion(self) -> None:
        """! @brief PASS JSON이 exact byte와 PWM-owned 제외 근거를 함께 기록합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m14-pin-hil-") as temporary:
            root = Path(temporary)
            image = root / "zephyr.hex"
            image.write_bytes(b":00000001FF\n")
            transcript = valid_transcript()
            transcript_path = root / "result.transcript.log"
            evidence = MODULE.build_evidence(
                core_revision="a" * 40,
                board_revision="b" * 40,
                board_id="fixture-board",
                image=image,
                flash_sequence="42",
                flash_byte_count="1234",
                port_name="COM9",
                transcript_path=transcript_path,
                transcript=transcript,
                result=MODULE.parse_transcript(transcript),
                build_record={"record_name": "nucode_arduino_core_build.yml"},
                image_size=image.stat().st_size,
                image_sha256=MODULE.file_sha256(image),
            )
            encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            self.assertEqual(evidence["status"], "passed")
            self.assertEqual(evidence["excluded_pin"]["owner"], "PIN_PWM0")
            self.assertEqual(evidence["image"]["sha256"], MODULE.file_sha256(image))
            self.assertEqual(evidence["transcript"]["size"], len(transcript))
            self.assertNotIn(str(root), encoded)

    def test_existing_evidence_requires_explicit_overwrite(self) -> None:
        """! @brief 이전 PASS 증적을 자동으로 덮어쓰지 않는지 확인합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m14-evidence-") as temporary:
            evidence = Path(temporary) / "m14.json"
            evidence.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.PinHilFailure, "자동 덮어쓰지"):
                MODULE.prepare_output_paths(str(evidence), False)
            actual, transcript = MODULE.prepare_output_paths(str(evidence), True)
            self.assertEqual(actual, evidence.resolve())
            self.assertEqual(transcript.name, "m14.transcript.log")
            self.assertFalse(evidence.exists())

    def test_build_record_requires_clean_exact_target_identity(self) -> None:
        """! @brief dirty revision이나 다른 NCS/board target의 HEX를 거부합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m14-build-record-") as temporary:
            build = Path(temporary) / "m14_pin_hil"
            image = build / "zephyr" / "zephyr.hex"
            image.parent.mkdir(parents=True)
            image.write_bytes(b":00000001FF\n")
            core_revision = "a" * 40
            board_revision = "b" * 40
            record = build / "nucode_arduino_core_build.yml"
            record.write_text(
                "nucode_arduino_core:\n"
                f"  core_revision: '{core_revision[:12]}'\n"
                f"  core_source_sha256: '{'1' * 64}'\n"
                f"  application_source_sha256: '{'2' * 64}'\n"
                f"  board_revision: '{board_revision[:12]}'\n"
                f"  board_source_sha256: '{'3' * 64}'\n"
                "  ncs_revision: '99553055607b'\n"
                "  zephyr_revision: 'bf801e4e3d19'\n"
                "  board: 'nrf54l15dk'\n"
                "  board_qualifiers: 'nrf54l15/cpuapp/nu54dk'\n",
                encoding="utf-8",
            )
            source_digests = {
                "core_source_sha256": "1" * 64,
                "application_source_sha256": "2" * 64,
                "board_source_sha256": "3" * 64,
            }
            with mock.patch.object(
                MODULE, "current_source_digests", return_value=source_digests
            ):
                result = MODULE.validate_build_record(
                    image, core_revision, board_revision
                )
            self.assertEqual(result["core_revision"], core_revision[:12])

            clean_record = record.read_text(encoding="utf-8")
            for key, digest in source_digests.items():
                record.write_text(
                    clean_record.replace(
                        f"  {key}: '{digest}'", f"  {key}: '{'4' * 64}'"
                    ),
                    encoding="utf-8",
                )
                with mock.patch.object(
                    MODULE, "current_source_digests", return_value=source_digests
                ):
                    with self.assertRaisesRegex(
                        MODULE.PinHilFailure, "현재 exact source"
                    ):
                        MODULE.validate_build_record(
                            image, core_revision, board_revision
                        )

            record.write_text(clean_record, encoding="utf-8")
            record.write_text(
                record.read_text(encoding="utf-8").replace(
                    core_revision[:12], f"{core_revision[:12]}-dirty"
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                MODULE, "current_source_digests", return_value=source_digests
            ):
                with self.assertRaisesRegex(MODULE.PinHilFailure, "exact HIL"):
                    MODULE.validate_build_record(
                        image, core_revision, board_revision
                    )

    def test_board_checkout_must_match_parent_gitlink(self) -> None:
        """! @brief clean submodule이라도 부모 commit과 다른 revision이면 거부합니다. """

        expected = "b" * 40
        completed = MODULE.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout=f"{expected}\n", stderr=""
        )
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed):
            self.assertEqual(MODULE.parent_board_revision(), expected)
            MODULE.validate_board_revision(expected)
            with self.assertRaisesRegex(MODULE.PinHilFailure, "gitlink"):
                MODULE.validate_board_revision("c" * 40)


if __name__ == "__main__":
    unittest.main()
