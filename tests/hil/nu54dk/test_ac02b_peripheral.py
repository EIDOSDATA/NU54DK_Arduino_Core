#!/usr/bin/env python3
"""! @brief AC-02B pair HIL parser와 배선 gate를 장치 없이 검증합니다. """

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import inspect
import io
from pathlib import Path
import sys
from types import SimpleNamespace
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


## @brief pySerial ListPortInfo 대역을 생성합니다.
def fake_port(device: str, uid: str, interface_index: int) -> SimpleNamespace:
    return SimpleNamespace(
        device=device,
        serial_number=uid,
        location=f"1-2.3:x.{interface_index}",
        hwid=(
            f"USB VID:PID=0D28:0204 SER={uid} "
            f"LOCATION=1-2.3:x.{interface_index}"
        ),
        vid=MODULE.DAPLINK_VID,
        pid=MODULE.DAPLINK_PID,
    )


## @brief exact DUT 성공 transcript를 생성합니다.
def valid_dut_transcript() -> bytes:
    suffix = f":nonce={NONCE}".encode("ascii")
    lines = (
        b"NUCODE_AC02B_DUT:ARMED:PASS:control=console:serial1=aux-vcom-x.1"
        + suffix,
        b"NUCODE_AC02B_DUT:SERIAL1:PASS:baud=115200:cycles=2:echo=host-vcom-x.1"
        + suffix,
        b"NUCODE_AC02B_DUT:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32:restart=2"
        + suffix,
        b"NUCODE_AC02B_DUT:SPI:PASS:frequency=4000000:bytes=40:interrupt-mask=1"
        + suffix,
        *tuple(
            f"NUCODE_AC02B_RELAY:REQUEST:{command}:nonce={NONCE}".encode(
                "ascii"
            )
            for command, _ in MODULE.RELAY_STEPS[:4]
        ),
        b"NUCODE_AC02B_DUT:PWM:PASS:frequency=1000:duty=25,75" + suffix,
        *tuple(
            f"NUCODE_AC02B_RELAY:REQUEST:{command}:nonce={NONCE}".encode(
                "ascii"
            )
            for command, _ in MODULE.RELAY_STEPS[4:7]
        ),
        b"NUCODE_AC02B_DUT:ADC:PASS:bits=12:low=64:high=3900" + suffix,
        f"NUCODE_AC02B_RELAY:REQUEST:DONE:nonce={NONCE}".encode("ascii"),
        b"NUCODE_AC02B_DUT:FINAL:PASS" + suffix,
    )
    return b"boot\r\n" + b"\r\n".join(lines) + b"\r\n"


## @brief exact peer 성공 transcript를 생성합니다.
def valid_peer_transcript() -> bytes:
    suffix = f":nonce={NONCE}".encode("ascii")
    lines = [
        b"NUCODE_AC02B_PEER:ARMED:PASS:address=0x52:control=host-console"
        + suffix,
        b"NUCODE_AC02B_PEER:UART30:PASS:status=disabled:pins=high-z" + suffix,
        b"NUCODE_AC02B_PEER:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32"
        + suffix,
    ]
    for index, (_, response) in enumerate(MODULE.RELAY_STEPS):
        lines.append(
            f"NUCODE_AC02B_RELAY:RESPONSE:{response}:nonce={NONCE}".encode(
                "ascii"
            )
        )
        if index == 3:
            lines.append(
                b"NUCODE_AC02B_PEER:PWM:PASS:frequency=1000:duty=25,75"
                + suffix
            )
        if index == 5:
            lines.append(
                b"NUCODE_AC02B_PEER:ADC:PASS:levels=0,1" + suffix
            )
    lines.append(b"NUCODE_AC02B_PEER:FINAL:PASS" + suffix)
    return b"boot\n" + b"\n".join(lines) + b"\n"


## @brief exact DUT auxiliary VCOM transcript를 생성합니다.
def valid_auxiliary_transcript() -> bytes:
    return (
        f"S1:{NONCE}:0\r\nS1:{NONCE}:1\r\n".encode("ascii")
    )


## @brief exact host relay audit transcript를 생성합니다.
def valid_relay_transcript() -> bytes:
    lines: list[str] = []
    for cycle in range(2):
        lines.extend(
            (f"AUX:RX:S1:{NONCE}:{cycle}", f"AUX:TX:E1:{NONCE}:{cycle}")
        )
    for command, response in MODULE.RELAY_STEPS:
        request = f"NUCODE_AC02B_RELAY:REQUEST:{command}:nonce={NONCE}"
        reply = f"NUCODE_AC02B_RELAY:RESPONSE:{response}:nonce={NONCE}"
        lines.extend(
            (
                f"DUT:RX:{request}",
                f"PEER:TX:{request}",
                f"PEER:RX:{reply}",
                f"DUT:TX:{reply}",
            )
        )
    return ("\n".join(lines) + "\n").encode("ascii")


