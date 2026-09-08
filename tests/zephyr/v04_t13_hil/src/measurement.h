/** @file @brief T13 연속 DMA의 고정 경계와 지연 분포를 독립적으로 판정합니다. */
#pragma once
#include "model.h"

namespace t13
{
    /** @brief 경계 1·2·4…16384µs 및 초과 구간의 관측 수·합계·최대값입니다. */
    struct Timing
    {
        std::uint32_t count = 0U, maximum = 0U, bins[16]{};
        std::uint64_t total = 0U;

        void add(std::uint32_t microseconds)
        {
            unsigned index = 0U;
            while (index < 15U && microseconds > (1U << index))
            {
                ++index;
            }
            ++bins[index];
            ++count;
            total += microseconds;
            if (microseconds > maximum)
            {
                maximum = microseconds;
            }
        }

        void snapshot(std::uint32_t *out) const
        {
            out[0] = count;
            out[1] = maximum;
            out[2] = static_cast<std::uint32_t>(total);
            out[3] = static_cast<std::uint32_t>(total >> 32U);
            for (unsigned index = 0U; index < 16U; ++index)
            {
                out[index + 4U] = bins[index];
            }
        }
    };

    /** @brief 실제 고정 DMA 길이 앞뒤 16-byte guard이며 반환 후에만 다시 초기화합니다. */
    template <typename T, unsigned length> struct alignas(4) Block
    {
        static_assert((length * sizeof(T)) % 4U == 0U);
        std::uint32_t before[4]{};
        T values[length]{};
        std::uint32_t after[4]{};

        void initialize(T sentinel)
        {
            for (unsigned index = 0U; index < 4U; ++index)
            {
                before[index] = after[index] = guard_word;
            }
            for (auto &value : values)
            {
                value = sentinel;
            }
        }

        bool guards() const
        {
            for (unsigned index = 0U; index < 4U; ++index)
            {
                if (before[index] != guard_word || after[index] != guard_word)
                {
                    return false;
                }
            }
            return true;
        }
    };

    /** @brief 모든 PWM 에지의 교대와 DPPI timestamp 간격을 검사하며 누락을 허용하지 않습니다. */
    struct Edges
    {
        std::uint32_t count = 0U, first = 0U, last = 0U, level = 0U;
        std::uint32_t bad = 0U, high_min = UINT32_MAX, high_max = 0U;
        std::uint32_t low_min = UINT32_MAX, low_max = 0U, maximum_poll_gap = 0U;

        bool consume(std::uint32_t timestamp, std::uint32_t next_level, unsigned duty)
        {
            if (count == 0U)
            {
                first = timestamp;
            }
            else
            {
                const auto delta = timestamp - last;
                const auto expected = level == 1U ? duty * 10U : 1000U - duty * 10U;
                if (next_level == level || delta + 8U < expected || delta > expected + 8U)
                {
                    ++bad;
                }
                auto &minimum = level == 1U ? high_min : low_min;
                auto &maximum = level == 1U ? high_max : low_max;
                minimum = delta < minimum ? delta : minimum;
                maximum = delta > maximum ? delta : maximum;
            }
            last = timestamp;
            level = next_level;
            ++count;
            return bad == 0U;
        }
    };

    /** @brief 진단 전용으로 최초 오류 뒤 최대8에지/10ms를 더 관측하되 실패는 유지합니다. */
    struct FailureTail
    {
        bool enabled = false;
        std::uint32_t first_count = 0U, first_cycle = 0U;

        void observe(std::uint32_t count, std::uint32_t cycle)
        {
            if (first_count == 0U)
            {
                first_count = count;
                first_cycle = cycle;
            }
        }

        bool stop(std::uint32_t count, std::uint32_t cycle, std::uint32_t frequency) const
        {
            return first_count != 0U &&
                   (!enabled || count - first_count >= 8U ||
                    static_cast<std::uint32_t>(cycle - first_cycle) >= frequency / 100U);
        }
    };
} // namespace t13
