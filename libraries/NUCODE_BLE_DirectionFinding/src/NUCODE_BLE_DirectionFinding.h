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
}

#endif
