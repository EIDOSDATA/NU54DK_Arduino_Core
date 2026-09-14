"""! @brief M30-PAIR-01 target와 strict runner 계약을 검증합니다. """
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL_DIRECTORY = ROOT / "tests/hil/nu54dk"
RUNNER_PATH = HIL_DIRECTORY / "m30_ble_pair.py"
TARGET_PATH = ROOT / "tests/zephyr/m30_ble_pair_hil/src/main.cpp"
TESTCASE_PATH = ROOT / "tests/zephyr/m30_ble_pair_hil/testcase.yaml"
MATRIX_PATH = ROOT / "tools/ci/run_zephyr_build.py"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))
SPEC = spec_from_file_location("nu54_m30_ble_pair", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
PAIR = module_from_spec(SPEC)
sys.modules[SPEC.name] = PAIR
SPEC.loader.exec_module(PAIR)


class M30BlePairTests(unittest.TestCase):
    """! @brief IO 조합·50회·passkey redaction·exact link 판정을 고정합니다. """

    def test_five_capability_cases_cover_all_io_values(self) -> None:
        """! @brief 5종 IO capability가 role 조합에 적어도 한 번씩 등장합니다. """

        self.assertEqual(len(PAIR.CASES), 5)
        values = {
            value
            for case in PAIR.CASES
            for value in (case.peripheral_io, case.central_io)
        }
        self.assertEqual(values, set(range(5)))
        self.assertEqual(PAIR.ROUNDS_PER_CAPABILITY, 10)

    def test_target_uses_sc_l4_exact_handle_and_runtime_key_size(self) -> None:
        """! @brief 합성 PASS 대신 실제 generation·L4·암호화 key 길이를 검사합니다. """

        source = TARGET_PATH.read_text(encoding="utf-8")
        for token in (
            "SecurityLevel::secure_connections",
            "BLESecurity.requestSecurity(connection_handle)",
            "BLESecurity.acceptPairing(event.connection, true)",
            "BLESecurity.confirmPasskey(event.connection, true)",
            "BLESecurity.enterPasskey(connection_handle",
            "bt_conn_enc_key_size(connection)",
            "event.connection != connection_handle",
            "unexpected_auth_failures",
        ):
            self.assertIn(token, source, token)

    def test_passkey_is_redacted_before_evidence_capture(self) -> None:
        """! @brief 표시 passkey 6자리는 transcript byte에 기록되지 않습니다. """

        capture = bytearray()
        PAIR.capture_sanitized(
            capture,
            b"M30PAIR|1|DISPLAY|role=peripheral|case=display_keyboard|"
            b"round=1|nonce=0123456789abcdef0123456789abcdef|value=123456",
        )
        self.assertNotIn(b"value=123456", capture)
        self.assertIn(b"value=<redacted>", capture)

    def test_pass_record_parser_rejects_duplicate_fields(self) -> None:
        """! @brief field 순서를 빌미로 중복 key를 덮어쓰지 못합니다. """

        valid = (
            b"M30PAIR|1|PASS|role=central|case=no_input_output|round=1|"
            b"method=just_works|level=4|key_size=16|paired=1|"
            b"unexpected_auth_failures=0|nonce=0123456789abcdef0123456789abcdef"
        )
        self.assertEqual(PAIR.parse_fields(valid, "PASS")["key_size"], "16")
        with self.assertRaises(PAIR.M30PairFailure):
            PAIR.parse_fields(valid + b"|level=3", "PASS")

    def test_ten_role_images_are_in_target_and_canonical_matrix(self) -> None:
        """! @brief 다섯 조합의 양쪽 image가 Twister와 v0.5.0 gate에 모두 포함됩니다. """

        testcase = TESTCASE_PATH.read_text(encoding="utf-8")
        matrix = MATRIX_PATH.read_text(encoding="utf-8")
        for case in PAIR.CASES:
            for role in ("peripheral", "central"):
                scenario = PAIR.scenario_name(case, role)
                self.assertIn(scenario, testcase)
                self.assertIn(scenario, matrix)

    def test_runner_is_uid_bound_sector_flash_and_power_cut_free(self) -> None:
        """! @brief W02 flash는 exact UID sector 방식이며 실제 전원 차단을 수행하지 않습니다. """

        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("flash_image_pyocd", source)
        self.assertIn("serial_module, list_ports = import_pyserial()", source)
        self.assertNotIn("serial_module.tools.list_ports", source)
        self.assertIn("board_revision = git_revision(BOARD_ROOT)", source)
        self.assertIn("validate_board_revision(board_revision)", source)
        self.assertIn('"power_cut_injected": False', source)
        self.assertIn('"mass_erase_or_recover": False', source)
        self.assertIn("30.0 <= args.result_timeout <= 600.0", source)


if __name__ == "__main__":
    unittest.main()
