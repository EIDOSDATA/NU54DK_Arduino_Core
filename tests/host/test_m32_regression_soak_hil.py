#!/usr/bin/env python3
"""! @brief M32-W11 세 보드 유한 soak 계약을 검증합니다. """

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
APPLICATION = REPOSITORY / "tests" / "zephyr" / "m32_regression_soak_hil"
M28_SOURCE = REPOSITORY / "tests" / "zephyr" / "m28_ble_3board_hil" / "src" / "main.cpp"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
from m32_regression_soak_run import _parse_role  # noqa: E402


NONCE = "0123456789abcdef0123456789abcdef"


def _transcript(
    role: str,
    gap_ms: int = 180,
    cleanup_ms: int = 10,
    ready_replays: int = 0,
) -> bytes:
    """! @brief 한 역할의 정상 W11 soak protocol 원본을 만듭니다. """
    suffix = f":nonce={NONCE}"
    transmitted = 10000 if role in ("mixed", "central") else 0
    received = 10000 if role in ("peripheral", "mixed") else 0
    links = 2 if role == "mixed" else 1
    sequence = "sequence_per_link" if role == "mixed" else "sequence"
    ready = f"NUCODE_M28B3_READY:role={role}:test=SOAK"
    lines = [ready] * (ready_replays + 1)
    if role in ("peripheral", "mixed"):
        lines.append(
            f"NUCODE_M28B3_{role}:ADVERTISE:PASS:test=SOAK{suffix}"
        )
    lines.extend(
        (
            f"NUCODE_M28B3_{role}:TRACE:PASS:test=SOAK:source=rf-gatt"
            f":tx={transmitted}:rx={received}{suffix}",
            f"NUCODE_M28B3_{role}:SOAK:PASS:duration_s=1800:links={links}"
            f":{sequence}=10000:loss=0:corrupt=0:duplicate=0"
            ":unexpected_disconnect=0:recovery_failures=0:drops=0"
            f":max_gap_ms={gap_ms}:cleanup_ms={cleanup_ms}:cleanup=pass{suffix}",
            f"NUCODE_M28B3_{role}:FINAL:PASS:test=SOAK{suffix}",
        )
    )
    return ("boot noise\r\n" + "\r\n".join(lines) + "\r\n").encode("ascii")


class M32RegressionSoakHilTests(unittest.TestCase):
    """! @brief 분모·상한·V2 안전 경계를 고정합니다. """

    def test_all_three_roles_require_exact_denominators(self) -> None:
        for role in ("peripheral", "mixed", "central"):
            with self.subTest(role=role):
                gap = 0 if role == "central" else 180
                result = _parse_role(_transcript(role, gap), NONCE, role)
                self.assertEqual(role, result["role"])
                self.assertEqual(0, result["loss"])
                self.assertEqual("pass", result["cleanup"])

    def test_gap_cleanup_and_packet_changes_are_rejected(self) -> None:
        invalid = (
            _transcript("mixed", 501),
            _transcript("mixed", 180, 30001),
            _transcript("mixed").replace(b"sequence_per_link=10000", b"sequence_per_link=9999"),
            _transcript("mixed").replace(b"corrupt=0", b"corrupt=1"),
        )
        for payload in invalid:
            with self.subTest(payload=payload[-180:]), self.assertRaises(
                BlePairHilFailure
            ):
                _parse_role(payload, NONCE, "mixed")

    def test_pre_start_ready_replay_is_bounded_and_post_start_reset_is_rejected(self) -> None:
        """! @brief START 전 동일 READY만 허용하고 실행 중 reset은 거부합니다. """
        result = _parse_role(
            _transcript("peripheral", ready_replays=1), NONCE, "peripheral"
        )
        self.assertEqual(10000, result["received"])
        ready = b"NUCODE_M28B3_READY:role=peripheral:test=SOAK"
        advertising = (
            b"NUCODE_M28B3_peripheral:ADVERTISE:PASS:test=SOAK:nonce="
            + NONCE.encode("ascii")
        )
        reset_during_test = _transcript("peripheral").replace(
            advertising, advertising + b"\r\n" + ready
        )
        with self.assertRaises(BlePairHilFailure):
            _parse_role(reset_during_test, NONCE, "peripheral")

    def test_target_uses_bounded_gap_and_cleanup(self) -> None:
        source = M28_SOURCE.read_text(encoding="utf-8")
        cmake = (APPLICATION / "CMakeLists.txt").read_text(encoding="utf-8")
        cases = (APPLICATION / "testcase.yaml").read_text(encoding="utf-8")
        for value in (
            "constexpr std::int64_t soak_gap_limit_ms = 500;",
            "constexpr std::int64_t cleanup_timeout_ms = 30000;",
            'fail("soak-service-gap")',
            'fail("soak-bounded-recovery")',
            'Serial.print(":max_gap_ms=")',
            'Serial.print(":cleanup=pass")',
        ):
            self.assertIn(value, source)
        self.assertIn("NUCODE_M32_W11_SOAK=1", cmake)
        self.assertIn("NUCODE_M28_B3_TEST_SOAK=1", cmake)
        self.assertEqual(3, cases.count("  nucode.m32.regression_soak_hil."))

    def test_runner_is_v2_only_sector_flash_with_access_preserving_reset(self) -> None:
        """! @brief nRF54L 접근 보호를 보존하는 reset 계약을 고정합니다. """

        runner = (HIL / "m32_regression_soak_run.py").read_text(encoding="utf-8")
        shared = (HIL / "m28_ble_3board.py").read_text(encoding="utf-8")
        for value in (
            '"cmsis_dap": "v2-only"',
            '"auto_unlock": False',
            '"erase": "sector"',
            '"reset": "software"',
            "hardware_reset=True",
            "preserve_nrf54l_access=True",
            "ready_replay_settle_seconds=0.25",
            'TEST_ID = "M32-SOAK-01:primary"',
        ):
            self.assertIn(value, runner)
        self.assertIn("cmsis_dap_v1=False", shared)
        self.assertNotIn("cmsis_dap_v1=True", runner)


if __name__ == "__main__":
    unittest.main()
