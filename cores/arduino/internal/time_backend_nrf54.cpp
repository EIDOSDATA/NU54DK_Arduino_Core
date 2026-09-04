/**
 * @file time_backend_nrf54.cpp
 * @brief nRF54L15 GRTC와 Zephyr kernel을 사용하는 시간 백엔드입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "TimeBackend.h"
#include "TimeMath.h"

#include <stdint.h>

#include <zephyr/drivers/timer/nrf_grtc_timer.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/time_units.h>

namespace nucode::arduino::internal
{
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

            const int32_t sleepChunk = nextSleepChunkMilliseconds(remaining);

            static_cast<void>(k_msleep(sleepChunk));
        }
    }

    void busyWaitMicroseconds(uint32_t microseconds)
    {
        if ((microseconds == 0U) || k_is_in_isr())
        {
            return;
        }

        while (microseconds != 0U)
        {
            const uint32_t waitChunk = nextBusyWaitChunkMicroseconds(microseconds);
            k_busy_wait(waitChunk);
            microseconds -= waitChunk;
        }
    }

} // namespace nucode::arduino::internal
