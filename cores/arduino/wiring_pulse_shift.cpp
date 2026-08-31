/**
 * @file wiring_pulse_shift.cpp
 * @brief NU54DK GPIO 위에 Arduino pulse와 shift API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/time_units.h>

#include <cstddef>
#include <cstdint>

#include "internal/pin_description.h"

namespace
{
	using nucode::arduino::internal::GpioError;
	using nucode::arduino::internal::hasPinCapability;
	using nucode::arduino::internal::isPinConfiguredForInput;
	using nucode::arduino::internal::isPinConfiguredForOutput;
	using nucode::arduino::internal::lastGpioError;
	using nucode::arduino::internal::PinCapability;
	using nucode::arduino::internal::PinDescription;
	using nucode::arduino::internal::pinDescription;
	using nucode::arduino::internal::setGpioBackendError;
	using nucode::arduino::internal::setGpioBackendSuccess;

	/** @brief pulseInLong()이 같은 우선순위 thread에 양보하는 polling 간격입니다. */
	constexpr std::uint32_t long_pulse_yield_interval = 64U;

	/**
	 * @brief pulse 측정에 사용할 input descriptor를 검증합니다.
	 *
	 * @param pin Arduino 논리 핀입니다.
	 * @return 측정할 수 있으면 descriptor 주소, 아니면 nullptr입니다.
	 */
	[[nodiscard]] const PinDescription *inputDescription(pin_size_t pin) noexcept
	{
		if (k_is_in_isr())
		{
			setGpioBackendError(GpioError::invalid_context);
			return nullptr;
		}

		const auto logical_pin = static_cast<std::size_t>(pin);
		const PinDescription *const description = pinDescription(logical_pin);
		if (description == nullptr)
		{
			setGpioBackendError(GpioError::invalid_pin);
			return nullptr;
		}
		if (!hasPinCapability(description->capabilities, PinCapability::digital_input))
		{
			setGpioBackendError(GpioError::unsupported_capability);
			return nullptr;
		}
		if (!isPinConfiguredForInput(logical_pin))
		{
			setGpioBackendError(GpioError::wrong_mode);
			return nullptr;
		}
		if (!gpio_is_ready_dt(&description->gpio))
		{
			setGpioBackendError(GpioError::device_not_ready);
			return nullptr;
		}
		return description;
	}

	/** @brief 지정한 descriptor의 raw 전기 상태를 읽습니다. */
	[[nodiscard]] int readRaw(const PinDescription &description) noexcept
	{
		const int result = gpio_pin_get_raw(description.gpio.port, description.gpio.pin);
		if (result < 0)
		{
			setGpioBackendError(GpioError::driver_error, result);
		}
		return result;
	}

	/**
	 * @brief 하나의 polling 단계에서 timeout과 선택적 scheduler 양보를 처리합니다.
	 *
	 * @param started_cycles 전체 측정 시작 cycle입니다.
	 * @param timeout_cycles 전체 제한 cycle입니다.
	 * @param cooperative pulseInLong()의 양보 정책을 사용할지 여부입니다.
	 * @param polls 현재 polling 횟수입니다.
	 * @return 전체 deadline에 도달했으면 true입니다.
	 */
	[[nodiscard]] bool pollDeadline(std::uint64_t started_cycles,
								std::uint64_t timeout_cycles,
								bool cooperative,
								std::uint32_t &polls) noexcept
	{
		++polls;
		if (cooperative && ((polls % long_pulse_yield_interval) == 0U) && k_can_yield())
		{
			k_yield();
		}
		return (k_cycle_get_64() - started_cycles) >= timeout_cycles;
	}

	/** @brief pulseIn()과 pulseInLong()의 공통 64-bit deadline 구현입니다. */
	[[nodiscard]] unsigned long measurePulse(pin_size_t pin, std::uint8_t state,
										 unsigned long timeout, bool cooperative) noexcept
	{
		if ((state != static_cast<std::uint8_t>(LOW)) &&
			(state != static_cast<std::uint8_t>(HIGH)))
		{
			setGpioBackendError(GpioError::invalid_value);
			return 0UL;
		}

		const PinDescription *const description = inputDescription(pin);
		if (description == nullptr)
		{
			return 0UL;
		}
		if (timeout == 0UL)
		{
			setGpioBackendSuccess();
			return 0UL;
		}

		const int target = (state == static_cast<std::uint8_t>(HIGH)) ? 1 : 0;
		const std::uint64_t started_cycles = k_cycle_get_64();
		const std::uint64_t timeout_cycles =
			k_us_to_cyc_ceil64(static_cast<std::uint64_t>(timeout));
		std::uint32_t polls = 0U;

		int raw = readRaw(*description);
		if (raw < 0)
		{
			return 0UL;
		}
		while (raw == target)
		{
			if (pollDeadline(started_cycles, timeout_cycles, cooperative, polls))
			{
				setGpioBackendSuccess();
				return 0UL;
			}
			raw = readRaw(*description);
			if (raw < 0)
			{
				return 0UL;
			}
		}

		while (raw != target)
		{
			if (pollDeadline(started_cycles, timeout_cycles, cooperative, polls))
			{
				setGpioBackendSuccess();
				return 0UL;
			}
			raw = readRaw(*description);
			if (raw < 0)
			{
				return 0UL;
			}
		}

		const std::uint64_t pulse_started_cycles = k_cycle_get_64();
		while (raw == target)
		{
			if (pollDeadline(started_cycles, timeout_cycles, cooperative, polls))
			{
				setGpioBackendSuccess();
				return 0UL;
			}
			raw = readRaw(*description);
			if (raw < 0)
			{
				return 0UL;
			}
		}

		const std::uint64_t elapsed_cycles = k_cycle_get_64() - pulse_started_cycles;
		const std::uint64_t elapsed_microseconds = k_cyc_to_us_floor64(elapsed_cycles);
		setGpioBackendSuccess();
		return static_cast<unsigned long>((elapsed_microseconds == 0U)
										  ? 1U
										  : elapsed_microseconds);
	}

	/** @brief shift API의 output pin을 변경 전에 검증합니다. */
	[[nodiscard]] bool validateOutputPin(pin_size_t pin) noexcept
	{
		const auto logical_pin = static_cast<std::size_t>(pin);
		const PinDescription *const description = pinDescription(logical_pin);
		if (description == nullptr)
		{
			setGpioBackendError(GpioError::invalid_pin);
			return false;
		}
		if (!hasPinCapability(description->capabilities, PinCapability::digital_output))
		{
			setGpioBackendError(GpioError::unsupported_capability);
			return false;
		}
		if (!isPinConfiguredForOutput(logical_pin))
		{
			setGpioBackendError(GpioError::wrong_mode);
			return false;
		}
		return true;
	}

	/** @brief shift API의 bit order 인자를 검증합니다. */
	[[nodiscard]] bool validateBitOrder(BitOrder bit_order) noexcept
	{
		if ((bit_order != LSBFIRST) && (bit_order != MSBFIRST))
		{
			setGpioBackendError(GpioError::invalid_value);
			return false;
		}
		return true;
	}
}

