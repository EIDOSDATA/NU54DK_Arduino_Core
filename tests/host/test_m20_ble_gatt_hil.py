#!/usr/bin/env python3
"""! @brief M20 generic GATT 두 보드 HIL protocol parser를 host에서 검증합니다. """

from pathlib import Path
import sys
import unittest


HIL_DIRECTORY = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m20_ble_gatt import (  # noqa: E402
    parse_central_transcript,
    parse_peripheral_transcript,
)


NONCE = "0123456789abcdef0123456789abcdef"


def transcript(lines: tuple[str, ...]) -> bytes:
    """! @brief synthetic UART line을 CRLF raw transcript로 만듭니다. """

    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def central_lines(nonce: str = NONCE) -> tuple[str, ...]:
    """! @brief valid central generic GATT protocol 순서를 반환합니다. """

    suffix = f":nonce={nonce}"
    return (
        "NUCODE_M20_READY:role=central",
        "NUCODE_M20_CENTRAL:SCAN_FILTER:PASS" + suffix,
        "NUCODE_M20_EVENT:CONNECTED:round=1" + suffix,
        "NUCODE_M20_CENTRAL:DISCOVERY:PASS:round=1" + suffix,
        "NUCODE_M20_CENTRAL:NONCE_CHALLENGE:PASS" + suffix,
        "NUCODE_M20_CENTRAL:READ:PASS" + suffix,
        "NUCODE_M20_CENTRAL:WRITE_RESPONSE:PASS" + suffix,
        "NUCODE_M20_CENTRAL:WRITE_COMMAND:PASS" + suffix,
        "NUCODE_M20_CENTRAL:SUBSCRIBE_NOTIFY:PASS:round=1" + suffix,
        "NUCODE_M20_CENTRAL:NOTIFICATION:PASS:round=1" + suffix,
        "NUCODE_M20_CENTRAL:UNSUBSCRIBE_NOTIFY:PASS:round=1" + suffix,
        "NUCODE_M20_CENTRAL:SUBSCRIBE_INDICATE:PASS" + suffix,
        "NUCODE_M20_CENTRAL:INDICATION:PASS" + suffix,
        "NUCODE_M20_CENTRAL:UNSUBSCRIBE_INDICATE:PASS" + suffix,
        "NUCODE_M20_EVENT:DISCONNECTED:count=1" + suffix,
        "NUCODE_M20_CENTRAL:HANDLES_INVALIDATED:PASS:round=1" + suffix,
        "NUCODE_M20_CENTRAL:RECONNECT_REQUEST:PASS" + suffix,
        "NUCODE_M20_EVENT:CONNECTED:round=2" + suffix,
        "NUCODE_M20_CENTRAL:DISCOVERY:PASS:round=2" + suffix,
        "NUCODE_M20_CENTRAL:SUBSCRIBE_NOTIFY:PASS:round=2" + suffix,
        "NUCODE_M20_CENTRAL:NOTIFICATION:PASS:round=2" + suffix,
        "NUCODE_M20_CENTRAL:UNSUBSCRIBE_NOTIFY:PASS:round=2" + suffix,
        "NUCODE_M20_EVENT:DISCONNECTED:count=2" + suffix,
        "NUCODE_M20_CENTRAL:HANDLES_INVALIDATED:PASS:round=2" + suffix,
        "NUCODE_M20_CENTRAL:FINAL:PASS:callback_context=PASS:rediscovery=PASS"
        + suffix,
    )


def peripheral_lines(nonce: str = NONCE) -> tuple[str, ...]:
    """! @brief valid peripheral generic GATT protocol 순서를 반환합니다. """

    suffix = f":nonce={nonce}"
    return (
        "NUCODE_M20_READY:role=peripheral",
        "NUCODE_M20_PERIPHERAL:ADVERTISE:PASS" + suffix,
        "NUCODE_M20_EVENT:CONNECTED:round=1" + suffix,
        "NUCODE_M20_PERIPHERAL:WRITE_RESPONSE:PASS" + suffix,
        "NUCODE_M20_PERIPHERAL:WRITE_COMMAND:PASS" + suffix,
        "NUCODE_M20_PERIPHERAL:INDICATION_CONFIRMED:PASS" + suffix,
        "NUCODE_M20_EVENT:DISCONNECTED:count=1" + suffix,
        "NUCODE_M20_PERIPHERAL:READVERTISE:PASS" + suffix,
        "NUCODE_M20_EVENT:CONNECTED:round=2" + suffix,
        "NUCODE_M20_EVENT:DISCONNECTED:count=2" + suffix,
        "NUCODE_M20_PERIPHERAL:FINAL:PASS:callback_context=PASS:rediscovery=PASS"
        + suffix,
    )


class M20BleGattHilParserTest(unittest.TestCase):
    """! @brief PASS와 stale/reorder/누락/FAIL 거부 계약을 검증합니다. """

    def test_valid_pair_transcripts_pass(self) -> None:
        central = parse_central_transcript(transcript(central_lines()), NONCE)
        peripheral = parse_peripheral_transcript(
            transcript(peripheral_lines()), NONCE
        )
        self.assertEqual((1, 2), central.discovery_rounds)
        self.assertEqual("PASS", central.nonce_challenge)
        self.assertEqual("PASS", peripheral.indication_confirmation)

    def test_short_nonce_is_rejected(self) -> None:
        """! @brief full 128-bit가 아닌 runner challenge를 fail-closed로 거부합니다. """

        with self.assertRaises(BlePairHilFailure):
            parse_central_transcript(transcript(central_lines()), "0123")

    def test_stale_nonce_is_rejected(self) -> None:
        with self.assertRaises(BlePairHilFailure):
            parse_central_transcript(transcript(central_lines("a" * 32)), NONCE)

    def test_missing_rediscovery_is_rejected(self) -> None:
        lines = tuple(
            line
            for line in central_lines()
            if "DISCOVERY:PASS:round=2" not in line
        )
        with self.assertRaises(BlePairHilFailure):
            parse_central_transcript(transcript(lines), NONCE)

    def test_reordered_write_modes_are_rejected(self) -> None:
        lines = list(peripheral_lines())
        lines[3], lines[4] = lines[4], lines[3]
        with self.assertRaises(BlePairHilFailure):
            parse_peripheral_transcript(transcript(tuple(lines)), NONCE)

    def test_target_fail_is_rejected(self) -> None:
        lines = peripheral_lines()[:-1] + (
            "NUCODE_M20_FAIL:role=peripheral:reason=x",
        )
        with self.assertRaises(BlePairHilFailure):
            parse_peripheral_transcript(transcript(lines), NONCE)


if __name__ == "__main__":
    unittest.main()
