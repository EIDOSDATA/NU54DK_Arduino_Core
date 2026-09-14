/** @file @brief OOB codec Host 시험용 little-endian helper입니다. */
#pragma once

#include <cstdint>

inline void sys_put_le16(std::uint16_t value, std::uint8_t *output)
{
    output[0] = static_cast<std::uint8_t>(value);
    output[1] = static_cast<std::uint8_t>(value >> 8U);
}

inline std::uint16_t sys_get_le16(const std::uint8_t *input)
{
    return static_cast<std::uint16_t>(input[0]) |
           (static_cast<std::uint16_t>(input[1]) << 8U);
}

inline void sys_put_le32(std::uint32_t value, std::uint8_t *output)
{
    output[0] = static_cast<std::uint8_t>(value);
    output[1] = static_cast<std::uint8_t>(value >> 8U);
    output[2] = static_cast<std::uint8_t>(value >> 16U);
    output[3] = static_cast<std::uint8_t>(value >> 24U);
}

inline std::uint32_t sys_get_le32(const std::uint8_t *input)
{
    return static_cast<std::uint32_t>(input[0]) |
           (static_cast<std::uint32_t>(input[1]) << 8U) |
           (static_cast<std::uint32_t>(input[2]) << 16U) |
           (static_cast<std::uint32_t>(input[3]) << 24U);
}
