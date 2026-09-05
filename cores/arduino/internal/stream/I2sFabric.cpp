/** @file @brief I2s의 private context·driver·IRQ와 lifecycle을 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#include "StreamFabricInternal.h"
#include <hal/nrf_i2s.h>
#include <nrfx_i2s.h>
namespace nucode::arduino
{
    using namespace internal::stream;
    namespace
    {
        inline constexpr std::size_t i2s_dma_capacity = 8U;
        struct I2sContext
        {
            I2sConfiguration configuration{};
            IoResourceLease base_lease{};
            DmaLeaseSlot dma_leases[i2s_dma_capacity]{};
            EventQueue<I2sEvent> events{};
            StreamFabricState state{StreamFabricState::inactive};
            internal::FabricDiagnostic<StreamFabricResult> diagnostics{};
            internal::FabricStopSignal stop_signal{};
            bool stop_waiting{false};
            bool first_callback{true};
        };

        I2sContext i2s_context{};
        nrfx_i2s_t i2s_driver = NRFX_I2S_INSTANCE(NRF_I2S20);
        bool exchangeFirstCallback(bool first) noexcept
        {
            const auto key = k_spin_lock(&dmaMetadataLock());
            const bool previous = i2s_context.first_callback;
            i2s_context.first_callback = first;
            k_spin_unlock(&dmaMetadataLock(), key);
            return previous;
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

        void i2sEventHandler(const nrfx_i2s_buffers_t *released, std::uint32_t status)
        {
            const bool first_callback = exchangeFirstCallback(false);
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
                    record(i2s_context, StreamFabricResult::resource_exhausted, -ENOBUFS);
                }
            }
            if ((status & NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED) != 0U)
            {
                const auto type = empty_release && !first_callback ? I2sEventType::underrun
                                                                   : I2sEventType::buffers_needed;
                if (!pushEvent(i2s_context.events, {type, {}, 0}))
                {
                    record(i2s_context, StreamFabricResult::resource_exhausted, -ENOBUFS);
                }
            }
            if ((status & NRFX_I2S_STATUS_TRANSFER_STOPPED) != 0U)
            {
                i2s_context.stop_signal.notifyStopped();
                if (!pushEvent(i2s_context.events, {I2sEventType::stopped, {}, 0}))
                {
                    record(i2s_context, StreamFabricResult::resource_exhausted, -ENOBUFS);
                }
            }
        }
    } // namespace
    std::uint8_t I2sFabric::instance() const noexcept
    {
        return 20U;
    }

    StreamFabricState I2sFabric::state() const noexcept
    {
        lockStream();
        const auto value = i2s_context.state;
        unlockStream();
        return value;
    }

    StreamFabricResult I2sFabric::lastResult() const noexcept
    {
        lockStream();
        const auto value = i2s_context.diagnostics.snapshot().result;
        unlockStream();
        return value;
    }

    int I2sFabric::lastDriverError() const noexcept
    {
        lockStream();
        const int value = i2s_context.diagnostics.snapshot().driver_error;
        unlockStream();
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

        lockStream();
        if (i2s_context.state == StreamFabricState::active ||
            i2s_context.state == StreamFabricState::stopping ||
            i2s_context.state == StreamFabricState::faulted)
        {
            record(i2s_context, i2s_context.state == StreamFabricState::faulted
                                    ? StreamFabricResult::faulted
                                    : StreamFabricResult::wrong_state);
            const auto result = i2s_context.diagnostics.snapshot().result;
            unlockStream();
            return result;
        }
        i2s_context.configuration = configuration;
        i2s_context.state = StreamFabricState::configured;
        clearEvents(i2s_context.events);
        record(i2s_context, StreamFabricResult::success);
        unlockStream();
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

        lockStream();
        if (i2s_context.state != StreamFabricState::configured)
        {
            record(i2s_context, StreamFabricResult::wrong_state);
            unlockStream();
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
            unlockStream();
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
            unlockStream();
            return result;
        }

        i2s_context.stop_signal.beginRun();
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
        (void)exchangeFirstCallback(true);
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
            unlockStream();
            return StreamFabricResult::driver_error;
        }
        const auto base_commit = internal::commitIoResources(i2s_context.base_lease);
        const auto rx_commit = rx_slot != nullptr ? commitDma(*rx_slot) : IoResourceResult::success;
        const auto tx_commit = tx_slot != nullptr ? commitDma(*tx_slot) : IoResourceResult::success;
        if (base_commit != IoResourceResult::success || rx_commit != IoResourceResult::success ||
            tx_commit != IoResourceResult::success)
        {
            i2s_context.state = StreamFabricState::stopping;
            (void)i2s_context.stop_signal.arm();
            nrfx_i2s_stop(&i2s_driver);
            record(i2s_context, StreamFabricResult::release_failed);
            unlockStream();
            return StreamFabricResult::release_failed;
        }
        i2s_context.state = StreamFabricState::active;
        record(i2s_context, StreamFabricResult::success);
        unlockStream();
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
        lockStream();
        if (i2s_context.state != StreamFabricState::active)
        {
            record(i2s_context, StreamFabricResult::wrong_state);
            unlockStream();
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
            unlockStream();
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
            unlockStream();
            return StreamFabricResult::driver_error;
        }
        const auto rx_commit = rx_slot != nullptr ? commitDma(*rx_slot) : IoResourceResult::success;
        const auto tx_commit = tx_slot != nullptr ? commitDma(*tx_slot) : IoResourceResult::success;
        if (rx_commit != IoResourceResult::success || tx_commit != IoResourceResult::success)
        {
            i2s_context.state = StreamFabricState::stopping;
            (void)i2s_context.stop_signal.arm();
            nrfx_i2s_stop(&i2s_driver);
            record(i2s_context, StreamFabricResult::release_failed);
            unlockStream();
            return StreamFabricResult::release_failed;
        }
        record(i2s_context, StreamFabricResult::success);
        unlockStream();
        return StreamFabricResult::success;
    }

    StreamFabricResult I2sFabric::stop(std::uint32_t timeout_us) noexcept
    {
        if (k_is_in_isr())
        {
            return StreamFabricResult::invalid_context;
        }
        lockStream();
        auto &context = i2s_context;
        if ((context.state != StreamFabricState::active &&
             context.state != StreamFabricState::stopping) ||
            context.stop_waiting)
        {
            record(context, StreamFabricResult::wrong_state);
            unlockStream();
            return StreamFabricResult::wrong_state;
        }
        const bool first_request = context.state == StreamFabricState::active;
        context.state = StreamFabricState::stopping;
        context.stop_waiting = true;
        const auto generation = context.stop_signal.arm();
        unlockStream();
        if (first_request)
        {
            nrfx_i2s_stop(&i2s_driver);
        }
        const bool stopped = internal::waitFabricStop(
            [&]
            {
                return context.stop_signal.completed(generation);
            },
            timeout_us);
        lockStream();
        context.stop_waiting = false;
        if (!stopped)
        {
            /** @brief timeout 뒤 늦은 STOP callback을 같은 실행에 보존하고 명시적 재시도를 허용합니다. */
            record(context, StreamFabricResult::stop_timeout, -ETIMEDOUT);
            unlockStream();
            return StreamFabricResult::stop_timeout;
        }
        nrfx_i2s_uninit(&i2s_driver);
        const auto dma_release = releaseAllDma(context.dma_leases);
        const auto base_release = context.base_lease.phase == internal::IoLeasePhase::reserved
                                      ? internal::rollbackIoResources(context.base_lease)
                                      : internal::releaseIoResources(context.base_lease);
        if (base_release == IoResourceResult::success)
        {
            context.base_lease = {};
        }
        const auto result =
            dma_release == IoResourceResult::success && base_release == IoResourceResult::success
                ? StreamFabricResult::success
                : StreamFabricResult::release_failed;
        context.state = result == StreamFabricResult::success ? StreamFabricState::configured
                                                              : StreamFabricState::faulted;
        record(context, result);
        unlockStream();
        return result;
    }

    bool I2sFabric::takeEvent(I2sEvent &event) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        lockStream();
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
        unlockStream();
        return available;
    }

} // namespace nucode::arduino
namespace nucode::arduino::internal::stream
{
    void i2s20Irq(const void *)
    {
        nrfx_i2s_irq_handler(&i2s_driver);
    }
} // namespace nucode::arduino::internal::stream
