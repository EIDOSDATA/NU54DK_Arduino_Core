/**
 * @file NUCODE_BLE_ISO.h
 * @brief NU54DK Bluetooth LE Isochronous Channels 공개 API를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_ISO_H
#define NUCODE_BLE_ISO_H

#include <Arduino.h>

#include <cstdint>

namespace nucode::ble::iso
{
    /** @brief 예제 image가 수행할 ISO 역할입니다. */
    enum class Role : std::uint8_t
    {
        cis_central = 0U,
        cis_peripheral,
        cis_to_bis_peer,
        bis_source,
        bis_receiver,
        bis_encrypted_source,
        bis_encrypted_receiver,
        bis_time_source,
        bis_time_receiver,
        cis_to_bis_bridge,
        cis_to_bis_receiver,
    };

    /** @brief ISO 프로그램 초기화와 실행 상태의 안정된 오류 분류입니다. */
    enum class Error : std::uint8_t
    {
        none = 0U,
        configuration_mismatch,
        not_started,
    };

    /**
     * @brief 선택한 CIS, BIS 또는 bridge 역할을 Arduino loop에서 실행합니다.
     *
     * 역할별 Zephyr Kconfig는 예제의 prj.conf가 소유합니다. 생성자의 역할과
     * image에 선택된 역할이 다르면 begin()이 configuration_mismatch를 반환합니다.
     */
    class Program final
    {
      public:
        /** @brief 실행할 역할을 지정합니다. */
        explicit constexpr Program(Role role) noexcept
            : role_(role)
        {
        }

        /** @brief Serial과 선택된 ISO backend를 초기화합니다. */
        Error begin() noexcept;

        /** @brief callback 뒤의 명령과 종료 처리를 Arduino main thread에서 진행합니다. */
        Error poll() noexcept;

        /** @brief 이 객체에 지정된 역할을 반환합니다. */
        [[nodiscard]] constexpr Role role() const noexcept
        {
            return role_;
        }

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] constexpr Error lastError() const noexcept
        {
            return last_error_;
        }

        /** @brief 현재 image의 Kconfig에 선택된 역할을 반환합니다. */
        [[nodiscard]] static Role configuredRole() noexcept;

      private:
        Role role_;
        Error last_error_ = Error::not_started;
        bool started_ = false;
    };
}

#endif
