/**
 * @file NUCODE_BLE_DirectionFinding.h
 * @brief 기본 안테나 AoA CTE 송신의 Arduino 공개 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_DIRECTION_FINDING_H
#define NUCODE_BLE_DIRECTION_FINDING_H

#include <Arduino.h>
#include <cstdint>

namespace nucode::ble
{
    class BLEConnectionHandle;
}

namespace nucode::ble::df
{
    /** @brief 공개 CTE 송신 오류 분류입니다. */
    enum class Error : std::uint8_t
    {
        none = 0U,
        invalid_argument,
        busy,
        not_initialized,
        already_started,
        not_started,
        controller_error,
        not_connected,
    };

    /** @brief periodic advertising 한 event의 CTE 송신 설정입니다. */
    struct BeaconConfig
    {
        std::uint8_t cte_length_8us = 20U;
        std::uint8_t cte_count = 5U;
    };

    /**
     * @brief 단일 안테나에서 connectionless AoA CTE를 송신합니다.
     *
     * 이 객체는 한 시점에 하나만 활성화할 수 있습니다. 각 함수는 Arduino main thread에서
     * 호출하며 Zephyr 광고 객체와 callback은 구현 내부에 유지됩니다.
     */
    class Beacon final
    {
      public:
        /** @brief 시작 전의 빈 송신 객체를 만듭니다. */
        Beacon() = default;

        /** @brief 남아 있는 광고 자원을 반환합니다. */
        ~Beacon()
        {
            end();
        }

        Beacon(const Beacon &) = delete;
        Beacon &operator=(const Beacon &) = delete;
        Beacon(Beacon &&) = delete;
        Beacon &operator=(Beacon &&) = delete;

        /** @brief Bluetooth와 CTE 광고 set을 한 번 준비합니다. */
        Error begin(const BeaconConfig &config = {}) noexcept;

        /** @brief CTE와 periodic·extended advertising을 시작합니다. */
        Error start() noexcept;

        /** @brief 송신을 중단하고 같은 광고 set의 재시작을 허용합니다. */
        Error stop() noexcept;

        /** @brief 광고 set을 삭제하고 singleton 소유권을 반환합니다. */
        void end() noexcept;

        /** @brief 현재 광고 실행 상태를 반환합니다. */
        [[nodiscard]] bool active() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 controller 또는 Host의 음수 오류 코드를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        void *advertisement_ = nullptr;
        Error last_error_ = Error::not_initialized;
        int native_code_ = 0;
        bool active_ = false;
    };

    /**
     * @brief 연결된 peer의 AoA CTE 요청에 기본 안테나로 응답합니다.
     *
     * 연결 수명과 광고는 NUCODE_BLE Core가 소유합니다. 이 객체는 응답 설정과
     * 활성화만 담당하며 Zephyr 연결 객체를 공개하지 않습니다.
     */
    class ConnectedResponder final
    {
      public:
        /** @brief 아직 연결되지 않은 응답 객체를 만듭니다. */
        ConnectedResponder() = default;

        /** @brief 객체가 소유한 연결 reference와 응답 설정을 반환합니다. */
        ~ConnectedResponder()
        {
            end();
        }

        ConnectedResponder(const ConnectedResponder &) = delete;
        ConnectedResponder &operator=(const ConnectedResponder &) = delete;
        ConnectedResponder(ConnectedResponder &&) = delete;
        ConnectedResponder &operator=(ConnectedResponder &&) = delete;

        /** @brief 현재 연결에서 기본 안테나 AoA CTE 응답을 준비합니다. */
        Error begin(BLEConnectionHandle connection) noexcept;

        /** @brief peer가 보낸 CTE 요청에 대한 응답을 활성화합니다. */
        Error start() noexcept;

        /** @brief 응답을 중단하고 동일 연결에서 재시작할 수 있게 합니다. */
        Error stop() noexcept;

        /** @brief 연결 reference를 반환하며 단절 뒤에도 호출할 수 있습니다. */
        void end() noexcept;

        /** @brief 현재 응답 활성 상태를 반환합니다. */
        [[nodiscard]] bool active() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 controller 또는 Host 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        void *connection_ = nullptr;
        Error last_error_ = Error::not_initialized;
        int native_code_ = 0;
        bool active_ = false;
    };
}

#endif
