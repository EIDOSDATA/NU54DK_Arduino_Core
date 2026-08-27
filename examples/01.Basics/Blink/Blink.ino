/**
 * @file Blink.ino
 * @brief NU54DK 내장 LED를 250 ms 간격으로 점멸합니다.
 */

/** @brief 내장 LED를 출력으로 초기화합니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
}

/** @brief 내장 LED의 논리 상태를 반복해서 전환합니다. */
void loop()
{
    writeBuiltinLed(true);
    delay(250);
    writeBuiltinLed(false);
    delay(250);
}

/**
 * @brief 내장 LED 상태를 기록합니다.
 * @note loop보다 아래에 두어 Arduino prototype 생성도 함께 검증합니다.
 */
void writeBuiltinLed(bool high)
{
    digitalWrite(LED_BUILTIN, high ? HIGH : LOW);
}
