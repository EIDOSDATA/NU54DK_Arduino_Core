#!/usr/bin/env python3
"""! @brief M28 두 보드 fixed protocol parser를 Host에서 검증합니다. """

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HIL_DIRECTORY = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
APPLICATION_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "zephyr"
    / "m28_ble_2board_hil"
    / "src"
    / "main.cpp"
)
APPLICATION_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "zephyr"
    / "m28_ble_2board_hil"
    / "prj.conf"
)
PAIR_RUNNER_COMMON = HIL_DIRECTORY / "ble_pair_hil_common.py"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
import ble_pair_hil_common  # noqa: E402
from m28_ble_2board import parse_arguments, parse_role_transcript  # noqa: E402


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
            transcript(role_lines("central")), NONCE, "central"
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

    def test_pawr_controller_dependencies_are_enabled(self) -> None:
        """! @brief PAwR controller 기능이 PAST 누락으로 꺼지는 회귀를 막습니다. """

        config = APPLICATION_CONFIG.read_text(encoding="utf-8").splitlines()
        required = {
            "CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER=y",
            "CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER=y",
            "CONFIG_BT_CTLR_SDC_PAWR_ADV=y",
            "CONFIG_BT_CTLR_SDC_PAWR_SYNC=y",
            "CONFIG_BT_CTLR_TX_PWR_PLUS_8=y",
        }
        self.assertTrue(required.issubset(set(config)))

        source = APPLICATION_SOURCE.read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_CTLR_SYNC_TRANSFER_RECEIVER", source)
        self.assertIn("CONFIG_BT_CTLR_SYNC_TRANSFER_SENDER", source)
        self.assertIn("CONFIG_BT_CTLR_SDC_PAWR_ADV", source)
        self.assertIn("CONFIG_BT_CTLR_SDC_PAWR_SYNC", source)
        self.assertIn("constexpr std::uint32_t required_pawr_responses = 100U;", source)
        self.assertIn("pawr_response_count < 99U", source)
        self.assertIn("pawr_discovery_timeout_ms = 60000", source)
        self.assertIn("pawr_response_window_ms = 35000", source)
        self.assertIn("privacy_scan_prepare_ms = 5000", source)
        self.assertIn(
            "pawr_phase_deadline_ms = k_uptime_get() + pawr_response_window_ms;",
            source,
        )
        self.assertIn("std::uint8_t response[23] = {};", source)
        self.assertIn("response_subevent = report.subevent;", source)
        self.assertIn('Serial.print("M28_PAWR_DIAG:received=");', source)
        self.assertIn("pawr_subevent_counts[response.subevent]", source)
        self.assertIn("pawr_slot_counts[response.response_slot]", source)
        self.assertIn("first_pawr_response_event =", source)
        self.assertIn('fail("pawr-response-sequence");', source)
        self.assertIn("phase = Phase::privacy_wait;", source)
        self.assertIn("privacy_rotation_start_pending = true;", source)
        self.assertLess(
            source.index("BLEPrivacy.setRotationTimeout(1U)"),
            source.index("startAdvertisingPhase();", source.index("void startProtocol()")),
        )
        prepare = source.index("void preparePrivateConnectionAdvertising()")
        self.assertLess(
            source.index("BLEPrivacy.setRotationTimeout(60U)", prepare),
            source.index("phase = Phase::privacy_settle", prepare),
        )
        self.assertIn("privacy_rpa_restart_pending = true;", source)
        self.assertIn("fail(\"privacy-rpa-rotate\");", source)
        restart = source.index(
            "if (privacy_rpa_restart_pending && now >= privacy_rpa_restart_ms)"
        )
        self.assertLess(
            source.index("BLEExtendedAdvertising.stop(advertising_set)", restart),
            source.index("BLEExtendedAdvertising.start(advertising_set)", restart),
        )

    def test_pyocd_sector_flash_is_uid_bound(self) -> None:
        """! @brief M28 기본 flash가 exact UID와 sector erase만 사용합니다. """

        result = SimpleNamespace(
            returncode=0,
            stdout=b"programmed 12288 bytes",
            stderr=b"",
        )
        with patch.object(ble_pair_hil_common.subprocess, "run", return_value=result) as run:
            sequence, byte_count = ble_pair_hil_common.flash_image_pyocd(
                "peripheral", "a" * 32, Path("image.hex"), 45.0
            )
        command = run.call_args.args[0]
        self.assertEqual("a" * 32, command[command.index("--uid") + 1])
        self.assertEqual("500000", command[command.index("--frequency") + 1])
        self.assertIn("cmsis_dap.limit_packets=true", command)
        self.assertIn("auto_unlock=false", command)
        self.assertEqual("sector", command[command.index("--erase") + 1])
        self.assertNotIn("chip", command)
        self.assertEqual("pyocd-sector", sequence)
        self.assertEqual("12288", byte_count)

        arguments = parse_arguments(
            ["--peripheral-board-id", "a" * 32, "--central-board-id", "b" * 32]
        )
        self.assertEqual("pyocd-sector", arguments.flash_backend)

    def test_each_role_discards_only_pre_flash_uart_bytes(self) -> None:
        """! @brief 각 image 기록 직전의 이전 실행 UART만 폐기합니다. """

        source = PAIR_RUNNER_COMMON.read_text(encoding="utf-8")
        pyocd_branch = source.index('if flash_backend == "pyocd-sector":')
        msd_branch = source.index("else:", pyocd_branch)
        wait_ready = source.index("deadline = time.monotonic()", msd_branch)
        for branch_start, branch_end in (
            (pyocd_branch, msd_branch),
            (msd_branch, wait_ready),
        ):
            branch = source[branch_start:branch_end]
            peripheral_reset = branch.index(
                'ports["peripheral"].reset_input_buffer()'
            )
            peripheral_flash = branch.index('flashes["peripheral"] =')
            central_reset = branch.index('ports["central"].reset_input_buffer()')
            central_flash = branch.index('flashes["central"] =')
            self.assertLess(peripheral_reset, peripheral_flash)
            self.assertLess(peripheral_flash, central_reset)
            self.assertLess(central_reset, central_flash)


if __name__ == "__main__":
    unittest.main()
