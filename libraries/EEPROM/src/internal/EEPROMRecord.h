/** @file @brief 기존 EEPROM record의 byte 순서·CRC·고정 형식을 보존합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <EEPROM.h>
namespace nucode::eeprom::internal
{
    inline constexpr char settings_key[] = "arduino/eeprom";
    inline constexpr std::uint32_t record_magic = 0x45503534UL;
    inline constexpr std::uint16_t record_version = 1U;
    inline constexpr std::size_t record_header_size = 12U;

    /** @brief 작은 정수를 record의 little-endian byte 순서로 기록합니다. */
    template <typename T> void storeInteger(std::uint8_t *destination, T value) noexcept
    {
        for (std::size_t index = 0U; index < sizeof(T); ++index)
        {
            destination[index] = static_cast<std::uint8_t>(value >> (index * 8U));
        }
    }

    /** @brief record의 little-endian byte를 작은 정수로 복원합니다. */
    template <typename T> T loadInteger(const std::uint8_t *source) noexcept
    {
        T value = 0U;
        for (std::size_t index = 0U; index < sizeof(T); ++index)
        {
            value |= static_cast<T>(source[index]) << (index * 8U);
        }
        return value;
    }

    std::uint32_t crc32(const std::uint8_t *data, std::size_t length) noexcept;
} // namespace nucode::eeprom::internal
