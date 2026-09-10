/**
 * @file NUCODE_Peripheral_Fabric.h
 * @brief 검증된 NU54DK 직접 Peripheral Fabric API의 Arduino 설치 진입점입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_PERIPHERAL_FABRIC_H_
#define NUCODE_PERIPHERAL_FABRIC_H_

#include <Arduino.h>
#include <nucode/AnalogFabric.h>
#include <nucode/EventFabric.h>
#include <nucode/PeripheralInventory.h>
#include <nucode/SerialFabric.h>
#include <nucode/StreamFabric.h>
#include <nucode/SystemFabric.h>

#include <cstdint>

namespace nucode::peripheral
{
    /** @brief 설치 profile이 선언하는 기능 지원 수준입니다. */
    enum class Support : std::uint8_t
    {
        unsupported = 0U,
        experimental,
        supported,
    };

    /** @brief `fabric` profile에서 선택 가능한 API family입니다. */
    struct Capabilities
    {
        Support serial;
        Support analog;
        Support event;
        Support pdm;
        Support i2s;
        Support qdec;
        Support system;
    };

    /** @brief 현재 설치 profile의 안정된 ID입니다. */
    inline constexpr char profile_id[] = "fabric";

    /**
     * @brief T15에서 확정한 지원 경계를 설치 profile capability로 제공합니다.
     *
     * QDEC는 알려진 manual read/clear 누산 제한 때문에 지원으로 승격하지 않습니다.
     */
    inline constexpr Capabilities capabilities{
        Support::supported, Support::supported,   Support::supported, Support::supported,
        Support::supported, Support::unsupported, Support::supported,
    };

    /** @brief capability가 일반 사용자 지원 범위인지 확인합니다. */
    [[nodiscard]] constexpr bool isSupported(Support support) noexcept
    {
        return support == Support::supported;
    }
} // namespace nucode::peripheral

#endif
