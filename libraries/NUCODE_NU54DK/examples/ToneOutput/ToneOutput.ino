/**
 * @file ToneOutput.ino
 * @brief PWM21의 유한 duration tone과 noTone 동작을 보여줍니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
}

void loop()
{
    tone(PIN_PWM0, 440, 250);
    delay(500);
    tone(PIN_PWM0, 880);
    delay(250);
    noTone(PIN_PWM0);
    delay(500);
}
