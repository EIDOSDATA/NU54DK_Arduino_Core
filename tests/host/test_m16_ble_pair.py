#!/usr/bin/env python3
"""! @brief M16 BLE NUS 두 보드 HIL parser와 증적 경계를 회귀 검증합니다. """

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "hil" / "nu54dk" / "m16_ble_pair.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m16_ble_pair", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"M16 BLE pair HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)


NONCE = "0123456789abcdef0123456789abcdef"
STALE_NONCE = "fedcba9876543210fedcba9876543210"


## @brief 정확한 central frame 경계·재연결 transcript를 생성합니다.
def valid_central_transcript(nonce: str = NONCE) -> bytes:
    lines = [
        "NUCODE_M16_READY:role=central",
        f"NUCODE_M16_CENTRAL:SCAN:PASS:nonce={nonce}",
        f"NUCODE_M16_EVENT:CONNECTED:round=1:nonce={nonce}",
        f"NUCODE_M16_EVENT:READY:round=1:nonce={nonce}",
    ]
    lines.extend(
        f"NUCODE_M16_CENTRAL:FRAME:PASS:round=1:size={size}:nonce={nonce}"
        for size in (1, 20, 21, 64)
    )
    lines.extend(
        (
            f"NUCODE_M16_EVENT:DISCONNECTED:count=1:nonce={nonce}",
            f"NUCODE_M16_EVENT:CONNECTED:round=2:nonce={nonce}",
            f"NUCODE_M16_EVENT:READY:round=2:nonce={nonce}",
            f"NUCODE_M16_CENTRAL:FRAME:PASS:round=2:size=21:nonce={nonce}",
            "NUCODE_M16_CENTRAL:FINAL:PASS:callback_context=PASS:"
            f"reconnect=PASS:nonce={nonce}",
        )
    )
    return ("Zephyr boot log\r\n" + "\r\n".join(lines) + "\r\n").encode("ascii")


## @brief 정확한 peripheral 광고·byte 수·재연결 transcript를 생성합니다.
def valid_peripheral_transcript(nonce: str = NONCE) -> bytes:
    lines = (
        "NUCODE_M16_READY:role=peripheral",
        f"NUCODE_M16_PERIPHERAL:ADVERTISE:PASS:nonce={nonce}",
        f"NUCODE_M16_EVENT:CONNECTED:round=1:nonce={nonce}",
        f"NUCODE_M16_EVENT:READY:round=1:nonce={nonce}",
        f"NUCODE_M16_PERIPHERAL:ROUND:PASS:round=1:bytes=106:nonce={nonce}",
        f"NUCODE_M16_EVENT:DISCONNECTED:count=1:nonce={nonce}",
        f"NUCODE_M16_EVENT:CONNECTED:round=2:nonce={nonce}",
        f"NUCODE_M16_EVENT:READY:round=2:nonce={nonce}",
        "NUCODE_M16_PERIPHERAL:FINAL:PASS:callback_context=PASS:"
        f"reconnect=PASS:bytes=21:nonce={nonce}",
    )
    return ("Zephyr boot log\n" + "\n".join(lines) + "\n").encode("ascii")


## @brief 테스트용 DAPLink DETAILS.TXT와 endpoint를 만듭니다.
def endpoint(board_id: str, drive: str, port: str) -> object:
    details = f"Target Detect: nRF54L15\nUnique ID: {board_id}\n"
    volume = MODULE.DaplinkVolume(root=Path(drive), details=details)
    return MODULE.RoleEndpoint(board_id=board_id, volume=volume, port_name=port)


