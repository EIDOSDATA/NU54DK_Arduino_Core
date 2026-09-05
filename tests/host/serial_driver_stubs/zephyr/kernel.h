/** @file @brief 실제 thread 배타성과 제어 가능한 IRQ/시간을 제공하는 Host kernel입니다. */
#pragma once
#include <atomic>
#include <cstdint>
#include <functional>
#include <mutex>
#include <thread>
inline std::recursive_mutex mock_irq_mutex;
inline thread_local bool mock_in_isr = false;
inline std::function<void(std::uint32_t)> mock_wait;
inline std::atomic<std::uint64_t> waited_us{0};
#define K_MUTEX_DEFINE(name) std::recursive_mutex name
#define K_FOREVER 0
/** @brief 별도 translation unit에서도 초기화 함수 참조를 보존하며 장치 초기화는 실행하지 않습니다. */
#define SYS_INIT(fn, level, priority) [[maybe_unused]] static auto mock_init_##fn = &fn
inline bool k_is_in_isr()
{
    return mock_in_isr;
}
inline void k_mutex_lock(std::recursive_mutex *mutex, int)
{
    mutex->lock();
}
inline void k_mutex_unlock(std::recursive_mutex *mutex)
{
    mutex->unlock();
}
inline void k_busy_wait(std::uint32_t us)
{
    waited_us += us;
    if (mock_wait)
    {
        mock_wait(us);
    }
    std::this_thread::yield();
}
struct k_spinlock
{
    std::mutex mutex;
};
using k_spinlock_key_t = unsigned;
inline k_spinlock_key_t k_spin_lock(k_spinlock *lock)
{
    mock_irq_mutex.lock();
    lock->mutex.lock();
    return 0;
}
inline void k_spin_unlock(k_spinlock *lock, k_spinlock_key_t)
{
    lock->mutex.unlock();
    mock_irq_mutex.unlock();
}
