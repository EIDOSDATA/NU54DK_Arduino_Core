#!/usr/bin/env python3
"""! @brief 실제 20-cycle ISO timestamp 원본과 후보 승격 차단을 검사합니다. """

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
sys.path.insert(0, str(HIL))
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_iso_time import M31TimeFailure, parse_time_transcript, validate_time_envelope  # noqa: E402


TRANSCRIPT = (ROOT / "tests/host/fixtures/m31_iso_time_20cycle_dev_candidate.log").read_bytes()
NONCES = list(dict.fromkeys(re.findall(
    rb"source: M31BIS\|1\|BEGIN\|nonce=([0-9a-f]{32})\|role=source", TRANSCRIPT
)))
NONCES = [item.decode("ascii") for item in NONCES]
IDENTITY = ExpectedIdentity(
    "26270df3bcddd2cd39c866c346047bb170cd7df4",
    "fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3",
    "99553055607b2e9885fbc80ccd11fa9da81c2df0",
    "bf801e4e3d19e1ffa76164346480cb7734dd2800",
)


class M31IsoTimeTests(unittest.TestCase):
    """! @brief source·receiver 독립 시계에서 10ms 관계와 반환을 판정합니다. """

    def test_real_twenty_cycle_time_transcript_has_all_valid_sdu(self) -> None:
        """! @brief 실제 20회 2,000 timestamp 수신과 1,980 explicit 송신을 확인합니다. """
        result = parse_time_transcript(TRANSCRIPT, NONCES, IDENTITY)
        self.assertEqual((result.cycles, result.total_sent, result.total_received), (20, 2000, 2000))
        self.assertEqual((result.valid_monotonic, result.timestamped_sent,
                          result.stale_callback), (2000, 1980, 0))

    def test_missing_or_wrong_timestamp_and_stale_callback_fail(self) -> None:
        """! @brief TIME event 절단·시각 관계·stale 결과를 각각 거부합니다. """
        for corrupted in (
            TRANSCRIPT.replace(b"|TIME_END|nonce=", b"|TIME_MISSING|nonce=", 1),
            TRANSCRIPT.replace(b"|stale=0|", b"|stale=1|", 1),
            TRANSCRIPT.replace(b"|timestamped=99|", b"|timestamped=98|", 1),
            re.sub(rb"\|last_ts=\d+", b"|last_ts=1", TRANSCRIPT, count=1),
        ):
            with self.subTest(corrupted=corrupted[:60]):
                with self.assertRaises(M31TimeFailure):
                    parse_time_transcript(corrupted, NONCES, IDENTITY)

    def test_dirty_time_attempt_cannot_be_exact(self) -> None:
        """! @brief 기능 분모가 맞아도 미커밋 firmware를 마감 증거로 승격하지 않습니다. """
        images = {"source": "a" * 64, "receiver": "b" * 64}
        envelope = {
            "source_clean": False, "test_id": "M31-ISO-01:time_sync",
            "transcript": TRANSCRIPT, "nonces": NONCES,
            "boards": {
                "source": {"image_sha256": images["source"], "probe_sha256": "c" * 64},
                "receiver": {"image_sha256": images["receiver"], "probe_sha256": "d" * 64},
            },
        }
        with self.assertRaisesRegex(M31TimeFailure, "미커밋"):
            validate_time_envelope(envelope, images, IDENTITY)


if __name__ == "__main__":
    unittest.main()
