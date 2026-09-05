/** @file @brief 실제 atomic 저장과 SPI 초기화 형식을 연결합니다. */
#pragma once
#include "../../../serial_driver_stubs/zephyr/sys/atomic.h"
using atomic_val_t = int;
#define ATOMIC_INIT(value) (value)
