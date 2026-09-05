/** @file @brief EEPROM record의 순수 IEEE CRC-32 계산입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "EEPROMRecord.h"
namespace nucode::eeprom::internal
{
    /** @brief EEPROM payload의 IEEE CRC-32를 계산합니다. */
    std::uint32_t crc32(const std::uint8_t *data, std::size_t length) noexcept
    {
        std::uint32_t crc = 0xffffffffUL;
        for (std::size_t index = 0U; index < length; ++index)
        {
            crc ^= data[index];
            for (std::uint8_t bit = 0U; bit < 8U; ++bit)
            {
                const std::uint32_t mask = 0U - (crc & 1U);
                crc = (crc >> 1U) ^ (0xedb88320UL & mask);
            }
        }
        return ~crc;
    }

} // namespace nucode::eeprom::internal
#endif
