/**
 * @file TimeMath.h
 * @brief Arduino 시간 경계 계산을 검증 가능한 순수 함수로 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_TIME_MATH_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_TIME_MATH_H_

#include <limits.h>
#include <stdint.h>

namespace nucode::arduino::internal
{

    /** @brief 한 번의 Zephyr sleep에 전달할 수 있는 최대 밀리초입니다. */
    constexpr int32_t kMaximumSleepChunkMilliseconds = INT32_MAX;

    /** @brief 한 번의 nRF54 busy-wait에 전달하는 최대 마이크로초입니다. */
    constexpr uint32_t kMaximumBusyWaitChunkMicroseconds = 1000000U;

    /**
	 * @brief 순환하는 32비트 시간값 사이의 경과 시간을 계산합니다.
	 *
	 * unsigned 뺄셈의 모듈러 연산을 사용하므로 시작점과 현재점 사이에 한 번의
	 * rollover가 있어도 올바른 차이를 반환합니다. Arduino Sketch가 `millis()`와
	 * `micros()`의 차이를 계산할 때 사용하는 것과 같은 규칙입니다.
	 *
	 * @param start 시작 시각의 하위 32비트입니다.
	 * @param current 현재 시각의 하위 32비트입니다.
	 * @return 모듈러 2^32 기준 경과 시간입니다.
	 */
    [[nodiscard]] constexpr uint32_t elapsedTime32(uint32_t start, uint32_t current) noexcept
    {
        return current - start;
    }

    /**
	 * @brief 남은 밀리초에서 다음 Zephyr sleep 단위를 계산합니다.
	 *
	 * @param remaining_milliseconds deadline까지 남은 밀리초입니다.
	 * @return 대기가 끝났으면 0, 아니면 `INT32_MAX` 이하의 양수입니다.
	 */
    [[nodiscard]] constexpr int32_t
    nextSleepChunkMilliseconds(int64_t remaining_milliseconds) noexcept
    {
        if (remaining_milliseconds <= 0)
        {
            return 0;
        }

        return remaining_milliseconds > static_cast<int64_t>(kMaximumSleepChunkMilliseconds)
                   ? kMaximumSleepChunkMilliseconds
                   : static_cast<int32_t>(remaining_milliseconds);
    }

    /**
	 * @brief 남은 마이크로초에서 다음 nRF54 busy-wait 단위를 계산합니다.
	 *
	 * @param remaining_microseconds 아직 대기해야 하는 마이크로초입니다.
	 * @return 대기가 끝났으면 0, 아니면 1초 이하의 단위입니다.
	 */
    [[nodiscard]] constexpr uint32_t
    nextBusyWaitChunkMicroseconds(uint32_t remaining_microseconds) noexcept
    {
        return remaining_microseconds > kMaximumBusyWaitChunkMicroseconds
                   ? kMaximumBusyWaitChunkMicroseconds
                   : remaining_microseconds;
    }

} // namespace nucode::arduino::internal

#endif
