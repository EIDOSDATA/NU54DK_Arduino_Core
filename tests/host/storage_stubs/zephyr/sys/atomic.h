/** @file @brief File 오류 기록용 실제 Host atomic입니다. */
#pragma once
#include "../../../serial_driver_stubs/zephyr/sys/atomic.h"
using atomic_val_t = int;
#define ATOMIC_INIT(value) {value}
