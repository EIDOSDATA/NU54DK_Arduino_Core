/**
 * @file main.cpp
 * @brief M25 SAADC/PWM 전 instance 후보 API 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/AnalogFabric.h>

#include <variant.h>

#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>

namespace
{
    using namespace nucode::arduino;

    const SaadcChannelConfiguration scan_channels[] = {
        {SaadcInput::ain0, SaadcInput::disabled},
        {SaadcInput::ain1, SaadcInput::disabled},
        {SaadcInput::ain2, SaadcInput::ain3},
        {SaadcInput::vdd, SaadcInput::disabled},
    };
} // namespace

ZTEST(m25_analog_fabric_contract, test_saadc_scan_contract)
{
    auto &saadc = analogFabric().saadc();
    zassert_equal(saadc.configure({scan_channels, 4U, 14U, 16U, 0U}),
                  AnalogFabricResult::success, "4-channel scan 설정 실패");
    zassert_equal(saadc.state(), AnalogFabricState::configured,
                  "SAADC configured 상태 불일치");
    zassert_not_equal(saadc.sampleTaskAddress(), 0U,
                      "SAADC SAMPLE task 주소 누락");
    zassert_not_equal(saadc.readyEventAddress(), 0U,
                      "SAADC READY event 주소 누락");
}

ZTEST(m25_analog_fabric_contract, test_saadc_invalid_combinations_fail_closed)
{
    auto &saadc = analogFabric().saadc();
    zassert_equal(saadc.configure({scan_channels, 4U, 12U, 4U, 10U}),
                  AnalogFabricResult::invalid_argument,
                  "다중 channel internal timer를 허용했습니다.");
    const SaadcChannelConfiguration duplicate[] = {
        {SaadcInput::ain0, SaadcInput::disabled},
        {SaadcInput::ain0, SaadcInput::disabled},
    };
    zassert_equal(saadc.configure({duplicate, 2U, 12U, 1U, 0U}),
                  AnalogFabricResult::invalid_argument,
                  "중복 positive channel을 허용했습니다.");
}

ZTEST(m25_analog_fabric_contract, test_all_pwm_instances_and_routes_exist)
{
    const std::uint8_t instances[] = {20U, 21U, 22U};
    const pin_size_t pins[] = {PIN_P1_04, PIN_P1_05, PIN_P1_06, PIN_P1_07};
    for (const std::uint8_t instance : instances)
    {
        auto *const pwm = analogFabric().pwm(instance);
        zassert_not_null(pwm, "PWM handle 누락");
        PwmSequenceConfiguration configuration{};
        for (std::size_t index = 0U; index < 4U; ++index)
            configuration.output_pins[index] = pins[index];
        configuration.top_value = 1000U;
        configuration.load = PwmSequenceLoad::individual;
        zassert_equal(pwm->configure(configuration), AnalogFabricResult::success,
                      "PWM route 설정 실패");
        zassert_equal(pwm->state(), AnalogFabricState::configured,
                      "PWM configured 상태 불일치");
    }
    zassert_is_null(analogFabric().pwm(23U), "존재하지 않는 PWM handle 노출");
}

ZTEST(m25_analog_fabric_contract, test_inactive_stop_operations_fail_closed)
{
    auto *const pwm = analogFabric().pwm(20U);
    zassert_equal(pwm->stop(), AnalogFabricResult::wrong_state,
                  "active가 아닌 PWM stop을 허용했습니다.");
    std::int16_t samples[8]{};
    auto &saadc = analogFabric().saadc();
    zassert_equal(saadc.sample(), AnalogFabricResult::wrong_state,
                  "active/READY가 아닌 SAADC SAMPLE을 허용했습니다.");
    zassert_equal(saadc.queueBuffer(samples, 8U), AnalogFabricResult::wrong_state,
                  "active가 아닌 SAADC buffer를 허용했습니다.");
}

ZTEST_SUITE(m25_analog_fabric_contract, nullptr, nullptr, nullptr, nullptr,
            nullptr);
