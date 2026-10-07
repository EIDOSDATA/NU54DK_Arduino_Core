/**
 * @file NUCODE_BLE_ProfileCodec.cpp
 * @brief 표준 GATT wire 값의 길이·범위·reserved bit를 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#include "NUCODE_BLE_ProfileCodec.h"

namespace nucode::ble::profiles
{
    namespace
    {
        /** @brief bounded little-endian 정수를 기록합니다. */
        void put(std::uint8_t *data, std::uint64_t value, std::size_t bytes) noexcept
        {
            for (std::size_t i = 0U; i < bytes; ++i)
            {
                data[i] = static_cast<std::uint8_t>(value >> (8U * i));
            }
        }
        /** @brief bounded little-endian 정수를 복원합니다. */
        std::uint64_t get(const std::uint8_t *data, std::size_t bytes) noexcept
        {
            std::uint64_t result = 0U;
            for (std::size_t i = 0U; i < bytes; ++i)
            {
                result |= static_cast<std::uint64_t>(data[i]) << (8U * i);
            }
            return result;
        }
        /** @brief 실제 달력과 Bluetooth unknown 날짜를 검증합니다. */
        bool validDate(const DateTime &date) noexcept
        {
            if ((date.year != 0U && (date.year < 1582U || date.year > 9999U)) || date.month > 12U ||
                date.day > 31U || date.hour > 23U || date.minute > 59U || date.second > 59U)
            {
                return false;
            }
            if (date.month == 0U || date.day == 0U)
            {
                return true;
            }
            const std::uint8_t days[] = {31U, 28U, 31U, 30U, 31U, 30U,
                                         31U, 31U, 30U, 31U, 30U, 31U};
            const bool leap =
                date.year == 0U ||
                (date.year % 4U == 0U && (date.year % 100U != 0U || date.year % 400U == 0U));
            return date.day <= days[date.month - 1U] + (date.month == 2U && leap ? 1U : 0U);
        }
        void putDate(std::uint8_t *data, const DateTime &date) noexcept
        {
            put(data, date.year, 2U);
            data[2] = date.month;
            data[3] = date.day;
            data[4] = date.hour;
            data[5] = date.minute;
            data[6] = date.second;
        }
        DateTime getDate(const std::uint8_t *data) noexcept
        {
            return {static_cast<std::uint16_t>(get(data, 2U)),
                    data[2],
                    data[3],
                    data[4],
                    data[5],
                    data[6]};
        }
        /** @brief 과장된 UTF-8 길이·overlong·surrogate·잘린 multibyte를 거부합니다. */
        bool validUtf8(const std::uint8_t *data, std::size_t length) noexcept
        {
            for (std::size_t i = 0U; i < length;)
            {
                const std::uint8_t first = data[i++];
                if (first == 0U)
                {
                    return false;
                }
                if (first < 0x80U)
                {
                    continue;
                }
                const std::size_t count = first >= 0xc2U && first <= 0xdfU   ? 1U
                                          : first >= 0xe0U && first <= 0xefU ? 2U
                                          : first >= 0xf0U && first <= 0xf4U ? 3U
                                                                             : 0U;
                if (count == 0U || count > length - i)
                {
                    return false;
                }
                if ((first == 0xe0U && data[i] < 0xa0U) || (first == 0xedU && data[i] >= 0xa0U) ||
                    (first == 0xf0U && data[i] < 0x90U) || (first == 0xf4U && data[i] >= 0x90U))
                {
                    return false;
                }
                for (std::size_t j = 0U; j < count; ++j)
                {
                    if ((data[i++] & 0xc0U) != 0x80U)
                    {
                        return false;
                    }
                }
            }
            return true;
        }
    } // namespace

    bool Codec::encode(const CurrentTime &v, Packet &out) noexcept
    {
        out.length = 0U;
        if (!validDate(v.date) || v.weekday > 7U || (v.adjust_reason & 0xf0U) != 0U)
        {
            return false;
        }
        putDate(out.data, v.date);
        out.data[7] = v.weekday;
        out.data[8] = v.fractions256;
        out.data[9] = v.adjust_reason;
        out.length = 10U;
        return true;
    }
    bool Codec::decode(const std::uint8_t *data, std::size_t length, CurrentTime &out) noexcept
    {
        if (data == nullptr || length != 10U)
        {
            return false;
        }
        const CurrentTime value{getDate(data), data[7], data[8], data[9]};
        Packet check;
        if (!encode(value, check))
        {
            return false;
        }
        out = value;
        return true;
    }
    bool Codec::encode(const Temperature &v, Packet &out) noexcept
    {
        out.length = 0U;
        if (v.mantissa < -8388608 || v.mantissa > 8388607 ||
            (v.has_timestamp && !validDate(v.timestamp)) ||
            (v.has_type && (v.type < 1U || v.type > 9U)))
        {
            return false;
        }
        out.data[0] =
            (v.fahrenheit ? 1U : 0U) | (v.has_timestamp ? 2U : 0U) | (v.has_type ? 4U : 0U);
        put(out.data + 1U, static_cast<std::uint32_t>(v.mantissa), 3U);
        out.data[4] = static_cast<std::uint8_t>(v.exponent);
        out.length = 5U;
        if (v.has_timestamp)
        {
            putDate(out.data + out.length, v.timestamp);
            out.length += 7U;
        }
        if (v.has_type)
        {
            out.data[out.length++] = v.type;
        }
        return true;
    }
    bool Codec::decode(const std::uint8_t *data, std::size_t length, Temperature &out) noexcept
    {
        if (data == nullptr || length < 5U || (data[0] & 0xf8U) != 0U ||
            length != 5U + ((data[0] & 2U) != 0U ? 7U : 0U) + ((data[0] & 4U) != 0U ? 1U : 0U))
        {
            return false;
        }
        Temperature value;
        value.fahrenheit = (data[0] & 1U) != 0U;
        value.has_timestamp = (data[0] & 2U) != 0U;
        value.has_type = (data[0] & 4U) != 0U;
        const auto raw = static_cast<std::uint32_t>(get(data + 1U, 3U));
        value.mantissa = static_cast<std::int32_t>(raw) - ((raw & 0x800000U) != 0U ? 16777216 : 0);
        value.exponent = static_cast<std::int8_t>(data[4]);
        if (value.has_timestamp)
        {
            value.timestamp = getDate(data + 5U);
        }
        if (value.has_type)
        {
            value.type = data[length - 1U];
        }
        Packet check;
        if (!encode(value, check))
        {
            return false;
        }
        out = value;
        return true;
    }
    bool Codec::encode(const CyclingMeasurement &v, Packet &out) noexcept
    {
        out.length = 1U;
        out.data[0] = (v.has_wheel ? 1U : 0U) | (v.has_crank ? 2U : 0U);
        if (v.has_wheel)
        {
            put(out.data + out.length, v.wheel_revolutions, 4U);
            put(out.data + out.length + 4U, v.wheel_event1024, 2U);
            out.length += 6U;
        }
        if (v.has_crank)
        {
            put(out.data + out.length, v.crank_revolutions, 2U);
            put(out.data + out.length + 2U, v.crank_event1024, 2U);
            out.length += 4U;
        }
        return true;
    }
    bool Codec::decode(const std::uint8_t *data, std::size_t length,
                       CyclingMeasurement &out) noexcept
    {
        if (data == nullptr || length < 1U || (data[0] & 0xfcU) != 0U ||
            length != 1U + ((data[0] & 1U) != 0U ? 6U : 0U) + ((data[0] & 2U) != 0U ? 4U : 0U))
        {
            return false;
        }
        CyclingMeasurement value;
        value.has_wheel = (data[0] & 1U) != 0U;
        value.has_crank = (data[0] & 2U) != 0U;
        std::size_t offset = 1U;
        if (value.has_wheel)
        {
            value.wheel_revolutions = static_cast<std::uint32_t>(get(data + offset, 4U));
            value.wheel_event1024 = static_cast<std::uint16_t>(get(data + offset + 4U, 2U));
            offset += 6U;
        }
        if (value.has_crank)
        {
            value.crank_revolutions = static_cast<std::uint16_t>(get(data + offset, 2U));
            value.crank_event1024 = static_cast<std::uint16_t>(get(data + offset + 2U, 2U));
        }
        out = value;
        return true;
    }
    bool Codec::encode(const RunningMeasurement &v, Packet &out) noexcept
    {
        out.data[0] = (v.has_stride ? 1U : 0U) | (v.has_distance ? 2U : 0U) | (v.running ? 4U : 0U);
        put(out.data + 1U, v.speed256, 2U);
        out.data[3] = v.cadence;
        out.length = 4U;
        if (v.has_stride)
        {
            put(out.data + out.length, v.stride_cm, 2U);
            out.length += 2U;
        }
        if (v.has_distance)
        {
            put(out.data + out.length, v.distance_decimetres, 4U);
            out.length += 4U;
        }
        return true;
    }
    bool Codec::decode(const std::uint8_t *data, std::size_t length,
                       RunningMeasurement &out) noexcept
    {
        if (data == nullptr || length < 4U || (data[0] & 0xf8U) != 0U ||
            length != 4U + ((data[0] & 1U) != 0U ? 2U : 0U) + ((data[0] & 2U) != 0U ? 4U : 0U))
        {
            return false;
        }
        RunningMeasurement value;
        value.has_stride = (data[0] & 1U) != 0U;
        value.has_distance = (data[0] & 2U) != 0U;
        value.running = (data[0] & 4U) != 0U;
        value.speed256 = static_cast<std::uint16_t>(get(data + 1U, 2U));
        value.cadence = data[3];
        if (value.has_stride)
        {
            value.stride_cm = static_cast<std::uint16_t>(get(data + 4U, 2U));
        }
        if (value.has_distance)
        {
            value.distance_decimetres = static_cast<std::uint32_t>(get(data + length - 4U, 4U));
        }
        out = value;
        return true;
    }
    bool Codec::encode(const GlucoseMeasurement &v, Packet &out) noexcept
    {
        out.length = 0U;
        if (v.mantissa < -2048 || v.mantissa > 2047 || v.exponent < -8 || v.exponent > 7)
        {
            return false;
        }
        out.data[0] = 6U;
        out.data[1] = 0U;
        const std::uint16_t raw = (static_cast<std::uint16_t>(v.mantissa) & 0x0fffU) |
                                  ((static_cast<std::uint16_t>(v.exponent) & 0x0fU) << 12U);
        put(out.data + 2U, raw, 2U);
        put(out.data + 4U, v.time_offset_minutes, 2U);
        out.length = 6U;
        return true;
    }
    bool Codec::decode(const std::uint8_t *data, std::size_t length,
                       GlucoseMeasurement &out) noexcept
    {
        if (data == nullptr || length != 6U || data[0] != 6U || data[1] != 0U)
        {
            return false;
        }
        const auto raw = static_cast<std::uint16_t>(get(data + 2U, 2U));
        GlucoseMeasurement value;
        value.mantissa =
            static_cast<std::int16_t>(raw & 0x0fffU) - ((raw & 0x0800U) != 0U ? 4096 : 0);
        value.exponent = static_cast<std::int8_t>(raw >> 12U) - ((raw & 0x8000U) != 0U ? 16 : 0);
        value.time_offset_minutes = static_cast<std::uint16_t>(get(data + 4U, 2U));
        out = value;
        return true;
    }
    bool Codec::encode(const ElapsedTime &v, Packet &out) noexcept
    {
        out.length = 0U;
        if ((v.flags & 0xc0U) != 0U || v.counter > 0xffffffffffffULL || v.source > 7U ||
            (v.clock_status & 0xfeU) != 0U || (v.clock_capabilities & 0xfcU) != 0U ||
            ((v.flags & 0x10U) != 0U && (v.timezone_quarters < -48 || v.timezone_quarters > 56)))
        {
            return false;
        }
        out.data[0] = v.flags;
        put(out.data + 1U, v.counter, 6U);
        out.data[7] = v.source;
        out.data[8] = static_cast<std::uint8_t>(v.timezone_quarters);
        out.data[9] = v.clock_status;
        out.data[10] = v.clock_capabilities;
        out.length = 11U;
        return true;
    }
    bool Codec::decode(const std::uint8_t *data, std::size_t length, ElapsedTime &out) noexcept
    {
        if (data == nullptr || length != 11U)
        {
            return false;
        }
        const ElapsedTime value{data[0], get(data + 1U, 6U),
                                data[7], static_cast<std::int8_t>(data[8]),
                                data[9], data[10]};
        Packet check;
        if (!encode(value, check))
        {
            return false;
        }
        out = value;
        return true;
    }
    bool Codec::encode(const Alert &v, Packet &out) noexcept
    {
        out.length = 0U;
        std::size_t text_length = 0U;
        while (text_length < sizeof(v.text) && v.text[text_length] != '\0')
        {
            ++text_length;
        }
        if (v.category > 9U || text_length > 18U ||
            !validUtf8(reinterpret_cast<const std::uint8_t *>(v.text), text_length))
        {
            return false;
        }
        out.data[0] = v.category;
        out.data[1] = v.count;
        for (std::size_t i = 0U; i < text_length; ++i)
        {
            out.data[i + 2U] = static_cast<std::uint8_t>(v.text[i]);
        }
        out.length = text_length + 2U;
        return true;
    }
    bool Codec::decode(const std::uint8_t *data, std::size_t length, Alert &out) noexcept
    {
        if (data == nullptr || length < 2U || length > 20U || data[0] > 9U ||
            !validUtf8(data + 2U, length - 2U))
        {
            return false;
        }
        Alert value;
        value.category = data[0];
        value.count = data[1];
        for (std::size_t i = 2U; i < length; ++i)
        {
            value.text[i - 2U] = static_cast<char>(data[i]);
        }
        out = value;
        return true;
    }
    bool Codec::valid(Kind kind, const std::uint8_t *data, std::size_t length) noexcept
    {
        switch (kind)
        {
        case Kind::current_time:
        {
            CurrentTime value;
            return decode(data, length, value);
        }
        case Kind::thermometer:
        {
            Temperature value;
            return decode(data, length, value);
        }
        case Kind::cycling:
        {
            CyclingMeasurement value;
            return decode(data, length, value);
        }
        case Kind::running:
        {
            RunningMeasurement value;
            return decode(data, length, value);
        }
        case Kind::glucose:
        {
            GlucoseMeasurement value;
            return decode(data, length, value);
        }
        case Kind::elapsed_time:
        {
            ElapsedTime value;
            return decode(data, length, value);
        }
        case Kind::alert:
        {
            Alert value;
            return decode(data, length, value);
        }
        default:
            return false;
        }
    }
    std::uint16_t Codec::measurementUuid(Kind kind) noexcept
    {
        switch (kind)
        {
        case Kind::current_time:
            return 0x2a2bU;
        case Kind::thermometer:
            return 0x2a1cU;
        case Kind::alert:
            return 0x2a46U;
        case Kind::running:
            return 0x2a53U;
        case Kind::cycling:
            return 0x2a5bU;
        case Kind::glucose:
            return 0x2aa7U;
        case Kind::elapsed_time:
            return 0x2bf2U;
        case Kind::bond_management:
            return 0x2aa4U;
        default:
            return 0U;
        }
    }
    bool Codec::usesIndications(Kind kind) noexcept
    {
        return kind == Kind::thermometer || kind == Kind::elapsed_time;
    }
    bool AlertControl::apply(const std::uint8_t *data, std::size_t length) noexcept
    {
        if (data == nullptr || length != 2U || data[0] > 5U || (data[1] > 9U && data[1] != 0xffU))
        {
            return false;
        }
        const std::uint16_t mask =
            data[1] == 0xffU ? 0x03ffU : static_cast<std::uint16_t>(1U << data[1]);
        switch (data[0])
        {
        case 0U:
            new_mask_ |= mask;
            break;
        case 1U:
            unread_mask_ |= mask;
            break;
        case 2U:
            new_mask_ &= static_cast<std::uint16_t>(~mask);
            break;
        case 3U:
            unread_mask_ &= static_cast<std::uint16_t>(~mask);
            break;
        case 4U:
            immediate_new_ |= mask & new_mask_;
            break;
        case 5U:
            immediate_unread_ |= mask & unread_mask_;
            break;
        default:
            return false;
        }
        return true;
    }
    bool AlertControl::newEnabled(std::uint8_t category) const noexcept
    {
        return category < 10U && (new_mask_ & (1U << category)) != 0U;
    }
    bool AlertControl::unreadEnabled(std::uint8_t category) const noexcept
    {
        return category < 10U && (unread_mask_ & (1U << category)) != 0U;
    }
    std::uint16_t AlertControl::takeImmediateNew() noexcept
    {
        const auto result = immediate_new_;
        immediate_new_ = 0U;
        return result;
    }
    std::uint16_t AlertControl::takeImmediateUnread() noexcept
    {
        const auto result = immediate_unread_;
        immediate_unread_ = 0U;
        return result;
    }
    void AlertControl::reset() noexcept
    {
        *this = AlertControl{};
    }
} // namespace nucode::ble::profiles
