/** @file @brief 실제 등록 work handler를 수동 진행하는 최소 Zephyr 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <vector>
#define ARG_UNUSED(value) static_cast<void>(value)
#define K_NO_WAIT 0
#define K_MSEC(value) static_cast<std::int64_t>(value)
struct k_work
{
    void (*handler)(k_work *);
};
struct k_work_delayable
{
    k_work work;
};
namespace radio154_fixture
{
    inline k_work_delayable *pending = nullptr;
    inline std::vector<std::int64_t> delays{};
    inline std::int64_t now_ms = 0;
    inline unsigned int cancellations = 0U;
}
#define K_WORK_DELAYABLE_DEFINE(name, function) static k_work_delayable name{{function}}
inline int k_work_reschedule(k_work_delayable *work, std::int64_t delay)
{
    radio154_fixture::pending = work;
    radio154_fixture::delays.push_back(delay);
    return 1;
}
inline int k_work_cancel_delayable(k_work_delayable *work)
{
    ++radio154_fixture::cancellations;
    if (radio154_fixture::pending == work)
    {
        radio154_fixture::pending = nullptr;
    }
    return 0;
}
inline std::int64_t k_uptime_get()
{
    return radio154_fixture::now_ms;
}
inline void k_sleep(std::int64_t delay)
{
    radio154_fixture::now_ms += delay;
}
/** @brief 송신 회귀에서는 수신 queue가 항상 비어 있으며 수신 검증을 주장하지 않습니다. */
struct k_msgq
{
};
#define K_MSGQ_DEFINE(name, size, capacity, alignment) static k_msgq name{}
inline int k_msgq_put(k_msgq *, const void *, int)
{
    return 0;
}
inline int k_msgq_get(k_msgq *, void *, int)
{
    return -ENOMSG;
}
inline void k_msgq_purge(k_msgq *)
{
}
inline std::size_t k_msgq_num_used_get(k_msgq *)
{
    return 0U;
}
