#!/usr/bin/env python3
"""! @brief M31 Audio LC3 transcript의 수락·변조 거부를 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


HIL = Path(__file__).resolve().parents[1] / "hil/nu54dk"
sys.path.insert(0, str(HIL))

from m31_audio_lc3 import M31AudioLc3Failure, parse_lc3_transcript, validate_lc3_envelope  # noqa: E402
from m31_ble_capability import ExpectedIdentity  # noqa: E402


IDENTITY = ExpectedIdentity("1" * 40, "2" * 40, "3" * 40, "4" * 40)
NONCES = [f"{index:032x}" for index in range(20)]


def transcript() -> bytes:
    """! @brief 정상 20-cycle fixture를 만듭니다. """
    lines = ["NUCODE_AUDIO|1|READY|scenario=lc3-loopback|role=codec"]
    for nonce in NONCES:
        lines.extend((
            f"NUCODE_AUDIO|1|NEG_END|nonce={nonce}|scenario=lc3-loopback|rejected=2|invalid_accept=0",
            f"NUCODE_AUDIO|1|BEGIN|nonce={nonce}|scenario=lc3-loopback|role=codec",
            f"NUCODE_AUDIO|1|IDENTITY|nonce={nonce}|core={IDENTITY.core}|board={IDENTITY.board}|ncs={IDENTITY.ncs}|zephyr={IDENTITY.zephyr}",
            f"NUCODE_AUDIO|1|END|nonce={nonce}|scenario=lc3-loopback|encoded=100|decoded=100|frame_samples=160|frame_octets=40|checksum=1234|energy=5678|plc=0|errors=0",
            f"NUCODE_AUDIO|1|STOPPED|nonce={nonce}|scenario=lc3-loopback",
        ))
    return ("\n".join(lines) + "\n").encode("ascii")


class M31AudioLc3Tests(unittest.TestCase):
    """! @brief 실제 parser의 분모·identity·negative 경계를 검사합니다. """

    def test_accepts_complete_twenty_cycles(self) -> None:
        """! @brief 2,000 frame과 40개 invalid 거부를 수락합니다. """
        result = parse_lc3_transcript(transcript(), NONCES, IDENTITY)
        self.assertEqual((result.cycles, result.encoded_frames, result.decoded_frames,
                          result.rejected_invalid), (20, 2000, 2000, 40))

    def test_rejects_mutated_counts_identity_and_order(self) -> None:
        """! @brief 수치·revision·순서 변조를 각각 거부합니다. """
        raw = transcript()
        mutations = (
            raw.replace(b"encoded=100", b"encoded=99", 1),
            raw.replace(("core=" + IDENTITY.core).encode(), b"core=" + b"a" * 40, 1),
            raw.replace(b"|rejected=2|invalid_accept=0", b"|rejected=1|invalid_accept=1", 1),
            raw.replace(b"|END|", b"|STOPPED|", 1),
        )
        for mutated in mutations:
            with self.subTest(mutated=mutated[:80]):
                with self.assertRaises(M31AudioLc3Failure):
                    parse_lc3_transcript(mutated, NONCES, IDENTITY)

    def test_exact_envelope_requires_clean_hardware_reset_evidence(self) -> None:
        """! @brief dirty source와 이전 flash mode를 exact PASS에서 거부합니다. """
        image = "5" * 64
        envelope = {
            "source_clean": True,
            "test_id": "M31-AUDIO-01:W03-01",
            "transcript": transcript(),
            "nonces": NONCES,
            "board": {
                "image_sha256": image,
                "probe_sha256": "6" * 64,
                "flash_mode": "pyocd-sector-hw-reset",
            },
        }
        self.assertEqual(validate_lc3_envelope(envelope, image, IDENTITY).cycles, 20)
        for key, value in (("source_clean", False), ("test_id", "M31-AUDIO-01:W03-02")):
            altered = dict(envelope)
            altered[key] = value
            with self.assertRaises(M31AudioLc3Failure):
                validate_lc3_envelope(altered, image, IDENTITY)
        altered = dict(envelope)
        altered["board"] = {**envelope["board"], "flash_mode": "pyocd-sector"}
        with self.assertRaises(M31AudioLc3Failure):
            validate_lc3_envelope(altered, image, IDENTITY)


if __name__ == "__main__":
    unittest.main()
