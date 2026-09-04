#pragma once
#include <cstdint>
struct device;
struct gpio_dt_spec { const device *port; std::uint32_t pin; };
