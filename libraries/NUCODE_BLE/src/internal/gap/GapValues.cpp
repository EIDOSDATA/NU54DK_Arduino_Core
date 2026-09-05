/** @file @brief BLE UUID/address 값의 parsing·표현·비교입니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_BLE_GAP.h>
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <string.h>
#include <stdio.h>
namespace
{
    /** @brief ASCII hex 한 글자를 0..15로 변환합니다. */
    int hexValue(char value) noexcept
    {
        if (value >= '0' && value <= '9')
        {
            return value - '0';
        }
        if (value >= 'a' && value <= 'f')
        {
            return value - 'a' + 10;
        }
        if (value >= 'A' && value <= 'F')
        {
            return value - 'A' + 10;
        }
        return -1;
    }
} // namespace
namespace nucode::ble
{
    BLEUuid::BLEUuid(std::uint16_t value) noexcept : type_(Type::uuid16)
    {
        bytes_[0] = static_cast<std::uint8_t>(value & 0xffU);
        bytes_[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
    }

    BLEUuid::BLEUuid(const char *canonical) noexcept
    {
        if (canonical == nullptr || ::strlen(canonical) != 36U || canonical[8] != '-' ||
            canonical[13] != '-' || canonical[18] != '-' || canonical[23] != '-')
        {
            return;
        }

        std::uint8_t network_order[16] = {};
        std::size_t source = 0U;
        std::size_t destination = 0U;
        while (source < 36U)
        {
            if (canonical[source] == '-')
            {
                ++source;
                continue;
            }
            if (source + 1U >= 36U || destination >= sizeof(network_order))
            {
                return;
            }
            const int high = hexValue(canonical[source]);
            const int low = hexValue(canonical[source + 1U]);
            if (high < 0 || low < 0)
            {
                return;
            }
            network_order[destination++] = static_cast<std::uint8_t>((high << 4U) | low);
            source += 2U;
        }
        if (destination != sizeof(network_order))
        {
            return;
        }
        for (std::size_t index = 0U; index < sizeof(network_order); ++index)
        {
            bytes_[index] = network_order[sizeof(network_order) - index - 1U];
        }
        type_ = Type::uuid128;
    }

    BLEUuid BLEUuid::from32(std::uint32_t value) noexcept
    {
        BLEUuid result;
        result.type_ = Type::uuid32;
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            result.bytes_[index] = static_cast<std::uint8_t>((value >> (index * 8U)) & 0xffU);
        }
        return result;
    }

    bool BLEUuid::valid() const noexcept
    {
        return type_ != Type::invalid;
    }

    BLEUuid::Type BLEUuid::type() const noexcept
    {
        return type_;
    }

    std::size_t BLEUuid::size() const noexcept
    {
        return static_cast<std::size_t>(type_);
    }

    const std::uint8_t *BLEUuid::data() const noexcept
    {
        return bytes_;
    }

    bool BLEUuid::format(char *output, std::size_t capacity) const noexcept
    {
        if (output == nullptr || !valid())
        {
            return false;
        }
        if (type_ == Type::uuid16)
        {
            if (capacity < 5U)
            {
                return false;
            }
            const std::uint16_t value = static_cast<std::uint16_t>(bytes_[0]) |
                                        (static_cast<std::uint16_t>(bytes_[1]) << 8U);
            return ::snprintf(output, capacity, "%04x", value) == 4;
        }
        if (type_ == Type::uuid32)
        {
            if (capacity < 9U)
            {
                return false;
            }
            std::uint32_t value = 0U;
            for (std::size_t index = 0U; index < 4U; ++index)
            {
                value |= static_cast<std::uint32_t>(bytes_[index]) << (index * 8U);
            }
            return ::snprintf(output, capacity, "%08lx", static_cast<unsigned long>(value)) == 8;
        }
        if (capacity < 37U)
        {
            return false;
        }
        std::uint8_t network_order[16] = {};
        for (std::size_t index = 0U; index < sizeof(network_order); ++index)
        {
            network_order[index] = bytes_[sizeof(network_order) - index - 1U];
        }
        return ::snprintf(output, capacity,
                          "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-"
                          "%02x%02x%02x%02x%02x%02x",
                          network_order[0], network_order[1], network_order[2], network_order[3],
                          network_order[4], network_order[5], network_order[6], network_order[7],
                          network_order[8], network_order[9], network_order[10], network_order[11],
                          network_order[12], network_order[13], network_order[14],
                          network_order[15]) == 36;
    }

    bool BLEUuid::operator==(const BLEUuid &other) const noexcept
    {
        return type_ == other.type_ && valid() && ::memcmp(bytes_, other.bytes_, size()) == 0;
    }

    bool BLEUuid::operator!=(const BLEUuid &other) const noexcept
    {
        return !(*this == other);
    }

    BLEAddress::BLEAddress(const char *text, Type type) noexcept
    {
        if (text == nullptr || type == Type::invalid)
        {
            return;
        }
        unsigned int values[6] = {};
        int consumed = 0;
        if (::sscanf(text, "%2x:%2x:%2x:%2x:%2x:%2x%n", &values[0], &values[1], &values[2],
                     &values[3], &values[4], &values[5], &consumed) != 6 ||
            consumed != 17 || text[consumed] != '\0')
        {
            return;
        }
        for (std::size_t index = 0U; index < 6U; ++index)
        {
            if (values[index] > 0xffU)
            {
                return;
            }
            bytes_[5U - index] = static_cast<std::uint8_t>(values[index]);
        }
        type_ = type;
    }

    BLEAddress::BLEAddress(const std::uint8_t bytes[6], Type type) noexcept
    {
        if (bytes == nullptr || type == Type::invalid)
        {
            return;
        }
        ::memcpy(bytes_, bytes, sizeof(bytes_));
        type_ = type;
    }

    bool BLEAddress::valid() const noexcept
    {
        return type_ != Type::invalid;
    }

    BLEAddress::Type BLEAddress::type() const noexcept
    {
        return type_;
    }

    const std::uint8_t *BLEAddress::data() const noexcept
    {
        return bytes_;
    }

    bool BLEAddress::format(char *output, std::size_t capacity) const noexcept
    {
        if (output == nullptr || capacity < 18U || !valid())
        {
            return false;
        }
        return ::snprintf(output, capacity, "%02X:%02X:%02X:%02X:%02X:%02X", bytes_[5], bytes_[4],
                          bytes_[3], bytes_[2], bytes_[1], bytes_[0]) == 17;
    }

    bool BLEAddress::operator==(const BLEAddress &other) const noexcept
    {
        return type_ == other.type_ && valid() &&
               ::memcmp(bytes_, other.bytes_, sizeof(bytes_)) == 0;
    }

    bool BLEAddress::operator!=(const BLEAddress &other) const noexcept
    {
        return !(*this == other);
    }

} // namespace nucode::ble
#endif
