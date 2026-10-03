/**
 * @file NUCODE_BLE_Beacon.h
 * @brief iBeacon, Eddystone UID, BTHome v2 광고 payload 코덱을 선언합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_BEACON_H_
#define NUCODE_BLE_BEACON_H_

#include <cstddef>
#include <cstdint>

namespace nucode::ble
{

    /** @brief Beacon 코덱이 반환하는 형식 검증 결과입니다. */
    enum class BLEBeaconCodecError : std::uint8_t
    {
        none,
        invalid_argument,
        output_too_small,
        field_not_found,
        malformed_advertising,
        wrong_company,
        wrong_uuid,
        unsupported_frame,
        unsupported_version,
        encrypted_payload,
        invalid_value,
        reserved_bits,
    };

    /** @brief iBeacon 식별자와 1 m 보정 송신 전력입니다. */
    struct BLEIBeaconFrame
    {
        std::uint8_t uuid[16] = {};
        std::uint16_t major = 0U;
        std::uint16_t minor = 0U;
        std::int8_t measured_power_dbm = 0;
    };

    /** @brief Eddystone UID의 namespace, instance와 0 m 보정 송신 전력입니다. */
    struct BLEEddystoneUidFrame
    {
        std::int8_t tx_power_at_zero_meters_dbm = 0;
        std::uint8_t namespace_id[10] = {};
        std::uint8_t instance_id[6] = {};
    };

    /** @brief BTHome v2 비암호화 온도·습도 센서 한 묶음입니다. */
    struct BLEBTHomeSensorFrame
    {
        std::uint8_t packet_id = 0U;
        std::int16_t temperature_centi_celsius = 0;
        std::uint16_t humidity_centi_percent = 0U;
        bool trigger_based = false;
    };

    /** @brief 고정 크기 Beacon payload를 heap 없이 인코딩하고 엄격하게 해석합니다. */
    class BLEBeaconCodec final
    {
      public:
        static constexpr std::uint16_t i_beacon_company_id = 0x004cU;
        static constexpr std::uint16_t eddystone_service_uuid = 0xfeaaU;
        static constexpr std::uint16_t bthome_service_uuid = 0xfcd2U;
        static constexpr std::size_t i_beacon_manufacturer_data_length = 23U;
        static constexpr std::size_t eddystone_uid_service_data_length = 20U;
        static constexpr std::size_t bthome_sensor_service_data_length = 9U;

        /** @brief Advertising::setManufacturerData()에 전달할 iBeacon data를 만듭니다. */
        [[nodiscard]] static BLEBeaconCodecError encodeIBeacon(
            const BLEIBeaconFrame &frame,
            std::uint8_t *output,
            std::size_t capacity,
            std::size_t &length) noexcept;

        /** @brief company ID를 제외한 iBeacon manufacturer data를 해석합니다. */
        [[nodiscard]] static BLEBeaconCodecError decodeIBeaconManufacturerData(
            const std::uint8_t *data,
            std::size_t length,
            BLEIBeaconFrame &frame) noexcept;

        /** @brief 전체 advertising payload에서 Apple iBeacon AD field를 찾아 해석합니다. */
        [[nodiscard]] static BLEBeaconCodecError decodeIBeaconAdvertisement(
            const std::uint8_t *advertising,
            std::size_t length,
            BLEIBeaconFrame &frame) noexcept;

        /** @brief Advertising::setServiceData()에 전달할 Eddystone UID data를 만듭니다. */
        [[nodiscard]] static BLEBeaconCodecError encodeEddystoneUid(
            const BLEEddystoneUidFrame &frame,
            std::uint8_t *output,
            std::size_t capacity,
            std::size_t &length) noexcept;

        /** @brief UUID를 제외한 Eddystone UID service data를 해석합니다. */
        [[nodiscard]] static BLEBeaconCodecError decodeEddystoneUidServiceData(
            const std::uint8_t *data,
            std::size_t length,
            BLEEddystoneUidFrame &frame) noexcept;

        /** @brief 전체 advertising payload에서 Eddystone UID AD field를 찾아 해석합니다. */
        [[nodiscard]] static BLEBeaconCodecError decodeEddystoneUidAdvertisement(
            const std::uint8_t *advertising,
            std::size_t length,
            BLEEddystoneUidFrame &frame) noexcept;

        /** @brief Advertising::setServiceData()에 전달할 BTHome v2 sensor data를 만듭니다. */
        [[nodiscard]] static BLEBeaconCodecError encodeBTHomeSensor(
            const BLEBTHomeSensorFrame &frame,
            std::uint8_t *output,
            std::size_t capacity,
            std::size_t &length) noexcept;

        /** @brief UUID를 제외한 BTHome v2 sensor service data를 해석합니다. */
        [[nodiscard]] static BLEBeaconCodecError decodeBTHomeSensorServiceData(
            const std::uint8_t *data,
            std::size_t length,
            BLEBTHomeSensorFrame &frame) noexcept;

        /** @brief 전체 advertising payload에서 BTHome v2 AD field를 찾아 해석합니다. */
        [[nodiscard]] static BLEBeaconCodecError decodeBTHomeSensorAdvertisement(
            const std::uint8_t *advertising,
            std::size_t length,
            BLEBTHomeSensorFrame &frame) noexcept;
    };

} // namespace nucode::ble

#endif
