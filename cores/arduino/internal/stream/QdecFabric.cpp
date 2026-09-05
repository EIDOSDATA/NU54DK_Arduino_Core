/** @file @brief Qdec의 private context·driver·IRQ와 lifecycle을 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#include "StreamFabricInternal.h"
#include <hal/nrf_qdec.h>
#include <nrfx_qdec.h>
#include "internal/qdec_sampling.h"
namespace nucode::arduino
{
    using namespace internal::stream;
    namespace
    {
        struct QdecContext
        {
            std::uint8_t instance{0U};
            QdecConfiguration configuration{};
            IoResourceLease base_lease{};
            EventQueue<QdecEvent> events{};
            StreamFabricState state{StreamFabricState::inactive};
            internal::FabricDiagnostic<StreamFabricResult> diagnostics{};
        };

        QdecContext qdec_contexts[2]{{20U}, {21U}};
        nrfx_qdec_t qdec_drivers[2]{NRFX_QDEC_INSTANCE(NRF_QDEC20), NRFX_QDEC_INSTANCE(NRF_QDEC21)};
        [[nodiscard]] QdecContext *qdecContext(std::uint8_t instance) noexcept
        {
            for (auto &context : qdec_contexts)
            {
                if (context.instance == instance)
                {
                    return &context;
                }
            }
            return nullptr;
        }

        [[nodiscard]] nrfx_qdec_t *qdecDriver(std::uint8_t instance) noexcept
        {
            if (instance == 20U)
            {
                return &qdec_drivers[0];
            }
            if (instance == 21U)
            {
                return &qdec_drivers[1];
            }
            return nullptr;
        }

        void qdecEventHandler(nrfx_qdec_event_t event, void *context_pointer)
        {
            auto &context = *static_cast<QdecContext *>(context_pointer);
            QdecEvent translated{};
            switch (event.type)
            {
            case NRF_QDEC_EVENT_SAMPLERDY:
                translated.type = QdecEventType::sample;
                translated.accumulated = event.data.sample.value;
                break;
            case NRF_QDEC_EVENT_REPORTRDY:
                translated.type = QdecEventType::report;
                translated.accumulated = event.data.report.acc;
                translated.double_transitions = event.data.report.accdbl;
                break;
            case NRF_QDEC_EVENT_ACCOF:
            default:
                translated.type = QdecEventType::error;
                translated.driver_error = -EOVERFLOW;
                break;
            }
            if (!pushEvent(context.events, translated))
            {
                record(context, StreamFabricResult::resource_exhausted, -ENOBUFS);
            }
        }
    } // namespace
    std::uint8_t QdecFabric::instance() const noexcept
    {
        return instance_;
    }

    StreamFabricState QdecFabric::state() const noexcept
    {
        lockStream();
        const auto *const context = qdecContext(instance_);
        const auto value = context != nullptr ? context->state : StreamFabricState::faulted;
        unlockStream();
        return value;
    }

    StreamFabricResult QdecFabric::lastResult() const noexcept
    {
        lockStream();
        const auto *const context = qdecContext(instance_);
        const auto value = context != nullptr ? context->diagnostics.snapshot().result
                                              : StreamFabricResult::unsupported_instance;
        unlockStream();
        return value;
    }

    int QdecFabric::lastDriverError() const noexcept
    {
        lockStream();
        const auto *const context = qdecContext(instance_);
        const int value =
            context != nullptr ? context->diagnostics.snapshot().driver_error : -ENODEV;
        unlockStream();
        return value;
    }

    StreamFabricResult QdecFabric::configure(const QdecConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        if (!internal::qdecSamplingValid(configuration.sample_period_us, configuration.led_pre_us))
        {
            return StreamFabricResult::invalid_argument;
        }
        const pin_size_t pins[]{configuration.phase_a_pin, configuration.phase_b_pin,
                                configuration.led_pin};
        if (duplicatePins(pins, 3U) ||
            streamPin(configuration.phase_a_pin, PinCapability::digital_input,
                      configuration.electrical_profile) == nullptr ||
            streamPin(configuration.phase_b_pin, PinCapability::digital_input,
                      configuration.electrical_profile) == nullptr ||
            (configuration.led_pin != disconnected_pin &&
             streamPin(configuration.led_pin, PinCapability::digital_output,
                       configuration.electrical_profile) == nullptr))
        {
            return StreamFabricResult::unsupported_route;
        }
        lockStream();
        auto *const context = qdecContext(instance_);
        if (context == nullptr)
        {
            unlockStream();
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state == StreamFabricState::active ||
            context->state == StreamFabricState::faulted)
        {
            record(*context, context->state == StreamFabricState::faulted
                                 ? StreamFabricResult::faulted
                                 : StreamFabricResult::wrong_state);
            const auto result = context->diagnostics.snapshot().result;
            unlockStream();
            return result;
        }
        context->configuration = configuration;
        context->state = StreamFabricState::configured;
        clearEvents(context->events);
        record(*context, StreamFabricResult::success);
        unlockStream();
        return StreamFabricResult::success;
    }

    StreamFabricResult QdecFabric::start() noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        lockStream();
        auto *const context = qdecContext(instance_);
        auto *const driver = qdecDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            unlockStream();
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::configured)
        {
            record(*context, StreamFabricResult::wrong_state);
            unlockStream();
            return StreamFabricResult::wrong_state;
        }
        const pin_size_t pins[]{context->configuration.phase_a_pin,
                                context->configuration.phase_b_pin, context->configuration.led_pin};
        auto result = claimBase(*context, IoOwnerKind::qdec, instance_, driver->p_reg, pins, 3U);
        if (result != StreamFabricResult::success)
        {
            record(*context, result);
            unlockStream();
            return result;
        }
        const auto pinNumber = [](pin_size_t pin)
        {
            return pin == disconnected_pin ? static_cast<std::uint32_t>(NRF_QDEC_PIN_NOT_CONNECTED)
                                           : physicalPin(*internal::pinDescription(pin));
        };
        nrfx_qdec_config_t driver_configuration =
            NRFX_QDEC_DEFAULT_CONFIG(pinNumber(pins[0]), pinNumber(pins[1]), pinNumber(pins[2]));
        driver_configuration.interrupt_priority = IRQ_PRIO_LOWEST;
        driver_configuration.dbfen = context->configuration.debounce;
        driver_configuration.sample_inten = context->configuration.sample_events;
        static_assert(static_cast<unsigned>(NRF_QDEC_SAMPLEPER_128US) == 0U &&
                          static_cast<unsigned>(NRF_QDEC_SAMPLEPER_256US) == 1U &&
                          static_cast<unsigned>(NRF_QDEC_SAMPLEPER_16384US) == 7U &&
                          static_cast<unsigned>(NRF_QDEC_SAMPLEPER_131MS) == 10U,
                      "QDEC 샘플 주기 HW 인코딩을 다시 검토해야 합니다.");
        driver_configuration.sampleper = static_cast<nrf_qdec_sampleper_t>(
            internal::qdecSamplePeriodCode(context->configuration.sample_period_us));
        driver_configuration.ledpre = context->configuration.led_pre_us;
        driver_configuration.reportper_inten = context->configuration.report_events;
        const int driver_error =
            nrfx_qdec_init(driver, &driver_configuration, qdecEventHandler, context);
        if (driver_error != 0)
        {
            (void)internal::rollbackIoResources(context->base_lease);
            context->base_lease = {};
            record(*context, StreamFabricResult::driver_error, driver_error);
            unlockStream();
            return StreamFabricResult::driver_error;
        }
        if (internal::commitIoResources(context->base_lease) != IoResourceResult::success)
        {
            nrfx_qdec_uninit(driver);
            (void)internal::rollbackIoResources(context->base_lease);
            context->base_lease = {};
            context->state = StreamFabricState::faulted;
            record(*context, StreamFabricResult::release_failed);
            unlockStream();
            return StreamFabricResult::release_failed;
        }
        nrfx_qdec_enable(driver);
        context->state = StreamFabricState::active;
        record(*context, StreamFabricResult::success);
        unlockStream();
        return StreamFabricResult::success;
    }

    StreamFabricResult QdecFabric::read(QdecEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        lockStream();
        auto *const context = qdecContext(instance_);
        auto *const driver = qdecDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            unlockStream();
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::active)
        {
            record(*context, StreamFabricResult::wrong_state);
            unlockStream();
            return StreamFabricResult::wrong_state;
        }
        event = {};
        event.type = QdecEventType::report;
        nrfx_qdec_accumulators_read(driver, &event.accumulated, &event.double_transitions);
        record(*context, StreamFabricResult::success);
        unlockStream();
        return StreamFabricResult::success;
    }

    StreamFabricResult QdecFabric::stop() noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        lockStream();
        auto *const context = qdecContext(instance_);
        auto *const driver = qdecDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            unlockStream();
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::active)
        {
            record(*context, StreamFabricResult::wrong_state);
            unlockStream();
            return StreamFabricResult::wrong_state;
        }
        nrfx_qdec_disable(driver);
        nrfx_qdec_uninit(driver);
        const auto release_result = internal::releaseIoResources(context->base_lease);
        context->base_lease = {};
        if (release_result != IoResourceResult::success)
        {
            context->state = StreamFabricState::faulted;
            record(*context, StreamFabricResult::release_failed);
            unlockStream();
            return StreamFabricResult::release_failed;
        }
        context->state = StreamFabricState::configured;
        record(*context, StreamFabricResult::success);
        unlockStream();
        return StreamFabricResult::success;
    }

    bool QdecFabric::takeEvent(QdecEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        lockStream();
        auto *const context = qdecContext(instance_);
        const bool available = context != nullptr && popEvent(context->events, event);
        unlockStream();
        return available;
    }

} // namespace nucode::arduino
namespace nucode::arduino::internal::stream
{
    void qdec20Irq(const void *)
    {
        nrfx_qdec_irq_handler(&qdec_drivers[0]);
    }

    void qdec21Irq(const void *)
    {
        nrfx_qdec_irq_handler(&qdec_drivers[1]);
    }
} // namespace nucode::arduino::internal::stream
