/**
 * @file PwmRuntime.h
 * @brief AC-02B PWM20·PWM21·PWM22의 고정 자원 allocator 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_PWM_RUNTIME_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_PWM_RUNTIME_H_

#include <api/Common.h>
#include <zephyr/device.h>
#include <zephyr/drivers/pwm.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
	/** @brief PWM block을 사용하는 Arduino 기능입니다. */
	enum class PwmRuntimeClient : std::uint8_t
	{
		analog_write = 0U,
		tone,
		servo,
	};

	/** @brief PWM runtime 연산 결과입니다. */
	enum class PwmRuntimeResult : std::uint8_t
	{
		success = 0U,
		invalid_context,
		invalid_argument,
		invalid_pin,
		unsupported_route,
		device_not_ready,
		ownership_conflict,
		period_conflict,
		channel_exhausted,
		not_active,
		route_error,
		driver_error,
	};

	/** @brief PWM block 하나가 동시에 출력할 수 있는 최대 채널 수입니다. */
	inline constexpr std::size_t pwm_runtime_channel_capacity = 4U;

	/**
	 * @brief 한 PWM block에 원자적으로 적용할 전체 출력 route입니다.
	 *
	 * @details nRF PWM pinctrl은 block 단위 default/sleep state이므로 채널을
	 * 하나씩 바꾸지 않고 네 출력의 전체 desired state를 한 번에 전달합니다.
	 */
	struct PwmRuntimeRouteSet
	{
		pin_size_t pins[pwm_runtime_channel_capacity]{};
		std::uint8_t channels[pwm_runtime_channel_capacity]{};
		std::size_t count{0U};
	};

	/** @brief 한 PWM block의 실제 Zephyr 장치와 polarity입니다. */
	struct PwmRuntimeBlock
	{
		const struct device *device{nullptr};
		pwm_flags_t flags{0U};
	};

	/** @brief GPIO 전환 실패 시 PWM 출력을 되살리기 위한 중지 snapshot입니다. */
	struct PwmRuntimeSuspendedOutput
	{
		PwmRuntimeClient client{PwmRuntimeClient::analog_write};
		pin_size_t pin{};
		std::uint32_t period_ns{0U};
		std::uint32_t pulse_ns{0U};
		bool valid{false};
	};

	/**
	 * @brief B2 runtime route 구현을 PWM allocator에 연결하는 adapter입니다.
	 *
	 * @details apply()는 기존 route가 있다면 suspend/deactivate한 뒤 전체 새
	 * route를 stage/activate합니다. 실패하면 호출 전 route를 복원해야 합니다.
	 * clear()도 실패 시 기존 활성 route를 유지합니다. Adapter는 pinctrl
	 * default/sleep state, PM runtime과 block ownership을 함께 관리합니다.
	 */
	struct PwmRuntimeRouteBackend
	{
		bool (*supports)(pin_size_t pin, std::uint8_t block_instance) noexcept;
		PwmRuntimeResult (*block)(std::uint8_t block_instance,
								  PwmRuntimeBlock &block) noexcept;
		PwmRuntimeResult (*apply)(std::uint8_t block_instance,
								  const PwmRuntimeRouteSet &routes) noexcept;
		PwmRuntimeResult (*clear)(std::uint8_t block_instance) noexcept;
		int (*last_driver_error)(std::uint8_t block_instance) noexcept;
	};

	/** @brief client에 고정된 NU54DK PWM block 번호를 반환합니다. */
	[[nodiscard]] constexpr std::uint8_t pwmRuntimeBlockInstance(
		PwmRuntimeClient client) noexcept
	{
		switch (client)
		{
		case PwmRuntimeClient::analog_write:
			return 20U;
		case PwmRuntimeClient::tone:
			return 21U;
		case PwmRuntimeClient::servo:
			return 22U;
		default:
			return 0xFFU;
		}
	}

	/**
	 * @brief 부팅 중 B2 runtime route backend를 한 번 설치합니다.
	 *
	 * @return 설치되었으면 true, 잘못된 adapter이거나 출력이 활성 상태이면 false입니다.
	 */
	[[nodiscard]] bool installPwmRuntimeRouteBackend(
		const PwmRuntimeRouteBackend &backend) noexcept;

	/** @brief 지정 핀을 client용 PWM route로 사용할 수 있는지 확인합니다. */
	[[nodiscard]] bool pwmRuntimePinSupported(PwmRuntimeClient client,
											  pin_size_t pin) noexcept;

	/**
	 * @brief 핀에 지정 주기와 pulse를 출력하거나 기존 출력을 갱신합니다.
	 */
	[[nodiscard]] PwmRuntimeResult pwmRuntimeWrite(
		PwmRuntimeClient client, pin_size_t pin, std::uint32_t period_ns,
		std::uint32_t pulse_ns) noexcept;

	/** @brief 활성 출력의 duty 비율을 보존하면서 주기만 변경합니다. */
	[[nodiscard]] PwmRuntimeResult pwmRuntimeRetune(
		PwmRuntimeClient client, pin_size_t pin,
		std::uint32_t period_ns) noexcept;

	/** @brief 지정 client가 소유한 핀 출력을 중지하고 GPIO 상태를 복원합니다. */
	[[nodiscard]] PwmRuntimeResult pwmRuntimeStop(
		PwmRuntimeClient client, pin_size_t pin) noexcept;

	/** @brief 출력값을 snapshot에 보존한 채 route에서 안전하게 제거합니다. */
	[[nodiscard]] PwmRuntimeResult pwmRuntimeSuspend(
		PwmRuntimeClient client, pin_size_t pin,
		PwmRuntimeSuspendedOutput &snapshot) noexcept;

	/** @brief 실패한 GPIO 전환 뒤 보존한 PWM 출력을 다시 적용합니다. */
	[[nodiscard]] PwmRuntimeResult pwmRuntimeResume(
		PwmRuntimeSuspendedOutput &snapshot) noexcept;

	/** @brief 핀의 client 출력이 활성 상태인지 확인합니다. */
	[[nodiscard]] bool pwmRuntimeActive(PwmRuntimeClient client,
										pin_size_t pin) noexcept;

	/** @brief 마지막 Zephyr PWM 또는 pin route 오류 번호를 반환합니다. */
	[[nodiscard]] int lastPwmRuntimeDriverError() noexcept;

#if defined(CONFIG_ZTEST)
	/** @brief ztest 격리를 위해 allocator와 backend 등록을 초기화합니다. */
	void resetPwmRuntimeForTest() noexcept;
#endif
}

#endif
