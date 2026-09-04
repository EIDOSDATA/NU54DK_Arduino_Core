/**
 * @file AnalogFabric.cpp
 * @brief M25 SAADC scan과 PWM20/21/22 sequence EasyDMA adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/AnalogFabric.h>

#include "internal/IoResourceManager.h"
#include "internal/pin_description.h"

#include <variant.h>

#include <hal/nrf_gpio.h>
#include <hal/nrf_pwm.h>
#include <hal/nrf_saadc.h>
#include <haly/nrfy_saadc.h>
#include <nrfx_pwm.h>
#include <nrfx_saadc.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>

namespace nucode::arduino
{
    namespace
    {
        using internal::IoAcquirePolicy;
        using internal::IoOwnerKind;
        using internal::IoResourceId;
        using internal::IoResourceKind;
        using internal::IoResourceLease;
        using internal::IoResourceResult;
        using internal::PinCapability;
        using internal::PinPolicy;
        using internal::PinRoute;

        inline constexpr std::size_t saadc_channel_capacity = 8U;
        inline constexpr std::size_t event_queue_capacity = 8U;
        inline constexpr pin_size_t disconnected_pin = 0xFFU;

        template <typename Event>
        struct EventQueue
        {
            Event entries[event_queue_capacity]{};
            std::size_t read_index{0U};
            std::size_t write_index{0U};
            std::size_t count{0U};
            struct k_spinlock lock{};
        };

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
            AnalogFabricResult last_result{AnalogFabricResult::success};
            int last_driver_error{0};
            atomic_t sample_ready{0};
        };

        struct PwmContext
        {
            std::uint8_t instance{0U};
            PwmSequenceConfiguration configuration{};
            IoResourceLease lease{};
            EventQueue<PwmSequenceEvent> events{};
            AnalogFabricState state{AnalogFabricState::inactive};
            AnalogFabricResult last_result{AnalogFabricResult::success};
            int last_driver_error{0};
            std::uintptr_t start_task{0U};
        };

        K_MUTEX_DEFINE(analog_fabric_mutex);
        SaadcContext saadc_context{};
        PwmContext pwm_contexts[3]{{20U}, {21U}, {22U}};
        nrfx_pwm_t pwm_drivers[3]{NRFX_PWM_INSTANCE(NRF_PWM20),
                                  NRFX_PWM_INSTANCE(NRF_PWM21),
                                  NRFX_PWM_INSTANCE(NRF_PWM22)};

        template <typename Event>
        bool pushEvent(EventQueue<Event> &queue, const Event &event) noexcept
        {
            const k_spinlock_key_t key = k_spin_lock(&queue.lock);
            if (queue.count == event_queue_capacity)
            {
                k_spin_unlock(&queue.lock, key);
                return false;
            }
            queue.entries[queue.write_index] = event;
            queue.write_index = (queue.write_index + 1U) % event_queue_capacity;
            ++queue.count;
            k_spin_unlock(&queue.lock, key);
            return true;
        }

        template <typename Event>
        bool popEvent(EventQueue<Event> &queue, Event &event) noexcept
        {
            const k_spinlock_key_t key = k_spin_lock(&queue.lock);
            if (queue.count == 0U)
            {
                k_spin_unlock(&queue.lock, key);
                return false;
            }
            event = queue.entries[queue.read_index];
            queue.read_index = (queue.read_index + 1U) % event_queue_capacity;
            --queue.count;
            k_spin_unlock(&queue.lock, key);
            return true;
        }

        template <typename Event>
        void clearEvents(EventQueue<Event> &queue) noexcept
        {
            const k_spinlock_key_t key = k_spin_lock(&queue.lock);
            queue.read_index = 0U;
            queue.write_index = 0U;
            queue.count = 0U;
            k_spin_unlock(&queue.lock, key);
        }

        void record(SaadcContext &context, AnalogFabricResult result,
                    int driver_error = 0) noexcept
        {
            context.last_result = result;
            context.last_driver_error = driver_error;
        }

        void record(PwmContext &context, AnalogFabricResult result,
                    int driver_error = 0) noexcept
        {
            context.last_result = result;
            context.last_driver_error = driver_error;
        }

        [[nodiscard]] AnalogFabricResult
        mapResourceResult(IoResourceResult result) noexcept
        {
            switch (result)
            {
            case IoResourceResult::success:
                return AnalogFabricResult::success;
            case IoResourceResult::invalid_context:
                return AnalogFabricResult::invalid_context;
            case IoResourceResult::invalid_argument:
                return AnalogFabricResult::invalid_argument;
            case IoResourceResult::conflict:
                return AnalogFabricResult::ownership_conflict;
            case IoResourceResult::capacity_exhausted:
                return AnalogFabricResult::resource_exhausted;
            default:
                return AnalogFabricResult::release_failed;
            }
        }

        [[nodiscard]] AnalogFabricResult reserveSaadcDma(SaadcContext &context,
                                                         void *address,
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
                return AnalogFabricResult::resource_exhausted;
            const IoResourceId resource =
                internal::dmaMemoryIoResource(address, static_cast<std::uint32_t>(bytes));
            slot->lease = {};
            const IoResourceResult reserve_result =
                internal::reserveIoResources({IoOwnerKind::adc, 0U}, &resource, 1U,
                                             IoAcquirePolicy::exclusive, slot->lease);
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
                return;
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
                return IoResourceResult::success;
            const IoResourceResult result = internal::releaseIoResources(slot.lease);
            slot = {};
            return result;
        }

        [[nodiscard]] IoResourceResult
        releaseSaadcDmaFor(SaadcContext &context, const void *address) noexcept
        {
            for (auto &slot : context.dma_leases)
            {
                if (slot.active && slot.address == address)
                    return releaseSaadcDma(slot);
            }
            return IoResourceResult::stale_lease;
        }

        [[nodiscard]] bool externalInput(SaadcInput input) noexcept
        {
            return static_cast<std::uint8_t>(input) <=
                   static_cast<std::uint8_t>(SaadcInput::ain7);
        }

        [[nodiscard]] bool supportedInput(SaadcInput input) noexcept
        {
            if (externalInput(input))
                return true;
            // The nrfx enum spans several SoCs. nRF54L15 maps only these
            // internal inputs; accepting VSS or VDD/2 deferred failure to start().
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

        [[nodiscard]] const internal::PinDescription *
        pinForAnalogInput(SaadcInput input) noexcept
        {
            if (!externalInput(input))
                return nullptr;
            const std::int8_t channel =
                static_cast<std::int8_t>(static_cast<std::uint8_t>(input));
            for (std::size_t pin = 0U; pin < NUM_PIN_ROLES; ++pin)
            {
                const auto *const description = internal::pinDescription(pin);
                if (description != nullptr && description->canonical_pin == pin &&
                    description->analog_channel == channel)
                    return description;
            }
            return nullptr;
        }

        [[nodiscard]] bool validResolution(std::uint8_t bits) noexcept
        {
            return bits == 8U || bits == 10U || bits == 12U || bits == 14U;
        }

        [[nodiscard]] bool validOversample(std::uint16_t oversample) noexcept
        {
            return oversample == 1U || oversample == 2U || oversample == 4U ||
                   oversample == 8U || oversample == 16U || oversample == 32U ||
                   oversample == 64U || oversample == 128U || oversample == 256U;
        }

        [[nodiscard]] nrf_saadc_resolution_t
        saadcResolution(std::uint8_t bits) noexcept
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

        [[nodiscard]] nrf_saadc_oversample_t
        saadcOversample(std::uint16_t count) noexcept
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
                return static_cast<nrfx_analog_input_t>(value);
            if (value >= static_cast<std::uint8_t>(SaadcInput::vdd) &&
                value <= static_cast<std::uint8_t>(SaadcInput::vss))
                return static_cast<nrfx_analog_input_t>(
                    static_cast<std::uint8_t>(NRFX_ANALOG_INTERNAL_VDD) + value -
                    static_cast<std::uint8_t>(SaadcInput::vdd));
            return NRFX_ANALOG_INPUT_DISABLED;
        }

        [[nodiscard]] PwmContext *pwmContext(std::uint8_t instance) noexcept
        {
            for (auto &context : pwm_contexts)
            {
                if (context.instance == instance)
                    return &context;
            }
            return nullptr;
        }

        [[nodiscard]] nrfx_pwm_t *pwmDriver(std::uint8_t instance) noexcept
        {
            switch (instance)
            {
            case 20U:
                return &pwm_drivers[0];
            case 21U:
                return &pwm_drivers[1];
            case 22U:
                return &pwm_drivers[2];
            default:
                return nullptr;
            }
        }

        [[nodiscard]] PinRoute pwmRoute(std::uint8_t instance) noexcept
        {
            switch (instance)
            {
            case 20U:
                return PinRoute::pwm20;
            case 21U:
                return PinRoute::pwm21;
            case 22U:
                return PinRoute::pwm22;
            default:
                return PinRoute::none;
            }
        }

        [[nodiscard]] std::uint32_t
        physicalPin(const internal::PinDescription &description) noexcept
        {
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio0))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio0)))
                return NRF_GPIO_PIN_MAP(0U, description.gpio.pin);
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio1))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio1)))
                return NRF_GPIO_PIN_MAP(1U, description.gpio.pin);
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio2))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio2)))
                return NRF_GPIO_PIN_MAP(2U, description.gpio.pin);
#endif
            return NRF_PWM_PIN_NOT_CONNECTED;
        }

        [[nodiscard]] nrf_pwm_dec_load_t pwmLoad(PwmSequenceLoad load) noexcept
        {
            switch (load)
            {
            case PwmSequenceLoad::common:
                return NRF_PWM_LOAD_COMMON;
            case PwmSequenceLoad::grouped:
                return NRF_PWM_LOAD_GROUPED;
            case PwmSequenceLoad::wave_form:
                return NRF_PWM_LOAD_WAVE_FORM;
            case PwmSequenceLoad::individual:
            default:
                return NRF_PWM_LOAD_INDIVIDUAL;
            }
        }

        [[nodiscard]] bool validPwmValueCount(PwmSequenceLoad load,
                                              std::size_t count) noexcept
        {
            if (count == 0U || count > UINT16_MAX)
                return false;
            switch (load)
            {
            case PwmSequenceLoad::grouped:
                return (count % 2U) == 0U;
            case PwmSequenceLoad::individual:
                return (count % 4U) == 0U;
            case PwmSequenceLoad::wave_form:
                return (count % 4U) == 0U;
            case PwmSequenceLoad::common:
            default:
                return true;
            }
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
                saadc_context.last_driver_error = -ENOBUFS;
                saadc_context.last_result = AnalogFabricResult::resource_exhausted;
            }
        }

        void pwmEventHandler(nrfx_pwm_event_type_t event, void *context_pointer)
        {
            auto &context = *static_cast<PwmContext *>(context_pointer);
            PwmSequenceEvent translated{};
            translated.instance = context.instance;
            switch (event)
            {
            case NRFX_PWM_EVENT_END_SEQ0:
                translated.type = PwmSequenceEventType::sequence0_complete;
                break;
            case NRFX_PWM_EVENT_END_SEQ1:
                translated.type = PwmSequenceEventType::sequence1_complete;
                break;
            case NRFX_PWM_EVENT_FINISHED:
                translated.type = PwmSequenceEventType::playback_complete;
                break;
            case NRFX_PWM_EVENT_STOPPED:
                translated.type = PwmSequenceEventType::stopped;
                break;
            default:
                translated.type = PwmSequenceEventType::error;
                translated.driver_error = -EIO;
                break;
            }
            if (!pushEvent(context.events, translated))
            {
                context.last_driver_error = -ENOBUFS;
                context.last_result = AnalogFabricResult::resource_exhausted;
            }
        }

        void saadcIrq(const void *) { nrfx_saadc_irq_handler(); }
        void pwm20Irq(const void *) { nrfx_pwm_irq_handler(&pwm_drivers[0]); }
        void pwm21Irq(const void *) { nrfx_pwm_irq_handler(&pwm_drivers[1]); }
        void pwm22Irq(const void *) { nrfx_pwm_irq_handler(&pwm_drivers[2]); }

        int connectAnalogFabricIrqs()
        {
            IRQ_CONNECT(SAADC_IRQn, IRQ_PRIO_LOWEST, saadcIrq, nullptr, 0);
            IRQ_CONNECT(PWM20_IRQn, IRQ_PRIO_LOWEST, pwm20Irq, nullptr, 0);
            IRQ_CONNECT(PWM21_IRQn, IRQ_PRIO_LOWEST, pwm21Irq, nullptr, 0);
            IRQ_CONNECT(PWM22_IRQn, IRQ_PRIO_LOWEST, pwm22Irq, nullptr, 0);
            return 0;
        }

        SYS_INIT(connectAnalogFabricIrqs, APPLICATION,
                 CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace

    AnalogFabricState SaadcFabric::state() const noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const auto value = saadc_context.state;
        k_mutex_unlock(&analog_fabric_mutex);
        return value;
    }

    AnalogFabricResult SaadcFabric::lastResult() const noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const auto value = saadc_context.last_result;
        k_mutex_unlock(&analog_fabric_mutex);
        return value;
    }

    int SaadcFabric::lastDriverError() const noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const int value = saadc_context.last_driver_error;
        k_mutex_unlock(&analog_fabric_mutex);
        return value;
    }

    AnalogFabricResult
    SaadcFabric::configure(const SaadcConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        if (configuration.channels == nullptr || configuration.channel_count == 0U ||
            configuration.channel_count > saadc_channel_capacity ||
            !validResolution(configuration.resolution_bits) ||
            !validOversample(configuration.oversample) ||
            configuration.interval_us > NRFX_SAADC_INTERNAL_TIMER_INTERVAL_MAX_US ||
            (configuration.interval_us != 0U && configuration.channel_count != 1U))
            return AnalogFabricResult::invalid_argument;

        bool used_positive[saadc_channel_capacity]{};
        for (std::size_t index = 0U; index < configuration.channel_count; ++index)
        {
            const auto &channel = configuration.channels[index];
            if (static_cast<unsigned>(channel.gain) > static_cast<unsigned>(SaadcGain::one_quarter) ||
                !supportedInput(channel.positive) ||
                (channel.negative != SaadcInput::disabled &&
                 (!externalInput(channel.positive) ||
                  !externalInput(channel.negative) ||
                  channel.negative == channel.positive)))
                return AnalogFabricResult::invalid_argument;
            if (externalInput(channel.positive))
            {
                const auto number = static_cast<std::uint8_t>(channel.positive);
                if (used_positive[number] ||
                    pinForAnalogInput(channel.positive) == nullptr)
                    return AnalogFabricResult::invalid_argument;
                used_positive[number] = true;
            }
        }

        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        if (saadc_context.state == AnalogFabricState::active ||
            saadc_context.state == AnalogFabricState::stopping)
        {
            record(saadc_context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        for (std::size_t index = 0U; index < configuration.channel_count; ++index)
            saadc_context.channels[index] = configuration.channels[index];
        saadc_context.channel_count = configuration.channel_count;
        saadc_context.resolution_bits = configuration.resolution_bits;
        saadc_context.oversample = configuration.oversample;
        saadc_context.interval_us = configuration.interval_us;
        saadc_context.state = AnalogFabricState::configured;
        clearEvents(saadc_context.events);
        record(saadc_context, AnalogFabricResult::success);
        k_mutex_unlock(&analog_fabric_mutex);
        return AnalogFabricResult::success;
    }

    AnalogFabricResult SaadcFabric::start(std::int16_t *first_buffer,
                                          std::size_t first_samples,
                                          std::int16_t *next_buffer,
                                          std::size_t next_samples) noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        if (first_buffer == nullptr || first_samples == 0U ||
            first_samples > UINT16_MAX ||
            (next_buffer == nullptr) != (next_samples == 0U) ||
            next_samples > UINT16_MAX)
            return AnalogFabricResult::invalid_argument;

        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto &context = saadc_context;
        if (context.state != AnalogFabricState::configured)
        {
            record(context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        if ((first_samples % context.channel_count) != 0U ||
            (next_samples != 0U && (next_samples % context.channel_count) != 0U))
        {
            record(context, AnalogFabricResult::invalid_argument);
            k_mutex_unlock(&analog_fabric_mutex);
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
                    continue;
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
                    resources[resource_count++] = resource;
            }
        }
        resources[resource_count++] = internal::dmaMemoryIoResource(
            first_buffer,
            static_cast<std::uint32_t>(first_samples * sizeof(*first_buffer)));
        if (next_buffer != nullptr)
        {
            resources[resource_count++] = internal::dmaMemoryIoResource(
                next_buffer,
                static_cast<std::uint32_t>(next_samples * sizeof(*next_buffer)));
        }

        context.lease = {};
        const IoResourceResult reserve_result = internal::reserveIoResources(
            {IoOwnerKind::adc, 0U}, resources, resource_count,
            IoAcquirePolicy::exclusive, context.lease);
        if (reserve_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(reserve_result);
            record(context, result);
            k_mutex_unlock(&analog_fabric_mutex);
            return result;
        }

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
                    nrfx_saadc_channel_t channel = NRFX_SAADC_DEFAULT_CHANNEL_SE(
                        positive, static_cast<std::uint8_t>(index));
                    channels[index] = channel;
                }
                else
                {
                    nrfx_saadc_channel_t channel = NRFX_SAADC_DEFAULT_CHANNEL_DIFFERENTIAL(
                        positive, negative, static_cast<std::uint8_t>(index));
                    channels[index] = channel;
                }
                // This core targets nRF54L15. Assert the complete encoding below
                // instead of relying on another SoC's gain enum order.
                static_assert(SAADC_CH_CONFIG_GAIN_Gain2 == 0 && SAADC_CH_CONFIG_GAIN_Gain1 == 1 &&
                              SAADC_CH_CONFIG_GAIN_Gain2_3 == 2 && SAADC_CH_CONFIG_GAIN_Gain2_4 == 3 &&
                              SAADC_CH_CONFIG_GAIN_Gain2_5 == 4 && SAADC_CH_CONFIG_GAIN_Gain2_6 == 5 &&
                              SAADC_CH_CONFIG_GAIN_Gain2_7 == 6 && SAADC_CH_CONFIG_GAIN_Gain2_8 == 7);
                channels[index].channel_config.gain = static_cast<nrf_saadc_gain_t>(context.channels[index].gain);
            }
            driver_error = nrfx_saadc_channels_config(channels, context.channel_count);
        }
        if (driver_error == 0)
        {
            nrfx_saadc_adv_config_t advanced = NRFX_SAADC_DEFAULT_ADV_CONFIG;
            advanced.oversampling = saadcOversample(context.oversample);
            advanced.burst = context.oversample == 1U ? NRF_SAADC_BURST_DISABLED
                                                      : NRF_SAADC_BURST_ENABLED;
            advanced.internal_timer_cc =
                context.interval_us == 0U
                    ? 0U
                    : nrfx_saadc_interval_to_cc(context.interval_us);
            advanced.start_on_end = true;
            const std::uint32_t mask = (1UL << context.channel_count) - 1UL;
            driver_error = nrfx_saadc_advanced_mode_set(
                mask, saadcResolution(context.resolution_bits), &advanced,
                saadcEventHandler);
        }
        if (driver_error == 0)
            driver_error = nrfx_saadc_buffer_set(first_buffer, first_samples);
        if (driver_error == 0 && next_buffer != nullptr)
            driver_error = nrfx_saadc_buffer_set(next_buffer, next_samples);
        if (driver_error == 0)
            driver_error = nrfx_saadc_mode_trigger();

        if (driver_error != 0)
        {
            if (nrfx_saadc_init_check())
                nrfx_saadc_uninit();
            (void)internal::rollbackIoResources(context.lease);
            context.lease = {};
            record(context, AnalogFabricResult::driver_error, driver_error);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::driver_error;
        }
        const IoResourceResult commit_result =
            internal::commitIoResources(context.lease);
        if (commit_result != IoResourceResult::success)
        {
            nrfx_saadc_abort();
            nrfx_saadc_uninit();
            (void)internal::rollbackIoResources(context.lease);
            context.lease = {};
            context.state = AnalogFabricState::faulted;
            record(context, AnalogFabricResult::release_failed);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::release_failed;
        }
        context.state = AnalogFabricState::active;
        record(context, AnalogFabricResult::success);
        k_mutex_unlock(&analog_fabric_mutex);
        return AnalogFabricResult::success;
    }

    AnalogFabricResult SaadcFabric::queueBuffer(std::int16_t *buffer,
                                                std::size_t samples) noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        if (buffer == nullptr || samples == 0U || samples > UINT16_MAX)
            return AnalogFabricResult::invalid_argument;
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto &context = saadc_context;
        if (context.state != AnalogFabricState::active)
        {
            record(context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        if ((samples % context.channel_count) != 0U)
        {
            record(context, AnalogFabricResult::invalid_argument);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::invalid_argument;
        }
        DmaLeaseSlot *slot = nullptr;
        const AnalogFabricResult reserve_result =
            reserveSaadcDma(context, buffer, samples * sizeof(*buffer), slot);
        if (reserve_result != AnalogFabricResult::success)
        {
            record(context, reserve_result);
            k_mutex_unlock(&analog_fabric_mutex);
            return reserve_result;
        }
        const int error = nrfx_saadc_buffer_set(buffer, samples);
        if (error != 0)
        {
            rollbackSaadcDma(*slot);
            record(context, AnalogFabricResult::driver_error, error);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::driver_error;
        }
        const IoResourceResult commit_result = commitSaadcDma(*slot);
        const auto result = commit_result == IoResourceResult::success
                                ? AnalogFabricResult::success
                                : AnalogFabricResult::release_failed;
        if (commit_result != IoResourceResult::success)
            context.state = AnalogFabricState::faulted;
        record(context, result, error);
        k_mutex_unlock(&analog_fabric_mutex);
        return result;
    }

    AnalogFabricResult SaadcFabric::sample() noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto &context = saadc_context;
        const unsigned int irq_key = irq_lock();
        if (context.state != AnalogFabricState::active ||
            context.interval_us != 0U || atomic_get(&context.sample_ready) == 0)
        {
            irq_unlock(irq_key);
            record(context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        // Advanced non-blocking mode_trigger() only arms the buffer. Once
        // READY, manual conversion requires SAMPLE, not a second START.
        nrfy_saadc_sample_start(NRF_SAADC, nullptr);
        irq_unlock(irq_key);
        const auto result = AnalogFabricResult::success;
        record(context, result);
        k_mutex_unlock(&analog_fabric_mutex);
        return result;
    }

    AnalogFabricResult SaadcFabric::calibrate() noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto &context = saadc_context;
        if (context.state != AnalogFabricState::active)
        {
            record(context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        const int error = nrfx_saadc_offset_calibrate(saadcEventHandler);
        const auto result = error == 0 ? AnalogFabricResult::success
                                       : AnalogFabricResult::driver_error;
        record(context, result, error);
        k_mutex_unlock(&analog_fabric_mutex);
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
            return AnalogFabricResult::invalid_context;
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto &context = saadc_context;
        if (context.state != AnalogFabricState::active &&
            context.state != AnalogFabricState::stopping)
        {
            record(context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        context.state = AnalogFabricState::stopping;
        atomic_clear(&context.sample_ready);
        // nrfx consumes STOPPED in its IRQ and disables SAADC on FINISHED.
        // A completed one-shot is already stopped; do not wait for a stale bit.
        if (nrf_saadc_enable_check(NRF_SAADC))
            nrfx_saadc_abort();
        std::uint32_t waited = 0U;
        while (nrf_saadc_enable_check(NRF_SAADC) &&
               !nrf_saadc_event_check(NRF_SAADC, NRF_SAADC_EVENT_STOPPED) &&
               waited < timeout_us)
        {
            k_busy_wait(10U);
            waited += 10U;
        }
        const bool stopped =
            !nrf_saadc_enable_check(NRF_SAADC) ||
            nrf_saadc_event_check(NRF_SAADC, NRF_SAADC_EVENT_STOPPED);
        if (!stopped)
        {
            // Keep both the peripheral and DMA leases until STOP is proven.
            // The caller may retry stop(); configure()/start() remain blocked.
            record(context, AnalogFabricResult::stop_timeout, -ETIMEDOUT);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::stop_timeout;
        }
        nrfx_saadc_uninit();
        IoResourceResult release_result = internal::releaseIoResources(context.lease);
        context.lease = {};
        for (auto &slot : context.dma_leases)
        {
            const IoResourceResult slot_result = releaseSaadcDma(slot);
            if (slot_result != IoResourceResult::success)
                release_result = slot_result;
        }
        if (release_result != IoResourceResult::success)
        {
            context.state = AnalogFabricState::faulted;
            record(context, AnalogFabricResult::release_failed);
        }
        else
        {
            context.state = AnalogFabricState::configured;
            record(context, AnalogFabricResult::success);
        }
        const auto result = context.last_result;
        k_mutex_unlock(&analog_fabric_mutex);
        return result;
    }

    bool SaadcFabric::takeEvent(SaadcEvent &event) noexcept
    {
        if (k_is_in_isr())
            return false;
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const bool present = popEvent(saadc_context.events, event);
        if (present && event.type == SaadcEventType::buffer_complete)
        {
            const IoResourceResult release_result =
                releaseSaadcDmaFor(saadc_context, event.buffer);
            if (release_result != IoResourceResult::success &&
                release_result != IoResourceResult::stale_lease)
            {
                saadc_context.state = AnalogFabricState::faulted;
                record(saadc_context, AnalogFabricResult::release_failed);
            }
        }
        k_mutex_unlock(&analog_fabric_mutex);
        return present;
    }

    std::uint8_t PwmSequenceFabric::instance() const noexcept { return instance_; }

    AnalogFabricState PwmSequenceFabric::state() const noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const auto *const context = pwmContext(instance_);
        const auto value =
            context != nullptr ? context->state : AnalogFabricState::faulted;
        k_mutex_unlock(&analog_fabric_mutex);
        return value;
    }

    AnalogFabricResult PwmSequenceFabric::lastResult() const noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const auto *const context = pwmContext(instance_);
        const auto value = context != nullptr
                               ? context->last_result
                               : AnalogFabricResult::unsupported_instance;
        k_mutex_unlock(&analog_fabric_mutex);
        return value;
    }

    int PwmSequenceFabric::lastDriverError() const noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const auto *const context = pwmContext(instance_);
        const int value = context != nullptr ? context->last_driver_error : -ENODEV;
        k_mutex_unlock(&analog_fabric_mutex);
        return value;
    }

    AnalogFabricResult PwmSequenceFabric::configure(
        const PwmSequenceConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        if (configuration.top_value < 3U || configuration.top_value > 32767U)
            return AnalogFabricResult::invalid_argument;
        const PinRoute route = pwmRoute(instance_);
        if (route == PinRoute::none)
            return AnalogFabricResult::unsupported_instance;

        bool has_output = false;
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            const pin_size_t pin = configuration.output_pins[index];
            if (pin == disconnected_pin)
                continue;
            has_output = true;
            const auto *const description = internal::pinDescription(pin);
            if (description == nullptr || description->canonical_pin != pin ||
                description->policy == PinPolicy::system_reserved ||
                !internal::hasPinCapability(description->capabilities,
                                            PinCapability::pwm_output) ||
                !internal::hasPinRoute(description->routes, route) ||
                physicalPin(*description) == NRF_PWM_PIN_NOT_CONNECTED)
                return AnalogFabricResult::unsupported_route;
            for (std::size_t prior = 0U; prior < index; ++prior)
            {
                if (configuration.output_pins[prior] == pin)
                    return AnalogFabricResult::invalid_argument;
            }
        }
        if (!has_output)
            return AnalogFabricResult::invalid_argument;

        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto *const context = pwmContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::unsupported_instance;
        }
        if (context->state == AnalogFabricState::active ||
            context->state == AnalogFabricState::stopping)
        {
            record(*context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        context->configuration = configuration;
        context->state = AnalogFabricState::configured;
        context->start_task = 0U;
        clearEvents(context->events);
        record(*context, AnalogFabricResult::success);
        k_mutex_unlock(&analog_fabric_mutex);
        return AnalogFabricResult::success;
    }

    AnalogFabricResult PwmSequenceFabric::play(const PwmSequenceBuffer &sequence0,
                                               const PwmSequenceBuffer *sequence1,
                                               std::uint16_t playback_count,
                                               bool loop,
                                               bool start_via_task) noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        if (sequence0.values == nullptr || playback_count == 0U ||
            (loop && playback_count != 1U))
            return AnalogFabricResult::invalid_argument;

        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto *const context = pwmContext(instance_);
        auto *const driver = pwmDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::unsupported_instance;
        }
        if (context->state != AnalogFabricState::configured)
        {
            record(*context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        if (!validPwmValueCount(context->configuration.load, sequence0.value_count) ||
            (sequence1 != nullptr && (sequence1->values == nullptr ||
                                      !validPwmValueCount(context->configuration.load,
                                                          sequence1->value_count))))
        {
            record(*context, AnalogFabricResult::invalid_argument);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::invalid_argument;
        }

        IoResourceId resources[internal::io_resource_lease_capacity]{};
        std::size_t resource_count = 0U;
        resources[resource_count++] = internal::peripheralIoResource(
            IoResourceKind::pwm_block, instance_, driver->p_reg);
        for (const pin_size_t pin : context->configuration.output_pins)
        {
            if (pin == disconnected_pin)
                continue;
            const auto *const description = internal::pinDescription(pin);
            resources[resource_count++] = internal::gpioIoResource(description->gpio);
        }
        resources[resource_count++] = internal::dmaMemoryIoResource(
            sequence0.values, static_cast<std::uint32_t>(sequence0.value_count *
                                                         sizeof(std::uint16_t)));
        if (sequence1 != nullptr)
        {
            resources[resource_count++] = internal::dmaMemoryIoResource(
                sequence1->values, static_cast<std::uint32_t>(sequence1->value_count *
                                                              sizeof(std::uint16_t)));
        }
        context->lease = {};
        const IoResourceResult reserve_result = internal::reserveIoResources(
            {IoOwnerKind::pwm, instance_}, resources, resource_count,
            IoAcquirePolicy::exclusive, context->lease);
        if (reserve_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(reserve_result);
            record(*context, result);
            k_mutex_unlock(&analog_fabric_mutex);
            return result;
        }

        nrfx_pwm_config_t driver_configuration = NRFX_PWM_DEFAULT_CONFIG(
            NRF_PWM_PIN_NOT_CONNECTED, NRF_PWM_PIN_NOT_CONNECTED,
            NRF_PWM_PIN_NOT_CONNECTED, NRF_PWM_PIN_NOT_CONNECTED);
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            const pin_size_t pin = context->configuration.output_pins[index];
            if (pin != disconnected_pin)
            {
                driver_configuration.output_pins[index] =
                    physicalPin(*internal::pinDescription(pin));
                driver_configuration.pin_inverted[index] =
                    context->configuration.inverted[index];
            }
        }
        driver_configuration.irq_priority = IRQ_PRIO_LOWEST;
        driver_configuration.base_clock = NRF_PWM_CLK_1MHz;
        driver_configuration.count_mode = NRF_PWM_MODE_UP;
        driver_configuration.top_value = context->configuration.top_value;
        driver_configuration.load_mode = pwmLoad(context->configuration.load);
        driver_configuration.step_mode = context->configuration.triggered_step
                                             ? NRF_PWM_STEP_TRIGGERED
                                             : NRF_PWM_STEP_AUTO;

        int driver_error =
            nrfx_pwm_init(driver, &driver_configuration, pwmEventHandler, context);
        nrf_pwm_sequence_t first{{.p_raw = sequence0.values},
                                 static_cast<std::uint16_t>(sequence0.value_count),
                                 sequence0.repeats,
                                 sequence0.end_delay};
        nrf_pwm_sequence_t next{};
        if (sequence1 != nullptr)
        {
            next.values.p_raw = sequence1->values;
            next.length = static_cast<std::uint16_t>(sequence1->value_count);
            next.repeats = sequence1->repeats;
            next.end_delay = sequence1->end_delay;
        }
        if (driver_error == 0)
        {
            std::uint32_t flags =
                NRFX_PWM_FLAG_SIGNAL_END_SEQ0 | NRFX_PWM_FLAG_SIGNAL_END_SEQ1;
            flags |= loop ? NRFX_PWM_FLAG_LOOP : NRFX_PWM_FLAG_STOP;
            if (start_via_task)
                flags |= NRFX_PWM_FLAG_START_VIA_TASK;
            context->start_task =
                sequence1 == nullptr
                    ? nrfx_pwm_simple_playback(driver, &first, playback_count, flags)
                    : nrfx_pwm_complex_playback(driver, &first, &next, playback_count,
                                                flags);
        }
        if (driver_error != 0)
        {
            if (nrfx_pwm_init_check(driver))
                nrfx_pwm_uninit(driver);
            (void)internal::rollbackIoResources(context->lease);
            context->lease = {};
            record(*context, AnalogFabricResult::driver_error, driver_error);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::driver_error;
        }
        const IoResourceResult commit_result =
            internal::commitIoResources(context->lease);
        if (commit_result != IoResourceResult::success)
        {
            (void)nrfx_pwm_stop(driver, false);
            nrfx_pwm_uninit(driver);
            (void)internal::rollbackIoResources(context->lease);
            context->lease = {};
            context->state = AnalogFabricState::faulted;
            record(*context, AnalogFabricResult::release_failed);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::release_failed;
        }
        context->state = AnalogFabricState::active;
        record(*context, AnalogFabricResult::success);
        k_mutex_unlock(&analog_fabric_mutex);
        return AnalogFabricResult::success;
    }

    std::uintptr_t PwmSequenceFabric::startTaskAddress() const noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        const auto *const context = pwmContext(instance_);
        const std::uintptr_t value = context != nullptr ? context->start_task : 0U;
        k_mutex_unlock(&analog_fabric_mutex);
        return value;
    }

    AnalogFabricResult PwmSequenceFabric::step() noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto *const context = pwmContext(instance_);
        auto *const driver = pwmDriver(instance_);
        if (context == nullptr || driver == nullptr ||
            context->state != AnalogFabricState::active ||
            !context->configuration.triggered_step)
        {
            if (context != nullptr)
                record(*context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        nrfx_pwm_step(driver);
        record(*context, AnalogFabricResult::success);
        k_mutex_unlock(&analog_fabric_mutex);
        return AnalogFabricResult::success;
    }

    AnalogFabricResult PwmSequenceFabric::stop(std::uint32_t timeout_us) noexcept
    {
        if (k_is_in_isr())
            return AnalogFabricResult::invalid_context;
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
        auto *const context = pwmContext(instance_);
        auto *const driver = pwmDriver(instance_);
        if (context == nullptr || driver == nullptr ||
            context->state != AnalogFabricState::active)
        {
            if (context != nullptr)
                record(*context, AnalogFabricResult::wrong_state);
            k_mutex_unlock(&analog_fabric_mutex);
            return AnalogFabricResult::wrong_state;
        }
        context->state = AnalogFabricState::stopping;
        bool stopped = nrfx_pwm_stop(driver, false);
        std::uint32_t waited = 0U;
        while (!stopped && waited < timeout_us)
        {
            k_busy_wait(10U);
            waited += 10U;
            stopped = nrfx_pwm_stopped_check(driver);
        }
        nrfx_pwm_uninit(driver);
        const IoResourceResult release_result =
            internal::releaseIoResources(context->lease);
        context->lease = {};
        context->start_task = 0U;
        if (release_result != IoResourceResult::success)
        {
            context->state = AnalogFabricState::faulted;
            record(*context, AnalogFabricResult::release_failed);
        }
        else if (!stopped)
        {
            context->state = AnalogFabricState::faulted;
            record(*context, AnalogFabricResult::stop_timeout, -ETIMEDOUT);
        }
        else
        {
            context->state = AnalogFabricState::configured;
            record(*context, AnalogFabricResult::success);
        }
        const auto result = context->last_result;
        k_mutex_unlock(&analog_fabric_mutex);
        return result;
    }

    bool PwmSequenceFabric::takeEvent(PwmSequenceEvent &event) noexcept
    {
        auto *const context = pwmContext(instance_);
        return context != nullptr && popEvent(context->events, event);
    }

    SaadcFabric &AnalogFabric::saadc() noexcept
    {
        static SaadcFabric handle;
        return handle;
    }

    PwmSequenceFabric *AnalogFabric::pwm(std::uint8_t instance) noexcept
    {
        static PwmSequenceFabric handles[3]{
            PwmSequenceFabric(20U), PwmSequenceFabric(21U), PwmSequenceFabric(22U)};
        switch (instance)
        {
        case 20U:
            return &handles[0];
        case 21U:
            return &handles[1];
        case 22U:
            return &handles[2];
        default:
            return nullptr;
        }
    }

    AnalogFabric &analogFabric() noexcept
    {
        static AnalogFabric fabric;
        return fabric;
    }

} // namespace nucode::arduino
