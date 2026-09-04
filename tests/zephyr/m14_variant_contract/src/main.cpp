/**
 * @file main.cpp
 * @brief NU54DK Core-owned DTS에서 생성한 31핀 canonical Variant를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/util.h>
#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>

#include "internal/pin_description.h"

namespace
{
    using nucode::arduino::internal::canonicalPinId;
    using nucode::arduino::internal::GpioError;
    using nucode::arduino::internal::hasPinCapability;
    using nucode::arduino::internal::hasPinRoute;
    using nucode::arduino::internal::lastGpioError;
    using nucode::arduino::internal::PinCapability;
    using nucode::arduino::internal::PinDescription;
    using nucode::arduino::internal::pinDescription;
    using nucode::arduino::internal::PinOwnership;
    using nucode::arduino::internal::PinPolicy;
    using nucode::arduino::internal::PinRoute;

    /** @brief DTS child와 canonical 논리 ID의 기대 관계입니다. */
    struct ExpectedPin
    {
        std::size_t logical_pin;
        gpio_dt_spec gpio;
        PinCapability capabilities;
        PinOwnership ownership;
        PinPolicy policy;
        PinRoute routes;
        std::int8_t analog_channel;
    };

    /** @brief profile에서 조건부 GPIO capability를 fail-closed로 제거합니다. */
    [[nodiscard]] constexpr PinCapability expectedCapabilities(std::uint32_t raw,
                                                               PinPolicy policy) noexcept
    {
        if ((policy == PinPolicy::conditional_lfxo) && (NUCODE_NU54DK_HAS_LFXO_GPIO_PINS == 0))
        {
            return PinCapability::none;
        }
        if ((policy == PinPolicy::conditional_dap_uart) &&
            (NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS == 0))
        {
            return PinCapability::none;
        }
        return static_cast<PinCapability>(raw);
    }

    const ExpectedPin expected_pins[] = {
#define NUCODE_NU54DK_PHYSICAL_PIN(logical_pin, node_label)                                        \
    {static_cast<std::size_t>(logical_pin),                                                        \
     GPIO_DT_SPEC_GET(DT_NODELABEL(node_label), gpios),                                            \
     expectedCapabilities(                                                                         \
         DT_PROP(DT_NODELABEL(node_label), nucode_capability_mask),                                \
         static_cast<PinPolicy>(DT_PROP(DT_NODELABEL(node_label), nucode_policy))),                \
     static_cast<PinOwnership>(DT_PROP(DT_NODELABEL(node_label), nucode_ownership)),               \
     static_cast<PinPolicy>(DT_PROP(DT_NODELABEL(node_label), nucode_policy)),                     \
     static_cast<PinRoute>(DT_PROP(DT_NODELABEL(node_label), nucode_route_mask)),                  \
     static_cast<std::int8_t>(DT_PROP_OR(DT_NODELABEL(node_label), nucode_analog_channel, -1))},
#include <digital_pins.inc>
#undef NUCODE_NU54DK_PHYSICAL_PIN
    };

    static_assert(LED_BUILTIN == 0U && PIN_BUTTON0 == 1U && PIN_A0 == 2U && PIN_PWM0 == 3U &&
                      PIN_LED1 == 4U && PIN_BUTTON3 == 9U,
                  "v0.1~v0.2 공개 논리 pin 번호를 보존해야 합니다.");
    static_assert(NUM_DIGITAL_PINS == 32U && NUM_DIGITAL_CAPABLE_PINS == 20U &&
                      NUM_PIN_ROLES == 32U && NUM_PHYSICAL_PINS == 31U,
                  "31개 실제 pad와 legacy alias span 계약이 다릅니다.");
    static_assert(ARRAY_SIZE(expected_pins) == NUM_PHYSICAL_PINS,
                  "DTS 기반 canonical descriptor 수가 31개가 아닙니다.");
    static_assert(D0 == LED_BUILTIN && D1 == PIN_BUTTON0 && D10 == PIN_GPIO0 && D11 == PIN_GPIO1,
                  "기존 Arduino digital 별칭 값이 달라졌습니다.");
    static_assert(digitalPinToInterrupt(PIN_A0) == PIN_A0 &&
                      digitalPinToInterrupt(PIN_PWM0) == PIN_PWM0 &&
                      digitalPinToInterrupt(PIN_LED1) == PIN_PWM0 &&
                      digitalPinToInterrupt(LED_BUILTIN) == NOT_AN_INTERRUPT &&
                      digitalPinToInterrupt(PIN_GPIO0) == NOT_AN_INTERRUPT &&
                      digitalPinToInterrupt(PIN_P2_04) == NOT_AN_INTERRUPT,
                  "canonical interrupt와 P2 fail-closed 계약이 다릅니다.");

    /** @brief 실제 descriptor와 DTS에서 생성한 전체 metadata를 비교합니다. */
    void verifyPin(const ExpectedPin &expected)
    {
        const PinDescription *const actual = pinDescription(expected.logical_pin);
        zassert_not_null(actual, "canonical pin descriptor가 없습니다.");
        zassert_equal(actual->canonical_pin, expected.logical_pin,
                      "descriptor canonical ID가 다릅니다.");
        zassert_equal(actual->gpio.port, expected.gpio.port,
                      "descriptor GPIO controller가 Core-owned DTS와 다릅니다.");
        zassert_equal(actual->gpio.pin, expected.gpio.pin,
                      "descriptor GPIO pin이 Core-owned DTS와 다릅니다.");
        zassert_equal(actual->gpio.dt_flags, expected.gpio.dt_flags,
                      "descriptor GPIO flag가 Core-owned DTS와 다릅니다.");
        zassert_equal(actual->capabilities, expected.capabilities,
                      "descriptor capability가 Core-owned DTS와 다릅니다.");
        zassert_equal(actual->ownership, expected.ownership,
                      "descriptor ownership metadata가 다릅니다.");
        zassert_equal(actual->policy, expected.policy, "descriptor policy metadata가 다릅니다.");
        zassert_equal(actual->routes, expected.routes, "descriptor route metadata가 다릅니다.");
        zassert_equal(actual->analog_channel, expected.analog_channel,
                      "descriptor analog channel metadata가 다릅니다.");
    }
} // namespace