class Ac02bPeripheralParserTests(unittest.TestCase):
    """! @brief nonce, exact 순서, 계측 범위와 수동 배선 경계를 고정합니다. """

    def test_accepts_complete_dut_and_peer_protocol(self) -> None:
        """! @brief 두 role의 완전한 exact protocol만 승인합니다. """

        dut = MODULE.parse_dut_transcript(valid_dut_transcript(), NONCE)
        peer = MODULE.parse_peer_transcript(valid_peer_transcript(), NONCE)
        auxiliary = MODULE.parse_auxiliary_transcript(
            valid_auxiliary_transcript(), NONCE
        )
        relay = MODULE.parse_relay_transcript(valid_relay_transcript(), NONCE)
        self.assertEqual(dut.adc_low, 64)
        self.assertEqual(dut.adc_high, 3900)
        self.assertEqual(dut.wire_clocks, (100000, 400000))
        self.assertEqual(peer.target_address, 0x52)
        self.assertEqual(peer.wire_bytes, 32)
        self.assertEqual(peer.uart30_state, "disabled-high-z")
        self.assertEqual(auxiliary.cycles, (0, 1))
        self.assertEqual(relay.commands, len(MODULE.RELAY_STEPS))

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

    def test_auxiliary_and_relay_are_nonce_order_fail_closed(self) -> None:
        """! @brief x.1 frame와 host relay의 stale·재배치·추가 line을 거부합니다. """

        reordered_aux = valid_auxiliary_transcript().replace(
            b":0\r\nS1:", b":1\r\nS1:", 1
        )
        with self.assertRaisesRegex(MODULE.Ac02bHilFailure, "순서/nonce"):
            MODULE.parse_auxiliary_transcript(reordered_aux, NONCE)

        stale_relay = valid_relay_transcript().replace(
            NONCE.encode("ascii"), b"f" * 32, 1
        )
        with self.assertRaisesRegex(MODULE.Ac02bHilFailure, "relay"):
            MODULE.parse_relay_transcript(stale_relay, NONCE)

        extra_aux = valid_auxiliary_transcript() + b"S1:unexpected:2\r\n"
        with self.assertRaises(MODULE.Ac02bHilFailure):
            MODULE.parse_auxiliary_transcript(extra_aux, NONCE)

    def test_auxiliary_ignores_only_non_protocol_startup_noise(self) -> None:
        """! @brief x.1 UARTE 기동 잡음은 보존하되 S1 계약에는 포함하지 않습니다. """

        noisy = b"\xff\xcb\xb7\xeb\x84" + valid_auxiliary_transcript()
        result = MODULE.parse_auxiliary_transcript(noisy, NONCE)
        self.assertEqual(result.cycles, (0, 1))

        stale = noisy.replace(NONCE.encode("ascii"), b"f" * 32, 1)
        with self.assertRaisesRegex(MODULE.Ac02bHilFailure, "순서/nonce"):
            MODULE.parse_auxiliary_transcript(stale, NONCE)

    def test_selects_exact_uid_x1_and_x3_only(self) -> None:
        """! @brief 같은 UID의 console x.3과 auxiliary x.1을 혼동하지 않습니다. """

        uid = "a" * 32
        other_uid = "b" * 32
        ports = SimpleNamespace(
            comports=lambda: [
                fake_port("COM10", uid, 1),
                fake_port("COM11", uid, 3),
                fake_port("COM12", other_uid, 1),
                fake_port("COM13", other_uid, 3),
            ]
        )
        self.assertEqual(
            MODULE.find_uid_interface_port(uid, 1, "auto", ports), "COM10"
        )
        self.assertEqual(
            MODULE.find_uid_interface_port(uid, 3, "auto", ports), "COM11"
        )
        with self.assertRaisesRegex(MODULE.Ac02bHilFailure, "interface=x.1"):
            MODULE.find_uid_interface_port(uid, 1, "COM11", ports)
        with self.assertRaisesRegex(MODULE.Ac02bHilFailure, "UID/interface"):
            MODULE.find_uid_interface_port(uid, 1, "COM12", ports)

    def test_runtime_ports_are_rediscovered_after_both_flashes(self) -> None:
        """! @brief execute가 flash 뒤 exact UID COM을 재탐색한 후에만 엽니다. """

        source = inspect.getsource(MODULE.execute_ac02b)
        peer_flash = source.index('MILESTONE, "peer"')
        dut_flash = source.index('MILESTONE, "dut"')
        rediscover = source.index("rediscover_runtime_ports(")
        serial_open = source.index("serial_module.Serial(")
        self.assertLess(peer_flash, rediscover)
        self.assertLess(dut_flash, rediscover)
        self.assertLess(rediscover, serial_open)
        self.assertIn("runtime_ports.dut_auxiliary", source)

    def test_requires_two_distinct_board_ids(self) -> None:
        """! @brief DUT와 peer UID 인자를 생략할 수 없게 고정합니다. """

        with self.assertRaises(SystemExit):
            MODULE.parse_arguments([])
        arguments = MODULE.parse_arguments(
            ["--dut-board-id", "dut", "--peer-board-id", "peer"]
        )
        self.assertFalse(arguments.acknowledge_wiring)
        self.assertEqual(arguments.dut_port, "auto")
        self.assertEqual(arguments.dut_aux_port, "auto")
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
            "COM43",
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

    def test_peer_uses_console_only_and_uart30_is_high_z(self) -> None:
        """! @brief peer P0 UART를 disabled하고 host console RX만 사용하게 고정합니다. """

        peer_root = MODULE.REPOSITORY / "tests" / "zephyr" / "ac02b_hil_peer"
        configuration = (peer_root / "prj.conf").read_text(encoding="utf-8")
        source = (peer_root / "src" / "main.cpp").read_text(encoding="utf-8")
        overlay = (peer_root / "app.overlay").read_text(encoding="utf-8")
        self.assertIn("CONFIG_UART_INTERRUPT_DRIVEN=y", configuration)
        self.assertIn("uart_irq_callback_user_data_set", source)
        self.assertIn("startUartRx(console_uart, console_rx_context)", source)
        self.assertIn("readQueuedLine(console_rx_context, command", source)
        self.assertNotIn("peer_uart", source)
        self.assertNotIn("peer_rx_queue", source)
        self.assertNotIn("DEVICE_DT_GET(DT_NODELABEL(uart30))", source)
        self.assertIn("!DT_NODE_HAS_STATUS(DT_NODELABEL(uart30), okay)", source)
        self.assertIn('&uart30 {', overlay)
        self.assertIn('status = "disabled";', overlay)
        self.assertIn("/delete-property/ pinctrl-0;", overlay)

    def test_peer_prepares_twis_read_before_write_done(self) -> None:
        """! @brief repeated-start의 READ_REQ/WRITE_DONE 순서에 의존하지 않게 고정합니다. """

        source = (
            MODULE.REPOSITORY
            / "tests"
            / "zephyr"
            / "ac02b_hil_peer"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        callback = source.split("int targetBufferReadRequested", maxsplit=1)[1].split(
            "/** @brief P1.14", maxsplit=1
        )[0]
        self.assertIn("*data = i2c_response_payload;", callback)
        self.assertIn("*size = sizeof(i2c_response_payload);", callback)
        self.assertNotIn("i2c_valid_write_count", callback)
        self.assertIn("targetBufferWriteReceived() 및 최종 판정에서 검증", source)

    def test_dut_serial1_failure_is_stage_specific(self) -> None:
        """! @brief Serial1 물리 실패가 route·echo·lifecycle 단계로 구분되게 고정합니다. """

        source = (
            MODULE.REPOSITORY
            / "tests"
            / "zephyr"
            / "ac02b_hil_dut"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for stage in (
            "serial1-set-pins",
            "serial1-begin",
            "serial1-active-route",
            "serial1-frame",
            "serial1-echo",
            "serial1-end",
            "serial1-restage",
        ):
            self.assertIn(stage, source)
        self.assertIn("reportFailure(serial1_failure_stage)", source)
        self.assertIn("echo=host-vcom-x.1", source)
        self.assertNotIn("sendPeerLine", source)

    def test_dut_preserves_wire_driver_error_before_end(self) -> None:
        """! @brief Wire.end()가 진단을 지우기 전에 backend 오류를 보존하게 고정합니다. """

        source = (
            MODULE.REPOSITORY
            / "tests"
            / "zephyr"
            / "ac02b_hil_dut"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        request_failure = source.split(
            'wire_failure_stage = "wire-request";', maxsplit=1
        )[1].split("return false;", maxsplit=1)[0]
        self.assertIn("lastWireError()", request_failure)
        self.assertIn("lastWireDriverError()", request_failure)
        self.assertIn('Serial.print(":wire-error=");', source)
        self.assertIn('Serial.print(":driver=");', source)

    def test_dut_wire_failure_is_stage_specific(self) -> None:
        """! @brief Wire 물리 실패가 route·restart·read 단계로 구분되게 고정합니다. """

        source = (
            MODULE.REPOSITORY
            / "tests"
            / "zephyr"
            / "ac02b_hil_dut"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for stage in (
            "wire-set-pins",
            "wire-begin",
            "wire-active-route",
            "wire-clock",
            "wire-write",
            "wire-pending-restart",
            "wire-request",
            "wire-read",
            "wire-final-state",
            "wire-end",
        ):
            self.assertIn(stage, source)
        self.assertIn("reportFailure(wire_failure_stage)", source)


if __name__ == "__main__":
    unittest.main()
