/**
 * @file AnalogResolution.ino
 * @brief NU54DK SAADC A0를 네 hardware 해상도로 읽습니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
    Serial.begin(115200);
}

void loop()
{
    const uint8_t resolutions[] = {8, 10, 12, 14};
    for (const uint8_t bits : resolutions)
    {
        analogReadResolution(bits);
        Serial.print(bits);
        Serial.print(" bit: ");
        Serial.println(analogRead(A0));
    }
    delay(1000);
}
