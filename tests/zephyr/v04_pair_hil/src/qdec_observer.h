/** @file @brief QDEC 하드웨어와 별개로 GPIO Gray 전이와 관측 간격을 누산합니다. */
#pragma once
#include <cstdint>

namespace v04
{
    struct QdecObserver
    {
        std::int32_t steps{0};
        std::uint32_t doubles{0U}, transitions{0U}, max_gap{0U};
        std::uint32_t last_poll{0U}, last_edge{0U}, phase{0U};

        /** @brief 송신기가 유지 중인 최초 pad 상태와 현재 cycle을 기준으로 시작합니다. */
        void start(std::uint32_t now, std::uint32_t state)
        {
            *this = {};
            last_poll = last_edge = now;
            phase = state;
        }

        /** @brief cycle wrap을 허용하며 유효 전이·대각 전이·정지 상태를 구분합니다. */
        void sample(std::uint32_t now, std::uint32_t state)
        {
            const auto gap = now - last_poll;
            if (gap > max_gap)
            {
                max_gap = gap;
            }
            last_poll = now;
            if (state == phase)
            {
                return;
            }
            ++transitions;
            if ((state ^ phase) == 3U)
            {
                ++doubles;
            }
            else
            {
                constexpr std::uint32_t clockwise[]{1U, 3U, 0U, 2U};
                steps += state == clockwise[phase] ? 1 : -1;
            }
            last_edge = now;
            phase = state;
        }

        /** @brief 판정한 구간의 수만 지우고 실제 현재 phase와 간격 관측을 유지합니다. */
        void clearCounts()
        {
            steps = 0;
            doubles = transitions = 0U;
        }
    };
} // namespace v04
