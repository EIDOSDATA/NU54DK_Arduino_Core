/**
 * @file qdec_waveform.h
 * @brief Nordic의 AB 전이 표에 맞는 유한 PWM quadrature 파형을 구성합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

namespace v04
{
    /** @brief AB는 A가 상위 비트이며 정방향은 00→01→11→10→00입니다. */
    constexpr std::uint8_t qdecState(unsigned step, bool reverse)
    {
        constexpr std::uint8_t forward[4]{1U, 3U, 2U, 0U};
        constexpr std::uint8_t backward[4]{2U, 3U, 1U, 0U};
        return reverse ? backward[step % 4U] : forward[step % 4U];
    }

    /** @brief FallingEdge 극성에서 비교값 0은 LOW, TOP은 HIGH를 유지합니다. */
    constexpr std::uint16_t qdecPwmValue(unsigned step, unsigned channel, bool reverse,
                                         std::uint16_t top)
    {
        const auto state = qdecState(step, reverse);
        const unsigned mask = channel == 0U ? 2U : channel == 1U ? 1U : 0U;
        return static_cast<std::uint16_t>(0x8000U | ((state & mask) != 0U ? top : 0U));
    }
} // namespace v04
