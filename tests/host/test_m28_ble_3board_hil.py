#!/usr/bin/env python3
"""! @brief M28 세 보드 fixed protocol parser와 runner 경계를 검증합니다. """

from pathlib import Path
import sys
import unittest


HIL_DIRECTORY = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
APPLICATION_ROOT = (
    Path(__file__).resolve().parents[1] / "zephyr" / "m28_ble_3board_hil"
)
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m28_ble_3board import (  # noqa: E402
    TEST_NAMES,
    collect_debug_identities,
    daplink_debug_identity,
    parse_arguments,
    parse_pyocd_identity,
    parse_role_transcript,
)
from m6_serial_echo import DaplinkVolume  # noqa: E402
from ble_pair_hil_common import RoleEndpoint  # noqa: E402


NONCE = "0123456789abcdef0123456789abcdef"


def transcript(lines: tuple[str, ...]) -> bytes:
    """! @brief synthetic protocol에 boot noise와 CRLF를 결합합니다. """

    return ("boot noise\r\n" + "\r\n".join(lines) + "\r\n").encode("ascii")


def role_lines(test_id: str, role: str, nonce: str = NONCE) -> tuple[str, ...]:
    """! @brief test·role별 valid fixed protocol 전체를 반환합니다. """

    test = TEST_NAMES[test_id]
    suffix = f":nonce={nonce}"
    lines = [f"NUCODE_M28B3_READY:role={role}:test={test}"]
    if role in ("peripheral", "mixed"):
        lines.append(
            f"NUCODE_M28B3_{role}:ADVERTISE:PASS:test={test}" + suffix
        )
    if test == "LINK":
        tx = 1000 if role in ("mixed", "central") else 0
        rx = 1000 if role in ("peripheral", "mixed") else 0
        lines.append(
            f"NUCODE_M28B3_{role}:TRACE:PASS:test=LINK:source=rf-gatt:tx={tx}:rx={rx}"
            + suffix
        )
        if role == "mixed":
            result = (
                "NUCODE_M28B3_mixed:LINK:PASS:links=2:central=1:peripheral=1"
                ":reconnects_per_link=20:sequence_per_link=1000"
            )
        else:
            result = (
                f"NUCODE_M28B3_{role}:LINK:PASS:links=1:reconnects=20"
                ":sequence=1000"
            )
        lines.append(
            result + ":loss=0:corrupt=0:duplicate=0:stale=0:drops=0" + suffix
        )
    elif test == "PER":
        if role == "peripheral":
            lines.extend(
                (
                    "NUCODE_M28B3_peripheral:PERIODIC:STARTED:sid=7" + suffix,
                    "NUCODE_M28B3_peripheral:PER:PASS:emitted=1000:corrupt=0:drops=0"
                    + suffix,
                )
            )
        elif role == "mixed":
            lines.extend(
                (
                    "NUCODE_M28B3_mixed:PERIODIC:SYNCED:sid=7" + suffix,
                    "NUCODE_M28B3_mixed:PER:PASS:past_sent=20:source_reports=1000"
                    ":corrupt=0:drops=0"
                    + suffix,
                )
            )
        else:
            lines.extend(
                (
                    "NUCODE_M28B3_central:TRACE:PASS:test=PER:source=rf-periodic"
                    ":denominator=1000:received=995:loss=5"
                    + suffix,
                    "NUCODE_M28B3_central:PER:PASS:reports=995:denominator=1000"
                    ":loss=5:corrupt=0:past=20:drops=0"
                    + suffix,
                )
            )
    elif test == "CTRL":
        if role == "mixed":
            lines.append(
                "NUCODE_M28B3_mixed:CTRL:PASS:links=2:requests_per_link=20"
                ":cross_state=0:stale=0:unreported_driver=0"
                ":unexpected_disconnect=0:drops=0"
                + suffix
            )
        else:
            lines.append(
                f"NUCODE_M28B3_{role}:CTRL:PASS:links=1:rounds=20"
                ":unexpected_disconnect=0:drops=0"
                + suffix
            )
    else:
        tx = 10000 if role in ("mixed", "central") else 0
        rx = 10000 if role in ("peripheral", "mixed") else 0
        lines.append(
            f"NUCODE_M28B3_{role}:TRACE:PASS:test=SOAK:source=rf-gatt:tx={tx}:rx={rx}"
            + suffix
        )
        if role == "mixed":
            result = (
                "NUCODE_M28B3_mixed:SOAK:PASS:duration_s=1800:links=2"
                ":sequence_per_link=10000"
            )
        else:
            result = (
                f"NUCODE_M28B3_{role}:SOAK:PASS:duration_s=1800:links=1"
                ":sequence=10000"
            )
        lines.append(
            result
            + ":loss=0:corrupt=0:duplicate=0:unexpected_disconnect=0"
            + ":recovery_failures=0:drops=0"
            + suffix
        )
    lines.append(f"NUCODE_M28B3_{role}:FINAL:PASS:test={test}" + suffix)
    return tuple(lines)


