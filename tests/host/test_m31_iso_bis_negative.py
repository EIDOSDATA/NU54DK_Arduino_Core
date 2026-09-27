#!/usr/bin/env python3
"""! @file test_m31_iso_bis_negative.py
@brief 두 실제 BIS negative 원본의 거부 원인과 새 BIG 복구를 검증합니다.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_iso_bis import M31BisFailure  # noqa: E402
from m31_iso_bis_negative import parse_negative_transcript, validate_negative_envelope  # noqa: E402


TRANSCRIPTS = {
    "wrong_broadcast_code": (ROOT / "tests/host/fixtures/m31_iso_bis_bad_code_dev_candidate.log").read_bytes(),
    "sync_loss": (ROOT / "tests/host/fixtures/m31_iso_bis_sync_loss_dev_candidate.log").read_bytes(),
}
IDENTITY = ExpectedIdentity(
    "9753c253cdc5ca9e68fd27e2b42e876a99fe21a4",
    "fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3",
    "99553055607b2e9885fbc80ccd11fa9da81c2df0",
    "bf801e4e3d19e1ffa76164346480cb7734dd2800",
)


def nonces(transcript: bytes) -> list[str]:
    """! @brief 실제 source session의 두 nonce를 순서대로 선택합니다. """
    return [item.decode("ascii") for item in re.findall(
        rb"source: M31BIS\|1\|BEGIN\|nonce=([0-9a-f]{32})\|role=source", transcript
    )]


class M31BisNegativeTests(unittest.TestCase):
    """! @brief MIC 거부·PA 손실의 false positive와 dirty 승격을 막습니다. """

    def test_actual_mic_and_pa_loss_recover_with_new_100_sdu_big(self) -> None:
        """! @brief 실기 두 원본에서 실패 1회와 즉시 100개 payload 복구를 판정합니다. """
        for negative_class, transcript in TRANSCRIPTS.items():
            with self.subTest(negative_class=negative_class):
                result = parse_negative_transcript(transcript, nonces(transcript),
                                                   IDENTITY, negative_class)
                self.assertEqual((result.cycles, result.rejected_payloads,
                                  result.recovery_sent, result.recovery_received),
                                 (2, 0, 100, 100))

    def test_mic_reason_payload_leak_and_lost_recovery_fail_closed(self) -> None:
        """! @brief wrong code가 RF 손실·payload 유출·복구 손상을 성공으로 가장하지 못합니다. """
        raw = TRANSCRIPTS["wrong_broadcast_code"]
        changes = (
            raw.replace(b"BAD_CODE_DISCONNECTED|nonce=" + nonces(raw)[0].encode() + b"|reason=61",
                        b"BAD_CODE_DISCONNECTED|nonce=" + nonces(raw)[0].encode() + b"|reason=19", 1),
            raw.replace(b"BAD_CODE_REJECTED|nonce=" + nonces(raw)[0].encode() + b"|received=0",
                        b"BAD_CODE_REJECTED|nonce=" + nonces(raw)[0].encode() + b"|received=1", 1),
            raw.replace(b"|corrupt=0|", b"|corrupt=1|", 1),
        )
        for corrupted in changes:
            with self.subTest(corrupted=corrupted[:80]):
                with self.assertRaises(M31BisFailure):
                    parse_negative_transcript(corrupted, nonces(raw), IDENTITY,
                                              "wrong_broadcast_code")

    def test_pa_loss_requires_induced_stop_and_complete_restart(self) -> None:
        """! @brief loss 이벤트·peer 해제·같은 nonce 100 SDU 복구의 누락을 거부합니다. """
        raw = TRANSCRIPTS["sync_loss"]
        corrupted = (
            raw.replace(b"receiver: M31BIS|1|SYNC_LOST", b"receiver: M31BIS|1|LOSS_MISSING", 1),
            raw.replace(b"|reason=19", b"|reason=22", 1),
            raw.replace(b"|role=source|tx=0|rx=0", b"|role=source|tx=100|rx=0", 1),
            raw[:-1],
        )
        for candidate in corrupted:
            with self.subTest(candidate=candidate[:80]):
                with self.assertRaises(M31BisFailure):
                    parse_negative_transcript(candidate, nonces(raw), IDENTITY, "sync_loss")

    def test_dirty_candidate_cannot_be_marked_exact(self) -> None:
        """! @brief clean 이미지·이중 probe 경계 없이 negative PASS를 쓰지 않습니다. """
        transcript = TRANSCRIPTS["wrong_broadcast_code"]
        images = {"source": "a" * 64, "receiver": "b" * 64}
        envelope = {
            "source_clean": False,
            "test_id": "M31-ISO-01:bis",
            "negative_class": "wrong_broadcast_code",
            "nonces": nonces(transcript),
            "transcript": transcript,
            "boards": {
                "source": {"image_sha256": images["source"], "probe_sha256": "c" * 64},
                "receiver": {"image_sha256": images["receiver"], "probe_sha256": "d" * 64},
            },
        }
        with self.assertRaises(M31BisFailure):
            validate_negative_envelope(envelope, images, IDENTITY)


if __name__ == "__main__":
    unittest.main()
