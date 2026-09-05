/** @file @brief 실제 mutex와 lock 진입 관측으로 File thread 교차를 검증합니다. */
#pragma once
#include <functional>
#include <mutex>
inline thread_local bool mock_in_isr = false;
inline thread_local std::function<void()> mock_before_lock;
#define K_MUTEX_DEFINE(name) std::recursive_mutex name
#define K_FOREVER 0
inline bool k_is_in_isr()
{
    return mock_in_isr;
}
inline int k_mutex_lock(std::recursive_mutex *mutex, int)
{
    if (mock_before_lock)
    {
        mock_before_lock();
    }
    mutex->lock();
    return 0;
}
inline int k_mutex_unlock(std::recursive_mutex *mutex)
{
    mutex->unlock();
    return 0;
}
