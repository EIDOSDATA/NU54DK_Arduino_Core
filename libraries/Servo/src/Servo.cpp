/**
 * @file Servo.cpp
 * @brief NU54DK PWM22 기반 Arduino Servo API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Servo.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <Arduino.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>

#include "internal/PwmRuntime.h"

namespace
{
	using nucode::arduino::internal::PwmRuntimeClient;
	using nucode::arduino::internal::PwmRuntimeResult;

	/** @brief Servo 한 개의 소유 객체와 마지막 성공 pulse입니다. */
	struct ServoSlot
	{
		Servo *owner{nullptr};
		pin_size_t pin{};
		std::uint16_t pulse_us{DEFAULT_PULSE_WIDTH};
	};

	K_MUTEX_DEFINE(servo_mutex);
	ServoSlot servo_slots[MAX_SERVOS]{};

	/** @brief Servo refresh 주기를 nanosecond로 반환합니다. */
	constexpr std::uint32_t servo_period_ns =
		static_cast<std::uint32_t>(REFRESH_INTERVAL) * 1000U;

	/** @brief microsecond pulse를 nanosecond로 안전하게 변환합니다. */
	[[nodiscard]] constexpr std::uint32_t pulseNanoseconds(
		std::uint16_t pulse_us) noexcept
	{
		return static_cast<std::uint32_t>(pulse_us) * 1000U;
	}

	/** @brief 객체가 실제로 소유하는 slot을 반환합니다. */
	[[nodiscard]] ServoSlot *ownedSlot(Servo *owner,
									   std::uint8_t index) noexcept
	{
		return index < MAX_SERVOS && servo_slots[index].owner == owner
				   ? &servo_slots[index]
				   : nullptr;
	}

	/** @brief 정수 값을 포함 범위로 제한합니다. */
	[[nodiscard]] constexpr int clampValue(int value, int minimum,
										   int maximum) noexcept
	{
		return value < minimum ? minimum : (value > maximum ? maximum : value);
	}
}

Servo::Servo()
	: servo_index_(INVALID_SERVO), minimum_(MIN_PULSE_WIDTH),
	  maximum_(MAX_PULSE_WIDTH)
{
}

std::uint8_t Servo::attach(int pin)
{
	return attach(pin, MIN_PULSE_WIDTH, MAX_PULSE_WIDTH);
}

std::uint8_t Servo::attach(int pin, int minimum, int maximum)
{
	if (k_is_in_isr() || pin < 0 ||
		static_cast<unsigned long>(pin) >
			static_cast<unsigned long>(static_cast<pin_size_t>(-1)) ||
		minimum <= 0 || maximum <= minimum || maximum > REFRESH_INTERVAL)
	{
		return INVALID_SERVO;
	}

	if (attached())
	{
		detach();
		if (attached())
		{
			return INVALID_SERVO;
		}
	}

	static_cast<void>(k_mutex_lock(&servo_mutex, K_FOREVER));
	std::uint8_t index = INVALID_SERVO;
	for (std::uint8_t candidate = 0U; candidate < MAX_SERVOS; ++candidate)
	{
		if (servo_slots[candidate].owner == nullptr)
		{
			index = candidate;
			break;
		}
	}
	if (index == INVALID_SERVO)
	{
		static_cast<void>(k_mutex_unlock(&servo_mutex));
		return INVALID_SERVO;
	}

	const auto logical_pin = static_cast<pin_size_t>(pin);
	const std::uint16_t initial_pulse = static_cast<std::uint16_t>(
		clampValue(DEFAULT_PULSE_WIDTH, minimum, maximum));
	const PwmRuntimeResult result = nucode::arduino::internal::pwmRuntimeWrite(
		PwmRuntimeClient::servo, logical_pin, servo_period_ns,
		pulseNanoseconds(initial_pulse));
	if (result != PwmRuntimeResult::success)
	{
		static_cast<void>(k_mutex_unlock(&servo_mutex));
		return INVALID_SERVO;
	}

	servo_slots[index] = {this, logical_pin, initial_pulse};
	servo_index_ = index;
	minimum_ = static_cast<std::uint16_t>(minimum);
	maximum_ = static_cast<std::uint16_t>(maximum);
	static_cast<void>(k_mutex_unlock(&servo_mutex));
	return index;
}

