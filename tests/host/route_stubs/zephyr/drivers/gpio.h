/** @file @brief 물리 GPIO 키만 제공하는 Host descriptor입니다. */
#pragma once
#include <cstdint>
struct gpio_dt_spec
{
    const void *port;
    std::uint32_t pin;
    std::uint32_t dt_flags;
};
