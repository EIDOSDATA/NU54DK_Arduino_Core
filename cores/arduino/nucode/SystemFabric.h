/**
 * @file SystemFabric.h
 * @brief TEMP와 WDT30/31을 노출하는 v0.4 후보 system API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_SYSTEM_FABRIC_H_
#define NUCODE_ARDUINO_CORE_NUCODE_SYSTEM_FABRIC_H_

#include <cstdint>

namespace nucode::arduino
{

    /** @brief M26 system fabric 연산 결과입니다. */
    enum class SystemFabricResult : std::uint8_t
    {
        success = 0U,
        invalid_context,
        invalid_argument,
        unsupported_instance,
        driver_unavailable,
        wrong_state,
        resource_exhausted,
        driver_error,
    };

    /** @brief nRF54L15 내부 TEMP 센서의 동기 측정 handle입니다. */
    class TemperatureFabric
    {
      public:
        /** @brief 섭씨 온도를 0.01도 단위로 읽습니다. */
        [[nodiscard]] SystemFabricResult readCentiCelsius(std::int32_t &temperature) noexcept;
        [[nodiscard]] int lastDriverError() const noexcept;

      private:
        friend class SystemFabric;
        constexpr TemperatureFabric() noexcept = default;
    };

    /** @brief WDT30 또는 WDT31 한 block의 명시적 lifecycle handle입니다. */
    class WatchdogFabric
    {
      public:
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] bool configured() const noexcept;
        [[nodiscard]] bool active() const noexcept;
        [[nodiscard]] int lastDriverError() const noexcept;

        /**
         * @brief 한 reload channel을 설치합니다.
         *
         * @param timeout_ms reload timeout. 0은 허용하지 않습니다.
         * @param run_in_sleep true이면 CPU sleep 중에도 watchdog이 진행합니다.
         * @param run_in_halt true이면 debugger halt 중에도 watchdog이 진행합니다.
         */
        [[nodiscard]] SystemFabricResult configure(std::uint32_t timeout_ms,
                                                   bool run_in_sleep = true,
                                                   bool run_in_halt = false) noexcept;
        [[nodiscard]] SystemFabricResult start() noexcept;
        [[nodiscard]] SystemFabricResult feed() noexcept;
        [[nodiscard]] SystemFabricResult stop() noexcept;

      private:
        friend class SystemFabric;
        constexpr explicit WatchdogFabric(std::uint8_t instance) noexcept : instance_(instance)
        {
        }

        std::uint8_t instance_;
    };

    /** @brief M26 온칩 system peripheral 후보 handle factory입니다. */
    class SystemFabric
    {
      public:
        [[nodiscard]] TemperatureFabric &temperature() noexcept;
        [[nodiscard]] WatchdogFabric *watchdog(std::uint8_t instance) noexcept;

      private:
        friend SystemFabric &systemFabric() noexcept;
        constexpr SystemFabric() noexcept = default;
    };

    /** @brief process-wide M26 system fabric factory를 반환합니다. */
    [[nodiscard]] SystemFabric &systemFabric() noexcept;

} // namespace nucode::arduino

#endif
