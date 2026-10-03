/**
 * @file NUCODE_Radio_IEEE802154.h
 * @brief NU54DK 단독 IEEE 802.15.4 검증용 공개 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_RADIO_IEEE802154_H
#define NUCODE_RADIO_IEEE802154_H

#include <cstddef>
#include <cstdint>

namespace nucode::radio154
{
    /** @brief 단독 radio 역할입니다. */
    enum class Role : std::uint8_t
    {
        transmitter,
        receiver,
    };

    /** @brief 공개 오류 분류입니다. */
    enum class Error : std::uint8_t
    {
        none,
        not_started,
        invalid_argument,
        busy,
        queue_full,
        driver_error,
        stop_timeout,
    };

    /** @brief channel, 주소, 재전송과 정지 상한입니다. */
    struct Configuration
    {
        std::uint16_t pan_id = 0x4E55U;
        std::uint16_t local_address = 0x0001U;
        std::uint16_t peer_address = 0x0002U;
        std::uint16_t retry_delay_ms = 4U;
        std::uint16_t stop_timeout_ms = 100U;
        std::uint8_t channel = 20U;
        std::uint8_t retry_count = 3U;
        std::int8_t tx_power_dbm = 0;
        bool clear_channel_assessment = true;
    };

    /** @brief 수신 packet의 검증 결과와 복사된 payload입니다. */
    struct Packet
    {
        static constexpr std::size_t payload_capacity = 80U;

        std::uint32_t sequence = 0U;
        std::size_t length = 0U;
        std::int8_t rssi_dbm = 0;
        std::uint8_t link_quality = 0U;
        bool duplicate = false;
        bool hash_valid = false;
        std::uint8_t payload[payload_capacity]{};
    };

    /** @brief 송수신, ACK, 손실, 중복과 정지 통계입니다. */
    struct Statistics
    {
        std::uint32_t tx_requested = 0U;
        std::uint32_t tx_acknowledged = 0U;
        std::uint32_t tx_failed = 0U;
        std::uint32_t tx_retried = 0U;
        std::uint32_t rx_received = 0U;
        std::uint32_t rx_duplicates = 0U;
        std::uint32_t rx_hash_failures = 0U;
        std::uint32_t rx_dropped = 0U;
        std::uint32_t stops = 0U;
    };

    /** @brief nRF 802.15.4 driver를 단독 소유하는 bounded adapter입니다. */
    class Radio154 final
    {
      public:
        /** @brief 단독 RADIO 소유권과 지정 역할을 시작합니다. */
        [[nodiscard]] bool begin(Role role, const Configuration &configuration = {}) noexcept;

        /** @brief sequence와 hash가 결합된 ACK 요청 frame을 비동기로 전송합니다. */
        [[nodiscard]] bool send(std::uint32_t sequence,
                                const std::uint8_t *payload,
                                std::size_t length) noexcept;

        /** @brief 복사 완료된 수신 packet이 있는지 반환합니다. */
        [[nodiscard]] bool available() const noexcept;

        /** @brief 다음 수신 packet을 사용자 buffer로 이동합니다. */
        [[nodiscard]] bool read(Packet &packet) noexcept;

        /** @brief 예약된 재전송을 취소하고 역할에 맞는 idle 상태로 복구합니다. */
        [[nodiscard]] bool cancel() noexcept;

        /** @brief 유한 시간 안에 RADIO를 sleep/deinit하고 buffer를 반환합니다. */
        [[nodiscard]] bool stop() noexcept;

        /** @brief 현재 전송이 완료되지 않았는지 반환합니다. */
        [[nodiscard]] bool busy() const noexcept;

        /** @brief IRQ 문맥에서 갱신된 통계를 일관된 snapshot으로 반환합니다. */
        [[nodiscard]] Statistics statistics() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 driver 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;
    };
}

/** @brief NU54DK의 단일 IEEE 802.15.4 radio 객체입니다. */
extern nucode::radio154::Radio154 NUCODERadio154;

#endif
