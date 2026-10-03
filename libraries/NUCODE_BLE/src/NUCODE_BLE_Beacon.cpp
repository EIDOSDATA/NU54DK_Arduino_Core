/**
 * @file NUCODE_BLE_Beacon.cpp
 * @brief iBeacon, Eddystone UID, BTHome v2 광고 payload 코덱을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Beacon.h"

namespace
{

    constexpr std::uint8_t manufacturer_data_type = 0xffU;
    constexpr std::uint8_t service_data_uuid16_type = 0x16U;

    struct AdvertisingField
    {
        const std::uint8_t *data = nullptr;
        std::size_t length = 0U;
        bool saw_type = false;
    };

    /** @brief 겹치지 않는 고정 길이 byte 배열을 복사합니다. */
    void copyBytes(std::uint8_t *destination,
                   const std::uint8_t *source,
                   std::size_t length) noexcept
    {
        for (std::size_t index = 0U; index < length; ++index)
        {
            destination[index] = source[index];
        }
    }

    /** @brief 전체 AD 구조를 검증하며 type과 16-bit prefix가 일치하는 첫 field를 찾습니다. */
    nucode::ble::BLEBeaconCodecError findAdvertisingField(
        const std::uint8_t *advertising,
        std::size_t length,
        std::uint8_t type,
        std::uint16_t prefix,
        AdvertisingField &field) noexcept
    {
        if (advertising == nullptr && length != 0U)
        {
            return nucode::ble::BLEBeaconCodecError::invalid_argument;
        }

        std::size_t offset = 0U;
        while (offset < length)
        {
            const std::size_t field_length = advertising[offset];
            if (field_length == 0U)
            {
                for (std::size_t index = offset + 1U; index < length; ++index)
                {
                    if (advertising[index] != 0U)
                    {
                        return nucode::ble::BLEBeaconCodecError::malformed_advertising;
                    }
                }
                break;
            }
            if (field_length > length - offset - 1U)
            {
                return nucode::ble::BLEBeaconCodecError::malformed_advertising;
            }

            const std::uint8_t field_type = advertising[offset + 1U];
            const std::size_t data_length = field_length - 1U;
            const std::uint8_t *data = advertising + offset + 2U;
            if (field_type == type)
            {
                field.saw_type = true;
                if (data_length >= 2U && data[0] == static_cast<std::uint8_t>(prefix) &&
                    data[1] == static_cast<std::uint8_t>(prefix >> 8U) &&
                    field.data == nullptr)
                {
                    field.data = data + 2U;
                    field.length = data_length - 2U;
                }
            }
            offset += field_length + 1U;
        }

        if (field.data == nullptr)
        {
            return field.saw_type ? nucode::ble::BLEBeaconCodecError::wrong_uuid
                                  : nucode::ble::BLEBeaconCodecError::field_not_found;
        }
        return nucode::ble::BLEBeaconCodecError::none;
    }

} // namespace

namespace nucode::ble
{

    BLEBeaconCodecError BLEBeaconCodec::encodeIBeacon(
        const BLEIBeaconFrame &frame,
        std::uint8_t *output,
        std::size_t capacity,
        std::size_t &length) noexcept
    {
        length = 0U;
        if (output == nullptr)
        {
            return BLEBeaconCodecError::invalid_argument;
        }
        if (capacity < i_beacon_manufacturer_data_length)
        {
            return BLEBeaconCodecError::output_too_small;
        }

        output[0] = 0x02U;
        output[1] = 0x15U;
        copyBytes(output + 2U, frame.uuid, sizeof(frame.uuid));
        output[18] = static_cast<std::uint8_t>(frame.major >> 8U);
        output[19] = static_cast<std::uint8_t>(frame.major);
        output[20] = static_cast<std::uint8_t>(frame.minor >> 8U);
        output[21] = static_cast<std::uint8_t>(frame.minor);
        output[22] = static_cast<std::uint8_t>(frame.measured_power_dbm);
        length = i_beacon_manufacturer_data_length;
        return BLEBeaconCodecError::none;
    }

