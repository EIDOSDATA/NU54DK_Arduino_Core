/**
 * @file Servo.h
 * @brief PWM22를 사용하는 NU54DK Arduino Servo 호환 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_LIBRARY_SERVO_H_
#define NUCODE_ARDUINO_LIBRARY_SERVO_H_

#include <api/Common.h>

#include <cstdint>

/** @brief Servo 기본 최소 pulse 폭입니다. */
#define MIN_PULSE_WIDTH 544
/** @brief Servo 기본 최대 pulse 폭입니다. */
#define MAX_PULSE_WIDTH 2400
/** @brief attach 직후 출력하는 중앙 pulse 폭입니다. */
#define DEFAULT_PULSE_WIDTH 1500
/** @brief 표준 아날로그 Servo의 refresh 주기입니다. */
#define REFRESH_INTERVAL 20000
/** @brief NU54DK PWM22가 동시에 제공하는 Servo channel 수입니다. */
#define MAX_SERVOS 4
/** @brief attach 실패 또는 분리 상태를 나타내는 값입니다. */
#define INVALID_SERVO 255

/**
 * @brief 고정 메모리 PWM22 backend를 사용하는 Arduino Servo입니다.
 *
 * @details Servo motor 전원은 GPIO 또는 보드 3.3 V 출력에서 공급하지 않습니다.
 * 신호와 공통 GND만 NU54DK에 연결하고 motor 전원은 사양에 맞는 외부 전원을
 * 사용해야 합니다.
 */
class Servo
{
public:
	/** @brief 분리 상태의 Servo 객체를 생성합니다. */
	Servo();

	/** @brief 기본 544~2400 us 범위로 핀을 PWM22에 연결합니다. */
	std::uint8_t attach(int pin);

	/** @brief 사용자 최소·최대 pulse 범위로 핀을 PWM22에 연결합니다. */
	std::uint8_t attach(int pin, int minimum, int maximum);

	/** @brief 출력을 중지하고 이전 GPIO 상태를 복원합니다. */
	void detach();

	/** @brief 0~180도 또는 200 이상인 microsecond 값을 기록합니다. */
	void write(int value);

	/** @brief Servo pulse 폭을 설정 범위 안으로 제한해 기록합니다. */
	void writeMicroseconds(int value);

	/** @brief 마지막 pulse 값을 0~180도 범위로 반환합니다. */
	int read();

	/** @brief 마지막으로 성공한 pulse 폭을 microsecond로 반환합니다. */
	int readMicroseconds();

	/** @brief 이 객체가 현재 PWM22 channel을 소유하는지 반환합니다. */
	bool attached();

private:
	std::uint8_t servo_index_;
	std::uint16_t minimum_;
	std::uint16_t maximum_;
};

#endif
