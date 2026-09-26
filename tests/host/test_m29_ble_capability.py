#!/usr/bin/env python3
"""! @brief M29 capability protocol parser의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tests" / "hil" / "nu54dk" / "m29_ble_capability.py"
APP_CMAKE_PATH = (
    REPOSITORY / "tests" / "zephyr" / "m29_ble_capability" / "CMakeLists.txt"
)
SPECIFICATION = importlib.util.spec_from_file_location("m29_ble_capability_test", MODULE_PATH)
assert SPECIFICATION is not None and SPECIFICATION.loader is not None
MODULE = importlib.util.module_from_spec(SPECIFICATION)
sys.modules[SPECIFICATION.name] = MODULE
SPECIFICATION.loader.exec_module(MODULE)

NONCE = "0123456789abcdef0123456789abcdef"
IDENTITY = MODULE.ExpectedIdentity("1" * 40, "2" * 40, "3" * 40, "4" * 40)


def valid_lines(nonce: str = NONCE, identity: object = IDENTITY) -> list[str]:
    """! @brief Host 등록·정책 분류가 일치하는 canonical protocol을 만듭니다. """

    host = "|".join(f"{name}={value}" for name, value in MODULE.HOST_FIELDS)
    contract = "|".join(
        f"{name}={value}" for name, value in MODULE.CONTRACT_FIELDS
    )
    capabilities = [
        f"M29CAP|1|CAP|nonce={nonce}|id={identifier}|sdk={sdk_status}|"
        f"config=pass|probe={probe_status}"
        for identifier, sdk_status, probe_status in MODULE.CAPABILITY_EXPECTATIONS
    ]
    return [
        "M29CAP|1|READY",
        f"M29CAP|1|BEGIN|nonce={nonce}",
        f"M29CAP|1|IDENTITY|nonce={nonce}|core={identity.core}|"
        f"board={identity.board}|ncs={identity.ncs}|zephyr={identity.zephyr}",
        f"M29CAP|1|HOST|nonce={nonce}|{host}",
        f"M29CAP|1|PROBE|nonce={nonce}|gatt_service=1|l2cap_server=1|l2cap_psm=128",
        f"M29CAP|1|CONTRACT|nonce={nonce}|{contract}",
        *capabilities,
        f"M29CAP|1|END|records=11|capabilities=7|nonce={nonce}",
    ]


def transcript(lines: list[str]) -> bytes:
    """! @brief line 목록을 target과 같은 CRLF transcript로 만듭니다. """

    return ("\r\n".join(lines) + "\r\n").encode("ascii")


class EmptySerial:
    """! @brief timeout 시험에서 byte를 반환하지 않는 UART 대역입니다. """

    in_waiting = 0

    def reset_input_buffer(self) -> None:
        """! @brief flash reset 구간의 입력 폐기를 모사합니다. """

    def write(self, payload: bytes) -> int:
        """! @brief command 전체가 UART에 기록된 것으로 모사합니다. """

        return len(payload)

    def flush(self) -> None:
        """! @brief synthetic UART에는 지연된 출력이 없습니다. """

    def read(self, _size: int) -> bytes:
        """! @brief 항상 빈 입력을 반환합니다. """

        return b""


class M29BleCapabilityParserTests(unittest.TestCase):
    """! @brief canonical PASS와 stale·duplicate·missing·noise·timeout 거부를 고정합니다. """

    def test_canonical_protocol_passes(self) -> None:
        """! @brief 7개 capability와 실제 Host 등록 결과를 반환합니다. """

        result = MODULE.parse_transcript(transcript(valid_lines()), NONCE, IDENTITY)
        self.assertEqual(len(result.capabilities), 7)
        self.assertEqual(result.l2cap_psm, 128)
        self.assertEqual(result.contract["value_bytes"], 512)
        self.assertEqual(result.identity, IDENTITY)

    def test_revision_query_is_container_ownership_safe(self) -> None:
        """! @brief container의 다른 checkout 소유자를 명령 단위로 처리합니다. """

        cmake = APP_CMAKE_PATH.read_text(encoding="utf-8")
        self.assertIn('git -c "safe.directory=${repository}"', cmake)
        self.assertNotIn("git config --global", cmake)

    def test_stale_nonce_is_rejected(self) -> None:
        """! @brief 이전 실행 nonce로 묶인 전체 transcript도 거부합니다. """

        stale = "f" * 32
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(valid_lines(stale)), NONCE, IDENTITY)

    def test_wrong_revision_is_rejected(self) -> None:
        """! @brief 형식이 맞아도 기대 checkout과 다른 image revision을 거부합니다. """

        wrong = MODULE.ExpectedIdentity("a" * 40, IDENTITY.board, IDENTITY.ncs, IDENTITY.zephyr)
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(valid_lines(identity=wrong)), NONCE, IDENTITY)

    def test_noise_line_is_rejected(self) -> None:
        """! @brief protocol prefix가 없는 boot/debug 문자열을 허용하지 않습니다. """

        lines = valid_lines()
        lines.insert(1, "unexpected boot noise")
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_duplicate_record_is_rejected(self) -> None:
        """! @brief 같은 capability record를 추가해 count를 맞출 수 없습니다. """

        lines = valid_lines()
        lines.insert(8, lines[7])
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_missing_record_is_rejected(self) -> None:
        """! @brief 필수 capability 하나가 없으면 END가 있어도 거부합니다. """

        lines = valid_lines()
        del lines[8]
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_reordered_capabilities_are_rejected(self) -> None:
        """! @brief 모든 값이 있어도 순서를 바꾸면 거부합니다. """

        lines = valid_lines()
        lines[6], lines[7] = lines[7], lines[6]
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_host_configuration_shortfall_is_rejected(self) -> None:
        """! @brief ATT prepare buffer나 EATT 상한이 작으면 거부합니다. """

        lines = valid_lines()
        lines[3] = lines[3].replace("prepare_count=8", "prepare_count=7")
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_registration_failure_is_rejected(self) -> None:
        """! @brief compile 설정만 맞고 실제 Host API 등록이 실패한 결과를 거부합니다. """

        lines = valid_lines()
        lines[4] = lines[4].replace("l2cap_server=1", "l2cap_server=0")
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_invalid_dynamic_psm_is_rejected(self) -> None:
        """! @brief LE 동적 PSM 범위 밖의 등록 결과를 거부합니다. """

        lines = valid_lines()
        lines[4] = lines[4].replace("l2cap_psm=128", "l2cap_psm=127")
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_resource_contract_mismatch_is_rejected(self) -> None:
        """! @brief target이 더 작은 SDU 상한을 보고하면 거부합니다. """

        lines = valid_lines()
        lines[5] = lines[5].replace("coc_sdu_bytes=512", "coc_sdu_bytes=511")
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_deprecated_and_experimental_labels_cannot_be_promoted(self) -> None:
        """! @brief Signed Write/EATT의 SDK 분류를 stable로 바꾸면 거부합니다. """

        lines = valid_lines()
        lines[11] = lines[11].replace("sdk=deprecated", "sdk=stable")
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_peer_required_features_cannot_claim_runtime_pass(self) -> None:
        """! @brief peer 미실행 capability를 W01 runtime PASS로 승격하면 거부합니다. """

        lines = valid_lines()
        lines[12] = lines[12].replace("probe=peer_required", "probe=gatt_registered")
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_target_failure_record_is_rejected(self) -> None:
        """! @brief target 초기화 실패를 정상 transcript로 해석하지 않습니다. """

        lines = valid_lines()
        lines[4] = "M29CAP|1|FAIL|stage=l2cap_register|code=-12"
        with self.assertRaises(MODULE.M29CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_timeout_is_finite_and_rejected(self) -> None:
        """! @brief READY가 없는 UART를 유한 deadline 뒤 실패시킵니다. """

        with self.assertRaises(TimeoutError):
            MODULE.collect_transcript(
                EmptySerial(),
                NONCE,
                1.0,
                monotonic=lambda: 0.0,
                sleeper=lambda _seconds: None,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
