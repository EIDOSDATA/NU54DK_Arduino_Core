/**
 * @file wire_whoami.cpp
 * @brief 고정 LSM6DS3TR-C WHO_AM_I repeated-start HIL firmware입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{
	/** @brief NU54DK Qwiic에 연결된 IMU의 고정 7-bit 주소입니다. */
	constexpr std::uint8_t imu_address = 0x6BU;

	/** @brief LSM6DS3TR-C WHO_AM_I register입니다. */
	constexpr std::uint8_t who_am_i_register = 0x0FU;

	/** @brief LSM6DS3TR-C가 반환해야 하는 WHO_AM_I 값입니다. */
	constexpr std::uint8_t who_am_i_expected = 0x6AU;

	/** @brief HIL host가 보낼 수 있는 유일한 고정 요청입니다. */
	constexpr char request_token[] = "NUCODE_M7_I2C_WHOAMI_RS:6B:0F";

	char request_buffer[sizeof(request_token)] = {};
	std::size_t request_length = 0U;
	bool request_overflow = false;

	/** @brief 고정 IMU register를 no-STOP write와 repeated-start read로 읽습니다. */
	void readWhoAmI(void)
	{
		Wire.beginTransmission(imu_address);
		if ((Wire.write(who_am_i_register) != 1U) ||
			(Wire.endTransmission(false) != 0U))
		{
			Serial.println("NUCODE_M7_I2C_ERROR:TX");
			return;
		}

		if ((Wire.requestFrom(imu_address, 1U, true) != 1U) ||
			(Wire.available() != 1))
		{
			Serial.println("NUCODE_M7_I2C_ERROR:RX");
			return;
		}

		const int value = Wire.read();
		if (value != who_am_i_expected)
		{
			Serial.println("NUCODE_M7_I2C_ERROR:WHOAMI");
			return;
		}

		Serial.println("NUCODE_M7_I2C_RESULT:6B:0F:6A:RS");
	}

	/** @brief 완성된 UART 줄이 고정 HIL 요청과 같은 경우에만 I2C를 실행합니다. */
	void finishRequest(void)
	{
		request_buffer[request_length] = '\0';
		if (!request_overflow &&
			(request_length == (sizeof(request_token) - 1U)) &&
			(strcmp(request_buffer, request_token) == 0))
		{
			readWhoAmI();
		}

		request_length = 0U;
		request_overflow = false;
	}

	/**
	 * @brief 한 UART byte를 고정 요청 parser에 반영합니다.
	 *
	 * @param value 수신한 byte입니다.
	 */
	void consumeRequestByte(char value)
	{
		if (value == '\r')
		{
			return;
		}
		if (value == '\n')
		{
			finishRequest();
			return;
		}

		if (request_length < (sizeof(request_buffer) - 1U))
		{
			request_buffer[request_length++] = value;
		}
		else
		{
			request_overflow = true;
		}
	}
}

/** @brief Serial과 400 kHz Wire controller를 시작하고 준비 token을 출력합니다. */
void setup(void)
{
	Serial.begin(115200U);
	Wire.begin();
	Wire.setClock(400000U);
	Serial.println("NUCODE_M7_I2C_READY");
}

/** @brief 고정 UART 요청만 수신하며 I2C 주소 탐색은 수행하지 않습니다. */
void loop(void)
{
	while (Serial.available() > 0)
	{
		const int value = Serial.read();
		if (value < 0)
		{
			break;
		}
		consumeRequestByte(static_cast<char>(value));
	}
	delay(1U);
}
