/**
 * @file NUCODE_BLE_ISO.h
 * @brief NU54DK Bluetooth LE Isochronous Channels 공개 API를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_ISO_H
#define NUCODE_BLE_ISO_H

#include <Arduino.h>

#include <cstddef>
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
        invalid_argument,
        busy,
        not_ready,
        transport_failure,
    };

    /** @brief 한 CIS에서 받은 사용자 SDU와 controller 메타데이터입니다. */
    struct CisFrame final
    {
        std::uint8_t data[16] = {};
        std::uint8_t length = 0U;
        std::uint16_t sequence = 0U;
        std::uint32_t timestamp_us = 0U;
        bool timestamp_valid = false;
    };

    /**
     * @brief CIS의 사용자 SDU를 직접 송수신하는 Arduino facade입니다.
     *
     * 현재 image의 CIS central/peripheral Kconfig 역할 하나만 소유합니다. begin()에
     * 넘기는 16-byte session ID가 같은 두 보드만 연결하며, 수신 frame은 내부
     * 8개 queue에 복사되어 readFrame()으로 전달됩니다. Zephyr handle은 노출하지
     * 않습니다. 한 image에서 이 객체 하나만 사용할 수 있습니다.
     */
    class RawCis final
    {
      public:
        /** @brief role과 16-byte session ID를 정하고 무선 연결을 시작합니다. */
        Error begin(Role role, const std::uint8_t session_id[16]) noexcept;

        /** @brief 비동기 해제를 진행하고 마지막 공개 오류를 반환합니다. */
        Error poll() noexcept;

        /** @brief 최대 16-byte 사용자 SDU를 송신합니다. */
        Error sendFrame(const std::uint8_t *data, std::size_t length) noexcept;

        /** @brief 다음 수신 SDU가 있으면 복사하고 true를 반환합니다. */
        bool readFrame(CisFrame &frame) noexcept;

        /** @brief CIS·ACL을 끊고 scan/광고를 중지합니다. poll()로 해제를 마칩니다. */
        Error stop() noexcept;

        /** @brief ISO HCI data path 연결 상태입니다. */
        [[nodiscard]] bool connected() const noexcept;

        /** @brief 모든 무선 자원이 반환되었으면 true입니다. */
        [[nodiscard]] bool stopped() const noexcept;

        /** @brief native 호출의 마지막 실패 코드를 반환합니다. */
        [[nodiscard]] int nativeError() const noexcept;

        /** @brief image에 실제로 포함된 Core source revision을 반환합니다. */
        [[nodiscard]] static const char *buildRevision() noexcept;
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
