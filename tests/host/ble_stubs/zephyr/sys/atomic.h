/** @file @brief BLE reference/session 검사에 사용하는 Host atomic입니다. */
#pragma once
#include "../../../serial_driver_stubs/zephyr/sys/atomic.h"
using atomic_val_t = int;
using atomic_ptr_t = std::atomic<void *>;
#define ATOMIC_INIT(value) value
inline bool atomic_cas(atomic_t *value, int old_value, int new_value)
{
    return value->compare_exchange_strong(old_value, new_value);
}
inline int atomic_inc(atomic_t *value)
{
    return value->fetch_add(1);
}
inline int atomic_dec(atomic_t *value)
{
    return value->fetch_sub(1);
}

inline void *atomic_ptr_get(const atomic_ptr_t *value)
{
    return value->load();
}

inline bool atomic_ptr_cas(atomic_ptr_t *value, void *old_value, void *new_value)
{
    return value->compare_exchange_strong(old_value, new_value);
}
