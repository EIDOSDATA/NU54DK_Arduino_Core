/**
 * @file interrupt_button.cpp
 * @brief GPIO interrupt로 NU54DK 버튼 변화에 따라 LED를 갱신합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

namespace
{
	/** @brief ISR에서 loop로 버튼 변화만 전달하는 최소 flag입니다. */
	volatile bool button_changed = false;

	/** @brief GPIO ISR에서 blocking 작업 없이 변화 flag만 설정합니다. */
	void onButtonChange(void)
	{
		button_changed = true;
	}

}

/** @brief 버튼 입력, LED 출력과 raw CHANGE interrupt를 구성합니다. */
void setup(void)
{
	pinMode(LED_BUILTIN, OUTPUT);
	pinMode(PIN_BUTTON0, INPUT_PULLUP);
	attachInterrupt(digitalPinToInterrupt(PIN_BUTTON0), onButtonChange, CHANGE);
	button_changed = true;
}

/** @brief 버튼 변화가 있을 때 thread 문맥에서 입력을 읽고 LED를 갱신합니다. */
void loop(void)
{
	if (button_changed)
	{
		button_changed = false;
		const PinStatus button_raw = digitalRead(PIN_BUTTON0);
		digitalWrite(LED_BUILTIN, (button_raw == LOW) ? LOW : HIGH);
	}

	delay(1UL);
}
