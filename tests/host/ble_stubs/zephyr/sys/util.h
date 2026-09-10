/** @file @brief BLE compile에 필요한 순수 Zephyr macro입니다. */
#pragma once
#define ARG_UNUSED(value) (void)(value)
#define ARRAY_SIZE(value) (sizeof(value) / sizeof((value)[0]))
/** @brief PE-COFF GAP 단독 링크에서는 기본 hook을 명시적인 강한 정의로 만듭니다. */
#if defined(NUCODE_HOST_STRONG_DEFAULT_HOOKS)
#define __weak
#else
#define __weak __attribute__((weak))
#endif
#define BIT(index) (1UL << (index))
