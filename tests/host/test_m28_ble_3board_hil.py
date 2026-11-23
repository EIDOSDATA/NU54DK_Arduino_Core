#!/usr/bin/env python3
"""! @brief M28 세 보드 fixed protocol parser와 runner 경계를 검증합니다. """

from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


HIL_DIRECTORY = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
APPLICATION_ROOT = (
    Path(__file__).resolve().parents[1] / "zephyr" / "m28_ble_3board_hil"
)
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BlePairHilFailure,
    discover_endpoint_sha256,
    probe_sha256,
    public_endpoint,
    redact_probe_output,
)
from m28_ble_3board import (  # noqa: E402
    TEST_NAMES,
    collect_until_final,
    collect_debug_identities,
    daplink_debug_identity,
    parse_arguments,
    parse_pyocd_identity,
    parse_role_transcript,
)
from m6_serial_echo import DaplinkVolume  # noqa: E402
from ble_pair_hil_common import RoleEndpoint  # noqa: E402
import m28_ble_3board as runner  # noqa: E402


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
            result
            + ":attempt_failures=0:loss=0:corrupt=0:duplicate=0:stale=0:drops=0"
            + suffix
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

    def test_final_collector_accepts_bound_identity_suffix(self) -> None:
        """! @brief M32 compile-time identity가 READY뿐 아니라 FINAL에도 결합됩니다. """
        identity = b":source_manifest_sha256=" + b"a" * 64
        line = (
            b"NUCODE_M28B3_central:FINAL:PASS:test=SOAK"
            + identity
            + b":nonce="
            + NONCE.encode("ascii")
        )
        with mock.patch("m28_ble_3board.common.read_line", side_effect=[line]):
            collect_until_final(
                object(),
                "central",
                "SOAK",
                NONCE,
                bytearray(),
                bytearray(),
                1.0,
                threading.Event(),
                identity,
            )

    def test_all_four_tests_and_three_roles_pass(self) -> None:
        """! @brief 시작 전 동일 READY 재전송은 기존 정량 결과를 바꾸지 않습니다. """
        for test_id in TEST_NAMES:
            for role in ("peripheral", "mixed", "central"):
                lines = role_lines(test_id, role)
                expected = parse_role_transcript(transcript(lines), NONCE, test_id, role)
                for replays in (0, 1, 2):
                    with self.subTest(test_id=test_id, role=role, replays=replays):
                        result = parse_role_transcript(
                            transcript((lines[0],) * replays + lines),
                            NONCE, test_id, role,
                        )
                        self.assertEqual(expected, result)
                        self.assertEqual(test_id, result.test_id)
                        self.assertEqual(role, result.role)

    def test_missing_line_is_rejected(self) -> None:
        lines = role_lines("M28-LINK-01", "mixed")
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(lines[:2] + lines[3:]), NONCE, "M28-LINK-01", "mixed"
            )

    def test_duplicate_line_is_rejected(self) -> None:
        """! @brief 선두 READY 이후의 재등장과 결과 중복은 계속 거부합니다. """
        lines = list(role_lines("M28-SOAK-01", "peripheral"))
        lines.insert(3, lines[2])
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(tuple(lines)), NONCE, "M28-SOAK-01", "peripheral"
            )
        for role in ("peripheral", "mixed", "central"):
            valid = role_lines("M28-LINK-01", role)
            for position in range(2, len(valid) + 1):
                with self.subTest(role=role, late_ready_position=position):
                    invalid = valid[:position] + (valid[0],) + valid[position:]
                    with self.assertRaises(BlePairHilFailure):
                        parse_role_transcript(
                            transcript(invalid), NONCE, "M28-LINK-01", role
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
        """! @brief 다른 역할·시험·추가 필드의 READY를 재전송으로 인정하지 않습니다. """
        valid = role_lines("M28-CTRL-01", "central")
        unexpected = (
            "NUCODE_M28B3_central:DEBUG:PASS:nonce=" + NONCE,
            "NUCODE_M28B3_READY:role=peripheral:test=CTRL",
            "NUCODE_M28B3_READY:role=central:test=LINK",
            valid[0] + ":unexpected=1",
        )
        for token in unexpected:
            with self.subTest(token=token):
                lines = valid[:1] + (token,) + valid[1:]
                with self.assertRaises(BlePairHilFailure):
                    parse_role_transcript(
                        transcript(lines), NONCE, "M28-CTRL-01", "central"
                    )

    def test_completed_capture_survives_validation_failure(self) -> None:
        """! @brief 완료 후 이미지·파서 검사가 실패해도 세 UART 원본과 최초 예외를 보존합니다. """
        for stage in ("parser", "image_validation"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                evidence = base / "result.json"
                images = {role: base / (role + ".hex") for role in runner.ROLES}
                for role, path in images.items():
                    path.write_bytes((role + " image").encode("ascii"))
                captures = {
                    role: transcript(role_lines("M28-LINK-01", role))
                    for role in runner.ROLES
                }
                if stage == "parser":
                    captures["peripheral"] = captures["peripheral"].replace(
                        b":reconnects=20:", b":reconnects=19:"
                    )
                completed = SimpleNamespace(**{
                    role: SimpleNamespace(transcript=data)
                    for role, data in captures.items()
                })
                args = SimpleNamespace(
                    test_id="M28-LINK-01", evidence=evidence, overwrite_evidence=False,
                    discover_only=False, expected_core_revision="a" * 40,
                    flash_backend="pyocd-sector", result_timeout=None,
                    baud=115200, flash_timeout=120,
                )
                for index, role in enumerate(runner.ROLES):
                    setattr(args, "probe_" + role + "_sha256", str(index + 1) * 64)
                    setattr(args, role + "_volume", None)
                    setattr(args, role + "_port", "COM" + str(index + 1))
                    setattr(args, role + "_hex", images[role])

                def execute(**_kwargs):
                    """! @brief 장비 경계를 대체하고 필요할 때 실제 파일 변조를 주입합니다. """
                    if stage == "image_validation":
                        images["peripheral"].write_bytes(b"changed after capture")
                    return completed

                with ExitStack() as stack:
                    patches = {
                        "parse_arguments": {"return_value": args},
                        "import_pyserial": {"return_value": (object(), object())},
                        "discover_role_endpoint": {"return_value": SimpleNamespace(port_name="COM1")},
                        "validate_three_board_identity": {},
                        "collect_debug_identities": {"return_value": {}},
                        "public_endpoint": {"return_value": {"probe_sha256": "1" * 64}},
                        "validate_hex_image": {"side_effect": lambda path: path},
                        "git_revision": {"return_value": "a" * 40},
                        "validate_board_revision": {},
                        "validate_source_clean": {},
                        "validate_build_record": {"return_value": {}},
                        "build_nonce": {"return_value": NONCE},
                    }
                    for name, options in patches.items():
                        stack.enter_context(mock.patch.object(runner, name, **options))
                    run = stack.enter_context(mock.patch.object(runner, "execute_three_board", side_effect=execute))
                    save = stack.enter_context(mock.patch.object(
                        runner, "save_failure_transcripts", wraps=runner.save_failure_transcripts
                    ))
                    with self.assertRaises(BlePairHilFailure) as failure:
                        runner.main([])
                    self.assertIs(failure.exception, save.call_args.args[1])
                    run.assert_called_once()
                self.assertFalse(evidence.exists())
                for role in runner.ROLES:
                    self.assertEqual(
                        captures[role],
                        evidence.with_name(evidence.stem + "." + role + ".transcript.log").read_bytes(),
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

    def test_excessive_reconnect_attempt_failures_are_rejected(self) -> None:
        lines = tuple(
            line.replace("attempt_failures=0", "attempt_failures=4")
            for line in role_lines("M28-LINK-01", "central")
        )
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(
                transcript(lines), NONCE, "M28-LINK-01", "central"
            )

    def test_default_flash_is_uid_bound_sector_programming(self) -> None:
        args = parse_arguments(
            [
                "--test-id",
                "M28-LINK-01",
                "--probe-peripheral-sha256",
                "a" * 64,
                "--probe-mixed-sha256",
                "b" * 64,
                "--probe-central-sha256",
                "c" * 64,
            ]
        )
        self.assertEqual("pyocd-sector", args.flash_backend)

    def test_public_board_identity_and_debug_output_never_expose_raw_uid(self) -> None:
        """! @brief native evidence와 pyOCD 오류에서 raw UID를 제거합니다. """

        raw_uid = "0123456789abcdef0123456789abcdef"
        endpoint = RoleEndpoint(raw_uid, DaplinkVolume(Path("E:/"), ""), "COM7")
        public = public_endpoint(endpoint)
        self.assertNotIn(raw_uid, repr(public))
        self.assertEqual(len(public["probe_sha256"]), 64)
        redacted = redact_probe_output(
            f"probe={raw_uid.upper()} failed".encode("ascii"), raw_uid
        )
        self.assertNotIn(raw_uid, redacted.casefold())
        details = "Target Detect: nRF54L15\nUnique ID: " + raw_uid
        with mock.patch(
                "ble_pair_hil_common.read_details", return_value=details), \
                mock.patch(
                    "ble_pair_hil_common.find_serial_port",
                    side_effect=RuntimeError("uid=" + raw_uid),
                ):
            with self.assertRaises(BlePairHilFailure) as context:
                discover_endpoint_sha256(
                    probe_sha256(raw_uid), "E:/", "auto", object()
                )
        self.assertNotIn(raw_uid, str(context.exception))

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
            "constexpr std::uint32_t reconnect_attempt_failure_limit = 3U;",
            "constexpr std::int64_t reconnect_peer_ready_delay_ms = 1000;",
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
            "BLEEvent::connection_recycled",
            'ClientWriteKind::link_up, "LINK_UP"',
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
            "collect_register_identity_sha256",
            "flash_image_pyocd_sha256",
            "probe_sha256(endpoint.board_id)",
            "ready_replay_settle_seconds=0.75",
            'target not in ("nRF54L15", "unsupported target")',
        ):
            self.assertIn(value, runner)
        self.assertNotIn('"--uid"', runner)
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
