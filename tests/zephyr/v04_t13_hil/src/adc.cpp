/** @file @brief 내부 VDD/AVDD를 2ms SAMPLE·32 sample 두 DMA slot으로 계속 검사합니다. */
#include "stream_types.h"
#include <nucode/AnalogFabric.h>

namespace
{
    using namespace nucode::arduino;
    using namespace t13;
    auto &stats = stream_stats[0];
    SaadcFabric *adc = nullptr;
    Block<std::int16_t, 32U> buffers[2];
    bool pending[2]{}, ready = false, needs_buffer = false;
    std::uint32_t submitted[2]{};
    std::uint64_t next_sample = 0U;
    unsigned channels = 0U;

    bool guards()
    {
        return !stats.enabled || (buffers[0].guards() && buffers[1].guards());
    }
} // namespace

bool t13::adcPrepare(const Case &test)
{
    stats.enabled = CONFIG_NUCODE_V04_HIL_ROLE == 1U && test.adc_channels != 0U;
    adc = nullptr;
    ready = needs_buffer = false;
    channels = test.adc_channels;
    if (!stats.enabled)
    {
        return true;
    }
    for (unsigned slot = 0U; slot < 2U; ++slot)
    {
        buffers[slot].initialize(0x5A5A);
        pending[slot] = false;
    }
    const SaadcChannelConfiguration input[]{
        {SaadcInput::vdd, SaadcInput::disabled, SaadcGain::one_quarter},
        {SaadcInput::avdd, SaadcInput::disabled, SaadcGain::one_quarter}};
    adc = &analogFabric().saadc();
    const auto result = adc->configure({input, channels, 12U, 1U, 0U});
    return result == AnalogFabricResult::success ||
           stats.fail(1U, static_cast<std::uint32_t>(result));
}

bool t13::adcStart()
{
    if (!stats.enabled)
    {
        return true;
    }
    submitted[0] = submitted[1] = k_cycle_get_32();
    const auto result = adc->start(buffers[0].values, 32U, buffers[1].values, 32U);
    if (result != AnalogFabricResult::success)
    {
        return stats.fail(2U, static_cast<std::uint32_t>(result));
    }
    pending[0] = pending[1] = stats.active = true;
    stats.queued = 2U;
    next_sample = k_uptime_get() + 2U;
    return true;
}

void t13::adcService()
{
    if (!stats.active || stats.error != 0U)
    {
        return;
    }
    SaadcEvent event{};
    while (adc->takeEvent(event))
    {
        if (event.type == SaadcEventType::ready)
        {
            ready = true;
        }
        else if (event.type == SaadcEventType::buffer_needed)
        {
            needs_buffer = true;
        }
        else if (event.type == SaadcEventType::buffer_complete)
        {
            const auto slot = stats.completed % 2U;
            if (!pending[slot] || event.buffer != buffers[slot].values || event.samples != 32U ||
                !guards())
            {
                stats.fail(3U, event.samples);
                break;
            }
            for (unsigned index = 0U; index < 32U; ++index)
            {
                const auto value = event.buffer[index];
                /** @brief 정밀 전압 교정 대신 실제 변환·포화·미기록 sentinel을 검사합니다. */
                if (value < 500 || value >= 4095)
                {
                    stats.fail(4U, static_cast<std::uint32_t>(value));
                }
                stats.minimum = value < stats.minimum ? value : stats.minimum;
                stats.maximum = value > stats.maximum ? value : stats.maximum;
                stats.hash = hashByte(hashByte(stats.hash, value & 255U), (value >> 8U) & 255U);
            }
            stats.first = static_cast<std::uint32_t>(event.buffer[0]);
            stats.last = static_cast<std::uint32_t>(event.buffer[31]);
            stats.complete(32U, submitted[slot]);
            pending[slot] = false;
        }
        else
        {
            stats.fail(5U, static_cast<std::uint32_t>(event.type));
        }
    }
    const auto slot = stats.queued % 2U;
    if (needs_buffer && !pending[slot] && stats.error == 0U)
    {
        const auto began = k_cycle_get_32();
        buffers[slot].initialize(0x5A5A);
        const auto result = adc->queueBuffer(buffers[slot].values, 32U);
        stats.queue_time.add(k_cyc_to_us_floor32(k_cycle_get_32() - began));
        if (result != AnalogFabricResult::success)
        {
            stats.fail(6U, static_cast<std::uint32_t>(result));
            return;
        }
        submitted[slot] = began;
        pending[slot] = true;
        ++stats.queued;
        needs_buffer = false;
    }
    const auto now = static_cast<std::uint64_t>(k_uptime_get());
    if (ready && stats.error == 0U && now >= next_sample)
    {
        const auto result = adc->sample();
        if (result != AnalogFabricResult::success)
        {
            stats.fail(7U, static_cast<std::uint32_t>(result));
        }
        ++stats.extra[0];
        stats.extra[1] = channels;
        next_sample = now + 2U;
    }
}

bool t13::adcStop()
{
    if (adc != nullptr &&
        (adc->state() == AnalogFabricState::active || adc->state() == AnalogFabricState::stopping ||
         adc->state() == AnalogFabricState::faulted))
    {
        const auto result = adc->stop(100000U);
        if (result != AnalogFabricResult::success)
        {
            return stats.fail(8U, static_cast<std::uint32_t>(result));
        }
    }
    stats.active = false;
    return guards() || stats.fail(9U);
}

bool t13::adcHealthy()
{
    return stats.error == 0U;
}

void t13::adcSnapshot(std::uint32_t *out)
{
    stats.snapshot(0U, guards(), out);
}