extern "C" unsigned long pulseIn(pin_size_t pin, std::uint8_t state, unsigned long timeout)
{
	return measurePulse(pin, state, timeout, false);
}

extern "C" unsigned long pulseInLong(pin_size_t pin, std::uint8_t state,
										unsigned long timeout)
{
	return measurePulse(pin, state, timeout, true);
}

extern "C" void shiftOut(pin_size_t data_pin, pin_size_t clock_pin, BitOrder bit_order,
							 std::uint8_t value)
{
	if (k_is_in_isr())
	{
		setGpioBackendError(GpioError::invalid_context);
		return;
	}
	if (data_pin == clock_pin)
	{
		setGpioBackendError(GpioError::ownership_conflict);
		return;
	}
	if (!validateBitOrder(bit_order) || !validateOutputPin(data_pin) ||
		!validateOutputPin(clock_pin))
	{
		return;
	}

	for (std::uint8_t index = 0U; index < 8U; ++index)
	{
		const std::uint8_t bit_index =
			(bit_order == LSBFIRST) ? index : static_cast<std::uint8_t>(7U - index);
		const PinStatus state = ((value >> bit_index) & 0x01U) != 0U ? HIGH : LOW;
		digitalWrite(data_pin, state);
		if (lastGpioError() != GpioError::none)
		{
			return;
		}
		digitalWrite(clock_pin, HIGH);
		if (lastGpioError() != GpioError::none)
		{
			return;
		}
		digitalWrite(clock_pin, LOW);
		if (lastGpioError() != GpioError::none)
		{
			return;
		}
	}
	setGpioBackendSuccess();
}

extern "C" std::uint8_t shiftIn(pin_size_t data_pin, pin_size_t clock_pin,
								 BitOrder bit_order)
{
	if (k_is_in_isr())
	{
		setGpioBackendError(GpioError::invalid_context);
		return 0U;
	}
	if (data_pin == clock_pin)
	{
		setGpioBackendError(GpioError::ownership_conflict);
		return 0U;
	}
	if (!validateBitOrder(bit_order) || (inputDescription(data_pin) == nullptr) ||
		!validateOutputPin(clock_pin))
	{
		return 0U;
	}

	std::uint8_t value = 0U;
	for (std::uint8_t index = 0U; index < 8U; ++index)
	{
		digitalWrite(clock_pin, HIGH);
		if (lastGpioError() != GpioError::none)
		{
			return 0U;
		}
		const PinStatus state = digitalRead(data_pin);
		if (lastGpioError() != GpioError::none)
		{
			return 0U;
		}
		const std::uint8_t bit_index =
			(bit_order == LSBFIRST) ? index : static_cast<std::uint8_t>(7U - index);
		if (state == HIGH)
		{
			value = static_cast<std::uint8_t>(value | (1U << bit_index));
		}
		digitalWrite(clock_pin, LOW);
		if (lastGpioError() != GpioError::none)
		{
			return 0U;
		}
	}
	setGpioBackendSuccess();
	return value;
}
