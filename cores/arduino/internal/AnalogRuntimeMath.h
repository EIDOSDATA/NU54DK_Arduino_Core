/**
 * @file AnalogRuntimeMath.h
 * @brief AC-02B ADC/PWM 해상도와 시간 변환의 순수 계산 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_ANALOG_RUNTIME_MATH_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_ANALOG_RUNTIME_MATH_H_

#include <cstdint>

namespace nucode::arduino::internal
{
	/** @brief ADC가 지원하는 해상도인지 확인합니다. */
	[[nodiscard]] constexpr bool isSupportedAnalogReadResolution(
		std::uint8_t bits) noexcept
	{
		return bits == 8U || bits == 10U || bits == 12U || bits == 14U;
	}

	/** @brief PWM duty 입력에 허용하는 해상도인지 확인합니다. */
	[[nodiscard]] constexpr bool isSupportedAnalogWriteResolution(
		std::uint8_t bits) noexcept
	{
		return bits >= 1U && bits <= 16U;
	}

	/**
	 * @brief 해상도에 대응하는 unsigned 최댓값을 반환합니다.
	 *
	 * @param bits 1~31 범위의 bit 수입니다.
	 * @return 유효하면 2^bits-1, 범위를 벗어나면 0입니다.
	 */
	[[nodiscard]] constexpr std::uint32_t analogResolutionMaximum(
		std::uint8_t bits) noexcept
	{
		return bits >= 1U && bits <= 31U
				   ? (static_cast<std::uint32_t>(1UL) << bits) - 1U
				   : 0U;
	}

	/**
	 * @brief PWM 주기와 정수 duty 값을 nanosecond pulse로 변환합니다.
	 *
	 * @details 64-bit 중간값과 반올림을 사용하므로 16-bit duty와 최대
	 * 32-bit nanosecond 주기의 곱이 넘치지 않습니다.
	 */
	[[nodiscard]] constexpr std::uint32_t scaleAnalogDutyToPulse(
		std::uint32_t period_ns, std::uint32_t value,
		std::uint8_t resolution_bits) noexcept
	{
		const std::uint32_t maximum = analogResolutionMaximum(resolution_bits);
		if (maximum == 0U || value > maximum)
		{
			return 0U;
		}
		if (value == maximum)
		{
			return period_ns;
		}

		const std::uint64_t scaled =
			static_cast<std::uint64_t>(period_ns) * value + maximum / 2U;
		return static_cast<std::uint32_t>(scaled / maximum);
	}

	/**
	 * @brief Hz를 정수 nanosecond 주기로 변환합니다.
	 *
	 * @param frequency_hz 0보다 큰 주파수입니다.
	 * @param period_ns 변환 결과를 받을 주소입니다.
	 * @return 표현 가능한 주기이면 true입니다.
	 */
	[[nodiscard]] constexpr bool frequencyToPeriodNanoseconds(
		std::uint32_t frequency_hz, std::uint32_t &period_ns) noexcept
	{
		constexpr std::uint64_t nanoseconds_per_second = 1000000000ULL;
		if (frequency_hz == 0U)
		{
			return false;
		}

		const std::uint64_t rounded =
			(nanoseconds_per_second + frequency_hz / 2U) / frequency_hz;
		if (rounded == 0U || rounded > UINT32_MAX)
		{
			return false;
		}

		period_ns = static_cast<std::uint32_t>(rounded);
		return true;
	}

	/** @brief 기존 duty 비율을 새 주기의 pulse로 옮깁니다. */
	[[nodiscard]] constexpr std::uint32_t rescalePulseForPeriod(
		std::uint32_t old_period_ns, std::uint32_t old_pulse_ns,
		std::uint32_t new_period_ns) noexcept
	{
		if (old_period_ns == 0U)
		{
			return 0U;
		}
		if (old_pulse_ns >= old_period_ns)
		{
			return new_period_ns;
		}

		const std::uint64_t scaled =
			static_cast<std::uint64_t>(new_period_ns) * old_pulse_ns +
			old_period_ns / 2U;
		return static_cast<std::uint32_t>(scaled / old_period_ns);
	}
}

#endif
