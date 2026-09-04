/**
 * @file SerialFabricBackend.h
 * @brief Serial Fabric 공통 상태기계와 personality adapter 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_SERIAL_FABRIC_BACKEND_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_SERIAL_FABRIC_BACKEND_H_

#include <nucode/SerialFabric.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
    inline constexpr std::size_t serial_fabric_pin_capacity = 5U;
    inline constexpr std::size_t serial_fabric_dma_workspace_capacity = 4U;

    /** @brief board validator가 canonical pin/resource를 보존한 route입니다. */
    struct ValidatedSerialRoute
    {
        SerialSignalPin pins[serial_fabric_pin_capacity]{};
        std::size_t pin_count{0U};
        SerialDmaWorkspace dma_workspaces[serial_fabric_dma_workspace_capacity]{};
        std::size_t dma_workspace_count{0U};
        SerialRouteClass route{SerialRouteClass::p1_flexible};
        SerialElectricalProfile electrical_profile{
            SerialElectricalProfile::connector_fixture};
    };

    /** @brief hardware adapter가 구현할 bounded handover 수명주기입니다. */
    struct SerialFabricDriverAdapter
    {
        SerialFabricResult (*validate)(std::uint8_t instance,
                                       const ValidatedSerialRoute &route,
                                       int &driver_error) noexcept;
        SerialFabricResult (*activate)(std::uint8_t instance,
                                       const ValidatedSerialRoute &route,
                                       int &driver_error) noexcept;
        SerialFabricResult (*request_stop)(std::uint8_t instance,
                                           int &driver_error) noexcept;
        bool (*stopped)(std::uint8_t instance) noexcept;
        SerialFabricResult (*deactivate)(std::uint8_t instance,
                                         int &driver_error) noexcept;
        void (*handle_irq)(std::uint8_t instance) noexcept;
    };

    /** @brief 한 personality adapter를 등록합니다. 재등록은 거부합니다. */
    [[nodiscard]] SerialFabricResult
    registerSerialFabricAdapter(SerialPersonality personality,
                                std::uint8_t instance,
                                const SerialFabricDriverAdapter &adapter) noexcept;

    /** @brief 현재 handle이 active인지 driver operation 전에 확인합니다. */
    [[nodiscard]] bool isSerialFabricHandleActive(SerialPersonality personality,
                                                  std::uint8_t instance) noexcept;

    /** @brief block IRQ trampoline에서 현재 active personality로 전달합니다. */
    void dispatchSerialFabricIrq(std::uint8_t instance) noexcept;

#if defined(CONFIG_ZTEST)
    /** @brief ztest 격리를 위해 fabric 상태와 adapter table을 초기화합니다. */
    void resetSerialFabricForTest() noexcept;
#endif
} // namespace nucode::arduino::internal

#endif
