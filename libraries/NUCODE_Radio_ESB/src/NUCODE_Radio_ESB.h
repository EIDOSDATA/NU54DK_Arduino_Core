/**
 * @file NUCODE_Radio_ESB.h
 * @brief NU54DK 단독 Enhanced ShockBurst 검증용 공개 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_RADIO_ESB_H
#define NUCODE_RADIO_ESB_H

#include <cstddef>
#include <cstdint>

namespace nucode::esb
{
    /** @brief ESB 단독 radio 역할입니다. */
    enum class Role : std::uint8_t
    {
        primary_transmitter,
        primary_receiver,
    };

    /** @brief 검증 가능한 ESB 전송률입니다. */
    enum class Bitrate : std::uint8_t
    {
        mbps1,
        mbps2,
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

    /** @brief channel, 전송률, hardware ACK 재전송 경계입니다. */
    struct Configuration
    {
        std::uint16_t retransmit_delay_us = 600U;
        std::uint16_t stop_timeout_ms = 100U;
        std::uint8_t channel = 40U;
        std::uint8_t retransmit_count = 3U;
        std::uint8_t pipe = 0U;
        Bitrate bitrate = Bitrate::mbps2;
    };

    /** @brief 수신 packet의 sequence/hash 검증 결과입니다. */
    struct Packet
    {
        static constexpr std::size_t payload_capacity = 20U;

        std::uint32_t sequence = 0U;
        std::size_t length = 0U;
        std::uint8_t pipe = 0U;
        bool duplicate = false;
        bool hash_valid = false;
        std::uint8_t payload[payload_capacity]{};
    };

    /** @brief ESB ACK, 재전송, 수신, 중복, 오류 통계입니다. */
    struct Statistics
    {
        std::uint32_t tx_requested = 0U;
        std::uint32_t tx_acknowledged = 0U;
        std::uint32_t tx_failed = 0U;
        std::uint32_t tx_attempts = 0U;
        std::uint32_t rx_received = 0U;
        std::uint32_t rx_duplicates = 0U;
        std::uint32_t rx_hash_failures = 0U;
        std::uint32_t rx_dropped = 0U;
        std::uint32_t timeslot_failures = 0U;
        std::uint32_t stops = 0U;
    };

    /** @brief ESB가 RADIO와 ACK/retry buffer를 단독 소유하는 adapter입니다. */
    class EsbRadio final
    {
      public:
        /** @brief PTX 또는 PRX 역할로 ESB를 초기화합니다. */
        [[nodiscard]] bool begin(Role role, const Configuration &configuration = {}) noexcept;

        /** @brief sequence와 hash를 포함한 ACK 요청 payload를 queue에 넣습니다. */
        [[nodiscard]] bool send(std::uint32_t sequence,
                                const std::uint8_t *payload,
                                std::size_t length) noexcept;

        /** @brief 복사 완료된 수신 payload가 있는지 반환합니다. */
        [[nodiscard]] bool available() const noexcept;

        /** @brief 다음 수신 payload를 반환합니다. */
        [[nodiscard]] bool read(Packet &packet) noexcept;

        /** @brief 진행 통신과 FIFO를 취소하고 PRX이면 수신을 다시 시작합니다. */
        [[nodiscard]] bool cancel() noexcept;

        /** @brief 유한 시간 안에 ESB를 suspend/disable하고 FIFO를 반환합니다. */
        [[nodiscard]] bool stop() noexcept;

        /** @brief PTX 전송이 완료되지 않았는지 반환합니다. */
        [[nodiscard]] bool busy() const noexcept;

        /** @brief callback 통계의 일관된 snapshot을 반환합니다. */
        [[nodiscard]] Statistics statistics() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 ESB 음수 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;
    };
}

/** @brief NU54DK의 단일 ESB radio 객체입니다. */
extern nucode::esb::EsbRadio NUCODEEsb;

#endif
