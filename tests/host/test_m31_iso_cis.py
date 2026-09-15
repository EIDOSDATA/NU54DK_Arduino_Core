"""! @brief 실제 20-cycle 개발 transcript의 무결성 및 완료 승격 차단을 검사합니다. """

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
sys.path.insert(0, str(HIL))
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_iso_cis import M31IsoFailure, parse_cis_transcript, validate_cis_envelope  # noqa: E402


TRANSCRIPT = (ROOT / "tests/host/fixtures/m31_iso_cis_20cycle_dev_candidate.log").read_bytes()
NONCES = list(dict.fromkeys(re.findall(
    rb"peripheral: M31ISO\|1\|BEGIN\|nonce=([0-9a-f]{32})\|role=peripheral", TRANSCRIPT
)))
NONCES = [item.decode("ascii") for item in NONCES]
IDENTITY = ExpectedIdentity(
    "10f16eaa913f9b1d1906239fbe6ff98c53c73cd1",
    "fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3",
    "99553055607b2e9885fbc80ccd11fa9da81c2df0",
    "bf801e4e3d19e1ffa76164346480cb7734dd2800",
)


class M31IsoCisTests(unittest.TestCase):
    """! @brief 기능 측정과 후보 증거의 단계 구분을 검증합니다. """

    def test_real_twenty_cycle_candidate_has_all_sdu_and_stop_records(self) -> None:
        """! @brief 실제 보드 출력에서 20회 × 100 유효 SDU를 검출합니다. """
        result = parse_cis_transcript(TRANSCRIPT, NONCES, IDENTITY)
        self.assertEqual((result.cycles, result.total_sent, result.total_received), (20, 2000, 2000))
        self.assertEqual(result.minimum_received, 100)

    def test_corrupt_counter_or_missing_stop_fails_closed(self) -> None:
        """! @brief 종료 일부와 payload 오류를 보드 성공으로 숨기지 않습니다. """
        corrupt = TRANSCRIPT.replace(b"|received=100|corrupt=0|", b"|received=100|corrupt=1|", 1)
        with self.assertRaises(M31IsoFailure):
            parse_cis_transcript(corrupt, NONCES, IDENTITY)
        truncated = TRANSCRIPT.replace(
            b"central: M31ISO|1|STOPPED|nonce=" + NONCES[0].encode(),
            b"central: M31ISO|1|MISSING|nonce=" + NONCES[0].encode(), 1,
        )
        with self.assertRaises(M31IsoFailure):
            parse_cis_transcript(truncated, NONCES, IDENTITY)

    def test_unknown_role_nonce_and_partial_transcript_fail(self) -> None:
        """! @brief 역할·nonce·출력 절단 오류를 각각 거부합니다. """
        wrong_nonce = TRANSCRIPT.replace(NONCES[0].encode(), b"0" * 32, 1)
        with self.assertRaises(M31IsoFailure):
            parse_cis_transcript(wrong_nonce, NONCES, IDENTITY)
        unknown_role = TRANSCRIPT.replace(b"peripheral: M31ISO|1|READY", b"receiver: M31ISO|1|READY", 1)
        with self.assertRaises(M31IsoFailure):
            parse_cis_transcript(unknown_role, NONCES, IDENTITY)
        with self.assertRaises(M31IsoFailure):
            parse_cis_transcript(TRANSCRIPT[:-1], NONCES, IDENTITY)

    def test_dirty_development_attempt_cannot_be_exact_evidence(self) -> None:
        """! @brief 유효한 개발 transcript도 clean image 증거로 승격하지 않습니다. """
        images = {"central": "a" * 64, "peripheral": "b" * 64}
        envelope = {
            "source_clean": False, "test_id": "M31-ISO-01:cis", "transcript": TRANSCRIPT,
            "nonces": NONCES,
            "boards": {
                "central": {"image_sha256": images["central"], "probe_sha256": "c" * 64},
                "peripheral": {"image_sha256": images["peripheral"], "probe_sha256": "d" * 64},
            },
        }
        with self.assertRaisesRegex(M31IsoFailure, "미커밋"):
            validate_cis_envelope(envelope, images, IDENTITY)


if __name__ == "__main__":
    unittest.main()
