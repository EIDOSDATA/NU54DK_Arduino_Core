/**
 * @file main.cpp
 * @brief DAP VCOM으로 UARTE20/21/22/30의 32-byte EasyDMA 왕복을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include <variant.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>

namespace
{
    using namespace nucode::arduino;

    inline constexpr std::uint8_t instance = CONFIG_NUCODE_M24_UARTE_HIL_INSTANCE;
    inline constexpr std::size_t packet_size = 32U;

    alignas(4) std::uint8_t workspace[packet_size * 2U]{};
    std::uint8_t *const receive_buffer = &workspace[0];
    std::uint8_t *const transmit_buffer = &workspace[packet_size];

    const SerialSignalPin p1_pins[] = {{SerialSignal::txd, PIN_P1_04},
                                       {SerialSignal::rxd, PIN_P1_05}};
    const SerialSignalPin p0_pins[] = {{SerialSignal::txd, PIN_P0_00},
                                       {SerialSignal::rxd, PIN_P0_01}};

    [[noreturn]] void halt()
    {
        while (true)
        {
            k_sleep(K_FOREVER);
        }
    }

    bool startReceive(UarteHandle &handle)
    {
        const auto result = handle.receiveAsync(receive_buffer, packet_size);
        return result == SerialFabricResult::success;
    }

    void sendReady(UarteHandle &handle)
    {
        for (std::size_t index = 0U; index < packet_size; ++index)
        {
            transmit_buffer[index] = static_cast<std::uint8_t>(0xA0U ^ instance ^ index);
        }
        if (handle.transmitAsync(transmit_buffer, packet_size) != SerialFabricResult::success)
        {
            halt();
        }
        while (true)
        {
            UarteEvent event{};
            if (!handle.takeEvent(event))
            {
                k_sleep(K_MSEC(1));
                continue;
            }
            if (event.type == UarteEventType::tx_complete && event.buffer == transmit_buffer &&
                event.transferred == packet_size)
            {
                return;
            }
            if (event.type == UarteEventType::error || event.type == UarteEventType::tx_cancelled)
            {
                halt();
            }
        }
    }
} // namespace

int main()
{
    if ((instance != 20U) && (instance != 21U) && (instance != 22U) && (instance != 30U))
    {
        halt();
    }
    auto *const handle = serialFabric().uarte(instance);
    if (handle == nullptr ||
        handle->configure({115200U, UarteParity::none, false}) != SerialFabricResult::success)
    {
        halt();
    }
    const bool p0 = instance == 30U;
    const SerialDmaWorkspace dma{workspace, sizeof(workspace)};
    const SerialFabricConfiguration configuration{
        p0 ? SerialRouteClass::p0_flexible : SerialRouteClass::p1_flexible,
        SerialElectricalProfile::dap_uart_bridge,
        p0 ? p0_pins : p1_pins,
        2U,
        &dma,
        1U,
    };
    if (handle->stage(configuration) != SerialFabricResult::success ||
        handle->activate() != SerialFabricResult::success)
    {
        halt();
    }
    sendReady(*handle);
    if (!startReceive(*handle))
    {
        halt();
    }

    while (true)
    {
        UarteEvent event{};
        if (!handle->takeEvent(event))
        {
            k_sleep(K_MSEC(1));
            continue;
        }
        if (event.type == UarteEventType::rx_complete && event.buffer == receive_buffer &&
            event.transferred == packet_size)
        {
            for (std::size_t index = 0U; index < packet_size; ++index)
            {
                transmit_buffer[index] = receive_buffer[packet_size - index - 1U];
            }
            while (handle->transmitAsync(transmit_buffer, packet_size) !=
                   SerialFabricResult::success)
            {
                k_sleep(K_MSEC(1));
            }
        }
        else if (event.type == UarteEventType::tx_complete)
        {
            while (!startReceive(*handle))
            {
                k_sleep(K_MSEC(1));
            }
        }
        else if (event.type == UarteEventType::error)
        {
            halt();
        }
    }
}
