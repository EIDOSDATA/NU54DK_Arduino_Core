/**
 * @file Sweep.ino
 * @brief NU54DK PWM22 Servo 출력의 기본 각도 sweep 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Servo.h>

Servo servo;

void setup()
{
	if (servo.attach(PIN_PWM0) == INVALID_SERVO)
	{
		while (true)
		{
			delay(1000);
		}
	}
}

void loop()
{
	for (int angle = 0; angle <= 180; ++angle)
	{
		servo.write(angle);
		delay(15);
	}
	for (int angle = 180; angle >= 0; --angle)
	{
		servo.write(angle);
		delay(15);
	}
}
