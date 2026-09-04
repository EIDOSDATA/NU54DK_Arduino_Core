/**
 * @file main.cpp
 * @brief M25 PDM/I2S/QDEC 전 instance 후보 API 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/StreamFabric.h>

#include <variant.h>

#include <zephyr/ztest.h>

#include <cstdint>

using namespace nucode::arduino;

ZTEST(m25_stream_fabric_contract, test_all_stream_instances_exist)
{
    zassert_not_null(streamFabric().pdm(20U), "PDM20 handle 누락");
    zassert_not_null(streamFabric().pdm(21U), "PDM21 handle 누락");
    zassert_is_null(streamFabric().pdm(22U), "가짜 PDM handle 노출");
    zassert_not_null(streamFabric().i2s(20U), "I2S20 handle 누락");
    zassert_is_null(streamFabric().i2s(21U), "가짜 I2S handle 노출");
    zassert_not_null(streamFabric().qdec(20U), "QDEC20 handle 누락");
    zassert_not_null(streamFabric().qdec(21U), "QDEC21 handle 누락");
    zassert_is_null(streamFabric().qdec(22U), "가짜 QDEC handle 노출");
}

ZTEST(m25_stream_fabric_contract, test_pdm_header_routes_configure)
{
    auto *const pdm20 = streamFabric().pdm(20U);
    auto *const pdm21 = streamFabric().pdm(21U);
    zassert_equal(pdm20->configure({PIN_P1_04, PIN_P1_05, 16000U, false, false,
                                    StreamElectricalProfile::dap_uart_disabled}),
                  StreamFabricResult::success, "PDM20 route 설정 실패");
    zassert_equal(pdm21->configure({PIN_P1_06, PIN_P1_07, 32000U, true, true,
                                    StreamElectricalProfile::dap_uart_disabled}),
                  StreamFabricResult::success, "PDM21 route 설정 실패");
    zassert_not_equal(pdm20->startTaskAddress(), 0U, "PDM20 START task endpoint 누락");
}

ZTEST(m25_stream_fabric_contract, test_i2s_full_duplex_route_configures)
{
    auto *const i2s = streamFabric().i2s(20U);
    I2sConfiguration configuration{};
    configuration.sck_pin = PIN_P1_04;
    configuration.lrck_pin = PIN_P1_05;
    configuration.data_out_pin = PIN_P1_06;
    configuration.data_in_pin = PIN_P1_07;
    configuration.electrical_profile = StreamElectricalProfile::dap_uart_disabled;
    configuration.sample_rate_hz = 48000U;
    configuration.sample_width = I2sSampleWidth::bits24;
    configuration.channels = I2sChannels::stereo;
    zassert_equal(i2s->configure(configuration), StreamFabricResult::success,
                  "I2S20 full-duplex route 설정 실패");
    zassert_equal(i2s->state(), StreamFabricState::configured, "I2S20 configured 상태 불일치");
}

ZTEST(m25_stream_fabric_contract, test_qdec_routes_configure)
{
    const std::uint8_t instances[]{20U, 21U};
    for (const std::uint8_t instance : instances)
    {
        auto *const qdec = streamFabric().qdec(instance);
        QdecConfiguration configuration{PIN_P1_04, PIN_P1_05, PIN_P1_06, true, true};
        configuration.electrical_profile = StreamElectricalProfile::dap_uart_disabled;
        zassert_equal(qdec->configure(configuration), StreamFabricResult::success,
                      "QDEC route 설정 실패");
        zassert_equal(qdec->state(), StreamFabricState::configured, "QDEC configured 상태 불일치");
    }
}

ZTEST(m25_stream_fabric_contract, test_inactive_dma_calls_fail_closed)
{
    std::int16_t pdm_samples[32]{};
    std::uint32_t i2s_samples[32]{};
    zassert_equal(streamFabric().pdm(20U)->queueBuffer(pdm_samples, 32U),
                  StreamFabricResult::wrong_state, "inactive PDM queue를 허용했습니다.");
    zassert_equal(streamFabric().i2s(20U)->queueBuffers({i2s_samples, nullptr, 32U}),
                  StreamFabricResult::wrong_state, "inactive I2S queue를 허용했습니다.");
}

ZTEST(m25_stream_fabric_contract, test_qdec_sampling_rejects_aliasing_configuration_errors)
{
    auto *const qdec = streamFabric().qdec(20U);
    QdecConfiguration configuration{PIN_P1_04, PIN_P1_05, 0xff, false, false};
    configuration.sample_period_us = 256;
    configuration.led_pre_us = 50;
    configuration.report_events = false;
    configuration.electrical_profile = StreamElectricalProfile::dap_uart_disabled;
    zassert_equal(qdec->configure(configuration), StreamFabricResult::success,
                  "명시적인 256us 수동 누산 설정을 거부했습니다.");
    configuration.sample_period_us = 200;
    zassert_equal(qdec->configure(configuration), StreamFabricResult::invalid_argument,
                  "지원하지 않는 샘플 주기를 허용했습니다.");
    configuration.sample_period_us = 128;
    configuration.led_pre_us = 128;
    zassert_equal(qdec->configure(configuration), StreamFabricResult::invalid_argument,
                  "샘플 주기 이상의 LED 준비 시간을 허용했습니다.");
}

ZTEST(m25_stream_fabric_contract, test_dap_stream_route_requires_explicit_isolation)
{
    auto *const pdm = streamFabric().pdm(20U);
    PdmConfiguration configuration{PIN_P1_04, PIN_P1_05, 16000, false, false};
    zassert_equal(pdm->configure(configuration), StreamFabricResult::unsupported_route,
                  "기본 profile에서 콘솔 예약 DAP 핀을 허용했습니다.");
    configuration.electrical_profile = StreamElectricalProfile::dap_uart_disabled;
    configuration.clock_pin = PIN_P1_02;
    zassert_equal(pdm->configure(configuration), StreamFabricResult::unsupported_route,
                  "DAP 격리 profile에 PMIC 버스 핀을 섞었습니다.");
}

ZTEST_SUITE(m25_stream_fabric_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
