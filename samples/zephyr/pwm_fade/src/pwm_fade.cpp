/**
 * @file pwm_fade.cpp
 * @brief NU54DK PIN_PWM0/P1.10의 8-bit PWM duty를 변화시킵니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

namespace
{
	int duty = 0;
	int step = 1;
}

/** @brief 0% edge에서 PWM 예제를 시작합니다. */
void setup(void)
{
	analogWrite(PIN_PWM0, 0);
}

/** @brief 고정 20 ms period에서 duty 0..255 edge를 왕복합니다. */
void loop(void)
{
	analogWrite(PIN_PWM0, duty);
	duty += step;
	if ((duty == 255) || (duty == 0))
	{
		step = -step;
	}
	delay(10U);
}
