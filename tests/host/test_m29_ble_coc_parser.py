#!/usr/bin/env python3
"""! @brief M29-W06 두 role CoC transcript parser의 fail-closed 경계를 검증합니다. """

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m29_ble_coc import parse_role_transcript  # noqa: E402


NONCE = "00112233445566778899aabbccddeeff"
REVISION = "1" * 40
SUFFIX = f"|nonce={NONCE}|core={REVISION}"


def lines(role: str) -> list[str]:
    """! @brief role별 정상 W06 고정 record를 만듭니다. """

    records = [
        f"M29W06|1|READY|role={role}|core={REVISION}",
        f"M29W06|1|BEGIN|role={role}{SUFFIX}",
    ]
    if role == "peripheral":
        records.extend(
            (
                f"M29W06|1|ADVERTISE|role=peripheral|psm=128|status=pass{SUFFIX}",
                "M29W06|1|NEG|role=peripheral|class=offset|attempts=20"
                f"|rejected=20|unexpected=0{SUFFIX}",
                "M29W06|1|NEG|role=peripheral|class=execute|attempts=20"
                f"|rejected=20|unexpected=0{SUFFIX}",
            )
        )
    else:
        records.append(f"M29W06|1|SCAN|role=central|status=pass{SUFFIX}")
    records.append(
        f"M29W06|1|CHANNELS|role={role}|connected=2|local_mtu=512"
        f"|remote_mtu=512{SUFFIX}"
    )
    if role == "central":
        for error_class in ("malformed", "psm", "credit"):
            records.append(
                f"M29W06|1|NEG|role=central|class={error_class}|attempts=20"
                f"|rejected=20|unexpected=0{SUFFIX}"
            )
    records.append(
        f"M29W06|1|COC|role={role}|channels=2|sdu=512|tx_per_channel=1000"
        f"|rx_per_channel=1000|payload_errors=0{SUFFIX}"
    )
    if role == "peripheral":
        records.extend(
            (
                "M29W06|1|RECOVERY|role=peripheral|new_channels=2|echoes=2"
                f"|failures=0{SUFFIX}",
                "M29W06|1|RESULT|role=peripheral|offset=20|execute=20"
                "|unexpected=0|recovery_failures=0|cross_channel=0"
                f"|callback_context=pass{SUFFIX}",
            )
        )
    else:
        records.extend(
            (
                "M29W06|1|RECOVERY|role=central|old_rejected=2|new_channels=2"
                f"|echoes=2|failures=0{SUFFIX}",
                "M29W06|1|RESULT|role=central|malformed=20|psm=20|credit=20"
                "|unexpected=0|recovery_failures=0|stale=0"
                f"|callback_context=pass{SUFFIX}",
            )
        )
    records.append(f"M29W06|1|END|role={role}|status=pass{SUFFIX}")
    return records


def transcript(role: str) -> bytes:
    """! @brief 정상 record를 CRLF transcript로 직렬화합니다. """

    return ("\r\n".join(lines(role)) + "\r\n").encode("ascii")


class M29BleCocParserTests(unittest.TestCase):
    """! @brief 정상 수락과 identity/order/정량 위반 거부를 검사합니다. """

    def assert_rejected(self, raw: bytes, role: str = "central") -> None:
        """! @brief 지정 transcript가 예외로 거부되는지 검사합니다. """

        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(raw, NONCE, REVISION, role)

    def test_accepts_exact_roles(self) -> None:
        central = parse_role_transcript(transcript("central"), NONCE, REVISION, "central")
        peripheral = parse_role_transcript(
            transcript("peripheral"), NONCE, REVISION, "peripheral"
        )
        self.assertEqual((central.channels, central.credit_rejected), (2, 20))
        self.assertEqual(
            (peripheral.offset_rejected, peripheral.execute_rejected), (20, 20)
        )

    def test_rejects_missing_record(self) -> None:
        records = lines("central")
        self.assert_rejected(("\n".join(records[:5] + records[6:]) + "\n").encode())

    def test_rejects_duplicate_record(self) -> None:
        records = lines("central")
        self.assert_rejected(("\n".join(records[:5] + records[4:]) + "\n").encode())

    def test_rejects_reordered_record(self) -> None:
        records = lines("central")
        records[4], records[5] = records[5], records[4]
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
                b"M29W06|1|RESULT|role=central",
                b"M29W06|1|FAIL|role=central|stage=traffic",
            )
        )

    def test_rejects_wrong_quantitative_value(self) -> None:
        self.assert_rejected(
            transcript("central").replace(b"tx_per_channel=1000", b"tx_per_channel=999")
        )

    def test_rejects_wrong_role(self) -> None:
        self.assert_rejected(transcript("central"), "peripheral")

    def test_rejects_invalid_revision_argument(self) -> None:
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript("central"), NONCE, "bad", "central")


if __name__ == "__main__":
    unittest.main()
