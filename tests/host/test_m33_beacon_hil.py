#!/usr/bin/env python3
"""M33 Beacon HIL의 bounded record와 고정 분모를 검증합니다."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))
SPEC = importlib.util.spec_from_file_location(
    "m33_beacon_run", HIL / "m33_beacon_run.py"
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def passing_results() -> dict[str, dict[str, str]]:
    """고정 분모를 만족하는 합성 target 결과를 반환합니다."""
    return {
        "advertiser": {
            "switches": "90",
            "ibeacon_sequences": "30",
            "eddystone_sequences": "30",
            "bthome_sequences": "30",
            "codec_negative": "pass",
        },
        "observer": {
            "raw": "600",
            "ibeacon_raw": "200",
            "eddystone_raw": "200",
            "bthome_raw": "200",
            "ibeacon_unique": "30",
            "eddystone_unique": "30",
            "bthome_unique": "30",
            "semantic_errors": "0",
            "callback_context": "pass",
            "codec_negative": "pass",
        },
    }


def stopped_record(role: str = "advertiser") -> str:
    """정상 자원 해제 상태의 STOPPED record를 반환합니다."""
    return (
        f"M33BEACON|1|STOPPED|role={role}|nonce={'a' * 32}|core={'b' * 40}"
        "|advertising=0|scan=0|device=0"
    )


class BeaconHilContractTest(unittest.TestCase):
    """HIL Host oracle가 누락·중복·분모 축소를 거부하는지 검사합니다."""

    def test_result_record_parser(self) -> None:
        fields = RUNNER._fields(
            "M33BEACON|1|RESULT|role=observer|raw=600|codec_negative=pass"
        )
        self.assertEqual(fields["role"], "observer")
        self.assertEqual(fields["raw"], "600")

    def test_duplicate_field_is_rejected(self) -> None:
        with self.assertRaises(RUNNER.BeaconExecutionFailure):
            RUNNER._fields("M33BEACON|1|RESULT|raw=600|raw=601")

    def test_accepts_fixed_denominator(self) -> None:
        RUNNER._validate_results(passing_results())

    def test_rejects_packet_denominator_reduction(self) -> None:
        results = passing_results()
        results["observer"]["raw"] = "599"
        with self.assertRaises(RUNNER.BeaconExecutionFailure):
            RUNNER._validate_results(results)

    def test_rejects_missing_format_coverage(self) -> None:
        results = passing_results()
        results["observer"]["ibeacon_raw"] = "149"
        with self.assertRaises(RUNNER.BeaconExecutionFailure):
            RUNNER._validate_results(results)

    def test_rejects_semantic_corruption(self) -> None:
        results = passing_results()
        results["observer"]["semantic_errors"] = "1"
        with self.assertRaises(RUNNER.BeaconExecutionFailure):
            RUNNER._validate_results(results)

    def test_accepts_single_clean_stop_record(self) -> None:
        self.assertTrue(
            RUNNER._validate_stop_record(
                "advertiser", stopped_record(), "a" * 32, "b" * 40, False
            )
        )

    def test_rejects_late_target_fail(self) -> None:
        line = (
            "M33BEACON|1|FAIL|role=advertiser|stage=cleanup_advertising_stop"
            f"|code=-5|nonce={'a' * 32}|core={'b' * 40}"
            "|advertising=0|scan=0|device=0"
        )
        with self.assertRaisesRegex(
            RUNNER.BeaconExecutionFailure, "target FAIL after STOP"
        ):
            RUNNER._validate_stop_record(
                "advertiser", line, "a" * 32, "b" * 40, True
            )

    def test_rejects_stop_cleanup_resource_failure(self) -> None:
        for resource in ("advertising", "scan", "device"):
            with self.subTest(resource=resource):
                line = stopped_record().replace(f"{resource}=0", f"{resource}=1")
                with self.assertRaisesRegex(
                    RUNNER.BeaconExecutionFailure, "cleanup resource mismatch"
                ):
                    RUNNER._validate_stop_record(
                        "advertiser", line, "a" * 32, "b" * 40, False
                    )

    def test_rejects_duplicate_and_unexpected_stop_records(self) -> None:
        line = stopped_record()
        with self.assertRaisesRegex(
            RUNNER.BeaconExecutionFailure, "duplicate STOPPED"
        ):
            RUNNER._validate_stop_record(
                "advertiser", line, "a" * 32, "b" * 40, True
            )
        unexpected = (
            f"M33BEACON|1|RESULT|role=advertiser|nonce={'a' * 32}"
            f"|core={'b' * 40}"
        )
        with self.assertRaisesRegex(
            RUNNER.BeaconExecutionFailure, "unexpected record after STOP"
        ):
            RUNNER._validate_stop_record(
                "advertiser", unexpected, "a" * 32, "b" * 40, False
            )

    def test_target_stop_path_checks_driver_and_resource_state(self) -> None:
        source = (
            REPOSITORY / "tests" / "zephyr" / "m33_ble_beacon_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        stop_path = source.split("void stopProtocol()", 1)[1].split(
            "/** @brief CR/LF", 1
        )[0]
        self.assertNotIn("static_cast<void>(BLEAdvertising.stop())", stop_path)
        self.assertNotIn("static_cast<void>(BLEScan.stop())", stop_path)
        self.assertIn('cleanupFail("cleanup_advertising_stop"', stop_path)
        self.assertIn('cleanupFail("cleanup_scan_stop"', stop_path)
        self.assertIn('cleanupFail("cleanup_resource_state"', stop_path)

    def test_target_resets_state_and_restarts_device_for_second_session(self) -> None:
        """두 번째 독립 nonce가 첫 session 상태를 재사용하지 않는지 검사합니다."""

        source = (
            REPOSITORY / "tests" / "zephyr" / "m33_ble_beacon_hil" / "src" / "main.cpp"
        ).read_text(encoding="utf-8")
        begin_path = source.split("void beginProtocol()", 1)[1].split(
            "/** @brief STOP", 1
        )[0]
        self.assertIn("finished = false;", begin_path)
        self.assertIn("::memset(format_sequences, 0", begin_path)
        self.assertIn("::memset(seen, 0", begin_path)
        self.assertIn("!BLEDevice.initialized() && !BLEDevice.begin(roleName())", begin_path)


if __name__ == "__main__":
    unittest.main()
