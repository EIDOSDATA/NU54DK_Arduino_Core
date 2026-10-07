"""! @brief M30-W07 3보드 동시 보안 link target·runner 계약을 검증합니다. """

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from m30_ble_multi_protocol import (  # noqa: E402
    CYCLE_COUNT,
    MultiSecurityProtocolFailure,
    expected_campaign_lines,
    expected_lines,
    parse_role_campaign,
    parse_role_transcript,
    validate_three_role_session,
)


TARGET_ROOT = ROOT / "tests/zephyr/m30_ble_multi_hil"
TARGET = TARGET_ROOT / "src/main.cpp"
CONFIG = TARGET_ROOT / "prj.conf"
CASES = TARGET_ROOT / "testcase.yaml"
RUNNER_PATH = HIL / "m30_ble_multi.py"
MATRIX = ROOT / "tools/ci/run_zephyr_build.py"
NONCE = "00112233445566778899aabbccddeeff"
REVISION = "0123456789abcdef0123456789abcdef01234567"
NONCES = tuple(f"{index:032x}" for index in range(CYCLE_COUNT))


def _load_runner():
    """! @brief runner를 테스트 전용 이름으로 import합니다. """

    specification = importlib.util.spec_from_file_location(
        "m30_ble_multi_test_module", RUNNER_PATH
    )
    if specification is None or specification.loader is None:
        raise AssertionError("M30 multi runner를 import할 수 없습니다.")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


RUNNER = _load_runner()


def _transcript(role: str) -> bytes:
    """! @brief canonical role transcript를 만듭니다. """

    return ("\r\n".join(expected_lines(role, NONCE, REVISION)) + "\r\n").encode(
        "ascii"
    )


