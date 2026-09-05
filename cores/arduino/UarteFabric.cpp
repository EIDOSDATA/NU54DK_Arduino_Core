/**
 * @file UarteFabric.cpp
 * @brief M24 UARTE00/20/21/22/30 async EasyDMA adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"

#include <nrfx_uarte.h>

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
        using internal::SerialFabricDriverAdapter;
        using internal::ValidatedSerialRoute;

        inline constexpr std::size_t uarte_count = 5U;
        inline constexpr std::size_t event_capacity = 8U;
        inline constexpr std::size_t buffer_capacity = 3U;
        inline constexpr std::uint32_t event_queue_overflow = 0x80000000UL;

        struct BufferRecord
        {
            const void *address{nullptr};
            std::size_t size{0U};
            DmaBufferState state{DmaBufferState::application_owned};
        };

        struct UarteContext
        {
            nrfx_uarte_t driver;
            UarteConfiguration configuration{};
            ValidatedSerialRoute route{};
            BufferRecord buffers[buffer_capacity]{};
            UarteEvent events[event_capacity]{};
            std::uint8_t event_head{0U};
            std::uint8_t event_tail{0U};
            std::uint8_t event_count{0U};
            bool event_overflow{false};
            atomic_t active{0};
            atomic_t tx_active{0};
            atomic_t rx_active{0};
            atomic_t cancelling_rx{0};
            k_spinlock lock{};
        };

        UarteContext contexts[uarte_count] = {
            {NRFX_UARTE_INSTANCE(NRF_UARTE00)}, {NRFX_UARTE_INSTANCE(NRF_UARTE20)},
            {NRFX_UARTE_INSTANCE(NRF_UARTE21)}, {NRFX_UARTE_INSTANCE(NRF_UARTE22)},
            {NRFX_UARTE_INSTANCE(NRF_UARTE30)},
        };

        [[nodiscard]] constexpr int instanceIndex(std::uint8_t instance) noexcept
        {
            switch (instance)
            {
            case 0U:
                return 0;
            case 20U:
                return 1;
            case 21U:
                return 2;
            case 22U:
                return 3;
            case 30U:
                return 4;
            default:
                return -1;
            }
        }

        [[nodiscard]] UarteContext *contextFor(std::uint8_t instance) noexcept
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
                return SerialFabricResult::wrong_state;
            case -ENOMEM:
                return SerialFabricResult::resource_exhausted;
            default:
                return SerialFabricResult::driver_error;
            }
        }

        [[nodiscard]] bool baudrate(std::uint32_t value, nrf_uarte_baudrate_t &result) noexcept
        {
            switch (value)
            {
            case 9600U:
                result = NRF_UARTE_BAUDRATE_9600;
                return true;
            case 19200U:
                result = NRF_UARTE_BAUDRATE_19200;
                return true;
            case 38400U:
                result = NRF_UARTE_BAUDRATE_38400;
                return true;
            case 57600U:
                result = NRF_UARTE_BAUDRATE_57600;
                return true;
            case 115200U:
                result = NRF_UARTE_BAUDRATE_115200;
                return true;
            case 230400U:
                result = NRF_UARTE_BAUDRATE_230400;
                return true;
            case 460800U:
                result = NRF_UARTE_BAUDRATE_460800;
                return true;
            case 921600U:
                result = NRF_UARTE_BAUDRATE_921600;
                return true;
            case 1000000U:
                result = NRF_UARTE_BAUDRATE_1000000;
                return true;
            default:
                return false;
            }
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
            const SerialSignalPin *const entry = signalPin(route, signal);
            return entry != nullptr && internal::nu54dkSerialFabricPsel(entry->pin, psel) ==
                                           SerialFabricResult::success;
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

        [[nodiscard]] bool leasedBuffer(const UarteContext &context, const void *address,
                                        std::size_t size) noexcept
        {
            for (std::size_t index = 0U; index < context.route.dma_workspace_count; ++index)
            {
                if (rangeInside(context.route.dma_workspaces[index], address, size))
                {
                    return true;
                }
            }
            return false;
        }

        [[nodiscard]] BufferRecord *bufferFor(UarteContext &context, const void *address) noexcept
        {
            for (auto &buffer : context.buffers)
            {
                if (buffer.address == address)
                {
                    return &buffer;
                }
            }
            return nullptr;
        }

        void setBufferState(UarteContext &context, const void *address,
                            DmaBufferState state) noexcept
        {
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            if (auto *const buffer = bufferFor(context, address))
            {
                buffer->state = state;
            }
            k_spin_unlock(&context.lock, key);
        }

        void pushEvent(UarteContext &context, const UarteEvent &event) noexcept
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

        void uarteEvent(const nrfx_uarte_event_t *event, void *opaque)
        {
            auto &context = *static_cast<UarteContext *>(opaque);
            switch (event->type)
            {
            case NRFX_UARTE_EVT_TX_DONE:
            {
                const bool aborted = (event->data.tx.flags & NRFX_UARTE_TX_DONE_ABORTED) != 0U;
                setBufferState(context, event->data.tx.p_buffer,
                               aborted ? DmaBufferState::cancelled : DmaBufferState::completed);
                atomic_clear(&context.tx_active);
                pushEvent(context,
                          {aborted ? UarteEventType::tx_cancelled : UarteEventType::tx_complete,
                           event->data.tx.p_buffer, event->data.tx.length, 0U});
                break;
            }
            case NRFX_UARTE_EVT_RX_DONE:
            {
                const bool cancelling = atomic_get(&context.cancelling_rx) != 0;
                setBufferState(context, event->data.rx.p_buffer,
                               cancelling ? DmaBufferState::cancelled : DmaBufferState::completed);
                pushEvent(context,
                          {cancelling ? UarteEventType::rx_cancelled : UarteEventType::rx_complete,
                           event->data.rx.p_buffer, event->data.rx.length, 0U});
                break;
            }
            case NRFX_UARTE_EVT_RX_BUF_REQUEST:
            {
                const k_spinlock_key_t key = k_spin_lock(&context.lock);
                const auto second = context.buffers[2];
                k_spin_unlock(&context.lock, key);
                if (second.address != nullptr && second.state == DmaBufferState::queued)
                {
                    const int result = nrfx_uarte_rx_buffer_set(
                        &context.driver,
                        static_cast<std::uint8_t *>(const_cast<void *>(second.address)),
                        second.size);
                    if (result == 0)
                    {
                        setBufferState(context, second.address, DmaBufferState::dma_owned);
                    }
                    else
                    {
                        setBufferState(context, second.address, DmaBufferState::error);
                        pushEvent(context, {UarteEventType::error, second.address, 0U,
                                            static_cast<std::uint32_t>(-result)});
                    }
                }
                else
                {
                    pushEvent(context, {UarteEventType::rx_buffer_needed, nullptr, 0U, 0U});
                }
                break;
            }
            case NRFX_UARTE_EVT_RX_DISABLED:
                atomic_clear(&context.rx_active);
                atomic_clear(&context.cancelling_rx);
                break;
            case NRFX_UARTE_EVT_ERROR:
                atomic_clear(&context.rx_active);
                setBufferState(context, event->data.error.rx.p_buffer, DmaBufferState::error);
                pushEvent(context, {UarteEventType::error, event->data.error.rx.p_buffer,
                                    event->data.error.rx.length, event->data.error.error_mask});
                break;
            default:
                break;
            }
        }

        SerialFabricResult validateAdapter(std::uint8_t instance, const ValidatedSerialRoute &route,
                                           int &driver_error) noexcept
        {
            driver_error = 0;
            auto *const context = contextFor(instance);
            nrf_uarte_baudrate_t ignored{};
            if ((context == nullptr) || !baudrate(context->configuration.baud_rate, ignored))
            {
                return SerialFabricResult::invalid_argument;
            }
            std::uint32_t pin = 0U;
            if (!pselFor(route, SerialSignal::txd, pin) || !pselFor(route, SerialSignal::rxd, pin))
            {
                return SerialFabricResult::unsupported_route;
            }
            if (context->configuration.hardware_flow_control &&
                (!pselFor(route, SerialSignal::rts, pin) ||
                 !pselFor(route, SerialSignal::cts, pin)))
            {
                return SerialFabricResult::invalid_argument;
            }
            return SerialFabricResult::success;
        }

        SerialFabricResult activateAdapter(std::uint8_t instance, const ValidatedSerialRoute &route,
                                           int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
            {
                return SerialFabricResult::unsupported_instance;
            }
            std::uint32_t tx = 0U;
            std::uint32_t rx = 0U;
            std::uint32_t rts = NRF_UARTE_PSEL_DISCONNECTED;
            std::uint32_t cts = NRF_UARTE_PSEL_DISCONNECTED;
            nrf_uarte_baudrate_t selected_baud{};
            if (!pselFor(route, SerialSignal::txd, tx) || !pselFor(route, SerialSignal::rxd, rx) ||
                !baudrate(context->configuration.baud_rate, selected_baud))
            {
                return SerialFabricResult::invalid_argument;
            }
            if (context->configuration.hardware_flow_control &&
                (!pselFor(route, SerialSignal::rts, rts) ||
                 !pselFor(route, SerialSignal::cts, cts)))
            {
                return SerialFabricResult::invalid_argument;
            }

            nrfx_uarte_config_t configuration = NRFX_UARTE_DEFAULT_CONFIG(tx, rx);
            configuration.p_context = context;
            configuration.rts_pin = rts;
            configuration.cts_pin = cts;
            configuration.baudrate = selected_baud;
            configuration.config.hwfc = context->configuration.hardware_flow_control
                                            ? NRF_UARTE_HWFC_ENABLED
                                            : NRF_UARTE_HWFC_DISABLED;
            configuration.config.parity = context->configuration.parity == UarteParity::even
                                              ? NRF_UARTE_PARITY_INCLUDED
                                              : NRF_UARTE_PARITY_EXCLUDED;

            /**
             * @brief 독점 block lease와 이전 adapter의 STOP 증명 뒤에만 초기화합니다.
             *
             * TWIM/SPIM DMA READY register는 UARTE RXSTARTED와 주소가 겹칩니다. 비활성 block의
             * stale READY를 동작 중인 bootloader RX로 해석하지 않습니다.
             */
            if (context->driver.p_reg->ENABLE != 0U)
            {
                driver_error = -EBUSY;
                return SerialFabricResult::wrong_state;
            }
            nrf_uarte_event_clear(context->driver.p_reg, NRF_UARTE_EVENT_RXSTARTED);
            nrf_uarte_shorts_set(context->driver.p_reg, 0U);
            context->event_head = context->event_tail = context->event_count = 0U;
            context->event_overflow = false;
            for (auto &buffer : context->buffers)
            {
                buffer = {};
            }
            driver_error = nrfx_uarte_init(&context->driver, &configuration, uarteEvent);
            if (driver_error != 0)
            {
                /**
                 * @brief RX/TX 준비 실패 전에 생긴 nrfx 부분 초기화를 남기지 않습니다.
                 */
                if (nrfx_uarte_init_check(&context->driver))
                {
                    nrfx_uarte_uninit(&context->driver);
                }
                return mapResult(driver_error);
            }
            context->route = route;
            atomic_set(&context->active, 1);
            irq_enable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
            return SerialFabricResult::success;
        }

        SerialFabricResult requestStopAdapter(std::uint8_t instance, int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
            {
                return SerialFabricResult::unsupported_instance;
            }
            driver_error = 0;
            if (atomic_get(&context->tx_active) != 0)
            {
                const int result = nrfx_uarte_tx_abort(&context->driver, true);
                if ((result != 0) && (result != -EINPROGRESS))
                {
                    driver_error = result;
                }
                atomic_clear(&context->tx_active);
            }
            if (atomic_get(&context->rx_active) != 0)
            {
                const int result = nrfx_uarte_rx_abort(&context->driver, true, true);
                if ((result != 0) && (result != -EINPROGRESS) && (driver_error == 0))
                {
                    driver_error = result;
                }
                atomic_clear(&context->rx_active);
                atomic_clear(&context->cancelling_rx);
            }
            return driver_error == 0 ? SerialFabricResult::success : mapResult(driver_error);
        }

        bool stoppedAdapter(std::uint8_t instance) noexcept
        {
            const auto *const context = contextFor(instance);
            return context != nullptr && atomic_get(&context->tx_active) == 0 &&
                   atomic_get(&context->rx_active) == 0 &&
                   !nrfx_uarte_tx_in_progress(&context->driver);
        }

        SerialFabricResult deactivateAdapter(std::uint8_t instance, int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
            {
                return SerialFabricResult::unsupported_instance;
            }
            irq_disable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
            nrfx_uarte_uninit(&context->driver);
            atomic_clear(&context->active);
            context->route = {};
            for (auto &buffer : context->buffers)
            {
                buffer = {};
            }
            driver_error = 0;
            return SerialFabricResult::success;
        }

        void handleIrq(std::uint8_t instance) noexcept
        {
            if (auto *const context = contextFor(instance))
            {
                nrfx_uarte_irq_handler(&context->driver);
            }
        }

        const SerialFabricDriverAdapter adapter{validateAdapter,    activateAdapter,
                                                requestStopAdapter, stoppedAdapter,
                                                deactivateAdapter,  handleIrq};

        int registerAdapters()
        {
            const std::uint8_t instances[] = {0U, 20U, 21U, 22U, 30U};
            for (const std::uint8_t instance : instances)
            {
                if (internal::registerSerialFabricAdapter(SerialPersonality::uarte, instance,
                                                          adapter) != SerialFabricResult::success)
                {
                    return -EIO;
                }
            }
            return 0;
        }

        SYS_INIT(registerAdapters, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace

    SerialFabricResult UarteHandle::configure(const UarteConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const internal::SerialFabricOperationGuard operation_guard;
        if ((state() != SerialFabricState::inactive) && (state() != SerialFabricState::staged))
        {
            return SerialFabricResult::wrong_state;
        }
        auto *const context = contextFor(instance());
        nrf_uarte_baudrate_t ignored{};
        if ((context == nullptr) || !baudrate(configuration.baud_rate, ignored))
        {
            return SerialFabricResult::invalid_argument;
        }
        context->configuration = configuration;
        return SerialFabricResult::success;
    }

    SerialFabricResult UarteHandle::transmitAsync(const void *buffer, std::size_t size) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const internal::SerialFabricOperationGuard operation_guard;
        auto *const context = contextFor(instance());
        if ((context == nullptr) ||
            !internal::isSerialFabricHandleActive(SerialPersonality::uarte, instance()))
        {
            return SerialFabricResult::wrong_state;
        }
        if ((size > UINT16_MAX) || !leasedBuffer(*context, buffer, size) ||
            atomic_get(&context->tx_active) != 0)
        {
            return SerialFabricResult::invalid_argument;
        }
        {
            const k_spinlock_key_t key = k_spin_lock(&context->lock);
            context->buffers[0] = {buffer, size, DmaBufferState::dma_owned};
            k_spin_unlock(&context->lock, key);
        }
        atomic_set(&context->tx_active, 1);
        const int result =
            nrfx_uarte_tx(&context->driver, static_cast<const std::uint8_t *>(buffer), size, 0U);
        if (result != 0)
        {
            atomic_clear(&context->tx_active);
            setBufferState(*context, buffer, DmaBufferState::error);
            return mapResult(result);
        }
        return SerialFabricResult::success;
    }

    SerialFabricResult UarteHandle::receiveAsync(void *first_buffer, std::size_t first_size,
                                                 void *second_buffer,
                                                 std::size_t second_size) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const internal::SerialFabricOperationGuard operation_guard;
        auto *const context = contextFor(instance());
        if ((context == nullptr) ||
            !internal::isSerialFabricHandleActive(SerialPersonality::uarte, instance()))
        {
            return SerialFabricResult::wrong_state;
        }
        const bool second_valid = second_buffer != nullptr && second_size != 0U;
        if (context->configuration.continuous_receive &&
            (!second_valid || first_size < 32U || second_size < 32U))
        {
            return SerialFabricResult::invalid_argument;
        }
        if ((first_size > UINT16_MAX) || (second_size > UINT16_MAX) ||
            !leasedBuffer(*context, first_buffer, first_size) ||
            ((second_buffer == nullptr) != (second_size == 0U)) ||
            (second_valid && !leasedBuffer(*context, second_buffer, second_size)) ||
            atomic_get(&context->rx_active) != 0)
        {
            return SerialFabricResult::invalid_argument;
        }
        const auto first_start = reinterpret_cast<std::uintptr_t>(first_buffer);
        const auto first_end = first_start + first_size;
        const auto second_start = reinterpret_cast<std::uintptr_t>(second_buffer);
        const auto second_end = second_start + second_size;
        if (second_valid && first_start < second_end && second_start < first_end)
        {
            return SerialFabricResult::invalid_argument;
        }

        {
            const k_spinlock_key_t key = k_spin_lock(&context->lock);
            context->buffers[1] = {first_buffer, first_size, DmaBufferState::dma_owned};
            context->buffers[2] =
                second_valid ? BufferRecord{second_buffer, second_size, DmaBufferState::queued}
                             : BufferRecord{};
            k_spin_unlock(&context->lock, key);
        }
        atomic_set(&context->rx_active, 1);
        atomic_clear(&context->cancelling_rx);
        int result = nrfx_uarte_rx_buffer_set(
            &context->driver, static_cast<std::uint8_t *>(first_buffer), first_size);
        if (result == 0)
        {
            const auto flags =
                NRFX_UARTE_RX_ENABLE_STOP_ON_END |
                (context->configuration.continuous_receive ? NRFX_UARTE_RX_ENABLE_CONT : 0U);
            result = nrfx_uarte_rx_enable(&context->driver, flags);
        }
        if (result != 0)
        {
            atomic_clear(&context->rx_active);
            setBufferState(*context, first_buffer, DmaBufferState::error);
            return mapResult(result);
        }
        return SerialFabricResult::success;
    }

    SerialFabricResult UarteHandle::cancelTransmit() noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const internal::SerialFabricOperationGuard operation_guard;
        /** @brief lifecycle STOP 예약 중에는 adapter의 취소 상태를 다시 변경하지 않습니다. */
        if (!internal::isSerialFabricHandleActive(SerialPersonality::uarte, instance()))
        {
            return SerialFabricResult::wrong_state;
        }

        auto *const context = contextFor(instance());
        if ((context == nullptr) || atomic_get(&context->active) == 0 ||
            atomic_get(&context->tx_active) == 0)
        {
            return SerialFabricResult::wrong_state;
        }
        const int result = nrfx_uarte_tx_abort(&context->driver, false);
        return result == 0 ? SerialFabricResult::success : mapResult(result);
    }

    SerialFabricResult UarteHandle::cancelReceive() noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const internal::SerialFabricOperationGuard operation_guard;
        /** @brief lifecycle STOP 예약 중에는 adapter의 취소 상태를 다시 변경하지 않습니다. */
        if (!internal::isSerialFabricHandleActive(SerialPersonality::uarte, instance()))
        {
            return SerialFabricResult::wrong_state;
        }

        auto *const context = contextFor(instance());
        if ((context == nullptr) || atomic_get(&context->active) == 0 ||
            atomic_get(&context->rx_active) == 0)
        {
            return SerialFabricResult::wrong_state;
        }
        atomic_set(&context->cancelling_rx, 1);
        const int result = nrfx_uarte_rx_abort(&context->driver, true, false);
        if (result != 0)
        {
            atomic_clear(&context->cancelling_rx);
        }
        return result == 0 ? SerialFabricResult::success : mapResult(result);
    }

    bool UarteHandle::takeEvent(UarteEvent &event) noexcept
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
            event = {UarteEventType::error, nullptr, 0U, event_queue_overflow};
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

    DmaBufferState UarteHandle::bufferState(const void *buffer) const noexcept
    {
        auto *const context = contextFor(instance());
        if (context == nullptr)
        {
            return DmaBufferState::error;
        }
        const k_spinlock_key_t key = k_spin_lock(&context->lock);
        const auto *const record = bufferFor(*context, buffer);
        const auto state = record == nullptr ? DmaBufferState::application_owned : record->state;
        k_spin_unlock(&context->lock, key);
        return state;
    }
} // namespace nucode::arduino
