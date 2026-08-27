/**
 * @file WirePmicId.ino
 * @brief 온보드 BQ25186의 Device ID를 repeated-start로 읽습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Wire.h>

#include <string.h>

namespace
{
	/** @brief NU54DK 온보드 BQ25186의 고정 7-bit 주소입니다. */
	constexpr uint8_t pmic_address = 0x6AU;

	/** @brief BQ25186 MASK_ID register입니다. */
	constexpr uint8_t mask_id_register = 0x0CU;

	/** @brief MASK_ID 하위 nibble에 있는 Device ID mask입니다. */
	constexpr uint8_t device_id_mask = 0x0FU;

	/** @brief BQ25186이 반환해야 하는 Device ID입니다. */
	constexpr uint8_t device_id_expected = 0x01U;

	/** @brief HIL host가 보낼 수 있는 유일한 고정 요청입니다. */
	constexpr char request_token[] = "NUCODE_M7_I2C_PMIC_ID_RS:6A:0C";

	/** @brief UART protocol에서 byte를 두 자리 대문자 16진수로 출력할 표입니다. */
	constexpr char hexadecimal_digits[] = "0123456789ABCDEF";

	char request_buffer[sizeof(request_token)] = {};
	size_t request_length = 0U;
	bool request_overflow = false;

	/**
	 * @brief BQ25186 MASK_ID를 no-STOP pointer write와 repeated-start read로 읽습니다.
	 *
	 * 첫 I2C transaction은 PMIC의 기본 160초 watchdog을 시작합니다. 이 함수는
	 * register 값을 쓰지 않으며 Device ID가 있는 하위 nibble만 판정합니다.
	 */
	void readPmicId(void)
	{
		Wire.beginTransmission(pmic_address);
		if ((Wire.write(mask_id_register) != 1U) ||
			(Wire.endTransmission(false) != 0U))
		{
			Serial.println("NUCODE_M7_I2C_ERROR:TX");
			return;
		}

		if ((Wire.requestFrom(pmic_address, 1U, true) != 1U) ||
			(Wire.available() != 1))
		{
			Serial.println("NUCODE_M7_I2C_ERROR:RX");
			return;
		}

		const int value = Wire.read();
		if ((value < 0) ||
			((static_cast<uint8_t>(value) & device_id_mask) != device_id_expected))
		{
			Serial.println("NUCODE_M7_I2C_ERROR:PMIC_ID");
			return;
		}

		const uint8_t register_value = static_cast<uint8_t>(value);
		Serial.print("NUCODE_M7_I2C_RESULT:6A:0C:");
		Serial.print(hexadecimal_digits[(register_value >> 4U) & 0x0FU]);
		Serial.print(hexadecimal_digits[register_value & 0x0FU]);
		Serial.println(":RS");
	}

	/** @brief 완성된 UART 줄이 고정 HIL 요청과 같은 경우에만 I2C를 실행합니다. */
	void finishRequest(void)
	{
		request_buffer[request_length] = '\0';
		if (!request_overflow &&
			(request_length == (sizeof(request_token) - 1U)) &&
			(strcmp(request_buffer, request_token) == 0))
		{
			readPmicId();
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

/** @brief Serial과 보수적인 100 kHz Wire controller를 시작하고 준비 token을 출력합니다. */
void setup(void)
{
	Serial.begin(115200U);
	Wire.begin();
	Wire.setClock(100000U);
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
