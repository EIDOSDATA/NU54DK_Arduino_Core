/** @file @brief Host thread 간 상태 publish를 실제 atomic으로 검증합니다. */
#pragma once
#include <atomic>
using atomic_t = std::atomic<int>;
inline int atomic_get(const atomic_t *value)
{
    return value->load();
}
inline void atomic_set(atomic_t *value, int next)
{
    value->store(next);
}
inline void atomic_clear(atomic_t *value)
{
    value->store(0);
}
using atomic_ptr_t = std::atomic<void *>;
inline void atomic_ptr_set(atomic_ptr_t *slot, void *value)
{
    slot->store(value);
}
inline void atomic_ptr_clear(atomic_ptr_t *slot)
{
    slot->store(nullptr);
}
inline void *atomic_ptr_get(atomic_ptr_t *slot)
{
    return slot->load();
}
