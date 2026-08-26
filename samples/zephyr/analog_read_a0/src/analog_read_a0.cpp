/**
 * @file analog_read_a0.cpp
 * @brief NU54DK A0/P1.12의 고정 12-bit raw ADC 값을 출력합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

/** @brief Serial과 DTS 고정 reference 계약을 시작합니다. */
void setup(void)
{
	Serial.begin(115200U);
	analogReference(AR_DEFAULT);
}

/** @brief A0 raw 값 0..4095 또는 오류 -1을 출력합니다. */
void loop(void)
{
	const int raw = analogRead(A0);
	Serial.print("NUCODE_M7_A0_RAW:");
	Serial.println(raw);
	delay(250U);
}
