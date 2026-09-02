#!/usr/bin/env python3
"""! @brief M19 GAP 두 보드 HIL protocol parser를 host에서 검증합니다. """

from pathlib import Path
import sys
import unittest


HIL_DIRECTORY = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m19_ble_gap import (  # noqa: E402
    parse_central_transcript,
    parse_peripheral_transcript,
)


NONCE = "0123456789abcdef0123456789abcdef"


def transcript(lines: tuple[str, ...]) -> bytes:
    """! @brief synthetic UART line을 CRLF raw transcript로 만듭니다. """

    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def central_lines(nonce: str = NONCE) -> tuple[str, ...]:
    """! @brief valid central protocol 순서를 반환합니다. """

    suffix = f":nonce={nonce}"
    return (
        "NUCODE_M19_READY:role=central",
        "NUCODE_M19_CENTRAL:SCAN_FILTER:PASS" + suffix,
        "NUCODE_M19_EVENT:CONNECTED:round=1" + suffix,
        "NUCODE_M19_CENTRAL:TX_POWER:PASS" + suffix,
        "NUCODE_M19_CENTRAL:LINK_REQUESTS:PASS" + suffix,
        "NUCODE_M19_EVENT:DISCONNECTED:count=1" + suffix,
        "NUCODE_M19_CENTRAL:RECONNECT_REQUEST:PASS" + suffix,
        "NUCODE_M19_EVENT:CONNECTED:round=2" + suffix,
        "NUCODE_M19_CENTRAL:RECONNECT:PASS" + suffix,
        "NUCODE_M19_EVENT:DISCONNECTED:count=2" + suffix,
        "NUCODE_M19_CENTRAL:FINAL:PASS:callback_context=PASS:reconnect=PASS"
        + suffix,
    )


def peripheral_lines(nonce: str = NONCE) -> tuple[str, ...]:
    """! @brief valid peripheral protocol 순서를 반환합니다. """

    suffix = f":nonce={nonce}"
    return (
        "NUCODE_M19_READY:role=peripheral",
        "NUCODE_M19_PERIPHERAL:ADVERTISE:PASS" + suffix,
        "NUCODE_M19_EVENT:CONNECTED:round=1" + suffix,
        "NUCODE_M19_EVENT:DISCONNECTED:count=1" + suffix,
        "NUCODE_M19_PERIPHERAL:READVERTISE:PASS" + suffix,
        "NUCODE_M19_EVENT:CONNECTED:round=2" + suffix,
        "NUCODE_M19_PERIPHERAL:RECONNECT:PASS" + suffix,
        "NUCODE_M19_EVENT:DISCONNECTED:count=2" + suffix,
        "NUCODE_M19_PERIPHERAL:FINAL:PASS:callback_context=PASS:reconnect=PASS"
        + suffix,
    )


class M19BleGapHilParserTest(unittest.TestCase):
    """! @brief PASS와 stale/reorder/FAIL 거부 계약을 검증합니다. """

    def test_valid_pair_transcripts_pass(self) -> None:
        central = parse_central_transcript(transcript(central_lines()), NONCE)
        peripheral = parse_peripheral_transcript(
            transcript(peripheral_lines()), NONCE
        )
        self.assertEqual((1, 2), central.connection_rounds)
        self.assertEqual("PASS", peripheral.reconnect)

    def test_stale_nonce_is_rejected(self) -> None:
        stale = "f" * 32
        with self.assertRaises(BlePairHilFailure):
            parse_central_transcript(transcript(central_lines(stale)), NONCE)

    def test_short_nonce_is_rejected(self) -> None:
        """! @brief full 128-bit가 아닌 RF fixture nonce를 거부합니다. """

        with self.assertRaises(BlePairHilFailure):
            parse_central_transcript(transcript(central_lines()), "0123")

    def test_reordered_token_is_rejected(self) -> None:
        lines = list(peripheral_lines())
        lines[3], lines[4] = lines[4], lines[3]
        with self.assertRaises(BlePairHilFailure):
            parse_peripheral_transcript(transcript(tuple(lines)), NONCE)

    def test_target_fail_is_rejected(self) -> None:
        lines = central_lines()[:-1] + ("NUCODE_M19_FAIL:role=central:reason=x",)
        with self.assertRaises(BlePairHilFailure):
            parse_central_transcript(transcript(lines), NONCE)


if __name__ == "__main__":
    unittest.main()
