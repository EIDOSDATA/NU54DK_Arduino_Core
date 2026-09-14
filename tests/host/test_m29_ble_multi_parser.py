#!/usr/bin/env python3
"""! @brief M29-W07-D 3보드 parser의 fail-closed 경계를 검증합니다. """

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from m29_ble_multi_protocol import (  # noqa: E402
    MultiProtocolFailure,
    expected_lines,
    parse_role_transcript,
    validate_three_role_session,
)


NONCE = "00112233445566778899aabbccddeeff"
REVISION = "1" * 40


def transcript(role: str) -> bytes:
    """! @brief 정상 role record를 CRLF transcript로 직렬화합니다. """

    return ("\r\n".join(expected_lines(role, NONCE, REVISION)) + "\r\n").encode("ascii")


class M29BleMultiParserTests(unittest.TestCase):
    """! @brief 정상 3-role 수락과 identity/order/정량 위반 거부를 검사합니다. """

    def assert_rejected(self, raw: bytes, role: str = "mixed") -> None:
        """! @brief 지정 transcript가 예외로 거부되는지 검사합니다. """

        with self.assertRaises(MultiProtocolFailure):
            parse_role_transcript(raw, role, NONCE, REVISION)

    def test_accepts_exact_three_role_session(self) -> None:
        results = {
            role: parse_role_transcript(transcript(role), role, NONCE, REVISION)
            for role in ("peripheral", "mixed", "central")
        }
        validate_three_role_session(results)
        self.assertEqual(results["mixed"].connections, 2)
        self.assertEqual(results["mixed"].coc_tx, 2000)

    def test_rejects_missing_record(self) -> None:
        records = expected_lines("mixed", NONCE, REVISION)
        self.assert_rejected(("\n".join(records[:3] + records[4:]) + "\n").encode())

    def test_rejects_duplicate_record(self) -> None:
        records = expected_lines("mixed", NONCE, REVISION)
        self.assert_rejected(("\n".join(records[:4] + records[3:]) + "\n").encode())

    def test_rejects_reordered_record(self) -> None:
        records = expected_lines("mixed", NONCE, REVISION)
        records[4], records[5] = records[5], records[4]
        self.assert_rejected(("\n".join(records) + "\n").encode())

    def test_rejects_stale_nonce(self) -> None:
        self.assert_rejected(transcript("mixed").replace(NONCE.encode(), b"f" * 32))

    def test_rejects_wrong_revision(self) -> None:
        self.assert_rejected(transcript("mixed").replace(REVISION.encode(), b"2" * 40))

    def test_rejects_ascii_noise(self) -> None:
        self.assert_rejected(b"boot noise\n" + transcript("mixed"))

    def test_rejects_non_ascii_noise(self) -> None:
        self.assert_rejected(b"\xff\n" + transcript("mixed"))

    def test_rejects_target_failure(self) -> None:
        raw = transcript("mixed").replace(
            b"M29W07D|1|RESULT|role=mixed",
            b"M29W07D|1|FAIL|role=mixed|stage=traffic",
        )
        self.assert_rejected(raw)

    def test_rejects_short_operation_count(self) -> None:
        self.assert_rejected(transcript("mixed").replace(b"gatt_tx=1000", b"gatt_tx=999"))

    def test_rejects_cross_link_event(self) -> None:
        self.assert_rejected(transcript("mixed").replace(b"cross_link=0", b"cross_link=1"))

    def test_rejects_trailing_record(self) -> None:
        self.assert_rejected(transcript("mixed") + transcript("mixed").splitlines()[0] + b"\n")

    def test_rejects_wrong_role(self) -> None:
        self.assert_rejected(transcript("central"), "mixed")

    def test_rejects_incomplete_role_set(self) -> None:
        results = {
            role: parse_role_transcript(transcript(role), role, NONCE, REVISION)
            for role in ("peripheral", "mixed")
        }
        with self.assertRaises(MultiProtocolFailure):
            validate_three_role_session(results)


if __name__ == "__main__":
    unittest.main()
