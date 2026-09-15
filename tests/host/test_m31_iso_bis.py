#!/usr/bin/env python3
"""! @brief 실제 20-cycle BIS 후보 출력의 단계·무결성 경계를 검사합니다. """

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
sys.path.insert(0, str(HIL))
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_iso_bis import M31BisFailure, parse_bis_transcript, validate_bis_envelope  # noqa: E402


TRANSCRIPT = (ROOT / "tests/host/fixtures/m31_iso_bis_20cycle_dev_candidate.log").read_bytes()
NONCES = list(dict.fromkeys(re.findall(
    rb"source: M31BIS\|1\|BEGIN\|nonce=([0-9a-f]{32})\|role=source", TRANSCRIPT
)))
NONCES = [item.decode("ascii") for item in NONCES]
IDENTITY = ExpectedIdentity(
    "9cc1d21505c493d11e316f92a16fa4f4684e6107",
    "fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3",
    "99553055607b2e9885fbc80ccd11fa9da81c2df0",
    "bf801e4e3d19e1ffa76164346480cb7734dd2800",
)


class M31IsoBisTests(unittest.TestCase):
    """! @brief 실제 radio 결과와 후보 승격·오류 입력 차단을 확인합니다. """

    def test_real_candidate_has_20_complete_big_and_sdu_cycles(self) -> None:
        """! @brief 두 실제 보드의 2000 TX·2000 RX와 양 BIG 반환을 판정합니다. """
        result = parse_bis_transcript(TRANSCRIPT, NONCES, IDENTITY)
        self.assertEqual((result.cycles, result.total_sent, result.total_received), (20, 2000, 2000))
        self.assertEqual(result.minimum_received, 100)
        self.assertGreater(result.empty_slots, 0)

    def test_corrupt_order_and_missing_big_return_fail_closed(self) -> None:
        """! @brief payload 오류·역순 수신·BIG 자원 반환 누락을 각각 거부합니다. """
        for corrupted in (
            TRANSCRIPT.replace(b"|corrupt=0|", b"|corrupt=1|", 1),
            TRANSCRIPT.replace(b"|out_of_order=0|", b"|out_of_order=1|", 1),
            TRANSCRIPT.replace(b"source: M31BIS|1|BIG_DISCONNECTED|nonce=",
                               b"source: M31BIS|1|BIG_MISSING|nonce=", 1),
        ):
            with self.subTest(corrupted=corrupted[:60]):
                with self.assertRaises(M31BisFailure):
                    parse_bis_transcript(corrupted, NONCES, IDENTITY)

    def test_stale_nonce_role_and_truncated_output_fail_closed(self) -> None:
        """! @brief 다른 세션·role과 잘린 UART를 성공 증거로 사용하지 않습니다. """
        for corrupted in (
            TRANSCRIPT.replace(NONCES[0].encode(), b"0" * 32, 1),
            TRANSCRIPT.replace(b"receiver: M31BIS|1|READY", b"unknown: M31BIS|1|READY", 1),
            TRANSCRIPT[:-1],
        ):
            with self.subTest(corrupted=corrupted[:60]):
                with self.assertRaises(M31BisFailure):
                    parse_bis_transcript(corrupted, NONCES, IDENTITY)

    def test_dirty_candidate_cannot_be_exact_evidence(self) -> None:
        """! @brief 개발 시도는 SDU 분모가 충족돼도 exact PASS가 아닙니다. """
        images = {"source": "a" * 64, "receiver": "b" * 64}
        envelope = {
            "source_clean": False, "test_id": "M31-ISO-01:bis", "transcript": TRANSCRIPT,
            "nonces": NONCES,
            "boards": {
                "source": {"image_sha256": images["source"], "probe_sha256": "c" * 64},
                "receiver": {"image_sha256": images["receiver"], "probe_sha256": "d" * 64},
            },
        }
        with self.assertRaisesRegex(M31BisFailure, "미커밋"):
            validate_bis_envelope(envelope, images, IDENTITY)


if __name__ == "__main__":
    unittest.main()
