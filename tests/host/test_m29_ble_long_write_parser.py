"""! @brief M29-W03 fixed UART protocol parser의 fail-closed 동작을 검증합니다. """

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m29_ble_long_write import parse_role_transcript  # noqa: E402


NONCE = "00112233445566778899aabbccddeeff"
REVISION = "0123456789abcdef0123456789abcdef01234567"
SUFFIX = f"|nonce={NONCE}|core={REVISION}"


def transcript(role: str) -> bytes:
    """! @brief role별 정상 protocol transcript를 구성합니다. """

    common = [
        f"M29W03|1|READY|role={role}|core={REVISION}",
        f"M29W03|1|BEGIN|role={role}{SUFFIX}",
    ]
    if role == "peripheral":
        common += [
            f"M29W03|1|ADVERTISE|role=peripheral|status=pass{SUFFIX}",
            f"M29W03|1|LINK|role=peripheral|mtu=247{SUFFIX}",
            f"M29W03|1|RESULT|role=peripheral|writes=100|bytes=512|corrupt=0"
            f"|partial_commit=0|callback_context=pass{SUFFIX}",
            f"M29W03|1|END|role=peripheral|status=pass{SUFFIX}",
        ]
    else:
        common += [
            f"M29W03|1|SCAN|role=central|status=pass{SUFFIX}",
            f"M29W03|1|LINK|role=central|mtu=247{SUFFIX}",
            f"M29W03|1|RESULT|role=central|reads=100|writes=100|bytes=512"
            f"|corrupt=0|stale=0|callback_context=pass{SUFFIX}",
            f"M29W03|1|END|role=central|status=pass{SUFFIX}",
        ]
    return ("\r\n".join(common) + "\r\n").encode("ascii")


class M29BleLongWriteParserTests(unittest.TestCase):
    """! @brief strict identity·순서·정량 parser의 양성·음성 case입니다. """

    def assert_rejected(self, raw: bytes, role: str = "central") -> None:
        """! @brief 변형 transcript가 반드시 거부되는지 확인합니다. """

        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(raw, NONCE, REVISION, role)

    def test_accepts_exact_two_role_protocol(self):
        central = parse_role_transcript(transcript("central"), NONCE, REVISION, "central")
        peripheral = parse_role_transcript(
            transcript("peripheral"), NONCE, REVISION, "peripheral"
        )
        self.assertEqual(
            (central.mtu, central.reads, central.writes, central.payload_bytes),
            (247, 100, 100, 512),
        )
        self.assertEqual((peripheral.writes, peripheral.partial_commits), (100, 0))

    def test_rejects_noise(self):
        self.assert_rejected(b"noise\r\n" + transcript("central"))

    def test_rejects_non_ascii_noise(self):
        self.assert_rejected(b"\xff\r\n" + transcript("central"))

    def test_rejects_missing_record(self):
        lines = transcript("central").splitlines()
        self.assert_rejected(b"\n".join(lines[:3] + lines[4:]) + b"\n")

    def test_rejects_duplicate_record(self):
        lines = transcript("central").splitlines()
        self.assert_rejected(b"\n".join(lines[:2] + [lines[1]] + lines[2:]) + b"\n")

    def test_rejects_reordered_record(self):
        lines = transcript("central").splitlines()
        lines[2], lines[3] = lines[3], lines[2]
        self.assert_rejected(b"\n".join(lines) + b"\n")

    def test_rejects_stale_nonce(self):
        self.assert_rejected(transcript("central").replace(NONCE.encode(), b"f" * 32))

    def test_rejects_wrong_revision(self):
        self.assert_rejected(transcript("central").replace(REVISION.encode(), b"f" * 40))

    def test_rejects_wrong_quantitative_result(self):
        self.assert_rejected(transcript("central").replace(b"writes=100", b"writes=99"))
        self.assert_rejected(
            transcript("peripheral").replace(b"partial_commit=0", b"partial_commit=1"),
            "peripheral",
        )

    def test_rejects_target_fail(self):
        raw = transcript("central").replace(
            b"M29W03|1|RESULT|role=central",
            b"M29W03|1|FAIL|role=central|stage=write",
        )
        self.assert_rejected(raw)

    def test_rejects_wrong_role_and_invalid_revision_argument(self):
        self.assert_rejected(transcript("peripheral"), "central")
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript("central"), NONCE, "bad", "central")


if __name__ == "__main__":
    unittest.main(verbosity=2)
