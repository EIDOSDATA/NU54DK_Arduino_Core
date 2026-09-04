#pragma once
using atomic_ptr_t = void *;
inline void atomic_ptr_set(atomic_ptr_t *slot, void *value) { *slot = value; }
inline void atomic_ptr_clear(atomic_ptr_t *slot) { *slot = nullptr; }
inline void *atomic_ptr_get(atomic_ptr_t *slot) { return *slot; }
