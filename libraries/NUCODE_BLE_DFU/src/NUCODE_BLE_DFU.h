/**
 * @file NUCODE_BLE_DFU.h
 * @brief 인증 BLE DFU image 상태와 명시적 MCUboot confirm API를 선언합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_DFU_H_
#define NUCODE_BLE_DFU_H_

#include <NUCODE_BLE_Security.h>

#include <cstdint>

namespace nucode::ble
{

    /** @brief secure DFU facade의 오류 분류입니다. */
    enum class SecureDfuError : std::uint8_t
    {
        none,
        not_initialized,
        invalid_image,
        driver_error,
    };

    /** @brief 실행 중인 MCUboot image의 semantic version입니다. */
    struct SecureDfuImageVersion
    {
        std::uint8_t major = 0U;
        std::uint8_t minor = 0U;
        std::uint16_t revision = 0U;
        std::uint32_t build = 0U;
    };

    /**
     * @brief secure_ble_dfu profile의 MCUboot image 상태를 관리합니다.
     *
     * begin()은 image를 자동 confirm하지 않습니다. Sketch의 self-test가 성공한 뒤 confirm()을
     * 명시적으로 호출해야 하며, 호출하지 않은 test image는 MCUboot rollback 대상입니다.
     */
    class SecureDfuManager final
    {
      public:
        /** @brief 현재 slot의 MCUboot header를 검증하고 facade를 초기화합니다. */
        [[nodiscard]] bool begin() noexcept;

        /** @brief Sketch self-test가 끝난 현재 image를 MCUboot confirmed로 기록합니다. */
        [[nodiscard]] bool confirm() noexcept;

        /** @brief 현재 실행 image가 confirmed인지 반환합니다. */
        [[nodiscard]] bool confirmed() const noexcept;

        /** @brief 현재 실행 중인 MCUboot area ID를 반환합니다. */
        [[nodiscard]] std::uint8_t activeSlot() const noexcept;

        /** @brief begin()에서 읽은 semantic version을 반환합니다. */
        [[nodiscard]] SecureDfuImageVersion version() const noexcept;

        /** @brief MCUmgr SMP service의 128-bit UUID를 반환합니다. */
        [[nodiscard]] static BLEUuid serviceUuid() noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] SecureDfuError lastError() const noexcept;

        /** @brief 마지막 Zephyr/MCUboot 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;

      private:
        SecureDfuImageVersion version_ = {};
        SecureDfuError error_ = SecureDfuError::not_initialized;
        int driver_error_ = 0;
        std::uint8_t active_slot_ = 0U;
        bool initialized_ = false;
    };

} // namespace nucode::ble

extern nucode::ble::SecureDfuManager BLESecureDfu;

#endif // NUCODE_BLE_DFU_H_
