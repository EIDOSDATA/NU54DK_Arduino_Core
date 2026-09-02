/**
 * @file PWMFade.ino
 * @brief NU54DK PIN_PWM0/P1.10을 8-bit analogWrite로 변화시킵니다.
 * @note NU54DK 보드 전용 PWM 역할을 사용합니다.
 *
 * SPDX-License-Identifier: MIT
 */

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
