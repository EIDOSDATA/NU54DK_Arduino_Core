/** @file @brief 실제 mutex와 lock 진입 관측으로 File thread 교차를 검증합니다. */
#pragma once
#include <functional>
#include <mutex>
#include <zephyr/sys/atomic.h>
using k_mutex = std::recursive_mutex;
inline thread_local bool mock_in_isr = false;
/** @brief 여러 TU에서 동일 thread의 lock 관측 callback을 공유합니다. */
inline std::function<void()> &mockBeforeLock()
{
    static thread_local std::function<void()> callback;
    return callback;
}
#define K_MUTEX_DEFINE(name) std::recursive_mutex name
#define K_FOREVER 0
inline bool k_is_in_isr()
{
    return mock_in_isr;
}
inline int k_mutex_lock(std::recursive_mutex *mutex, int)
{
    if (mockBeforeLock())
    {
        mockBeforeLock()();
    }
    mutex->lock();
    return 0;
}
inline int k_mutex_unlock(std::recursive_mutex *mutex)
{
    mutex->unlock();
    return 0;
}
