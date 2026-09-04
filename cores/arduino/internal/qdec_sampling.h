/**
 * @file qdec_sampling.h
 * @brief nRF54L15 QDEC 샘플 주기와 LED 준비 시간의 순수 경계 검사입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

namespace nucode::arduino::internal
{
    /** @brief 128us부터 131072us까지의 2배 주기를 HW 코드로 바꾸며 잘못된 값은 -1입니다. */
    constexpr int qdecSamplePeriodCode(std::uint32_t microseconds) noexcept
    {
        for (unsigned code = 0; code <= 10; ++code)
        {
            if (microseconds == (128U << code))
            {
                return static_cast<int>(code);
            }
        }
        return -1;
    }

    /** @brief LEDPRE의 9비트 범위와 샘플 주기보다 짧은 조건을 검사합니다. */
    constexpr bool qdecSamplingValid(std::uint32_t period_us, std::uint32_t led_pre_us) noexcept
    {
        return qdecSamplePeriodCode(period_us) >= 0 && led_pre_us <= 511U && led_pre_us < period_us;
    }
} // namespace nucode::arduino::internal
