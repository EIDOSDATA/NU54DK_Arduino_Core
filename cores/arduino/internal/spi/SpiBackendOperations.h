/**
 * @file SpiBackendOperations.h
 * @brief facade mutex 안에서 호출하는 SPI00 backend 내부 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "internal/SPIBackend.h"
#include <api/HardwareSPI.h>
#include <cstddef>
#include <cstdint>
namespace nucode::arduino::internal
{
    /** @brief facade와 driver가 공유하는 기존 atomic 진단을 기록합니다. */
    void recordSpiError(SpiError error, int driver_error = 0) noexcept;
    void recordSpiSuccess() noexcept;
    namespace spi_backend
    {
        /** @brief 기존 runtime route의 stage·활성화·종료 경계입니다. */
        [[nodiscard]] bool setPins(pin_size_t sck_pin, pin_size_t miso_pin,
                                   pin_size_t mosi_pin) noexcept;
        void begin() noexcept;
        [[nodiscard]] bool end() noexcept;
        [[nodiscard]] bool started() noexcept;
        /** @brief 고정 SPI00 prescaler 정책으로 요청 주파수를 검사합니다. */
        [[nodiscard]] bool frequencySupported(std::uint32_t frequency) noexcept;
        /** @brief 검증 시도마다 기존 두 configuration의 다음 slot을 선택합니다. */
        void advanceConfiguration() noexcept;
        /** @brief facade가 검증한 설정을 다음 Zephyr slot에 복사합니다. */
        void configureValidated(const ::arduino::SPISettings &settings) noexcept;
        /** @brief interrupt suspend 성공 뒤에만 driver configuration을 publish합니다. */
        void commitConfiguration() noexcept;
        void clearConfiguration() noexcept;
        [[nodiscard]] bool configurationReady() noexcept;
        /** @brief 수동 CS를 변경하지 않고 현재 설정으로 byte block을 전송합니다. */
        [[nodiscard]] bool transferBlock(const std::uint8_t *transmit, std::uint8_t *receive,
                                         std::size_t length) noexcept;
    } // namespace spi_backend
} // namespace nucode::arduino::internal
