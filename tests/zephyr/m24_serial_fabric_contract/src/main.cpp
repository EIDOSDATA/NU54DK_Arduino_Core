/**
 * @file main.cpp
 * @brief M24 공통 Serial Fabric의 selector, route와 handover 의미를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include "internal/IoResourceManager.h"
#include "internal/SerialFabricBackend.h"

#include <variant.h>

#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;

    struct FakeDriverState
    {
        bool active{false};
        bool stop_complete{true};
        bool fail_activate{false};
        std::uint32_t activation_count{0U};
        std::uint32_t deactivation_count{0U};
    };

    FakeDriverState fake[31]{};
    alignas(4) std::uint8_t dma_a[64]{};
    alignas(4) std::uint8_t dma_b[64]{};

    SerialFabricResult fakeValidate(std::uint8_t, const ValidatedSerialRoute &route,
                                    int &driver_error) noexcept
    {
        driver_error = 0;
        return route.pin_count > 0U ? SerialFabricResult::success
                                    : SerialFabricResult::invalid_argument;
    }

    SerialFabricResult fakeActivate(std::uint8_t instance, const ValidatedSerialRoute &,
                                    int &driver_error) noexcept
    {
        if (fake[instance].fail_activate)
        {
            driver_error = -5;
            return SerialFabricResult::driver_error;
        }
        fake[instance].active = true;
        ++fake[instance].activation_count;
        driver_error = 0;
        return SerialFabricResult::success;
    }

    SerialFabricResult fakeRequestStop(std::uint8_t, int &driver_error) noexcept
    {
        driver_error = 0;
        return SerialFabricResult::success;
    }

    bool fakeStopped(std::uint8_t instance) noexcept
    {
        return fake[instance].stop_complete;
    }

    SerialFabricResult fakeDeactivate(std::uint8_t instance, int &driver_error) noexcept
    {
        fake[instance].active = false;
        ++fake[instance].deactivation_count;
        driver_error = 0;
        return SerialFabricResult::success;
    }

    void fakeHandleIrq(std::uint8_t) noexcept
    {
    }

    const SerialFabricDriverAdapter fake_adapter{fakeValidate, fakeActivate,   fakeRequestStop,
                                                 fakeStopped,  fakeDeactivate, fakeHandleIrq};

    const SerialSignalPin uarte00_pins[] = {
        {SerialSignal::txd, PIN_P2_02},
        {SerialSignal::rxd, PIN_P2_00},
    };
    const SerialSignalPin spim00_pins[] = {
        {SerialSignal::sck, PIN_P2_01},
        {SerialSignal::mosi, PIN_P2_02},
        {SerialSignal::miso, PIN_P2_04},
    };
    const SerialSignalPin uarte21_pins[] = {
        {SerialSignal::txd, PIN_P1_10},
        {SerialSignal::rxd, PIN_P1_14},
    };
    const SerialSignalPin spim21_pins[] = {
        {SerialSignal::sck, PIN_P1_10},
        {SerialSignal::mosi, PIN_P1_12},
        {SerialSignal::miso, PIN_P1_14},
    };
    const SerialSignalPin twim22_pins[] = {
        {SerialSignal::sda, PIN_P1_02},
        {SerialSignal::scl, PIN_P1_03},
    };
    const SerialSignalPin uarte30_pins[] = {
        {SerialSignal::txd, PIN_P0_00},
        {SerialSignal::rxd, PIN_P0_01},
    };

    SerialFabricConfiguration config(SerialRouteClass route, SerialElectricalProfile electrical,
                                     const SerialSignalPin *pins, std::size_t pin_count,
                                     void *dma = nullptr, std::size_t dma_size = 0U)
    {
        static SerialDmaWorkspace workspace;
        workspace = {dma, dma_size};
        return {route,
                electrical,
                pins,
                pin_count,
                dma == nullptr ? nullptr : &workspace,
                dma == nullptr ? 0U : 1U};
    }

    void registerAdapter(SerialPersonality personality, std::uint8_t instance)
    {
        zassert_equal(registerSerialFabricAdapter(personality, instance, fake_adapter),
                      SerialFabricResult::success, "fake adapter 등록 실패");
    }

    void beforeEach(void *)
    {
        resetIoResourceManagerForTest();
        resetSerialFabricForTest();
        for (auto &state : fake)
        {
            state = {};
        }
    }
} // namespace

ZTEST(m24_serial_fabric_contract, test_factory_exposes_exact_typed_identities)
{
    auto &fabric = serialFabric();
    const std::uint8_t full_instances[] = {0U, 20U, 21U, 22U, 30U};
    for (const std::uint8_t instance : full_instances)
    {
        zassert_not_null(fabric.uarte(instance), "UARTE selector 누락");
        zassert_not_null(fabric.spim(instance), "SPIM selector 누락");
        zassert_not_null(fabric.spis(instance), "SPIS selector 누락");
    }
    const std::uint8_t twi_instances[] = {20U, 21U, 22U, 30U};
    for (const std::uint8_t instance : twi_instances)
    {
        zassert_not_null(fabric.twim(instance), "TWIM selector 누락");
        zassert_not_null(fabric.twis(instance), "TWIS selector 누락");
    }
    zassert_is_null(fabric.uarte(1U), "없는 UARTE instance를 만들었습니다.");
    zassert_is_null(fabric.twim(0U), "없는 TWIM00을 만들었습니다.");
    zassert_equal(fabric.spim(21U)->personality(), SerialPersonality::spim,
                  "typed handle personality가 다릅니다.");
    zassert_equal(fabric.spim(21U)->instance(), 21U, "typed handle instance가 다릅니다.");
}

ZTEST(m24_serial_fabric_contract, test_stage_rejects_unavailable_unsafe_and_duplicate_routes)
{
    auto *const handle = serialFabric().uarte(0U);
    zassert_equal(
        handle->stage(config(SerialRouteClass::p2_dedicated20,
                             SerialElectricalProfile::connector_fixture, uarte00_pins, 2U)),
        SerialFabricResult::driver_unavailable, "adapter 없는 handle을 stage했습니다.");
    registerAdapter(SerialPersonality::uarte, 0U);
    zassert_equal(handle->stage(config(SerialRouteClass::p2_dedicated20,
                                       SerialElectricalProfile::dap_uart_bridge, uarte00_pins, 2U)),
                  SerialFabricResult::unsafe_electrical_profile,
                  "P2에 DAP profile을 허용했습니다.");
    const SerialSignalPin duplicate[] = {{SerialSignal::txd, PIN_P2_02},
                                         {SerialSignal::txd, PIN_P2_00}};
    zassert_equal(handle->stage(config(SerialRouteClass::p2_dedicated20,
                                       SerialElectricalProfile::connector_fixture, duplicate, 2U)),
                  SerialFabricResult::invalid_argument, "중복 signal을 허용했습니다.");
    zassert_equal(handle->state(), SerialFabricState::inactive,
                  "실패한 stage가 상태를 변경했습니다.");
}

ZTEST(m24_serial_fabric_contract, test_same_block_conflicts_then_handover_succeeds)
{
    registerAdapter(SerialPersonality::uarte, 0U);
    registerAdapter(SerialPersonality::spim, 0U);
    auto *const uart = serialFabric().uarte(0U);
    auto *const spi = serialFabric().spim(0U);
    zassert_equal(uart->stage(config(SerialRouteClass::p2_dedicated20,
                                     SerialElectricalProfile::connector_fixture, uarte00_pins, 2U)),
                  SerialFabricResult::success, "UARTE00 stage 실패");
    zassert_equal(spi->stage(config(SerialRouteClass::p2_dedicated20,
                                    SerialElectricalProfile::connector_fixture, spim00_pins, 3U)),
                  SerialFabricResult::success, "SPIM00 stage 실패");
    zassert_equal(uart->activate(), SerialFabricResult::success, "UARTE00 activate 실패");
    zassert_equal(spi->activate(), SerialFabricResult::ownership_conflict,
                  "같은 serial00 personality가 동시에 활성화됐습니다.");
    zassert_equal(uart->deactivate(), SerialFabricResult::success, "UARTE00 종료 실패");
    zassert_equal(spi->activate(), SerialFabricResult::success, "SPIM00 handover 실패");
    zassert_equal(spi->deactivate(), SerialFabricResult::success, "SPIM00 종료 실패");
}

ZTEST(m24_serial_fabric_contract, test_disjoint_blocks_and_dma_coexist_overlap_fails)
{
    registerAdapter(SerialPersonality::uarte, 21U);
    registerAdapter(SerialPersonality::twim, 22U);
    registerAdapter(SerialPersonality::uarte, 30U);
    auto *const uart21 = serialFabric().uarte(21U);
    auto *const twim22 = serialFabric().twim(22U);
    auto *const uart30 = serialFabric().uarte(30U);
    zassert_equal(uart21->stage(config(SerialRouteClass::p1_flexible,
                                       SerialElectricalProfile::connector_fixture, uarte21_pins, 2U,
                                       &dma_a[0], 32U)),
                  SerialFabricResult::success, "UARTE21 stage 실패");
    zassert_equal(
        twim22->stage(config(SerialRouteClass::p1_flexible, SerialElectricalProfile::pmic_read_only,
                             twim22_pins, 2U, &dma_b[0], 32U)),
        SerialFabricResult::success, "TWIM22 stage 실패");
    zassert_equal(uart30->stage(config(SerialRouteClass::p0_flexible,
                                       SerialElectricalProfile::dap_uart_bridge, uarte30_pins, 2U,
                                       &dma_a[16], 16U)),
                  SerialFabricResult::success, "UARTE30 stage 실패");
    zassert_equal(uart21->activate(), SerialFabricResult::success, "UARTE21 activate 실패");
    zassert_equal(twim22->activate(), SerialFabricResult::success, "TWIM22 동시 activate 실패");
    zassert_equal(uart30->activate(), SerialFabricResult::ownership_conflict,
                  "겹친 DMA workspace를 동시에 소유했습니다.");
    zassert_equal(twim22->deactivate(), SerialFabricResult::success, "TWIM22 종료 실패");
    zassert_equal(uart21->deactivate(), SerialFabricResult::success, "UARTE21 종료 실패");
}

ZTEST(m24_serial_fabric_contract, test_driver_failure_rolls_back_without_partial_owner)
{
    registerAdapter(SerialPersonality::uarte, 0U);
    registerAdapter(SerialPersonality::spim, 0U);
    fake[0].fail_activate = true;
    auto *const uart = serialFabric().uarte(0U);
    auto *const spi = serialFabric().spim(0U);
    zassert_equal(uart->stage(config(SerialRouteClass::p2_dedicated20,
                                     SerialElectricalProfile::connector_fixture, uarte00_pins, 2U)),
                  SerialFabricResult::success, "실패 주입 UARTE00 stage 실패");
    zassert_equal(spi->stage(config(SerialRouteClass::p2_dedicated20,
                                    SerialElectricalProfile::connector_fixture, spim00_pins, 3U)),
                  SerialFabricResult::success, "후속 SPIM00 stage 실패");
    zassert_equal(uart->activate(), SerialFabricResult::driver_error,
                  "driver 실패를 전달하지 않았습니다.");
    fake[0].fail_activate = false;
    zassert_equal(spi->activate(), SerialFabricResult::success,
                  "실패 rollback 뒤 block을 재획득하지 못했습니다.");
    zassert_equal(spi->deactivate(), SerialFabricResult::success, "SPIM00 종료 실패");
}

ZTEST(m24_serial_fabric_contract, test_unprovable_stop_latches_whole_block_fail_closed)
{
    registerAdapter(SerialPersonality::uarte, 21U);
    registerAdapter(SerialPersonality::spim, 21U);
    auto *const uart = serialFabric().uarte(21U);
    auto *const spi = serialFabric().spim(21U);
    zassert_equal(uart->stage(config(SerialRouteClass::p1_flexible,
                                     SerialElectricalProfile::connector_fixture, uarte21_pins, 2U)),
                  SerialFabricResult::success, "UARTE21 stage 실패");
    zassert_equal(uart->activate(), SerialFabricResult::success, "UARTE21 activate 실패");
    fake[21].stop_complete = false;
    zassert_equal(uart->deactivate(20U), SerialFabricResult::stop_timeout,
                  "bounded stop 실패를 허용했습니다.");
    zassert_equal(uart->state(), SerialFabricState::faulted, "fault가 latch되지 않았습니다.");
    zassert_equal(spi->stage(config(SerialRouteClass::p1_flexible,
                                    SerialElectricalProfile::connector_fixture, spim21_pins, 3U)),
                  SerialFabricResult::faulted, "같은 serial21의 재사용을 허용했습니다.");
}

ZTEST_SUITE(m24_serial_fabric_contract, nullptr, nullptr, beforeEach, nullptr, nullptr);
