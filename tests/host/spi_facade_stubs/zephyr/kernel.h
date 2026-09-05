/** @file @brief SPI transaction의 실제 Host thread identity를 제공합니다. */
#pragma once
#include "../../serial_driver_stubs/zephyr/kernel.h"
using k_tid_t = void *;
inline thread_local char mock_thread_identity;
inline k_tid_t k_current_get()
{
    return &mock_thread_identity;
}
