/**
 * @file main.cpp
 * @brief M24 다섯 UARTE adapter의 등록·설정·DMA 경계를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>
#include "internal/IoResourceManager.h"

#include <variant.h>

#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>

namespace
{
    using namespace nucode::arduino;

    alignas(4) std::uint8_t workspaces[5][128]{};

    const SerialSignalPin pins00[] = {{SerialSignal::txd, PIN_P2_02},
                                      {SerialSignal::rxd, PIN_P2_00}};
    const SerialSignalPin pins20[] = {{SerialSignal::txd, PIN_P2_02},
                                      {SerialSignal::rxd, PIN_P2_00}};
    const SerialSignalPin pins21[] = {{SerialSignal::txd, PIN_P1_10},
                                      {SerialSignal::rxd, PIN_P1_14}};
    const SerialSignalPin pins22[] = {{SerialSignal::txd, PIN_P1_10},
                                      {SerialSignal::rxd, PIN_P1_14}};
    const SerialSignalPin pins30[] = {{SerialSignal::txd, PIN_P0_00},
                                      {SerialSignal::rxd, PIN_P0_01}};

    SerialFabricConfiguration configuration(SerialRouteClass route,
                                            SerialElectricalProfile electrical,
                                            const SerialSignalPin *pins, std::size_t pin_count,
                                            std::size_t workspace)
    {
        static SerialDmaWorkspace dma[5];
        dma[workspace] = {workspaces[workspace], sizeof(workspaces[workspace])};
        return {route, electrical, pins, pin_count, &dma[workspace], 1U};
    }
} // namespace

ZTEST(m24_uarte_driver_contract, test_all_five_adapters_stage_exact_routes)
{
    auto &fabric = serialFabric();
    struct Case
    {
        std::uint8_t instance;
        SerialRouteClass route;
        SerialElectricalProfile electrical;
        const SerialSignalPin *pins;
        std::size_t pin_count;
    };
    const Case cases[] = {
        {0U, SerialRouteClass::p2_dedicated20, SerialElectricalProfile::connector_fixture, pins00,
         2U},
        {20U, SerialRouteClass::p2_dedicated20, SerialElectricalProfile::connector_fixture, pins20,
         2U},
        {21U, SerialRouteClass::p1_flexible, SerialElectricalProfile::connector_fixture, pins21,
         2U},
        {22U, SerialRouteClass::p1_flexible, SerialElectricalProfile::connector_fixture, pins22,
         2U},
        {30U, SerialRouteClass::p0_flexible, SerialElectricalProfile::dap_uart_bridge, pins30, 2U},
    };
    for (std::size_t index = 0U; index < 5U; ++index)
    {
        auto *const handle = fabric.uarte(cases[index].instance);
        zassert_not_null(handle, "UARTE handle이 없습니다.");
        zassert_equal(handle->configure({115200U, UarteParity::none, false}),
                      SerialFabricResult::success, "UARTE configure 실패");
        zassert_equal(
            handle->stage(configuration(cases[index].route, cases[index].electrical,
                                        cases[index].pins, cases[index].pin_count, index)),
            SerialFabricResult::success, "UARTE stage 실패");
    }
}

ZTEST(m24_uarte_driver_contract, test_inactive_transfer_and_invalid_baud_fail_closed)
{
    auto *const handle = serialFabric().uarte(21U);
    zassert_equal(handle->configure({12345U, UarteParity::none, false}),
                  SerialFabricResult::invalid_argument, "지원하지 않는 baud를 허용했습니다.");
    zassert_equal(handle->transmitAsync(workspaces[2], 8U), SerialFabricResult::wrong_state,
                  "inactive UARTE TX를 허용했습니다.");
    zassert_equal(handle->receiveAsync(workspaces[2], 8U), SerialFabricResult::wrong_state,
                  "inactive UARTE RX를 허용했습니다.");
    UarteEvent event{};
    zassert_false(handle->takeEvent(event), "가짜 완료 event가 생성됐습니다.");
}

ZTEST(m24_uarte_driver_contract, test_disabled_console_releases_p1_dap_route)
{
    using namespace nucode::arduino::internal;
    IoResourceSnapshot snapshot{};
    zassert_equal(
        ioResourceSnapshot(peripheralIoResource(IoResourceKind::serial_block, 20U), snapshot),
        IoResourceResult::success);
    zassert_equal(snapshot.state, IoResourceState::free,
                  "disabled uart20 still owns serial20 at boot");
    const SerialSignalPin dap[] = {{SerialSignal::txd, PIN_P1_04}, {SerialSignal::rxd, PIN_P1_05}};
    const std::uint8_t instances[] = {20U, 21U, 22U};
    for (const std::uint8_t instance : instances)
    {
        auto *const handle = serialFabric().uarte(instance);
        zassert_equal(
            handle->stage(configuration(SerialRouteClass::p1_flexible,
                                        SerialElectricalProfile::dap_uart_bridge, dap, 2U, 1U)),
            SerialFabricResult::success, "released P1 DAP UARTE route rejected");
        zassert_equal(
            handle->stage(configuration(SerialRouteClass::p1_flexible,
                                        SerialElectricalProfile::connector_fixture, dap, 2U, 1U)),
            SerialFabricResult::unsafe_electrical_profile,
            "DAP pins must not become arbitrary connector outputs");
    }
}

ZTEST_SUITE(m24_uarte_driver_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
