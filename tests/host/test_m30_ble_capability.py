#!/usr/bin/env python3
"""! @brief M30 capability protocol parser의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tests" / "hil" / "nu54dk" / "m30_ble_capability.py"
APP_CMAKE_PATH = REPOSITORY / "tests" / "zephyr" / "m30_ble_capability" / "CMakeLists.txt"
SPECIFICATION = importlib.util.spec_from_file_location("m30_ble_capability_test", MODULE_PATH)
assert SPECIFICATION is not None and SPECIFICATION.loader is not None
MODULE = importlib.util.module_from_spec(SPECIFICATION)
sys.modules[SPECIFICATION.name] = MODULE
SPECIFICATION.loader.exec_module(MODULE)

NONCE = "0123456789abcdef0123456789abcdef"
IDENTITY = MODULE.ExpectedIdentity("1" * 40, "2" * 40, "3" * 40, "4" * 40)


def valid_lines(nonce: str = NONCE, identity: object = IDENTITY) -> list[str]:
    """! @brief Host 등록·정책 분류가 일치하는 canonical protocol을 만듭니다. """

    host = "|".join(f"{name}={value}" for name, value in MODULE.HOST_FIELDS)
    probe = "|".join(f"{name}={value}" for name, value in MODULE.PROBE_FIELDS)
    contract = "|".join(
        f"{name}={value}" for name, value in MODULE.CONTRACT_FIELDS
    )
    capabilities = [
        f"M30CAP|1|CAP|nonce={nonce}|id={identifier}|source=candidate|"
        f"publication={publication}|probe={probe_status}"
        for identifier, publication, probe_status in MODULE.CAPABILITY_EXPECTATIONS
    ]
    return [
        "M30CAP|1|READY",
        f"M30CAP|1|BEGIN|nonce={nonce}",
        f"M30CAP|1|IDENTITY|nonce={nonce}|core={identity.core}|"
        f"board={identity.board}|ncs={identity.ncs}|zephyr={identity.zephyr}",
        f"M30CAP|1|HOST|nonce={nonce}|{host}",
        f"M30CAP|1|PROBE|nonce={nonce}|{probe}",
        f"M30CAP|1|CONTRACT|nonce={nonce}|{contract}",
        *capabilities,
        f"M30CAP|1|END|records=11|capabilities=7|nonce={nonce}",
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


class M30BleCapabilityParserTests(unittest.TestCase):
    """! @brief canonical PASS와 stale·duplicate·missing·noise·timeout 거부를 고정합니다. """

    def test_canonical_protocol_passes(self) -> None:
        """! @brief 7개 capability와 실제 Host 등록 결과를 반환합니다. """

        result = MODULE.parse_transcript(transcript(valid_lines()), NONCE, IDENTITY)
        self.assertEqual(len(result.capabilities), 7)
        self.assertEqual(result.host["min_key_bytes"], 16)
        self.assertEqual(result.probe["mcumgr_service"], 1)
        self.assertEqual(result.contract["oob_frame_bytes"], 192)
        self.assertEqual(result.identity, IDENTITY)

    def test_revision_query_is_container_ownership_safe(self) -> None:
        """! @brief container의 다른 checkout 소유자를 명령 단위로 처리합니다. """

        cmake = APP_CMAKE_PATH.read_text(encoding="utf-8")
        self.assertIn('git -c "safe.directory=${repository}"', cmake)
        self.assertNotIn("git config --global", cmake)

    def test_stale_nonce_is_rejected(self) -> None:
        """! @brief 이전 실행 nonce로 묶인 전체 transcript도 거부합니다. """

        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(valid_lines("f" * 32)), NONCE, IDENTITY)

    def test_wrong_revision_is_rejected(self) -> None:
        """! @brief 기대 checkout과 다른 image revision을 거부합니다. """

        wrong = MODULE.ExpectedIdentity("a" * 40, IDENTITY.board, IDENTITY.ncs, IDENTITY.zephyr)
        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(valid_lines(identity=wrong)), NONCE, IDENTITY)

    def test_noise_line_is_rejected(self) -> None:
        """! @brief protocol prefix가 없는 boot/debug 문자열을 허용하지 않습니다. """

        lines = valid_lines()
        lines.insert(1, "unexpected boot noise")
        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_duplicate_or_missing_record_is_rejected(self) -> None:
        """! @brief capability 중복과 누락을 모두 거부합니다. """

        duplicate = valid_lines()
        duplicate.insert(8, duplicate[7])
        missing = valid_lines()
        del missing[8]
        for lines in (duplicate, missing):
            with self.subTest(line_count=len(lines)):
                with self.assertRaises(MODULE.M30CapabilityFailure):
                    MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_reordered_capabilities_are_rejected(self) -> None:
        """! @brief 모든 값이 있어도 정책 순서를 바꾸면 거부합니다. """

        lines = valid_lines()
        lines[6], lines[7] = lines[7], lines[6]
        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_security_configuration_shortfall_is_rejected(self) -> None:
        """! @brief key 크기 또는 link 상한이 작으면 거부합니다. """

        lines = valid_lines()
        lines[3] = lines[3].replace("min_key_bytes=16", "min_key_bytes=15")
        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_host_registration_failure_is_rejected(self) -> None:
        """! @brief 실제 MCUmgr service 재등록 실패를 거부합니다. """

        lines = valid_lines()
        lines[4] = lines[4].replace("mcumgr_service=1", "mcumgr_service=0")
        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_resource_contract_mismatch_is_rejected(self) -> None:
        """! @brief target이 더 작은 OOB frame 상한을 보고하면 거부합니다. """

        lines = valid_lines()
        lines[5] = lines[5].replace("oob_frame_bytes=192", "oob_frame_bytes=191")
        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_source_only_capability_cannot_claim_runtime_probe(self) -> None:
        """! @brief boot/rollback 후보를 W01 runtime PASS로 승격하면 거부합니다. """

        lines = valid_lines()
        lines[10] = lines[10].replace("probe=source_only", "probe=service_registered")
        with self.assertRaises(MODULE.M30CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_target_failure_record_is_rejected(self) -> None:
        """! @brief target 초기화 실패를 정상 transcript로 해석하지 않습니다. """

        lines = valid_lines()
        lines[4] = "M30CAP|1|FAIL|stage=mcumgr_register|code=-12"
        with self.assertRaises(MODULE.M30CapabilityFailure):
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
