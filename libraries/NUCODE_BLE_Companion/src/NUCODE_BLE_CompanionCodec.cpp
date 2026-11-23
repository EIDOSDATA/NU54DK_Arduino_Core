/** @file @brief 고정 NCS ANCS/AMS wire 형식의 범위·분할 응답을 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#include "NUCODE_BLE_CompanionCodec.h"

namespace nucode::ble::companion
{
    namespace
    {
        uint32_t read32(const uint8_t *data)
        {
            return static_cast<uint32_t>(data[0]) | (static_cast<uint32_t>(data[1]) << 8) |
                   (static_cast<uint32_t>(data[2]) << 16) | (static_cast<uint32_t>(data[3]) << 24);
        }

        void write32(uint8_t *data, uint32_t value)
        {
            for (size_t i = 0; i < 4; ++i)
            {
                data[i] = static_cast<uint8_t>(value >> (8 * i));
            }
        }
    } // namespace

    Error decodeNotification(const uint8_t *data, size_t size, Notification &output) noexcept
    {
        if (data == nullptr || size != 8 || data[0] > 2 || (data[1] & 0xe0) != 0 || data[2] > 11)
        {
            return Error::malformed;
        }
        output = {read32(data + 4), data[0], data[1], data[2], data[3]};
        return Error::none;
    }

    bool validMediaAttribute(uint8_t entity, uint8_t attribute) noexcept
    {
        return entity <= 2 && attribute <= (entity == 0 ? 2 : 3);
    }

    Error decodeMediaUpdate(const uint8_t *data, size_t size, MediaUpdate &output) noexcept
    {
        if (data == nullptr || size < 3 || !validMediaAttribute(data[0], data[1]) ||
            (data[2] & 0xfe) != 0)
        {
            return Error::malformed;
        }
        output = {data[0], data[1], (data[2] & 1) != 0, data + 3, size - 3};
        return Error::none;
    }

    Error decodeMediaCommands(const uint8_t *data, size_t size, uint16_t &mask) noexcept
    {
        if ((data == nullptr && size != 0) || size > 14)
        {
            return Error::malformed;
        }
        uint16_t result = 0;
        for (size_t i = 0; i < size; ++i)
        {
            if (data[i] > 13 || (result & (1U << data[i])) != 0)
            {
                return Error::malformed;
            }
            result |= static_cast<uint16_t>(1U << data[i]);
        }
        mask = result;
        return Error::none;
    }

    Error encodeAttributeRequest(uint32_t uid, uint8_t attribute, uint16_t maximum, uint8_t *output,
                                 size_t capacity, size_t &length) noexcept
    {
        length = 0;
        if (output == nullptr || capacity < 8 || attribute > 7 || maximum == 0 || maximum > 128)
        {
            return Error::invalid_argument;
        }
        output[0] = 0;
        write32(output + 1, uid);
        output[5] = attribute;
        length = 6;
        if (attribute >= 1 && attribute <= 3)
        {
            output[6] = static_cast<uint8_t>(maximum);
            output[7] = static_cast<uint8_t>(maximum >> 8);
            length = 8;
        }
        return Error::none;
    }

    Error encodeNotificationAction(const Notification &notification, bool positive, uint8_t *output,
                                   size_t capacity) noexcept
    {
        const uint8_t required = positive ? 0x08 : 0x10;
        if (output == nullptr || capacity < 6 || notification.event == 2 ||
            (notification.flags & required) == 0)
        {
            return Error::invalid_argument;
        }
        output[0] = 2;
        write32(output + 1, notification.uid);
        output[5] = positive ? 0 : 1;
        return Error::none;
    }

    Error AttributeAssembler::begin(uint32_t uid, uint8_t attribute) noexcept
    {
        reset();
        if (attribute > 7)
        {
            return Error::invalid_argument;
        }
        uid_ = uid;
        attribute_ = attribute;
        active_ = true;
        return Error::none;
    }

    Error AttributeAssembler::feed(const uint8_t *data, size_t size) noexcept
    {
        if (!active_ || (data == nullptr && size != 0))
        {
            return Error::stale_session;
        }
        if (size > sizeof(buffer_) - used_)
        {
            reset();
            return Error::overflow;
        }
        for (size_t i = 0; i < size; ++i)
        {
            buffer_[used_++] = data[i];
        }
        if (used_ >= 8)
        {
            const size_t content =
                static_cast<size_t>(buffer_[6]) | (static_cast<size_t>(buffer_[7]) << 8);
            if (buffer_[0] != 0 || read32(buffer_ + 1) != uid_ || buffer_[5] != attribute_ ||
                content > maximum_text || used_ > content + 8)
            {
                reset();
                return Error::malformed;
            }
            expected_ = content + 8;
        }
        return Error::none;
    }

    void AttributeAssembler::reset() noexcept
    {
        for (uint8_t &value : buffer_)
        {
            value = 0;
        }
        used_ = expected_ = 0;
        uid_ = 0;
        attribute_ = 0;
        active_ = false;
    }

    bool AttributeAssembler::complete() const noexcept
    {
        return active_ && expected_ >= 8 && used_ == expected_;
    }

    const uint8_t *AttributeAssembler::text() const noexcept
    {
        return complete() ? buffer_ + 8 : nullptr;
    }

    size_t AttributeAssembler::length() const noexcept
    {
        return complete() ? expected_ - 8 : 0;
    }
} // namespace nucode::ble::companion
