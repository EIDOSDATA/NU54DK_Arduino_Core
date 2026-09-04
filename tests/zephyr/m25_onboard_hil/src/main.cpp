/**
 * @file main.cpp
 * @brief 배선 없이 EGU-DPPI-TIMER와 내부 VDD SAADC를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/AnalogFabric.h>
#include <nucode/EventFabric.h>
#include <nucode/SerialFabric.h>
#include <nucode/StreamFabric.h>

#include <variant.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>

namespace
{
    using namespace nucode::arduino;

    inline constexpr std::size_t packet_size = 32U;
    inline constexpr std::uint8_t dppi_channel = 0U;
    inline constexpr std::uint8_t egu_channel = 0U;
    alignas(4) std::uint8_t serial_workspace[packet_size * 2U]{};
    alignas(4) std::int16_t saadc_samples[1]{};
    std::uint8_t *const command_buffer = &serial_workspace[0];
    std::uint8_t *const response_buffer = &serial_workspace[packet_size];

    const SerialSignalPin result_pins[] = {
        {SerialSignal::txd, PIN_P0_00},
        {SerialSignal::rxd, PIN_P0_01},
    };
    const SaadcChannelConfiguration internal_vdd_channel[] = {
        {SaadcInput::vdd, SaadcInput::disabled},
    };

    [[noreturn]] void halt()
    {
        while (true)
            k_sleep(K_FOREVER);
    }

    void waitForTx(UarteHandle &serial)
    {
        while (true)
        {
            UarteEvent event{};
            if (!serial.takeEvent(event))
            {
                k_sleep(K_MSEC(1));
                continue;
            }
            if (event.type == UarteEventType::tx_complete &&
                event.buffer == response_buffer && event.transferred == packet_size)
                return;
            if (event.type == UarteEventType::error ||
                event.type == UarteEventType::tx_cancelled)
                halt();
        }
    }

    void send(UarteHandle &serial)
    {
        if (serial.transmitAsync(response_buffer, packet_size) !=
            SerialFabricResult::success)
            halt();
        waitForTx(serial);
    }

    void fillReady()
    {
        for (std::size_t index = 0U; index < packet_size; ++index)
            response_buffer[index] = static_cast<std::uint8_t>(0xE5U ^ index);
    }

    bool validCommand()
    {
        for (std::size_t index = 0U; index < packet_size; ++index)
        {
            if (command_buffer[index] != static_cast<std::uint8_t>(0x25U ^ index))
                return false;
        }
        return true;
    }

    bool exerciseEventFabric(std::uint32_t &ticks)
    {
        auto *const timer = eventFabric().timer(20U);
        auto *const egu = eventFabric().egu(20U);
        auto *const dppi = eventFabric().dppi(20U);
        if (timer == nullptr || egu == nullptr || dppi == nullptr)
            return false;
        if (timer->acquire(1000000U) != EventFabricResult::success)
            return false;
        if (egu->acquire(egu_channel) != EventFabricResult::success)
        {
            (void)timer->release();
            return false;
        }
        if (dppi->acquireChannel(dppi_channel) != EventFabricResult::success)
        {
            (void)egu->release(egu_channel);
            (void)timer->release();
            return false;
        }

        const EventEndpoint publisher = egu->event(egu_channel);
        const EventEndpoint subscriber = timer->task(TimerTask::start);
        bool connected = false;
        bool enabled = false;
        bool passed = timer->clear() == EventFabricResult::success;
        if (passed)
        {
            connected = dppi->connect(publisher, subscriber, dppi_channel) ==
                        EventFabricResult::success;
            passed = connected;
        }
        if (passed)
        {
            enabled = dppi->enable(dppi_channel) == EventFabricResult::success;
            passed = enabled;
        }
        if (passed)
            passed = egu->trigger(egu_channel) == EventFabricResult::success;
        if (passed)
        {
            k_busy_wait(2000U);
            ticks = timer->capture(1U);
            passed = ticks >= 1000U && ticks <= 100000U;
        }
        bool cleanup = true;
        if (enabled)
            cleanup &= dppi->disable(dppi_channel) == EventFabricResult::success;
        if (connected)
            cleanup &= dppi->disconnect(publisher, subscriber, dppi_channel) ==
                       EventFabricResult::success;
        cleanup &= dppi->releaseChannel(dppi_channel) == EventFabricResult::success;
        cleanup &= egu->release(egu_channel) == EventFabricResult::success;
        cleanup &= timer->release() == EventFabricResult::success;
        return passed && cleanup;
    }

    bool exerciseInternalSaadc(std::int16_t &sample)
    {
        auto &saadc = analogFabric().saadc();
        if (saadc.configure({internal_vdd_channel, 1U, 12U, 4U, 0U}) !=
                AnalogFabricResult::success ||
            saadc.start(saadc_samples, 1U, nullptr, 0U) !=
                AnalogFabricResult::success)
            return false;
        bool complete = false;
        bool failed = false;
        bool sampled = false;
        for (std::uint32_t waited = 0U; waited < 100000U && !complete && !failed;
             waited += 100U)
        {
            SaadcEvent event{};
            while (saadc.takeEvent(event))
            {
                if (event.type == SaadcEventType::ready && !sampled)
                {
                    sampled = saadc.sample() == AnalogFabricResult::success;
                    failed = !sampled;
                }
                if (event.type == SaadcEventType::buffer_complete &&
                    event.buffer == saadc_samples && event.samples == 1U)
                {
                    complete = true;
                    sample = saadc_samples[0];
                }
                if (event.type == SaadcEventType::error)
                {
                    failed = true;
                    break;
                }
            }
            if (!complete)
                k_busy_wait(100U);
        }
        const bool stopped = saadc.stop() == AnalogFabricResult::success;
        return sampled && !failed && complete && sample > 0 && stopped;
    }

    bool verifyStreamFabricIntegration()
    {
        auto *const pdm20 = streamFabric().pdm(20U);
        auto *const pdm21 = streamFabric().pdm(21U);
        auto *const i2s20 = streamFabric().i2s(20U);
        auto *const qdec20 = streamFabric().qdec(20U);
        auto *const qdec21 = streamFabric().qdec(21U);
        return pdm20 != nullptr && pdm21 != nullptr && i2s20 != nullptr &&
               qdec20 != nullptr && qdec21 != nullptr &&
               pdm20->state() == StreamFabricState::inactive &&
               pdm21->state() == StreamFabricState::inactive &&
               i2s20->state() == StreamFabricState::inactive &&
               qdec20->state() == StreamFabricState::inactive &&
               qdec21->state() == StreamFabricState::inactive;
    }

    void writeU32(std::size_t offset, std::uint32_t value)
    {
        for (std::size_t byte = 0U; byte < sizeof(value); ++byte)
            response_buffer[offset + byte] =
                static_cast<std::uint8_t>(value >> (byte * 8U));
    }

    void fillResult(bool event_pass, bool analog_pass, bool stream_linked,
                    std::uint32_t ticks, std::int16_t sample)
    {
        for (std::size_t index = 0U; index < packet_size; ++index)
            response_buffer[index] = 0U;
        response_buffer[0] = 'N';
        response_buffer[1] = 'U';
        response_buffer[2] = '2';
        response_buffer[3] = '5';
        response_buffer[4] = 1U;
        response_buffer[5] = event_pass ? 1U : 0U;
        response_buffer[6] = analog_pass ? 1U : 0U;
        response_buffer[7] = event_pass && analog_pass && stream_linked ? 1U : 0U;
        writeU32(8U, ticks);
        response_buffer[12] = static_cast<std::uint8_t>(sample);
        response_buffer[13] = static_cast<std::uint8_t>(sample >> 8U);
        response_buffer[14] = stream_linked ? 1U : 0U;
        std::uint8_t checksum = 0U;
        for (std::size_t index = 0U; index < packet_size - 1U; ++index)
            checksum ^= response_buffer[index];
        response_buffer[packet_size - 1U] = checksum;
    }
} // namespace

int main()
{
    auto *const serial = serialFabric().uarte(30U);
    if (serial == nullptr ||
        serial->configure({115200U, UarteParity::none, false}) !=
            SerialFabricResult::success)
        halt();
    const SerialDmaWorkspace serial_dma{serial_workspace,
                                        sizeof(serial_workspace)};
    const SerialFabricConfiguration serial_configuration{
        SerialRouteClass::p0_flexible,
        SerialElectricalProfile::dap_uart_bridge,
        result_pins,
        2U,
        &serial_dma,
        1U,
    };
    if (serial->stage(serial_configuration) != SerialFabricResult::success ||
        serial->activate() != SerialFabricResult::success)
        halt();

    while (true)
    {
        fillReady();
        send(*serial);
        if (serial->receiveAsync(command_buffer, packet_size) !=
            SerialFabricResult::success)
            halt();
        bool received = false;
        while (!received)
        {
            UarteEvent event{};
            if (!serial->takeEvent(event))
            {
                k_sleep(K_MSEC(1));
                continue;
            }
            if (event.type == UarteEventType::rx_complete &&
                event.buffer == command_buffer && event.transferred == packet_size)
                received = true;
            else if (event.type == UarteEventType::error)
                halt();
        }
        if (!validCommand())
            continue;

        std::uint32_t ticks = 0U;
        std::int16_t sample = 0;
        const bool event_pass = exerciseEventFabric(ticks);
        const bool analog_pass = exerciseInternalSaadc(sample);
        const bool stream_linked = verifyStreamFabricIntegration();
        fillResult(event_pass, analog_pass, stream_linked, ticks, sample);
        send(*serial);
        // One physical measurement per flash; no adjacent next-READY frame.
        halt();
    }
}
