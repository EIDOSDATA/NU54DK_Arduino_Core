/**
 * @file TwisFabric.cpp
 * @brief M24 TWIS20/21/22/30 target double-buffer EasyDMA adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"

#include <nrfx_twis.h>

#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>

namespace nucode::arduino
{
    namespace
    {
        using internal::SerialFabricDriverAdapter;
        using internal::ValidatedSerialRoute;

        inline constexpr std::size_t instance_count = 4U;
        inline constexpr std::size_t event_capacity = 12U;
        inline constexpr std::uint32_t event_queue_overflow = 0x80000000UL;

        struct BufferRecord
        {
            const void *address{nullptr};
            std::size_t size{0U};
            DmaBufferState state{DmaBufferState::application_owned};
        };

        struct TwisContext
        {
            nrfx_twis_t driver;
            TwisConfiguration configuration{};
            nrfx_twis_config_t driver_configuration{};
            ValidatedSerialRoute route{};
            BufferRecord tx[2]{};
            BufferRecord rx[2]{};
            TwiFabricEvent events[event_capacity]{};
            std::uint8_t event_head{0U};
            std::uint8_t event_tail{0U};
            std::uint8_t event_count{0U};
            bool event_overflow{false};
            atomic_t active{0};
            atomic_t initialized{0};
            atomic_t buffers_active{0};
            k_spinlock lock{};
        };

        TwisContext contexts[instance_count] = {
            {NRFX_TWIS_INSTANCE(NRF_TWIS20)},
            {NRFX_TWIS_INSTANCE(NRF_TWIS21)},
            {NRFX_TWIS_INSTANCE(NRF_TWIS22)},
            {NRFX_TWIS_INSTANCE(NRF_TWIS30)},
        };

        [[nodiscard]] constexpr int instanceIndex(std::uint8_t instance) noexcept
        {
            switch (instance)
            {
            case 20U:
                return 0;
            case 21U:
                return 1;
            case 22U:
                return 2;
            case 30U:
                return 3;
            default:
                return -1;
            }
        }

        [[nodiscard]] TwisContext *contextFor(std::uint8_t instance) noexcept
        {
            const int index = instanceIndex(instance);
            return index < 0 ? nullptr : &contexts[index];
        }

        [[nodiscard]] SerialFabricResult mapResult(int result) noexcept
        {
            switch (result)
            {
            case 0:
                return SerialFabricResult::success;
            case -EINVAL:
            case -EACCES:
            case -E2BIG:
                return SerialFabricResult::invalid_argument;
            case -EBUSY:
            case -EALREADY:
            case -EINPROGRESS:
                return SerialFabricResult::wrong_state;
            case -ENOMEM:
                return SerialFabricResult::resource_exhausted;
            default:
                return SerialFabricResult::driver_error;
            }
        }

        [[nodiscard]] bool rangeInside(const SerialDmaWorkspace &workspace, const void *address,
                                       std::size_t size) noexcept
        {
            if ((address == nullptr) || (size == 0U))
            {
                return false;
            }
            const auto base = reinterpret_cast<std::uintptr_t>(workspace.address);
            const auto start = reinterpret_cast<std::uintptr_t>(address);
            if ((start < base) || (workspace.size > UINTPTR_MAX - base) ||
                (size > UINTPTR_MAX - start))
            {
                return false;
            }
            return (start + size) <= (base + workspace.size);
        }

        [[nodiscard]] bool leasedBuffer(const TwisContext &context, const void *address,
                                        std::size_t size) noexcept
        {
            if ((address == nullptr) && (size == 0U))
            {
                return true;
            }
            for (std::size_t index = 0U; index < context.route.dma_workspace_count; ++index)
            {
                if (rangeInside(context.route.dma_workspaces[index], address, size))
                {
                    return true;
                }
            }
            return false;
        }

        [[nodiscard]] const SerialSignalPin *signalPin(const ValidatedSerialRoute &route,
                                                       SerialSignal signal) noexcept
        {
            for (std::size_t index = 0U; index < route.pin_count; ++index)
            {
                if (route.pins[index].signal == signal)
                {
                    return &route.pins[index];
                }
            }
            return nullptr;
        }

        [[nodiscard]] bool pselFor(const ValidatedSerialRoute &route, SerialSignal signal,
                                   std::uint32_t &psel) noexcept
        {
            const auto *const entry = signalPin(route, signal);
            return entry != nullptr && internal::nu54dkSerialFabricPsel(entry->pin, psel) ==
                                           SerialFabricResult::success;
        }

        void pushEvent(TwisContext &context, const TwiFabricEvent &event) noexcept
        {
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            if (context.event_count == event_capacity)
            {
                context.event_overflow = true;
            }
            else
            {
                context.events[context.event_tail] = event;
                context.event_tail =
                    static_cast<std::uint8_t>((context.event_tail + 1U) % event_capacity);
                ++context.event_count;
            }
            k_spin_unlock(&context.lock, key);
        }

        void emitBufferNeeded(TwisContext &context, bool read)
        {
            pushEvent(context,
                      {TwiFabricEventType::buffer_needed, context.configuration.primary_address,
                       nullptr, nullptr, 0U, 0U, read ? 1U : 2U});
        }

        void clearActiveWhenEmpty(TwisContext &context)
        {
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            const bool empty =
                (context.tx[0].address == nullptr) && (context.tx[1].address == nullptr) &&
                (context.rx[0].address == nullptr) && (context.rx[1].address == nullptr);
            k_spin_unlock(&context.lock, key);
            if (empty)
            {
                atomic_clear(&context.buffers_active);
            }
        }

        void handleReadRequest(TwisContext &context, bool buffer_required)
        {
            pushEvent(context,
                      {TwiFabricEventType::read_request, context.configuration.primary_address,
                       context.tx[0].address, nullptr, 0U, 0U, buffer_required ? 1U : 0U});
            if (!buffer_required)
            {
                return;
            }
            BufferRecord buffer{};
            {
                const k_spinlock_key_t key = k_spin_lock(&context.lock);
                buffer = context.tx[0];
                k_spin_unlock(&context.lock, key);
            }
            if (buffer.address == nullptr)
            {
                emitBufferNeeded(context, true);
                return;
            }
            const int result = nrfx_twis_tx_prepare(&context.driver, buffer.address, buffer.size);
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            context.tx[0].state = result == 0 ? DmaBufferState::dma_owned : DmaBufferState::error;
            k_spin_unlock(&context.lock, key);
            if (result != 0)
            {
                pushEvent(context,
                          {TwiFabricEventType::error, context.configuration.primary_address,
                           buffer.address, nullptr, 0U, 0U, static_cast<std::uint32_t>(-result)});
            }
        }

        void handleWriteRequest(TwisContext &context, bool buffer_required)
        {
            pushEvent(context,
                      {TwiFabricEventType::write_request, context.configuration.primary_address,
                       nullptr, const_cast<void *>(context.rx[0].address), 0U, 0U,
                       buffer_required ? 1U : 0U});
            if (!buffer_required)
            {
                return;
            }
            BufferRecord buffer{};
            {
                const k_spinlock_key_t key = k_spin_lock(&context.lock);
                buffer = context.rx[0];
                k_spin_unlock(&context.lock, key);
            }
            if (buffer.address == nullptr)
            {
                emitBufferNeeded(context, false);
                return;
            }
            const int result = nrfx_twis_rx_prepare(
                &context.driver, const_cast<void *>(buffer.address), buffer.size);
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            context.rx[0].state = result == 0 ? DmaBufferState::dma_owned : DmaBufferState::error;
            k_spin_unlock(&context.lock, key);
            if (result != 0)
            {
                pushEvent(context,
                          {TwiFabricEventType::error, context.configuration.primary_address,
                           nullptr, const_cast<void *>(buffer.address), 0U, 0U,
                           static_cast<std::uint32_t>(-result)});
            }
        }

        void completeRead(TwisContext &context, std::size_t amount, bool error)
        {
            BufferRecord completed{};
            {
                const k_spinlock_key_t key = k_spin_lock(&context.lock);
                completed = context.tx[0];
                completed.state = error ? DmaBufferState::error : DmaBufferState::completed;
                context.tx[0] = context.tx[1];
                context.tx[1] = {};
                k_spin_unlock(&context.lock, key);
            }
            pushEvent(context,
                      {error ? TwiFabricEventType::error : TwiFabricEventType::read_complete,
                       context.configuration.primary_address, completed.address, nullptr, amount,
                       0U, error ? nrfx_twis_error_get_and_clear(&context.driver) : 0U});
            if (context.tx[0].address == nullptr)
            {
                emitBufferNeeded(context, true);
            }
            clearActiveWhenEmpty(context);
        }

        void completeWrite(TwisContext &context, std::size_t amount, bool error)
        {
            BufferRecord completed{};
            {
                const k_spinlock_key_t key = k_spin_lock(&context.lock);
                completed = context.rx[0];
                completed.state = error ? DmaBufferState::error : DmaBufferState::completed;
                context.rx[0] = context.rx[1];
                context.rx[1] = {};
                k_spin_unlock(&context.lock, key);
            }
            pushEvent(context,
                      {error ? TwiFabricEventType::error : TwiFabricEventType::write_complete,
                       context.configuration.primary_address, nullptr,
                       const_cast<void *>(completed.address), 0U, amount,
                       error ? nrfx_twis_error_get_and_clear(&context.driver) : 0U});
            if (context.rx[0].address == nullptr)
            {
                emitBufferNeeded(context, false);
            }
            clearActiveWhenEmpty(context);
        }

        void twisEvent(TwisContext &context, const nrfx_twis_event_t &event)
        {
            switch (event.type)
            {
            case NRFX_TWIS_EVT_READ_REQ:
                handleReadRequest(context, event.data.buf_req);
                break;
            case NRFX_TWIS_EVT_READ_DONE:
                completeRead(context, event.data.tx_amount, false);
                break;
            case NRFX_TWIS_EVT_READ_ERROR:
                completeRead(context, nrfx_twis_tx_amount(&context.driver), true);
                break;
            case NRFX_TWIS_EVT_WRITE_REQ:
                handleWriteRequest(context, event.data.buf_req);
                break;
            case NRFX_TWIS_EVT_WRITE_DONE:
                completeWrite(context, event.data.rx_amount, false);
                break;
            case NRFX_TWIS_EVT_WRITE_ERROR:
                completeWrite(context, nrfx_twis_rx_amount(&context.driver), true);
                break;
            case NRFX_TWIS_EVT_GENERAL_ERROR:
                pushEvent(context,
                          {TwiFabricEventType::error, context.configuration.primary_address,
                           nullptr, nullptr, 0U, 0U, event.data.error});
                break;
            default:
                break;
            }
        }

        void event20(const nrfx_twis_event_t *event)
        {
            twisEvent(contexts[0], *event);
        }
        void event21(const nrfx_twis_event_t *event)
        {
            twisEvent(contexts[1], *event);
        }
        void event22(const nrfx_twis_event_t *event)
        {
            twisEvent(contexts[2], *event);
        }
        void event30(const nrfx_twis_event_t *event)
        {
            twisEvent(contexts[3], *event);
        }

        const nrfx_twis_event_handler_t handlers[instance_count] = {event20, event21, event22,
                                                                    event30};

        SerialFabricResult validateAdapter(std::uint8_t instance, const ValidatedSerialRoute &route,
                                           int &driver_error) noexcept
        {
            driver_error = 0;
            auto *const context = contextFor(instance);
            std::uint32_t ignored = 0U;
            const auto configuration =
                context == nullptr ? TwisConfiguration{} : context->configuration;
            if ((context == nullptr) || (configuration.primary_address == 0U) ||
                (configuration.primary_address > 0x7FU) ||
                (configuration.secondary_address > 0x7FU) ||
                ((configuration.secondary_address != 0U) &&
                 (configuration.secondary_address == configuration.primary_address)) ||
                !pselFor(route, SerialSignal::scl, ignored) ||
                !pselFor(route, SerialSignal::sda, ignored))
            {
                return SerialFabricResult::invalid_argument;
            }
            return SerialFabricResult::success;
        }

        SerialFabricResult activateAdapter(std::uint8_t instance, const ValidatedSerialRoute &route,
                                           int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            const int index = instanceIndex(instance);
            if ((context == nullptr) || (index < 0))
            {
                return SerialFabricResult::unsupported_instance;
            }
            std::uint32_t scl = 0U;
            std::uint32_t sda = 0U;
            if (!pselFor(route, SerialSignal::scl, scl) || !pselFor(route, SerialSignal::sda, sda))
            {
                return SerialFabricResult::invalid_argument;
            }
            context->driver_configuration =
                NRFX_TWIS_DEFAULT_CONFIG(scl, sda, context->configuration.primary_address);
            context->driver_configuration.addr[1] = context->configuration.secondary_address;
            if (context->configuration.internal_pullups)
            {
                context->driver_configuration.scl_pull = NRF_GPIO_PIN_PULLUP;
                context->driver_configuration.sda_pull = NRF_GPIO_PIN_PULLUP;
            }
            driver_error =
                nrfx_twis_init(&context->driver, &context->driver_configuration, handlers[index]);
            if (driver_error != 0)
            {
                return mapResult(driver_error);
            }
            nrfx_twis_enable(&context->driver);
            context->route = route;
            context->tx[0] = {};
            context->tx[1] = {};
            context->rx[0] = {};
            context->rx[1] = {};
            context->event_head = 0U;
            context->event_tail = 0U;
            context->event_count = 0U;
            context->event_overflow = false;
            atomic_clear(&context->buffers_active);
            atomic_set(&context->initialized, 1);
            atomic_set(&context->active, 1);
            irq_enable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
            return SerialFabricResult::success;
        }

        void cancelRecords(TwisContext &context)
        {
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            for (auto &record : context.tx)
            {
                if (record.address != nullptr)
                {
                    record.state = DmaBufferState::cancelled;
                }
            }
            for (auto &record : context.rx)
            {
                if (record.address != nullptr)
                {
                    record.state = DmaBufferState::cancelled;
                }
            }
            k_spin_unlock(&context.lock, key);
        }

        SerialFabricResult requestStopAdapter(std::uint8_t instance, int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
            {
                return SerialFabricResult::unsupported_instance;
            }
            irq_disable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
            if (atomic_get(&context->initialized) != 0)
            {
                nrfx_twis_disable(&context->driver);
                nrfx_twis_uninit(&context->driver);
                atomic_clear(&context->initialized);
            }
            cancelRecords(*context);
            atomic_clear(&context->buffers_active);
            driver_error = 0;
            return SerialFabricResult::success;
        }

        bool stoppedAdapter(std::uint8_t instance) noexcept
        {
            const auto *const context = contextFor(instance);
            return context != nullptr && atomic_get(&context->initialized) == 0;
        }

        SerialFabricResult deactivateAdapter(std::uint8_t instance, int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
            {
                return SerialFabricResult::unsupported_instance;
            }
            if (atomic_get(&context->initialized) != 0)
            {
                nrfx_twis_disable(&context->driver);
                nrfx_twis_uninit(&context->driver);
                atomic_clear(&context->initialized);
            }
            atomic_clear(&context->active);
            context->route = {};
            driver_error = 0;
            return SerialFabricResult::success;
        }

        void handleIrq(std::uint8_t instance) noexcept
        {
            if (auto *const context = contextFor(instance))
            {
                nrfx_twis_irq_handler(&context->driver);
            }
        }

        const SerialFabricDriverAdapter adapter{validateAdapter,    activateAdapter,
                                                requestStopAdapter, stoppedAdapter,
                                                deactivateAdapter,  handleIrq};

        int registerAdapters()
        {
            const std::uint8_t instances[] = {20U, 21U, 22U, 30U};
            for (const std::uint8_t instance : instances)
            {
                if (internal::registerSerialFabricAdapter(SerialPersonality::twis, instance,
                                                          adapter) != SerialFabricResult::success)
                {
                    return -EIO;
                }
            }
            return 0;
        }

        SYS_INIT(registerAdapters, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace

    SerialFabricResult TwisHandle::configure(const TwisConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const auto current = state();
        if (((current != SerialFabricState::inactive) && (current != SerialFabricState::staged)) ||
            (configuration.primary_address == 0U) || (configuration.primary_address > 0x7FU) ||
            (configuration.secondary_address > 0x7FU) ||
            ((configuration.secondary_address != 0U) &&
             (configuration.secondary_address == configuration.primary_address)))
        {
            return SerialFabricResult::invalid_argument;
        }
        auto *const context = contextFor(instance());
        if (context == nullptr)
        {
            return SerialFabricResult::unsupported_instance;
        }
        context->configuration = configuration;
        return SerialFabricResult::success;
    }

    SerialFabricResult TwisHandle::queueBuffers(const void *tx_buffer, std::size_t tx_size,
                                                void *rx_buffer, std::size_t rx_size,
                                                const void *next_tx_buffer,
                                                std::size_t next_tx_size, void *next_rx_buffer,
                                                std::size_t next_rx_size) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        auto *const context = contextFor(instance());
        if ((context == nullptr) ||
            !internal::isSerialFabricHandleActive(SerialPersonality::twis, instance()))
        {
            return SerialFabricResult::wrong_state;
        }
        if (((tx_buffer == nullptr) != (tx_size == 0U)) ||
            ((rx_buffer == nullptr) != (rx_size == 0U)) ||
            ((next_tx_buffer == nullptr) != (next_tx_size == 0U)) ||
            ((next_rx_buffer == nullptr) != (next_rx_size == 0U)) ||
            ((tx_size == 0U) && (rx_size == 0U)) || (tx_size > UINT16_MAX) ||
            (rx_size > UINT16_MAX) || (next_tx_size > UINT16_MAX) || (next_rx_size > UINT16_MAX) ||
            !leasedBuffer(*context, tx_buffer, tx_size) ||
            !leasedBuffer(*context, rx_buffer, rx_size) ||
            !leasedBuffer(*context, next_tx_buffer, next_tx_size) ||
            !leasedBuffer(*context, next_rx_buffer, next_rx_size) ||
            atomic_get(&context->buffers_active) != 0)
        {
            return SerialFabricResult::invalid_argument;
        }
        const k_spinlock_key_t key = k_spin_lock(&context->lock);
        context->tx[0] = {tx_buffer, tx_size, DmaBufferState::queued};
        context->tx[1] = {next_tx_buffer, next_tx_size, DmaBufferState::queued};
        context->rx[0] = {rx_buffer, rx_size, DmaBufferState::queued};
        context->rx[1] = {next_rx_buffer, next_rx_size, DmaBufferState::queued};
        k_spin_unlock(&context->lock, key);
        atomic_set(&context->buffers_active, 1);
        return SerialFabricResult::success;
    }

    SerialFabricResult TwisHandle::cancelBuffers() noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        auto *const context = contextFor(instance());
        const int index = instanceIndex(instance());
        if ((context == nullptr) || (index < 0) || atomic_get(&context->active) == 0 ||
            atomic_get(&context->buffers_active) == 0 || atomic_get(&context->initialized) == 0)
        {
            return SerialFabricResult::wrong_state;
        }
        irq_disable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
        nrfx_twis_disable(&context->driver);
        nrfx_twis_uninit(&context->driver);
        atomic_clear(&context->initialized);
        cancelRecords(*context);
        atomic_clear(&context->buffers_active);
        const int result =
            nrfx_twis_init(&context->driver, &context->driver_configuration, handlers[index]);
        if (result != 0)
        {
            pushEvent(*context, {TwiFabricEventType::error, context->configuration.primary_address,
                                 nullptr, nullptr, 0U, 0U, static_cast<std::uint32_t>(-result)});
            return mapResult(result);
        }
        nrfx_twis_enable(&context->driver);
        atomic_set(&context->initialized, 1);
        irq_enable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
        pushEvent(*context,
                  {TwiFabricEventType::transfer_cancelled, context->configuration.primary_address,
                   context->tx[0].address, const_cast<void *>(context->rx[0].address), 0U, 0U, 0U});
        return SerialFabricResult::success;
    }

    bool TwisHandle::takeEvent(TwiFabricEvent &event) noexcept
    {
        auto *const context = contextFor(instance());
        if (context == nullptr)
        {
            return false;
        }
        const k_spinlock_key_t key = k_spin_lock(&context->lock);
        if (context->event_overflow)
        {
            context->event_overflow = false;
            event = {TwiFabricEventType::error, 0U, nullptr, nullptr, 0U, 0U, event_queue_overflow};
            k_spin_unlock(&context->lock, key);
            return true;
        }
        if (context->event_count == 0U)
        {
            k_spin_unlock(&context->lock, key);
            return false;
        }
        event = context->events[context->event_head];
        context->event_head =
            static_cast<std::uint8_t>((context->event_head + 1U) % event_capacity);
        --context->event_count;
        k_spin_unlock(&context->lock, key);
        return true;
    }

    DmaBufferState TwisHandle::bufferState(const void *buffer) const noexcept
    {
        auto *const context = contextFor(instance());
        if (context == nullptr)
        {
            return DmaBufferState::error;
        }
        const k_spinlock_key_t key = k_spin_lock(&context->lock);
        DmaBufferState state = DmaBufferState::application_owned;
        for (const auto &record : context->tx)
        {
            if (record.address == buffer)
            {
                state = record.state;
            }
        }
        for (const auto &record : context->rx)
        {
            if (record.address == buffer)
            {
                state = record.state;
            }
        }
        k_spin_unlock(&context->lock, key);
        return state;
    }
} // namespace nucode::arduino
