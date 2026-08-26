/**
 * @file time_backend_nrf54.cpp
 * @brief nRF54L15 GRTC와 Zephyr kernel을 사용하는 시간 백엔드입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "TimeBackend.h"

#include <limits.h>
#include <stdint.h>

#include <zephyr/drivers/timer/nrf_grtc_timer.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/time_units.h>

namespace nucode::arduino::internal
{
	namespace
	{

		/**
		 * @brief nRF54L busy-wait 하위 구현의 내부 곱셈이 넘치지 않도록 제한한 단위입니다.
		 *
		 * 1초 단위는 nRF54L15의 최고 CPU clock에서도 32비트 cycle 계산 범위 안에
		 * 있으므로 더 긴 요청은 이 값으로 나누어 처리합니다.
		 */
		constexpr uint32_t kBusyWaitChunkMicroseconds = 1000000U;

	}

	uint32_t timeMillis(void)
	{
		return k_uptime_get_32();
	}

	uint32_t timeMicros(void)
	{
		const uint64_t startupCycles = z_nrf_grtc_timer_startup_value_get();
		const uint64_t elapsedCycles = k_cycle_get_64() - startupCycles;

		return static_cast<uint32_t>(k_cyc_to_us_floor64(elapsedCycles));
	}

	void yieldCurrentThread(void)
	{
		if (!k_can_yield())
		{
			return;
		}

		k_yield();
	}

	void sleepMilliseconds(uint32_t milliseconds)
	{
		if (milliseconds == 0U)
		{
			yieldCurrentThread();
			return;
		}

		if (!k_can_yield())
		{
			return;
		}

		const int64_t deadline = k_uptime_get() + static_cast<int64_t>(milliseconds);

		while (true)
		{
			const int64_t remaining = deadline - k_uptime_get();

			if (remaining <= 0)
			{
				return;
			}

			const int32_t sleepChunk = static_cast<int32_t>(
				remaining > static_cast<int64_t>(INT32_MAX) ? INT32_MAX : remaining);

			static_cast<void>(k_msleep(sleepChunk));
		}
	}

	void busyWaitMicroseconds(uint32_t microseconds)
	{
		if ((microseconds == 0U) || k_is_in_isr())
		{
			return;
		}

		while (microseconds > kBusyWaitChunkMicroseconds)
		{
			k_busy_wait(kBusyWaitChunkMicroseconds);
			microseconds -= kBusyWaitChunkMicroseconds;
		}

		k_busy_wait(microseconds);
	}

}
