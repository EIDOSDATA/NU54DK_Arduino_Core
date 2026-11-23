/**
 * @file m33_beacon_codec_main.cpp
 * @brief M33 Beacon payload 코덱의 알려진 byte와 음성 경계를 실행합니다.
 */

#include "NUCODE_BLE_Beacon.h"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace
{

    using nucode::ble::BLEBTHomeSensorFrame;
    using nucode::ble::BLEBeaconCodec;
    using nucode::ble::BLEBeaconCodecError;
    using nucode::ble::BLEEddystoneUidFrame;
    using nucode::ble::BLEIBeaconFrame;

    /** @brief 조건이 거짓이면 호출 지점의 줄 번호를 반환합니다. */
    int require(bool condition, int line) noexcept
    {
        return condition ? 0 : line;
    }

#define REQUIRE(condition)                  \
    do                                      \
    {                                       \
        const int result = require((condition), __LINE__); \
        if (result != 0)                    \
        {                                   \
            return result;                  \
        }                                   \
    } while (false)

    /** @brief iBeacon big-endian 필드와 Apple manufacturer AD 구조를 검증합니다. */
    int iBeaconScenario() noexcept
    {
        BLEIBeaconFrame input;
        for (std::size_t index = 0U; index < sizeof(input.uuid); ++index)
        {
            input.uuid[index] = static_cast<std::uint8_t>(index);
        }
        input.major = 0x1234U;
        input.minor = 0xabcdU;
        input.measured_power_dbm = -59;

        std::uint8_t encoded[BLEBeaconCodec::i_beacon_manufacturer_data_length] = {};
        std::size_t length = 99U;
        REQUIRE(BLEBeaconCodec::encodeIBeacon(input, encoded, sizeof(encoded), length) ==
                BLEBeaconCodecError::none);
        REQUIRE(length == sizeof(encoded));
        REQUIRE(encoded[0] == 0x02U && encoded[1] == 0x15U);
        REQUIRE(encoded[18] == 0x12U && encoded[19] == 0x34U);
        REQUIRE(encoded[20] == 0xabU && encoded[21] == 0xcdU);
        REQUIRE(encoded[22] == 0xc5U);

        std::uint8_t advertising[30] = {0x02U, 0x01U, 0x06U, 0x1aU, 0xffU, 0x4cU, 0x00U};
        std::memcpy(advertising + 7U, encoded, sizeof(encoded));
        BLEIBeaconFrame decoded;
        REQUIRE(BLEBeaconCodec::decodeIBeaconAdvertisement(
                    advertising, sizeof(advertising), decoded) == BLEBeaconCodecError::none);
        REQUIRE(std::memcmp(input.uuid, decoded.uuid, sizeof(input.uuid)) == 0);
        REQUIRE(decoded.major == input.major && decoded.minor == input.minor);
        REQUIRE(decoded.measured_power_dbm == input.measured_power_dbm);

        std::uint8_t short_output[22] = {};
        length = 77U;
        REQUIRE(BLEBeaconCodec::encodeIBeacon(
                    input, short_output, sizeof(short_output), length) ==
                BLEBeaconCodecError::output_too_small);
        REQUIRE(length == 0U);

        std::uint8_t wrong_company[] = {0x04U, 0xffU, 0x59U, 0x00U, 0x00U};
        REQUIRE(BLEBeaconCodec::decodeIBeaconAdvertisement(
                    wrong_company, sizeof(wrong_company), decoded) ==
                BLEBeaconCodecError::wrong_company);
        encoded[0] = 0x03U;
        REQUIRE(BLEBeaconCodec::decodeIBeaconManufacturerData(
                    encoded, sizeof(encoded), decoded) ==
                BLEBeaconCodecError::unsupported_frame);
        return 0;
    }

    /** @brief Eddystone UID 고정 길이, 범위와 RFU byte를 검증합니다. */
    int eddystoneScenario() noexcept
    {
        BLEEddystoneUidFrame input;
        input.tx_power_at_zero_meters_dbm = -20;
        for (std::size_t index = 0U; index < sizeof(input.namespace_id); ++index)
        {
            input.namespace_id[index] = static_cast<std::uint8_t>(0xa0U + index);
        }
        for (std::size_t index = 0U; index < sizeof(input.instance_id); ++index)
        {
            input.instance_id[index] = static_cast<std::uint8_t>(0xb0U + index);
        }

        std::uint8_t encoded[BLEBeaconCodec::eddystone_uid_service_data_length] = {};
        std::size_t length = 0U;
        REQUIRE(BLEBeaconCodec::encodeEddystoneUid(input, encoded, sizeof(encoded), length) ==
                BLEBeaconCodecError::none);
        REQUIRE(length == sizeof(encoded));
        REQUIRE(encoded[0] == 0x00U && encoded[1] == 0xecU);
        REQUIRE(encoded[18] == 0x00U && encoded[19] == 0x00U);

        std::uint8_t advertising[27] = {0x02U, 0x01U, 0x06U, 0x17U, 0x16U, 0xaaU, 0xfeU};
        std::memcpy(advertising + 7U, encoded, sizeof(encoded));
        BLEEddystoneUidFrame decoded;
        REQUIRE(BLEBeaconCodec::decodeEddystoneUidAdvertisement(
                    advertising, sizeof(advertising), decoded) == BLEBeaconCodecError::none);
        REQUIRE(decoded.tx_power_at_zero_meters_dbm == input.tx_power_at_zero_meters_dbm);
        REQUIRE(std::memcmp(input.namespace_id, decoded.namespace_id,
                            sizeof(input.namespace_id)) == 0);
        REQUIRE(std::memcmp(input.instance_id, decoded.instance_id,
                            sizeof(input.instance_id)) == 0);

        input.tx_power_at_zero_meters_dbm = 21;
        REQUIRE(BLEBeaconCodec::encodeEddystoneUid(input, encoded, sizeof(encoded), length) ==
                BLEBeaconCodecError::invalid_value);
        encoded[0] = 0x10U;
        REQUIRE(BLEBeaconCodec::decodeEddystoneUidServiceData(
                    encoded, sizeof(encoded), decoded) ==
                BLEBeaconCodecError::unsupported_frame);
        encoded[0] = 0x00U;
        encoded[18] = 0x01U;
        REQUIRE(BLEBeaconCodec::decodeEddystoneUidServiceData(
                    encoded, sizeof(encoded), decoded) ==
                BLEBeaconCodecError::reserved_bits);
        return 0;
    }

    /** @brief BTHome v2 little-endian 센서와 device-info 음성 경계를 검증합니다. */
    int bthomeScenario() noexcept
    {
        BLEBTHomeSensorFrame input;
        input.packet_id = 9U;
        input.temperature_centi_celsius = 2500;
        input.humidity_centi_percent = 5055U;
        input.trigger_based = true;

        std::uint8_t encoded[BLEBeaconCodec::bthome_sensor_service_data_length] = {};
        std::size_t length = 0U;
        REQUIRE(BLEBeaconCodec::encodeBTHomeSensor(input, encoded, sizeof(encoded), length) ==
                BLEBeaconCodecError::none);
        const std::uint8_t expected[] = {
            0x44U, 0x00U, 0x09U, 0x02U, 0xc4U, 0x09U, 0x03U, 0xbfU, 0x13U,
        };
        REQUIRE(length == sizeof(expected));
        REQUIRE(std::memcmp(encoded, expected, sizeof(expected)) == 0);

        std::uint8_t advertising[16] = {0x02U, 0x01U, 0x06U, 0x0cU, 0x16U, 0xd2U, 0xfcU};
        std::memcpy(advertising + 7U, encoded, sizeof(encoded));
        BLEBTHomeSensorFrame decoded;
        REQUIRE(BLEBeaconCodec::decodeBTHomeSensorAdvertisement(
                    advertising, sizeof(advertising), decoded) == BLEBeaconCodecError::none);
        REQUIRE(decoded.packet_id == input.packet_id);
        REQUIRE(decoded.temperature_centi_celsius == input.temperature_centi_celsius);
        REQUIRE(decoded.humidity_centi_percent == input.humidity_centi_percent);
        REQUIRE(decoded.trigger_based);

        encoded[0] = 0x45U;
        REQUIRE(BLEBeaconCodec::decodeBTHomeSensorServiceData(
                    encoded, sizeof(encoded), decoded) ==
                BLEBeaconCodecError::encrypted_payload);
        encoded[0] = 0x60U;
        REQUIRE(BLEBeaconCodec::decodeBTHomeSensorServiceData(
                    encoded, sizeof(encoded), decoded) ==
                BLEBeaconCodecError::unsupported_version);
        encoded[0] = 0x42U;
        REQUIRE(BLEBeaconCodec::decodeBTHomeSensorServiceData(
                    encoded, sizeof(encoded), decoded) ==
                BLEBeaconCodecError::reserved_bits);
        encoded[0] = 0x40U;
        encoded[3] = 0x03U;
        REQUIRE(BLEBeaconCodec::decodeBTHomeSensorServiceData(
                    encoded, sizeof(encoded), decoded) ==
                BLEBeaconCodecError::unsupported_frame);

        input.humidity_centi_percent = 10001U;
        REQUIRE(BLEBeaconCodec::encodeBTHomeSensor(input, encoded, sizeof(encoded), length) ==
                BLEBeaconCodecError::invalid_value);
        return 0;
    }

    /** @brief AD length, 종료 padding과 UUID 선택 경계를 검증합니다. */
    int malformedScenario() noexcept
    {
        BLEIBeaconFrame i_beacon;
        const std::uint8_t truncated[] = {0x05U, 0xffU, 0x4cU};
        REQUIRE(BLEBeaconCodec::decodeIBeaconAdvertisement(
                    truncated, sizeof(truncated), i_beacon) ==
                BLEBeaconCodecError::malformed_advertising);

        BLEBTHomeSensorFrame bthome;
        const std::uint8_t nonzero_after_padding[] = {0x00U, 0x01U};
        REQUIRE(BLEBeaconCodec::decodeBTHomeSensorAdvertisement(
                    nonzero_after_padding, sizeof(nonzero_after_padding), bthome) ==
                BLEBeaconCodecError::malformed_advertising);

        BLEEddystoneUidFrame eddystone;
        const std::uint8_t wrong_uuid[] = {0x04U, 0x16U, 0xd2U, 0xfcU, 0x40U};
        REQUIRE(BLEBeaconCodec::decodeEddystoneUidAdvertisement(
                    wrong_uuid, sizeof(wrong_uuid), eddystone) ==
                BLEBeaconCodecError::wrong_uuid);
        const std::uint8_t flags_only[] = {0x02U, 0x01U, 0x06U};
        REQUIRE(BLEBeaconCodec::decodeEddystoneUidAdvertisement(
                    flags_only, sizeof(flags_only), eddystone) ==
                BLEBeaconCodecError::field_not_found);
        return 0;
    }

} // namespace

int main(int argument_count, char **arguments)
{
    if (argument_count != 2)
    {
        return 2;
    }
    if (std::strcmp(arguments[1], "ibeacon") == 0)
    {
        return iBeaconScenario();
    }
    if (std::strcmp(arguments[1], "eddystone") == 0)
    {
        return eddystoneScenario();
    }
    if (std::strcmp(arguments[1], "bthome") == 0)
    {
        return bthomeScenario();
    }
    if (std::strcmp(arguments[1], "malformed") == 0)
    {
        return malformedScenario();
    }
    return 3;
}
