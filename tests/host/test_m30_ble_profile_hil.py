"""! @brief M30-PROFILE-01 API·target·runner 계약을 검증합니다. """

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries/NUCODE_BLE_Security"
HIL_DIRECTORY = ROOT / "tests/hil/nu54dk"
RUNNER = HIL_DIRECTORY / "m30_ble_profile.py"
TARGET = ROOT / "tests/zephyr/m30_ble_profile_hil"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))
SPEC = spec_from_file_location("nu54_m30_ble_profile", RUNNER)
assert SPEC is not None and SPEC.loader is not None
PROFILE = module_from_spec(SPEC)
sys.modules[SPEC.name] = PROFILE
SPEC.loader.exec_module(PROFILE)


class M30BleProfileHilTests(unittest.TestCase):
    """! @brief 일곱 profile과 100회 정량 fail-closed 경계를 고정합니다. """

    def test_public_catalog_contains_seven_profiles(self) -> None:
        """! @brief 기존 3종과 신규 4종 공개 facade를 검사합니다. """

        header = (LIBRARY / "src/NUCODE_BLE_Security.h").read_text(encoding="utf-8")
        for token in (
            "class BatteryService",
            "class DeviceInformationService",
            "class HidKeyboard",
            "class HidMouse",
            "class HidConsumerControl",
            "class HeartRateService",
            "class EnvironmentalSensingService",
        ):
            self.assertIn(token, header)
        self.assertEqual(len(PROFILE.CATALOG), 7)

    def test_hids_backend_uses_three_fixed_input_reports(self) -> None:
        """! @brief heap 없이 keyboard·mouse·consumer report를 고정합니다. """

        backend = (LIBRARY / "src/internal/NUCODE_BLE_HidsBackend.c").read_text(
            encoding="utf-8"
        )
        implementation = (
            LIBRARY / "src/internal/security/SecurityHid.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("NUCODE_BLE_INPUT_REPORT_COUNT 3U", backend)
        self.assertIn("reports[2].id = 3U", backend)
        self.assertIn("consumer_report_index = 2U", implementation)
        for forbidden in ("malloc(", "calloc(", "realloc(", "new "):
            self.assertNotIn(forbidden, backend)
            self.assertNotIn(forbidden, implementation)

    def test_standard_hrs_and_ess_are_encrypted(self) -> None:
        """! @brief HRS와 ESS UUID·암호화 permission·bounded 값을 검사합니다. """

        configuration = (LIBRARY / "zephyr/ble-security.conf").read_text(
            encoding="utf-8"
        )
        backend = (
            LIBRARY / "src/internal/NUCODE_BLE_ProfilesBackend.c"
        ).read_text(encoding="utf-8")
        implementation = (
            LIBRARY / "src/internal/security/SecurityProfiles.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_HRS=y", configuration)
        self.assertIn("CONFIG_BT_HRS_DEFAULT_PERM_RW_ENCRYPT=y", configuration)
        self.assertIn("BT_UUID_ESS", backend)
        self.assertIn("BT_UUID_TEMPERATURE", backend)
        self.assertIn("BT_UUID_HUMIDITY", backend)
        self.assertIn("BT_GATT_PERM_READ_ENCRYPT", backend)
        self.assertIn("hundredths_percent > 10000U", implementation)

    def test_examples_exist_without_private_sidecars(self) -> None:
        """! @brief 신규 profile마다 canonical Arduino example 하나를 요구합니다. """

        for name in (
            "SecureMouse",
            "SecureConsumerControl",
            "HeartRate",
            "EnvironmentalSensing",
        ):
            example = LIBRARY / "examples" / name / f"{name}.ino"
            self.assertTrue(example.is_file(), example)
            self.assertFalse(example.with_suffix(".conf").exists())
            self.assertFalse(example.with_suffix(".overlay").exists())

    def test_target_matrix_contains_both_profile_roles(self) -> None:
        """! @brief v0.5.0 target matrix와 900초 HIL 계약을 검사합니다. """

        matrix = (ROOT / "tools/ci/run_zephyr_build.py").read_text(encoding="utf-8")
        self.assertIn('(\"m30_ble_profile_hil\", \"nucode.m30.profile.p\")', matrix)
        self.assertIn('(\"m30_ble_profile_hil\", \"nucode.m30.profile.c\")', matrix)
        target = (TARGET / "src/main.cpp").read_text(encoding="utf-8")
        self.assertIn("required_operations = 100U", target)
        self.assertIn("catalog_entries = 7U", target)
        self.assertIn("payload_errors", target)
        self.assertIn("M30_PROFILE_CORE_REVISION", target)

    def test_result_parser_rejects_any_quantitative_drift(self) -> None:
        """! @brief operation·payload 오류·nonce 변조를 모두 거부합니다. """

        nonce = "01" * 16
        revision = "a" * 40
        for role in ("peripheral", "central"):
            line = PROFILE.expected_result(role, nonce, revision)
            result = PROFILE.parse_result(line, role, nonce, revision)
            self.assertEqual(result.catalog, 7)
            self.assertEqual(result.operations, 100)
            self.assertEqual(result.payload_errors, 0)
            with self.assertRaises(PROFILE.M30ProfileFailure):
                PROFILE.parse_result(line.replace(b"operations=100", b"operations=99"),
                                     role, nonce, revision)
            with self.assertRaises(PROFILE.M30ProfileFailure):
                PROFILE.parse_result(line.replace(b"errors=0", b"errors=1"),
                                     role, nonce, revision)


if __name__ == "__main__":
    unittest.main()
