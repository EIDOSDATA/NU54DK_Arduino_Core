/**
 * @file TwimFabric.cpp
 * @brief M24 TWIM20/21/22/30 sync/async repeated-start EasyDMA adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"

#include <nrfx_twim.h>

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
        inline constexpr std::size_t event_capacity = 8U;
        inline constexpr std::uint32_t event_queue_overflow = 0x80000000UL;

        struct BufferRecord
        {
            const void *address{nullptr};
            std::size_t size{0U};
            DmaBufferState state{DmaBufferState::application_owned};
        };

        struct TwimContext
        {
            nrfx_twim_t driver;
            TwimConfiguration configuration{};
            ValidatedSerialRoute route{};
            BufferRecord buffers[2]{};
            TwiFabricEvent events[event_capacity]{};
            std::uint8_t event_head{0U};
            std::uint8_t event_tail{0U};
            std::uint8_t event_count{0U};
            bool event_overflow{false};
            atomic_t active{0};
            atomic_t transfer_active{0};
            atomic_t cancel_requested{0};
            k_spinlock lock{};
        };

        TwimContext contexts[instance_count] = {
            {NRFX_TWIM_INSTANCE(NRF_TWIM20)},
            {NRFX_TWIM_INSTANCE(NRF_TWIM21)},
            {NRFX_TWIM_INSTANCE(NRF_TWIM22)},
            {NRFX_TWIM_INSTANCE(NRF_TWIM30)},
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

        [[nodiscard]] TwimContext *contextFor(std::uint8_t instance) noexcept
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
            case -ENOTSUP:
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

        [[nodiscard]] bool rangeInside(const SerialDmaWorkspace &workspace,
                                       const void *address, std::size_t size) noexcept
        {
            if ((address == nullptr) || (size == 0U))
                return false;
            const auto base = reinterpret_cast<std::uintptr_t>(workspace.address);
            const auto start = reinterpret_cast<std::uintptr_t>(address);
            if ((start < base) || (workspace.size > UINTPTR_MAX - base) ||
                (size > UINTPTR_MAX - start))
            {
                return false;
            }
            return (start + size) <= (base + workspace.size);
        }

        [[nodiscard]] bool leasedBuffer(const TwimContext &context, const void *address,
                                        std::size_t size) noexcept
        {
            if ((address == nullptr) && (size == 0U))
                return true;
            for (std::size_t index = 0U; index < context.route.dma_workspace_count;
                 ++index)
            {
                if (rangeInside(context.route.dma_workspaces[index], address, size))
                    return true;
            }
            return false;
        }

        [[nodiscard]] const SerialSignalPin *
        signalPin(const ValidatedSerialRoute &route, SerialSignal signal) noexcept
        {
            for (std::size_t index = 0U; index < route.pin_count; ++index)
            {
                if (route.pins[index].signal == signal)
                    return &route.pins[index];
            }
            return nullptr;
        }

        [[nodiscard]] bool pselFor(const ValidatedSerialRoute &route,
                                   SerialSignal signal, std::uint32_t &psel) noexcept
        {
            const auto *const entry = signalPin(route, signal);
            return entry != nullptr &&
                   internal::nu54dkSerialFabricPsel(entry->pin, psel) ==
                       SerialFabricResult::success;
        }

        [[nodiscard]] bool frequencyFor(TwiFabricFrequency frequency,
                                        nrf_twim_frequency_t &value) noexcept
        {
            switch (frequency)
            {
            case TwiFabricFrequency::standard:
                value = NRF_TWIM_FREQ_100K;
                return true;
            case TwiFabricFrequency::fast:
                value = NRF_TWIM_FREQ_400K;
                return true;
            case TwiFabricFrequency::fast_plus:
                value = NRF_TWIM_FREQ_1000K;
                return true;
            default:
                return false;
            }
        }

        void setBufferState(TwimContext &context, const void *address,
                            DmaBufferState state) noexcept
        {
            if (address == nullptr)
                return;
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            for (auto &buffer : context.buffers)
            {
                if (buffer.address == address)
                    buffer.state = state;
            }
            k_spin_unlock(&context.lock, key);
        }

        void pushEvent(TwimContext &context, const TwiFabricEvent &event) noexcept
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

        [[nodiscard]] TwiFabricEventType eventType(nrfx_twim_event_type_t type)
        {
            switch (type)
            {
            case NRFX_TWIM_EVT_DONE:
                return TwiFabricEventType::transfer_complete;
            case NRFX_TWIM_EVT_ADDRESS_NACK:
                return TwiFabricEventType::address_nack;
            case NRFX_TWIM_EVT_DATA_NACK:
                return TwiFabricEventType::data_nack;
            case NRFX_TWIM_EVT_OVERRUN:
                return TwiFabricEventType::overrun;
            case NRFX_TWIM_EVT_BUS_ERROR:
                return TwiFabricEventType::bus_error;
            default:
                return TwiFabricEventType::error;
            }
        }

        void twimEvent(const nrfx_twim_event_t *event, void *opaque)
        {
            auto &context = *static_cast<TwimContext *>(opaque);
            const bool cancelled = atomic_get(&context.cancel_requested) != 0;
            const auto type = cancelled ? TwiFabricEventType::transfer_cancelled
                                        : eventType(event->type);
            const auto state = cancelled ? DmaBufferState::cancelled
                               : event->type == NRFX_TWIM_EVT_DONE
                                   ? DmaBufferState::completed
                                   : DmaBufferState::error;
            setBufferState(context, event->xfer_desc.p_primary_buf, state);
            setBufferState(context, event->xfer_desc.p_secondary_buf, state);
            atomic_clear(&context.cancel_requested);
            atomic_clear(&context.transfer_active);

            const bool primary_tx = (event->xfer_desc.type == NRFX_TWIM_XFER_TX) ||
                                    (event->xfer_desc.type == NRFX_TWIM_XFER_TXRX) ||
                                    (event->xfer_desc.type == NRFX_TWIM_XFER_TXTX);
            const bool secondary_rx = event->xfer_desc.type == NRFX_TWIM_XFER_TXRX;
            pushEvent(
                context,
                {type, event->xfer_desc.address,
                 primary_tx ? event->xfer_desc.p_primary_buf : nullptr,
                 primary_tx ? (secondary_rx ? event->xfer_desc.p_secondary_buf : nullptr)
                            : event->xfer_desc.p_primary_buf,
                 primary_tx ? event->xfer_desc.primary_length : 0U,
                 primary_tx ? (secondary_rx ? event->xfer_desc.secondary_length : 0U)
                            : event->xfer_desc.primary_length,
                 static_cast<std::uint32_t>(event->type)});
        }

        SerialFabricResult validateAdapter(std::uint8_t instance,
                                           const ValidatedSerialRoute &route,
                                           int &driver_error) noexcept
        {
            driver_error = 0;
            auto *const context = contextFor(instance);
            std::uint32_t ignored = 0U;
            nrf_twim_frequency_t frequency{};
            if ((context == nullptr) ||
                !frequencyFor(context->configuration.frequency, frequency) ||
                !pselFor(route, SerialSignal::scl, ignored) ||
                !pselFor(route, SerialSignal::sda, ignored))
            {
                return SerialFabricResult::invalid_argument;
            }
            context->route = route;
            return SerialFabricResult::success;
        }

        SerialFabricResult activateAdapter(std::uint8_t instance,
                                           const ValidatedSerialRoute &route,
                                           int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
                return SerialFabricResult::unsupported_instance;
            std::uint32_t scl = 0U;
            std::uint32_t sda = 0U;
            nrf_twim_frequency_t frequency{};
            if (!pselFor(route, SerialSignal::scl, scl) ||
                !pselFor(route, SerialSignal::sda, sda) ||
                !frequencyFor(context->configuration.frequency, frequency))
            {
                return SerialFabricResult::invalid_argument;
            }
            nrfx_twim_config_t configuration = NRFX_TWIM_DEFAULT_CONFIG(scl, sda);
            configuration.frequency = frequency;
            driver_error =
                nrfx_twim_init(&context->driver, &configuration, twimEvent, context);
            if (driver_error != 0)
                return mapResult(driver_error);
            // nrfx_twim_init leaves the instance INITIALIZED, not POWERED_ON.
            // xfer() requires the explicit enable transition on this nrfx API.
            nrfx_twim_enable(&context->driver);
            context->route = route;
            context->buffers[0] = {};
            context->buffers[1] = {};
            context->event_head = 0U;
            context->event_tail = 0U;
            context->event_count = 0U;
            context->event_overflow = false;
            atomic_clear(&context->transfer_active);
            atomic_clear(&context->cancel_requested);
            atomic_set(&context->active, 1);
            irq_enable(NRFX_IRQ_NUMBER_GET(context->driver.p_twim));
            return SerialFabricResult::success;
        }

        SerialFabricResult requestStopAdapter(std::uint8_t instance,
                                              int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
                return SerialFabricResult::unsupported_instance;
            driver_error = 0;
            if (atomic_get(&context->transfer_active) != 0)
            {
                atomic_set(&context->cancel_requested, 1);
                nrfy_twim_task_trigger(context->driver.p_twim, NRF_TWIM_TASK_STOP);
            }
            return SerialFabricResult::success;
        }

        bool stoppedAdapter(std::uint8_t instance) noexcept
        {
            auto *const context = contextFor(instance);
            return context != nullptr && atomic_get(&context->transfer_active) == 0 &&
                   !nrfx_twim_is_busy(&context->driver);
        }

        SerialFabricResult deactivateAdapter(std::uint8_t instance,
                                             int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
                return SerialFabricResult::unsupported_instance;
            irq_disable(NRFX_IRQ_NUMBER_GET(context->driver.p_twim));
            nrfx_twim_uninit(&context->driver);
            atomic_clear(&context->active);
            context->route = {};
            context->buffers[0] = {};
            context->buffers[1] = {};
            driver_error = 0;
            return SerialFabricResult::success;
        }

        void handleIrq(std::uint8_t instance) noexcept
        {
            if (auto *const context = contextFor(instance))
                nrfx_twim_irq_handler(&context->driver);
        }

        const SerialFabricDriverAdapter adapter{validateAdapter, activateAdapter,
                                                requestStopAdapter, stoppedAdapter,
                                                deactivateAdapter, handleIrq};

        int registerAdapters()
        {
            const std::uint8_t instances[] = {20U, 21U, 22U, 30U};
            for (const std::uint8_t instance : instances)
            {
                if (internal::registerSerialFabricAdapter(SerialPersonality::twim, instance,
                                                          adapter) !=
                    SerialFabricResult::success)
                {
                    return -EIO;
                }
            }
            return 0;
        }

        SYS_INIT(registerAdapters, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace

    SerialFabricResult
    TwimHandle::configure(const TwimConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
            return SerialFabricResult::invalid_context;
        const auto current = state();
        nrf_twim_frequency_t ignored{};
        if (((current != SerialFabricState::inactive) &&
             (current != SerialFabricState::staged)) ||
            !frequencyFor(configuration.frequency, ignored))
        {
            return SerialFabricResult::invalid_argument;
        }
        auto *const context = contextFor(instance());
        if (context == nullptr)
            return SerialFabricResult::unsupported_instance;
        context->configuration = configuration;
        return SerialFabricResult::success;
    }

    SerialFabricResult TwimHandle::transferAsync(std::uint8_t address,
                                                 const void *tx_buffer,
                                                 std::size_t tx_size,
                                                 void *rx_buffer,
                                                 std::size_t rx_size) noexcept
    {
        if (k_is_in_isr())
            return SerialFabricResult::invalid_context;
        auto *const context = contextFor(instance());
        if ((context == nullptr) || !internal::isSerialFabricHandleActive(
                                        SerialPersonality::twim, instance()))
        {
            return SerialFabricResult::wrong_state;
        }
        if ((address == 0U) || (address > 0x7FU) ||
            ((tx_buffer == nullptr) != (tx_size == 0U)) ||
            ((rx_buffer == nullptr) != (rx_size == 0U)) ||
            ((tx_size == 0U) && (rx_size == 0U)) || (tx_size > UINT16_MAX) ||
            (rx_size > UINT16_MAX) || !leasedBuffer(*context, tx_buffer, tx_size) ||
            !leasedBuffer(*context, rx_buffer, rx_size) ||
            atomic_get(&context->transfer_active) != 0)
        {
            return SerialFabricResult::invalid_argument;
        }

        nrfx_twim_xfer_desc_t descriptor{};
        descriptor.address = address;
        descriptor.p_primary_buf =
            const_cast<std::uint8_t *>(static_cast<const std::uint8_t *>(tx_buffer));
        descriptor.primary_length = tx_size;
        descriptor.p_secondary_buf = static_cast<std::uint8_t *>(rx_buffer);
        descriptor.secondary_length = rx_size;
        if ((tx_size != 0U) && (rx_size != 0U))
        {
            descriptor.type = NRFX_TWIM_XFER_TXRX;
        }
        else if (tx_size != 0U)
        {
            descriptor.type = NRFX_TWIM_XFER_TX;
        }
        else
        {
            descriptor.type = NRFX_TWIM_XFER_RX;
            descriptor.p_primary_buf = static_cast<std::uint8_t *>(rx_buffer);
            descriptor.primary_length = rx_size;
            descriptor.p_secondary_buf = nullptr;
            descriptor.secondary_length = 0U;
        }
        {
            const k_spinlock_key_t key = k_spin_lock(&context->lock);
            context->buffers[0] = {tx_buffer, tx_size, DmaBufferState::dma_owned};
            context->buffers[1] = {rx_buffer, rx_size, DmaBufferState::dma_owned};
            k_spin_unlock(&context->lock, key);
        }
        atomic_clear(&context->cancel_requested);
        atomic_set(&context->transfer_active, 1);
        const int result = nrfx_twim_xfer(&context->driver, &descriptor, 0U);
        if (result != 0)
        {
            atomic_clear(&context->transfer_active);
            setBufferState(*context, tx_buffer, DmaBufferState::error);
            setBufferState(*context, rx_buffer, DmaBufferState::error);
            return mapResult(result);
        }
        return SerialFabricResult::success;
    }

    SerialFabricResult TwimHandle::transfer(std::uint8_t address,
                                            const void *tx_buffer,
                                            std::size_t tx_size, void *rx_buffer,
                                            std::size_t rx_size,
                                            std::uint32_t timeout_us) noexcept
    {
        if ((timeout_us == 0U) || k_is_in_isr())
            return SerialFabricResult::invalid_argument;
        auto result = transferAsync(address, tx_buffer, tx_size, rx_buffer, rx_size);
        if (result != SerialFabricResult::success)
            return result;
        for (std::uint32_t elapsed = 0U; elapsed < timeout_us; elapsed += 10U)
        {
            TwiFabricEvent event{};
            if (takeEvent(event))
            {
                if (event.type == TwiFabricEventType::transfer_complete)
                    return SerialFabricResult::success;
                if (event.type != TwiFabricEventType::transfer_cancelled)
                    return SerialFabricResult::driver_error;
            }
            k_busy_wait(10U);
        }
        (void)cancelTransfer();
        return SerialFabricResult::stop_timeout;
    }

    SerialFabricResult TwimHandle::cancelTransfer() noexcept
    {
        if (k_is_in_isr())
            return SerialFabricResult::invalid_context;
        auto *const context = contextFor(instance());
        if ((context == nullptr) || atomic_get(&context->active) == 0 ||
            atomic_get(&context->transfer_active) == 0)
        {
            return SerialFabricResult::wrong_state;
        }
        atomic_set(&context->cancel_requested, 1);
        nrfy_twim_task_trigger(context->driver.p_twim, NRF_TWIM_TASK_STOP);
        return SerialFabricResult::success;
    }

    SerialFabricResult TwimHandle::recoverBus() noexcept
    {
        if (k_is_in_isr())
            return SerialFabricResult::invalid_context;
        auto *const context = contextFor(instance());
        if ((context == nullptr) || (state() != SerialFabricState::staged))
            return SerialFabricResult::wrong_state;
        std::uint32_t scl = 0U;
        std::uint32_t sda = 0U;
        if (!pselFor(context->route, SerialSignal::scl, scl) ||
            !pselFor(context->route, SerialSignal::sda, sda))
        {
            return SerialFabricResult::invalid_argument;
        }
        return mapResult(nrfx_twim_bus_recover(scl, sda));
    }

    bool TwimHandle::takeEvent(TwiFabricEvent &event) noexcept
    {
        auto *const context = contextFor(instance());
        if (context == nullptr)
            return false;
        const k_spinlock_key_t key = k_spin_lock(&context->lock);
        if (context->event_overflow)
        {
            context->event_overflow = false;
            event = {TwiFabricEventType::error, 0U, nullptr, nullptr, 0U, 0U,
                     event_queue_overflow};
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

    DmaBufferState TwimHandle::bufferState(const void *buffer) const noexcept
    {
        auto *const context = contextFor(instance());
        if (context == nullptr)
            return DmaBufferState::error;
        const k_spinlock_key_t key = k_spin_lock(&context->lock);
        DmaBufferState state = DmaBufferState::application_owned;
        for (const auto &record : context->buffers)
        {
            if (record.address == buffer)
                state = record.state;
        }
        k_spin_unlock(&context->lock, key);
        return state;
    }
} // namespace nucode::arduino
