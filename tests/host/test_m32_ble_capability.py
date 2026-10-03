"""! @brief M32 modern LE capability 증거의 fail-closed 경계를 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tests/hil/nu54dk/m32_ble_capability.py"
RUNNER_PATH = ROOT / "tests/hil/nu54dk/m32_ble_capability_run.py"
SPEC = importlib.util.spec_from_file_location("m32_ble_capability_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

NONCE = "0123456789abcdef0123456789abcdef"
IDENTITY = MODULE.ExpectedIdentity("1" * 40, "2" * 40, "3" * 40, "4" * 40)
IMAGE = "a" * 64


def valid_lines(profile: str = "ble_extended") -> list[str]:
    """! @brief raw feature·Kconfig·자원이 일치하는 target 출력을 만듭니다. """
    extended = profile == "ble_extended"
    raw = bytearray(16 if extended else 8)
    for identifier, bit in MODULE.CAPABILITY_BITS:
        if extended or identifier == "channel_classification":
            raw[bit // 8] |= 1 << (bit % 8)
    resources = MODULE.PROFILE_RESOURCES[profile]
    lines = [
        "M32CAP|1|READY",
        f"M32CAP|1|BEGIN|nonce={NONCE}|controller=product_sdc|profile={profile}",
        f"M32CAP|1|IDENTITY|nonce={NONCE}|core={IDENTITY.core}|"
        f"board={IDENTITY.board}|ncs={IDENTITY.ncs}|zephyr={IDENTITY.zephyr}|"
        f"controller=product_sdc|profile={profile}",
        f"M32CAP|1|LE_FEATURES|nonce={NONCE}|max_page={1 if extended else 0}|"
        f"octets={len(raw)}|features={raw.hex()}",
        f"M32CAP|1|RESOURCES|nonce={NONCE}|connections={resources['connections']}|"
        f"peripherals={resources['peripherals']}|adv_sets={resources['adv_sets']}|"
        f"identities={resources['identities']}|syncs={resources['syncs']}|"
        f"acl_tx={resources['acl_tx']}|acl_rx={resources['acl_rx']}",
    ]
    for identifier, bit in MODULE.CAPABILITY_BITS:
        enabled = extended or identifier == "channel_classification"
        controller_bit = bit // 8 < len(raw) and bool(raw[bit // 8] & (1 << (bit % 8)))
        lines.append(
            f"M32CAP|1|CAP|nonce={NONCE}|id={identifier}|"
            f"controller_bit={1 if controller_bit else 0}|"
            f"host_config={1 if enabled else 0}"
        )
    lines.append(f"M32CAP|1|END|records=17|capabilities=13|nonce={NONCE}")
    return lines


def transcript(lines: list[str]) -> bytes:
    """! @brief VCOM의 CRLF line 종료를 그대로 전달합니다. """
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


class M32CapabilityParserTests(unittest.TestCase):
    """! @brief HCI query와 compile profile을 기능 runtime PASS로 확대하지 않습니다. """

    def test_baseline_and_extended_profiles_are_separate(self) -> None:
        """! @brief 두 프로필의 page 길이·Host 설정·자원을 각각 고정합니다. """
        baseline = MODULE.parse_transcript(
            transcript(valid_lines("ble_baseline")), NONCE, IDENTITY, "ble_baseline"
        )
        extended = MODULE.parse_transcript(
            transcript(valid_lines("ble_extended")), NONCE, IDENTITY, "ble_extended"
        )
        self.assertEqual(len(baseline.feature_bytes), 8)
        self.assertEqual(len(extended.feature_bytes), 16)
        self.assertFalse(baseline.host_config["path_loss_monitor"])
        self.assertTrue(extended.host_config["path_loss_monitor"])
        self.assertEqual(extended.resources["adv_sets"], 3)

    def test_register_query_timeout_and_sector_flash_are_explicit(self) -> None:
        """! @brief 실행기는 자동 unlock 없이 제한 시간의 sector flash만 사용합니다. """
        runner = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("REGISTER_QUERY_TIMEOUT_SECONDS = 60", runner)
        self.assertIn("timeout=REGISTER_QUERY_TIMEOUT_SECONDS", runner)
        self.assertIn('"auto_unlock=false"', runner)
        self.assertIn('"cmsis_dap.prefer_v1=false"', runner)
        self.assertIn('"--frequency", "500000"', runner)
        self.assertIn('"--connect", "attach"', runner)
        self.assertNotIn("cmsis_dap_v1=True", runner)
        self.assertIn("flash_image_pyocd", runner)
        self.assertIn("hardware_reset=True", runner)
        self.assertIn("preserve_nrf54l_access=True", runner)

    def test_wrong_nonce_revision_profile_and_controller_are_rejected(self) -> None:
        """! @brief 다른 attempt·source·image 프로필 출력을 재사용하지 않습니다. """
        scenarios = []
        wrong_nonce = valid_lines()
        wrong_nonce[1] = wrong_nonce[1].replace(NONCE, "f" * 32)
        scenarios.append(wrong_nonce)
        wrong_revision = valid_lines()
        wrong_revision[2] = wrong_revision[2].replace(IDENTITY.core, "0" * 40)
        scenarios.append(wrong_revision)
        wrong_profile = valid_lines()
        wrong_profile[1] = wrong_profile[1].replace("ble_extended", "ble_baseline")
        scenarios.append(wrong_profile)
        wrong_controller = valid_lines()
        wrong_controller[1] = wrong_controller[1].replace("product_sdc", "wrong")
        scenarios.append(wrong_controller)
        for lines in scenarios:
            with self.subTest(line=lines[1]):
                with self.assertRaises(MODULE.M32CapabilityFailure):
                    MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY, "ble_extended")

    def test_duplicate_missing_noise_truncation_and_uid_are_rejected(self) -> None:
        """! @brief 부분·중복·잡음 transcript와 raw probe UID를 성공으로 세지 않습니다. """
        duplicate = valid_lines()
        duplicate.insert(6, duplicate[5])
        missing = valid_lines()
        del missing[6]
        noisy = valid_lines()
        noisy[0] = "unexpected boot banner"
        leaked = valid_lines()
        leaked[3] += "|uid=raw-secret"
        scenarios = [
            transcript(duplicate), transcript(missing), transcript(noisy),
            transcript(valid_lines())[:-1], transcript(leaked),
        ]
        for input_bytes in scenarios:
            with self.subTest(size=len(input_bytes)):
                with self.assertRaises(MODULE.M32CapabilityFailure):
                    MODULE.parse_transcript(input_bytes, NONCE, IDENTITY, "ble_extended")

    def test_feature_page_shape_and_capability_bit_are_recomputed(self) -> None:
        """! @brief page 메타데이터와 CAP 복사 값이 raw byte와 다르면 거부합니다. """
        scenarios = []
        wrong_page = valid_lines()
        wrong_page[3] = wrong_page[3].replace("max_page=1", "max_page=0")
        scenarios.append(wrong_page)
        wrong_octets = valid_lines()
        wrong_octets[3] = wrong_octets[3].replace("octets=16", "octets=8")
        scenarios.append(wrong_octets)
        wrong_bit = valid_lines()
        wrong_bit[5] = wrong_bit[5].replace("controller_bit=1", "controller_bit=0")
        scenarios.append(wrong_bit)
        wrong_status = valid_lines()
        wrong_status[5] = wrong_status[5].replace("host_config=1", "host_config=pass")
        scenarios.append(wrong_status)
        for lines in scenarios:
            with self.subTest(feature=lines[3]):
                with self.assertRaises(MODULE.M32CapabilityFailure):
                    MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY, "ble_extended")

    def test_resource_and_host_config_contracts_are_exact(self) -> None:
        """! @brief 자원 숫자와 compile-time Kconfig의 drift를 모두 막습니다. """
        wrong_resource = valid_lines()
        wrong_resource[4] = wrong_resource[4].replace("adv_sets=3", "adv_sets=4")
        wrong_host = valid_lines()
        wrong_host[6] = wrong_host[6].replace("host_config=1", "host_config=0")
        malformed_integer = valid_lines()
        malformed_integer[4] = malformed_integer[4].replace("acl_tx=8", "acl_tx=08")
        for lines in (wrong_resource, wrong_host, malformed_integer):
            with self.subTest(resources=lines[4]):
                with self.assertRaises(MODULE.M32CapabilityFailure):
                    MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY, "ble_extended")

    def test_image_hash_role_and_transcript_envelope_are_required(self) -> None:
        """! @brief image·role·nonce·transcript를 같은 실행에 결합합니다. """
        envelope = {
            "hex_sha256": IMAGE,
            "role": "capability_probe",
            "nonce": NONCE,
            "transcript": transcript(valid_lines()),
        }
        result = MODULE.validate_evidence_envelope(
            envelope, IMAGE, IDENTITY, "ble_extended"
        )
        self.assertEqual(result.nonce, NONCE)
        for mutation in (
            {"hex_sha256": "b" * 64},
            {"role": "wrong_role"},
            {"transcript": b""},
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(MODULE.M32CapabilityFailure):
                    MODULE.validate_evidence_envelope(
                        {**envelope, **mutation}, IMAGE, IDENTITY, "ble_extended"
                    )


if __name__ == "__main__":
    unittest.main()
