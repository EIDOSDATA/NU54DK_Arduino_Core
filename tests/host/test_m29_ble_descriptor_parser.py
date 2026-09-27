#!/usr/bin/env python3
"""! @brief M29-W04 두 role transcript parser의 fail-closed 경계를 검증합니다. """

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m29_ble_descriptor import parse_role_transcript  # noqa: E402


NONCE = "00112233445566778899aabbccddeeff"
REVISION = "1" * 40
SUFFIX = f"|nonce={NONCE}|core={REVISION}"


def lines(role: str) -> list[str]:
    """! @brief role별 정상 W04 고정 record를 만듭니다. """

    records = [
        f"M29W04|1|READY|role={role}|core={REVISION}",
        f"M29W04|1|BEGIN|role={role}{SUFFIX}",
    ]
    if role == "peripheral":
        records.extend(
            (
                f"M29W04|1|ADVERTISE|role=peripheral|status=pass{SUFFIX}",
                f"M29W04|1|LINK|role=peripheral|mtu=247{SUFFIX}",
                "M29W04|1|RESULT|role=peripheral|descriptors=4"
                "|authorization_checks=402|allowed=401|denied=1|descriptor_writes=0"
                f"|authorization_errors=0|callback_context=pass{SUFFIX}",
            )
        )
    else:
        records.extend(
            (
                f"M29W04|1|SCAN|role=central|status=pass{SUFFIX}",
                f"M29W04|1|LINK|role=central|mtu=247{SUFFIX}",
                "M29W04|1|RESULT|role=central|descriptors=4|reads=100|handles=4"
                "|bytes=16|expected_denials=1|authorization_errors=0|corrupt=0"
                f"|stale=0|callback_context=pass{SUFFIX}",
            )
        )
    records.append(f"M29W04|1|END|role={role}|status=pass{SUFFIX}")
    return records


def transcript(role: str) -> bytes:
    """! @brief 정상 record를 CRLF transcript로 직렬화합니다. """

    return ("\r\n".join(lines(role)) + "\r\n").encode("ascii")


class M29BleDescriptorParserTests(unittest.TestCase):
    """! @brief 정상 수락과 모든 identity/order 위반 거부를 검사합니다. """

    def assert_rejected(self, raw: bytes, role: str = "central") -> None:
        """! @brief 지정 transcript가 예외로 거부되는지 검사합니다. """

        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(raw, NONCE, REVISION, role)

    def test_accepts_exact_roles(self) -> None:
        central = parse_role_transcript(transcript("central"), NONCE, REVISION, "central")
        peripheral = parse_role_transcript(
            transcript("peripheral"), NONCE, REVISION, "peripheral"
        )
        self.assertEqual((central.reads, central.handles), (100, 4))
        self.assertEqual(
            (peripheral.authorization_checks, peripheral.authorization_denied),
            (402, 1),
        )

    def test_rejects_missing_record(self) -> None:
        records = lines("central")
        self.assert_rejected(("\n".join(records[:3] + records[4:]) + "\n").encode())

    def test_rejects_duplicate_record(self) -> None:
        records = lines("central")
        self.assert_rejected(("\n".join(records[:3] + records[2:]) + "\n").encode())

    def test_rejects_reordered_record(self) -> None:
        records = lines("central")
        records[2], records[3] = records[3], records[2]
        self.assert_rejected(("\n".join(records) + "\n").encode())

    def test_rejects_stale_nonce(self) -> None:
        self.assert_rejected(transcript("central").replace(NONCE.encode(), b"f" * 32))

    def test_rejects_wrong_revision(self) -> None:
        self.assert_rejected(transcript("central").replace(REVISION.encode(), b"2" * 40))

    def test_rejects_ascii_noise(self) -> None:
        self.assert_rejected(b"boot noise\n" + transcript("central"))

    def test_rejects_non_ascii_noise(self) -> None:
        self.assert_rejected(b"\xff\n" + transcript("central"))

    def test_rejects_target_failure(self) -> None:
        self.assert_rejected(
            transcript("central").replace(
                b"M29W04|1|RESULT|role=central",
                b"M29W04|1|FAIL|role=central|stage=read",
            )
        )

    def test_rejects_wrong_quantitative_value(self) -> None:
        self.assert_rejected(transcript("central").replace(b"reads=100", b"reads=99"))

    def test_rejects_invalid_revision_argument(self) -> None:
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript("central"), NONCE, "bad", "central")


if __name__ == "__main__":
    unittest.main()
