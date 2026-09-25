"""! @brief M31 CS one-sided stale-key fixture와 runner 계약을 검사합니다. """

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
RUNNER = HIL / "m31_cs_stale_key_run.py"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))
SPEC = spec_from_file_location("m31_cs_stale_key_run", RUNNER)
assert SPEC is not None and SPEC.loader is not None
STALE = module_from_spec(SPEC)
sys.modules[SPEC.name] = STALE
SPEC.loader.exec_module(STALE)


class M31CsStaleKeyTests(unittest.TestCase):
    """! @brief 임의 LTK 주입으로 확대하지 않는 negative 판정을 고정합니다. """

    def test_strict_status_parser_accepts_expected_roles(self) -> None:
        """! @brief role별 field 차이와 exact end anchor를 검사합니다. """

        initiator = STALE.parse_status_line(
            "initiator",
            "CSKEY initiator status bonds=1 pairing_rejected=1 "
            "l2=0 ready=0 raw=0 connected=0",
        )
        reflector = STALE.parse_status_line(
            "reflector",
            "CSKEY reflector status bonds=0 pairing_rejected=2 "
            "l2=0 ready=0 active=0 connected=0",
        )
        self.assertEqual(initiator["bonds"], 1)
        self.assertEqual(reflector["active"], 0)
        self.assertIsNone(
            STALE.parse_status_line(
                "initiator",
                "CSKEY initiator status bonds=1 pairing_rejected=1 "
                "l2=0 ready=0 raw=0 connected=0 trailing",
            )
        )

    def test_negative_snapshot_rejects_security_or_cs_progress(self) -> None:
        """! @brief bond 1:0과 양쪽 repair 거부 뒤 L2·ready·raw·active 0만 허용합니다. """

        initiator = {
            "bonds": 1,
            "pairing_rejected": 1,
            "l2": 0,
            "ready": 0,
            "raw": 0,
            "connected": 0,
        }
        reflector = {
            "bonds": 0,
            "pairing_rejected": 1,
            "l2": 0,
            "ready": 0,
            "active": 0,
            "connected": 0,
        }
        STALE.validate_negative_snapshot(initiator, reflector)
        for role, field in (
            (initiator, "raw"),
            (initiator, "l2"),
            (reflector, "ready"),
            (reflector, "active"),
        ):
            changed = role.copy()
            changed[field] = 1
            with self.assertRaises(STALE.StaleKeyFailure):
                if role is initiator:
                    STALE.validate_negative_snapshot(changed, reflector)
                else:
                    STALE.validate_negative_snapshot(initiator, changed)

    def test_only_reflector_has_one_sided_stale_erase_command(self) -> None:
        """! @brief 초기 clean 뒤 stale 단계에서는 reflector만 bond를 삭제합니다. """

        initiator = (
            HIL / "fixtures/RasStaleKeyInitiator/RasStaleKeyInitiator.ino"
        ).read_text(encoding="utf-8")
        reflector = (
            HIL / "fixtures/RasStaleKeyReflector/RasStaleKeyReflector.ino"
        ).read_text(encoding="utf-8")
        self.assertNotIn("stale erased bonds=", initiator)
        self.assertIn("CSKEY reflector stale erased bonds=", reflector)
        self.assertIn("BLESecurity.acceptPairing(record.connection, accept)", initiator)
        self.assertIn("BLESecurity.acceptPairing(record.connection, accept)", reflector)

    def test_adaptive_build_roles_are_explicit(self) -> None:
        """! @brief 내부 fixture도 CS 역할을 fail-closed manifest로 선언합니다. """

        for fixture, role in (
            ("RasStaleKeyInitiator", "ble-cs-ras-initiator"),
            ("RasStaleKeyReflector", "ble-cs-ras-reflector"),
        ):
            manifest = json.loads(
                (HIL / f"fixtures/{fixture}/nucode-build.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["roles"], [role])
            self.assertEqual(manifest["capabilities"], [])
            self.assertEqual(manifest["capacities"], {})

    def test_runner_labels_scope_without_arbitrary_ltk_claim(self) -> None:
        """! @brief 증적 명칭을 one-sided stale key로 한정하고 exact source를 요구할 수 있습니다. """

        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"test": "one_sided_stale_key_rejection"', source)
        self.assertIn('"arbitrary_unequal_ltk_injection": False', source)
        self.assertIn("exact HIL requires clean source", source)
        self.assertIn("refusing to overwrite existing evidence", source)


if __name__ == "__main__":
    unittest.main()
