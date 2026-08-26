/**
 * @file spi_transaction.cpp
 * @brief CS를 자동 생성하지 않는 SPI transaction build/HIL firmware입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <cstdint>

/** @brief mode 0, MSB-first, 4 MHz transaction에서 두 byte를 전송합니다. */
void setup(void)
{
	Serial.begin(115200U);
	SPI.begin();
	SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
	std::uint8_t frame[] = {0x9FU, 0x00U};
	SPI.transfer(frame, sizeof(frame));
	SPI.endTransaction();
	Serial.println("NUCODE_M7_SPI_TRANSACTION_DONE");
}

/** @brief 단일 transaction 예제이므로 추가 전송은 수행하지 않습니다. */
void loop(void)
{
	delay(1000U);
}
