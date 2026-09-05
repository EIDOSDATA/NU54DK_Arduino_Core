/** @file @brief PwmSequence의 private context·driver·IRQ와 lifecycle을 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#include "AnalogFabricInternal.h"
#include <hal/nrf_pwm.h>
#include <nrfx_pwm.h>
namespace nucode::arduino
{
    using namespace internal::analog;
    namespace
    {
        struct PwmContext
        {
            std::uint8_t instance{0U};
            PwmSequenceConfiguration configuration{};
            IoResourceLease lease{};
            EventQueue<PwmSequenceEvent> events{};
            AnalogFabricState state{AnalogFabricState::inactive};
            internal::FabricDiagnostic<AnalogFabricResult> diagnostics{};
            internal::FabricStopSignal stop_signal{};
            bool stop_waiting{false};
            std::uintptr_t start_task{0U};
        };

        PwmContext pwm_contexts[3]{{20U}, {21U}, {22U}};
        nrfx_pwm_t pwm_drivers[3]{NRFX_PWM_INSTANCE(NRF_PWM20), NRFX_PWM_INSTANCE(NRF_PWM21),
                                  NRFX_PWM_INSTANCE(NRF_PWM22)};

        [[nodiscard]] PwmContext *pwmContext(std::uint8_t instance) noexcept
        {
            for (auto &context : pwm_contexts)
            {
                if (context.instance == instance)
                {
                    return &context;
                }
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
            {
                return NRF_GPIO_PIN_MAP(0U, description.gpio.pin);
            }
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio1))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio1)))
            {
                return NRF_GPIO_PIN_MAP(1U, description.gpio.pin);
            }
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio2))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio2)))
            {
                return NRF_GPIO_PIN_MAP(2U, description.gpio.pin);
            }
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

        [[nodiscard]] bool validPwmValueCount(PwmSequenceLoad load, std::size_t count) noexcept
        {
            /** @brief nRF54L15 PWM DMA MAXCNT는 uint16_t 개수가 아니라 byte 단위입니다. */
            if (!internal::dmaCountFits(count, PWM_DMA_SEQ_MAXCNT_MAXCNT_Msk,
                                        sizeof(std::uint16_t)))
            {
                return false;
            }
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
                context.stop_signal.notifyStopped();
                translated.type = PwmSequenceEventType::stopped;
                break;
            default:
                translated.type = PwmSequenceEventType::error;
                translated.driver_error = -EIO;
                break;
            }
            if (!pushEvent(context.events, translated))
            {
                record(context, AnalogFabricResult::resource_exhausted, -ENOBUFS);
            }
        }
    } // namespace
    std::uint8_t PwmSequenceFabric::instance() const noexcept
    {
        return instance_;
    }

    AnalogFabricState PwmSequenceFabric::state() const noexcept
    {
        lockAnalog();
        const auto *const context = pwmContext(instance_);
        const auto value = context != nullptr ? context->state : AnalogFabricState::faulted;
        unlockAnalog();
        return value;
    }

    AnalogFabricResult PwmSequenceFabric::lastResult() const noexcept
    {
        lockAnalog();
        const auto *const context = pwmContext(instance_);
        const auto value = context != nullptr ? context->diagnostics.snapshot().result
                                              : AnalogFabricResult::unsupported_instance;
        unlockAnalog();
        return value;
    }

    int PwmSequenceFabric::lastDriverError() const noexcept
    {
        lockAnalog();
        const auto *const context = pwmContext(instance_);
        const int value =
            context != nullptr ? context->diagnostics.snapshot().driver_error : -ENODEV;
        unlockAnalog();
        return value;
    }

    AnalogFabricResult
    PwmSequenceFabric::configure(const PwmSequenceConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        if (configuration.top_value < 3U || configuration.top_value > 32767U)
        {
            return AnalogFabricResult::invalid_argument;
        }
        const PinRoute route = pwmRoute(instance_);
        if (route == PinRoute::none)
        {
            return AnalogFabricResult::unsupported_instance;
        }

        bool has_output = false;
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            const pin_size_t pin = configuration.output_pins[index];
            if (pin == disconnected_pin)
            {
                continue;
            }
            has_output = true;
            const auto *const description = internal::pinDescription(pin);
            if (description == nullptr || description->canonical_pin != pin ||
                description->policy == PinPolicy::system_reserved ||
                !internal::hasPinCapability(description->capabilities, PinCapability::pwm_output) ||
                !internal::hasPinRoute(description->routes, route) ||
                physicalPin(*description) == NRF_PWM_PIN_NOT_CONNECTED)
            {
                return AnalogFabricResult::unsupported_route;
            }
            for (std::size_t prior = 0U; prior < index; ++prior)
            {
                if (configuration.output_pins[prior] == pin)
                {
                    return AnalogFabricResult::invalid_argument;
                }
            }
        }
        if (!has_output)
        {
            return AnalogFabricResult::invalid_argument;
        }

        lockAnalog();
        auto *const context = pwmContext(instance_);
        if (context == nullptr)
        {
            unlockAnalog();
            return AnalogFabricResult::unsupported_instance;
        }
        if (context->state == AnalogFabricState::active ||
            context->state == AnalogFabricState::stopping ||
            context->state == AnalogFabricState::faulted)
        {
            record(*context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        context->configuration = configuration;
        context->state = AnalogFabricState::configured;
        context->start_task = 0U;
        clearEvents(context->events);
        record(*context, AnalogFabricResult::success);
        unlockAnalog();
        return AnalogFabricResult::success;
    }

    AnalogFabricResult PwmSequenceFabric::play(const PwmSequenceBuffer &sequence0,
                                               const PwmSequenceBuffer *sequence1,
                                               std::uint16_t playback_count, bool loop,
                                               bool start_via_task) noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        if (sequence0.values == nullptr || playback_count == 0U || (loop && playback_count != 1U))
        {
            return AnalogFabricResult::invalid_argument;
        }

        lockAnalog();
        auto *const context = pwmContext(instance_);
        auto *const driver = pwmDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            unlockAnalog();
            return AnalogFabricResult::unsupported_instance;
        }
        if (context->state != AnalogFabricState::configured)
        {
            record(*context, AnalogFabricResult::wrong_state);
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        if (!validPwmValueCount(context->configuration.load, sequence0.value_count) ||
            !internal::dmaMemoryRangeValid(sequence0.values,
                                           sequence0.value_count * sizeof(std::uint16_t),
                                           alignof(std::uint16_t)) ||
            (sequence1 != nullptr &&
             (sequence1->values == nullptr ||
              !validPwmValueCount(context->configuration.load, sequence1->value_count) ||
              !internal::dmaMemoryRangeValid(sequence1->values,
                                             sequence1->value_count * sizeof(std::uint16_t),
                                             alignof(std::uint16_t)))))
        {
            record(*context, AnalogFabricResult::invalid_argument);
            unlockAnalog();
            return AnalogFabricResult::invalid_argument;
        }

        IoResourceId resources[internal::io_resource_lease_capacity]{};
        std::size_t resource_count = 0U;
        resources[resource_count++] =
            internal::peripheralIoResource(IoResourceKind::pwm_block, instance_, driver->p_reg);
        for (const pin_size_t pin : context->configuration.output_pins)
        {
            if (pin == disconnected_pin)
            {
                continue;
            }
            const auto *const description = internal::pinDescription(pin);
            resources[resource_count++] = internal::gpioIoResource(description->gpio);
        }
        resources[resource_count++] = internal::dmaMemoryIoResource(
            sequence0.values,
            static_cast<std::uint32_t>(sequence0.value_count * sizeof(std::uint16_t)));
        if (sequence1 != nullptr)
        {
            resources[resource_count++] = internal::dmaMemoryIoResource(
                sequence1->values,
                static_cast<std::uint32_t>(sequence1->value_count * sizeof(std::uint16_t)));
        }
        context->lease = {};
        const IoResourceResult reserve_result =
            internal::reserveIoResources({IoOwnerKind::pwm, instance_}, resources, resource_count,
                                         IoAcquirePolicy::exclusive, context->lease);
        if (reserve_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(reserve_result);
            record(*context, result);
            unlockAnalog();
            return result;
        }

        context->stop_signal.beginRun();
        nrfx_pwm_config_t driver_configuration =
            NRFX_PWM_DEFAULT_CONFIG(NRF_PWM_PIN_NOT_CONNECTED, NRF_PWM_PIN_NOT_CONNECTED,
                                    NRF_PWM_PIN_NOT_CONNECTED, NRF_PWM_PIN_NOT_CONNECTED);
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            const pin_size_t pin = context->configuration.output_pins[index];
            if (pin != disconnected_pin)
            {
                driver_configuration.output_pins[index] =
                    physicalPin(*internal::pinDescription(pin));
                driver_configuration.pin_inverted[index] = context->configuration.inverted[index];
            }
        }
        driver_configuration.irq_priority = IRQ_PRIO_LOWEST;
        driver_configuration.base_clock = NRF_PWM_CLK_1MHz;
        driver_configuration.count_mode = NRF_PWM_MODE_UP;
        driver_configuration.top_value = context->configuration.top_value;
        driver_configuration.load_mode = pwmLoad(context->configuration.load);
        driver_configuration.step_mode =
            context->configuration.triggered_step ? NRF_PWM_STEP_TRIGGERED : NRF_PWM_STEP_AUTO;

        int driver_error = nrfx_pwm_init(driver, &driver_configuration, pwmEventHandler, context);
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
            std::uint32_t flags = NRFX_PWM_FLAG_SIGNAL_END_SEQ0 | NRFX_PWM_FLAG_SIGNAL_END_SEQ1;
            flags |= loop ? NRFX_PWM_FLAG_LOOP : NRFX_PWM_FLAG_STOP;
            if (start_via_task)
            {
                flags |= NRFX_PWM_FLAG_START_VIA_TASK;
            }
            context->start_task =
                sequence1 == nullptr
                    ? nrfx_pwm_simple_playback(driver, &first, playback_count, flags)
                    : nrfx_pwm_complex_playback(driver, &first, &next, playback_count, flags);
        }
        if (driver_error != 0)
        {
            if (nrfx_pwm_init_check(driver))
            {
                nrfx_pwm_uninit(driver);
            }
            (void)internal::rollbackIoResources(context->lease);
            context->lease = {};
            record(*context, AnalogFabricResult::driver_error, driver_error);
            unlockAnalog();
            return AnalogFabricResult::driver_error;
        }
        const IoResourceResult commit_result = internal::commitIoResources(context->lease);
        if (commit_result != IoResourceResult::success)
        {
            context->state = AnalogFabricState::stopping;
            (void)context->stop_signal.arm();
            (void)nrfx_pwm_stop(driver, false);
            record(*context, AnalogFabricResult::release_failed);
            unlockAnalog();
            return AnalogFabricResult::release_failed;
        }
        context->state = AnalogFabricState::active;
        record(*context, AnalogFabricResult::success);
        unlockAnalog();
        return AnalogFabricResult::success;
    }

    std::uintptr_t PwmSequenceFabric::startTaskAddress() const noexcept
    {
        lockAnalog();
        const auto *const context = pwmContext(instance_);
        const std::uintptr_t value = context != nullptr ? context->start_task : 0U;
        unlockAnalog();
        return value;
    }

    AnalogFabricResult PwmSequenceFabric::step() noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        lockAnalog();
        auto *const context = pwmContext(instance_);
        auto *const driver = pwmDriver(instance_);
        if (context == nullptr || driver == nullptr ||
            context->state != AnalogFabricState::active || !context->configuration.triggered_step)
        {
            if (context != nullptr)
            {
                record(*context, AnalogFabricResult::wrong_state);
            }
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        nrfx_pwm_step(driver);
        record(*context, AnalogFabricResult::success);
        unlockAnalog();
        return AnalogFabricResult::success;
    }

    AnalogFabricResult PwmSequenceFabric::stop(std::uint32_t timeout_us) noexcept
    {
        if (k_is_in_isr())
        {
            return AnalogFabricResult::invalid_context;
        }
        lockAnalog();
        auto *const context = pwmContext(instance_);
        auto *const driver = pwmDriver(instance_);
        if (context == nullptr || driver == nullptr ||
            (context->state != AnalogFabricState::active &&
             context->state != AnalogFabricState::stopping) ||
            context->stop_waiting)
        {
            if (context != nullptr)
            {
                record(*context, AnalogFabricResult::wrong_state);
            }
            unlockAnalog();
            return AnalogFabricResult::wrong_state;
        }
        context->state = AnalogFabricState::stopping;
        context->stop_waiting = true;
        const auto generation = context->stop_signal.arm();
        unlockAnalog();
        (void)nrfx_pwm_stop(driver, false);
        const bool stopped = internal::waitFabricStop(
            [&]
            {
                return context->stop_signal.completed(generation) || nrfx_pwm_stopped_check(driver);
            },
            timeout_us);
        lockAnalog();
        context->stop_waiting = false;
        if (!stopped)
        {
            /** @brief STOP 미확인 상태에서 uninit이나 lease 반환을 수행하지 않습니다. */
            record(*context, AnalogFabricResult::stop_timeout, -ETIMEDOUT);
            unlockAnalog();
            return AnalogFabricResult::stop_timeout;
        }
        nrfx_pwm_uninit(driver);
        const auto release_result = context->lease.phase == internal::IoLeasePhase::reserved
                                        ? internal::rollbackIoResources(context->lease)
                                        : internal::releaseIoResources(context->lease);
        if (release_result == IoResourceResult::success)
        {
            context->lease = {};
        }
        context->start_task = 0U;
        const auto result = release_result == IoResourceResult::success
                                ? AnalogFabricResult::success
                                : AnalogFabricResult::release_failed;
        context->state = result == AnalogFabricResult::success ? AnalogFabricState::configured
                                                               : AnalogFabricState::faulted;
        record(*context, result);
        unlockAnalog();
        return result;
    }

    bool PwmSequenceFabric::takeEvent(PwmSequenceEvent &event) noexcept
    {
        auto *const context = pwmContext(instance_);
        const bool available = context != nullptr && popEvent(context->events, event);
        if (available && event.driver_error == -ENOBUFS)
        {
            event.instance = instance_;
        }
        return available;
    }

} // namespace nucode::arduino
namespace nucode::arduino::internal::analog
{
    void pwm20Irq(const void *)
    {
        nrfx_pwm_irq_handler(&pwm_drivers[0]);
    }

    void pwm21Irq(const void *)
    {
        nrfx_pwm_irq_handler(&pwm_drivers[1]);
    }

    void pwm22Irq(const void *)
    {
        nrfx_pwm_irq_handler(&pwm_drivers[2]);
    }
} // namespace nucode::arduino::internal::analog
