/** @file @brief 내부 VDD/AVDD의 순서·calibration 완료·guard·반복 재시작을 검증합니다. */
#pragma once
#include <hal/nrf_saadc.h>

struct GuardedAdc
{
    std::uint32_t before[4];
    std::int16_t samples[32];
    std::uint32_t after[4];
};
extern "C"
{
    alignas(4) GuardedAdc nojumper_adc_buffer{};
}
namespace
{
    auto &adc_buffer = nojumper_adc_buffer;

    /** @brief 내부 입력만 선택하며 외부 AIN pad는 사용하지 않습니다. */
    void exerciseSaadc(const std::uint32_t *request, std::uint32_t *result)
    {
        const auto channels = request[3];
        const auto flags = request[4];
        const auto sample_count = request[5];
        const auto repetitions = request[6];
        if ((channels != 1U && channels != 2U) || flags > 3U ||
            (sample_count != 1U && sample_count != 32U) || sample_count % channels != 0U ||
            repetitions == 0U || repetitions > 100U || request[7] != 1U)
        {
            result[2] = 1U;
            return;
        }
        auto &adc = analogFabric().saadc();
        SaadcChannelConfiguration configuration[2] = {
            {SaadcInput::vdd, SaadcInput::disabled, SaadcGain::one_quarter},
            {SaadcInput::avdd, SaadcInput::disabled, SaadcGain::one_quarter}};
        if ((flags & 1U) != 0U)
        {
            configuration[0].positive = SaadcInput::avdd;
            configuration[1].positive = SaadcInput::vdd;
        }
        const SaadcChannelConfiguration unsupported{SaadcInput::vss, SaadcInput::disabled,
                                                    SaadcGain::one_quarter};
        result[26] = static_cast<std::uint32_t>(adc.configure({&unsupported, 1U, 12U, 1U, 0U}));
        if (result[26] != static_cast<std::uint32_t>(AnalogFabricResult::invalid_argument))
        {
            result[2] = 6U;
            return;
        }
        result[12] = result[14] = 4095U;
        for (std::uint32_t run = 0U; run < repetitions; ++run)
        {
            for (unsigned index = 0U; index < 4U; ++index)
            {
                adc_buffer.before[index] = guard;
                adc_buffer.after[index] = guard;
            }
            for (auto &sample : adc_buffer.samples)
            {
                sample = 0x5555;
            }
            result[8] =
                static_cast<std::uint32_t>(adc.configure({configuration, channels, 12U, 1U, 0U}));
            if (result[8] != 0U)
            {
                result[2] = 2U;
                break;
            }
            result[9] = static_cast<std::uint32_t>(
                adc.start(adc_buffer.samples, sample_count, nullptr, 0U));
            if (result[9] != 0U)
            {
                result[2] = 3U;
                break;
            }
            bool ready = false;
            bool finished = false;
            bool complete = false;
            bool calibrated = false;
            bool events_ok = true;
            auto drain = [&]
            {
                SaadcEvent event{};
                while (adc.takeEvent(event))
                {
                    ready |= event.type == SaadcEventType::ready;
                    finished |= event.type == SaadcEventType::finished;
                    calibrated |= event.type == SaadcEventType::calibration_complete;
                    if (event.type == SaadcEventType::buffer_complete)
                    {
                        events_ok &= !complete && event.buffer == adc_buffer.samples &&
                                     event.samples == sample_count;
                        complete = true;
                    }
                    events_ok &= event.type != SaadcEventType::error && event.driver_error == 0;
                }
            };
            auto deadline = k_uptime_get() + 100;
            while (!ready && k_uptime_get() < deadline)
            {
                drain();
                k_busy_wait(50U);
            }
            events_ok &= ready;
            for (std::uint32_t index = 0U; events_ok && index < sample_count / channels; ++index)
            {
                events_ok &= adc.sample() == AnalogFabricResult::success;
                k_busy_wait(100U);
                drain();
            }
            deadline = k_uptime_get() + 100;
            while (!finished && k_uptime_get() < deadline)
            {
                drain();
                k_busy_wait(50U);
            }
            events_ok &= complete && finished;
            if (events_ok && (flags & 2U) != 0U)
            {
                result[22] = static_cast<std::uint32_t>(adc.calibrate());
                deadline = k_uptime_get() + 100;
                while (!calibrated && k_uptime_get() < deadline)
                {
                    drain();
                    k_busy_wait(50U);
                }
                events_ok &= result[22] == 0U && calibrated;
                if (calibrated)
                {
                    ++result[23];
                }
            }
            result[10] = static_cast<std::uint32_t>(adc.stop(100000U));
            result[11] = static_cast<std::uint32_t>(adc.state());
            result[17] = NRF_SAADC->ENABLE;
            result[19] = 1U;
            for (unsigned index = 0U; index < 4U; ++index)
            {
                result[19] &= adc_buffer.before[index] == guard && adc_buffer.after[index] == guard;
            }
            for (std::uint32_t index = sample_count; index < 32U; ++index)
            {
                result[19] &= adc_buffer.samples[index] == 0x5555;
            }
            result[20] =
                resourceFree(peripheralIoResource(IoResourceKind::adc_block, 0U, NRF_SAADC)) &&
                resourceFree(dmaMemoryIoResource(adc_buffer.samples, sample_count * 2U));
            for (std::uint32_t index = 0U; index < sample_count; ++index)
            {
                const auto sample = adc_buffer.samples[index];
                const auto channel = index % channels;
                if (sample < 0 || sample > 4095)
                {
                    events_ok = false;
                    break;
                }
                const auto value = static_cast<std::uint32_t>(sample);
                const auto minimum = 12U + channel * 2U;
                const auto maximum = minimum + 1U;
                if (value < result[minimum])
                {
                    result[minimum] = value;
                }
                if (value > result[maximum])
                {
                    result[maximum] = value;
                }
                ++result[16];
            }
            if (!events_ok || result[10] != 0U || result[17] != 0U || result[19] != 1U ||
                result[20] != 1U)
            {
                result[2] = 4U;
                break;
            }
            ++result[21];
        }
    }
} // namespace
