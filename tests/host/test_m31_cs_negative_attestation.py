"""! @brief M31 CS negative 네 phase의 native attestation 계약을 검사합니다. """

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
HELPER = HIL / "m31_cs_negative_attestation.py"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))
SPEC = spec_from_file_location("m31_cs_negative_attestation", HELPER)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def cleanup(roles: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """! @brief 기본 PASS cleanup을 role별로 만듭니다. """

    return {
        role: {
            "stop": "PASS",
            "disconnect": "PASS",
            "serial_close": "PASS",
        }
        for role in roles
    }


class M31CsNegativeAttestationTests(unittest.TestCase):
    """! @brief 네 negative를 단일 20-cycle로 축약하지 못하게 고정합니다. """

    def test_phase_denominators_and_roles_are_independent(self) -> None:
        """! @brief stale 1·insecure 20·wrong 100·missing 20 분모를 고정합니다. """

        expected = {
            "stale_key": (("initiator", "reflector"), 1),
            "insecure_read": (("client", "reflector"), 20),
            "wrong_peer": (("initiator", "reflector", "wrong_peer"), 100),
            "missing_service": (
                ("initiator", "missing_service_peer"),
                20,
            ),
        }
        self.assertEqual(set(MODULE.PHASES), set(expected))
        self.assertEqual(
            len({spec.identifier for spec in MODULE.PHASES.values()}), 4
        )
        for name, (roles, cycles) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(MODULE.PHASES[name].roles, roles)
                self.assertEqual(MODULE.PHASES[name].cycles, cycles)

    def test_stale_key_is_one_real_negative_phase(self) -> None:
        """! @brief prime 성공 뒤 1:0 bond와 CS 무진행 1회만 PASS합니다. """

        record = {
            "test": "one_sided_stale_key_rejection",
            "arbitrary_unequal_ltk_injection": False,
            "prime_raw_reports": 1,
            "negative_raw_reports": 0,
            "rejection_path": "controller_key_failure_disconnect",
            "initiator_negative": {
                "bonds": 1,
                "pairing_requests": 0,
                "pairing_rejected": 0,
                "security_errors": 0,
                "security_reason": 0,
                "disconnects": 1,
                "disconnect_reason": 6,
                "l2": 0,
                "ready": 0,
                "raw": 0,
                "connected": 0,
            },
            "reflector_negative": {
                "bonds": 0,
                "pairing_requests": 0,
                "pairing_rejected": 0,
                "security_errors": 1,
                "security_reason": 4,
                "disconnects": 1,
                "disconnect_reason": 5,
                "l2": 0,
                "ready": 0,
                "active": 0,
                "connected": 0,
            },
            "initiator_lines": [
                "CSKEY initiator prime ready raw=1 bonds=1",
                "CSKEY initiator status bonds=1 pairing_requests=0 "
                "pairing_rejected=0 security_errors=0 security_reason=0 "
                "disconnects=1 disconnect_reason=6 l2=0 ready=0 raw=0 "
                "connected=0",
                "CSKEY initiator STOPPED",
            ],
            "reflector_lines": [
                "CSKEY reflector status bonds=0 pairing_requests=0 "
                "pairing_rejected=0 security_errors=1 security_reason=4 "
                "disconnects=1 disconnect_reason=5 l2=0 ready=0 active=0 "
                "connected=0",
                "CSKEY reflector STOPPED",
            ],
        }
        rows = MODULE.build_stale_key_records(
            record, cleanup(MODULE.PHASES["stale_key"].roles)
        )
        self.assertEqual(len(rows), 1)
        record["negative_raw_reports"] = 1
        with self.assertRaises(MODULE.CsNegativeAttestationFailure):
            MODULE.build_stale_key_records(
                record, cleanup(MODULE.PHASES["stale_key"].roles)
            )

    def test_insecure_read_requires_twenty_same_acl_raw_rejections(self) -> None:
        """! @brief 한 ACL·한 discovery에서 count 1..20과 ATT 5/15만 허용합니다. """

        timestamps = [100 + (index * 50) for index in range(20)]
        record = {
            "test": "unencrypted_ranging_features_read_20",
            "same_acl": True,
            "mode": "same_acl",
            "cycles_expected": 20,
            "rejected": 20,
            "connections": 1,
            "connection_events_observed": 1,
            "discovery_events_observed": 1,
            "unexpected_disconnects": 0,
            "read_timestamps_ms": timestamps,
            "att_errors": [5] * 20,
            "cycles": [{"cycle": index} for index in range(1, 21)],
            "client_lines": [
                "CS insecure peer connected count=1",
                "CS insecure RAS discovered",
                *[
                f"CS insecure read rejected att=5 count={index} ms={timestamp}"
                for index, timestamp in enumerate(timestamps, 1)
                ],
                *(["CS insecure retry requested"] * 19),
                "CS insecure peer disconnected reason=19",
            ],
            "reflector_lines": ["CS reflector disconnected"],
        }
        rows = MODULE.build_insecure_read_records(
            record, cleanup(MODULE.PHASES["insecure_read"].roles)
        )
        self.assertEqual(len(rows), 20)
        record["connections"] = 2
        with self.assertRaises(MODULE.CsNegativeAttestationFailure):
            MODULE.build_insecure_read_records(
                record, cleanup(MODULE.PHASES["insecure_read"].roles)
            )

    def test_wrong_peer_requires_three_roles_and_one_hundred_raw_results(self) -> None:
        """! @brief 잘못된 peer 무연결과 counter 0..99의 실제 결과를 함께 요구합니다. """

        phase_cleanup = cleanup(MODULE.PHASES["wrong_peer"].roles)
        phase_cleanup["reflector"]["stop"] = "NOT_APPLICABLE"
        phase_cleanup["wrong_peer"]["stop"] = "NOT_APPLICABLE"
        phase_cleanup["wrong_peer"]["disconnect"] = "NOT_APPLICABLE"
        record = {
            "test": "same_name_wrong_service_third_peer",
            "procedures": 100,
            "initiator_lines": [
                f"CS_RAW counter={index} local=2 peer=2 rtt=1 tone=1 valid_rtt=1"
                for index in range(100)
            ] + ["CS procedures stop requested", "CS initiator disconnected"],
            "reflector_lines": [
                "CS reflector connected",
                "CS reflector disconnected",
            ],
            "wrong_peer_lines": ["CS wrong peer advertising"],
        }
        rows = MODULE.build_wrong_peer_records(record, phase_cleanup)
        self.assertEqual(len(rows), 100)
        record["wrong_peer_lines"].append("CS wrong peer connected")
        with self.assertRaises(MODULE.CsNegativeAttestationFailure):
            MODULE.build_wrong_peer_records(record, phase_cleanup)

    def test_missing_service_requires_twenty_failures_and_final_disconnect(self) -> None:
        """! @brief UUID 광고만 있는 peer의 20회 -2와 양쪽 disconnect를 요구합니다. """

        phase_cleanup = cleanup(MODULE.PHASES["missing_service"].roles)
        phase_cleanup["missing_service_peer"]["stop"] = "NOT_APPLICABLE"
        record = {
            "test": "advertised_ranging_uuid_without_gatt_service",
            "cycles_expected": 20,
            "cycles_rejected": 20,
            "initiator_disconnects": 20,
            "peer_disconnects": 20,
            "initiator_lines": ["CS initiator failed: -2"] * 20,
            "missing_service_peer_lines": [
                "CS missing service connected"
            ] * 20,
        }
        rows = MODULE.build_missing_service_records(record, phase_cleanup)
        self.assertEqual(len(rows), 20)
        record["initiator_lines"].append("CS procedures requested")
        with self.assertRaises(MODULE.CsNegativeAttestationFailure):
            MODULE.build_missing_service_records(record, phase_cleanup)

    def test_runners_bind_exact_program_and_dispatch_attestation(self) -> None:
        """! @brief 네 runner가 build·readback helper와 독립 attestation을 모두 사용합니다. """

        runners = (
            "m31_cs_stale_key_run.py",
            "m31_cs_insecure_read_run.py",
            "m31_cs_wrong_peer_run.py",
            "m31_cs_missing_service_run.py",
        )
        for filename in runners:
            with self.subTest(filename=filename):
                source = (HIL / filename).read_text(encoding="utf-8")
                self.assertIn("prepare_program_phase(", source)
                self.assertIn("complete_program_phase(", source)
                self.assertIn('record["m33_dispatch_attestation"]', source)
                self.assertIn('record["cleanup"]', source)
                self.assertNotIn("mass erase", source.lower())
                self.assertNotIn("--unlock", source)
                self.assertNotIn(" recover ", source.lower())


if __name__ == "__main__":
    unittest.main()
