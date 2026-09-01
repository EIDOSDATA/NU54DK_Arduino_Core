#!/usr/bin/env python3
"""! @brief AC-02B pair HIL parser와 배선 gate를 장치 없이 검증합니다. """

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("ac02b_peripheral.py")
MODULE_SPEC = importlib.util.spec_from_file_location("ac02b_peripheral", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"AC-02B HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)

NONCE = "0123456789abcdef0123456789abcdef"


## @brief exact DUT 성공 transcript를 생성합니다.
def valid_dut_transcript() -> bytes:
    suffix = f":nonce={NONCE}".encode("ascii")
    lines = (
        b"NUCODE_AC02B_READY:role=dut",
        b"NUCODE_AC02B_DUT:SERIAL1:PASS:baud=115200:cycles=2:bytes=64" + suffix,
        b"NUCODE_AC02B_DUT:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32:restart=2"
        + suffix,
        b"NUCODE_AC02B_DUT:SPI:PASS:frequency=4000000:bytes=40:interrupt-mask=1"
        + suffix,
        b"NUCODE_AC02B_DUT:PWM:PASS:frequency=1000:duty=25,75" + suffix,
        b"NUCODE_AC02B_DUT:ADC:PASS:bits=12:low=64:high=3900" + suffix,
        b"NUCODE_AC02B_DUT:FINAL:PASS" + suffix,
    )
    return b"boot\r\n" + b"\r\n".join(lines) + b"\r\n"


## @brief exact peer 성공 transcript를 생성합니다.
def valid_peer_transcript() -> bytes:
    suffix = f":nonce={NONCE}".encode("ascii")
    lines = (
        b"NUCODE_AC02B_READY:role=peer",
        b"NUCODE_AC02B_PEER:ARMED:PASS:address=0x52" + suffix,
        b"NUCODE_AC02B_PEER:SERIAL1:PASS:baud=115200:cycles=2:bytes=64" + suffix,
        b"NUCODE_AC02B_PEER:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32"
        + suffix,
        b"NUCODE_AC02B_PEER:PWM:PASS:frequency=1000:duty=25,75" + suffix,
        b"NUCODE_AC02B_PEER:ADC:PASS:levels=0,1" + suffix,
        b"NUCODE_AC02B_PEER:FINAL:PASS" + suffix,
    )
    return b"boot\n" + b"\n".join(lines) + b"\n"


class Ac02bPeripheralParserTests(unittest.TestCase):
    """! @brief nonce, exact 순서, 계측 범위와 수동 배선 경계를 고정합니다. """

    def test_accepts_complete_dut_and_peer_protocol(self) -> None:
        """! @brief 두 role의 완전한 exact protocol만 승인합니다. """

        dut = MODULE.parse_dut_transcript(valid_dut_transcript(), NONCE)
        peer = MODULE.parse_peer_transcript(valid_peer_transcript(), NONCE)
        self.assertEqual(dut.adc_low, 64)
        self.assertEqual(dut.adc_high, 3900)
        self.assertEqual(dut.wire_clocks, (100000, 400000))
        self.assertEqual(peer.target_address, 0x52)
        self.assertEqual(peer.wire_bytes, 32)

    def test_rejects_stale_nonce_and_target_fail(self) -> None:
        """! @brief stale nonce 또는 FAIL이 다른 PASS와 섞여도 거부합니다. """

        stale = valid_dut_transcript().replace(
            NONCE.encode("ascii"), b"f" * 32, 1
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "stale"):
            MODULE.parse_dut_transcript(stale, NONCE)

        failed = valid_peer_transcript() + (
            f"NUCODE_AC02B_FAIL:role=peer:stage=wire:nonce={NONCE}\n".encode(
                "ascii"
            )
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "실패"):
            MODULE.parse_peer_transcript(failed, NONCE)

    def test_rejects_reorder_missing_and_extra_token(self) -> None:
        """! @brief 단계 재배치, 누락과 FINAL 뒤 추가 token을 모두 거부합니다. """

        reordered = valid_dut_transcript().replace(
            b"NUCODE_AC02B_DUT:WIRE", b"TEMP_AC02B_DUT:WIRE", 1
        ).replace(
            b"NUCODE_AC02B_DUT:SPI", b"NUCODE_AC02B_DUT:WIRE", 1
        ).replace(
            b"TEMP_AC02B_DUT:WIRE", b"NUCODE_AC02B_DUT:SPI", 1
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "순서"):
            MODULE.parse_dut_transcript(reordered, NONCE)

        missing = valid_peer_transcript().replace(
            b"NUCODE_AC02B_PEER:PWM:PASS:frequency=1000:duty=25,75:nonce="
            + NONCE.encode("ascii")
            + b"\n",
            b"",
        )
        with self.assertRaises(MODULE.BlePairHilFailure):
            MODULE.parse_peer_transcript(missing, NONCE)

        extra = valid_peer_transcript() + (
            f"NUCODE_AC02B_PEER:ADC:PASS:levels=0,1:nonce={NONCE}\n".encode(
                "ascii"
            )
        )
        with self.assertRaisesRegex(MODULE.BlePairHilFailure, "FINAL 뒤"):
            MODULE.parse_peer_transcript(extra, NONCE)

    def test_rejects_adc_that_does_not_prove_external_levels(self) -> None:
        """! @brief raw 범위 안이더라도 LOW/HIGH 분리가 부족하면 거부합니다. """

        high_too_low = valid_dut_transcript().replace(b"high=3900", b"high=2048")
        with self.assertRaisesRegex(MODULE.Ac02bHilFailure, "ADC LOW/HIGH"):
            MODULE.parse_dut_transcript(high_too_low, NONCE)

        low_too_high = valid_dut_transcript().replace(b"low=64", b"low=500")
        with self.assertRaisesRegex(MODULE.Ac02bHilFailure, "ADC LOW/HIGH"):
            MODULE.parse_dut_transcript(low_too_high, NONCE)

    def test_requires_two_distinct_board_ids(self) -> None:
        """! @brief DUT와 peer UID 인자를 생략할 수 없게 고정합니다. """

        with self.assertRaises(SystemExit):
            MODULE.parse_arguments([])
        arguments = MODULE.parse_arguments(
            ["--dut-board-id", "dut", "--peer-board-id", "peer"]
        )
        self.assertFalse(arguments.acknowledge_wiring)
        self.assertEqual(arguments.dut_port, "auto")
        self.assertEqual(arguments.peer_port, "auto")

    def test_rejects_shared_uid_msd_or_com_identity(self) -> None:
        """! @brief 두 role의 UID·MSD·COM 중 하나라도 같으면 거부합니다. """

        dut = MODULE.RoleEndpoint(
            "uid-a", mock.Mock(root=Path("C:/ac02b/dut")), "COM41"
        )
        valid_peer = MODULE.RoleEndpoint(
            "uid-b", mock.Mock(root=Path("C:/ac02b/peer")), "COM42"
        )
        MODULE.validate_pair_identity(dut, valid_peer)

        collisions = (
            MODULE.RoleEndpoint(
                "uid-a", mock.Mock(root=Path("C:/ac02b/peer")), "COM42"
            ),
            MODULE.RoleEndpoint(
                "uid-b", mock.Mock(root=Path("C:/ac02b/dut")), "COM42"
            ),
            MODULE.RoleEndpoint(
                "uid-b", mock.Mock(root=Path("C:/ac02b/peer")), "com41"
            ),
        )
        for peer in collisions:
            with self.assertRaises(MODULE.BlePairHilFailure):
                MODULE.validate_pair_identity(dut, peer)

    def test_wiring_gate_stops_before_flash_and_evidence(self) -> None:
        """! @brief 승인 없는 preflight는 execute/증적 생성 없이 code 3으로 멈춥니다. """

        fake_preflight = (
            mock.sentinel.dut_endpoint,
            mock.sentinel.peer_endpoint,
            Path("dut.hex"),
            Path("peer.hex"),
            "0" * 40,
            "1" * 40,
            {},
            {},
        )
        with mock.patch.object(
            MODULE, "import_pyserial", return_value=(mock.sentinel.serial, mock.sentinel.ports)
        ), mock.patch.object(MODULE, "preflight", return_value=fake_preflight), mock.patch.object(
            MODULE, "execute_ac02b"
        ) as execute, mock.patch.object(MODULE, "prepare_output_paths") as outputs, redirect_stdout(
            io.StringIO()
        ) as captured:
            result = MODULE.main(
                ["--dut-board-id", "dut", "--peer-board-id", "peer"]
            )
        self.assertEqual(result, MODULE.WIRING_REQUIRED_EXIT_CODE)
        self.assertIn("WIRING_REQUIRED", captured.getvalue())
        execute.assert_not_called()
        outputs.assert_not_called()

    def test_role_images_are_build_only_in_twister(self) -> None:
        """! @brief READY 한 줄이 물리 HIL PASS로 오인되지 않도록 고정합니다. """

        repository = MODULE.REPOSITORY
        for role in ("ac02b_hil_dut", "ac02b_hil_peer"):
            metadata = (
                repository / "tests" / "zephyr" / role / "testcase.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("build_only: true", metadata)
            self.assertNotIn("harness: console", metadata)


if __name__ == "__main__":
    unittest.main()
