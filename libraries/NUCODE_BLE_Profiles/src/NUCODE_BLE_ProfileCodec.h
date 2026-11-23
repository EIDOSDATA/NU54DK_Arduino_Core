/**
 * @file NUCODE_BLE_ProfileCodec.h
 * @brief 표준 GATT characteristic의 고정 크기 wire 형식을 선언합니다.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_BLE_PROFILE_CODEC_H_
#define NUCODE_BLE_PROFILE_CODEC_H_

#include <cstddef>
#include <cstdint>

namespace nucode::ble::profiles
{
    /** @brief 제공하는 GATT 서비스의 표준 16-bit UUID입니다. */
    enum class Kind : std::uint16_t
    {
        current_time = 0x1805U,
        thermometer = 0x1809U,
        alert = 0x1811U,
        running = 0x1814U,
        cycling = 0x1816U,
        bond_management = 0x181eU,
        glucose = 0x181fU,
        elapsed_time = 0x183fU,
    };

    /** @brief heap 없이 전송 가능한 bounded characteristic 값입니다. */
    struct Packet
    {
        static constexpr std::size_t capacity = 32U;
        std::uint8_t data[capacity] = {};
        std::size_t length = 0U;
    };

    /** @brief Bluetooth Date Time입니다. year/month/day의 0은 알려지지 않음을 뜻합니다. */
    struct DateTime
    {
        std::uint16_t year = 2026U;
        std::uint8_t month = 1U;
        std::uint8_t day = 1U;
        std::uint8_t hour = 0U;
        std::uint8_t minute = 0U;
        std::uint8_t second = 0U;
    };

    /** @brief 1/256초와 조정 원인을 포함하는 CTS 값입니다. */
    struct CurrentTime
    {
        DateTime date;
        std::uint8_t weekday = 0U;
        std::uint8_t fractions256 = 0U;
        std::uint8_t adjust_reason = 0U;
    };

    /** @brief IEEE-11073 FLOAT의 24-bit signed mantissa와 10진 exponent입니다. */
    struct Temperature
    {
        std::int32_t mantissa = 2350;
        std::int8_t exponent = -2;
        bool fahrenheit = false;
        bool has_timestamp = false;
        DateTime timestamp;
        bool has_type = false;
        std::uint8_t type = 2U;
    };

    /** @brief CSC event time은 1/1024초 단위의 wrap-around counter입니다. */
    struct CyclingMeasurement
    {
        bool has_wheel = true;
        bool has_crank = true;
        std::uint32_t wheel_revolutions = 0U;
        std::uint16_t wheel_event1024 = 0U;
        std::uint16_t crank_revolutions = 0U;
        std::uint16_t crank_event1024 = 0U;
    };

    /** @brief RSC 속도는 1/256 m/s, 보폭은 cm, 누적 거리는 0.1 m입니다. */
    struct RunningMeasurement
    {
        std::uint16_t speed256 = 0U;
        std::uint8_t cadence = 0U;
        bool running = false;
        bool has_stride = false;
        std::uint16_t stride_cm = 0U;
        bool has_distance = false;
        std::uint32_t distance_decimetres = 0U;
    };

    /** @brief CGM의 최소 6-byte 측정값입니다. SFLOAT 농도 단위는 mg/dL입니다. */
    struct GlucoseMeasurement
    {
        std::int16_t mantissa = 100;
        std::int8_t exponent = 0;
        std::uint16_t time_offset_minutes = 0U;
    };

    /** @brief ETS의 48-bit 시간값과 clock 상태입니다. epoch는 2000-01-01입니다. */
    struct ElapsedTime
    {
        std::uint8_t flags = 0x22U;
        std::uint64_t counter = 0U;
        std::uint8_t source = 7U;
        std::int8_t timezone_quarters = 0;
        std::uint8_t clock_status = 1U;
        std::uint8_t clock_capabilities = 0U;
    };

    /** @brief ANS New Alert입니다. UTF-8 text는 최대 18 octet이며 null은 wire에 넣지 않습니다. */
    struct Alert
    {
        std::uint8_t category = 0U;
        std::uint8_t count = 1U;
        char text[19] = {};
    };

    /** @brief 알려진 값과 필드 경계를 엄격히 검사하는 portable codec입니다. */
    class Codec final
    {
      public:
        [[nodiscard]] static bool encode(const CurrentTime &value, Packet &output) noexcept;
        [[nodiscard]] static bool encode(const Temperature &value, Packet &output) noexcept;
        [[nodiscard]] static bool encode(const CyclingMeasurement &value, Packet &output) noexcept;
        [[nodiscard]] static bool encode(const RunningMeasurement &value, Packet &output) noexcept;
        [[nodiscard]] static bool encode(const GlucoseMeasurement &value, Packet &output) noexcept;
        [[nodiscard]] static bool encode(const ElapsedTime &value, Packet &output) noexcept;
        [[nodiscard]] static bool encode(const Alert &value, Packet &output) noexcept;
        [[nodiscard]] static bool decode(const std::uint8_t *data, std::size_t length,
                                         CurrentTime &output) noexcept;
        [[nodiscard]] static bool decode(const std::uint8_t *data, std::size_t length,
                                         Temperature &output) noexcept;
        [[nodiscard]] static bool decode(const std::uint8_t *data, std::size_t length,
                                         CyclingMeasurement &output) noexcept;
        [[nodiscard]] static bool decode(const std::uint8_t *data, std::size_t length,
                                         RunningMeasurement &output) noexcept;
        [[nodiscard]] static bool decode(const std::uint8_t *data, std::size_t length,
                                         GlucoseMeasurement &output) noexcept;
        [[nodiscard]] static bool decode(const std::uint8_t *data, std::size_t length,
                                         ElapsedTime &output) noexcept;
        [[nodiscard]] static bool decode(const std::uint8_t *data, std::size_t length,
                                         Alert &output) noexcept;
        /** @brief 서비스별 measurement 길이·flag·필드 검사를 수행합니다. */
        [[nodiscard]] static bool valid(Kind kind, const std::uint8_t *data,
                                        std::size_t length) noexcept;
        [[nodiscard]] static std::uint16_t measurementUuid(Kind kind) noexcept;
        [[nodiscard]] static bool usesIndications(Kind kind) noexcept;
    };

    /** @brief ANS 한 link의 category mask를 소유하며 다른 link와 공유하지 않습니다. */
    class AlertControl final
    {
      public:
        /** @brief command 0..5와 category 0..9/0xff를 적용합니다. */
        [[nodiscard]] bool apply(const std::uint8_t *data, std::size_t length) noexcept;
        [[nodiscard]] bool newEnabled(std::uint8_t category) const noexcept;
        [[nodiscard]] bool unreadEnabled(std::uint8_t category) const noexcept;
        [[nodiscard]] std::uint16_t takeImmediateNew() noexcept;
        [[nodiscard]] std::uint16_t takeImmediateUnread() noexcept;
        void reset() noexcept;

      private:
        std::uint16_t new_mask_ = 0U;
        std::uint16_t unread_mask_ = 0U;
        std::uint16_t immediate_new_ = 0U;
        std::uint16_t immediate_unread_ = 0U;
    };
} // namespace nucode::ble::profiles
#endif
