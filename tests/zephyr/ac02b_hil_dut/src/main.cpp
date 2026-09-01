/**
 * @file main.cpp
 * @brief 두 NU54DK를 사용하는 AC-02B DUT 주변장치 HIL을 실행합니다.
 *
 * @note 실제 실행에는 README에 명시된 보드 간 배선과 동일 nonce를 주입하는
 * host runner가 필요합니다. 독립적으로 부팅한 이미지는 READY 뒤 대기하며 PASS를
 * 스스로 만들지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <cstddef>
#include <cstdint>

#include "internal/AnalogBackend.h"
#include "internal/SPIBackend.h"
#include "internal/SerialBackend.h"
#include "internal/WireBackend.h"
#include "internal/pin_description.h"

namespace
{
	using nucode::arduino::internal::AnalogError;
	using nucode::arduino::internal::GpioError;
	using nucode::arduino::internal::SerialError;
	using nucode::arduino::internal::SpiError;
	using nucode::arduino::internal::WireError;

	/** @brief host가 양쪽 role에 결합하는 nonce의 ASCII 길이입니다. */
	constexpr std::size_t nonce_length = 32U;

	/** @brief 한 UART protocol line의 최대 길이입니다. */
	constexpr std::size_t line_capacity = 96U;

	/** @brief 모든 peer 응답의 제한 시간입니다. */
	constexpr unsigned long response_timeout_ms = 5000UL;

	/** @brief I2C target 시험 주소입니다. 보드 PMIC의 0x6A와 겹치지 않습니다. */
	constexpr std::uint8_t i2c_target_address = 0x52U;

	/** @brief SPI chunk 경계를 넘기는 loopback byte 수입니다. */
	constexpr std::size_t spi_byte_count = 40U;

	/** @brief 현재 실행에 결합된 128-bit nonce입니다. */
	char active_nonce[nonce_length + 1U]{};

	/** @brief 단발 실행이 끝났는지 나타냅니다. */
	bool execution_finished = false;

	/** @brief Serial1 실패의 가장 구체적인 단계를 보존합니다. */
	const char *serial1_failure_stage = "serial1-unknown";

	/** @brief SPI interrupt mask fixture용 callback입니다. 실제 edge는 만들지 않습니다. */
	void spiMaskFixtureCallback(void)
	{
	}

	/** @brief 문자가 소문자 16진수인지 확인합니다. */
	[[nodiscard]] bool isLowerHex(char value)
	{
		return ((value >= '0') && (value <= '9')) ||
			   ((value >= 'a') && (value <= 'f'));
	}

	/** @brief 정확히 32자리인 소문자 hex nonce를 검증합니다. */
	[[nodiscard]] bool validNonce(const char *nonce)
	{
		if ((nonce == nullptr) || (strlen(nonce) != nonce_length))
		{
			return false;
		}
		for (std::size_t index = 0U; index < nonce_length; ++index)
		{
			if (!isLowerHex(nonce[index]))
			{
				return false;
			}
		}
		return true;
	}

	/** @brief hex 문자 하나를 4-bit 값으로 변환합니다. */
	[[nodiscard]] std::uint8_t hexNibble(char value)
	{
		return static_cast<std::uint8_t>(
			(value <= '9') ? value - '0' : value - 'a' + 10);
	}

	/** @brief nonce를 I2C payload 16 byte로 변환합니다. */
	void noncePayload(std::uint8_t (&payload)[16])
	{
		for (std::size_t index = 0U; index < sizeof(payload); ++index)
		{
			payload[index] = static_cast<std::uint8_t>(
				(hexNibble(active_nonce[index * 2U]) << 4U) |
				hexNibble(active_nonce[(index * 2U) + 1U]));
		}
	}

	/**
	 * @brief Stream에서 CR을 제거한 bounded line 하나를 읽습니다.
	 *
	 * @return newline까지 읽고 NUL 종료했으면 true입니다.
	 */
	template <typename StreamType>
	[[nodiscard]] bool readLine(StreamType &stream, char *output,
								std::size_t capacity, unsigned long timeout_ms)
	{
		if ((output == nullptr) || (capacity < 2U))
		{
			return false;
		}
		const unsigned long started_at = millis();
		std::size_t length = 0U;
		while ((millis() - started_at) < timeout_ms)
		{
			while (stream.available() > 0)
			{
				const int value = stream.read();
				if (value < 0)
				{
					break;
				}
				if (value == '\r')
				{
					continue;
				}
				if (value == '\n')
				{
					output[length] = '\0';
					return length > 0U;
				}
				if ((length + 1U) >= capacity)
				{
					return false;
				}
				output[length++] = static_cast<char>(value);
			}
			delay(1U);
		}
		return false;
	}

	/** @brief 현재 nonce와 결합된 fail-closed token을 출력합니다. */
	void reportFailure(const char *stage)
	{
		Serial.print("NUCODE_AC02B_FAIL:role=dut:stage=");
		Serial.print(stage);
		Serial.print(":nonce=");
		Serial.println(validNonce(active_nonce) ? active_nonce
												: "00000000000000000000000000000000");
	}

	/** @brief 현재 nonce suffix를 protocol token에 추가합니다. */
	void finishToken(void)
	{
		Serial.print(":nonce=");
		Serial.println(active_nonce);
	}

	/** @brief Serial1 peer로 control line을 전송합니다. */
	void sendPeerLine(const char *line)
	{
		Serial1.println(line);
		Serial1.flush();
	}

	/** @brief Serial1 peer 응답이 exact line인지 확인합니다. */
	[[nodiscard]] bool expectPeerLine(const char *expected)
	{
		char observed[line_capacity]{};
		return readLine(Serial1, observed, sizeof(observed), response_timeout_ms) &&
			   (strcmp(observed, expected) == 0);
	}

	/** @brief uart30의 active route 거부와 end/rebegin 두 cycle echo를 검증합니다. */
	[[nodiscard]] bool testSerial1(void)
	{
		if (!Serial1.setPins(PIN_P0_01, PIN_P0_00))
		{
			serial1_failure_stage = "serial1-set-pins";
			return false;
		}
		for (unsigned int cycle = 0U; cycle < 2U; ++cycle)
		{
			Serial1.begin(115200U, SERIAL_8N1);
			if (!Serial1 ||
				(nucode::arduino::internal::lastSerial1Error() != SerialError::none))
			{
				serial1_failure_stage = "serial1-begin";
				return false;
			}
			if (Serial1.setPins(PIN_P0_01, PIN_P0_00))
			{
				serial1_failure_stage = "serial1-active-route";
				return false;
			}

			char frame[line_capacity]{};
			const int count = snprintf(frame, sizeof(frame), "S1:%s:%u",
									   active_nonce, cycle);
			if ((count <= 0) || (static_cast<std::size_t>(count) >= sizeof(frame)))
			{
				serial1_failure_stage = "serial1-frame";
				return false;
			}
			Serial1.println(frame);
			Serial1.flush();

			char expected[line_capacity]{};
			const int expected_count = snprintf(expected, sizeof(expected),
												"E1:%s:%u", active_nonce, cycle);
			if ((expected_count <= 0) ||
				(static_cast<std::size_t>(expected_count) >= sizeof(expected)) ||
				!expectPeerLine(expected))
			{
				serial1_failure_stage = "serial1-echo";
				return false;
			}
			Serial1.end();
			if (nucode::arduino::internal::lastSerial1Error() != SerialError::none)
			{
				serial1_failure_stage = "serial1-end";
				return false;
			}
			if ((cycle + 1U) < 2U && !Serial1.setPins(PIN_P0_01, PIN_P0_00))
			{
				serial1_failure_stage = "serial1-restage";
				return false;
			}
		}

		Serial1.begin(115200U, SERIAL_8N1);
		if (!Serial1)
		{
			serial1_failure_stage = "serial1-final-begin";
			return false;
		}
		Serial.print("NUCODE_AC02B_DUT:SERIAL1:PASS:baud=115200:cycles=2:bytes=64");
		finishToken();
		return true;
	}

	/** @brief 한 Wire clock에서 no-STOP write와 repeated-start read를 검증합니다. */
	[[nodiscard]] bool wireRound(std::uint32_t clock_hz,
								 const std::uint8_t (&payload)[16])
	{
		Wire.setClock(clock_hz);
		if (nucode::arduino::internal::lastWireError() != WireError::none)
		{
			return false;
		}
		Wire.beginTransmission(i2c_target_address);
		if (Wire.write(payload, sizeof(payload)) != sizeof(payload))
		{
			return false;
		}
		if ((Wire.endTransmission(false) != 0U) ||
			!nucode::arduino::internal::wireHasPendingRestart())
		{
			return false;
		}
		if (Wire.requestFrom(i2c_target_address, sizeof(payload), true) != sizeof(payload))
		{
			return false;
		}
		for (std::size_t index = 0U; index < sizeof(payload); ++index)
		{
			if ((Wire.available() <= 0) ||
				(Wire.read() != static_cast<int>(payload[index] ^ 0xA5U)))
			{
				return false;
			}
		}
		return (Wire.available() == 0) &&
			   (nucode::arduino::internal::lastWireError() == WireError::none);
	}

	/** @brief Wire route, active remap 거부, 100/400 kHz와 end/rebegin을 검증합니다. */
	[[nodiscard]] bool testWire(void)
	{
		std::uint8_t payload[16]{};
		noncePayload(payload);
		constexpr std::uint32_t clocks[]{100000U, 400000U};
		for (std::size_t cycle = 0U; cycle < 2U; ++cycle)
		{
			if (!Wire.setPins(PIN_P1_02, PIN_P1_03))
			{
				return false;
			}
			Wire.begin();
			if ((nucode::arduino::internal::lastWireError() != WireError::none) ||
				Wire.setPins(PIN_P1_02, PIN_P1_03) ||
				!wireRound(clocks[cycle], payload))
			{
				Wire.end();
				return false;
			}
			Wire.end();
			if (nucode::arduino::internal::lastWireError() != WireError::none)
			{
				return false;
			}
		}
		Serial.print("NUCODE_AC02B_DUT:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32:restart=2");
		finishToken();
		return true;
	}

	/** @brief local MOSI↔MISO loopback과 GPIO interrupt mask transaction을 검증합니다. */
	[[nodiscard]] bool testSpi(void)
	{
		attachInterrupt(digitalPinToInterrupt(PIN_BUTTON0), spiMaskFixtureCallback, CHANGE);
		if (nucode::arduino::internal::lastGpioError() != GpioError::none)
		{
			return false;
		}
		if (!SPI.setPins(PIN_P2_01, PIN_P2_04, PIN_P2_02))
		{
			detachInterrupt(digitalPinToInterrupt(PIN_BUTTON0));
			return false;
		}
		SPI.begin();
		if ((nucode::arduino::internal::lastSpiError() != SpiError::none) ||
			SPI.setPins(PIN_P2_01, PIN_P2_04, PIN_P2_02))
		{
			SPI.end();
			detachInterrupt(digitalPinToInterrupt(PIN_BUTTON0));
			return false;
		}
		SPI.usingInterrupt(static_cast<int>(digitalPinToInterrupt(PIN_BUTTON0)));
		if (nucode::arduino::internal::lastSpiError() != SpiError::none)
		{
			SPI.end();
			detachInterrupt(digitalPinToInterrupt(PIN_BUTTON0));
			return false;
		}

		std::uint8_t frame[spi_byte_count]{};
		for (std::size_t index = 0U; index < sizeof(frame); ++index)
		{
			frame[index] = static_cast<std::uint8_t>((index * 37U) + 0x5AU);
		}
		SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
		SPI.transfer(frame, sizeof(frame));
		SPI.endTransaction();
		for (std::size_t index = 0U; index < sizeof(frame); ++index)
		{
			if (frame[index] != static_cast<std::uint8_t>((index * 37U) + 0x5AU))
			{
				SPI.notUsingInterrupt(static_cast<int>(digitalPinToInterrupt(PIN_BUTTON0)));
				SPI.end();
				detachInterrupt(digitalPinToInterrupt(PIN_BUTTON0));
				return false;
			}
		}
		SPI.notUsingInterrupt(static_cast<int>(digitalPinToInterrupt(PIN_BUTTON0)));
		const bool spi_ok =
			nucode::arduino::internal::lastSpiError() == SpiError::none;
		SPI.end();
		detachInterrupt(digitalPinToInterrupt(PIN_BUTTON0));
		if (!spi_ok ||
			(nucode::arduino::internal::lastSpiError() != SpiError::none))
		{
			return false;
		}
		Serial.print("NUCODE_AC02B_DUT:SPI:PASS:frequency=4000000:bytes=40:interrupt-mask=1");
		finishToken();
		return true;
	}

	/** @brief peer edge capture를 이용해 P1.10의 1 kHz 25/75% PWM을 검증합니다. */
	[[nodiscard]] bool testPwm(void)
	{
		analogWriteResolution(8U);
		if (!analogWriteFrequency(PIN_P1_10, 1000U))
		{
			return false;
		}
		constexpr int values[]{64, 191};
		constexpr const char *arm_commands[]{"PWM:ARM:25", "PWM:ARM:75"};
		constexpr const char *armed_replies[]{"PWM:ARM:25:OK", "PWM:ARM:75:OK"};
		constexpr const char *check_commands[]{"PWM:CHECK:25", "PWM:CHECK:75"};
		constexpr const char *pass_replies[]{"PWM:25:PASS", "PWM:75:PASS"};
		for (std::size_t index = 0U; index < 2U; ++index)
		{
			sendPeerLine(arm_commands[index]);
			if (!expectPeerLine(armed_replies[index]))
			{
				return false;
			}
			analogWrite(PIN_P1_10, values[index]);
			if (nucode::arduino::internal::lastAnalogError() != AnalogError::none)
			{
				return false;
			}
			delay(40U);
			sendPeerLine(check_commands[index]);
			if (!expectPeerLine(pass_replies[index]))
			{
				return false;
			}
		}
		analogWrite(PIN_P1_10, 0);
		Serial.print("NUCODE_AC02B_DUT:PWM:PASS:frequency=1000:duty=25,75");
		finishToken();
		return true;
	}

	/** @brief A0를 여러 번 읽어 일시적 전환 잡음을 평균합니다. */
	[[nodiscard]] int averageAdc(void)
	{
		std::uint32_t total = 0U;
		for (unsigned int index = 0U; index < 8U; ++index)
		{
			const int value = analogRead(PIN_P1_12);
			if ((nucode::arduino::internal::lastAnalogError() != AnalogError::none) ||
				(value < 0) || (value > 4095))
			{
				return -1;
			}
			total += static_cast<std::uint32_t>(value);
			delay(1U);
		}
		return static_cast<int>(total / 8U);
	}

	/** @brief peer P2.5 LOW/HIGH를 A P1.12/AIN5에서 구분합니다. */
	[[nodiscard]] bool testAdc(int &low, int &high)
	{
		analogReadResolution(12U);
		sendPeerLine("ADC:LOW");
		if (!expectPeerLine("ADC:LOW:OK"))
		{
			return false;
		}
		delay(10U);
		low = averageAdc();
		sendPeerLine("ADC:HIGH");
		if (!expectPeerLine("ADC:HIGH:OK"))
		{
			return false;
		}
		delay(10U);
		high = averageAdc();
		sendPeerLine("ADC:LOW");
		if (!expectPeerLine("ADC:LOW:OK"))
		{
			return false;
		}
		return (low >= 0) && (low <= 384) && (high >= 2500) &&
			   ((high - low) >= 2200);
	}

	/** @brief 모든 물리 주변장치 단계를 exact 순서로 실행합니다. */
	[[nodiscard]] bool runHil(void)
	{
		if (!testSerial1())
		{
			reportFailure(serial1_failure_stage);
			return false;
		}
		if (!testWire())
		{
			reportFailure("wire");
			return false;
		}
		if (!testSpi())
		{
			reportFailure("spi");
			return false;
		}
		if (!testPwm())
		{
			reportFailure("pwm");
			return false;
		}
		int low = -1;
		int high = -1;
		if (!testAdc(low, high))
		{
			reportFailure("adc");
			return false;
		}
		Serial.print("NUCODE_AC02B_DUT:ADC:PASS:bits=12:low=");
		Serial.print(low);
		Serial.print(":high=");
		Serial.print(high);
		finishToken();

		sendPeerLine("DONE");
		if (!expectPeerLine("DONE:PASS"))
		{
			reportFailure("peer-final");
			return false;
		}
		Serial1.end();
		Serial.print("NUCODE_AC02B_DUT:FINAL:PASS");
		finishToken();
		return true;
	}
}

/** @brief console READY를 출력하고 host start command를 기다립니다. */
void setup(void)
{
	Serial.begin(115200U);
	Serial.println("NUCODE_AC02B_READY:role=dut");
}

/** @brief 한 nonce에 대해서만 AC-02B HIL을 실행하고 이후에는 대기합니다. */
void loop(void)
{
	if (execution_finished)
	{
		delay(1000U);
		return;
	}

	char command[line_capacity]{};
	if (!readLine(Serial, command, sizeof(command), 1000U))
	{
		return;
	}
	constexpr char prefix[] = "NUCODE_AC02B_START:";
	if ((strncmp(command, prefix, sizeof(prefix) - 1U) != 0) ||
		!validNonce(command + sizeof(prefix) - 1U))
	{
		return;
	}
	memcpy(active_nonce, command + sizeof(prefix) - 1U, nonce_length + 1U);
	execution_finished = true;
	static_cast<void>(runHil());
}
