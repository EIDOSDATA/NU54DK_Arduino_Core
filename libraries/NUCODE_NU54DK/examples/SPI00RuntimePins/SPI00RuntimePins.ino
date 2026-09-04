/**
 * @file SPI00RuntimePins.ino
 * @brief SPI00 전용 SCK/MISO/MOSI route와 transaction 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <SPI.h>

/** @brief nRF54L15 SPI00 고정 route P2.1/P2.4/P2.2를 시작합니다. */
void setup(void)
{
    if (!SPI.setPins(PIN_P2_01, PIN_P2_04, PIN_P2_02))
    {
        return;
    }
    SPI.begin();
}

/** @brief 외부 CS 없이 한 byte loopback transaction을 실행합니다. */
void loop(void)
{
    SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
    static_cast<void>(SPI.transfer(0xA5U));
    SPI.endTransaction();
    delay(1000U);
}
