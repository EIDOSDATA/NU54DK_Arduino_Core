"""! @brief M31 HCI capability의 수정·재실행 불가능한 증거 경계를 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tests/hil/nu54dk/m31_ble_capability.py"
RUNNER_PATH = ROOT / "tests/hil/nu54dk/m31_ble_capability_run.py"
SPEC = importlib.util.spec_from_file_location("m31_ble_capability_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

NONCE = "0123456789abcdef0123456789abcdef"
IDENTITY = MODULE.ExpectedIdentity("1" * 40, "2" * 40, "3" * 40, "4" * 40)
IMAGE = "a" * 64


def valid_lines() -> list[str]:
    """! @brief raw feature bit와 CAP record가 일치하는 target 출력을 만듭니다. """
    raw = bytearray(8)
    for _identifier, bit in MODULE.CAPABILITY_BITS:
        if bit != 20:
            raw[bit // 8] |= 1 << (bit % 8)
    lines = [
        "M31CAP|1|READY",
        f"M31CAP|1|BEGIN|nonce={NONCE}|controller=default_sdc",
        f"M31CAP|1|IDENTITY|nonce={NONCE}|core={IDENTITY.core}|"
        f"board={IDENTITY.board}|ncs={IDENTITY.ncs}|zephyr={IDENTITY.zephyr}|"
        "controller=default_sdc",
        f"M31CAP|1|LE_FEATURES|nonce={NONCE}|features={raw.hex()}",
    ]
    for identifier, bit in MODULE.CAPABILITY_BITS:
        expected = 0 if bit == 20 else 1
        lines.append(f"M31CAP|1|CAP|nonce={NONCE}|id={identifier}|"
                     f"controller_bit={expected}|host_config=0")
    lines.append(f"M31CAP|1|END|records=10|capabilities=7|nonce={NONCE}")
    return lines


def transcript(lines: list[str]) -> bytes:
    """! @brief VCOM의 CRLF line 종료를 그대로 전달합니다. """
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


class M31CapabilityParserTests(unittest.TestCase):
    """! @brief Host build와 HCI query를 기능 runtime PASS로 혼동하지 않습니다. """

    def test_canonical_controller_query_is_separate_from_host_config(self) -> None:
        """! @brief 7개 HCI bit와 Host 설정을 모두 보존합니다. """
        result = MODULE.parse_transcript(transcript(valid_lines()), NONCE, IDENTITY)
        self.assertEqual(len(result.controller_bits), 7)
        self.assertTrue(result.controller_bits["channel_sounding"])
        self.assertFalse(result.controller_bits["raw_iq_rx"])
        self.assertFalse(any(result.host_config.values()))

    def test_register_query_timeout_is_bounded_for_three_probe_runs(self) -> None:
        """! @brief 병렬 빌드 중에도 DP/AP 조회 시간을 제한된 60초로 확보합니다. """
        runner = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("REGISTER_QUERY_TIMEOUT_SECONDS = 60", runner)
        self.assertIn("timeout=REGISTER_QUERY_TIMEOUT_SECONDS", runner)

    def test_wrong_nonce_and_revision_are_rejected(self) -> None:
        """! @brief 다른 attempt/source의 serial 출력을 재사용하지 않습니다. """
        for replacement in (NONCE.replace("0", "f"), "0" * 40):
            lines = valid_lines()
            if len(replacement) == 32:
                lines[1] = lines[1].replace(NONCE, replacement)
            else:
                lines[2] = lines[2].replace(IDENTITY.core, replacement)
            with self.subTest(replacement=replacement):
                with self.assertRaises(MODULE.M31CapabilityFailure):
                    MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_duplicate_missing_noise_and_truncation_are_rejected(self) -> None:
        """! @brief 부분 transcript나 재출력 CAP 한 줄을 성공으로 세지 않습니다. """
        scenarios = []
        duplicate = valid_lines()
        duplicate.insert(5, duplicate[4])
        scenarios.append(transcript(duplicate))
        missing = valid_lines()
        del missing[5]
        scenarios.append(transcript(missing))
        noisy = valid_lines()
        noisy[0] = "unexpected boot banner"
        scenarios.append(transcript(noisy))
        scenarios.append(transcript(valid_lines())[:-1])
        for input_bytes in scenarios:
            with self.subTest(size=len(input_bytes)):
                with self.assertRaises(MODULE.M31CapabilityFailure):
                    MODULE.parse_transcript(input_bytes, NONCE, IDENTITY)

    def test_raw_probe_uid_is_rejected(self) -> None:
        """! @brief UID가 기록될 조짐이 있으면 artifact 생성을 거부합니다. """
        lines = valid_lines()
        lines[3] += "|uid=raw-secret"
        with self.assertRaisesRegex(MODULE.M31CapabilityFailure, "UID"):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_unknown_role_status_and_bit_mismatch_are_rejected(self) -> None:
        """! @brief 잘못된 CAP label·상태·raw bit 복사를 모두 막습니다. """
        for replacement in ("id=wrong_role", "controller_bit=pass", "controller_bit=0"):
            lines = valid_lines()
            lines[4] = lines[4].replace("id=cis_central", replacement) if replacement.startswith("id=") else (
                lines[4].replace("controller_bit=1", replacement)
            )
            with self.subTest(replacement=replacement):
                with self.assertRaises(MODULE.M31CapabilityFailure):
                    MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_sdc_aod_or_iq_rx_false_support_is_rejected(self) -> None:
        """! @brief controller 지원 범위를 AoD/IQ 수신으로 확대하지 않습니다. """
        for bit in (20, 21):
            lines = valid_lines()
            raw = bytearray.fromhex(lines[3].split("features=", 1)[1])
            raw[bit // 8] |= 1 << (bit % 8)
            lines[3] = lines[3].split("features=", 1)[0] + "features=" + raw.hex()
            if bit == 20:
                lines[9] = lines[9].replace("controller_bit=0", "controller_bit=1")
            with self.subTest(bit=bit):
                with self.assertRaises(MODULE.M31CapabilityFailure):
                    MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_controller_variant_and_ll_antenna_boundary_are_checked(self) -> None:
        """! @brief LL 후보는 RX bit를 요구하되 AoA antenna switching으로 확대하지 않습니다. """
        lines = valid_lines()
        lines[1] = lines[1].replace("default_sdc", "zephyr_ll_candidate")
        lines[2] = lines[2].replace("default_sdc", "zephyr_ll_candidate")
        raw = bytearray.fromhex(lines[3].split("features=", 1)[1])
        raw[20 // 8] |= 1 << (20 % 8)
        lines[3] = lines[3].split("features=", 1)[0] + "features=" + raw.hex()
        lines[9] = lines[9].replace("controller_bit=0", "controller_bit=1")
        lines[9] = lines[9].replace("host_config=0", "host_config=1")
        result = MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY,
                                         "zephyr_ll_candidate")
        self.assertTrue(result.controller_bits["raw_iq_rx"])
        self.assertEqual(result.controller_variant, "zephyr_ll_candidate")
        with self.assertRaisesRegex(MODULE.M31CapabilityFailure, "wrong controller"):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)
        raw[22 // 8] |= 1 << (22 % 8)
        lines[3] = lines[3].split("features=", 1)[0] + "features=" + raw.hex()
        with self.assertRaisesRegex(MODULE.M31CapabilityFailure, "경계"):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY,
                                    "zephyr_ll_candidate")

    def test_image_hash_and_role_envelope_are_required(self) -> None:
        """! @brief image·role·nonce·transcript를 같은 실행에 결합합니다. """
        envelope = {"hex_sha256": IMAGE, "role": "capability_probe",
                    "nonce": NONCE, "transcript": transcript(valid_lines())}
        self.assertEqual(MODULE.validate_evidence_envelope(envelope, IMAGE, IDENTITY).nonce, NONCE)
        for mutation in ({"hex_sha256": "b" * 64}, {"role": "wrong_role"},
                         {"transcript": b""}):
            broken = {**envelope, **mutation}
            with self.subTest(mutation=mutation):
                with self.assertRaises(MODULE.M31CapabilityFailure):
                    MODULE.validate_evidence_envelope(broken, IMAGE, IDENTITY)


if __name__ == "__main__":
    unittest.main()
