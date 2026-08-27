/**
 * @file main.cpp
 * @brief M7 실제 SPI loopback, ADC와 PWM driver 검증 결과를 UART token으로 보고합니다.
 *
 * @note 이 시험은 ADC 전압 정확도 또는 PWM 외부 파형을 검증하지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <SPI.h>

#include <cstddef>
#include <cstdint>

#include "internal/AnalogBackend.h"
#include "internal/SPIBackend.h"

namespace
{
	using nucode::arduino::internal::AnalogError;
	using nucode::arduino::internal::lastAnalogDriverError;
	using nucode::arduino::internal::lastAnalogError;
	using nucode::arduino::internal::lastSpiDriverError;
	using nucode::arduino::internal::lastSpiError;
	using nucode::arduino::internal::SpiError;

	/** @brief 실제 SPI buffer chunk 경계를 통과할 loopback byte 수입니다. */
	constexpr std::size_t spi_loopback_byte_count = 40U;

	/**
	 * @brief loopback 위치마다 재현 가능한 고정 시험 byte를 생성합니다.
	 *
	 * @param index 0부터 시작하는 buffer 위치입니다.
	 * @return 해당 위치에서 송신하고 다시 수신해야 하는 byte입니다.
	 */
	constexpr std::uint8_t spiPatternByte(std::size_t index)
	{
		return static_cast<std::uint8_t>((index * 37U) + 0x5AU);
	}

	/** @brief SPI driver 실패 상태와 원본 Zephyr 오류를 UART에 기록합니다. */
	void reportSpiFailure(void)
	{
		Serial.print("NUCODE_M7_SPI_DRIVER:FAIL:error=");
		Serial.print(static_cast<unsigned int>(lastSpiError()));
		Serial.print(":driver=");
		Serial.println(lastSpiDriverError());
	}

	/** @brief ADC/PWM 실패 상태와 원본 Zephyr 오류를 UART에 기록합니다. */
	void reportAnalogFailure(const char *prefix)
	{
		Serial.print(prefix);
		Serial.print(":FAIL:error=");
		Serial.print(static_cast<unsigned int>(lastAnalogError()));
		Serial.print(":driver=");
		Serial.println(lastAnalogDriverError());
	}

	/**
	 * @brief CS 없는 실제 spi00에서 4 MHz, 40-byte 물리 loopback을 실행합니다.
	 *
	 * @return driver가 성공하고 모든 수신 byte가 송신 byte와 같으면 true입니다.
	 */
	bool testSpiLoopback(void)
	{
		std::uint8_t frame[spi_loopback_byte_count] = {};
		for (std::size_t index = 0U; index < spi_loopback_byte_count; ++index)
		{
			frame[index] = spiPatternByte(index);
		}

		SPI.begin();
		if (lastSpiError() != SpiError::none)
		{
			reportSpiFailure();
			return false;
		}

		SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
		if (lastSpiError() != SpiError::none)
		{
			reportSpiFailure();
			return false;
		}

		SPI.transfer(frame, sizeof(frame));
		if (lastSpiError() != SpiError::none)
		{
			reportSpiFailure();
			SPI.endTransaction();
			return false;
		}

		SPI.endTransaction();
		if (lastSpiError() != SpiError::none)
		{
			reportSpiFailure();
			return false;
		}

		for (std::size_t index = 0U; index < spi_loopback_byte_count; ++index)
		{
			const std::uint8_t expected = spiPatternByte(index);
			if (frame[index] != expected)
			{
				Serial.print("NUCODE_M7_SPI_LOOPBACK:FAIL:index=");
				Serial.print(static_cast<unsigned int>(index));
				Serial.print(":expected=0x");
				Serial.print(expected, HEX);
				Serial.print(":actual=0x");
				Serial.println(frame[index], HEX);
				return false;
			}
		}

		Serial.println(
			"NUCODE_M7_SPI_LOOPBACK:PASS:frequency=4000000:bytes=40:pattern=MUL37_ADD5A");
		return true;
	}

	/**
	 * @brief 실제 A0 channel에서 12-bit raw ADC driver read를 한 번 실행합니다.
	 *
	 * @return driver가 성공하고 반환값이 0..4095이면 true입니다.
	 */
	bool testAdcDriver(void)
	{
		analogReference(AR_DEFAULT);
		if (lastAnalogError() != AnalogError::none)
		{
			reportAnalogFailure("NUCODE_M7_ADC_DRIVER");
			return false;
		}

		const int raw = analogRead(A0);
		if ((lastAnalogError() != AnalogError::none) || (raw < 0) || (raw > 4095))
		{
			reportAnalogFailure("NUCODE_M7_ADC_DRIVER");
			return false;
		}

		Serial.print("NUCODE_M7_ADC_DRIVER:PASS:raw=");
		Serial.println(raw);
		return true;
	}

	/**
	 * @brief 실제 pwm_led1에 0, 128과 255 duty driver 요청을 순서대로 전달합니다.
	 *
	 * @return 세 PWM driver 호출이 모두 성공하면 true입니다.
	 */
	bool testPwmDriver(void)
	{
		constexpr int duty_values[] = {0, 128, 255};
		for (const int duty : duty_values)
		{
			analogWrite(PIN_PWM0, duty);
			if (lastAnalogError() != AnalogError::none)
			{
				reportAnalogFailure("NUCODE_M7_PWM_DRIVER");
				return false;
			}
		}

		Serial.println("NUCODE_M7_PWM_DRIVER:PASS:duty=0,128,255");
		return true;
	}
}

/** @brief 실제 주변장치 driver 시험을 한 번 실행하고 최종 결과 token을 출력합니다. */
void setup(void)
{
	Serial.begin(115200U);
	Serial.println("NUCODE_M7_PERIPHERAL_HIL_READY");

	const bool spi_ok = testSpiLoopback();
	const bool adc_ok = testAdcDriver();
	const bool pwm_ok = testPwmDriver();
	Serial.println((spi_ok && adc_ok && pwm_ok)
		? "NUCODE_M7_PERIPHERAL_HIL_PASS"
		: "NUCODE_M7_PERIPHERAL_HIL_FAIL");
}

/** @brief 단발성 driver 시험 뒤 추가 주변장치 접근 없이 대기합니다. */
void loop(void)
{
	delay(1000U);
}