class M30BleMultiTests(unittest.TestCase):
    """! @brief 2-link 자원·generation 격리·strict parser를 고정합니다. """

    def test_target_has_two_link_security_operation_contract(self) -> None:
        target = TARGET.read_text(encoding="utf-8")
        config = CONFIG.read_text(encoding="utf-8")
        for token in (
            "CONFIG_BT_MAX_CONN == 2",
            "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1",
            "BLEConnectionHandle client_connection",
            "BLEConnectionHandle server_connection",
            "required_operations = 100U",
            "requestSecurity(handle)",
            "currentLevel(handle)",
            "encryptionKeySize(handle)",
            "cross_link_events",
            'fail("cross_link_security_event")',
            'Serial.print("|cross_link=0|security_errors=0|key_size_errors=0")',
            'stop_prefix[] = "M30W07|1|STOP|nonce="',
            "driveCleanup()",
            'Serial.print("|active_links=0|pending_operations=0|buffers=0|status=pass")',
            "resetSessionState()",
        ):
            self.assertIn(token, target)
        for token in (
            "CONFIG_BT_MAX_CONN=2",
            "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1",
            "CONFIG_BT_SMP_SC_PAIR_ONLY=y",
            "CONFIG_BT_SMP_MIN_ENC_KEY_SIZE=16",
        ):
            self.assertIn(token, config)

    def test_three_role_builds_are_canonical(self) -> None:
        cases = CASES.read_text(encoding="utf-8")
        matrix = MATRIX.read_text(encoding="utf-8")
        for role in ("peripheral", "mixed", "central"):
            scenario = f"nucode.m30.multi.{role}"
            self.assertIn(scenario, cases)
            self.assertIn(f"M30_MULTI_ROLE={role}", cases)
            self.assertIn(f'("m30_ble_multi_hil", "{scenario}")', matrix)

    def test_runner_requires_three_distinct_devices_and_exact_images(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        for token in (
            "validate_three_board_identity",
            "validate_source_clean",
            "validate_build_record",
            "validate_image_unchanged",
            "ThreadPoolExecutor(max_workers=3)",
            "probe_sha256",
            '"security_operations_per_link": 100',
            '"power_cut_executed": False',
            "CYCLE_COUNT",
            "serial_closed",
            "discover_endpoint_sha256",
        ):
            self.assertIn(token, source)
        self.assertNotIn('"daplink_uid"', source)
        self.assertNotIn("--peripheral-board-id", source)

    def test_twenty_session_campaign_requires_unique_nonce_and_cleanup(self) -> None:
        """! @brief 20회 campaign 분모와 각 cycle zero cleanup을 고정합니다. """

        raw = (
            "\r\n".join(expected_campaign_lines("mixed", NONCES, REVISION))
            + "\r\n"
        ).encode("ascii")
        results = parse_role_campaign(raw, "mixed", NONCES, REVISION)
        self.assertEqual(len(results), CYCLE_COUNT)
        self.assertTrue(all(result.cleanup_active_links == 0 for result in results))
        with self.assertRaises(MultiSecurityProtocolFailure):
            expected_campaign_lines("mixed", (NONCES[0],) * CYCLE_COUNT, REVISION)
        lines = expected_campaign_lines("mixed", NONCES, REVISION)
        cleanup = next(index for index, line in enumerate(lines) if "|CLEANUP|" in line)
        without_cleanup = (
            "\n".join(lines[:cleanup] + lines[cleanup + 1 :]) + "\n"
        ).encode("ascii")
        with self.assertRaises(MultiSecurityProtocolFailure):
            parse_role_campaign(without_cleanup, "mixed", NONCES, REVISION)

    def test_canonical_transcripts_pass(self) -> None:
        results = {
            role: parse_role_transcript(_transcript(role), role, NONCE, REVISION)
            for role in ("peripheral", "mixed", "central")
        }
        validate_three_role_session(results)
        self.assertEqual(results["mixed"].client_operations, 100)
        self.assertEqual(results["mixed"].server_operations, 100)

    def test_parser_rejects_noise_stale_identity_and_cross_link_value(self) -> None:
        canonical = _transcript("mixed")
        mutations = (
            b"noise\n" + canonical,
            canonical.replace(NONCE.encode("ascii"), b"f" * 32, 1),
            canonical.replace(b"cross_link=0", b"cross_link=1"),
            canonical.replace(b"operations_per_link=100", b"operations_per_link=99", 1),
            canonical + b"M30W07|1|EXTRA\n",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[-80:]):
                with self.assertRaises(MultiSecurityProtocolFailure):
                    parse_role_transcript(mutation, "mixed", NONCE, REVISION)

    def test_parser_rejects_missing_role(self) -> None:
        results = {
            role: parse_role_transcript(_transcript(role), role, NONCE, REVISION)
            for role in ("peripheral", "mixed")
        }
        with self.assertRaises(MultiSecurityProtocolFailure):
            validate_three_role_session(results)

    def test_discovery_arguments_require_only_hashed_probe_identity(self) -> None:
        raw_uid = "00112233445566778899aabbccddeeff"
        digest = hashlib.sha256(raw_uid.encode("ascii")).hexdigest()
        arguments = [
            value
            for role in ("peripheral", "mixed", "central")
            for value in (f"--probe-{role}-sha256", digest)
        ]
        parsed = RUNNER.parse_arguments(arguments)
        self.assertEqual(parsed.probe_peripheral_sha256, digest)
        endpoint = RUNNER.RoleEndpoint(
            raw_uid,
            RUNNER.common.DaplinkVolume(
                Path("E:/"),
                "Target Detect: nRF54L15\nUnique ID: " + raw_uid,
            ),
            "COM13",
        )
        serialized_argv = json.dumps(vars(parsed), sort_keys=True).encode("utf-8")
        serialized_native = json.dumps(
            {"boards": {"peripheral": RUNNER._board(endpoint)}},
            sort_keys=True,
        ).encode("utf-8")
        self.assertNotIn(raw_uid.encode("ascii"), serialized_argv)
        self.assertNotIn(raw_uid.encode("ascii"), serialized_native)
        self.assertIn(digest.encode("ascii"), serialized_argv)
        self.assertIn(digest.encode("ascii"), serialized_native)
        with self.assertRaises(SystemExit):
            RUNNER.parse_arguments(["--peripheral-board-id", "raw-secret"])


if __name__ == "__main__":
    unittest.main()
