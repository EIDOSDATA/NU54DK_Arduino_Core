/** @file @brief TIMER 44개 CC의 compare·clear/stop shortcut과 자원 반환을 검증합니다. */
#pragma once
#include <hal/nrf_timer.h>

namespace
{
    NRF_TIMER_Type *timerRegisters(std::uint32_t instance)
    {
        switch (instance)
        {
        case 0U:
            return NRF_TIMER00;
        case 10U:
            return NRF_TIMER10;
        case 20U:
            return NRF_TIMER20;
        case 21U:
            return NRF_TIMER21;
        case 22U:
            return NRF_TIMER22;
        case 23U:
            return NRF_TIMER23;
        case 24U:
            return NRF_TIMER24;
        default:
            return nullptr;
        }
    }

    /** @brief 다른 CC로 capture하여 시험 중인 compare 값을 보존합니다. */
    void exerciseTimer(const std::uint32_t *request, std::uint32_t *result)
    {
        const auto instance = request[3];
        const auto channel = request[4];
        const auto flags = request[5];
        const auto top = request[6];
        const auto repetitions = request[7];
        auto *const registers = timerRegisters(instance);
        auto *const timer = eventFabric().timer(static_cast<std::uint8_t>(instance));
        if (registers == nullptr || timer == nullptr || channel >= timer->channelCount() ||
            flags > 3U || (top != 1000U && top != 10000U) || repetitions == 0U || repetitions > 10U)
        {
            result[2] = 1U;
            return;
        }
        const auto capture_channel =
            static_cast<std::uint8_t>((channel + 1U) % timer->channelCount());
        const auto compare_channel = static_cast<std::uint8_t>(channel);
        const auto compare_event = nrf_timer_compare_event_get(compare_channel);
        result[12] = 0xFFFFFFFFU;
        result[18] = 1U;
        for (std::uint32_t run = 0U; run < repetitions; ++run)
        {
            if (!refusesReservation(peripheralIoResource(IoResourceKind::timer_block,
                                                         static_cast<std::uint8_t>(instance),
                                                         registers),
                                    [&]
                                    {
                                        return timer->acquire(1000000U);
                                    }))
            {
                result[2] = 6U;
                return;
            }
            ++result[27];
            result[8] = static_cast<std::uint32_t>(timer->acquire(1000000U));
            if (result[8] != 0U)
            {
                result[2] = 2U;
                break;
            }
            nrf_timer_event_clear(registers, compare_event);
            result[9] = static_cast<std::uint32_t>(
                timer->setCompare(compare_channel, top, (flags & 1U) != 0U, (flags & 2U) != 0U));
            const auto before = k_cycle_get_32();
            result[22] = static_cast<std::uint32_t>(timer->start());
            k_busy_wait(top + top / 2U);
            const auto captured = timer->capture(capture_channel);
            const auto elapsed = k_cyc_to_us_floor32(k_cycle_get_32() - before);
            const auto expected = (flags & 2U) != 0U
                                      ? ((flags & 1U) != 0U ? 0U : top)
                                      : ((flags & 1U) != 0U ? elapsed % top : elapsed);
            const auto error = captured > expected ? captured - expected : expected - captured;
            bool valid = (flags & 2U) != 0U ? captured == expected : error <= top / 20U;
            result[15] = nrf_timer_event_check(registers, compare_event) ? 1U : 0U;
            result[23] = static_cast<std::uint32_t>(timer->stop());
            const auto stopped = timer->capture(capture_channel);
            k_busy_wait(50U);
            result[18] &= stopped == timer->capture(capture_channel);
            result[24] = static_cast<std::uint32_t>(timer->clear());
            result[19] = timer->capture(capture_channel) == 0U ? 1U : 0U;
            result[10] = static_cast<std::uint32_t>(timer->release());
            result[11] = timer->active() ? 1U : 0U;
            result[17] = registers->SHORTS;
            result[20] = resourceFree(peripheralIoResource(
                IoResourceKind::timer_block, static_cast<std::uint8_t>(instance), registers));
            if (captured < result[12])
            {
                result[12] = captured;
            }
            if (captured > result[13])
            {
                result[13] = captured;
            }
            if (error > result[14])
            {
                result[14] = error;
            }
            result[25] = elapsed;
            result[26] = captured;
            valid &= result[9] == 0U && result[10] == 0U && result[11] == 0U && result[15] == 1U &&
                     result[17] == 0U && result[18] == 1U && result[19] == 1U && result[20] == 1U &&
                     result[22] == 0U && result[23] == 0U && result[24] == 0U;
            if (!valid)
            {
                result[2] = 4U;
                break;
            }
            ++result[21];
        }
    }
} // namespace
