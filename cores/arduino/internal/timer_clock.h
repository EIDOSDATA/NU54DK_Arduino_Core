// SPDX-License-Identifier: MIT
#ifndef NUCODE_INTERNAL_TIMER_CLOCK_H_
#define NUCODE_INTERNAL_TIMER_CLOCK_H_
#include <cstdint>
namespace nucode::arduino::internal
{
    /** @brief nRF54L15의 TIMER00, TIMER10, TIMER2x는 서로 다른 base clock을 사용합니다. */
    constexpr bool timerPrescalerFor(std::uint32_t base_hz, std::uint32_t frequency_hz,
                                     std::uint32_t maximum, std::uint32_t &prescaler) noexcept
    {
        prescaler = 0;
        if (!base_hz || !frequency_hz || frequency_hz > base_hz || base_hz % frequency_hz)
        {
            return false;
        }
        auto ratio = base_hz / frequency_hz;
        if (ratio & (ratio - 1U))
        {
            return false;
        }
        while (ratio > 1U)
        {
            ratio >>= 1U;
            ++prescaler;
        }
        return prescaler <= maximum;
    }
} // namespace nucode::arduino::internal
#endif
