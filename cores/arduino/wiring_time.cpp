/**
 * @file wiring_time.cpp
 * @brief ArduinoCore-API 호환 시간 함수의 공개 진입점을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdint.h>

#include "internal/TimeBackend.h"

/**
 * @brief Zephyr kernel 시간 기준점 이후 경과한 밀리초를 반환합니다.
 *
 * @return 하위 32비트가 약 49.7일마다 순환하는 경과 시간입니다.
 */
extern "C" unsigned long millis(void)
{
	return static_cast<unsigned long>(nucode::arduino::internal::timeMillis());
}

/**
 * @brief Zephyr kernel 시간 기준점 이후 경과한 마이크로초를 반환합니다.
 *
 * @return 하위 32비트가 약 71.6분마다 순환하는 경과 시간입니다.
 */
extern "C" unsigned long micros(void)
{
	return static_cast<unsigned long>(nucode::arduino::internal::timeMicros());
}

/**
 * @brief 현재 Arduino thread를 지정한 밀리초 이상 대기시킵니다.
 *
 * @param milliseconds 대기할 밀리초입니다.
 */
extern "C" void delay(unsigned long milliseconds)
{
	nucode::arduino::internal::sleepMilliseconds(static_cast<uint32_t>(milliseconds));
}

/**
 * @brief 현재 Arduino thread에서 마이크로초 단위 busy wait를 수행합니다.
 *
 * @param microseconds 대기할 마이크로초입니다.
 */
extern "C" void delayMicroseconds(unsigned int microseconds)
{
	nucode::arduino::internal::busyWaitMicroseconds(static_cast<uint32_t>(microseconds));
}

/**
 * @brief 현재 Arduino thread가 실행 기회를 양보합니다.
 */
extern "C" void yield(void)
{
	nucode::arduino::internal::yieldCurrentThread();
}
