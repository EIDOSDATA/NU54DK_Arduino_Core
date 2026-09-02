/**
 * @file SPITransaction.ino
 * @brief CS를 자동 생성하지 않는 NU54DK SPI transaction 예제입니다.
 * @note SPI library와 함께 배포되는 보드 검증 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <SPI.h>

/**
 * @brief mode 0, MSB-first, 4 MHz transaction에서 두 byte를 전송합니다.
 *
 * @note 실제 target의 CS는 확정된 외부 GPIO를 Sketch가 직접 제어해야 합니다.
 */
void setup(void)
{
	Serial.begin(115200U);
	SPI.begin();
	SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
	uint8_t frame[] = {0x9FU, 0x00U};
	SPI.transfer(frame, sizeof(frame));
	SPI.endTransaction();
	Serial.println("NUCODE_M7_SPI_TRANSACTION_DONE");
}

/** @brief 단일 transaction 예제이므로 추가 전송은 수행하지 않습니다. */
void loop(void)
{
	delay(1000U);
}
