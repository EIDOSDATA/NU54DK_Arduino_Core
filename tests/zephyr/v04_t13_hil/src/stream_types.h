/** @file @brief 각 T13 연속 stream의 별도 DMA 통계와 수명주기 경계입니다. */
#pragma once
#include "engine.h"
#include "measurement.h"
#include <zephyr/kernel.h>

namespace t13
{
    struct StreamStats
    {
        bool enabled = false, active = false;
        std::uint32_t error = 0U, detail = 0U, completed = 0U, queued = 0U;
        std::uint64_t units = 0U, previous_ms = 0U;
        std::uint32_t hash = hash_initial, first = 0U, last = 0U;
        std::int32_t minimum = INT32_MAX, maximum = INT32_MIN;
        std::uint32_t padding = 0U, extra[2]{}, max_gap_ms = 0U;
        Timing queue_time, completion_time;

        bool fail(std::uint32_t code, std::uint32_t value = 0U)
        {
            if (error == 0U)
            {
                error = code;
                detail = value;
            }
            return false;
        }

        void complete(std::uint32_t amount, std::uint32_t submitted)
        {
            const auto now = static_cast<std::uint64_t>(k_uptime_get());
            if (previous_ms != 0U && now - previous_ms > max_gap_ms)
            {
                max_gap_ms = static_cast<std::uint32_t>(now - previous_ms);
            }
            previous_ms = now;
            completion_time.add(k_cyc_to_us_floor32(k_cycle_get_32() - submitted));
            ++completed;
            units += amount;
        }

        void snapshot(unsigned kind, bool guards, std::uint32_t *out) const
        {
            const std::uint32_t values[]{kind,
                                         active,
                                         error,
                                         detail,
                                         completed,
                                         queued,
                                         static_cast<std::uint32_t>(units),
                                         static_cast<std::uint32_t>(units >> 32U),
                                         hash,
                                         static_cast<std::uint32_t>(minimum),
                                         static_cast<std::uint32_t>(maximum),
                                         first,
                                         last,
                                         padding,
                                         extra[0],
                                         extra[1],
                                         max_gap_ms,
                                         queue_time.maximum,
                                         guards,
                                         enabled};
            for (unsigned index = 0U; index < 20U; ++index)
            {
                out[index] = values[index];
            }
        }
    };

    bool adcPrepare(const Case &test);
    bool adcStart();
    void adcService();
    bool adcStop();
    bool adcHealthy();
    void adcSnapshot(std::uint32_t *out);
    bool audioPrepare(const Case &test, std::uint32_t seed);
    bool audioStart();
    void audioService();
    bool audioStop();
    bool audioHealthy();
    void audioSnapshot(std::uint32_t *out);
    bool pwmPrepare(const Case &test);
    bool pwmStart();
    bool pwmStop();
    bool pwmHealthy();
    void pwmService();
    void pwmSnapshot(std::uint32_t *out);
    bool pdmPrepare(const Case &test);
    bool pdmStart();
    void pdmService();
    bool pdmStop();
    bool pdmHealthy();
    void pdmSnapshot(std::uint32_t *out);
    extern StreamStats stream_stats[4];
    extern bool streams_quiesced;
} // namespace t13
