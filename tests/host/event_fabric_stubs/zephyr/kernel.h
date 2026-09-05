/** @file @brief production Event registry에 실제 Host mutex와 초기화 순서를 제공합니다. */
#pragma once
#include "../../serial_driver_stubs/zephyr/kernel.h"
using k_mutex = std::recursive_mutex;
#undef SYS_INIT
#define SYS_INIT(fn, level, priority) const int mock_init_##fn = fn()
