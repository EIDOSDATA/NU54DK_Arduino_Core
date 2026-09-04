/**
 * @file WireRuntimePins.ino
 * @brief TWIM22 controller의 runtime SDA/SCL 선택 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Wire.h>

/** @brief P1.2 SDA와 P1.3 SCL을 400 kHz controller로 시작합니다. */
void setup(void)
{
    if (!Wire.setPins(PIN_P1_02, PIN_P1_03))
    {
        return;
    }
    Wire.begin();
    Wire.setClock(400000U);
}

/** @brief 예제는 bus를 점유하지 않고 lifecycle만 유지합니다. */
void loop(void)
{
    delay(1000U);
}
