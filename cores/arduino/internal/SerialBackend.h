/**
 * @file SerialBackend.h
 * @brief Zephyr Serial backend의 비공개 진단 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_SERIAL_BACKEND_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_SERIAL_BACKEND_H_

#include <cstdint>

namespace nucode::arduino::internal
{

    /** @brief 기본 Serial에서 마지막으로 관측한 상태입니다. */
    enum class SerialError : std::uint8_t
    {
        none = 0U,
        invalid_context,
        unsupported_config,
        device_not_ready,
        not_started,
        driver_error,
        rx_overflow,
        invalid_pin_route,
        route_busy,
        route_error,
    };

    /** @brief 마지막 Serial 상태를 반환합니다. */
    [[nodiscard]] SerialError lastSerialError() noexcept;

    /** @brief 마지막 Zephyr UART 오류 번호를 반환합니다. */
    [[nodiscard]] int lastSerialDriverError() noexcept;

    /** @brief RX queue가 가득 차서 버린 누적 byte 수를 반환합니다. */
    [[nodiscard]] std::uint32_t serialDroppedRxBytes() noexcept;

    /** @brief Serial 오류와 RX drop 누적값을 초기화합니다. */
    void clearSerialDiagnostics() noexcept;

#if !defined(__ZEPHYR__) || defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
    /** @brief Serial1에서 마지막으로 관측한 상태입니다. */
    [[nodiscard]] SerialError lastSerial1Error() noexcept;

    /** @brief Serial1의 마지막 Zephyr 또는 route 오류 번호입니다. */
    [[nodiscard]] int lastSerial1DriverError() noexcept;

    /** @brief Serial1 RX queue overflow 누적값을 반환합니다. */
    [[nodiscard]] std::uint32_t serial1DroppedRxBytes() noexcept;

    /** @brief Serial1 진단과 RX drop 누적값을 초기화합니다. */
    void clearSerial1Diagnostics() noexcept;
#endif

}

#endif
