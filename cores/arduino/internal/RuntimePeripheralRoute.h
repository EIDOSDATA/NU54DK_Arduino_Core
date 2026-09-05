/**
 * @file RuntimePeripheralRoute.h
 * @brief 주변장치 pinctrl·PM·GPIO ownership 전환을 하나의 수명주기로 관리합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_RUNTIME_PERIPHERAL_ROUTE_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_RUNTIME_PERIPHERAL_ROUTE_H_

#include "internal/IoResourceManager.h"
#include "internal/PinHandover.h"

#include <api/Common.h>

#include <zephyr/device.h>
#include <zephyr/drivers/pinctrl.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
    /** @brief 하나의 runtime 주변장치 route가 사용할 수 있는 최대 signal 수입니다. */
    inline constexpr std::size_t runtime_peripheral_route_pin_capacity = 4U;

    /** @brief nRF pinctrl로 변환할 주변장치 signal입니다. */
    enum class PeripheralSignal : std::uint8_t
    {
        invalid = 0U,
        uart_rx,
        uart_tx,
        i2c_sda,
        i2c_scl,
        spi_sck,
        spi_miso,
        spi_mosi,
        pwm_out0,
        pwm_out1,
        pwm_out2,
        pwm_out3,
    };

    /** @brief stage 가능한 하나의 주변장치 route입니다. */
    struct PeripheralRouteConfiguration
    {
        pin_size_t logical_pins[runtime_peripheral_route_pin_capacity]{};
        PeripheralSignal signals[runtime_peripheral_route_pin_capacity]{};
        pinctrl_soc_pin_t default_pins[runtime_peripheral_route_pin_capacity]{};
        pinctrl_soc_pin_t sleep_pins[runtime_peripheral_route_pin_capacity]{};
        std::size_t pin_count{0U};
    };

    /** @brief runtime route 계층의 고정 오류 분류입니다. */
    enum class RuntimePeripheralRouteError : std::uint8_t
    {
        none = 0U,
        invalid_argument,
        invalid_context,
        not_staged,
        already_active,
        faulted,
        device_not_ready,
        pm_not_enabled,
        device_not_suspended,
        ownership_conflict,
        pin_handover_failed,
        pinctrl_failed,
        pm_failed,
        release_failed,
    };

    /**
	 * @brief 한 Zephyr 장치의 runtime route 수명주기를 고정 메모리로 관리합니다.
	 *
	 * @details stage()는 장치가 종료된 동안 route를 복사만 합니다. activate()가
	 * peripheral block과 GPIO pad를 예약하고, suspend 상태에서 default/sleep pinctrl을
	 * 교체한 뒤 runtime PM reference를 획득합니다. deactivate()는 반대 순서로 장치를
	 * suspend하고 이전 GPIO 상태를 복원합니다.
	 */
    class RuntimePeripheralRoute final
    {
      public:
        /**
		 * @brief 고정 장치와 peripheral block 소유자를 연결합니다.
		 *
		 * @param device runtime PM을 제공하는 Zephyr 장치입니다.
		 * @param pinctrl_config CONFIG_PINCTRL_DYNAMIC으로 외부 노출된 장치 설정입니다.
		 * @param owner 주변장치 backend owner입니다.
		 * @param block_kind ownership manager가 구분할 peripheral block 종류입니다.
		 * @param block_index peripheral block 또는 instance 번호입니다.
		 */
        RuntimePeripheralRoute(const struct device *device,
                               struct pinctrl_dev_config *pinctrl_config, IoResourceOwner owner,
                               IoResourceKind block_kind, std::uint16_t block_index) noexcept;

        RuntimePeripheralRoute(const RuntimePeripheralRoute &) = delete;
        RuntimePeripheralRoute &operator=(const RuntimePeripheralRoute &) = delete;

        /** @brief 종료 상태에서 다음 activate()가 적용할 route를 복사합니다. */
        [[nodiscard]] bool stage(const PeripheralRouteConfiguration &configuration) noexcept;

        /** @brief ownership, pinctrl과 runtime PM을 원자적 실패 복구 순서로 활성화합니다. */
        [[nodiscard]] bool activate() noexcept;

        /** @brief 장치를 suspend하고 이전 GPIO 상태와 block ownership을 복원합니다. */
        [[nodiscard]] bool deactivate() noexcept;

        /** @brief route가 활성 상태인지 반환합니다. */
        [[nodiscard]] bool active() const noexcept;

        /** @brief 복구할 수 없는 release 오류 뒤 재사용이 차단되었는지 반환합니다. */
        [[nodiscard]] bool faulted() const noexcept;

        /** @brief 마지막 route 오류를 반환합니다. */
        [[nodiscard]] RuntimePeripheralRouteError lastError() const noexcept;

        /** @brief 마지막 Zephyr 또는 ownership 계층 오류 번호를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;

        /** @brief stage된 route를 반환합니다. */
        [[nodiscard]] const PeripheralRouteConfiguration &configuration() const noexcept;

      private:
        /** @brief 하위 계층 결과를 기존 음수 진단 코드로 변환합니다. */
        [[nodiscard]] static int handoverError(PinHandoverResult result) noexcept;
        [[nodiscard]] static int ownershipError(IoResourceResult result) noexcept;

        /** @brief activate 실패 뒤 PM, pinctrl, GPIO와 block을 안전한 역순으로 복구합니다. */
        [[nodiscard]] bool unwindActivation(std::size_t handover_count) noexcept;

        /** @brief prepared handover의 lock만 해제하고 fail-closed 상태로 보존합니다. */
        void abandonPreparedPinsFailClosed(std::size_t handover_count) noexcept;

        /** @brief 아직 commit된 GPIO handover 개수를 다시 계산합니다. */
        void refreshCommittedPinCount() noexcept;

        /** @brief 오류와 원래 driver 상태를 함께 기록합니다. */
        void recordError(RuntimePeripheralRouteError error, int driver_error = 0) noexcept;

        const struct device *device_;
        struct pinctrl_dev_config *pinctrl_config_;
        IoResourceOwner owner_;
        IoResourceKind block_kind_;
        std::uint16_t block_index_;
        PeripheralRouteConfiguration staged_configuration_{};
        /** @brief 다음 API 허용 여부이며 실제 잔여 자원은 acquired_가 보존합니다. */
        enum class Phase : std::uint8_t
        {
            empty,
            staged,
            active,
            faulted,
        };
        /** @brief 부분 성공·복구 실패에서도 버리지 않는 실제 획득 기록입니다. */
        struct AcquiredResources
        {
            pinctrl_soc_pin_t active_default_pins_[runtime_peripheral_route_pin_capacity]{};
            pinctrl_soc_pin_t active_sleep_pins_[runtime_peripheral_route_pin_capacity]{};
            struct pinctrl_state active_states_[2]{};
            const struct pinctrl_state *previous_states_{nullptr};
            std::uint8_t previous_state_count_{0U};
            IoResourceLease block_lease_{};
            GpioPinHandover pin_handovers_[runtime_peripheral_route_pin_capacity]{};
            std::size_t committed_pin_count_{0U};
            bool pinctrl_route_installed_{false};
            bool pm_reference_held_{false};
        };
        AcquiredResources acquired_{};
        Phase phase_{Phase::empty};
        RuntimePeripheralRouteError last_error_{RuntimePeripheralRouteError::none};
        int last_driver_error_{0};
    };

} // namespace nucode::arduino::internal

#endif
