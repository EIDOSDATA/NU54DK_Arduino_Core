/**
 * @file main.cpp
 * @brief 배선 없이 내부 TEMP와 WDT30 만료 reset을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>
#include <nucode/SystemFabric.h>

#include <variant.h>

#include <zephyr/drivers/hwinfo.h>
#include <zephyr/kernel.h>
#include <zephyr/linker/section_tags.h>

#include <cstddef>
#include <cstdint>

namespace
{
    using namespace nucode::arduino;

    inline constexpr std::size_t packet_size = 32U;
    inline constexpr std::uint32_t retained_magic = 0x4D323657UL;
    inline constexpr std::uint32_t retained_salt = 0xA55A26C3UL;
    inline constexpr std::uint32_t watchdog_timeout_ms = 1500U;

    struct RetainedState
    {
        std::uint32_t magic;
        std::int32_t temperature;
        std::uint32_t guard;
    };

    RetainedState __noinit retained_state;
    alignas(4) std::uint8_t serial_workspace[packet_size * 2U]{};
    std::uint8_t *const command_buffer = &serial_workspace[0];
    std::uint8_t *const response_buffer = &serial_workspace[packet_size];

    const SerialSignalPin result_pins[] = {
        {SerialSignal::txd, PIN_P0_00},
        {SerialSignal::rxd, PIN_P0_01},
    };

    [[nodiscard]] std::uint32_t guardFor(const RetainedState &state) noexcept
    {
        return state.magic ^ static_cast<std::uint32_t>(state.temperature) ^
               retained_salt;
    }

    [[nodiscard]] bool validRetainedState() noexcept
    {
        return retained_state.magic == retained_magic &&
               retained_state.guard == guardFor(retained_state);
    }

    void clearRetainedState() noexcept
    {
        retained_state.magic = 0U;
        retained_state.temperature = 0;
        retained_state.guard = 0U;
    }

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

    void clearResponse() noexcept
    {
        for (std::size_t index = 0U; index < packet_size; ++index)
            response_buffer[index] = 0U;
    }

    void finishChecksum() noexcept
    {
        std::uint8_t checksum = 0U;
        for (std::size_t index = 0U; index < packet_size - 1U; ++index)
            checksum ^= response_buffer[index];
        response_buffer[packet_size - 1U] = checksum;
    }

    void writeU32(std::size_t offset, std::uint32_t value) noexcept
    {
        for (std::size_t byte = 0U; byte < sizeof(value); ++byte)
            response_buffer[offset + byte] =
                static_cast<std::uint8_t>(value >> (byte * 8U));
    }

    void fillReady() noexcept
    {
        for (std::size_t index = 0U; index < packet_size; ++index)
            response_buffer[index] = static_cast<std::uint8_t>(0xE6U ^ index);
    }

    [[nodiscard]] bool validCommand() noexcept
    {
        for (std::size_t index = 0U; index < packet_size; ++index)
        {
            if (command_buffer[index] != static_cast<std::uint8_t>(0x26U ^ index))
                return false;
        }
        return true;
    }

    void fillArmed(bool temperature_pass, bool configured, bool started,
                   bool fed, std::int32_t temperature, int driver_error) noexcept
    {
        clearResponse();
        response_buffer[0] = 'A';
        response_buffer[1] = 'R';
        response_buffer[2] = '2';
        response_buffer[3] = '6';
        response_buffer[4] = 1U;
        response_buffer[5] = temperature_pass ? 1U : 0U;
        response_buffer[6] = configured ? 1U : 0U;
        response_buffer[7] = started ? 1U : 0U;
        response_buffer[8] = fed ? 1U : 0U;
        writeU32(9U, static_cast<std::uint32_t>(temperature));
        writeU32(13U, static_cast<std::uint32_t>(driver_error));
        response_buffer[17] = 30U;
        finishChecksum();
    }

    void fillResult(bool temperature_pass, bool reset_pass,
                    std::int32_t temperature, std::uint32_t cause,
                    std::uint32_t supported) noexcept
    {
        clearResponse();
        response_buffer[0] = 'N';
        response_buffer[1] = 'U';
        response_buffer[2] = '2';
        response_buffer[3] = '6';
        response_buffer[4] = 1U;
        response_buffer[5] = temperature_pass ? 1U : 0U;
        response_buffer[6] = reset_pass ? 1U : 0U;
        response_buffer[7] = temperature_pass && reset_pass ? 1U : 0U;
        writeU32(8U, static_cast<std::uint32_t>(temperature));
        writeU32(12U, cause);
        writeU32(16U, supported);
        response_buffer[20] = 30U;
        response_buffer[21] = 1U;
        finishChecksum();
    }

    [[nodiscard]] UarteHandle &startSerial()
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
        return *serial;
    }

    [[nodiscard]] bool receiveCommand(UarteHandle &serial)
    {
        if (serial.receiveAsync(command_buffer, packet_size) !=
            SerialFabricResult::success)
            return false;
        while (true)
        {
            UarteEvent event{};
            if (!serial.takeEvent(event))
            {
                k_sleep(K_MSEC(1));
                continue;
            }
            if (event.type == UarteEventType::rx_complete &&
                event.buffer == command_buffer && event.transferred == packet_size)
                return validCommand();
            if (event.type == UarteEventType::error ||
                event.type == UarteEventType::rx_cancelled)
                return false;
        }
    }
} // namespace

int main()
{
    std::uint32_t reset_cause = 0U;
    std::uint32_t supported_cause = 0U;
    const bool reset_report_pass = hwinfo_get_reset_cause(&reset_cause) == 0 &&
                                   hwinfo_get_supported_reset_cause(&supported_cause) == 0;
    const bool watchdog_reset =
        reset_report_pass &&
        (reset_cause & static_cast<std::uint32_t>(RESET_WATCHDOG)) != 0U;
    const bool resumed = validRetainedState() && watchdog_reset;
    const std::int32_t retained_temperature = retained_state.temperature;
    clearRetainedState();
    (void)hwinfo_clear_reset_cause();

    UarteHandle &serial = startSerial();
    if (resumed)
    {
        const bool temperature_pass = retained_temperature >= -4000 &&
                                      retained_temperature <= 12500;
        fillResult(temperature_pass, true, retained_temperature, reset_cause,
                   supported_cause);
        send(serial);
        halt();
    }

    while (true)
    {
        fillReady();
        send(serial);
        if (!receiveCommand(serial))
            continue;

        std::int32_t temperature = 0;
        const bool temperature_pass =
            systemFabric().temperature().readCentiCelsius(temperature) ==
                SystemFabricResult::success &&
            temperature >= -4000 && temperature <= 12500;
        auto *const watchdog = systemFabric().watchdog(30U);
        bool configured = false;
        bool started = false;
        bool fed = false;
        int driver_error = -1;
        if (temperature_pass && watchdog != nullptr)
        {
            retained_state.magic = retained_magic;
            retained_state.temperature = temperature;
            retained_state.guard = guardFor(retained_state);
            configured = watchdog->configure(watchdog_timeout_ms) ==
                         SystemFabricResult::success;
            if (configured)
                started = watchdog->start() == SystemFabricResult::success;
            if (started)
                fed = watchdog->feed() == SystemFabricResult::success;
            driver_error = watchdog->lastDriverError();
        }
        if (!temperature_pass || !configured || !started || !fed)
            clearRetainedState();
        fillArmed(temperature_pass, configured, started, fed, temperature,
                  driver_error);
        send(serial);
        if (!temperature_pass || !configured || !started || !fed)
            halt();

        while (true)
            k_sleep(K_FOREVER);
    }
}
