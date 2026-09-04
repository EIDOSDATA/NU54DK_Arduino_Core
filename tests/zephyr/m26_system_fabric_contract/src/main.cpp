/**
 * @file main.cpp
 * @brief M26 TEMP와 WDT30/31 후보 API의 target link 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SystemFabric.h>

#include <zephyr/ztest.h>

using namespace nucode::arduino;

ZTEST(m26_system_fabric_contract, test_factory_exposes_exact_instances)
{
    auto &fabric = systemFabric();
    auto *const wdt30 = fabric.watchdog(30U);
    auto *const wdt31 = fabric.watchdog(31U);
    zassert_not_null(wdt30, "WDT30 handle이 없습니다.");
    zassert_not_null(wdt31, "WDT31 handle이 없습니다.");
    zassert_equal(wdt30->instance(), 30U, "WDT30 identity가 다릅니다.");
    zassert_equal(wdt31->instance(), 31U, "WDT31 identity가 다릅니다.");
    zassert_is_null(fabric.watchdog(29U), "존재하지 않는 WDT를 노출했습니다.");
    zassert_false(wdt30->configured(), "WDT30 초기 상태가 configured입니다.");
    zassert_false(wdt31->active(), "WDT31 초기 상태가 active입니다.");
}

ZTEST(m26_system_fabric_contract, test_temp_driver_path_is_linked)
{
    std::int32_t centi_celsius = 0;
    const auto result = systemFabric().temperature().readCentiCelsius(centi_celsius);
    zassert_true(result == SystemFabricResult::success ||
                     result == SystemFabricResult::driver_unavailable ||
                     result == SystemFabricResult::driver_error,
                 "TEMP read가 계약 밖의 결과를 반환했습니다.");
    if (result == SystemFabricResult::success)
    {
        zassert_true(centi_celsius >= -4000 && centi_celsius <= 12500,
                     "TEMP 결과가 silicon 범위를 벗어났습니다.");
    }
}

ZTEST(m26_system_fabric_contract, test_watchdog_lifecycle_rejects_invalid_calls)
{
    auto *const watchdog = systemFabric().watchdog(30U);
    zassert_not_null(watchdog, "WDT30 handle이 없습니다.");
    zassert_equal(watchdog->configure(0U), SystemFabricResult::invalid_argument,
                  "0 ms timeout을 허용했습니다.");
    zassert_equal(watchdog->start(), SystemFabricResult::wrong_state,
                  "configure 전 WDT start를 허용했습니다.");
    zassert_equal(watchdog->feed(), SystemFabricResult::wrong_state,
                  "start 전 WDT feed를 허용했습니다.");
    zassert_equal(watchdog->stop(), SystemFabricResult::wrong_state,
                  "configure 전 WDT stop을 허용했습니다.");
}

ZTEST_SUITE(m26_system_fabric_contract, nullptr, nullptr, nullptr, nullptr,
            nullptr);
