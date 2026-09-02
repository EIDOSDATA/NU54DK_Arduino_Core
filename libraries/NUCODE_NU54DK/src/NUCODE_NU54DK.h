/**
 * @file NUCODE_NU54DK.h
 * @brief NU54DK 보드·전원 관리 기능의 Arduino 공개 API를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_NU54DK_H
#define NUCODE_NU54DK_H

#include <Arduino.h>

#include <cstddef>
#include <cstdint>

namespace nucode::nu54dk
{

	/** @brief 보드 라이브러리 API가 반환하는 안정된 오류 분류입니다. */
	enum class Error : std::uint8_t
	{
		none = 0U,
		invalid_argument,
		invalid_context,
		unsupported,
		device_not_ready,
		not_started,
		already_started,
		busy,
		not_found,
		buffer_too_small,
		permission_denied,
		configuration_required,
		driver_error,
	};

	/** @brief Zephyr hwinfo의 reset 원인 bit를 Arduino에서 해석하기 위한 값입니다. */
	enum class ResetCause : std::uint32_t
	{
		none = 0U,
		external_pin = (1UL << 0U),
		software = (1UL << 1U),
		brownout = (1UL << 2U),
		power_on = (1UL << 3U),
		watchdog = (1UL << 4U),
		debug = (1UL << 5U),
		security = (1UL << 6U),
		low_power_wake = (1UL << 7U),
		cpu_lockup = (1UL << 8U),
		parity = (1UL << 9U),
		pll = (1UL << 10U),
		clock = (1UL << 11U),
		hardware = (1UL << 12U),
		user = (1UL << 13U),
		temperature = (1UL << 14U),
		bootloader = (1UL << 15U),
		flash = (1UL << 16U),
	};

	/** @brief 현재 reset 원인과 하드웨어가 지원하는 원인 bit를 함께 보관합니다. */
	struct ResetReport
	{
		std::uint32_t cause = 0U;
		std::uint32_t supported = 0U;
	};

	/** @brief GRTC alarm이 work queue 문맥에서 호출할 함수 형식입니다. */
	using AlarmCallback = void (*)(std::uint64_t scheduled_ticks, void *context);

	/** @brief System OFF에서 wake source로 사용할 NU54DK 버튼입니다. */
	enum class WakeButton : std::uint8_t
	{
		sw0 = 0U,
		sw1,
		sw2,
		sw3,
	};

	/** @brief BQ25186에서 읽은 충전 상태입니다. */
	enum class PmicChargeState : std::uint8_t
	{
		not_charging = 0U,
		constant_current,
		constant_voltage,
		complete_or_disabled,
	};

	/** @brief BQ25186의 기본 상태와 현재 충전 설정입니다. */
	struct PmicStatus
	{
		bool input_power_good = false;
		bool charging_enabled = false;
		PmicChargeState charge_state = PmicChargeState::not_charging;
		std::uint16_t charge_voltage_mv = 0U;
		std::uint16_t charge_current_ma = 0U;
	};

	/** @brief BQ25186 SYS_REG[7:5]의 시스템 전압 동작입니다. */
	enum class PmicSystemRegulation : std::uint8_t
	{
		battery_tracking = 0U,
		v4_4 = 1U,
		v4_5 = 2U,
		v4_6 = 3U,
		v4_7 = 4U,
		v4_8 = 5U,
		v4_9 = 6U,
		pass_through_or_v5_5 = 7U,
	};

	/** @brief BQ25186 IC_CTRL[1:0]의 register watchdog 동작입니다. */
	enum class PmicRegisterWatchdog : std::uint8_t
	{
		seconds_160_restore_register_defaults = 0U,
		seconds_160_hardware_reset = 1U,
		seconds_40_hardware_reset = 2U,
		disabled = 3U,
	};

	/**
	 * @brief 배터리 조건을 사용자가 검증했다는 명시적 PMIC 쓰기 승인입니다.
	 *
	 * 승인은 RAM에만 유지되며 reset 뒤 자동으로 해제됩니다.
	 */
	enum class PmicWriteAuthorization : std::uint32_t
	{
		acknowledge_unverified_battery_hardware = 0x4E553534UL,
	};

	/** @brief NU54DK 보드·시스템·PMIC 기능을 제공하는 단일 진입점입니다. */
	class BoardSystem final
	{
	public:
		/** @brief 보드 모델 문자열을 반환합니다. */
		[[nodiscard]] const char *boardModel() const noexcept;

		/** @brief Zephyr board target 문자열을 반환합니다. */
		[[nodiscard]] const char *boardTarget() const noexcept;

		/** @brief 대상 SoC 문자열을 반환합니다. */
		[[nodiscard]] const char *socName() const noexcept;

		/** @brief 고정된 nRF Connect SDK 버전을 반환합니다. */
		[[nodiscard]] const char *ncsVersion() const noexcept;

		/** @brief 고정된 Zephyr 버전을 반환합니다. */
		[[nodiscard]] const char *zephyrVersion() const noexcept;

		/** @brief NU54DK Arduino Core 버전을 반환합니다. */
		[[nodiscard]] const char *coreVersion() const noexcept;

		/**
		 * @brief 칩의 raw device ID를 16진 문자열로 복사합니다.
		 * @note 이 값은 제조사가 UUID 유일성을 보장하는 식별자가 아닙니다.
		 */
		Error deviceId(char *destination, std::size_t destination_size) noexcept;

		/** @brief reset 원인과 지원 mask를 읽습니다. */
		Error resetReport(ResetReport &report) noexcept;

		/** @brief 누적된 reset 원인 latch를 지웁니다. */
		Error clearResetCause() noexcept;

		/** @brief 현재 boot 이후 64-bit uptime을 밀리초로 반환합니다. */
		[[nodiscard]] std::uint64_t uptimeMilliseconds() const noexcept;

		/** @brief 마지막 안정 오류를 반환합니다. */
		[[nodiscard]] Error lastError() const noexcept;

		/** @brief 마지막 Zephyr 또는 I2C 오류 번호를 반환합니다. */
		[[nodiscard]] int lastDriverError() const noexcept;

		/** @brief watchdog timeout을 설치하고 WDT31을 시작합니다. */
		Error watchdogBegin(std::uint32_t timeout_ms) noexcept;

		/** @brief 실행 중인 watchdog channel을 feed합니다. */
		Error watchdogFeed() noexcept;

		/** @brief 하드웨어가 지원하면 watchdog을 정지합니다. */
		Error watchdogStop() noexcept;

		/** @brief 이 API가 시작한 watchdog이 실행 중인지 반환합니다. */
		[[nodiscard]] bool watchdogRunning() const noexcept;

		/** @brief GRTC의 현재 absolute tick을 반환합니다. */
		[[nodiscard]] std::uint64_t hardwareCounterTicks() const noexcept;

		/** @brief GRTC tick 주파수를 Hz로 반환합니다. */
		[[nodiscard]] std::uint32_t hardwareCounterFrequency() const noexcept;

		/** @brief 한 번 실행되는 GRTC alarm을 예약합니다. */
		Error alarmAfterMicroseconds(std::uint64_t delay_us, AlarmCallback callback,
									void *context = nullptr) noexcept;

		/** @brief 대기 중인 GRTC alarm을 취소합니다. */
		Error cancelAlarm() noexcept;

		/** @brief GRTC alarm이 대기 중인지 반환합니다. */
		[[nodiscard]] bool alarmPending() const noexcept;

		/** @brief Settings/ZMS 저장소를 초기화합니다. */
		Error storageBegin() noexcept;

		/** @brief `nucode/` namespace에 제한된 값을 저장합니다. */
		Error storagePut(const char *key, const void *value, std::size_t length) noexcept;

		/** @brief 저장된 값을 읽고 실제 길이를 반환합니다. */
		Error storageGet(const char *key, void *value, std::size_t capacity,
						 std::size_t &actual_length) noexcept;

		/** @brief `nucode/` namespace의 한 값을 삭제합니다. */
		Error storageRemove(const char *key) noexcept;

		/**
		 * @brief 선택한 active-low 버튼을 설정하고 즉시 System OFF로 진입합니다.
		 * @return 준비 오류일 때만 반환하며, 성공하면 System OFF에 들어가 반환하지 않습니다.
		 */
		Error enterSystemOffOnButton(WakeButton button = WakeButton::sw0) noexcept;

		/**
		 * @brief GRTC wake를 설정하고 지정 시간 동안 즉시 System OFF로 진입합니다.
		 * @return 준비 오류일 때만 반환하며, 성공하면 System OFF에 들어가 반환하지 않습니다.
		 */
		Error enterSystemOffAfter(std::uint64_t wake_after_us) noexcept;

		/**
		 * @brief BQ25186 ID를 읽어 PMIC 접근을 시작합니다.
		 * @note 첫 I2C 접근은 PMIC 내부 register watchdog을 시작할 수 있습니다.
		 */
		Error pmicBegin() noexcept;

		/** @brief PMIC의 현재 상태와 충전 설정을 읽습니다. */
		Error pmicReadStatus(PmicStatus &status) noexcept;

		/** @brief 현재 BQ25186 SYS regulation을 읽습니다. */
		Error pmicReadSystemRegulation(PmicSystemRegulation &regulation) noexcept;

		/** @brief 현재 BQ25186 register watchdog 동작을 읽습니다. */
		Error pmicReadRegisterWatchdog(PmicRegisterWatchdog &watchdog) noexcept;

		/** @brief reset 전까지 PMIC 변경 API를 명시적으로 승인합니다. */
		Error pmicAuthorizeWrites(PmicWriteAuthorization authorization) noexcept;

		/** @brief PMIC 변경 승인을 동기적으로 해제합니다. */
		Error pmicRevokeWrites() noexcept;

		/** @brief PMIC 변경 승인이 현재 유지되는지 반환합니다. */
		[[nodiscard]] bool pmicWritesAuthorized() const noexcept;

		/** @brief 현재 승인에서 register watchdog 정책을 명시했는지 반환합니다. */
		[[nodiscard]] bool pmicRegisterWatchdogPolicyConfirmed() const noexcept;

		/** @brief 충전 완료 전압을 3500..4650 mV, 10 mV 단위로 설정합니다. */
		Error pmicSetChargeVoltage(std::uint16_t millivolts) noexcept;

		/** @brief 충전 전류를 BQ25186이 표현 가능한 5..1000 mA 값으로 설정합니다. */
		Error pmicSetChargeCurrent(std::uint16_t milliamps) noexcept;

		/** @brief 충전 경로를 활성화하거나 비활성화합니다. */
		Error pmicSetChargingEnabled(bool enabled) noexcept;

		/** @brief 재충전 문턱을 100 mV 또는 200 mV로 설정합니다. */
		Error pmicSetRechargeThreshold(std::uint16_t millivolts) noexcept;

		/** @brief SYS_REG[7:5]의 regulation 동작을 설정합니다. */
		Error pmicSetSystemRegulation(PmicSystemRegulation regulation) noexcept;

		/**
		 * @brief PMIC register watchdog 동작을 설정하고 현재 승인에 정책을 확정합니다.
		 * @note 충전·SYS 설정 API보다 먼저 호출해야 합니다.
		 */
		Error pmicSetRegisterWatchdog(PmicRegisterWatchdog watchdog) noexcept;

		/**
		 * @brief BQ25186 shutdown 진입을 요청합니다.
		 * @note 입력 전원이 있으면 제거 시 진입하고, 이미 없으면 즉시 진입할 수 있습니다.
		 * @note 즉시 진입하는 조건에서는 성공 경로가 반환된다고 보장하지 않습니다.
		 * @note 현재 승인에서 register watchdog 정책을 먼저 설정해야 합니다.
		 */
		Error pmicRequestShutdown() noexcept;

		/**
		 * @brief BQ25186 ship mode 진입을 요청합니다.
		 * @note 입력 전원이 있으면 제거 시 진입하고, 이미 없으면 즉시 진입할 수 있습니다.
		 * @note 즉시 진입하는 조건에서는 성공 경로가 반환된다고 보장하지 않습니다.
		 * @note 현재 승인에서 register watchdog 정책을 먼저 설정해야 합니다.
		 */
		Error pmicRequestShipMode() noexcept;

		/** @brief NU54DK 회로에 실제 배터리 NTC 입력이 없음을 반환합니다. */
		[[nodiscard]] constexpr bool hasBatteryTemperatureProtection() const noexcept
		{
			return false;
		}
	};

}

/** @brief Arduino sketch가 사용하는 NU54DK 보드 API 전역 객체입니다. */
extern nucode::nu54dk::BoardSystem &NU54DK;

#endif /* NUCODE_NU54DK_H */
