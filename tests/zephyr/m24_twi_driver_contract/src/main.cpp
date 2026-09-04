/**
 * @file main.cpp
 * @brief M24 TWIM/TWIS 전 instance adapter와 DMA 경계를 검증합니다.
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

    alignas(4) std::uint8_t workspaces[8][128]{};

    const SerialSignalPin p1_pins[] = {
        {SerialSignal::sda, PIN_P1_10},
        {SerialSignal::scl, PIN_P1_14},
    };
    const SerialSignalPin p0_pins[] = {
        {SerialSignal::sda, PIN_P0_00},
        {SerialSignal::scl, PIN_P0_01},
    };
    const SerialSignalPin pmic_pins[] = {
        {SerialSignal::sda, PIN_P1_02},
        {SerialSignal::scl, PIN_P1_03},
    };

    SerialFabricConfiguration configuration(std::uint8_t instance, std::size_t workspace)
    {
        static SerialDmaWorkspace dma[8];
        dma[workspace] = {workspaces[workspace], sizeof(workspaces[workspace])};
        if (instance == 30U)
        {
            return {SerialRouteClass::p0_flexible,
                    SerialElectricalProfile::dap_uart_disabled,
                    p0_pins,
                    2U,
                    &dma[workspace],
                    1U};
        }
        return {SerialRouteClass::p1_flexible,
                SerialElectricalProfile::connector_fixture,
                p1_pins,
                2U,
                &dma[workspace],
                1U};
    }
} // namespace

ZTEST(m24_twi_driver_contract, test_all_eight_adapters_stage_exact_routes)
{
    const std::uint8_t instances[] = {20U, 21U, 22U, 30U};
    for (std::size_t index = 0U; index < 4U; ++index)
    {
        auto *const controller = serialFabric().twim(instances[index]);
        auto *const target = serialFabric().twis(instances[index]);
        zassert_not_null(controller, "TWIM handle 누락");
        zassert_not_null(target, "TWIS handle 누락");
        zassert_equal(controller->configure({TwiFabricFrequency::fast}),
                      SerialFabricResult::success, "TWIM configure 실패");
        zassert_equal(target->configure({0x42U, 0x43U, false}), SerialFabricResult::success,
                      "TWIS configure 실패");
        zassert_equal(controller->stage(configuration(instances[index], index)),
                      SerialFabricResult::success, "TWIM stage 실패");
        zassert_equal(target->stage(configuration(instances[index], index + 4U)),
                      SerialFabricResult::success, "TWIS stage 실패");
    }
}

ZTEST(m24_twi_driver_contract, test_pmic_profile_is_controller_read_only)
{
    SerialDmaWorkspace dma{workspaces[0], sizeof(workspaces[0])};
    const SerialFabricConfiguration config{SerialRouteClass::p1_flexible,
                                           SerialElectricalProfile::pmic_read_only,
                                           pmic_pins,
                                           2U,
                                           &dma,
                                           1U};
    auto *const target = serialFabric().twis(20U);
    zassert_equal(target->stage(config), SerialFabricResult::unsafe_electrical_profile,
                  "TWIS가 온보드 PMIC net 구동을 허용했습니다.");
}

ZTEST(m24_twi_driver_contract, test_inactive_dma_operations_fail_closed)
{
    auto *const controller = serialFabric().twim(21U);
    auto *const target = serialFabric().twis(21U);
    zassert_equal(controller->transferAsync(0x42U, workspaces[0], 1U, workspaces[0] + 4U, 4U),
                  SerialFabricResult::wrong_state, "inactive TWIM transfer를 허용했습니다.");
    zassert_equal(target->queueBuffers(workspaces[1], 8U, workspaces[1] + 16U, 8U),
                  SerialFabricResult::wrong_state, "inactive TWIS buffer를 허용했습니다.");
    TwiFabricEvent event{};
    zassert_false(controller->takeEvent(event), "가짜 TWIM event가 있습니다.");
    zassert_false(target->takeEvent(event), "가짜 TWIS event가 있습니다.");
}

ZTEST_SUITE(m24_twi_driver_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
