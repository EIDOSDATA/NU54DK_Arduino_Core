/** @file @brief BLE compile에 필요한 순수 Zephyr macro입니다. */
#pragma once
#define ARG_UNUSED(value) (void)(value)
#define ARRAY_SIZE(value) (sizeof(value) / sizeof((value)[0]))
#define __weak __attribute__((weak))
#define BIT(index) (1UL << (index))
