/**
 * @file common_wiring.h
 * @brief 공통 17신호의 고정 대응과 단일 LOW의 제한 시간을 정의합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

namespace v04
{
    inline constexpr std::uint32_t wiring_count = 17U;
    inline constexpr std::uint32_t wiring_mask = (1U << wiring_count) - 1U;
    inline constexpr std::uint32_t wiring_none = UINT32_MAX;

    /** @brief GPIO의 port*32+pin 번호이며 Arduino 별칭과 connector 번호가 아닙니다. */
    constexpr std::uint32_t wiringPin(std::uint32_t role, std::uint32_t net)
    {
        constexpr std::uint32_t pins[]{46U, 42U, 36U, 37U, 38U, 39U, 0U,  1U, 2U,
                                       3U,  64U, 65U, 66U, 67U, 68U, 69U, 70U};
        if ((role != 1U && role != 2U) || net >= wiring_count)
        {
            return wiring_none;
        }
        if (role == 2U && (net == 4U || net == 5U))
        {
            return pins[9U - net];
        }
        return pins[net];
    }

    /** @brief Host가 응답하지 않아도 한 LOW를 500ms 안에 해제할 상태입니다. */
    class WiringPulse
    {
      public:
        static constexpr std::uint64_t limit_ms = 500U;

        constexpr bool start(std::uint32_t net, std::uint64_t now)
        {
            if (net >= wiring_count || net_ != wiring_none || now > UINT64_MAX - limit_ms)
            {
                return false;
            }
            net_ = net;
            deadline_ = now + limit_ms;
            return true;
        }

        constexpr bool expired(std::uint64_t now) const
        {
            return net_ != wiring_none && now >= deadline_;
        }

        constexpr void clear()
        {
            net_ = wiring_none;
            deadline_ = 0U;
        }

        constexpr std::uint32_t net() const
        {
            return net_;
        }

      private:
        std::uint32_t net_ = wiring_none;
        std::uint64_t deadline_ = 0U;
    };
} // namespace v04
