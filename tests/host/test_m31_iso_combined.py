#!/usr/bin/env python3
"""! @file test_m31_iso_combined.py
@brief 실제 세 보드 개발 원본에서 CIS→BIS 전달과 거짓 완료를 확인합니다.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_iso_combined import M31CombinedFailure, parse_combined_transcript, validate_combined_envelope  # noqa: E402


RAW = (ROOT / "tests/host/fixtures/m31_iso_combined_dev_candidate.log").read_bytes()
BOARD = "fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3"
NCS = "99553055607b2e9885fbc80ccd11fa9da81c2df0"
ZEPHYR = "bf801e4e3d19e1ffa76164346480cb7734dd2800"
SOURCE = ExpectedIdentity("64c6b5fcaad3b0330f181d5b5f814b00a14e41bf", BOARD, NCS, ZEPHYR)
RECEIVER = ExpectedIdentity("078587471637db187e508db2deec7d091a8262ef", BOARD, NCS, ZEPHYR)
IDENTITIES = {"peer": SOURCE, "combined": SOURCE, "receiver": RECEIVER}
NONCE = re.findall(rb"combined: M31COMB\|1\|BEGIN\|nonce=([0-9a-f]{32})", RAW)[0].decode("ascii")


class M31CombinedTests(unittest.TestCase):
    """! @brief CIS 입력·BIS 출력·세 보드 source의 필수 경계를 검사합니다. """

    def test_actual_three_board_forwarding(self) -> None:
        """! @brief 관찰된 100 SDU가 중간 CIS와 끝 BIS에서 모두 일치합니다. """
        result = parse_combined_transcript(RAW, [NONCE], IDENTITIES, 1)
        self.assertEqual((result.peer_sent, result.cis_received,
                          result.bis_forwarded, result.bis_received), (100, 100, 100, 100))

    def test_missing_or_corrupt_forwarding_fails_closed(self) -> None:
        """! @brief 입력만 성공하고 전달이 누락·오염된 원본을 거부합니다. """
        mutations = (
            RAW.replace(b"|sent=100|cross_stream=0", b"|sent=99|cross_stream=0", 1),
            RAW.replace(b"|corrupt=0|duplicate=0|cross_stream=0",
                        b"|corrupt=1|duplicate=0|cross_stream=0", 1),
            RAW.replace(b"|cross_stream=0|empty_slots=", b"|cross_stream=1|empty_slots=", 1),
            RAW.replace(b"receiver: M31BIS|1|RX_END", b"receiver: M31BIS|1|RX_MISSING", 1),
            RAW[:-1],
        )
        for candidate in mutations:
            with self.subTest(candidate=candidate[:80]):
                with self.assertRaises(M31CombinedFailure):
                    parse_combined_transcript(candidate, [NONCE], IDENTITIES, 1)

    def test_wrong_qos_or_source_revision_fails_closed(self) -> None:
        """! @brief controller TX 경로 및 receiver source가 다르면 성공하지 않습니다. """
        candidates = (
            RAW.replace(b"|can_send=1|p_bn=1|max_sdu=8",
                        b"|can_send=0|p_bn=1|max_sdu=8", 1),
            RAW.replace(b"receiver: M31BIS|1|IDENTITY|nonce=" + NONCE.encode() + b"|core=07858747",
                        b"receiver: M31BIS|1|IDENTITY|nonce=" + NONCE.encode() + b"|core=64c6b5fc", 1),
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate[:80]):
                with self.assertRaises(M31CombinedFailure):
                    parse_combined_transcript(candidate, [NONCE], IDENTITIES, 1)

    def test_dirty_one_cycle_cannot_be_exact(self) -> None:
        """! @brief 개발 원본과 단일 session은 20회 exact 승격을 막습니다. """
        images = {"peer": "a" * 64, "combined": "b" * 64, "receiver": "c" * 64}
        envelope = {
            "source_clean": False,
            "test_id": "M31-ISO-01:bis_cis_combined",
            "cycles": 1,
            "identity": vars(SOURCE),
            "nonces": [NONCE],
            "transcript": RAW,
            "boards": {
                role: {"image_sha256": images[role], "probe_sha256": str(index) * 64,
                       "flash_mode": "pyocd-sector"}
                for index, role in enumerate(images, 1)
            },
        }
        with self.assertRaises(M31CombinedFailure):
            validate_combined_envelope(envelope, images, SOURCE)


if __name__ == "__main__":
    unittest.main()
