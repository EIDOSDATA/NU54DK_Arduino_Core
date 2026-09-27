/**
 * @file NUCODE_BLE_ChannelSounding.h
 * @brief 연결 기반 Bluetooth Channel Sounding의 Arduino 공개 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_CHANNEL_SOUNDING_H
#define NUCODE_BLE_CHANNEL_SOUNDING_H

#include <Arduino.h>
#include <cstdint>

namespace nucode::ble
{
    class BLEConnectionHandle;
}

namespace nucode::ble::cs
{
    /** @brief 공개 Ranging Service reflector 오류 분류입니다. */
    enum class Error : std::uint8_t
    {
        none = 0U,
        invalid_argument,
        not_connected,
        already_started,
        busy,
        not_ready,
        not_started,
        unsupported,
        controller_error,
    };

    /**
     * @brief 보안 연결의 CS 절차와 Ranging Service 응답 역할을 준비합니다.
     *
     * 연결과 광고는 NUCODE_BLE Core가 소유합니다. 이 객체는 한 시점에 하나만
     * 활성화할 수 있으며 Zephyr 연결과 CS 설정은 구현 내부에 유지합니다.
     */
    class RasReflector final
    {
      public:
        RasReflector() = default;

        ~RasReflector()
        {
            end();
        }

        RasReflector(const RasReflector &) = delete;
        RasReflector &operator=(const RasReflector &) = delete;
        RasReflector(RasReflector &&) = delete;
        RasReflector &operator=(RasReflector &&) = delete;

        /** @brief 공개 연결 handle에 reflector 역할을 결합합니다. */
        Error begin(BLEConnectionHandle connection) noexcept;

        /** @brief 비동기 CS 설정 결과를 Arduino main 문맥에서 처리합니다. */
        void poll() noexcept;

        /** @brief 연결 reference와 내부 소유권을 반환합니다. */
        void end() noexcept;

        /** @brief CS 절차 파라미터 설정이 완료됐는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief peer의 CS 절차가 활성화됐는지 반환합니다. */
        [[nodiscard]] bool active() const noexcept;

        /** @brief 연결 보안 수준이 L2 이상인지 반환합니다. */
        [[nodiscard]] bool secure() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 controller·Host 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        void *state_ = nullptr;
        Error last_error_ = Error::not_connected;
        int native_code_ = 0;
    };

    /** @brief 현재 Ranging Requestor 절차의 공개 단계입니다. */
    enum class InitiatorStage : std::uint8_t
    {
        idle,
        securing,
        discovering,
        configuring,
        ready,
        ranging,
        failed,
    };

    /** @brief 같은 counter의 양쪽 RAS step data를 대조한 결과입니다. */
    struct RasReading
    {
        std::uint16_t ranging_counter = 0U;
        std::uint16_t local_steps = 0U;
        std::uint16_t peer_steps = 0U;
        std::uint16_t mode_1_steps = 0U;
        std::uint16_t mode_2_steps = 0U;
        /** @brief 유효한 양방향 mode 1 RTT 쌍의 수입니다. */
        std::uint8_t valid_rtt_samples = 0U;
        /** @brief mode 1 RTT 평균으로 계산한 미보정 거리(m)입니다. */
        float rtt_distance_meters = 0.0F;
    };

    /** @brief RAS 수명 중 결과 누락·중단 경로를 구분하는 누적 계수입니다. */
    struct RasStatistics
    {
        std::uint32_t local_busy_drops = 0U;
        std::uint32_t local_overflows = 0U;
        std::uint32_t procedure_aborts = 0U;
        std::uint32_t subevent_aborts = 0U;
        std::uint32_t ras_counter_mismatches = 0U;
        std::uint32_t ras_errors = 0U;
        std::uint32_t local_missing = 0U;
        std::uint32_t invalid_readings = 0U;
        std::uint32_t reading_queue_full = 0U;
    };

    /**
     * @brief 보안 연결에서 CS initiator와 Ranging Requestor를 실행합니다.
     *
     * BLE 연결은 NUCODE_BLE Core가 소유합니다. 이 객체는 비동기 보안·GATT·CS
     * 단계를 poll()에서 진행하고 같은 counter의 로컬·상대 step 결과를 전달합니다.
     */
    class RasInitiator final
    {
      public:
        RasInitiator() = default;

        ~RasInitiator()
        {
            end();
        }

        RasInitiator(const RasInitiator &) = delete;
        RasInitiator &operator=(const RasInitiator &) = delete;
        RasInitiator(RasInitiator &&) = delete;
        RasInitiator &operator=(RasInitiator &&) = delete;

        /** @brief 공개 BLE 연결을 받아 L2 보안과 RAS 탐색을 시작합니다. */
        Error begin(BLEConnectionHandle connection) noexcept;

        /** @brief 비동기 보안·RAS·CS 설정을 Arduino main 문맥에서 진행합니다. */
        void poll() noexcept;

        /** @brief 준비된 연결에서 CS 절차를 활성화합니다. */
        Error start() noexcept;

        /** @brief CS 절차를 중단하고 같은 연결의 재시작을 허용합니다. */
        Error stop() noexcept;

        /** @brief 연결 reference와 RAS 자원을 반환합니다. */
        void end() noexcept;

        /** @brief 현재 초기화·절차 단계를 반환합니다. */
        [[nodiscard]] InitiatorStage stage() const noexcept;

        /** @brief 완성된 raw step 대조 결과 하나를 읽습니다. */
        [[nodiscard]] bool read(RasReading &reading) noexcept;

        /** @brief 버려진 결과와 오류를 제외한 누적 결과 수를 반환합니다. */
        [[nodiscard]] std::uint32_t completed() const noexcept;

        /** @brief 현재 연결 수명에서 관찰한 누락·중단 원인 계수를 반환합니다. */
        [[nodiscard]] RasStatistics statistics() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 controller·Host 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        void *state_ = nullptr;
        InitiatorStage stage_ = InitiatorStage::idle;
        Error last_error_ = Error::not_connected;
        int native_code_ = 0;
    };
}

#endif
