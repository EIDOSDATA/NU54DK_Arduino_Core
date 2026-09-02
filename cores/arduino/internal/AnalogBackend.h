/**
 * @file AnalogBackend.h
 * @brief Zephyr ADC/PWM 기반 analog backend의 비공개 진단 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_ANALOG_BACKEND_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_ANALOG_BACKEND_H_

#include <cstdint>

namespace nucode::arduino::internal
{

	/** @brief A0가 반환하는 고정 raw ADC 해상도입니다. */
	constexpr std::uint8_t analog_read_resolution_bits = 12U;

	/** @brief analogWrite가 해석하는 고정 duty 해상도입니다. */
	constexpr std::uint8_t analog_write_resolution_bits = 8U;

	/** @brief analog API에서 마지막으로 관측한 상태입니다. */
	enum class AnalogError : std::uint8_t
	{
		none = 0U,
		invalid_context,
		invalid_pin,
		invalid_value,
		device_not_ready,
		unsupported_reference,
		unsupported_devicetree,
		driver_error,
	};

	/** @brief 마지막 analog 상태를 반환합니다. */
	[[nodiscard]] AnalogError lastAnalogError() noexcept;

	/** @brief 마지막 Zephyr ADC/PWM 오류 번호를 반환합니다. */
	[[nodiscard]] int lastAnalogDriverError() noexcept;

	/** @brief analog 오류 상태를 초기화합니다. */
	void clearAnalogDiagnostics() noexcept;

}

#endif
