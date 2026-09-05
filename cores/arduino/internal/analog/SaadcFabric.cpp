/** @file @brief Saadc의 private context·driver·IRQ와 lifecycle을 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#include "AnalogFabricInternal.h"
#include <hal/nrf_saadc.h>
#include <haly/nrfy_saadc.h>
#include <nrfx_saadc.h>
namespace nucode::arduino
{
    using namespace internal::analog;
    namespace
    {
        inline constexpr std::size_t saadc_channel_capacity = 8U;
        struct DmaLeaseSlot
        {
            void *address{nullptr};
            std::size_t bytes{0U};
            IoResourceLease lease{};
            bool active{false};
        };

        struct SaadcContext
        {
            SaadcChannelConfiguration channels[saadc_channel_capacity]{};
            std::size_t channel_count{0U};
            std::uint8_t resolution_bits{12U};
            std::uint16_t oversample{1U};
            std::uint16_t interval_us{0U};
            IoResourceLease lease{};
            DmaLeaseSlot dma_leases[3]{};
            EventQueue<SaadcEvent> events{};
            AnalogFabricState state{AnalogFabricState::inactive};
            internal::FabricDiagnostic<AnalogFabricResult> diagnostics{};
            internal::FabricStopSignal stop_signal{};
            bool stop_waiting{false};
            atomic_t sample_ready{0};
        };

        SaadcContext saadc_context{};
        [[nodiscard]] AnalogFabricResult reserveSaadcDma(SaadcContext &context, void *address,
                                                         std::size_t bytes,
                                                         DmaLeaseSlot *&slot) noexcept
        {
            slot = nullptr;
            for (auto &candidate : context.dma_leases)
            {
                if (!candidate.active)
                {
                    slot = &candidate;
                    break;
                }
            }
            if (slot == nullptr)
            {
                return AnalogFabricResult::resource_exhausted;
            }
            const IoResourceId resource =
                internal::dmaMemoryIoResource(address, static_cast<std::uint32_t>(bytes));
            slot->lease = {};
            const IoResourceResult reserve_result = internal::reserveIoResources(
                {IoOwnerKind::adc, 0U}, &resource, 1U, IoAcquirePolicy::exclusive, slot->lease);
            if (reserve_result != IoResourceResult::success)
            {
                slot = nullptr;
                return mapResourceResult(reserve_result);
            }
            slot->address = address;
            slot->bytes = bytes;
            slot->active = true;
            return AnalogFabricResult::success;
        }

        void rollbackSaadcDma(DmaLeaseSlot &slot) noexcept
        {
            if (!slot.active)
            {
                return;
            }
            (void)internal::rollbackIoResources(slot.lease);
            slot = {};
        }

        [[nodiscard]] IoResourceResult commitSaadcDma(DmaLeaseSlot &slot) noexcept
        {
            return slot.active ? internal::commitIoResources(slot.lease)
                               : IoResourceResult::success;
        }

        [[nodiscard]] IoResourceResult releaseSaadcDma(DmaLeaseSlot &slot) noexcept
        {
            if (!slot.active)
            {
                return IoResourceResult::success;
            }
            const IoResourceResult result = slot.lease.phase == internal::IoLeasePhase::reserved
                                                ? internal::rollbackIoResources(slot.lease)
                                                : internal::releaseIoResources(slot.lease);
            if (result == IoResourceResult::success)
            {
                slot = {};
            }
            return result;
        }

        [[nodiscard]] IoResourceResult releaseSaadcDmaFor(SaadcContext &context,
                                                          const void *address) noexcept
        {
            for (auto &slot : context.dma_leases)
            {
                if (slot.active && slot.address == address)
                {
                    return releaseSaadcDma(slot);
                }
            }
            return IoResourceResult::stale_lease;
        }

        [[nodiscard]] bool externalInput(SaadcInput input) noexcept
        {
            return static_cast<std::uint8_t>(input) <= static_cast<std::uint8_t>(SaadcInput::ain7);
        }

        [[nodiscard]] bool supportedInput(SaadcInput input) noexcept
        {
            if (externalInput(input))
            {
                return true;
            }
            /**
             * @brief 여러 SoC를 포함하는 nrfx enum에서 nRF54L15 입력만 승인합니다.
             *
             * VSS나 VDD/2를 받으면 실패가 start()까지 늦어지므로 사전에 거부합니다.
             */
            switch (input)
            {
            case SaadcInput::vdd:
            case SaadcInput::avdd:
                return true;
#if defined(NRF_SAADC_INPUT_DVDD)
            case SaadcInput::dvdd:
                return true;
#endif
            default:
                return false;
            }
        }

        [[nodiscard]] const internal::PinDescription *pinForAnalogInput(SaadcInput input) noexcept
        {
            if (!externalInput(input))
            {
                return nullptr;
            }
            const std::int8_t channel = static_cast<std::int8_t>(static_cast<std::uint8_t>(input));
            for (std::size_t pin = 0U; pin < NUM_PIN_ROLES; ++pin)
            {
                const auto *const description = internal::pinDescription(pin);
                if (description != nullptr && description->canonical_pin == pin &&
                    description->analog_channel == channel)
                {
                    return description;
                }
            }
            return nullptr;
        }

        [[nodiscard]] bool validResolution(std::uint8_t bits) noexcept
        {
            return bits == 8U || bits == 10U || bits == 12U || bits == 14U;
        }

        [[nodiscard]] bool validOversample(std::uint16_t oversample) noexcept
        {
            return oversample == 1U || oversample == 2U || oversample == 4U || oversample == 8U ||
                   oversample == 16U || oversample == 32U || oversample == 64U ||
                   oversample == 128U || oversample == 256U;
        }

        [[nodiscard]] nrf_saadc_resolution_t saadcResolution(std::uint8_t bits) noexcept
        {
            switch (bits)
            {
            case 8U:
                return NRF_SAADC_RESOLUTION_8BIT;
            case 10U:
                return NRF_SAADC_RESOLUTION_10BIT;
            case 14U:
                return NRF_SAADC_RESOLUTION_14BIT;
            case 12U:
            default:
                return NRF_SAADC_RESOLUTION_12BIT;
            }
        }

        [[nodiscard]] nrf_saadc_oversample_t saadcOversample(std::uint16_t count) noexcept
        {
            switch (count)
            {
            case 2U:
                return NRF_SAADC_OVERSAMPLE_2X;
            case 4U:
                return NRF_SAADC_OVERSAMPLE_4X;
            case 8U:
                return NRF_SAADC_OVERSAMPLE_8X;
            case 16U:
                return NRF_SAADC_OVERSAMPLE_16X;
            case 32U:
                return NRF_SAADC_OVERSAMPLE_32X;
            case 64U:
                return NRF_SAADC_OVERSAMPLE_64X;
            case 128U:
                return NRF_SAADC_OVERSAMPLE_128X;
            case 256U:
                return NRF_SAADC_OVERSAMPLE_256X;
            case 1U:
            default:
                return NRF_SAADC_OVERSAMPLE_DISABLED;
            }
        }

        [[nodiscard]] nrfx_analog_input_t nrfxAnalogInput(SaadcInput input) noexcept
        {
            const auto value = static_cast<std::uint8_t>(input);
            if (value <= static_cast<std::uint8_t>(SaadcInput::ain7))
            {
                return static_cast<nrfx_analog_input_t>(value);
            }
            if (value >= static_cast<std::uint8_t>(SaadcInput::vdd) &&
                value <= static_cast<std::uint8_t>(SaadcInput::vss))
            {
                return static_cast<nrfx_analog_input_t>(
                    static_cast<std::uint8_t>(NRFX_ANALOG_INTERNAL_VDD) + value -
                    static_cast<std::uint8_t>(SaadcInput::vdd));
            }
            return NRFX_ANALOG_INPUT_DISABLED;
        }

        void saadcEventHandler(const nrfx_saadc_evt_t *event)
        {
            SaadcEvent translated{};
            switch (event->type)
            {
            case NRFX_SAADC_EVT_READY:
                atomic_set(&saadc_context.sample_ready, 1);
                translated.type = SaadcEventType::ready;
                break;
            case NRFX_SAADC_EVT_DONE:
                translated.type = SaadcEventType::buffer_complete;
                translated.buffer = event->data.done.p_buffer;
                translated.samples = event->data.done.size;
                break;
            case NRFX_SAADC_EVT_BUF_REQ:
                translated.type = SaadcEventType::buffer_needed;
                break;
            case NRFX_SAADC_EVT_CALIBRATEDONE:
                translated.type = SaadcEventType::calibration_complete;
                break;
            case NRFX_SAADC_EVT_FINISHED:
                atomic_clear(&saadc_context.sample_ready);
                saadc_context.stop_signal.notifyStopped();
                translated.type = SaadcEventType::finished;
                break;
            case NRFX_SAADC_EVT_LIMIT:
            default:
                translated.type = SaadcEventType::error;
                translated.driver_error = -EIO;
                break;
            }
            if (!pushEvent(saadc_context.events, translated))
            {
                record(saadc_context, AnalogFabricResult::resource_exhausted, -ENOBUFS);
            }
        }
    } // namespace
    AnalogFabricState SaadcFabric::state() const noexcept
    {
        lockAnalog();
        const auto value = saadc_context.state;
        unlockAnalog();
        return value;
    }

    AnalogFabricResult SaadcFabric::lastResult() const noexcept
    {
        lockAnalog();
        const auto value = saadc_context.diagnostics.snapshot().result;
        unlockAnalog();
        return value;
    }

    int SaadcFabric::lastDriverError() const noexcept
    {
        lockAnalog();
        const int value = saadc_context.diagnostics.snapshot().driver_error;
        unlockAnalog();
        return value;
    }

    AnalogFabricResult SaadcFabric::configure(const SaadcConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        if (configuration.channels == nullptr || configuration.channel_count == 0U ||
            configuration.channel_count > saadc_channel_capacity ||
            !validResolution(configuration.resolution_bits) ||
            !validOversample(configuration.oversample) ||
            configuration.interval_us > NRFX_SAADC_INTERNAL_TIMER_INTERVAL_MAX_US ||
            (configuration.interval_us != 0U && configuration.channel_count != 1U))
        {
            return AnalogFabricResult::invalid_argument;
        }

        bool used_positive[saadc_channel_capacity]{};
        for (std::size_t index = 0U; index < configuration.channel_count; ++index)
        {
            const auto &channel = configuration.channels[index];
            if (static_cast<unsigned>(channel.gain) >
                    static_cast<unsigned>(SaadcGain::one_quarter) ||
                !supportedInput(channel.positive) ||
                (channel.negative != SaadcInput::disabled &&
                 (!externalInput(channel.positive) || !externalInput(channel.negative) ||
                  channel.negative == channel.positive)))
            {
                return AnalogFabricResult::invalid_argument;
            }
            if (externalInput(channel.positive))
            {
                const auto number = static_cast<std::uint8_t>(channel.positive);
                if (used_positive[number] || pinForAnalogInput(channel.positive) == nullptr)
                {
                    return AnalogFabricResult::invalid_argument;
                }
                used_positive[number] = true;
            }
        }

        lockAnalog();
        if (saadc_context.state == AnalogFabricState::active ||
            saadc_context.state == AnalogFabricState::stopping ||
            saadc_context.state == AnalogFabricState::faulted)
        {
            record(saadc_context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        for (std::size_t index = 0U; index < configuration.channel_count; ++index)
        {
            saadc_context.channels[index] = configuration.channels[index];
        }
        saadc_context.channel_count = configuration.channel_count;
        saadc_context.resolution_bits = configuration.resolution_bits;
        saadc_context.oversample = configuration.oversample;
        saadc_context.interval_us = configuration.interval_us;
        saadc_context.state = AnalogFabricState::configured;
        clearEvents(saadc_context.events);
        record(saadc_context, AnalogFabricResult::success);
        unlockAnalog();
        return AnalogFabricResult::success;
    }

    AnalogFabricResult SaadcFabric::start(std::int16_t *first_buffer, std::size_t first_samples,
                                          std::int16_t *next_buffer,
                                          std::size_t next_samples) noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        if (!internal::dmaCountFits(first_samples, SAADC_RESULT_MAXCNT_MAXCNT_Msk, 1U) ||
            !internal::dmaMemoryRangeValid(first_buffer, first_samples * sizeof(*first_buffer),
                                           alignof(std::int16_t)) ||
            (next_buffer == nullptr) != (next_samples == 0U) ||
            (next_samples != 0U &&
             (!internal::dmaCountFits(next_samples, SAADC_RESULT_MAXCNT_MAXCNT_Msk, 1U) ||
              !internal::dmaMemoryRangeValid(next_buffer, next_samples * sizeof(*next_buffer),
                                             alignof(std::int16_t)))))
        {
            return AnalogFabricResult::invalid_argument;
        }

        lockAnalog();
        auto &context = saadc_context;
        if (context.state != AnalogFabricState::configured)
        {
            record(context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        if ((first_samples % context.channel_count) != 0U ||
            (next_samples != 0U && (next_samples % context.channel_count) != 0U))
        {
            record(context, AnalogFabricResult::invalid_argument);
            unlockAnalog();
            return AnalogFabricResult::invalid_argument;
        }

        IoResourceId resources[internal::io_resource_lease_capacity]{};
        std::size_t resource_count = 0U;
        resources[resource_count++] =
            internal::peripheralIoResource(IoResourceKind::adc_block, 0U, NRF_SAADC);
        for (std::size_t index = 0U; index < context.channel_count; ++index)
        {
            const SaadcInput inputs[] = {context.channels[index].positive,
                                         context.channels[index].negative};
            for (const SaadcInput input : inputs)
            {
                const auto *const description = pinForAnalogInput(input);
                if (description == nullptr)
                {
                    continue;
                }
                bool duplicate = false;
                const auto resource = internal::gpioIoResource(description->gpio);
                for (std::size_t prior = 1U; prior < resource_count; ++prior)
                {
                    if (resources[prior].domain == resource.domain &&
                        resources[prior].index == resource.index)
                    {
                        duplicate = true;
                        break;
                    }
                }
                if (!duplicate)
                {
                    resources[resource_count++] = resource;
                }
            }
        }
        resources[resource_count++] = internal::dmaMemoryIoResource(
            first_buffer, static_cast<std::uint32_t>(first_samples * sizeof(*first_buffer)));
        if (next_buffer != nullptr)
        {
            resources[resource_count++] = internal::dmaMemoryIoResource(
                next_buffer, static_cast<std::uint32_t>(next_samples * sizeof(*next_buffer)));
        }

        context.lease = {};
        const IoResourceResult reserve_result =
            internal::reserveIoResources({IoOwnerKind::adc, 0U}, resources, resource_count,
                                         IoAcquirePolicy::exclusive, context.lease);
        if (reserve_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(reserve_result);
            record(context, result);
            unlockAnalog();
            return result;
        }

        context.stop_signal.beginRun();
        atomic_clear(&context.sample_ready);
        int driver_error = nrfx_saadc_init(IRQ_PRIO_LOWEST);
        if (driver_error == 0)
        {
            nrfx_saadc_channel_t channels[saadc_channel_capacity]{};
            for (std::size_t index = 0U; index < context.channel_count; ++index)
            {
                const auto positive = nrfxAnalogInput(context.channels[index].positive);
                const auto negative = nrfxAnalogInput(context.channels[index].negative);
                if (negative == NRFX_ANALOG_INPUT_DISABLED)
                {
                    nrfx_saadc_channel_t channel =
                        NRFX_SAADC_DEFAULT_CHANNEL_SE(positive, static_cast<std::uint8_t>(index));
                    channels[index] = channel;
                }
                else
                {
                    nrfx_saadc_channel_t channel = NRFX_SAADC_DEFAULT_CHANNEL_DIFFERENTIAL(
                        positive, negative, static_cast<std::uint8_t>(index));
                    channels[index] = channel;
                }
                /**
                 * @brief 다른 SoC의 gain enum 순서에 기대지 않고 nRF54L15 encoding을 전부 확인합니다.
                 */
                static_assert(
                    SAADC_CH_CONFIG_GAIN_Gain2 == 0 && SAADC_CH_CONFIG_GAIN_Gain1 == 1 &&
                    SAADC_CH_CONFIG_GAIN_Gain2_3 == 2 && SAADC_CH_CONFIG_GAIN_Gain2_4 == 3 &&
                    SAADC_CH_CONFIG_GAIN_Gain2_5 == 4 && SAADC_CH_CONFIG_GAIN_Gain2_6 == 5 &&
                    SAADC_CH_CONFIG_GAIN_Gain2_7 == 6 && SAADC_CH_CONFIG_GAIN_Gain2_8 == 7);
                channels[index].channel_config.gain =
                    static_cast<nrf_saadc_gain_t>(context.channels[index].gain);
            }
            driver_error = nrfx_saadc_channels_config(channels, context.channel_count);
        }
        if (driver_error == 0)
        {
            nrfx_saadc_adv_config_t advanced = NRFX_SAADC_DEFAULT_ADV_CONFIG;
            advanced.oversampling = saadcOversample(context.oversample);
            advanced.burst =
                context.oversample == 1U ? NRF_SAADC_BURST_DISABLED : NRF_SAADC_BURST_ENABLED;
            advanced.internal_timer_cc =
                context.interval_us == 0U ? 0U : nrfx_saadc_interval_to_cc(context.interval_us);
            advanced.start_on_end = true;
            const std::uint32_t mask = (1UL << context.channel_count) - 1UL;
            driver_error = nrfx_saadc_advanced_mode_set(
                mask, saadcResolution(context.resolution_bits), &advanced, saadcEventHandler);
        }
        if (driver_error == 0)
        {
            driver_error = nrfx_saadc_buffer_set(first_buffer, first_samples);
        }
        if (driver_error == 0 && next_buffer != nullptr)
        {
            driver_error = nrfx_saadc_buffer_set(next_buffer, next_samples);
        }
        if (driver_error == 0)
        {
            driver_error = nrfx_saadc_mode_trigger();
        }

        if (driver_error != 0)
        {
            if (nrfx_saadc_init_check())
            {
                nrfx_saadc_uninit();
            }
            (void)internal::rollbackIoResources(context.lease);
            context.lease = {};
            record(context, AnalogFabricResult::driver_error, driver_error);
            unlockAnalog();
            return AnalogFabricResult::driver_error;
        }
        const IoResourceResult commit_result = internal::commitIoResources(context.lease);
        if (commit_result != IoResourceResult::success)
        {
            context.state = AnalogFabricState::stopping;
            (void)context.stop_signal.arm();
            nrf_saadc_event_clear(NRF_SAADC, NRF_SAADC_EVENT_STOPPED);
            nrfx_saadc_abort();
            record(context, AnalogFabricResult::release_failed);
            unlockAnalog();
            return AnalogFabricResult::release_failed;
        }
        context.state = AnalogFabricState::active;
        record(context, AnalogFabricResult::success);
        unlockAnalog();
        return AnalogFabricResult::success;
    }

    AnalogFabricResult SaadcFabric::queueBuffer(std::int16_t *buffer, std::size_t samples) noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        if (!internal::dmaCountFits(samples, SAADC_RESULT_MAXCNT_MAXCNT_Msk, 1U) ||
            !internal::dmaMemoryRangeValid(buffer, samples * sizeof(*buffer),
                                           alignof(std::int16_t)))
        {
            return AnalogFabricResult::invalid_argument;
        }
        lockAnalog();
        auto &context = saadc_context;
        if (context.state != AnalogFabricState::active)
        {
            record(context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        if ((samples % context.channel_count) != 0U)
        {
            record(context, AnalogFabricResult::invalid_argument);
            unlockAnalog();
            return AnalogFabricResult::invalid_argument;
        }
        DmaLeaseSlot *slot = nullptr;
        const AnalogFabricResult reserve_result =
            reserveSaadcDma(context, buffer, samples * sizeof(*buffer), slot);
        if (reserve_result != AnalogFabricResult::success)
        {
            record(context, reserve_result);
            unlockAnalog();
            return reserve_result;
        }
        const int error = nrfx_saadc_buffer_set(buffer, samples);
        if (error != 0)
        {
            rollbackSaadcDma(*slot);
            record(context, AnalogFabricResult::driver_error, error);
            unlockAnalog();
            return AnalogFabricResult::driver_error;
        }
        const IoResourceResult commit_result = commitSaadcDma(*slot);
        const auto result = commit_result == IoResourceResult::success
                                ? AnalogFabricResult::success
                                : AnalogFabricResult::release_failed;
        if (commit_result != IoResourceResult::success)
        {
            context.state = AnalogFabricState::stopping;
            (void)context.stop_signal.arm();
            nrf_saadc_event_clear(NRF_SAADC, NRF_SAADC_EVENT_STOPPED);
            nrfx_saadc_abort();
        }
        record(context, result, error);
        unlockAnalog();
        return result;
    }

    AnalogFabricResult SaadcFabric::sample() noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        lockAnalog();
        auto &context = saadc_context;
        const unsigned int irq_key = irq_lock();
        if (context.state != AnalogFabricState::active || context.interval_us != 0U ||
            atomic_get(&context.sample_ready) == 0)
        {
            irq_unlock(irq_key);
            record(context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        /**
         * @brief 비동기 mode_trigger()는 buffer만 준비합니다.
         *
         * READY 이후 수동 변환에는 두 번째 START가 아니라 SAMPLE task가 필요합니다.
         */
        nrfy_saadc_sample_start(NRF_SAADC, nullptr);
        irq_unlock(irq_key);
        const auto result = AnalogFabricResult::success;
        record(context, result);
        unlockAnalog();
        return result;
    }

    AnalogFabricResult SaadcFabric::calibrate() noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        lockAnalog();
        auto &context = saadc_context;
        if (context.state != AnalogFabricState::active)
        {
            record(context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        const int error = nrfx_saadc_offset_calibrate(saadcEventHandler);
        const auto result =
            error == 0 ? AnalogFabricResult::success : AnalogFabricResult::driver_error;
        record(context, result, error);
        unlockAnalog();
        return result;
    }

    std::uintptr_t SaadcFabric::sampleTaskAddress() const noexcept
    {
        return nrf_saadc_task_address_get(NRF_SAADC, NRF_SAADC_TASK_SAMPLE);
    }

    std::uintptr_t SaadcFabric::readyEventAddress() const noexcept
    {
        return nrf_saadc_event_address_get(NRF_SAADC, NRF_SAADC_EVENT_STARTED);
    }

    AnalogFabricResult SaadcFabric::stop(std::uint32_t timeout_us) noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        lockAnalog();
        auto &context = saadc_context;
        if ((context.state != AnalogFabricState::active &&
             context.state != AnalogFabricState::stopping) ||
            context.stop_waiting)
        {
            record(context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        const bool first_request = context.state == AnalogFabricState::active;
        context.state = AnalogFabricState::stopping;
        context.stop_waiting = true;
        const auto generation = context.stop_signal.arm();
        atomic_clear(&context.sample_ready);
        unlockAnalog();
        /** @brief 같은 handle은 stopping 예약으로 차단하고 다른 block의 mutex는 놓습니다. */
        if (nrf_saadc_enable_check(NRF_SAADC))
        {
            if (first_request)
            {
                nrf_saadc_event_clear(NRF_SAADC, NRF_SAADC_EVENT_STOPPED);
            }
            nrfx_saadc_abort();
        }
        const bool stopped = internal::waitFabricStop(
            [&]
            {
                return !nrf_saadc_enable_check(NRF_SAADC) ||
                       context.stop_signal.completed(generation) ||
                       nrf_saadc_event_check(NRF_SAADC, NRF_SAADC_EVENT_STOPPED);
            },
            timeout_us);
        lockAnalog();
        context.stop_waiting = false;
        if (!stopped)
        {
            /** @brief 늦은 FINISHED와 명시적 stop 재시도까지 DMA와 base lease를 보존합니다. */
            record(context, AnalogFabricResult::stop_timeout, -ETIMEDOUT);
            unlockAnalog();
            return AnalogFabricResult::stop_timeout;
        }
        nrfx_saadc_uninit();
        IoResourceResult release_result = context.lease.phase == internal::IoLeasePhase::reserved
                                              ? internal::rollbackIoResources(context.lease)
                                              : internal::releaseIoResources(context.lease);
        if (release_result == IoResourceResult::success)
        {
            context.lease = {};
        }
        for (auto &slot : context.dma_leases)
        {
            const auto slot_result = releaseSaadcDma(slot);
            if (slot_result != IoResourceResult::success)
            {
                release_result = slot_result;
            }
        }
        const auto result = release_result == IoResourceResult::success
                                ? AnalogFabricResult::success
                                : AnalogFabricResult::release_failed;
        context.state = result == AnalogFabricResult::success ? AnalogFabricState::configured
                                                              : AnalogFabricState::faulted;
        record(context, result);
        unlockAnalog();
        return result;
    }

    bool SaadcFabric::takeEvent(SaadcEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        lockAnalog();
        const bool present = popEvent(saadc_context.events, event);
        if (present && event.type == SaadcEventType::buffer_complete)
        {
            const IoResourceResult release_result = releaseSaadcDmaFor(saadc_context, event.buffer);
            if (release_result != IoResourceResult::success &&
                release_result != IoResourceResult::stale_lease)
            {
                saadc_context.state = AnalogFabricState::faulted;
                record(saadc_context, AnalogFabricResult::release_failed);
            }
        }
        unlockAnalog();
        return present;
    }

} // namespace nucode::arduino
namespace nucode::arduino::internal::analog
{
    void saadcIrq(const void *)
    {
        nrfx_saadc_irq_handler();
    }
} // namespace nucode::arduino::internal::analog