class M16BlePairHilTests(unittest.TestCase):
    """! @brief nonce, frame, reconnect, 두 endpoint와 evidence를 검증합니다. """

    def test_accepts_exact_frame_boundaries_and_reconnect(self) -> None:
        """! @brief 양쪽 exact protocol에서 1/20/21/64 및 재연결을 승인합니다. """

        central = MODULE.parse_central_transcript(valid_central_transcript(), NONCE)
        peripheral = MODULE.parse_peripheral_transcript(
            valid_peripheral_transcript(), NONCE
        )
        self.assertEqual(central.frame_sizes_round_1, (1, 20, 21, 64))
        self.assertEqual(central.frame_sizes_round_2, (21,))
        self.assertEqual(central.connection_rounds, (1, 2))
        self.assertEqual(peripheral.first_round_bytes, 106)
        self.assertEqual(peripheral.second_round_bytes, 21)
        self.assertEqual(peripheral.connection_rounds, (1, 2))

    def test_rejects_stale_nonce_before_current_final(self) -> None:
        """! @brief 이전 실행 FINAL이나 frame을 현재 PASS로 재사용하지 못하게 합니다. """

        stale_final = (
            "NUCODE_M16_CENTRAL:FINAL:PASS:callback_context=PASS:"
            f"reconnect=PASS:nonce={STALE_NONCE}\n"
        ).encode("ascii")
        transcript = valid_central_transcript().replace(
            b"NUCODE_M16_CENTRAL:SCAN:PASS", stale_final + b"NUCODE_M16_CENTRAL:SCAN:PASS"
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "stale|nonce"):
            MODULE.parse_central_transcript(transcript, NONCE)

        stale_peripheral = valid_peripheral_transcript().replace(
            f"NUCODE_M16_EVENT:CONNECTED:round=1:nonce={NONCE}".encode("ascii"),
            f"NUCODE_M16_EVENT:CONNECTED:round=1:nonce={STALE_NONCE}".encode(
                "ascii"
            ),
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "stale|nonce"):
            MODULE.parse_peripheral_transcript(stale_peripheral, NONCE)

    def test_rejects_missing_or_wrong_frame_boundary(self) -> None:
        """! @brief 20/21 byte 경계 누락이나 잘못된 길이를 PASS로 승격하지 않습니다. """

        missing = valid_central_transcript().replace(
            f"NUCODE_M16_CENTRAL:FRAME:PASS:round=1:size=20:nonce={NONCE}\r\n".encode(
                "ascii"
            ),
            b"",
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "순서|누락"):
            MODULE.parse_central_transcript(missing, NONCE)

        wrong = valid_central_transcript().replace(b"size=21", b"size=22", 1)
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "순서|값"):
            MODULE.parse_central_transcript(wrong, NONCE)

    def test_rejects_missing_reconnect_and_wrong_byte_total(self) -> None:
        """! @brief 두 번째 연결과 peripheral 106/21 byte 계약 누락을 거부합니다. """

        no_reconnect = valid_central_transcript().replace(
            f"NUCODE_M16_EVENT:CONNECTED:round=2:nonce={NONCE}\r\n".encode(
                "ascii"
            ),
            b"",
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "순서|누락"):
            MODULE.parse_central_transcript(no_reconnect, NONCE)

        wrong_total = valid_peripheral_transcript().replace(b"bytes=106", b"bytes=105")
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "순서|값"):
            MODULE.parse_peripheral_transcript(wrong_total, NONCE)

    def test_rejects_target_fail_and_tokens_after_final(self) -> None:
        """! @brief target FAIL 및 FINAL 뒤 중복 protocol token을 모두 거부합니다. """

        failure = valid_peripheral_transcript().replace(
            b"NUCODE_M16_PERIPHERAL:ADVERTISE:PASS",
            b"NUCODE_M16_FAIL:role=peripheral:reason=advertise",
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "실패"):
            MODULE.parse_peripheral_transcript(failure, NONCE)

        duplicate = valid_central_transcript() + (
            f"NUCODE_M16_EVENT:READY:round=2:nonce={NONCE}\n"
        ).encode("ascii")
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "FINAL 뒤"):
            MODULE.parse_central_transcript(duplicate, NONCE)

    def test_requires_two_distinct_uids_volumes_and_ports(self) -> None:
        """! @brief 같은 UID·MSD·COM을 role 두 개로 오인하지 않게 차단합니다. """

        peripheral = endpoint("a" * 32, "P:/", "COM10")
        central = endpoint("b" * 32, "Q:/", "COM11")
        MODULE.validate_pair_identity(peripheral, central)

        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "UID"):
            MODULE.validate_pair_identity(
                peripheral, endpoint("a" * 32, "Q:/", "COM11")
            )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "MSD"):
            MODULE.validate_pair_identity(
                peripheral, endpoint("b" * 32, "P:/", "COM11")
            )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "UART"):
            MODULE.validate_pair_identity(
                peripheral, endpoint("b" * 32, "Q:/", "com10")
            )

    def test_nonce_is_exact_lowercase_hex(self) -> None:
        """! @brief nonce 길이·문자 집합을 고정해 stale 판정의 모호성을 제거합니다. """

        self.assertEqual(MODULE.build_nonce(NONCE), NONCE)
        for invalid in ("a" * 31, "A" * 32, "g" * 32, ""):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(MODULE.BlePairHilFailure, "nonce"):
                    MODULE.build_nonce(invalid)

    def test_evidence_binds_two_boards_images_and_raw_transcript_sha(self) -> None:
        """! @brief evidence가 두 UID·MSD·COM과 두 raw transcript hash를 기록합니다. """

        peripheral_raw = valid_peripheral_transcript()
        central_raw = valid_central_transcript()
        peripheral_result = MODULE.parse_peripheral_transcript(peripheral_raw, NONCE)
        central_result = MODULE.parse_central_transcript(central_raw, NONCE)
        execution = MODULE.PairExecution(
            peripheral=MODULE.RoleExecution("10", "1000", peripheral_raw),
            central=MODULE.RoleExecution("11", "1100", central_raw),
        )
        with tempfile.TemporaryDirectory(prefix="nu54-m16-pair-") as temporary:
            root = Path(temporary)
            peripheral_image = root / "peripheral.hex"
            central_image = root / "central.hex"
            peripheral_image.write_bytes(b":0100000001FE\n")
            central_image.write_bytes(b":0100000002FD\n")
            evidence = MODULE.build_evidence(
                core_revision="c" * 40,
                board_revision="d" * 40,
                nonce=NONCE,
                peripheral_endpoint=endpoint("a" * 32, "P:/", "COM10"),
                central_endpoint=endpoint("b" * 32, "Q:/", "COM11"),
                peripheral_image=peripheral_image,
                central_image=central_image,
                peripheral_image_size=peripheral_image.stat().st_size,
                central_image_size=central_image.stat().st_size,
                peripheral_image_sha256=MODULE.file_sha256(peripheral_image),
                central_image_sha256=MODULE.file_sha256(central_image),
                peripheral_build_record={"core_revision": "c" * 12},
                central_build_record={"core_revision": "c" * 12},
                peripheral_transcript_path=root / "pair.peripheral.transcript.log",
                central_transcript_path=root / "pair.central.transcript.log",
                execution=execution,
                peripheral_result=peripheral_result,
                central_result=central_result,
            )
        encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["boards"]["peripheral"]["daplink_uid"], "a" * 32)
        self.assertEqual(evidence["boards"]["central"]["uart_port"], "COM11")
        self.assertEqual(
            evidence["transcripts"]["peripheral"]["sha256"],
            hashlib.sha256(peripheral_raw).hexdigest(),
        )
        self.assertEqual(
            evidence["transcripts"]["central"]["sha256"],
            hashlib.sha256(central_raw).hexdigest(),
        )
        self.assertNotIn(str(root), encoded)

    def test_existing_evidence_requires_explicit_overwrite(self) -> None:
        """! @brief 기존 PASS와 companion raw transcript를 암묵적으로 덮지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-m16-evidence-") as temporary:
            evidence = Path(temporary) / "m16.json"
            peripheral = Path(temporary) / "m16.peripheral.transcript.log"
            evidence.write_text("{}\n", encoding="utf-8")
            peripheral.write_bytes(b"old")
            with self.assertRaisesRegex(MODULE.BlePairHilFailure, "덮어쓰지"):
                MODULE.prepare_output_paths(str(evidence), False)
            paths = MODULE.prepare_output_paths(str(evidence), True)
            self.assertEqual(paths[0], evidence.resolve())
            self.assertFalse(evidence.exists())
            self.assertFalse(peripheral.exists())


if __name__ == "__main__":
    unittest.main()
