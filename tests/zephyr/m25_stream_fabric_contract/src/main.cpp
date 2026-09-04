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
    zassert_equal(pdm20->configure({PIN_P1_04, PIN_P1_05, 16000U, false, false}),
                  StreamFabricResult::success, "PDM20 route 설정 실패");
    zassert_equal(pdm21->configure({PIN_P1_06, PIN_P1_07, 32000U, true, true}),
                  StreamFabricResult::success, "PDM21 route 설정 실패");
    zassert_not_equal(pdm20->startTaskAddress(), 0U,
                      "PDM20 START task endpoint 누락");
}

ZTEST(m25_stream_fabric_contract, test_i2s_full_duplex_route_configures)
{
    auto *const i2s = streamFabric().i2s(20U);
    I2sConfiguration configuration{};
    configuration.sck_pin = PIN_P1_02;
    configuration.lrck_pin = PIN_P1_03;
    configuration.mck_pin = PIN_P1_04;
    configuration.data_out_pin = PIN_P1_05;
    configuration.data_in_pin = PIN_P1_06;
    configuration.sample_rate_hz = 48000U;
    configuration.sample_width = I2sSampleWidth::bits24;
    configuration.channels = I2sChannels::stereo;
    zassert_equal(i2s->configure(configuration), StreamFabricResult::success,
                  "I2S20 full-duplex route 설정 실패");
    zassert_equal(i2s->state(), StreamFabricState::configured,
                  "I2S20 configured 상태 불일치");
}

ZTEST(m25_stream_fabric_contract, test_qdec_routes_configure)
{
    const std::uint8_t instances[]{20U, 21U};
    for (const std::uint8_t instance : instances)
    {
        auto *const qdec = streamFabric().qdec(instance);
        zassert_equal(
            qdec->configure({PIN_P1_04, PIN_P1_05, PIN_P1_06, true, true}),
            StreamFabricResult::success, "QDEC route 설정 실패");
        zassert_equal(qdec->state(), StreamFabricState::configured,
                      "QDEC configured 상태 불일치");
    }
}

ZTEST(m25_stream_fabric_contract, test_inactive_dma_calls_fail_closed)
{
    std::int16_t pdm_samples[32]{};
    std::uint32_t i2s_samples[32]{};
    zassert_equal(streamFabric().pdm(20U)->queueBuffer(pdm_samples, 32U),
                  StreamFabricResult::wrong_state,
                  "inactive PDM queue를 허용했습니다.");
    zassert_equal(
        streamFabric().i2s(20U)->queueBuffers({i2s_samples, nullptr, 32U}),
        StreamFabricResult::wrong_state, "inactive I2S queue를 허용했습니다.");
}

ZTEST_SUITE(m25_stream_fabric_contract, nullptr, nullptr, nullptr, nullptr,
            nullptr);
