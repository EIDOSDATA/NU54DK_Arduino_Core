/**
 * @file zephyr_coexist.ino
 * @brief Arduino API와 Zephyr API를 한 스케치에서 직접 함께 사용하는 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#define NU54_M11_FEATURE_ENABLED 1

#if NU54_M11_FEATURE_ENABLED
#define NU54_M11_VALUE_TYPE unsigned int
#else
#define NU54_M11_VALUE_TYPE invalid_target_type
#endif

/** @brief Arduino loop와 Zephyr atomic API가 공유하는 실행 횟수입니다. */
static atomic_t zephyrLoopCount;

/** @brief Arduino 초기화 API와 Zephyr atomic API를 같은 스케치에서 호출합니다. */
void setup(void)
{
	pinMode(LED_BUILTIN, OUTPUT);
	atomic_clear(&zephyrLoopCount);
	atomic_set(&zephyrLoopCount, (atomic_val_t)zephyrMixedValue(41U));
}

/** @brief Zephyr 직접 include와 사용자 macro가 있어도 자동 prototype 생성을 검증합니다. */
NU54_M11_VALUE_TYPE zephyrMixedValue(NU54_M11_VALUE_TYPE value)
{
	return value + 1U;
}

/** @brief Zephyr 시간·sleep API와 Arduino GPIO·시간 API의 공존을 빌드 검증합니다. */
void loop(void)
{
	const int64_t zephyrStart = k_uptime_get();
	const unsigned long arduinoStart = millis();

	atomic_inc(&zephyrLoopCount);
	k_sleep(K_MSEC(1));
	digitalWrite(LED_BUILTIN,
		     (atomic_get(&zephyrLoopCount) & 1) != 0 ? HIGH : LOW);

	if ((k_uptime_get() < zephyrStart) || (millis() < arduinoStart))
	{
		atomic_clear(&zephyrLoopCount);
	}
}
