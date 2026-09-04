/**
 * @file WireBackend.h
 * @brief Zephyr I2C 기반 Wire backend의 비공개 진단 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_WIRE_BACKEND_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_WIRE_BACKEND_H_

#include <cstdint>

namespace nucode::arduino::internal
{

    /** @brief Wire controller에서 마지막으로 관측한 상태입니다. */
    enum class WireError : std::uint8_t
    {
        none = 0U,
        invalid_context,
        device_not_ready,
        not_started,
        invalid_address,
        unsupported_clock,
        unsupported_peripheral_mode,
        transmission_not_active,
        transaction_owner_mismatch,
        tx_buffer_overflow,
        rx_buffer_overflow,
        pending_restart_conflict,
        pending_restart_address_mismatch,
        unsupported_no_stop_read,
        invalid_pin_route,
        route_busy,
        route_error,
        driver_error,
    };

    /** @brief 마지막 Wire 상태를 반환합니다. */
    [[nodiscard]] WireError lastWireError() noexcept;

    /** @brief 마지막 Zephyr I2C 오류 번호를 반환합니다. */
    [[nodiscard]] int lastWireDriverError() noexcept;

    /** @brief no-STOP write가 다음 repeated-start read를 기다리는지 반환합니다. */
    [[nodiscard]] bool wireHasPendingRestart() noexcept;

    /** @brief 현재 Wire controller SCL 설정을 Hz로 반환합니다. */
    [[nodiscard]] std::uint32_t wireClockFrequency() noexcept;

    /** @brief Wire 오류 상태를 초기화합니다. */
    void clearWireDiagnostics() noexcept;

} // namespace nucode::arduino::internal

#endif
