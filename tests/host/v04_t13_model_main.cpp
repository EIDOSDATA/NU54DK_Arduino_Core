/** @file @brief 실제 target 모델의 DMA 양끝 가드와 전역 byte 위치를 Host에서 대조합니다. */
#include "model.h"
#include "measurement.h"
#include <cstdio>

int main()
{
    t13::Block<std::int16_t, 32U> adc;
    t13::Block<std::int16_t, 1024U> pdm;
    adc.initialize(0x5A5A);
    pdm.initialize(0x5A5A);
    adc.values[31] = -123;
    pdm.values[1023] = 123;
    if (!adc.guards() || !pdm.guards())
    {
        return 10;
    }
    adc.before[3] ^= 1U;
    pdm.after[0] ^= 1U;
    if (adc.guards() || pdm.guards())
    {
        return 11;
    }
    t13::Timing timing;
    constexpr std::uint32_t delays[]{0U, 1U, 2U, 3U, 16384U, 16385U, UINT32_MAX};
    for (const auto delay : delays)
    {
        timing.add(delay);
    }
    std::uint32_t timing_words[20]{};
    timing.snapshot(timing_words);
    if (timing.count != 7U || timing.total != 4295000070ULL || timing.maximum != UINT32_MAX ||
        timing.bins[0] != 2U || timing.bins[1] != 1U || timing.bins[2] != 1U ||
        timing.bins[14] != 1U || timing.bins[15] != 2U || timing_words[3] != 1U)
    {
        return 12;
    }
    t13::Edges edges;
    /** @brief timer wrap을 포함한 25% 정상 파형과 실제 누락·중복 에지를 구분합니다. */
    if (!edges.consume(UINT32_MAX - 249U, 1U, 25U) || !edges.consume(0U, 0U, 25U) ||
        !edges.consume(750U, 1U, 25U) || !edges.consume(1000U, 0U, 25U) || edges.high_min != 250U ||
        edges.low_min != 750U)
    {
        return 13;
    }
    auto missing = edges;
    auto duplicate = edges;
    if (missing.consume(2750U, 1U, 25U) || duplicate.consume(1750U, 0U, 25U))
    {
        return 14;
    }
    t13::FailureTail immediate;
    immediate.observe(100U, 0U);
    if (!immediate.stop(100U, 0U, 1000000U))
    {
        return 15;
    }
    t13::FailureTail tail;
    tail.enabled = true;
    tail.observe(100U, UINT32_MAX - 999U);
    tail.observe(101U, 0U);
    if (tail.first_count != 100U || tail.first_cycle != UINT32_MAX - 999U ||
        tail.stop(107U, 8999U, 1000000U) || !tail.stop(108U, 8999U, 1000000U) ||
        !tail.stop(101U, 9000U, 1000000U) || edges.bad != 0U || missing.bad != 1U)
    {
        return 16;
    }
    t13::Buffer buffer{};
    constexpr unsigned lengths[]{4U, 32U, 256U, 1024U};
    for (const auto length : lengths)
    {
        if (!buffer.initialize(length) || !buffer.guards(length))
        {
            return 1;
        }
        buffer.data()[length - 1U] ^= 1U;
        if (!buffer.guards(length))
        {
            return 2;
        }
        buffer.data()[length] ^= 1U;
        if (buffer.guards(length))
        {
            return 3;
        }
        buffer.initialize(length);
        buffer.storage[3] ^= 1U;
        if (buffer.guards(length))
        {
            return 4;
        }
    }
    constexpr unsigned invalid[]{0U, 3U, 1028U, UINT32_MAX};
    for (const auto length : invalid)
    {
        if (buffer.initialize(length) || buffer.guards(length))
        {
            return 5;
        }
    }
    constexpr std::uint32_t positions[]{0U, 1U, 1023U, 1024U, 1000000U, UINT32_MAX};
    for (unsigned lane = 0U; lane < 5U; ++lane)
    {
        for (unsigned role = 1U; role <= 2U; ++role)
        {
            const auto seed = t13::laneSeed(0xA7130924U, lane, role);
            for (const auto position : positions)
            {
                std::printf("%u\n", static_cast<unsigned>(t13::pattern(seed, position)));
            }
        }
    }
    return 0;
}
