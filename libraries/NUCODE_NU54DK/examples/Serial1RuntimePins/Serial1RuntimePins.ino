/**
 * @file Serial1RuntimePins.ino
 * @brief uart30 Serial1의 핀 선택과 begin/end 재시작 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODEPeripheral.h>

/** @brief P0.1 RX와 P0.0 TX를 선택해 독립 UART를 시작합니다. */
void setup(void)
{
    if (!Serial1.setPins(PIN_P0_01, PIN_P0_00))
    {
        return;
    }
    Serial1.begin(115200U, SERIAL_8N1);
    Serial1.println("NU54 Serial1 ready");
}

/** @brief 수신 byte를 그대로 되돌려 보냅니다. */
void loop(void)
{
    if (Serial1.available() > 0)
    {
        Serial1.write(static_cast<uint8_t>(Serial1.read()));
    }
}
