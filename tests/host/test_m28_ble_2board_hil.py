#!/usr/bin/env python3
"""! @brief M28 두 보드 fixed protocol parser를 Host에서 검증합니다. """

from pathlib import Path
import sys
import unittest


HIL_DIRECTORY = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
APPLICATION_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "zephyr"
    / "m28_ble_2board_hil"
    / "src"
    / "main.cpp"
)
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m28_ble_2board import parse_role_transcript  # noqa: E402


NONCE = "0123456789abcdef0123456789abcdef"


def transcript(lines: tuple[str, ...]) -> bytes:
    """! @brief synthetic UART line을 boot noise가 있는 CRLF byte로 만듭니다. """

    return ("boot noise\r\n" + "\r\n".join(lines) + "\r\n").encode("ascii")


def role_lines(role: str, nonce: str = NONCE, responses: int = 100) -> tuple[str, ...]:
    """! @brief valid role protocol 전체 순서를 반환합니다. """

    upper = role.upper()
    suffix = f":nonce={nonce}"
    lines = [f"NUCODE_M28B2_READY:role={role}"]
    if role == "peripheral":
        lines.append("NUCODE_M28B2_PERIPHERAL:ADVERTISE:PASS" + suffix)
        reports = 110
    else:
        reports = 100
    lines.extend(
        (
            f"NUCODE_M28B2_{upper}:ADV:PASS:reports={reports}:payload=255:corrupt=0:stale=0"
            + suffix,
            f"NUCODE_M28B2_{upper}:PAWR:PASS:responses={responses}:corrupt=0:out_of_window=0:subevent_mask=15:slot_mask=15:drops=0"
            + suffix,
            f"NUCODE_M28B2_{upper}:RPA:PASS:rotations=3" + suffix,
            f"NUCODE_M28B2_{upper}:PRIV:PASS:connections=21:reconnects=20:pairings=1:bond_count=1:identity_mismatch=0:stale=0"
            + suffix,
            f"NUCODE_M28B2_{upper}:FINAL:PASS:adv=PASS:pawr=PASS:privacy=PASS"
            + suffix,
        )
    )
    return tuple(lines)


class M28TwoBoardHilParserTests(unittest.TestCase):
    """! @brief 완전한 PASS만 허용하고 누락·중복·stale·오판을 거부합니다. """

    def test_valid_pair_transcripts_pass_with_boot_noise(self) -> None:
        peripheral = parse_role_transcript(
            transcript(role_lines("peripheral")), NONCE, "peripheral"
        )
        central = parse_role_transcript(
            transcript(role_lines("central", responses=105)), NONCE, "central"
        )
        self.assertEqual(255, peripheral.advertising_payload_bytes)
        self.assertEqual(20, central.reconnects)

    def test_missing_line_is_rejected(self) -> None:
        lines = role_lines("central")
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript(lines[:2] + lines[3:]), NONCE, "central")

    def test_duplicate_line_is_rejected(self) -> None:
        lines = list(role_lines("peripheral"))
        lines.insert(3, lines[2])
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript(tuple(lines)), NONCE, "peripheral")

    def test_reordered_line_is_rejected(self) -> None:
        lines = list(role_lines("central"))
        lines[2], lines[3] = lines[3], lines[2]
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript(tuple(lines)), NONCE, "central")

    def test_stale_nonce_is_rejected(self) -> None:
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(role_lines("central", "f" * 32)), NONCE, "central"
            )

    def test_wrong_revision_of_protocol_is_rejected(self) -> None:
        lines = tuple(line.replace("M28B2", "M28B3") for line in role_lines("central"))
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript(lines), NONCE, "central")

    def test_unexpected_protocol_noise_is_rejected(self) -> None:
        lines = list(role_lines("central"))
        lines.insert(1, "NUCODE_M28B2_CENTRAL:DEBUG:PASS:nonce=" + NONCE)
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript(tuple(lines)), NONCE, "central")

    def test_target_fail_is_rejected(self) -> None:
        lines = role_lines("central")[:-1] + (
            "NUCODE_M28B2_FAIL:role=central:reason=synthetic",
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript(lines), NONCE, "central")

    def test_below_99_percent_pawr_is_rejected(self) -> None:
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(role_lines("central", responses=98)), NONCE, "central"
            )

    def test_wrong_privacy_count_is_rejected(self) -> None:
        lines = tuple(
            line.replace("reconnects=20", "reconnects=19")
            for line in role_lines("peripheral")
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript(lines), NONCE, "peripheral")

    def test_changing_payload_and_rpa_scans_disable_duplicate_filter(self) -> None:
        """! @brief 데이터·RPA 변화 관측 scan이 controller 중복 제거를 끕니다. """

        source = APPLICATION_SOURCE.read_text(encoding="utf-8")
        self.assertEqual(
            2,
            source.count("BLEScan.startExtended(false, false, false)"),
        )
        self.assertIn(
            "constexpr std::int64_t advertising_update_interval_ms = 200;",
            source,
        )


if __name__ == "__main__":
    unittest.main()
