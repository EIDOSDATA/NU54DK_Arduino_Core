/**
 * @file main.cpp
 * @brief M24 SPIM/SPIS 전 instance adapter와 DMA 경계를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include <variant.h>

#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>

namespace
{
    using namespace nucode::arduino;

    alignas(4) std::uint8_t workspaces[10][128]{};

    const SerialSignalPin controller_p2[] = {
        {SerialSignal::sck, PIN_P2_01},
        {SerialSignal::mosi, PIN_P2_02},
        {SerialSignal::miso, PIN_P2_04},
    };
    const SerialSignalPin peripheral_p2[] = {
        {SerialSignal::sck, PIN_P2_01},
        {SerialSignal::mosi, PIN_P2_04},
        {SerialSignal::miso, PIN_P2_02},
        {SerialSignal::csn, PIN_P2_05},
    };
    const SerialSignalPin controller_p1[] = {
        {SerialSignal::sck, PIN_P1_04},
        {SerialSignal::mosi, PIN_P1_05},
        {SerialSignal::miso, PIN_P1_06},
    };
    const SerialSignalPin peripheral_p1[] = {
        {SerialSignal::sck, PIN_P1_04},
        {SerialSignal::mosi, PIN_P1_05},
        {SerialSignal::miso, PIN_P1_06},
        {SerialSignal::csn, PIN_P1_07},
    };
    const SerialSignalPin controller_p0[] = {
        {SerialSignal::sck, PIN_P0_00},
        {SerialSignal::mosi, PIN_P0_01},
        {SerialSignal::miso, PIN_P0_02},
    };
    const SerialSignalPin peripheral_p0[] = {
        {SerialSignal::sck, PIN_P0_00},
        {SerialSignal::mosi, PIN_P0_01},
        {SerialSignal::miso, PIN_P0_02},
        {SerialSignal::csn, PIN_P0_03},
    };

    SerialFabricConfiguration configuration(SerialRouteClass route,
                                            SerialElectricalProfile electrical,
                                            const SerialSignalPin *pins, std::size_t pin_count,
                                            std::size_t workspace)
    {
        static SerialDmaWorkspace dma[10];
        dma[workspace] = {workspaces[workspace], sizeof(workspaces[workspace])};
        return {route, electrical, pins, pin_count, &dma[workspace], 1U};
    }
} // namespace

ZTEST(m24_spi_driver_contract, test_all_ten_adapters_stage_exact_routes)
{
    struct Case
    {
        std::uint8_t instance;
        SerialRouteClass route;
        SerialElectricalProfile electrical;
        const SerialSignalPin *controller;
        const SerialSignalPin *peripheral;
    };
    const Case cases[] = {
        {0U, SerialRouteClass::p2_dedicated20, SerialElectricalProfile::connector_fixture,
         controller_p2, peripheral_p2},
        {20U, SerialRouteClass::p2_dedicated20, SerialElectricalProfile::connector_fixture,
         controller_p2, peripheral_p2},
        {21U, SerialRouteClass::p1_flexible, SerialElectricalProfile::dap_uart_disabled,
         controller_p1, peripheral_p1},
        {22U, SerialRouteClass::p1_flexible, SerialElectricalProfile::dap_uart_disabled,
         controller_p1, peripheral_p1},
        {30U, SerialRouteClass::p0_flexible, SerialElectricalProfile::dap_uart_disabled,
         controller_p0, peripheral_p0},
    };
    for (std::size_t index = 0U; index < 5U; ++index)
    {
        auto *const controller = serialFabric().spim(cases[index].instance);
        auto *const peripheral = serialFabric().spis(cases[index].instance);
        zassert_not_null(controller, "SPIM handle 누락");
        zassert_not_null(peripheral, "SPIS handle 누락");
        zassert_equal(controller->configure(
                          {4000000U, SpiFabricMode::mode3, SpiFabricBitOrder::msb_first, 0xFFU}),
                      SerialFabricResult::success, "SPIM configure 실패");
        zassert_equal(
            peripheral->configure({0U, SpiFabricMode::mode3, SpiFabricBitOrder::msb_first, 0xFEU}),
            SerialFabricResult::success, "SPIS configure 실패");
        zassert_equal(controller->stage(configuration(cases[index].route, cases[index].electrical,
                                                      cases[index].controller, 3U, index)),
                      SerialFabricResult::success, "SPIM stage 실패");
        zassert_equal(peripheral->stage(configuration(cases[index].route, cases[index].electrical,
                                                      cases[index].peripheral, 4U, index + 5U)),
                      SerialFabricResult::success, "SPIS stage 실패");
    }
}

ZTEST(m24_spi_driver_contract, test_inactive_dma_operations_fail_closed)
{
    auto *const controller = serialFabric().spim(21U);
    auto *const peripheral = serialFabric().spis(21U);
    zassert_equal(controller->transferAsync(workspaces[0], 8U, workspaces[0], 8U),
                  SerialFabricResult::wrong_state, "inactive SPIM transfer를 허용했습니다.");
    zassert_equal(peripheral->queueBuffers(workspaces[1], 8U, workspaces[1], 8U),
                  SerialFabricResult::wrong_state, "inactive SPIS buffer를 허용했습니다.");
    SpiFabricEvent event{};
    zassert_false(controller->takeEvent(event), "가짜 SPIM event가 있습니다.");
    zassert_false(peripheral->takeEvent(event), "가짜 SPIS event가 있습니다.");
}

ZTEST_SUITE(m24_spi_driver_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
