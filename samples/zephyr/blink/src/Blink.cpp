/**
 * @file Blink.cpp
 * @brief Arduino GPIO와 시간 API만 사용하는 NU54DK LED 점멸 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

/**
 * @brief 내장 LED를 출력으로 초기화합니다.
 */
void setup(void)
{
	pinMode(LED_BUILTIN, OUTPUT);
}

/**
 * @brief 내장 LED를 250 ms 간격으로 켜고 끕니다.
 */
void loop(void)
{
	digitalWrite(LED_BUILTIN, HIGH);
	delay(250UL);
	digitalWrite(LED_BUILTIN, LOW);
	delay(250UL);
}
