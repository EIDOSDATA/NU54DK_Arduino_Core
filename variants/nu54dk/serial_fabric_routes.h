/**
 * @file serial_fabric_routes.h
 * @brief NU54DK Serial Fabric route를 회로 정책에 맞게 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_VARIANTS_NU54DK_SERIAL_FABRIC_ROUTES_H_
#define NUCODE_ARDUINO_VARIANTS_NU54DK_SERIAL_FABRIC_ROUTES_H_

#include "internal/IoResourceManager.h"
#include "internal/SerialFabricBackend.h"

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
    /** @brief 설정을 검증하고 canonical route와 lease 자원을 만듭니다. */
    [[nodiscard]] SerialFabricResult validateNu54dkSerialFabricRoute(
        SerialPersonality personality, std::uint8_t instance,
        const SerialFabricConfiguration &configuration, ValidatedSerialRoute &route,
        IoResourceId *resources, std::size_t resource_capacity,
        std::size_t &resource_count) noexcept;

    /** @brief canonical Arduino pin을 nrfx PSEL pin number로 변환합니다. */
    [[nodiscard]] SerialFabricResult
    nu54dkSerialFabricPsel(pin_size_t pin, std::uint32_t &psel) noexcept;
} // namespace nucode::arduino::internal

#endif
