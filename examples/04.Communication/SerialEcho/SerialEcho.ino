/**
 * @file SerialEcho.ino
 * @brief Zephyr 소유 console UART를 Arduino Serial로 빌려 쓰는 echo 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

/** @brief 개행과 문자열 종료 문자를 제외한 최대 payload 길이는 127 byte입니다. */
static char line_buffer[128] = {};

/** @brief 현재 line buffer에 저장한 payload 길이입니다. */
static size_t line_length = 0U;

/** @brief 현재 입력 줄이 line buffer 용량을 초과했는지 나타냅니다. */
static bool line_overflow = false;

/** @brief Serial을 Zephyr DTS 속도 그대로 시작하고 HIL 준비 token을 출력합니다. */
void setup(void)
{
	Serial.begin(115200U);
	if (Serial)
	{
		Serial.println("NUCODE_M6_SERIAL_READY");
	}
}

/**
 * @brief 완성된 입력 줄을 echo하거나 길이 초과 오류를 출력합니다.
 */
static void finish_line(void)
{
	if (line_overflow)
	{
		Serial.println("NUCODE_M6_ERROR:LINE_TOO_LONG");
	}
	else
	{
		line_buffer[line_length] = '\0';
		Serial.print("NUCODE_M6_ECHO:");
		Serial.println(line_buffer);
	}

	line_length = 0U;
	line_overflow = false;
}

/**
 * @brief 한 RX byte를 CRLF line protocol에 반영합니다.
 *
 * @param value 수신한 byte입니다.
 */
static void consume_serial_byte(char value)
{
	if (value == '\r')
	{
		return;
	}
	if (value == '\n')
	{
		finish_line();
		return;
	}

	if (!line_overflow && (line_length < (sizeof(line_buffer) - 1U)))
	{
		line_buffer[line_length++] = value;
	}
	else
	{
		line_overflow = true;
	}
}

/** @brief 수신 byte를 비우고 완성된 줄마다 echo 응답을 출력합니다. */
void loop(void)
{
	while (Serial.available() > 0)
	{
		const int value = Serial.read();
		if (value < 0)
		{
			break;
		}
		consume_serial_byte(static_cast<char>(value));
	}

	delay(1UL);
}
