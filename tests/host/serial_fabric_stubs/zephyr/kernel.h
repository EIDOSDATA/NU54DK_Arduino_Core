#pragma once
#include <cstdint>
#define K_MUTEX_DEFINE(name) int name = 0
#define K_FOREVER 0
inline bool k_is_in_isr()
{
    return false;
}
inline void k_mutex_lock(int *, int)
{
}
inline void k_mutex_unlock(int *)
{
}
extern std::uint64_t waited_us;
inline void k_busy_wait(std::uint32_t us)
{
    waited_us += us;
}