ZTEST(m14_variant_contract, test_all_31_physical_pads_are_generated_from_core_dts)
{
    zassert_equal(nucode::arduino::internal::pinDescriptionCount(), NUM_PHYSICAL_PINS,
                  "canonical descriptor 개수가 31개가 아닙니다.");
    for (const auto &expected : expected_pins)
    {
        verifyPin(expected);
    }
    zassert_is_null(pinDescription(NUM_PIN_ROLES), "범위 밖 descriptor가 nullptr가 아닙니다.");
}

ZTEST(m14_variant_contract, test_legacy_id4_resolves_to_canonical_id3)
{
    zassert_equal(canonicalPinId(PIN_LED1), static_cast<std::size_t>(PIN_PWM0),
                  "legacy ID 4가 canonical ID 3으로 정규화되지 않았습니다.");
    zassert_equal(pinDescription(PIN_LED1), pinDescription(PIN_PWM0),
                  "legacy LED1과 canonical PWM0가 같은 descriptor를 사용하지 않습니다.");
    zassert_equal(pinDescription(PIN_LED1)->gpio.port, DEVICE_DT_GET(DT_NODELABEL(gpio1)),
                  "legacy LED1 controller가 P1이 아닙니다.");
    zassert_equal(pinDescription(PIN_LED1)->gpio.pin, 10U,
                  "legacy LED1이 P1.10을 가리키지 않습니다.");
}

ZTEST(m14_variant_contract, test_policy_and_port2_interrupts_fail_closed)
{
    for (const auto &expected : expected_pins)
    {
        const PinDescription *const description = pinDescription(expected.logical_pin);
        if (hasPinRoute(description->routes, PinRoute::port2))
        {
            zassert_false(hasPinCapability(description->capabilities, PinCapability::interrupt),
                          "P2 descriptor에 interrupt capability가 있습니다.");
            zassert_equal(digitalPinToInterrupt(expected.logical_pin), NOT_AN_INTERRUPT,
                          "P2 logical pin을 interrupt 번호로 노출했습니다.");
        }
        if ((description->policy == PinPolicy::input_only) ||
            (description->policy == PinPolicy::system_reserved))
        {
            zassert_false(
                hasPinCapability(description->capabilities, PinCapability::digital_output),
                "input-only/system-reserved pin에 output capability가 있습니다.");
        }
    }

    pinMode(PIN_P1_04, INPUT);
    zassert_equal(lastGpioError(), GpioError::unsupported_capability,
                  "UART20 system-reserved AIN0를 GPIO input으로 구성했습니다.");
    pinMode(PIN_BUTTON2, OUTPUT);
    zassert_equal(lastGpioError(), GpioError::unsupported_capability,
                  "input-only 버튼을 GPIO output으로 구성했습니다.");
}

ZTEST(m14_variant_contract, test_conditional_gpio_caps_are_gated_but_routes_remain)
{
    const PinDescription *const dap_tx = pinDescription(PIN_P0_00);
    const PinDescription *const lfxo = pinDescription(PIN_P1_00);
    zassert_not_null(dap_tx, "P0.0 descriptor가 없습니다.");
    zassert_not_null(lfxo, "P1.0 descriptor가 없습니다.");
    zassert_equal(dap_tx->capabilities, PinCapability::none,
                  "승인되지 않은 DAP UART pin에 GPIO capability가 있습니다.");
    zassert_equal(lfxo->capabilities, PinCapability::none,
                  "승인되지 않은 LFXO pin에 GPIO capability가 있습니다.");
    zassert_true(hasPinRoute(dap_tx->routes, PinRoute::uart30),
                 "GPIO gate가 Serial1 UART30 route까지 제거했습니다.");
    zassert_true(hasPinRoute(lfxo->routes, PinRoute::i2c22),
                 "GPIO gate가 P1 주변장치 기술 route까지 제거했습니다.");
}

ZTEST_SUITE(m14_variant_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
