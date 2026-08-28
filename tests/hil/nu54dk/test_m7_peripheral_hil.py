"""! @brief NU54DK M7 주변장치 HIL UART transcript parser를 hardware 없이 회귀 검증합니다. """

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("m7_peripheral_hil.py")
MODULE_SPEC = importlib.util.spec_from_file_location("m7_peripheral_hil", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"M7 peripheral HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)


class M7PeripheralHilParserTests(unittest.TestCase):
    """! @brief SPI loopback, ADC와 PWM token의 승인 및 거부 경계를 검증합니다. """

    def test_accepts_fixed_driver_contract(self) -> None:
        """! @brief 정해진 4 MHz SPI, 12-bit ADC와 PWM token을 승인하는지 검증합니다. """

        transcript = (
            b"NUCODE_M7_PERIPHERAL_HIL_READY\r\n"
            b"NUCODE_M7_SPI_LOOPBACK:PASS:frequency=4000000:bytes=40:"
            b"pattern=MUL37_ADD5A\r\n"
            b"NUCODE_M7_ADC_DRIVER:PASS:raw=2048\r\n"
            b"NUCODE_M7_PWM_DRIVER:PASS:duty=0,128,255\r\n"
            b"NUCODE_M7_PERIPHERAL_HIL_PASS\r\n"
        )
        result = MODULE.parse_transcript(transcript)
        self.assertEqual(result.spi_byte_count, 40)
        self.assertEqual(result.adc_raw, 2048)

    def test_rejects_wrong_spi_frequency(self) -> None:
        """! @brief 실제 nRF54L에서 실패한 1 MHz token을 성공 증거로 거부합니다. """

        transcript = (
            b"NUCODE_M7_PERIPHERAL_HIL_READY\n"
            b"NUCODE_M7_SPI_LOOPBACK:PASS:frequency=1000000:bytes=40:"
            b"pattern=MUL37_ADD5A\n"
            b"NUCODE_M7_ADC_DRIVER:PASS:raw=0\n"
            b"NUCODE_M7_PWM_DRIVER:PASS:duty=0,128,255\n"
            b"NUCODE_M7_PERIPHERAL_HIL_PASS\n"
        )
        with self.assertRaisesRegex(ValueError, "4 MHz SPI loopback"):
            MODULE.parse_transcript(transcript)

    def test_rejects_wrong_spi_loopback_byte_count(self) -> None:
        """! @brief 내부 SPI chunk 경계를 넘지 않는 축소 결과를 거부합니다. """

        transcript = (
            b"NUCODE_M7_PERIPHERAL_HIL_READY\n"
            b"NUCODE_M7_SPI_LOOPBACK:PASS:frequency=4000000:bytes=32:"
            b"pattern=MUL37_ADD5A\n"
            b"NUCODE_M7_ADC_DRIVER:PASS:raw=2048\n"
            b"NUCODE_M7_PWM_DRIVER:PASS:duty=0,128,255\n"
            b"NUCODE_M7_PERIPHERAL_HIL_PASS\n"
        )
        with self.assertRaisesRegex(ValueError, "byte 수"):
            MODULE.parse_transcript(transcript)

    def test_rejects_adc_out_of_range(self) -> None:
        """! @brief 12-bit 범위를 벗어난 ADC raw token을 거부하는지 검증합니다. """

        transcript = (
            b"NUCODE_M7_PERIPHERAL_HIL_READY\n"
            b"NUCODE_M7_SPI_LOOPBACK:PASS:frequency=4000000:bytes=40:"
            b"pattern=MUL37_ADD5A\n"
            b"NUCODE_M7_ADC_DRIVER:PASS:raw=4096\n"
            b"NUCODE_M7_PWM_DRIVER:PASS:duty=0,128,255\n"
            b"NUCODE_M7_PERIPHERAL_HIL_PASS\n"
        )
        with self.assertRaisesRegex(ValueError, "12-bit raw"):
            MODULE.parse_transcript(transcript)

    def test_rejects_target_failure_token(self) -> None:
        """! @brief target 최종 FAIL token을 다른 성공 줄과 무관하게 거부합니다. """

        with self.assertRaisesRegex(RuntimeError, "실패"):
            MODULE.parse_transcript(b"NUCODE_M7_PERIPHERAL_HIL_FAIL\r\n")

    def test_rejects_driver_failure_even_with_final_pass(self) -> None:
        """! @brief 잘못된 최종 PASS와 함께 온 개별 driver FAIL도 거부합니다. """

        transcript = (
            b"NUCODE_M7_SPI_DRIVER:FAIL:error=13:driver=-22\r\n"
            b"NUCODE_M7_PERIPHERAL_HIL_PASS\r\n"
        )
        with self.assertRaisesRegex(RuntimeError, "driver 실패"):
            MODULE.parse_transcript(transcript)

    def test_rejects_loopback_failure_even_with_final_pass(self) -> None:
        """! @brief data 불일치를 잘못된 최종 PASS와 무관하게 거부합니다. """

        transcript = (
            b"NUCODE_M7_SPI_LOOPBACK:FAIL:index=3:expected=0xC9:actual=0x00\r\n"
            b"NUCODE_M7_PERIPHERAL_HIL_PASS\r\n"
        )
        with self.assertRaisesRegex(RuntimeError, "loopback 불일치"):
            MODULE.parse_transcript(transcript)


if __name__ == "__main__":
    unittest.main()
