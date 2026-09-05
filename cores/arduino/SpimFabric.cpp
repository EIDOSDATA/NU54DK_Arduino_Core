/**
 * @file SpimFabric.cpp
 * @brief M24 SPIM00/20/21/22/30 sync/async EasyDMA adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"

#include <nrfx_spim.h>

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

        inline constexpr std::size_t instance_count = 5U;
        inline constexpr std::size_t event_capacity = 8U;
        inline constexpr std::uint32_t event_queue_overflow = 0x80000000UL;
        /** @brief SPIM00 128 MHz core에서 약 2 us CSN setup/hold를 만드는 최대 cycle 수입니다. */
        inline constexpr std::uint8_t spim00_csn_duration_cycles = 255U;
        /** @brief SPIM20/21/22/30 16 MHz core에서 2 us를 넘기는 CSN cycle 수입니다. */
        inline constexpr std::uint8_t serial_csn_duration_cycles = 33U;

        struct BufferRecord
        {
            const void *address{nullptr};
            std::size_t size{0U};
            DmaBufferState state{DmaBufferState::application_owned};
        };

        struct SpimContext
        {
            nrfx_spim_t driver;
            SpiFabricConfiguration configuration{};
            ValidatedSerialRoute route{};
            BufferRecord buffers[2]{};
            SpiFabricEvent events[event_capacity]{};
            std::uint8_t event_head{0U};
            std::uint8_t event_tail{0U};
            std::uint8_t event_count{0U};
            bool event_overflow{false};
            atomic_t active{0};
            atomic_t transfer_active{0};
            k_spinlock lock{};
        };

        SpimContext contexts[instance_count] = {
            {NRFX_SPIM_INSTANCE(NRF_SPIM00)}, {NRFX_SPIM_INSTANCE(NRF_SPIM20)},
            {NRFX_SPIM_INSTANCE(NRF_SPIM21)}, {NRFX_SPIM_INSTANCE(NRF_SPIM22)},
            {NRFX_SPIM_INSTANCE(NRF_SPIM30)},
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

        [[nodiscard]] SpimContext *contextFor(std::uint8_t instance) noexcept
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

        [[nodiscard]] bool leasedBuffer(const SpimContext &context, const void *address,
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

        [[nodiscard]] bool spiMode(SpiFabricMode mode, nrf_spim_mode_t &value) noexcept
        {
            switch (mode)
            {
            case SpiFabricMode::mode0:
                value = NRF_SPIM_MODE_0;
                return true;
            case SpiFabricMode::mode1:
                value = NRF_SPIM_MODE_1;
                return true;
            case SpiFabricMode::mode2:
                value = NRF_SPIM_MODE_2;
                return true;
            case SpiFabricMode::mode3:
                value = NRF_SPIM_MODE_3;
                return true;
            default:
                return false;
            }
        }

        void setBufferState(SpimContext &context, const void *address,
                            DmaBufferState state) noexcept
        {
            if (address == nullptr)
            {
                return;
            }
            const k_spinlock_key_t key = k_spin_lock(&context.lock);
            for (auto &buffer : context.buffers)
            {
                if (buffer.address == address)
                {
                    buffer.state = state;
                }
            }
            k_spin_unlock(&context.lock, key);
        }

        void pushEvent(SpimContext &context, const SpiFabricEvent &event) noexcept
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

        void spimEvent(const nrfx_spim_event_t *event, void *opaque)
        {
            auto &context = *static_cast<SpimContext *>(opaque);
            if (event->type != NRFX_SPIM_EVENT_DONE)
            {
                return;
            }
            setBufferState(context, event->xfer_desc.p_tx_buffer, DmaBufferState::completed);
            setBufferState(context, event->xfer_desc.p_rx_buffer, DmaBufferState::completed);
            atomic_clear(&context.transfer_active);
            pushEvent(context, {SpiFabricEventType::transfer_complete, event->xfer_desc.p_tx_buffer,
                                event->xfer_desc.p_rx_buffer, event->xfer_desc.tx_length,
                                event->xfer_desc.rx_length, 0U});
        }

        SerialFabricResult validateAdapter(std::uint8_t instance, const ValidatedSerialRoute &route,
                                           int &driver_error) noexcept
        {
            driver_error = 0;
            auto *const context = contextFor(instance);
            std::uint32_t ignored = 0U;
            nrf_spim_mode_t mode{};
            if ((context == nullptr) || (context->configuration.frequency == 0U) ||
                !spiMode(context->configuration.mode, mode) ||
                !pselFor(route, SerialSignal::sck, ignored) ||
                !pselFor(route, SerialSignal::mosi, ignored) ||
                !pselFor(route, SerialSignal::miso, ignored))
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
            std::uint32_t sck = 0U;
            std::uint32_t mosi = 0U;
            std::uint32_t miso = 0U;
            std::uint32_t csn = NRF_SPIM_PIN_NOT_CONNECTED;
            nrf_spim_mode_t mode{};
            if (!pselFor(route, SerialSignal::sck, sck) ||
                !pselFor(route, SerialSignal::mosi, mosi) ||
                !pselFor(route, SerialSignal::miso, miso) ||
                !spiMode(context->configuration.mode, mode))
            {
                return SerialFabricResult::invalid_argument;
            }
            (void)pselFor(route, SerialSignal::csn, csn);
            nrfx_spim_config_t configuration = NRFX_SPIM_DEFAULT_CONFIG(sck, mosi, miso, csn);
            configuration.frequency = context->configuration.frequency;
            configuration.mode = mode;
            configuration.bit_order =
                context->configuration.bit_order == SpiFabricBitOrder::lsb_first
                    ? NRF_SPIM_BIT_ORDER_LSB_FIRST
                    : NRF_SPIM_BIT_ORDER_MSB_FIRST;
            configuration.orc = context->configuration.overrun_character;
#if NRF_SPIM_HAS_HW_CSN
            /**
             * @brief 하드웨어 CSN으로 nRF54L15 SPIS의 최소 1 us setup/hold를 보장합니다.
             *
             * NRFX의 software CSN 경로는 GPIO assert 직후 START를 요청하므로 두 번째 전송의
             * 첫 bit에서 SPIS over-read character가 노출될 수 있습니다. 각 SPIM core clock에서
             * 최대 출력 준비 시간에 여유를 둔 약 2 us 값으로 시작·종료·전송 사이의 CSN timing을
             * 고정합니다.
             */
            configuration.use_hw_ss = csn != NRF_SPIM_PIN_NOT_CONNECTED;
            configuration.ss_duration =
                instance == 0U ? spim00_csn_duration_cycles : serial_csn_duration_cycles;
#endif
            driver_error = nrfx_spim_init(&context->driver, &configuration, spimEvent, context);
            if (driver_error != 0)
            {
                return mapResult(driver_error);
            }
            context->route = route;
            context->event_head = 0U;
            context->event_tail = 0U;
            context->event_count = 0U;
            context->event_overflow = false;
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
            if (atomic_get(&context->transfer_active) != 0)
            {
                nrfx_spim_abort(&context->driver);
                for (auto &buffer : context->buffers)
                {
                    setBufferState(*context, buffer.address, DmaBufferState::cancelled);
                }
                atomic_clear(&context->transfer_active);
            }
            return SerialFabricResult::success;
        }

        bool stoppedAdapter(std::uint8_t instance) noexcept
        {
            const auto *const context = contextFor(instance);
            return context != nullptr && atomic_get(&context->transfer_active) == 0 &&
                   !context->driver.cb.transfer_in_progress;
        }

        SerialFabricResult deactivateAdapter(std::uint8_t instance, int &driver_error) noexcept
        {
            auto *const context = contextFor(instance);
            if (context == nullptr)
            {
                return SerialFabricResult::unsupported_instance;
            }
            irq_disable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
            nrfx_spim_uninit(&context->driver);
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
                nrfx_spim_irq_handler(&context->driver);
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
                if (internal::registerSerialFabricAdapter(SerialPersonality::spim, instance,
                                                          adapter) != SerialFabricResult::success)
                {
                    return -EIO;
                }
            }
            return 0;
        }

        SYS_INIT(registerAdapters, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace

    SerialFabricResult SpimHandle::configure(const SpiFabricConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const auto current = state();
        nrf_spim_mode_t ignored{};
        if (((current != SerialFabricState::inactive) && (current != SerialFabricState::staged)) ||
            (configuration.frequency == 0U) || !spiMode(configuration.mode, ignored))
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

    SerialFabricResult SpimHandle::transferAsync(const void *tx_buffer, std::size_t tx_size,
                                                 void *rx_buffer, std::size_t rx_size) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        auto *const context = contextFor(instance());
        if ((context == nullptr) ||
            !internal::isSerialFabricHandleActive(SerialPersonality::spim, instance()))
        {
            return SerialFabricResult::wrong_state;
        }
        if (((tx_buffer == nullptr) != (tx_size == 0U)) ||
            ((rx_buffer == nullptr) != (rx_size == 0U)) || ((tx_size == 0U) && (rx_size == 0U)) ||
            (tx_size > UINT16_MAX) || (rx_size > UINT16_MAX) ||
            !leasedBuffer(*context, tx_buffer, tx_size) ||
            !leasedBuffer(*context, rx_buffer, rx_size) ||
            atomic_get(&context->transfer_active) != 0)
        {
            return SerialFabricResult::invalid_argument;
        }
        {
            const k_spinlock_key_t key = k_spin_lock(&context->lock);
            context->buffers[0] = {tx_buffer, tx_size, DmaBufferState::dma_owned};
            context->buffers[1] = {rx_buffer, rx_size, DmaBufferState::dma_owned};
            k_spin_unlock(&context->lock, key);
        }
        nrfx_spim_xfer_desc_t transfer =
            NRFX_SPIM_XFER_TRX(static_cast<const std::uint8_t *>(tx_buffer), tx_size,
                               static_cast<std::uint8_t *>(rx_buffer), rx_size);
        atomic_set(&context->transfer_active, 1);
        const int result = nrfx_spim_xfer(&context->driver, &transfer, 0U);
        if (result != 0)
        {
            atomic_clear(&context->transfer_active);
            setBufferState(*context, tx_buffer, DmaBufferState::error);
            setBufferState(*context, rx_buffer, DmaBufferState::error);
            return mapResult(result);
        }
        return SerialFabricResult::success;
    }

    SerialFabricResult SpimHandle::transfer(const void *tx_buffer, std::size_t tx_size,
                                            void *rx_buffer, std::size_t rx_size,
                                            std::uint32_t timeout_us) noexcept
    {
        if ((timeout_us == 0U) || k_is_in_isr())
        {
            return SerialFabricResult::invalid_argument;
        }
        auto result = transferAsync(tx_buffer, tx_size, rx_buffer, rx_size);
        if (result != SerialFabricResult::success)
        {
            return result;
        }
        for (std::uint32_t elapsed = 0U; elapsed < timeout_us; elapsed += 10U)
        {
            SpiFabricEvent event{};
            if (takeEvent(event) && event.type == SpiFabricEventType::transfer_complete)
            {
                return SerialFabricResult::success;
            }
            k_busy_wait(10U);
        }
        (void)cancelTransfer();
        return SerialFabricResult::stop_timeout;
    }

    SerialFabricResult SpimHandle::cancelTransfer() noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        auto *const context = contextFor(instance());
        if ((context == nullptr) || atomic_get(&context->active) == 0 ||
            atomic_get(&context->transfer_active) == 0)
        {
            return SerialFabricResult::wrong_state;
        }
        nrfx_spim_abort(&context->driver);
        for (auto &buffer : context->buffers)
        {
            setBufferState(*context, buffer.address, DmaBufferState::cancelled);
        }
        atomic_clear(&context->transfer_active);
        pushEvent(*context, {SpiFabricEventType::transfer_cancelled, context->buffers[0].address,
                             const_cast<void *>(context->buffers[1].address), 0U, 0U, 0U});
        return SerialFabricResult::success;
    }

    bool SpimHandle::takeEvent(SpiFabricEvent &event) noexcept
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
            event = {SpiFabricEventType::error, nullptr, nullptr, 0U, 0U, event_queue_overflow};
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

    DmaBufferState SpimHandle::bufferState(const void *buffer) const noexcept
    {
        auto *const context = contextFor(instance());
        if (context == nullptr)
        {
            return DmaBufferState::error;
        }
        const k_spinlock_key_t key = k_spin_lock(&context->lock);
        DmaBufferState state = DmaBufferState::application_owned;
        for (const auto &record : context->buffers)
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
