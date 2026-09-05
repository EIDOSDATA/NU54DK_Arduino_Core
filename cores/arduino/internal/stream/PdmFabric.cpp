/** @file @brief Pdm의 private context·driver·IRQ와 lifecycle을 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#include "StreamFabricInternal.h"
#include <hal/nrf_pdm.h>
#include <nrfx_pdm.h>
namespace nucode::arduino
{
    using namespace internal::stream;
    namespace
    {
        inline constexpr std::size_t pdm_dma_capacity = 4U;
        struct PdmContext
        {
            std::uint8_t instance{0U};
            PdmConfiguration configuration{};
            IoResourceLease base_lease{};
            DmaLeaseSlot dma_leases[pdm_dma_capacity]{};
            EventQueue<PdmEvent> events{};
            StreamFabricState state{StreamFabricState::inactive};
            internal::FabricDiagnostic<StreamFabricResult> diagnostics{};
            internal::FabricStopSignal stop_signal{};
            bool stop_waiting{false};
            bool ignore_initial_request{false};
        };

        PdmContext pdm_contexts[2]{{20U}, {21U}};
        nrfx_pdm_t pdm_drivers[2]{NRFX_PDM_INSTANCE(NRF_PDM20), NRFX_PDM_INSTANCE(NRF_PDM21)};
        void setInitialRequest(PdmContext &context, bool ignored) noexcept
        {
            const auto key = k_spin_lock(&dmaMetadataLock());
            context.ignore_initial_request = ignored;
            k_spin_unlock(&dmaMetadataLock(), key);
        }

        bool consumeInitialRequest(PdmContext &context) noexcept
        {
            const auto key = k_spin_lock(&dmaMetadataLock());
            const bool ignored = context.ignore_initial_request;
            context.ignore_initial_request = false;
            k_spin_unlock(&dmaMetadataLock(), key);
            return ignored;
        }

        [[nodiscard]] PdmContext *pdmContext(std::uint8_t instance) noexcept
        {
            for (auto &context : pdm_contexts)
            {
                if (context.instance == instance)
                {
                    return &context;
                }
            }
            return nullptr;
        }

        [[nodiscard]] nrfx_pdm_t *pdmDriver(std::uint8_t instance) noexcept
        {
            if (instance == 20U)
            {
                return &pdm_drivers[0];
            }
            if (instance == 21U)
            {
                return &pdm_drivers[1];
            }
            return nullptr;
        }

        void handlePdmEvent(PdmContext &context, const nrfx_pdm_evt_t *event)
        {
            if (event->buffer_requested)
            {
                if (!consumeInitialRequest(context) &&
                    !pushEvent(context.events, {PdmEventType::buffer_needed, nullptr, 0U, 0}))
                {
                    record(context, StreamFabricResult::resource_exhausted, -ENOBUFS);
                }
            }
            if (event->buffer_released != nullptr)
            {
                std::size_t samples = 0U;
                const auto key = k_spin_lock(&dmaMetadataLock());
                for (const auto &slot : context.dma_leases)
                {
                    if (slot.active && slot.address == event->buffer_released)
                    {
                        samples = slot.bytes / sizeof(std::int16_t);
                        break;
                    }
                }
                k_spin_unlock(&dmaMetadataLock(), key);
                if (!pushEvent(context.events,
                               {PdmEventType::buffer_complete, event->buffer_released, samples, 0}))
                {
                    record(context, StreamFabricResult::resource_exhausted, -ENOBUFS);
                }
            }
            if (event->error == NRFX_PDM_ERROR_OVERFLOW)
            {
                if (!pushEvent(context.events, {PdmEventType::overflow, nullptr, 0U, -EOVERFLOW}))
                {
                    record(context, StreamFabricResult::resource_exhausted, -ENOBUFS);
                }
            }
        }

        void pdm20EventHandler(const nrfx_pdm_evt_t *event)
        {
            handlePdmEvent(pdm_contexts[0], event);
        }

        void pdm21EventHandler(const nrfx_pdm_evt_t *event)
        {
            handlePdmEvent(pdm_contexts[1], event);
        }
    } // namespace
    std::uint8_t PdmFabric::instance() const noexcept
    {
        return instance_;
    }

    StreamFabricState PdmFabric::state() const noexcept
    {
        lockStream();
        const auto *const context = pdmContext(instance_);
        const auto value = context != nullptr ? context->state : StreamFabricState::faulted;
        unlockStream();
        return value;
    }

    StreamFabricResult PdmFabric::lastResult() const noexcept
    {
        lockStream();
        const auto *const context = pdmContext(instance_);
        const auto value = context != nullptr ? context->diagnostics.snapshot().result
                                              : StreamFabricResult::unsupported_instance;
        unlockStream();
        return value;
    }

    int PdmFabric::lastDriverError() const noexcept
    {
        lockStream();
        const auto *const context = pdmContext(instance_);
        const int value =
            context != nullptr ? context->diagnostics.snapshot().driver_error : -ENODEV;
        unlockStream();
        return value;
    }

    StreamFabricResult PdmFabric::configure(const PdmConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        const pin_size_t pins[]{configuration.clock_pin, configuration.data_pin};
        if (configuration.sample_rate_hz < 8000U || configuration.sample_rate_hz > 48000U ||
            duplicatePins(pins, 2U) ||
            streamPin(configuration.clock_pin, PinCapability::digital_output,
                      configuration.electrical_profile) == nullptr ||
            streamPin(configuration.data_pin, PinCapability::digital_input,
                      configuration.electrical_profile) == nullptr)
        {
            return StreamFabricResult::unsupported_route;
        }

        lockStream();
        auto *const context = pdmContext(instance_);
        if (context == nullptr)
        {
            unlockStream();
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state == StreamFabricState::active ||
            context->state == StreamFabricState::stopping ||
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

    StreamFabricResult PdmFabric::start(std::int16_t *first_buffer, std::size_t samples) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        if (samples == 0U || samples > NRFX_PDM_MAX_BUFFER_SIZE ||
            !internal::dmaMemoryRangeValid(first_buffer, samples * sizeof(*first_buffer),
                                           alignof(std::int16_t)))
        {
            return StreamFabricResult::invalid_argument;
        }

        lockStream();
        auto *const context = pdmContext(instance_);
        auto *const driver = pdmDriver(instance_);
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

        const pin_size_t pins[]{context->configuration.clock_pin, context->configuration.data_pin};
        auto result = claimBase(*context, IoOwnerKind::pdm, instance_, driver->p_reg, pins, 2U);
        if (result != StreamFabricResult::success)
        {
            record(*context, result);
            unlockStream();
            return result;
        }
        DmaLeaseSlot *dma_slot = nullptr;
        result = reserveDma(context->dma_leases, IoOwnerKind::pdm, instance_, first_buffer,
                            samples * sizeof(*first_buffer), dma_slot);
        if (result != StreamFabricResult::success)
        {
            (void)internal::rollbackIoResources(context->base_lease);
            context->base_lease = {};
            record(*context, result);
            unlockStream();
            return result;
        }

        context->stop_signal.beginRun();
        const auto *const clock = internal::pinDescription(pins[0]);
        const auto *const data = internal::pinDescription(pins[1]);
        nrfx_pdm_config_t driver_configuration =
            NRFX_PDM_DEFAULT_CONFIG(physicalPin(*clock), physicalPin(*data));
        driver_configuration.interrupt_priority = IRQ_PRIO_LOWEST;
        driver_configuration.mode =
            context->configuration.stereo ? NRF_PDM_MODE_STEREO : NRF_PDM_MODE_MONO;
        driver_configuration.edge = context->configuration.left_on_rising_edge
                                        ? NRF_PDM_EDGE_LEFTRISING
                                        : NRF_PDM_EDGE_LEFTFALLING;
        const nrfx_pdm_output_t output{32000000U, context->configuration.sample_rate_hz, 1000000U,
                                       3250000U};
        int driver_error = nrfx_pdm_prescalers_calc(&output, &driver_configuration.prescalers);
        if (driver_error == 0)
        {
            driver_error = nrfx_pdm_init(driver, &driver_configuration,
                                         instance_ == 20U ? pdm20EventHandler : pdm21EventHandler);
        }
        setInitialRequest(*context, true);
        if (driver_error == 0)
        {
            driver_error = nrfx_pdm_start(driver);
        }
        if (driver_error == 0)
        {
            driver_error =
                nrfx_pdm_buffer_set(driver, first_buffer, static_cast<std::uint16_t>(samples));
        }
        if (driver_error != 0)
        {
            if (nrfx_pdm_init_check(driver) && nrfx_pdm_enable_check(driver))
            {
                /** @brief start 뒤 buffer 설정 실패도 STOP 확인까지 자원을 보존합니다. */
                context->state = StreamFabricState::stopping;
                (void)context->stop_signal.arm();
                (void)nrfx_pdm_stop(driver);
                record(*context, StreamFabricResult::driver_error, driver_error);
                unlockStream();
                return StreamFabricResult::driver_error;
            }
            if (nrfx_pdm_init_check(driver))
            {
                nrfx_pdm_uninit(driver);
            }
            rollbackDma(*dma_slot);
            (void)internal::rollbackIoResources(context->base_lease);
            context->base_lease = {};
            setInitialRequest(*context, false);
            record(*context, StreamFabricResult::driver_error, driver_error);
            unlockStream();
            return StreamFabricResult::driver_error;
        }
        const auto base_commit = internal::commitIoResources(context->base_lease);
        const auto dma_commit = commitDma(*dma_slot);
        if (base_commit != IoResourceResult::success || dma_commit != IoResourceResult::success)
        {
            context->state = StreamFabricState::stopping;
            (void)context->stop_signal.arm();
            (void)nrfx_pdm_stop(driver);
            record(*context, StreamFabricResult::release_failed);
            unlockStream();
            return StreamFabricResult::release_failed;
        }
        context->state = StreamFabricState::active;
        record(*context, StreamFabricResult::success);
        unlockStream();
        return StreamFabricResult::success;
    }

    StreamFabricResult PdmFabric::queueBuffer(std::int16_t *buffer, std::size_t samples) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        if (samples == 0U || samples > NRFX_PDM_MAX_BUFFER_SIZE ||
            !internal::dmaMemoryRangeValid(buffer, samples * sizeof(*buffer),
                                           alignof(std::int16_t)))
        {
            return StreamFabricResult::invalid_argument;
        }
        lockStream();
        auto *const context = pdmContext(instance_);
        auto *const driver = pdmDriver(instance_);
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
        DmaLeaseSlot *slot = nullptr;
        auto result = reserveDma(context->dma_leases, IoOwnerKind::pdm, instance_, buffer,
                                 samples * sizeof(*buffer), slot);
        if (result != StreamFabricResult::success)
        {
            record(*context, result);
            unlockStream();
            return result;
        }
        const int driver_error =
            nrfx_pdm_buffer_set(driver, buffer, static_cast<std::uint16_t>(samples));
        if (driver_error != 0)
        {
            rollbackDma(*slot);
            record(*context, StreamFabricResult::driver_error, driver_error);
            unlockStream();
            return StreamFabricResult::driver_error;
        }
        if (commitDma(*slot) != IoResourceResult::success)
        {
            context->state = StreamFabricState::stopping;
            (void)context->stop_signal.arm();
            (void)nrfx_pdm_stop(driver);
            record(*context, StreamFabricResult::release_failed);
            unlockStream();
            return StreamFabricResult::release_failed;
        }
        record(*context, StreamFabricResult::success);
        unlockStream();
        return StreamFabricResult::success;
    }

    std::uintptr_t PdmFabric::startTaskAddress() const noexcept
    {
        const auto *const driver = pdmDriver(instance_);
        return driver != nullptr ? nrfx_pdm_task_address_get(driver, NRF_PDM_TASK_START) : 0U;
    }

    StreamFabricResult PdmFabric::stop(std::uint32_t timeout_us) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        lockStream();
        auto *const context = pdmContext(instance_);
        auto *const driver = pdmDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            unlockStream();
            return StreamFabricResult::unsupported_instance;
        }
        if ((context->state != StreamFabricState::active &&
             context->state != StreamFabricState::stopping) ||
            context->stop_waiting)
        {
            record(*context, StreamFabricResult::wrong_state);
            unlockStream();
            return StreamFabricResult::wrong_state;
        }
        context->state = StreamFabricState::stopping;
        context->stop_waiting = true;
        (void)context->stop_signal.arm();
        unlockStream();
        int driver_error = nrfx_pdm_stop(driver);
        const bool stopped = internal::waitFabricStop(
            [&]
            {
                if (driver_error == -EBUSY)
                {
                    driver_error = nrfx_pdm_stop(driver);
                }
                return driver_error == 0 && !nrfx_pdm_enable_check(driver);
            },
            timeout_us);
        lockStream();
        context->stop_waiting = false;
        if (!stopped)
        {
            record(*context, StreamFabricResult::stop_timeout,
                   driver_error != 0 ? driver_error : -ETIMEDOUT);
            unlockStream();
            return StreamFabricResult::stop_timeout;
        }
        nrfx_pdm_uninit(driver);
        const auto dma_release = releaseAllDma(context->dma_leases);
        const auto base_release = context->base_lease.phase == internal::IoLeasePhase::reserved
                                      ? internal::rollbackIoResources(context->base_lease)
                                      : internal::releaseIoResources(context->base_lease);
        if (base_release == IoResourceResult::success)
        {
            context->base_lease = {};
        }
        setInitialRequest(*context, false);
        const auto result =
            dma_release == IoResourceResult::success && base_release == IoResourceResult::success
                ? StreamFabricResult::success
                : StreamFabricResult::release_failed;
        context->state = result == StreamFabricResult::success ? StreamFabricState::configured
                                                               : StreamFabricState::faulted;
        (void)pushEvent(context->events, {PdmEventType::stopped, nullptr, 0U, 0});
        record(*context, result);
        unlockStream();
        return result;
    }

    bool PdmFabric::takeEvent(PdmEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        lockStream();
        auto *const context = pdmContext(instance_);
        const bool available = context != nullptr && popEvent(context->events, event);
        if (available && event.type == PdmEventType::buffer_complete)
        {
            for (const auto &slot : context->dma_leases)
            {
                if (slot.active && slot.address == event.buffer)
                {
                    event.samples = slot.bytes / sizeof(std::int16_t);
                    break;
                }
            }
            if (releaseDmaFor(context->dma_leases, event.buffer) != IoResourceResult::success)
            {
                context->state = StreamFabricState::faulted;
                record(*context, StreamFabricResult::release_failed);
            }
        }
        unlockStream();
        return available;
    }

} // namespace nucode::arduino
namespace nucode::arduino::internal::stream
{
    void pdm20Irq(const void *)
    {
        nrfx_pdm_irq_handler(&pdm_drivers[0]);
    }

    void pdm21Irq(const void *)
    {
        nrfx_pdm_irq_handler(&pdm_drivers[1]);
    }
} // namespace nucode::arduino::internal::stream
