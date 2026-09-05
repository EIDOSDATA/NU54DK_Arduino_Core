/**
 * @file main.cpp
 * @brief 선택한 personality의 실제 공개 함수 참조와 링크를 검증합니다.
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>
#include <zephyr/ztest.h>

using namespace nucode::arduino;

ZTEST(r01_serial, test_selected_personality_implementations_are_linked)
{
    auto &fabric = serialFabric();
    zassert_not_null(fabric.uarte(21U));
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE)
    zassert_equal(fabric.uarte(21U)->configure({115200U, UarteParity::none, false}),
                  SerialFabricResult::success);
#endif
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM)
    zassert_equal(fabric.spim(21U)->configure(
                      {4000000U, SpiFabricMode::mode0, SpiFabricBitOrder::msb_first, 0xFFU}),
                  SerialFabricResult::success);
#endif
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS)
    zassert_equal(fabric.spis(21U)->configure(
                      {0U, SpiFabricMode::mode0, SpiFabricBitOrder::msb_first, 0xFFU}),
                  SerialFabricResult::success);
#endif
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIM)
    zassert_equal(fabric.twim(21U)->configure({TwiFabricFrequency::standard}),
                  SerialFabricResult::success);
#endif
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIS)
    zassert_equal(fabric.twis(21U)->configure({0x42U}), SerialFabricResult::success);
#endif
}

ZTEST_SUITE(r01_serial, nullptr, nullptr, nullptr, nullptr, nullptr);
