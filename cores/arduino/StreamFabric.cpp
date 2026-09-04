/**
 * @file StreamFabric.cpp
 * @brief M25 PDM20/21, I2S20, QDEC20/21 직접 nrfx adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/StreamFabric.h>
#include "internal/qdec_sampling.h"

#include "internal/IoResourceManager.h"
#include "internal/dma_count.h"
#include "internal/dma_memory.h"
#include "internal/pin_description.h"

#include <variant.h>

#include <hal/nrf_gpio.h>
#include <hal/nrf_i2s.h>
#include <hal/nrf_pdm.h>
#include <hal/nrf_qdec.h>
#include <nrfx_i2s.h>
#include <nrfx_pdm.h>
#include <nrfx_qdec.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
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
        using internal::IoResourceToken;
        using internal::PinCapability;
        using internal::PinPolicy;
        using internal::PinRoute;

        inline constexpr pin_size_t disconnected_pin = 0xFFU;
        inline constexpr std::size_t event_queue_capacity = 12U;
        inline constexpr std::size_t pdm_dma_capacity = 4U;
        inline constexpr std::size_t i2s_dma_capacity = 8U;

        template <typename Event> struct EventQueue
        {
            Event entries[event_queue_capacity]{};
            std::size_t read_index{0U};
            std::size_t write_index{0U};
            std::size_t count{0U};
            struct k_spinlock lock{};
        };

        struct DmaLeaseSlot
        {
            const void *address{nullptr};
            std::size_t bytes{0U};
            IoResourceToken token{};
            bool active{false};
        };

        struct PdmContext
        {
            std::uint8_t instance{0U};
            PdmConfiguration configuration{};
            IoResourceLease base_lease{};
            DmaLeaseSlot dma_leases[pdm_dma_capacity]{};
            EventQueue<PdmEvent> events{};
            StreamFabricState state{StreamFabricState::inactive};
            StreamFabricResult last_result{StreamFabricResult::success};
            int last_driver_error{0};
            bool ignore_initial_request{false};
        };

        struct I2sContext
        {
            I2sConfiguration configuration{};
            IoResourceLease base_lease{};
            DmaLeaseSlot dma_leases[i2s_dma_capacity]{};
            EventQueue<I2sEvent> events{};
            StreamFabricState state{StreamFabricState::inactive};
            StreamFabricResult last_result{StreamFabricResult::success};
            int last_driver_error{0};
            volatile bool stopped_seen{false};
            bool first_callback{true};
        };

        struct QdecContext
        {
            std::uint8_t instance{0U};
            QdecConfiguration configuration{};
            IoResourceLease base_lease{};
            EventQueue<QdecEvent> events{};
            StreamFabricState state{StreamFabricState::inactive};
            StreamFabricResult last_result{StreamFabricResult::success};
            int last_driver_error{0};
        };

        K_MUTEX_DEFINE(stream_fabric_mutex);
        PdmContext pdm_contexts[2]{{20U}, {21U}};
        I2sContext i2s_context{};
        QdecContext qdec_contexts[2]{{20U}, {21U}};
        nrfx_pdm_t pdm_drivers[2]{NRFX_PDM_INSTANCE(NRF_PDM20), NRFX_PDM_INSTANCE(NRF_PDM21)};
        nrfx_i2s_t i2s_driver = NRFX_I2S_INSTANCE(NRF_I2S20);
        nrfx_qdec_t qdec_drivers[2]{NRFX_QDEC_INSTANCE(NRF_QDEC20), NRFX_QDEC_INSTANCE(NRF_QDEC21)};

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

        template <typename Event> bool popEvent(EventQueue<Event> &queue, Event &event) noexcept
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

        template <typename Event> void clearEvents(EventQueue<Event> &queue) noexcept
        {
            const k_spinlock_key_t key = k_spin_lock(&queue.lock);
            queue.read_index = 0U;
            queue.write_index = 0U;
            queue.count = 0U;
            k_spin_unlock(&queue.lock, key);
        }

        template <typename Context>
        void record(Context &context, StreamFabricResult result, int driver_error = 0) noexcept
        {
            context.last_result = result;
            context.last_driver_error = driver_error;
        }

        [[nodiscard]] StreamFabricResult mapResourceResult(IoResourceResult result) noexcept
        {
            switch (result)
            {
            case IoResourceResult::success:
                return StreamFabricResult::success;
            case IoResourceResult::invalid_context:
                return StreamFabricResult::invalid_context;
            case IoResourceResult::invalid_argument:
                return StreamFabricResult::invalid_argument;
            case IoResourceResult::conflict:
                return StreamFabricResult::ownership_conflict;
            case IoResourceResult::capacity_exhausted:
                return StreamFabricResult::resource_exhausted;
            default:
                return StreamFabricResult::release_failed;
            }
        }

        template <std::size_t Capacity>
        [[nodiscard]] StreamFabricResult
        reserveDma(DmaLeaseSlot (&slots)[Capacity], IoOwnerKind owner, std::uint8_t instance,
                   const void *address, std::size_t bytes, DmaLeaseSlot *&slot) noexcept
        {
            slot = nullptr;
            if (bytes > UINT32_MAX || !internal::dmaMemoryRangeValid(address, bytes))
            {
                return StreamFabricResult::invalid_argument;
            }
            for (auto &candidate : slots)
            {
                if (!candidate.active)
                {
                    slot = &candidate;
                    break;
                }
            }
            if (slot == nullptr)
            {
                return StreamFabricResult::resource_exhausted;
            }
            const IoResourceId resource =
                internal::dmaMemoryIoResource(address, static_cast<std::uint32_t>(bytes));
            slot->token = {};
            const auto result = internal::acquireIoResources(
                {owner, instance}, &resource, 1U, IoAcquirePolicy::exclusive, slot->token);
            if (result != IoResourceResult::success)
            {
                slot = nullptr;
                return mapResourceResult(result);
            }
            slot->address = address;
            slot->bytes = bytes;
            slot->active = true;
            return StreamFabricResult::success;
        }

        void rollbackDma(DmaLeaseSlot &slot) noexcept
        {
            if (slot.active)
            {
                (void)internal::releaseIoResources(slot.token);
            }
            slot = {};
        }

        [[nodiscard]] IoResourceResult commitDma(DmaLeaseSlot &slot) noexcept
        {
            return slot.active ? IoResourceResult::success : IoResourceResult::wrong_phase;
        }

        [[nodiscard]] IoResourceResult releaseDma(DmaLeaseSlot &slot) noexcept
        {
            if (!slot.active)
            {
                return IoResourceResult::success;
            }
            const auto result = internal::releaseIoResources(slot.token);
            slot = {};
            return result;
        }

        template <std::size_t Capacity>
        [[nodiscard]] IoResourceResult releaseDmaFor(DmaLeaseSlot (&slots)[Capacity],
                                                     const void *address) noexcept
        {
            if (address == nullptr)
            {
                return IoResourceResult::success;
            }
            for (auto &slot : slots)
            {
                if (slot.active && slot.address == address)
                {
                    return releaseDma(slot);
                }
            }
            return IoResourceResult::stale_lease;
        }

        template <std::size_t Capacity>
        [[nodiscard]] IoResourceResult releaseAllDma(DmaLeaseSlot (&slots)[Capacity]) noexcept
        {
            IoResourceResult result = IoResourceResult::success;
            for (auto &slot : slots)
            {
                const auto current = releaseDma(slot);
                if (current != IoResourceResult::success)
                {
                    result = current;
                }
            }
            return result;
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
            return UINT32_MAX;
        }

        [[nodiscard]] const internal::PinDescription *
        streamPin(pin_size_t pin, PinCapability capability,
                  StreamElectricalProfile profile) noexcept
        {
            if (pin == disconnected_pin)
            {
                return nullptr;
            }
            const auto *const description = internal::pinDescription(pin);
            if (description == nullptr || description->canonical_pin != pin ||
                !internal::hasPinRoute(description->routes, PinRoute::header) ||
                !internal::hasPinRoute(description->routes, PinRoute::port1) ||
                physicalPin(*description) == UINT32_MAX)
            {
                return nullptr;
            }
            if (profile == StreamElectricalProfile::dap_uart_disabled)
            {
                /** @brief 공개 GPIO 권한은 변경하지 않고 격리된 DAP pad만 빌립니다. */
                const auto physical = physicalPin(*description);
                const bool console_owns =
                    IS_ENABLED(CONFIG_SERIAL) && DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(uart20));
                if (console_owns || physical < NRF_GPIO_PIN_MAP(1, 4) ||
                    physical > NRF_GPIO_PIN_MAP(1, 7) ||
                    (capability != PinCapability::digital_input &&
                     capability != PinCapability::digital_output))
                {
                    return nullptr;
                }
                return description;
            }
            if (profile != StreamElectricalProfile::connector_fixture ||
                description->policy == PinPolicy::system_reserved ||
                !internal::hasPinCapability(description->capabilities, capability))
            {
                return nullptr;
            }
            return description;
        }

        [[nodiscard]] bool duplicatePins(const pin_size_t *pins, std::size_t count) noexcept
        {
            for (std::size_t index = 0U; index < count; ++index)
            {
                if (pins[index] == disconnected_pin)
                {
                    continue;
                }
                for (std::size_t prior = 0U; prior < index; ++prior)
                {
                    if (pins[prior] == pins[index])
                    {
                        return true;
                    }
                }
            }
            return false;
        }

        template <typename Context>
        [[nodiscard]] StreamFabricResult
        claimBase(Context &context, IoOwnerKind owner, std::uint8_t instance,
                  const void *driver_register, const pin_size_t *pins,
                  std::size_t pin_count) noexcept
        {
            IoResourceId resources[internal::io_resource_lease_capacity]{};
            std::size_t resource_count = 0U;
            resources[resource_count++] = internal::peripheralIoResource(
                IoResourceKind::stream_block, instance, driver_register);
            for (std::size_t index = 0U; index < pin_count; ++index)
            {
                if (pins[index] == disconnected_pin)
                {
                    continue;
                }
                const auto *const description = internal::pinDescription(pins[index]);
                resources[resource_count++] = internal::gpioIoResource(description->gpio);
            }
            context.base_lease = {};
            return mapResourceResult(
                internal::reserveIoResources({owner, instance}, resources, resource_count,
                                             IoAcquirePolicy::exclusive, context.base_lease));
        }

        [[nodiscard]] nrf_i2s_swidth_t i2sWidth(I2sSampleWidth width) noexcept
        {
            switch (width)
            {
            case I2sSampleWidth::bits8:
                return NRF_I2S_SWIDTH_8BIT;
            case I2sSampleWidth::bits24:
                return NRF_I2S_SWIDTH_24BIT;
            case I2sSampleWidth::bits32:
                return NRF_I2S_SWIDTH_32BIT;
            case I2sSampleWidth::bits16:
            default:
                return NRF_I2S_SWIDTH_16BIT;
            }
        }

        [[nodiscard]] nrf_i2s_channels_t i2sChannels(I2sChannels channels) noexcept
        {
            switch (channels)
            {
            case I2sChannels::left:
                return NRF_I2S_CHANNELS_LEFT;
            case I2sChannels::right:
                return NRF_I2S_CHANNELS_RIGHT;
            case I2sChannels::stereo:
            default:
                return NRF_I2S_CHANNELS_STEREO;
            }
        }

        void handlePdmEvent(PdmContext &context, const nrfx_pdm_evt_t *event)
        {
            if (event->buffer_requested)
            {
                if (context.ignore_initial_request)
                {
                    context.ignore_initial_request = false;
                }
                else if (!pushEvent(context.events, {PdmEventType::buffer_needed, nullptr, 0U, 0}))
                {
                    context.last_result = StreamFabricResult::resource_exhausted;
                    context.last_driver_error = -ENOBUFS;
                }
            }
            if (event->buffer_released != nullptr)
            {
                std::size_t samples = 0U;
                for (const auto &slot : context.dma_leases)
                {
                    if (slot.active && slot.address == event->buffer_released)
                    {
                        samples = slot.bytes / sizeof(std::int16_t);
                        break;
                    }
                }
                if (!pushEvent(context.events,
                               {PdmEventType::buffer_complete, event->buffer_released, samples, 0}))
                {
                    context.last_result = StreamFabricResult::resource_exhausted;
                    context.last_driver_error = -ENOBUFS;
                }
            }
            if (event->error == NRFX_PDM_ERROR_OVERFLOW)
            {
                if (!pushEvent(context.events, {PdmEventType::overflow, nullptr, 0U, -EOVERFLOW}))
                {
                    context.last_result = StreamFabricResult::resource_exhausted;
                    context.last_driver_error = -ENOBUFS;
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

        void i2sEventHandler(const nrfx_i2s_buffers_t *released, std::uint32_t status)
        {
            const bool empty_release = released == nullptr || (released->p_rx_buffer == nullptr &&
                                                               released->p_tx_buffer == nullptr);
            if (!empty_release)
            {
                I2sEvent event{};
                event.type = I2sEventType::buffers_complete;
                event.released.receive = released->p_rx_buffer;
                event.released.transmit = released->p_tx_buffer;
                event.released.words = released->buffer_size;
                if (!pushEvent(i2s_context.events, event))
                {
                    i2s_context.last_result = StreamFabricResult::resource_exhausted;
                    i2s_context.last_driver_error = -ENOBUFS;
                }
            }
            if ((status & NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED) != 0U)
            {
                const auto type = empty_release && !i2s_context.first_callback
                                      ? I2sEventType::underrun
                                      : I2sEventType::buffers_needed;
                if (!pushEvent(i2s_context.events, {type, {}, 0}))
                {
                    i2s_context.last_result = StreamFabricResult::resource_exhausted;
                    i2s_context.last_driver_error = -ENOBUFS;
                }
            }
            if ((status & NRFX_I2S_STATUS_TRANSFER_STOPPED) != 0U)
            {
                i2s_context.stopped_seen = true;
                if (!pushEvent(i2s_context.events, {I2sEventType::stopped, {}, 0}))
                {
                    i2s_context.last_result = StreamFabricResult::resource_exhausted;
                    i2s_context.last_driver_error = -ENOBUFS;
                }
            }
            i2s_context.first_callback = false;
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
                context.last_result = StreamFabricResult::resource_exhausted;
                context.last_driver_error = -ENOBUFS;
            }
        }

        void pdm20Irq(const void *)
        {
            nrfx_pdm_irq_handler(&pdm_drivers[0]);
        }
        void pdm21Irq(const void *)
        {
            nrfx_pdm_irq_handler(&pdm_drivers[1]);
        }
        void i2s20Irq(const void *)
        {
            nrfx_i2s_irq_handler(&i2s_driver);
        }
        void qdec20Irq(const void *)
        {
            nrfx_qdec_irq_handler(&qdec_drivers[0]);
        }
        void qdec21Irq(const void *)
        {
            nrfx_qdec_irq_handler(&qdec_drivers[1]);
        }

        int connectStreamFabricIrqs()
        {
            IRQ_CONNECT(PDM20_IRQn, IRQ_PRIO_LOWEST, pdm20Irq, nullptr, 0);
            IRQ_CONNECT(PDM21_IRQn, IRQ_PRIO_LOWEST, pdm21Irq, nullptr, 0);
            IRQ_CONNECT(I2S20_IRQn, IRQ_PRIO_LOWEST, i2s20Irq, nullptr, 0);
            IRQ_CONNECT(QDEC20_IRQn, IRQ_PRIO_LOWEST, qdec20Irq, nullptr, 0);
            IRQ_CONNECT(QDEC21_IRQn, IRQ_PRIO_LOWEST, qdec21Irq, nullptr, 0);
            return 0;
        }

        SYS_INIT(connectStreamFabricIrqs, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace

    std::uint8_t PdmFabric::instance() const noexcept
    {
        return instance_;
    }

    StreamFabricState PdmFabric::state() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto *const context = pdmContext(instance_);
        const auto value = context != nullptr ? context->state : StreamFabricState::faulted;
        k_mutex_unlock(&stream_fabric_mutex);
        return value;
    }

    StreamFabricResult PdmFabric::lastResult() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto *const context = pdmContext(instance_);
        const auto value =
            context != nullptr ? context->last_result : StreamFabricResult::unsupported_instance;
        k_mutex_unlock(&stream_fabric_mutex);
        return value;
    }

    int PdmFabric::lastDriverError() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto *const context = pdmContext(instance_);
        const int value = context != nullptr ? context->last_driver_error : -ENODEV;
        k_mutex_unlock(&stream_fabric_mutex);
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

        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = pdmContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state == StreamFabricState::active ||
            context->state == StreamFabricState::stopping ||
            context->state == StreamFabricState::faulted)
        {
            record(*context, context->state == StreamFabricState::faulted
                                 ? StreamFabricResult::faulted
                                 : StreamFabricResult::wrong_state);
            const auto result = context->last_result;
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }
        context->configuration = configuration;
        context->state = StreamFabricState::configured;
        clearEvents(context->events);
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
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

        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = pdmContext(instance_);
        auto *const driver = pdmDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::configured)
        {
            record(*context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }

        const pin_size_t pins[]{context->configuration.clock_pin, context->configuration.data_pin};
        auto result = claimBase(*context, IoOwnerKind::pdm, instance_, driver->p_reg, pins, 2U);
        if (result != StreamFabricResult::success)
        {
            record(*context, result);
            k_mutex_unlock(&stream_fabric_mutex);
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
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }

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
        context->ignore_initial_request = true;
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
            if (nrfx_pdm_init_check(driver))
            {
                nrfx_pdm_uninit(driver);
            }
            rollbackDma(*dma_slot);
            (void)internal::rollbackIoResources(context->base_lease);
            context->base_lease = {};
            context->ignore_initial_request = false;
            record(*context, StreamFabricResult::driver_error, driver_error);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::driver_error;
        }
        const auto base_commit = internal::commitIoResources(context->base_lease);
        const auto dma_commit = commitDma(*dma_slot);
        if (base_commit != IoResourceResult::success || dma_commit != IoResourceResult::success)
        {
            (void)nrfx_pdm_stop(driver);
            nrfx_pdm_uninit(driver);
            if (context->base_lease.phase == internal::IoLeasePhase::reserved)
            {
                (void)internal::rollbackIoResources(context->base_lease);
            }
            else
            {
                (void)internal::releaseIoResources(context->base_lease);
            }
            context->base_lease = {};
            (void)releaseDma(*dma_slot);
            context->state = StreamFabricState::faulted;
            record(*context, StreamFabricResult::release_failed);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        context->state = StreamFabricState::active;
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
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
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = pdmContext(instance_);
        auto *const driver = pdmDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::active)
        {
            record(*context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }
        DmaLeaseSlot *slot = nullptr;
        auto result = reserveDma(context->dma_leases, IoOwnerKind::pdm, instance_, buffer,
                                 samples * sizeof(*buffer), slot);
        if (result != StreamFabricResult::success)
        {
            record(*context, result);
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }
        const int driver_error =
            nrfx_pdm_buffer_set(driver, buffer, static_cast<std::uint16_t>(samples));
        if (driver_error != 0)
        {
            rollbackDma(*slot);
            record(*context, StreamFabricResult::driver_error, driver_error);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::driver_error;
        }
        if (commitDma(*slot) != IoResourceResult::success)
        {
            context->state = StreamFabricState::faulted;
            record(*context, StreamFabricResult::release_failed);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
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
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = pdmContext(instance_);
        auto *const driver = pdmDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::active)
        {
            record(*context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }
        context->state = StreamFabricState::stopping;
        const std::uint32_t started = k_cycle_get_32();
        int driver_error = nrfx_pdm_stop(driver);
        while ((driver_error == -EBUSY || nrfx_pdm_enable_check(driver)) &&
               k_cyc_to_us_floor32(k_cycle_get_32() - started) < timeout_us)
        {
            if (driver_error == -EBUSY)
            {
                driver_error = nrfx_pdm_stop(driver);
            }
            k_busy_wait(10U);
        }
        if (driver_error != 0 || nrfx_pdm_enable_check(driver))
        {
            context->state = StreamFabricState::faulted;
            record(*context, StreamFabricResult::stop_timeout,
                   driver_error != 0 ? driver_error : -ETIMEDOUT);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::stop_timeout;
        }
        nrfx_pdm_uninit(driver);
        const auto dma_release = releaseAllDma(context->dma_leases);
        const auto base_release = internal::releaseIoResources(context->base_lease);
        context->base_lease = {};
        context->ignore_initial_request = false;
        if (dma_release != IoResourceResult::success || base_release != IoResourceResult::success)
        {
            context->state = StreamFabricState::faulted;
            record(*context, StreamFabricResult::release_failed);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        context->state = StreamFabricState::configured;
        (void)pushEvent(context->events, {PdmEventType::stopped, nullptr, 0U, 0});
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    bool PdmFabric::takeEvent(PdmEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
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
        k_mutex_unlock(&stream_fabric_mutex);
        return available;
    }

    std::uint8_t I2sFabric::instance() const noexcept
    {
        return 20U;
    }

    StreamFabricState I2sFabric::state() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto value = i2s_context.state;
        k_mutex_unlock(&stream_fabric_mutex);
        return value;
    }

    StreamFabricResult I2sFabric::lastResult() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto value = i2s_context.last_result;
        k_mutex_unlock(&stream_fabric_mutex);
        return value;
    }

    int I2sFabric::lastDriverError() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const int value = i2s_context.last_driver_error;
        k_mutex_unlock(&stream_fabric_mutex);
        return value;
    }

    StreamFabricResult I2sFabric::configure(const I2sConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        const pin_size_t pins[]{configuration.sck_pin, configuration.lrck_pin,
                                configuration.mck_pin, configuration.data_out_pin,
                                configuration.data_in_pin};
        if (configuration.sample_rate_hz < 8000U || configuration.sample_rate_hz > 192000U ||
            duplicatePins(pins, 5U) || configuration.sck_pin == disconnected_pin ||
            configuration.lrck_pin == disconnected_pin ||
            (configuration.data_out_pin == disconnected_pin &&
             configuration.data_in_pin == disconnected_pin))
        {
            return StreamFabricResult::invalid_argument;
        }
        const auto clock_capability =
            configuration.master ? PinCapability::digital_output : PinCapability::digital_input;
        if (streamPin(configuration.sck_pin, clock_capability, configuration.electrical_profile) ==
                nullptr ||
            streamPin(configuration.lrck_pin, clock_capability, configuration.electrical_profile) ==
                nullptr ||
            (configuration.mck_pin != disconnected_pin &&
             streamPin(configuration.mck_pin, PinCapability::digital_output,
                       configuration.electrical_profile) == nullptr) ||
            (configuration.data_out_pin != disconnected_pin &&
             streamPin(configuration.data_out_pin, PinCapability::digital_output,
                       configuration.electrical_profile) == nullptr) ||
            (configuration.data_in_pin != disconnected_pin &&
             streamPin(configuration.data_in_pin, PinCapability::digital_input,
                       configuration.electrical_profile) == nullptr))
        {
            return StreamFabricResult::unsupported_route;
        }

        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        if (i2s_context.state == StreamFabricState::active ||
            i2s_context.state == StreamFabricState::stopping ||
            i2s_context.state == StreamFabricState::faulted)
        {
            record(i2s_context, i2s_context.state == StreamFabricState::faulted
                                    ? StreamFabricResult::faulted
                                    : StreamFabricResult::wrong_state);
            const auto result = i2s_context.last_result;
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }
        i2s_context.configuration = configuration;
        i2s_context.state = StreamFabricState::configured;
        clearEvents(i2s_context.events);
        record(i2s_context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    StreamFabricResult I2sFabric::start(const I2sBuffers &buffers) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        if (!internal::dmaCountFits(buffers.words, I2S_RXTXD_MAXCNT_MAXCNT_Msk, 1U) ||
            (buffers.receive == nullptr && buffers.transmit == nullptr) ||
            (buffers.receive != nullptr && buffers.transmit != nullptr &&
             buffers.receive == buffers.transmit) ||
            (buffers.receive != nullptr &&
             !internal::dmaMemoryRangeValid(buffers.receive, buffers.words * sizeof(std::uint32_t),
                                            alignof(std::uint32_t))) ||
            (buffers.transmit != nullptr &&
             !internal::dmaMemoryRangeValid(buffers.transmit, buffers.words * sizeof(std::uint32_t),
                                            alignof(std::uint32_t))))
        {
            return StreamFabricResult::invalid_argument;
        }

        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        if (i2s_context.state != StreamFabricState::configured)
        {
            record(i2s_context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }
        const auto &configuration = i2s_context.configuration;
        const pin_size_t pins[]{configuration.sck_pin, configuration.lrck_pin,
                                configuration.mck_pin, configuration.data_out_pin,
                                configuration.data_in_pin};
        auto result = claimBase(i2s_context, IoOwnerKind::i2s, 20U, i2s_driver.p_reg, pins, 5U);
        if (result != StreamFabricResult::success)
        {
            record(i2s_context, result);
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }
        DmaLeaseSlot *rx_slot = nullptr;
        DmaLeaseSlot *tx_slot = nullptr;
        if (buffers.receive != nullptr)
        {
            result = reserveDma(i2s_context.dma_leases, IoOwnerKind::i2s, 20U, buffers.receive,
                                buffers.words * sizeof(std::uint32_t), rx_slot);
        }
        if (result == StreamFabricResult::success && buffers.transmit != nullptr)
        {
            result = reserveDma(i2s_context.dma_leases, IoOwnerKind::i2s, 20U, buffers.transmit,
                                buffers.words * sizeof(std::uint32_t), tx_slot);
        }
        if (result != StreamFabricResult::success)
        {
            if (rx_slot != nullptr)
            {
                rollbackDma(*rx_slot);
            }
            if (tx_slot != nullptr)
            {
                rollbackDma(*tx_slot);
            }
            (void)internal::rollbackIoResources(i2s_context.base_lease);
            i2s_context.base_lease = {};
            record(i2s_context, result);
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }

        const auto pinNumber = [](pin_size_t pin)
        {
            return pin == disconnected_pin ? static_cast<std::uint32_t>(NRF_I2S_PIN_NOT_CONNECTED)
                                           : physicalPin(*internal::pinDescription(pin));
        };
        nrfx_i2s_config_t driver_configuration = NRFX_I2S_DEFAULT_CONFIG(
            pinNumber(configuration.sck_pin), pinNumber(configuration.lrck_pin),
            pinNumber(configuration.mck_pin), pinNumber(configuration.data_out_pin),
            pinNumber(configuration.data_in_pin));
        driver_configuration.irq_priority = IRQ_PRIO_LOWEST;
        driver_configuration.mode = configuration.master ? NRF_I2S_MODE_MASTER : NRF_I2S_MODE_SLAVE;
        driver_configuration.sample_width = i2sWidth(configuration.sample_width);
        driver_configuration.channels = i2sChannels(configuration.channels);
        int driver_error = 0;
        if (configuration.master)
        {
            const nrfx_i2s_clk_params_t clock{32000000U, configuration.sample_rate_hz,
                                              driver_configuration.sample_width, false};
            driver_error = nrfx_i2s_prescalers_calc(&clock, &driver_configuration.prescalers);
        }
        else
        {
            driver_configuration.prescalers.mck_setup = NRF_I2S_MCK_DISABLED;
        }
        if (driver_error == 0)
        {
            driver_error = nrfx_i2s_init(&i2s_driver, &driver_configuration, i2sEventHandler);
        }
        nrfx_i2s_buffers_t transfer{buffers.receive, buffers.transmit,
                                    static_cast<std::uint16_t>(buffers.words)};
        i2s_context.stopped_seen = false;
        i2s_context.first_callback = true;
        if (driver_error == 0)
        {
            driver_error = nrfx_i2s_start(&i2s_driver, &transfer, 0U);
        }
        if (driver_error != 0)
        {
            if (nrfx_i2s_init_check(&i2s_driver))
            {
                nrfx_i2s_uninit(&i2s_driver);
            }
            if (rx_slot != nullptr)
            {
                rollbackDma(*rx_slot);
            }
            if (tx_slot != nullptr)
            {
                rollbackDma(*tx_slot);
            }
            (void)internal::rollbackIoResources(i2s_context.base_lease);
            i2s_context.base_lease = {};
            record(i2s_context, StreamFabricResult::driver_error, driver_error);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::driver_error;
        }
        const auto base_commit = internal::commitIoResources(i2s_context.base_lease);
        const auto rx_commit = rx_slot != nullptr ? commitDma(*rx_slot) : IoResourceResult::success;
        const auto tx_commit = tx_slot != nullptr ? commitDma(*tx_slot) : IoResourceResult::success;
        if (base_commit != IoResourceResult::success || rx_commit != IoResourceResult::success ||
            tx_commit != IoResourceResult::success)
        {
            nrfx_i2s_stop(&i2s_driver);
            nrfx_i2s_uninit(&i2s_driver);
            if (i2s_context.base_lease.phase == internal::IoLeasePhase::reserved)
            {
                (void)internal::rollbackIoResources(i2s_context.base_lease);
            }
            else
            {
                (void)internal::releaseIoResources(i2s_context.base_lease);
            }
            i2s_context.base_lease = {};
            if (rx_slot != nullptr)
            {
                (void)releaseDma(*rx_slot);
            }
            if (tx_slot != nullptr)
            {
                (void)releaseDma(*tx_slot);
            }
            i2s_context.state = StreamFabricState::faulted;
            record(i2s_context, StreamFabricResult::release_failed);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        i2s_context.state = StreamFabricState::active;
        record(i2s_context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    StreamFabricResult I2sFabric::queueBuffers(const I2sBuffers &buffers) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        if (!internal::dmaCountFits(buffers.words, I2S_RXTXD_MAXCNT_MAXCNT_Msk, 1U) ||
            (buffers.receive == nullptr && buffers.transmit == nullptr) ||
            (buffers.receive != nullptr && buffers.transmit != nullptr &&
             buffers.receive == buffers.transmit) ||
            (buffers.receive != nullptr &&
             !internal::dmaMemoryRangeValid(buffers.receive, buffers.words * sizeof(std::uint32_t),
                                            alignof(std::uint32_t))) ||
            (buffers.transmit != nullptr &&
             !internal::dmaMemoryRangeValid(buffers.transmit, buffers.words * sizeof(std::uint32_t),
                                            alignof(std::uint32_t))))
        {
            return StreamFabricResult::invalid_argument;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        if (i2s_context.state != StreamFabricState::active)
        {
            record(i2s_context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }
        DmaLeaseSlot *rx_slot = nullptr;
        DmaLeaseSlot *tx_slot = nullptr;
        auto result = StreamFabricResult::success;
        if (buffers.receive != nullptr)
        {
            result = reserveDma(i2s_context.dma_leases, IoOwnerKind::i2s, 20U, buffers.receive,
                                buffers.words * sizeof(std::uint32_t), rx_slot);
        }
        if (result == StreamFabricResult::success && buffers.transmit != nullptr)
        {
            result = reserveDma(i2s_context.dma_leases, IoOwnerKind::i2s, 20U, buffers.transmit,
                                buffers.words * sizeof(std::uint32_t), tx_slot);
        }
        if (result != StreamFabricResult::success)
        {
            if (rx_slot != nullptr)
            {
                rollbackDma(*rx_slot);
            }
            if (tx_slot != nullptr)
            {
                rollbackDma(*tx_slot);
            }
            record(i2s_context, result);
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }
        const nrfx_i2s_buffers_t transfer{buffers.receive, buffers.transmit,
                                          static_cast<std::uint16_t>(buffers.words)};
        const int driver_error = nrfx_i2s_next_buffers_set(&i2s_driver, &transfer);
        if (driver_error != 0)
        {
            if (rx_slot != nullptr)
            {
                rollbackDma(*rx_slot);
            }
            if (tx_slot != nullptr)
            {
                rollbackDma(*tx_slot);
            }
            record(i2s_context, StreamFabricResult::driver_error, driver_error);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::driver_error;
        }
        const auto rx_commit = rx_slot != nullptr ? commitDma(*rx_slot) : IoResourceResult::success;
        const auto tx_commit = tx_slot != nullptr ? commitDma(*tx_slot) : IoResourceResult::success;
        if (rx_commit != IoResourceResult::success || tx_commit != IoResourceResult::success)
        {
            i2s_context.state = StreamFabricState::faulted;
            record(i2s_context, StreamFabricResult::release_failed);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        record(i2s_context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    StreamFabricResult I2sFabric::stop(std::uint32_t timeout_us) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        if (i2s_context.state != StreamFabricState::active)
        {
            record(i2s_context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }
        i2s_context.state = StreamFabricState::stopping;
        i2s_context.stopped_seen = false;
        nrfx_i2s_stop(&i2s_driver);
        const std::uint32_t started = k_cycle_get_32();
        while (!i2s_context.stopped_seen &&
               k_cyc_to_us_floor32(k_cycle_get_32() - started) < timeout_us)
        {
            k_busy_wait(10U);
        }
        if (!i2s_context.stopped_seen)
        {
            i2s_context.state = StreamFabricState::faulted;
            record(i2s_context, StreamFabricResult::stop_timeout, -ETIMEDOUT);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::stop_timeout;
        }
        nrfx_i2s_uninit(&i2s_driver);
        const auto dma_release = releaseAllDma(i2s_context.dma_leases);
        const auto base_release = internal::releaseIoResources(i2s_context.base_lease);
        i2s_context.base_lease = {};
        if (dma_release != IoResourceResult::success || base_release != IoResourceResult::success)
        {
            i2s_context.state = StreamFabricState::faulted;
            record(i2s_context, StreamFabricResult::release_failed);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        i2s_context.state = StreamFabricState::configured;
        record(i2s_context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    bool I2sFabric::takeEvent(I2sEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const bool available = popEvent(i2s_context.events, event);
        if (available && event.type == I2sEventType::buffers_complete)
        {
            const auto rx_result = releaseDmaFor(i2s_context.dma_leases, event.released.receive);
            const auto tx_result = releaseDmaFor(i2s_context.dma_leases, event.released.transmit);
            if (rx_result != IoResourceResult::success || tx_result != IoResourceResult::success)
            {
                i2s_context.state = StreamFabricState::faulted;
                record(i2s_context, StreamFabricResult::release_failed);
            }
        }
        k_mutex_unlock(&stream_fabric_mutex);
        return available;
    }

    std::uint8_t QdecFabric::instance() const noexcept
    {
        return instance_;
    }

    StreamFabricState QdecFabric::state() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto *const context = qdecContext(instance_);
        const auto value = context != nullptr ? context->state : StreamFabricState::faulted;
        k_mutex_unlock(&stream_fabric_mutex);
        return value;
    }

    StreamFabricResult QdecFabric::lastResult() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto *const context = qdecContext(instance_);
        const auto value =
            context != nullptr ? context->last_result : StreamFabricResult::unsupported_instance;
        k_mutex_unlock(&stream_fabric_mutex);
        return value;
    }

    int QdecFabric::lastDriverError() const noexcept
    {
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        const auto *const context = qdecContext(instance_);
        const int value = context != nullptr ? context->last_driver_error : -ENODEV;
        k_mutex_unlock(&stream_fabric_mutex);
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
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = qdecContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state == StreamFabricState::active ||
            context->state == StreamFabricState::faulted)
        {
            record(*context, context->state == StreamFabricState::faulted
                                 ? StreamFabricResult::faulted
                                 : StreamFabricResult::wrong_state);
            const auto result = context->last_result;
            k_mutex_unlock(&stream_fabric_mutex);
            return result;
        }
        context->configuration = configuration;
        context->state = StreamFabricState::configured;
        clearEvents(context->events);
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    StreamFabricResult QdecFabric::start() noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = qdecContext(instance_);
        auto *const driver = qdecDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::configured)
        {
            record(*context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }
        const pin_size_t pins[]{context->configuration.phase_a_pin,
                                context->configuration.phase_b_pin, context->configuration.led_pin};
        auto result = claimBase(*context, IoOwnerKind::qdec, instance_, driver->p_reg, pins, 3U);
        if (result != StreamFabricResult::success)
        {
            record(*context, result);
            k_mutex_unlock(&stream_fabric_mutex);
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
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::driver_error;
        }
        if (internal::commitIoResources(context->base_lease) != IoResourceResult::success)
        {
            nrfx_qdec_uninit(driver);
            (void)internal::rollbackIoResources(context->base_lease);
            context->base_lease = {};
            context->state = StreamFabricState::faulted;
            record(*context, StreamFabricResult::release_failed);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        nrfx_qdec_enable(driver);
        context->state = StreamFabricState::active;
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    StreamFabricResult QdecFabric::read(QdecEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = qdecContext(instance_);
        auto *const driver = qdecDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::active)
        {
            record(*context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::wrong_state;
        }
        event = {};
        event.type = QdecEventType::report;
        nrfx_qdec_accumulators_read(driver, &event.accumulated, &event.double_transitions);
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    StreamFabricResult QdecFabric::stop() noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = qdecContext(instance_);
        auto *const driver = qdecDriver(instance_);
        if (context == nullptr || driver == nullptr)
        {
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::unsupported_instance;
        }
        if (context->state != StreamFabricState::active)
        {
            record(*context, StreamFabricResult::wrong_state);
            k_mutex_unlock(&stream_fabric_mutex);
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
            k_mutex_unlock(&stream_fabric_mutex);
            return StreamFabricResult::release_failed;
        }
        context->state = StreamFabricState::configured;
        record(*context, StreamFabricResult::success);
        k_mutex_unlock(&stream_fabric_mutex);
        return StreamFabricResult::success;
    }

    bool QdecFabric::takeEvent(QdecEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        k_mutex_lock(&stream_fabric_mutex, K_FOREVER);
        auto *const context = qdecContext(instance_);
        const bool available = context != nullptr && popEvent(context->events, event);
        k_mutex_unlock(&stream_fabric_mutex);
        return available;
    }

    PdmFabric *StreamFabric::pdm(std::uint8_t instance) noexcept
    {
        static PdmFabric handles[]{PdmFabric(20U), PdmFabric(21U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    I2sFabric *StreamFabric::i2s(std::uint8_t instance) noexcept
    {
        static I2sFabric handle;
        return instance == 20U ? &handle : nullptr;
    }

    QdecFabric *StreamFabric::qdec(std::uint8_t instance) noexcept
    {
        static QdecFabric handles[]{QdecFabric(20U), QdecFabric(21U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    StreamFabric &streamFabric() noexcept
    {
        static StreamFabric fabric;
        return fabric;
    }

} // namespace nucode::arduino
