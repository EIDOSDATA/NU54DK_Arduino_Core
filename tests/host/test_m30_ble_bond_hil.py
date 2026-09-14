"""! @brief M30-BOND-01 runner의 final protocol parser를 검증합니다. """

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL_DIRECTORY = ROOT / "tests/hil/nu54dk"
RUNNER = HIL_DIRECTORY / "m30_ble_bond.py"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))
SPEC = spec_from_file_location("nu54_m30_ble_bond", RUNNER)
assert SPEC is not None and SPEC.loader is not None
BOND = module_from_spec(SPEC)
sys.modules[SPEC.name] = BOND
SPEC.loader.exec_module(BOND)


class M30BleBondHilTests(unittest.TestCase):
    """! @brief dynamic bond count만 허용하는 정량 RESULT 문법을 고정합니다. """

    def test_central_result_accepts_exact_contract(self) -> None:
        """! @brief central의 20 reconnect·3 rotation·migration·stale 0을 검사합니다. """

        nonce = "01" * 16
        revision = "a" * 40
        line = (
            "M30BOND|1|RESULT|role=central|bonded_reconnects=20|privacy_rotations=3|"
            "migration=1|stale_key_accepts=0|new_pairings=0|bond_count=1|"
            f"callback_context=pass|nonce={nonce}|core={revision}"
        ).encode("ascii")
        self.assertIsNotNone(BOND.result_pattern("central", nonce, revision).fullmatch(line))

    def test_peripheral_result_rejects_stale_accept(self) -> None:
        """! @brief stale key accept나 privacy field 교차를 허용하지 않습니다. """

        nonce = "23" * 16
        revision = "b" * 40
        valid = (
            "M30BOND|1|RESULT|role=peripheral|bonded_reconnects=20|migration=1|"
            "stale_key_accepts=0|new_pairings=0|bond_count=0|callback_context=pass|"
            f"nonce={nonce}|core={revision}"
        ).encode("ascii")
        pattern = BOND.result_pattern("peripheral", nonce, revision)
        self.assertIsNotNone(pattern.fullmatch(valid))
        self.assertIsNone(pattern.fullmatch(valid.replace(b"accepts=0", b"accepts=1")))
        self.assertIsNone(
            pattern.fullmatch(valid.replace(b"|migration=1", b"|privacy_rotations=3|migration=1"))
        )

    def test_build_matrix_contains_both_bond_roles(self) -> None:
        """! @brief v0.5.0 target matrix에 두 image가 모두 포함됩니다. """

        matrix = (ROOT / "tools/ci/run_zephyr_build.py").read_text(encoding="utf-8")
        self.assertIn('(\"m30_ble_bond_hil\", \"nucode.m30.bond.p\")', matrix)
        self.assertIn('(\"m30_ble_bond_hil\", \"nucode.m30.bond.c\")', matrix)

    def test_runner_checks_migration_after_first_restored_connection(self) -> None:
        """! @brief resume READY 전에는 0, 최종 restored link 뒤에는 1을 요구합니다. """

        runner = RUNNER.read_text(encoding="utf-8")
        target = (
            ROOT / "tests/zephyr/m30_ble_bond_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'f"migrations=0|rejected=0|core={core_revision}"',
            runner,
        )
        self.assertIn("BLESecurity.bondMigrationCount() != 0U", target)
        self.assertIn(
            'rb"\\|migration=1\\|stale_key_accepts=0\\|new_pairings=0"',
            runner,
        )


if __name__ == "__main__":
    unittest.main()
