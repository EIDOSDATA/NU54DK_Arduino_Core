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
}

#endif
