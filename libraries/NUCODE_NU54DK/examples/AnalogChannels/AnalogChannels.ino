/**
 * @file AnalogChannels.ino
 * @brief 기본 profile에서 강제 탈취 없이 읽을 수 있는 SAADC 별칭을 순회합니다.
 *
 * @details A1~A4는 UART20, A5는 PMIC INT 소유권을 유지하므로 기본 profile에서
 * analogRead()가 -1을 반환합니다. 해당 기능을 종료하고 route를 명시적으로 넘기는
 * 전용 profile을 사용하기 전에는 Core가 이 핀들을 암묵적으로 탈취하지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
	Serial.begin(115200);
	analogReadResolution(12);
}

void loop()
{
	const pin_size_t pins[] = {A0, A6, A7};
	const char *const labels[] = {"AIN5/A0", "AIN6/A6", "AIN7/A7"};
	for (size_t index = 0; index < 3; ++index)
	{
		Serial.print(labels[index]);
		Serial.print(": ");
		Serial.println(analogRead(pins[index]));
	}
	delay(1000);
}