    BLEBeaconCodecError BLEBeaconCodec::decodeIBeaconManufacturerData(
        const std::uint8_t *data,
        std::size_t length,
        BLEIBeaconFrame &frame) noexcept
    {
        if (data == nullptr)
        {
            return BLEBeaconCodecError::invalid_argument;
        }
        if (length != i_beacon_manufacturer_data_length)
        {
            return BLEBeaconCodecError::invalid_value;
        }
        if (data[0] != 0x02U || data[1] != 0x15U)
        {
            return BLEBeaconCodecError::unsupported_frame;
        }

        BLEIBeaconFrame decoded;
        copyBytes(decoded.uuid, data + 2U, sizeof(decoded.uuid));
        decoded.major = static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(data[18]) << 8U | data[19]);
        decoded.minor = static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(data[20]) << 8U | data[21]);
        decoded.measured_power_dbm = static_cast<std::int8_t>(data[22]);
        frame = decoded;
        return BLEBeaconCodecError::none;
    }

    BLEBeaconCodecError BLEBeaconCodec::decodeIBeaconAdvertisement(
        const std::uint8_t *advertising,
        std::size_t length,
        BLEIBeaconFrame &frame) noexcept
    {
        AdvertisingField field;
        BLEBeaconCodecError result = findAdvertisingField(
            advertising, length, manufacturer_data_type, i_beacon_company_id, field);
        if (result == BLEBeaconCodecError::wrong_uuid)
        {
            return BLEBeaconCodecError::wrong_company;
        }
        if (result != BLEBeaconCodecError::none)
        {
            return result;
        }
        return decodeIBeaconManufacturerData(field.data, field.length, frame);
    }

    BLEBeaconCodecError BLEBeaconCodec::encodeEddystoneUid(
        const BLEEddystoneUidFrame &frame,
        std::uint8_t *output,
        std::size_t capacity,
        std::size_t &length) noexcept
    {
        length = 0U;
        if (output == nullptr)
        {
            return BLEBeaconCodecError::invalid_argument;
        }
        if (capacity < eddystone_uid_service_data_length)
        {
            return BLEBeaconCodecError::output_too_small;
        }
        if (frame.tx_power_at_zero_meters_dbm < -100 ||
            frame.tx_power_at_zero_meters_dbm > 20)
        {
            return BLEBeaconCodecError::invalid_value;
        }

        output[0] = 0x00U;
        output[1] = static_cast<std::uint8_t>(frame.tx_power_at_zero_meters_dbm);
        copyBytes(output + 2U, frame.namespace_id, sizeof(frame.namespace_id));
        copyBytes(output + 12U, frame.instance_id, sizeof(frame.instance_id));
        output[18] = 0x00U;
        output[19] = 0x00U;
        length = eddystone_uid_service_data_length;
        return BLEBeaconCodecError::none;
    }

    BLEBeaconCodecError BLEBeaconCodec::decodeEddystoneUidServiceData(
        const std::uint8_t *data,
        std::size_t length,
        BLEEddystoneUidFrame &frame) noexcept
    {
        if (data == nullptr)
        {
            return BLEBeaconCodecError::invalid_argument;
        }
        if (length != eddystone_uid_service_data_length)
        {
            return BLEBeaconCodecError::invalid_value;
        }
        if (data[0] != 0x00U)
        {
            return BLEBeaconCodecError::unsupported_frame;
        }
        const std::int8_t tx_power = static_cast<std::int8_t>(data[1]);
        if (tx_power < -100 || tx_power > 20)
        {
            return BLEBeaconCodecError::invalid_value;
        }
        if (data[18] != 0x00U || data[19] != 0x00U)
        {
            return BLEBeaconCodecError::reserved_bits;
        }

        BLEEddystoneUidFrame decoded;
        decoded.tx_power_at_zero_meters_dbm = tx_power;
        copyBytes(decoded.namespace_id, data + 2U, sizeof(decoded.namespace_id));
        copyBytes(decoded.instance_id, data + 12U, sizeof(decoded.instance_id));
        frame = decoded;
        return BLEBeaconCodecError::none;
    }

    BLEBeaconCodecError BLEBeaconCodec::decodeEddystoneUidAdvertisement(
        const std::uint8_t *advertising,
        std::size_t length,
        BLEEddystoneUidFrame &frame) noexcept
    {
        AdvertisingField field;
        const BLEBeaconCodecError result = findAdvertisingField(
            advertising, length, service_data_uuid16_type, eddystone_service_uuid, field);
        if (result != BLEBeaconCodecError::none)
        {
            return result;
        }
        return decodeEddystoneUidServiceData(field.data, field.length, frame);
    }

    BLEBeaconCodecError BLEBeaconCodec::encodeBTHomeSensor(
        const BLEBTHomeSensorFrame &frame,
        std::uint8_t *output,
        std::size_t capacity,
        std::size_t &length) noexcept
    {
        length = 0U;
        if (output == nullptr)
        {
            return BLEBeaconCodecError::invalid_argument;
        }
        if (capacity < bthome_sensor_service_data_length)
        {
            return BLEBeaconCodecError::output_too_small;
        }
        if (frame.humidity_centi_percent > 10000U)
        {
            return BLEBeaconCodecError::invalid_value;
        }

        const std::uint16_t temperature =
            static_cast<std::uint16_t>(frame.temperature_centi_celsius);
        output[0] = static_cast<std::uint8_t>(0x40U | (frame.trigger_based ? 0x04U : 0x00U));
        output[1] = 0x00U;
        output[2] = frame.packet_id;
        output[3] = 0x02U;
        output[4] = static_cast<std::uint8_t>(temperature);
        output[5] = static_cast<std::uint8_t>(temperature >> 8U);
        output[6] = 0x03U;
        output[7] = static_cast<std::uint8_t>(frame.humidity_centi_percent);
        output[8] = static_cast<std::uint8_t>(frame.humidity_centi_percent >> 8U);
        length = bthome_sensor_service_data_length;
        return BLEBeaconCodecError::none;
    }

    BLEBeaconCodecError BLEBeaconCodec::decodeBTHomeSensorServiceData(
        const std::uint8_t *data,
        std::size_t length,
        BLEBTHomeSensorFrame &frame) noexcept
    {
        if (data == nullptr)
        {
            return BLEBeaconCodecError::invalid_argument;
        }
        if (length != bthome_sensor_service_data_length)
        {
            return BLEBeaconCodecError::invalid_value;
        }
        if ((data[0] & 0x01U) != 0U)
        {
            return BLEBeaconCodecError::encrypted_payload;
        }
        if ((data[0] & 0xe0U) != 0x40U)
        {
            return BLEBeaconCodecError::unsupported_version;
        }
        if ((data[0] & 0x1aU) != 0U)
        {
            return BLEBeaconCodecError::reserved_bits;
        }
        if (data[1] != 0x00U || data[3] != 0x02U || data[6] != 0x03U)
        {
            return BLEBeaconCodecError::unsupported_frame;
        }

        const std::uint16_t humidity = static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(data[8]) << 8U | data[7]);
        if (humidity > 10000U)
        {
            return BLEBeaconCodecError::invalid_value;
        }

        BLEBTHomeSensorFrame decoded;
        decoded.trigger_based = (data[0] & 0x04U) != 0U;
        decoded.packet_id = data[2];
        decoded.temperature_centi_celsius = static_cast<std::int16_t>(
            static_cast<std::uint16_t>(data[5]) << 8U | data[4]);
        decoded.humidity_centi_percent = humidity;
        frame = decoded;
        return BLEBeaconCodecError::none;
    }

    BLEBeaconCodecError BLEBeaconCodec::decodeBTHomeSensorAdvertisement(
        const std::uint8_t *advertising,
        std::size_t length,
        BLEBTHomeSensorFrame &frame) noexcept
    {
        AdvertisingField field;
        const BLEBeaconCodecError result = findAdvertisingField(
            advertising, length, service_data_uuid16_type, bthome_service_uuid, field);
        if (result != BLEBeaconCodecError::none)
        {
            return result;
        }
        return decodeBTHomeSensorServiceData(field.data, field.length, frame);
    }

} // namespace nucode::ble
