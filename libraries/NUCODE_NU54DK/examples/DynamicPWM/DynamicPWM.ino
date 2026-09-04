/**
 * @file DynamicPWM.ino
 * @brief PWM 해상도와 주파수를 바꾸면서 duty를 출력합니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
    analogWriteResolution(12);
    if (!analogWriteFrequency(PIN_PWM0, 1000))
    {
        while (true)
        {
            delay(1000);
        }
    }
}

void loop()
{
    for (int duty = 0; duty <= 4095; duty += 16)
    {
        analogWrite(PIN_PWM0, duty);
        delay(2);
    }
}
