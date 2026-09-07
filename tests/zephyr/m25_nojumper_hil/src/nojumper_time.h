/** @file @brief GRTC 기반 기존 micros/millis/delay endpoint를 별도 TIMER와 대조합니다. */
#pragma once

namespace
{
    void exerciseTime(const std::uint32_t *request, std::uint32_t *result)
    {
        const auto duration = request[3];
        const auto sleep_ms = request[4];
        const auto repetitions = request[5];
        if ((duration != 1000U && duration != 10000U) || sleep_ms > 1U || repetitions != 100U ||
            request[6] != 0U || request[7] != 1U)
        {
            result[2] = 1U;
            return;
        }
        auto &timer = *eventFabric().timer(20U);
        /** @brief nrfx busy-wait와 GRTC의 clock 차이는 시험표의 양방향 5%로 판정합니다. */
        const auto minimum_elapsed = sleep_ms != 0U ? duration : duration - duration / 20U;
        const auto maximum_elapsed = sleep_ms != 0U ? duration + 3000U : duration + duration / 20U;
        result[12] = 0xFFFFFFFFU;
        result[14] = 0xFFFFFFFFU;
        for (std::uint32_t run = 0U; run < repetitions; ++run)
        {
            result[8] = static_cast<std::uint32_t>(timer.acquire(1000000U));
            if (result[8] != 0U)
            {
                result[2] = 2U;
                return;
            }
            result[9] = static_cast<std::uint32_t>(timer.start());
            const auto before_us = static_cast<std::uint32_t>(micros());
            const auto before_ms = static_cast<std::uint32_t>(millis());
            if (sleep_ms != 0U)
            {
                delay(duration / 1000U);
            }
            else
            {
                delayMicroseconds(duration);
            }
            const auto after_us = static_cast<std::uint32_t>(micros());
            const auto after_ms = static_cast<std::uint32_t>(millis());
            const auto captured = timer.capture(0U);
            const auto elapsed = after_us - before_us;
            const auto elapsed_ms = after_ms - before_ms;
            const auto error = elapsed > captured ? elapsed - captured : captured - elapsed;
            result[10] = static_cast<std::uint32_t>(timer.release());
            if (elapsed < result[12])
            {
                result[12] = elapsed;
            }
            if (elapsed > result[13])
            {
                result[13] = elapsed;
            }
            if (elapsed_ms < result[14])
            {
                result[14] = elapsed_ms;
            }
            if (elapsed_ms > result[15])
            {
                result[15] = elapsed_ms;
            }
            if (error > result[16])
            {
                result[16] = error;
            }
            result[20] =
                resourceFree(peripheralIoResource(IoResourceKind::timer_block, 20U, NRF_TIMER20));
            const auto expected_ms = elapsed / 1000U;
            const auto error_ms =
                elapsed_ms > expected_ms ? elapsed_ms - expected_ms : expected_ms - elapsed_ms;
            if (result[9] != 0U || result[10] != 0U || result[20] != 1U ||
                elapsed < minimum_elapsed || elapsed > maximum_elapsed || error > duration / 20U ||
                error_ms > 1U)
            {
                result[2] = 4U;
                return;
            }
            ++result[21];
        }
    }
} // namespace
