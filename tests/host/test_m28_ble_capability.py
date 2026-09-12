#!/usr/bin/env python3
"""! @brief M28 capability protocol parser의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tests" / "hil" / "nu54dk" / "m28_ble_capability.py"
SPECIFICATION = importlib.util.spec_from_file_location("m28_ble_capability_test", MODULE_PATH)
assert SPECIFICATION is not None and SPECIFICATION.loader is not None
MODULE = importlib.util.module_from_spec(SPECIFICATION)
sys.modules[SPECIFICATION.name] = MODULE
SPECIFICATION.loader.exec_module(MODULE)

NONCE = "0123456789abcdef0123456789abcdef"
IDENTITY = MODULE.ExpectedIdentity(
    "1" * 40,
    "2" * 40,
    "3" * 40,
    "4" * 40,
)


def _set_bits(length: int, bits: tuple[tuple[int, int], ...]) -> bytes:
    """! @brief synthetic HCI byte 배열에 지정 bit를 설정합니다. """

    values = bytearray(length)
    for octet, bit in bits:
        values[octet] |= 1 << bit
    return bytes(values)


def valid_lines(nonce: str = NONCE, identity: object = IDENTITY) -> list[str]:
    """! @brief 모든 raw HCI 판정이 일치하는 canonical protocol을 만듭니다. """

    command_bits = tuple(
        sorted(
            {
                bit
                for requirements in MODULE.COMMAND_REQUIREMENTS.values()
                for bit in requirements
            }
        )
    )
    feature_bits = tuple(
        sorted(
            {
                bit
                for requirements in MODULE.FEATURE_REQUIREMENTS.values()
                for bit in requirements
            }
        )
    )
    commands = _set_bits(64, command_bits).hex()
    features = _set_bits(8, tuple((bit >> 3, bit & 7) for bit in feature_bits)).hex()
    host = "|".join(f"{name}={value}" for name, value in MODULE.HOST_FIELDS)
    capability_lines = [
        f"M28CAP|1|CAP|nonce={nonce}|id={identifier}|host=pass|"
        f"controller=pass|evidence={evidence}"
        for identifier, evidence in MODULE.CAPABILITY_EVIDENCE
    ]
    return [
        "M28CAP|1|READY",
        f"M28CAP|1|BEGIN|nonce={nonce}",
        f"M28CAP|1|IDENTITY|nonce={nonce}|core={identity.core}|"
        f"board={identity.board}|ncs={identity.ncs}|zephyr={identity.zephyr}",
        f"M28CAP|1|HOST|nonce={nonce}|{host}",
        f"M28CAP|1|HCI_VERSION|nonce={nonce}|hci_version=13|"
        "hci_revision=1|manufacturer=89|lmp_subversion=2",
        f"M28CAP|1|HCI_COMMANDS|nonce={nonce}|commands={commands}",
        f"M28CAP|1|LE_FEATURES|nonce={nonce}|features={features}",
        f"M28CAP|1|RESOURCES|nonce={nonce}|max_adv_data_len=255|"
        "adv_sets=1|per_adv_list=1|resolving_list=1",
        *capability_lines,
        f"M28CAP|1|END|records=12|capabilities=6|nonce={nonce}",
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
        """! @brief PROBE command 전체가 UART에 기록된 것으로 모사합니다. """

        return len(payload)

    def flush(self) -> None:
        """! @brief synthetic UART에는 지연된 출력이 없습니다. """

    def read(self, _size: int) -> bytes:
        """! @brief 항상 빈 입력을 반환합니다. """

        return b""


class M28BleCapabilityParserTests(unittest.TestCase):
    """! @brief canonical PASS와 stale/duplicate/missing/noise/timeout 거부를 고정합니다. """

    def test_canonical_protocol_passes(self) -> None:
        """! @brief 6개 Host/controller capability와 raw HCI 값을 반환합니다. """

        result = MODULE.parse_transcript(transcript(valid_lines()), NONCE, IDENTITY)
        self.assertEqual(len(result.capabilities), 6)
        self.assertEqual(result.maximum_advertising_data_length, 255)
        self.assertEqual(result.identity, IDENTITY)

    def test_ncs_3_4_sdc_command_map_passes(self) -> None:
        """! @brief 실제 SDC 응답에서 optional query bit가 없어도 실제 slot 왕복 결과를 인정합니다. """

        lines = valid_lines()
        commands = (
            "2000800000c000000000040000002802000000000000040000b73fec0f000000"
            "3040797e7efdbf04e00300000000e40300000000000000000000000000000000"
        )
        lines[5] = f"M28CAP|1|HCI_COMMANDS|nonce={NONCE}|commands={commands}"
        lines[6] = f"M28CAP|1|LE_FEATURES|nonce={NONCE}|features=fd71000310190000"
        lines[7] = (
            f"M28CAP|1|RESOURCES|nonce={NONCE}|max_adv_data_len=257|"
            "adv_sets=1|per_adv_list=1|resolving_list=8"
        )

        result = MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

        self.assertEqual(len(result.capabilities), 6)
        self.assertEqual(result.advertising_sets, 1)
        self.assertEqual(result.periodic_advertiser_list_size, 1)

    def test_stale_nonce_is_rejected(self) -> None:
        """! @brief 이전 실행 nonce로 묶인 전체 transcript도 거부합니다. """

        stale = "f" * 32
        with self.assertRaises(MODULE.M28CapabilityFailure):
            MODULE.parse_transcript(transcript(valid_lines(stale)), NONCE, IDENTITY)

    def test_wrong_revision_is_rejected(self) -> None:
        """! @brief 형식이 맞아도 기대 checkout과 다른 image revision을 거부합니다. """

        wrong = MODULE.ExpectedIdentity("a" * 40, IDENTITY.board, IDENTITY.ncs, IDENTITY.zephyr)
        with self.assertRaises(MODULE.M28CapabilityFailure):
            MODULE.parse_transcript(transcript(valid_lines(identity=wrong)), NONCE, IDENTITY)

    def test_noise_line_is_rejected(self) -> None:
        """! @brief protocol prefix가 없는 boot/debug 문자열을 허용하지 않습니다. """

        lines = valid_lines()
        lines.insert(1, "unexpected boot noise")
        with self.assertRaises(MODULE.M28CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_duplicate_record_is_rejected(self) -> None:
        """! @brief 같은 capability record를 추가해 count를 맞출 수 없습니다. """

        lines = valid_lines()
        lines.insert(9, lines[8])
        with self.assertRaises(MODULE.M28CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_missing_record_is_rejected(self) -> None:
        """! @brief 필수 capability 하나가 없으면 END가 있어도 거부합니다. """

        lines = valid_lines()
        del lines[10]
        with self.assertRaises(MODULE.M28CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_raw_feature_mismatch_is_rejected(self) -> None:
        """! @brief CAP 문자열만 PASS인 정적 후보 승격을 raw bit 대조로 거부합니다. """

        lines = valid_lines()
        prefix, _features = lines[6].rsplit("=", 1)
        lines[6] = prefix + "=" + ("0" * 16)
        with self.assertRaises(MODULE.M28CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_resource_shortfall_is_rejected(self) -> None:
        """! @brief 255-byte 광고 또는 controller list 자원이 부족하면 거부합니다. """

        lines = valid_lines()
        lines[7] = lines[7].replace("max_adv_data_len=255", "max_adv_data_len=31")
        with self.assertRaises(MODULE.M28CapabilityFailure):
            MODULE.parse_transcript(transcript(lines), NONCE, IDENTITY)

    def test_target_failure_record_is_rejected(self) -> None:
        """! @brief target query 실패를 정상 transcript로 해석하지 않습니다. """

        lines = valid_lines()
        lines[5] = "M28CAP|1|FAIL|stage=hci_commands|code=-5"
        with self.assertRaises(MODULE.M28CapabilityFailure):
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

    def test_readiness_keeps_source_candidates_separate_from_hci(self) -> None:
        """! @brief target build만으로 readiness의 HCI 상태를 PASS로 바꾸지 않습니다. """

        readiness = json.loads(MODULE.READINESS_PATH.read_text(encoding="utf-8"))
        for capability in readiness["source_capabilities"]:
            self.assertEqual(capability["source_status"], "candidate")
            self.assertEqual(capability["runtime_hci_status"], "not_run")


if __name__ == "__main__":
    unittest.main(verbosity=2)
