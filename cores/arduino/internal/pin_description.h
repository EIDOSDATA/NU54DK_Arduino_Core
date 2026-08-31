/**
 * @file pin_description.h
 * @brief Arduino 논리 핀과 Zephyr GPIO 자원을 연결하는 내부 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_PIN_DESCRIPTION_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_PIN_DESCRIPTION_H_

#include <zephyr/drivers/gpio.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{

	/**
	 * @brief Arduino 논리 핀이 지원하는 최소 GPIO 기능입니다.
	 */
	enum class PinCapability : std::uint8_t
	{
		none = 0U,
		digital_input = 1U << 0U,
		digital_output = 1U << 1U,
		interrupt = 1U << 2U,
		open_drain = 1U << 3U,
	};

	/**
	 * @brief 공개 논리 핀의 고정 자원 소유권을 구분합니다.
	 */
	enum class PinOwnership : std::uint8_t
	{
		board_led = 0U,
		board_button,
		connector_gpio,
	};

	/**
	 * @brief 두 핀 기능을 하나의 비트 마스크로 결합합니다.
	 *
	 * @param lhs 첫 번째 핀 기능입니다.
	 * @param rhs 두 번째 핀 기능입니다.
	 * @return 결합된 핀 기능 비트 마스크입니다.
	 */
	[[nodiscard]] constexpr PinCapability operator|(PinCapability lhs, PinCapability rhs) noexcept
	{
		return static_cast<PinCapability>(static_cast<std::uint8_t>(lhs) |
										  static_cast<std::uint8_t>(rhs));
	}

	/**
	 * @brief 핀 기능 비트 마스크에 요청 기능이 포함되는지 확인합니다.
	 *
	 * @param capabilities 핀이 제공하는 기능 비트 마스크입니다.
	 * @param requested 확인할 단일 기능입니다.
	 * @return 요청 기능을 제공하면 true, 그렇지 않으면 false입니다.
	 */
	[[nodiscard]] constexpr bool hasPinCapability(PinCapability capabilities,
												  PinCapability requested) noexcept
	{
		return (static_cast<std::uint8_t>(capabilities) & static_cast<std::uint8_t>(requested)) !=
			   0U;
	}

	/**
	 * @brief 하나의 Arduino 논리 핀에 대응하는 immutable 설명자입니다.
	 *
	 * 실제 GPIO controller, pin 번호와 Devicetree flag는 최종 보드·profile
	 * Devicetree에서 생성하며 C++ Core 또는 Variant가 물리 값을 복제하지 않습니다.
	 */
	struct PinDescription
	{
		gpio_dt_spec gpio;
		PinCapability capabilities;
		PinOwnership ownership;
	};

	/**
	 * @brief GPIO 공개 API에서 발생한 마지막 내부 오류입니다.
	 */
	enum class GpioError : std::uint8_t
	{
		none = 0U,
		invalid_context,
		invalid_pin,
		invalid_mode,
		invalid_value,
		unsupported_capability,
		unsupported_devicetree_flags,
		device_not_ready,
		pin_not_configured,
		wrong_mode,
		null_callback,
		invalid_interrupt_mode,
		interrupt_not_configured,
		ownership_conflict,
		nesting_overflow,
		interrupt_restore_without_disable,
		driver_error,
	};

	/**
	 * @brief Arduino 논리 핀의 immutable 설명자를 조회합니다.
	 *
	 * @param logical_pin Variant가 정의한 Arduino 논리 핀 index입니다.
	 * @return 유효한 핀이면 설명자 주소, 범위를 벗어나면 nullptr입니다.
	 */
	[[nodiscard]] const PinDescription *pinDescription(std::size_t logical_pin) noexcept;

	/**
	 * @brief 현재 Variant가 제공하는 논리 핀 개수를 반환합니다.
	 *
	 * @return Variant 설명자 배열의 원소 개수입니다.
	 */
	[[nodiscard]] std::size_t pinDescriptionCount() noexcept;

	/**
	 * @brief 마지막 GPIO 내부 오류를 반환합니다.
	 *
	 * Arduino 공개 API의 반환형으로 표현할 수 없는 오류를 시험과 향후 진단
	 * 경로에서 확인하기 위한 비공개 상태입니다.
	 *
	 * @return 마지막으로 기록된 GPIO 오류입니다.
	 */
	[[nodiscard]] GpioError lastGpioError() noexcept;

	/**
	 * @brief 마지막 Zephyr GPIO driver 오류 번호를 반환합니다.
	 *
	 * @return driver 오류가 있으면 원래 음수 오류 번호, 그렇지 않으면 0입니다.
	 */
	[[nodiscard]] int lastGpioDriverError() noexcept;

	/**
	 * @brief 마지막 GPIO 내부 오류와 driver 오류를 초기화합니다.
	 */
	void clearGpioError() noexcept;

	/**
	 * @brief GPIO backend 구현에서 공통 오류를 기록합니다.
	 *
	 * @param error Core 내부 오류 분류입니다.
	 * @param driver_error Zephyr GPIO가 반환한 오류 번호입니다.
	 */
	void setGpioBackendError(GpioError error, int driver_error = 0) noexcept;

	/** @brief GPIO backend 구현에서 성공 상태를 기록합니다. */
	void setGpioBackendSuccess() noexcept;

	/**
	 * @brief 논리 핀이 Arduino input mode로 설정되었는지 확인합니다.
	 *
	 * @param logical_pin 확인할 Arduino 논리 핀입니다.
	 * @return INPUT 계열 mode가 적용되었으면 true입니다.
	 */
	[[nodiscard]] bool isPinConfiguredForInput(std::size_t logical_pin) noexcept;

	/**
	 * @brief 논리 핀이 Arduino output mode로 설정되었는지 확인합니다.
	 *
	 * @param logical_pin 확인할 Arduino 논리 핀입니다.
	 * @return push-pull 또는 open-drain output mode이면 true입니다.
	 */
	[[nodiscard]] bool isPinConfiguredForOutput(std::size_t logical_pin) noexcept;

}

#endif
