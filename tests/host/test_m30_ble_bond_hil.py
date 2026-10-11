"""! @brief M30-BOND-01 runner의 final protocol parser를 검증합니다. """

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


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
            "M30BOND|1|RESULT|role=central|bonded_reconnects=20|migration=1|"
            "stale_key_accepts=0|new_pairings=0|bond_count=1|"
            f"callback_context=pass|nonce={nonce}|core={revision}"
        ).encode("ascii")
        self.assertIsNotNone(BOND.result_pattern("central", nonce, revision).fullmatch(line))

    def test_peripheral_result_rejects_stale_accept(self) -> None:
        """! @brief stale key accept나 privacy field 교차를 허용하지 않습니다. """

        nonce = "23" * 16
        revision = "b" * 40
        valid = (
            "M30BOND|1|RESULT|role=peripheral|bonded_reconnects=20|privacy_rotations=3|"
            "migration=1|stale_key_accepts=0|new_pairings=0|bond_count=0|"
            "callback_context=pass|"
            f"nonce={nonce}|core={revision}"
        ).encode("ascii")
        pattern = BOND.result_pattern("peripheral", nonce, revision)
        self.assertIsNotNone(pattern.fullmatch(valid))
        self.assertIsNone(pattern.fullmatch(valid.replace(b"accepts=0", b"accepts=1")))
        self.assertIsNone(
            pattern.fullmatch(valid.replace(b"|privacy_rotations=3", b""))
        )

    def test_build_matrix_contains_both_bond_roles(self) -> None:
        """! @brief v0.5.0 target matrix에 두 image가 모두 포함됩니다. """

        matrix = (ROOT / "tools/ci/run_zephyr_build.py").read_text(encoding="utf-8")
        self.assertIn('(\"m30_ble_bond_hil\", \"nucode.m30.bond.p\")', matrix)
        self.assertIn('(\"m30_ble_bond_hil\", \"nucode.m30.bond.c\")', matrix)

    def test_target_enables_extended_privacy_advertising(self) -> None:
        """! @brief 송신측 RPA 만료 callback에 필요한 단일 extended set을 고정합니다. """

        configuration = (
            ROOT / "tests/zephyr/m30_ble_bond_hil/prj.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_EXT_ADV=y", configuration)
        self.assertIn("CONFIG_BT_EXT_ADV_MAX_ADV_SET=1", configuration)

    def test_rpa_restart_waits_for_controller_resource_release(self) -> None:
        """! @brief RPA 회전 stop 뒤 -ENOMEM을 bounded 재시도로 흡수합니다. """

        target = (
            ROOT / "tests/zephyr/m30_ble_bond_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "rpa_start_pending = true;",
            "rpa_retry_error_pending = true;",
            "if (rpa_retry_error_pending &&",
            "rpa_retry_error_pending = false;",
            "rpa_retry_driver_error = -ENOMEM;",
            "rpa_retry_driver_error = -EALREADY;",
            "BLEDevice.lastError() == nucode::ble::BLEError::already_started",
            "BLEExtendedAdvertising.running(advertising_set)",
            "BLEDevice.lastError() == nucode::ble::BLEError::driver_error",
            "action_due_ms = now + 100;",
            "BLEDevice.lastDriverError() == -ENOMEM",
            "now < rpa_restart_deadline_ms",
            'fail("privacy-rpa-timeout-restore")',
        ):
            self.assertIn(token, target)

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
        self.assertIn("M30_BOND_PROGRESS={decoded}", runner)
        self.assertIn('peripheral_path.write_bytes(captures["peripheral"])', runner)

    def test_flash_roles_are_sequential_and_hash_bound(self) -> None:
        """! @brief 두 역할 flash 순서와 exact HEX hash 결합을 고정합니다. """

        class FlashComplete(RuntimeError):
            """! @brief flash 후 UART 단계 진입을 차단하는 시험 전용 예외입니다. """

        endpoints = {
            "peripheral": BOND.RoleEndpoint(
                "a" * 32, SimpleNamespace(root=Path("e:/")), "COM5"
            ),
            "central": BOND.RoleEndpoint(
                "b" * 32, SimpleNamespace(root=Path("f:/")), "COM18"
            ),
        }
        images = {
            role: BOND.ImageInput(Path(f"{role}.hex"), 4, character * 64, {})
            for role, character in (("peripheral", "1"), ("central", "2"))
        }
        captures = {"peripheral": bytearray(), "central": bytearray()}
        calls = []

        def flash(role, probe, path, timeout, *, expected_sha256):
            """! @brief 실제 접근 없이 순서와 immutable 입력만 기록합니다. """

            calls.append((role, probe, path, timeout, expected_sha256))
            return "pyocd-sector-sw-reset", "4"

        with mock.patch.object(
            BOND, "flash_image_pyocd_sha256", side_effect=flash
        ), mock.patch.object(BOND.time, "sleep", side_effect=FlashComplete):
            with self.assertRaises(FlashComplete):
                BOND.execute_hil(
                    None,
                    endpoints,
                    images,
                    BOND.DEFAULT_BAUD_RATE,
                    120.0,
                    600.0,
                    "a" * 40,
                    "01" * 16,
                    captures,
                )

        self.assertEqual([call[0] for call in calls], ["peripheral", "central"])
        for role, _probe, path, timeout, expected_sha256 in calls:
            self.assertEqual(path, images[role].path)
            self.assertEqual(timeout, 120.0)
            self.assertEqual(expected_sha256, images[role].sha256)
            records = [
                json.loads(line.split(b"|", 2)[2])
                for line in captures[role].splitlines()
            ]
            self.assertEqual(
                [record["stage"] for record in records],
                ["FLASH_CALL_ENTER", "FLASH_CALL_RETURNED"],
            )
            self.assertTrue(
                all(record["cleanup"] == "UNVERIFIED" for record in records)
            )

    def test_first_flash_error_stops_the_second_role(self) -> None:
        """! @brief 첫 flash 예외를 보존하고 central 접근을 금지합니다. """

        endpoints = {
            "peripheral": BOND.RoleEndpoint(
                "a" * 32, SimpleNamespace(root=Path("e:/")), "COM5"
            ),
            "central": BOND.RoleEndpoint(
                "b" * 32, SimpleNamespace(root=Path("f:/")), "COM18"
            ),
        }
        images = {
            role: BOND.ImageInput(Path(f"{role}.hex"), 4, character * 64, {})
            for role, character in (("peripheral", "1"), ("central", "2"))
        }
        captures = {"peripheral": bytearray(), "central": bytearray()}
        first_error = RuntimeError("first flash failure")
        calls = []

        def flash(role, _probe, _path, _timeout, *, expected_sha256):
            """! @brief 첫 역할에서 고정 예외를 주입합니다. """

            calls.append((role, expected_sha256))
            raise first_error

        with mock.patch.object(
            BOND, "flash_image_pyocd_sha256", side_effect=flash
        ):
            with self.assertRaises(RuntimeError) as caught:
                BOND.execute_hil(
                    None,
                    endpoints,
                    images,
                    BOND.DEFAULT_BAUD_RATE,
                    120.0,
                    600.0,
                    "a" * 40,
                    "01" * 16,
                    captures,
                )

        self.assertIs(caught.exception, first_error)
        self.assertEqual(calls, [("peripheral", "1" * 64)])
        self.assertEqual(captures["central"], b"")
        records = [
            json.loads(line.split(b"|", 2)[2])
            for line in captures["peripheral"].splitlines()
        ]
        self.assertEqual(
            [record["stage"] for record in records],
            ["FLASH_CALL_ENTER", "FLASH_CALL_ERROR"],
        )
        self.assertEqual(records[-1]["first_error_type"], "RuntimeError")
        self.assertEqual(records[-1]["cleanup"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