void Servo::detach()
{
	if (k_is_in_isr())
	{
		return;
	}
	static_cast<void>(k_mutex_lock(&servo_mutex, K_FOREVER));
	ServoSlot *const slot = ownedSlot(this, servo_index_);
	if (slot == nullptr)
	{
		servo_index_ = INVALID_SERVO;
		static_cast<void>(k_mutex_unlock(&servo_mutex));
		return;
	}

	const PwmRuntimeResult result = nucode::arduino::internal::pwmRuntimeStop(
		PwmRuntimeClient::servo, slot->pin);
	if (result == PwmRuntimeResult::success || result == PwmRuntimeResult::not_active)
	{
		*slot = {};
		servo_index_ = INVALID_SERVO;
	}
	static_cast<void>(k_mutex_unlock(&servo_mutex));
}

void Servo::write(int value)
{
	if (value < 200)
	{
		const int angle = clampValue(value, 0, 180);
		const std::uint32_t span = static_cast<std::uint32_t>(maximum_ - minimum_);
		const int pulse = static_cast<int>(minimum_) +
						  static_cast<int>((span * static_cast<std::uint32_t>(angle) + 90U) / 180U);
		writeMicroseconds(pulse);
		return;
	}
	writeMicroseconds(value);
}

void Servo::writeMicroseconds(int value)
{
	if (k_is_in_isr())
	{
		return;
	}
	static_cast<void>(k_mutex_lock(&servo_mutex, K_FOREVER));
	ServoSlot *const slot = ownedSlot(this, servo_index_);
	if (slot == nullptr)
	{
		static_cast<void>(k_mutex_unlock(&servo_mutex));
		return;
	}

	const auto pulse_us = static_cast<std::uint16_t>(
		clampValue(value, static_cast<int>(minimum_), static_cast<int>(maximum_)));
	const PwmRuntimeResult result = nucode::arduino::internal::pwmRuntimeWrite(
		PwmRuntimeClient::servo, slot->pin, servo_period_ns,
		pulseNanoseconds(pulse_us));
	if (result == PwmRuntimeResult::success)
	{
		slot->pulse_us = pulse_us;
	}
	static_cast<void>(k_mutex_unlock(&servo_mutex));
}

int Servo::read()
{
	if (k_is_in_isr())
	{
		return 0;
	}
	static_cast<void>(k_mutex_lock(&servo_mutex, K_FOREVER));
	ServoSlot *const slot = ownedSlot(this, servo_index_);
	if (slot == nullptr)
	{
		static_cast<void>(k_mutex_unlock(&servo_mutex));
		return 0;
	}
	const std::uint32_t span = static_cast<std::uint32_t>(maximum_ - minimum_);
	const std::uint32_t offset =
		static_cast<std::uint32_t>(slot->pulse_us - minimum_);
	const int angle = span == 0U
						  ? 0
						  : static_cast<int>((offset * 180U + span / 2U) / span);
	static_cast<void>(k_mutex_unlock(&servo_mutex));
	return angle;
}

int Servo::readMicroseconds()
{
	if (k_is_in_isr())
	{
		return 0;
	}
	static_cast<void>(k_mutex_lock(&servo_mutex, K_FOREVER));
	ServoSlot *const slot = ownedSlot(this, servo_index_);
	const int result = slot != nullptr ? static_cast<int>(slot->pulse_us) : 0;
	static_cast<void>(k_mutex_unlock(&servo_mutex));
	return result;
}

bool Servo::attached()
{
	if (k_is_in_isr())
	{
		return false;
	}
	static_cast<void>(k_mutex_lock(&servo_mutex, K_FOREVER));
	const bool result = ownedSlot(this, servo_index_) != nullptr;
	static_cast<void>(k_mutex_unlock(&servo_mutex));
	return result;
}

#endif
