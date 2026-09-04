/**
 * @file main.cpp
 * @brief AC-02B Serial1/Wire/SPI route와 PM begin/end를 보드에서 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <nucode/Diagnostics.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/pm/device.h>
#include <zephyr/pm/device_runtime.h>
#include <zephyr/ztest.h>

#include "internal/SPIBackend.h"

namespace
{
    /** @brief 장치가 runtime PM suspend 상태인지 확인합니다. */
    void expectSuspended(const struct device *device)
    {
        enum pm_device_state state = PM_DEVICE_STATE_ACTIVE;
        zassert_true(pm_device_runtime_is_enabled(device));
        zassert_ok(pm_device_state_get(device, &state));
        zassert_equal(state, PM_DEVICE_STATE_SUSPENDED);
    }

    /** @brief 장치가 Arduino begin 뒤 active인지 확인합니다. */
    void expectActive(const struct device *device)
    {
        enum pm_device_state state = PM_DEVICE_STATE_SUSPENDED;
        zassert_ok(pm_device_state_get(device, &state));
        zassert_equal(state, PM_DEVICE_STATE_ACTIVE);
    }

    /** @brief 공개 진단이 예상 분류와 route detail을 보존하는지 확인합니다. */
    void expectRouteDiagnostic(nucode::arduino::DiagnosticSubsystem subsystem,
                               nucode::arduino::DiagnosticCode code, bool require_detail)
    {
        const auto diagnostic = nucode::arduino::lastDiagnostic(subsystem);
        zassert_equal(diagnostic.subsystem, subsystem);
        zassert_equal(diagnostic.code, code);
        zassert_equal(diagnostic.driver_error, 0);
        if (require_detail)
        {
            zassert_not_equal(diagnostic.detail, 0U,
                              "invalid route의 세부 원인이 공개 진단에서 유실됐습니다.");
        }
    }
} // namespace

ZTEST(ac02b_b2, test_serial1_p0_zero_psel_and_rebegin)
{
    const struct device *const uart = DEVICE_DT_GET(DT_NODELABEL(uart30));
    expectSuspended(uart);
    zassert_false(Serial1.setPins(PIN_P1_02, PIN_P1_03));
    expectRouteDiagnostic(nucode::arduino::DiagnosticSubsystem::serial1,
                          nucode::arduino::DiagnosticCode::invalid_pin, true);
    zassert_true(Serial1.setPins(PIN_P0_01, PIN_P0_00));
    Serial1.begin(115200U, SERIAL_8N1);
    zassert_true(Serial1);
    expectActive(uart);
    zassert_false(Serial1.setPins(PIN_P0_03, PIN_P0_02));
    expectRouteDiagnostic(nucode::arduino::DiagnosticSubsystem::serial1,
                          nucode::arduino::DiagnosticCode::ownership_conflict, false);
    Serial1.begin(230400U, SERIAL_8E1);
    zassert_true(Serial1);
    Serial1.end();
    expectSuspended(uart);
    Serial1.begin(115200U, SERIAL_8N1);
    zassert_true(Serial1);
    Serial1.end();
}

ZTEST(ac02b_b2, test_wire_port_matrix_and_lifecycle)
{
    const struct device *const i2c = DEVICE_DT_GET(DT_NODELABEL(i2c22));
    expectSuspended(i2c);
    zassert_false(Wire.setPins(PIN_P0_00, PIN_P0_01));
    expectRouteDiagnostic(nucode::arduino::DiagnosticSubsystem::wire,
                          nucode::arduino::DiagnosticCode::invalid_pin, true);
    zassert_true(Wire.setPins(PIN_P1_02, PIN_P1_03));
    Wire.begin();
    expectActive(i2c);
    zassert_false(Wire.setPins(PIN_P1_10, PIN_P1_14));
    expectRouteDiagnostic(nucode::arduino::DiagnosticSubsystem::wire,
                          nucode::arduino::DiagnosticCode::ownership_conflict, false);
    Wire.setClock(400000U);
    Wire.end();
    expectSuspended(i2c);
}

ZTEST(ac02b_b2, test_spi00_exact_route_and_lifecycle)
{
    const struct device *const spi = DEVICE_DT_GET(DT_NODELABEL(spi00));
    expectSuspended(spi);
    zassert_false(SPI.setPins(PIN_P2_02, PIN_P2_04, PIN_P2_01));
    expectRouteDiagnostic(nucode::arduino::DiagnosticSubsystem::spi,
                          nucode::arduino::DiagnosticCode::invalid_pin, true);
    zassert_true(SPI.setPins(PIN_P2_01, PIN_P2_04, PIN_P2_02));
    SPI.begin();
    expectActive(spi);
    SPI.begin();
    zassert_equal(nucode::arduino::internal::lastSpiError(),
                  nucode::arduino::internal::SpiError::none,
                  "활성 상태의 SPI.begin() 재호출이 멱등 성공하지 않았습니다.");
    expectActive(spi);
    zassert_false(SPI.setPins(PIN_P2_01, PIN_P2_04, PIN_P2_02));
    expectRouteDiagnostic(nucode::arduino::DiagnosticSubsystem::spi,
                          nucode::arduino::DiagnosticCode::ownership_conflict, false);
    SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
    SPI.endTransaction();
    SPI.end();
    expectSuspended(spi);
}

ZTEST_SUITE(ac02b_b2, nullptr, nullptr, nullptr, nullptr, nullptr);
