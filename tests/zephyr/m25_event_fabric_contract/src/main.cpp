/**
 * @file main.cpp
 * @brief M25 event fabric 전 instance와 domain 경계를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/EventFabric.h>

#include <zephyr/ztest.h>

#include <cstdint>

using namespace nucode::arduino;

ZTEST(m25_event_fabric_contract, test_all_instance_handles_exist)
{
    const std::uint8_t timers[] = {0U, 10U, 20U, 21U, 22U, 23U, 24U};
    for (const auto instance : timers)
    {
        auto *const handle = eventFabric().timer(instance);
        zassert_not_null(handle, "TIMER handle 누락");
        zassert_true(handle->channelCount() >= 6U, "TIMER CC channel 누락");
    }
    zassert_is_null(eventFabric().timer(25U), "가짜 TIMER handle 노출");

    const std::uint8_t egus[] = {10U, 20U};
    for (const auto instance : egus)
        zassert_not_null(eventFabric().egu(instance), "EGU handle 누락");
    const std::uint8_t gpiotes[] = {20U, 30U};
    for (const auto instance : gpiotes)
        zassert_not_null(eventFabric().gpiote(instance), "GPIOTE handle 누락");
    const std::uint8_t dppis[] = {0U, 10U, 20U, 30U};
    for (const auto instance : dppis)
        zassert_not_null(eventFabric().dppi(instance), "DPPIC handle 누락");
    const std::uint8_t ppibs[] = {0U, 1U, 10U, 11U, 20U, 21U, 22U, 30U};
    for (const auto instance : ppibs)
        zassert_not_null(eventFabric().ppib(instance), "PPIB handle 누락");
}

ZTEST(m25_event_fabric_contract, test_endpoint_domains_are_explicit)
{
    auto *const timer20 = eventFabric().timer(20U);
    auto *const egu20 = eventFabric().egu(20U);
    auto *const ppib21 = eventFabric().ppib(21U);
    zassert_equal(timer20->compareEvent(0U).domain, 20U, "TIMER20 domain 불일치");
    zassert_equal(timer20->task(TimerTask::start).role,
                  EventEndpointRole::subscriber, "TIMER task role 불일치");
    zassert_equal(egu20->event(0U).role, EventEndpointRole::publisher,
                  "EGU event role 불일치");
    zassert_equal(ppib21->sendTask(0U).domain, 20U,
                  "PPIB21 bridge domain 불일치");
    zassert_not_equal(ppib21->receiveEvent(0U).address, 0U,
                      "PPIB receive endpoint 누락");
}

ZTEST(m25_event_fabric_contract, test_cross_domain_connect_fails_closed)
{
    auto *const dppi20 = eventFabric().dppi(20U);
    auto *const timer20 = eventFabric().timer(20U);
    auto *const timer10 = eventFabric().timer(10U);
    zassert_equal(dppi20->acquireChannel(0U), EventFabricResult::success,
                  "DPPIC20 channel 획득 실패");
    zassert_equal(dppi20->connect(timer10->compareEvent(0U),
                                  timer20->task(TimerTask::start), 0U),
                  EventFabricResult::unsupported_route,
                  "PPIB 없는 cross-domain 연결을 허용했습니다.");
    zassert_equal(dppi20->releaseChannel(0U), EventFabricResult::success,
                  "DPPIC20 channel 반환 실패");
}

ZTEST_SUITE(m25_event_fabric_contract, nullptr, nullptr, nullptr, nullptr,
            nullptr);