class M28ThreeBoardHilParserTests(unittest.TestCase):
    """! @brief 완전한 세 role PASS만 허용하고 protocol 오판을 거부합니다. """

    def test_all_four_tests_and_three_roles_pass(self) -> None:
        for test_id in TEST_NAMES:
            for role in ("peripheral", "mixed", "central"):
                with self.subTest(test_id=test_id, role=role):
                    result = parse_role_transcript(
                        transcript(role_lines(test_id, role)), NONCE, test_id, role
                    )
                    self.assertEqual(test_id, result.test_id)
                    self.assertEqual(role, result.role)

    def test_missing_line_is_rejected(self) -> None:
        lines = role_lines("M28-LINK-01", "mixed")
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(lines[:2] + lines[3:]), NONCE, "M28-LINK-01", "mixed"
            )

    def test_duplicate_line_is_rejected(self) -> None:
        lines = list(role_lines("M28-SOAK-01", "peripheral"))
        lines.insert(3, lines[2])
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(tuple(lines)), NONCE, "M28-SOAK-01", "peripheral"
            )

    def test_reordered_line_is_rejected(self) -> None:
        lines = list(role_lines("M28-PER-01", "central"))
        lines[1], lines[2] = lines[2], lines[1]
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(tuple(lines)), NONCE, "M28-PER-01", "central"
            )

    def test_stale_nonce_is_rejected(self) -> None:
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(role_lines("M28-CTRL-01", "mixed", "f" * 32)),
                NONCE,
                "M28-CTRL-01",
                "mixed",
            )

    def test_wrong_protocol_revision_is_rejected(self) -> None:
        lines = tuple(
            line.replace("M28B3", "M28B2")
            for line in role_lines("M28-LINK-01", "central")
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(lines), NONCE, "M28-LINK-01", "central"
            )

    def test_unexpected_protocol_noise_is_rejected(self) -> None:
        lines = list(role_lines("M28-CTRL-01", "central"))
        lines.insert(1, "NUCODE_M28B3_central:DEBUG:PASS:nonce=" + NONCE)
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(tuple(lines)), NONCE, "M28-CTRL-01", "central"
            )

    def test_target_fail_is_rejected(self) -> None:
        lines = role_lines("M28-SOAK-01", "mixed")[:-1] + (
            "NUCODE_M28B3_FAIL:role=mixed:test=SOAK:reason=synthetic:nonce="
            + NONCE,
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(lines), NONCE, "M28-SOAK-01", "mixed"
            )

    def test_below_99_percent_periodic_is_rejected(self) -> None:
        lines = tuple(
            line.replace("received=995:loss=5", "received=989:loss=11").replace(
                "reports=995:denominator=1000:loss=5",
                "reports=989:denominator=1000:loss=11",
            )
            for line in role_lines("M28-PER-01", "central")
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(lines), NONCE, "M28-PER-01", "central"
            )

    def test_wrong_reconnect_count_is_rejected(self) -> None:
        lines = tuple(
            line.replace("reconnects_per_link=20", "reconnects_per_link=19")
            for line in role_lines("M28-LINK-01", "mixed")
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(lines), NONCE, "M28-LINK-01", "mixed"
            )

    def test_default_flash_is_uid_bound_sector_programming(self) -> None:
        args = parse_arguments(
            [
                "--test-id",
                "M28-LINK-01",
                "--peripheral-board-id",
                "a" * 32,
                "--mixed-board-id",
                "b" * 32,
                "--central-board-id",
                "c" * 32,
            ]
        )
        self.assertEqual("pyocd-sector", args.flash_backend)

    def test_pyocd_identity_requires_nrf54l_aps_and_unlocked_device(self) -> None:
        output = "\n".join(
            (
                "DP register 0x24 = 0x201c0289",
                "AP register 0xfc = 0x84770001",
                "AP register 0x0 = 0x43000052",
                "AP register 0x20000fc = 0x32880000",
                "AP register 0x2000014 = 0x00000000",
            )
        )
        identity = parse_pyocd_identity(output)
        self.assertEqual("0x201c0289", identity["target_id"])
        for old, new in (
            ("0x201c0289", "0x201c0288"),
            ("0x43000052", "0x43000012"),
            ("0x00000000", "0x00000003"),
        ):
            with self.subTest(new=new), self.assertRaises(BlePairHilFailure):
                parse_pyocd_identity(output.replace(old, new))

    def test_daplink_identity_requires_target_idcode_and_voltage(self) -> None:
        details = "\n".join(
            (
                "Target Detect: nRF54L15",
                "SWD DP IDCODE: 0x6ba02477",
                "Target Voltage: 3295 mV (present)",
            )
        )
        endpoint = RoleEndpoint("a" * 32, DaplinkVolume(Path("E:/"), details), "COM13")
        identity = daplink_debug_identity(endpoint)
        self.assertEqual("daplink-details", identity["source"])
        identities = collect_debug_identities({"mixed": endpoint}, "daplink-msd")
        self.assertEqual("0x6ba02477", identities["mixed"]["swd_dp_idcode"])
        for old, new in (
            ("nRF54L15", "unsupported target"),
            ("0x6ba02477", "0x00000000"),
            ("3295 mV (present)", "0 mV (absent)"),
        ):
            with self.subTest(new=new), self.assertRaises(BlePairHilFailure):
                daplink_debug_identity(
                    RoleEndpoint(
                        "a" * 32,
                        DaplinkVolume(Path("E:/"), details.replace(old, new)),
                        "COM13",
                    )
                )

    def test_target_contract_contains_all_fixed_boundaries(self) -> None:
        source = (APPLICATION_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        config = (APPLICATION_ROOT / "prj.conf").read_text(encoding="utf-8")
        cases = (APPLICATION_ROOT / "testcase.yaml").read_text(encoding="utf-8")
        for value in (
            "constexpr std::uint32_t link_sequence_target = 1000U;",
            "constexpr std::uint32_t reconnect_target = 20U;",
            "constexpr std::uint32_t past_target = 20U;",
            "constexpr std::uint32_t periodic_sequence_target = 1000U;",
            "constexpr std::uint16_t periodic_interval_min = 80U;",
            "constexpr std::uint16_t periodic_interval_max = 96U;",
            "constexpr std::int64_t periodic_update_interval_ms = 250;",
            "constexpr std::uint32_t control_round_target = 20U;",
            "constexpr std::uint32_t soak_sequence_target = 10000U;",
            "constexpr std::int64_t soak_duration_ms = 1800000;",
            "BLEConnection.count() == 2U",
            "BLEConnection.requestMtu(outgoing_link)",
            "BLEConnection.mtu(outgoing_link) >= 31U",
            "BLEConnection.requestPhy(outgoing_link",
            "periodic.interval_min = periodic_interval_min;",
            "periodic.interval_max = periodic_interval_max;",
            "periodic.include_tx_power = false;",
            "BLEPeriodicAdvertising.transferSync(periodic_sync, incoming_link",
            "BLEDevice.end();",
        ):
            self.assertIn(value, source)
        self.assertLess(
            source.index("phase = Phase::reconnect_incoming;"),
            source.index('if (!notifyServer("LINK_CYCLE"))'),
        )
        runner = (HIL_DIRECTORY / "m28_ble_3board.py").read_text(encoding="utf-8")
        for value in (
            '"readdp 0x24"',
            '"readap 0 0xfc"',
            '"readap 2 0x14"',
            '"-I"',
            'target not in ("nRF54L15", "unsupported target")',
        ):
            self.assertIn(value, runner)
        for value in (
            "CONFIG_BT_MAX_CONN=2",
            "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1",
            "CONFIG_BT_L2CAP_TX_MTU=64",
            "CONFIG_BT_BUF_ACL_TX_SIZE=68",
            "CONFIG_BT_BUF_ACL_RX_SIZE=68",
            "CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER=y",
            "CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER=y",
            "CONFIG_BT_USER_PHY_UPDATE=y",
            "CONFIG_BT_USER_DATA_LEN_UPDATE=y",
        ):
            self.assertIn(value, config)
        self.assertEqual(12, cases.count("  nucode.m28.b3."))


if __name__ == "__main__":
    unittest.main()
