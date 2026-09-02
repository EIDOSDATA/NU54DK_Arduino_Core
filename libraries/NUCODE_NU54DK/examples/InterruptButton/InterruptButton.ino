/**
 * @file InterruptButton.ino
 * @brief NU54DK 버튼 edge interrupt로 내장 LED를 갱신하는 예제입니다.
 * @note ISR에서는 flag만 기록하고 실제 GPIO 처리는 loop에서 수행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

/** @brief ISR에서 loop로 버튼 변화만 전달하는 최소 flag입니다. */
static volatile bool button_changed = false;

/** @brief GPIO ISR에서 blocking 작업 없이 변화 flag만 설정합니다. */
static void on_button_change(void)
{
	button_changed = true;
}

/** @brief 버튼 입력, LED 출력과 raw CHANGE interrupt를 구성합니다. */
void setup(void)
{
	pinMode(LED_BUILTIN, OUTPUT);
	pinMode(PIN_BUTTON0, INPUT_PULLUP);
	attachInterrupt(digitalPinToInterrupt(PIN_BUTTON0), on_button_change, CHANGE);
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
