"""! @brief M7 고정 0x6B WHO_AM_I host protocol을 hardware 없이 회귀 검증합니다. """

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("m7_i2c_imu.py")
MODULE_SPEC = importlib.util.spec_from_file_location("m7_i2c_imu", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"M7 HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)


class FakeSerialPort:
    """! @brief READY와 고정 result를 순서대로 제공하는 최소 UART fake입니다. """

    def __init__(self, response: bytes):
        """! @brief 지정한 target 응답으로 UART fake를 초기화합니다. """

        self._response = bytearray(response)
        self.written = bytearray()
        self.reset_called = False

    def __enter__(self) -> "FakeSerialPort":
        """! @brief context manager 진입 시 같은 UART fake를 반환합니다. """

        return self

    def __exit__(self, *_: object) -> None:
        """! @brief context manager 종료 시 별도 자원을 해제하지 않습니다. """

        return None

    @property
    def in_waiting(self) -> int:
        """! @brief 아직 읽지 않은 fake 수신 byte 수를 반환합니다. """

        return len(self._response)

    def read(self, size: int) -> bytes:
        """! @brief 요청한 크기만큼 fake 수신 byte를 소비합니다. """

        count = min(size, len(self._response))
        data = bytes(self._response[:count])
        del self._response[:count]
        return data

    def write(self, data: bytes) -> int:
        """! @brief host가 보낸 byte를 기록하고 전체 길이를 반환합니다. """

        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        """! @brief 동기 fake에서는 별도 flush 동작을 수행하지 않습니다. """

        return None

    def reset_input_buffer(self) -> None:
        """! @brief 입력 초기화 호출 여부만 기록합니다. """

        self.reset_called = True


class FakeSerialModule:
    """! @brief pySerial 상수와 하나의 FakeSerialPort를 제공합니다. """

    EIGHTBITS = 8
    PARITY_NONE = "N"
    STOPBITS_ONE = 1

    def __init__(self, port: FakeSerialPort):
        """! @brief Serial 생성 시 반환할 고정 UART fake를 보존합니다. """

        self._port = port

    def Serial(self, **_: object) -> FakeSerialPort:
        """! @brief pySerial 호환 생성자 표면으로 고정 UART fake를 반환합니다. """

        return self._port


class M7I2cImuProtocolTests(unittest.TestCase):
    """! @brief 고정 주소·register·WHO_AM_I와 host 송신 계약을 검증합니다. """

    def test_valid_result(self) -> None:
        """! @brief 승인된 0x6B/0x0F/0x6A repeated-start 결과를 검증합니다. """

        result = MODULE.parse_result_line(MODULE.RESULT_TOKEN)
        self.assertEqual(result.address, 0x6B)
        self.assertEqual(result.register, 0x0F)
        self.assertEqual(result.value, 0x6A)
        self.assertTrue(result.repeated_start)

    def test_rejects_forbidden_0x6a_address(self) -> None:
        """! @brief HIL fixture가 금지한 0x6A target 주소를 거부하는지 검증합니다. """

        with self.assertRaisesRegex(ValueError, "승인되지 않은 I2C 주소"):
            MODULE.parse_result_line(b"NUCODE_M7_I2C_RESULT:6A:0F:6A:RS\r\n")

    def test_rejects_wrong_register_value_and_transfer_form(self) -> None:
        """! @brief 잘못된 register, 값과 transfer 형식을 모두 거부하는지 검증합니다. """

        invalid_lines = (
            b"NUCODE_M7_I2C_RESULT:6B:10:6A:RS\r\n",
            b"NUCODE_M7_I2C_RESULT:6B:0F:6B:RS\r\n",
            b"NUCODE_M7_I2C_RESULT:6B:0F:6A:STOP\r\n",
        )
        for line in invalid_lines:
            with self.subTest(line=line), self.assertRaises(ValueError):
                MODULE.parse_result_line(line)

    def test_fake_uart_sends_only_fixed_request(self) -> None:
        """! @brief host가 고정된 안전 요청 한 종류만 송신하는지 검증합니다. """

        fake_port = FakeSerialPort(MODULE.READY_TOKEN + MODULE.RESULT_TOKEN)
        fake_module = FakeSerialModule(fake_port)

        sequence, byte_count, result = MODULE.verify_i2c_whoami(
            serial_module=fake_module,
            port_name="COM-FAKE",
            baud_rate=115200,
            flash_callback=lambda: ("42", "1234"),
            ready_timeout=0.5,
            result_timeout=0.5,
        )

        self.assertTrue(fake_port.reset_called)
        self.assertEqual(bytes(fake_port.written), MODULE.REQUEST_TOKEN)
        self.assertEqual(sequence, "42")
        self.assertEqual(byte_count, "1234")
        self.assertEqual(result.address, 0x6B)

    def test_cli_surface_has_no_address_register_or_scan_option(self) -> None:
        """! @brief CLI에 임의 주소·register·scan 진입점이 없는지 검증합니다. """

        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in ("--address", "--register", "--expected", "--scan"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
