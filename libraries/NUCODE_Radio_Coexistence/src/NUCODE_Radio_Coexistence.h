/**
 * @file NUCODE_Radio_Coexistence.h
 * @brief MPSL 공존 조합의 protocol별 bounded 관측 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_RADIO_COEXISTENCE_H
#define NUCODE_RADIO_COEXISTENCE_H

#include <cstddef>
#include <cstdint>

namespace nucode::coexistence
{
    /** @brief 공존 시험에서 구분하는 radio service입니다. */
    enum class Protocol : std::uint8_t
    {
        ble,
        mesh,
        ieee802154,
        esb,
        external_radio,
        count,
    };

    /** @brief 한 protocol의 sequence, hash, drop과 서비스 간격 snapshot입니다. */
    struct ServiceStatistics
    {
        std::uint32_t requested = 0U;
        std::uint32_t delivered = 0U;
        std::uint32_t dropped = 0U;
        std::uint32_t sequence_errors = 0U;
        std::uint32_t hash_errors = 0U;
        std::uint32_t timeslot_failures = 0U;
        std::uint32_t restart_count = 0U;
        std::uint32_t starvation_events = 0U;
        std::uint32_t maximum_service_gap_ms = 0U;
        std::uint32_t last_sequence = 0U;
        std::uint32_t last_hash = 0U;
        bool active = false;
    };

    /** @brief 공존 scheduler의 service 품질과 외부 1-wire grant를 관측합니다. */
    class CoexistenceMonitor final
    {
      public:
        /** @brief 통계를 지우고 starvation 판정 상한을 설정합니다. */
        [[nodiscard]] bool begin(std::uint32_t starvation_limit_ms = 500U) noexcept;

        /** @brief protocol service가 scheduler에 요청된 횟수를 기록합니다. */
        void recordRequested(Protocol protocol) noexcept;

        /** @brief 전달된 sequence/hash와 서비스 간격을 기록합니다. */
        void recordDelivered(Protocol protocol, std::uint32_t sequence,
                             std::uint32_t hash, bool hash_valid = true) noexcept;

        /** @brief queue 또는 scheduler에서 drop된 service 수를 기록합니다. */
        void recordDropped(Protocol protocol, std::uint32_t count = 1U) noexcept;

        /** @brief MPSL timeslot 거부 또는 실패를 기록합니다. */
        void recordTimeslotFailure(Protocol protocol) noexcept;

        /** @brief protocol 종료 뒤 성공적으로 재시작한 횟수를 기록합니다. */
        void recordRestart(Protocol protocol) noexcept;

        /** @brief protocol의 현재 활성 상태를 고정합니다. */
        void setActive(Protocol protocol, bool active) noexcept;

        /** @brief 지정 protocol의 일관된 통계 snapshot을 반환합니다. */
        [[nodiscard]] ServiceStatistics statistics(Protocol protocol) const noexcept;

        /** @brief 모든 protocol에서 hash/sequence/starvation 오류가 없는지 반환합니다. */
        [[nodiscard]] bool healthy() const noexcept;

        /** @brief profile이 제공하는 1-wire grant output과 radio event 계수를 시작합니다. */
        [[nodiscard]] bool beginOneWire() noexcept;

        /** @brief 외부 grant 입력에 연결된 local output을 허용/거부 상태로 바꿉니다. */
        [[nodiscard]] bool setExternalGrant(bool granted) noexcept;

        /** @brief 1-wire backend가 현재 image에 포함되었는지 반환합니다. */
        [[nodiscard]] bool oneWireSupported() const noexcept;

        /** @brief MPSL RADIO READY event 누적 수를 반환합니다. */
        [[nodiscard]] std::uint32_t radioEventCount() const noexcept;

        /** @brief 모든 service 상태를 비활성화하고 1-wire output을 안전 상태로 둡니다. */
        void stop() noexcept;

      private:
        static constexpr std::size_t protocol_count =
            static_cast<std::size_t>(Protocol::count);

        ServiceStatistics statistics_[protocol_count]{};
        std::uint32_t last_service_ms_[protocol_count]{};
        std::uint32_t starvation_limit_ms_ = 500U;
        bool started_ = false;
        bool one_wire_started_ = false;
    };
}

/** @brief NU54DK 공존 시험의 단일 bounded 관측 객체입니다. */
extern nucode::coexistence::CoexistenceMonitor NUCODECoexistence;

#endif
