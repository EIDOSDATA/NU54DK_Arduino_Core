/** @file @brief Fabric stop 시험에 R02 thread 모델과 가상 cycle 시계를 제공합니다. */
#pragma once
#include "../../serial_driver_stubs/zephyr/kernel.h"
inline std::uint32_t k_cycle_get_32()
{
    return static_cast<std::uint32_t>(waited_us.load());
}
inline std::uint32_t k_cyc_to_us_floor32(std::uint32_t value)
{
    return value;
}
