/**
 * @file wiring_digital.cpp
 * @brief Zephyr GPIO 위에 M3 Arduino digital API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <variant.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>

#include "internal/pin_description.h"

namespace
{

	using nucode::arduino::internal::GpioError;
	using nucode::arduino::internal::hasPinCapability;
	using nucode::arduino::internal::PinCapability;
	using nucode::arduino::internal::PinDescription;
	using nucode::arduino::internal::pinDescription;

	/**
	 * @brief Core가 성공적으로 적용한 Arduino pin mode입니다.
	 */
	enum class RuntimePinMode : atomic_val_t
	{
		unconfigured = 0,
		input,
		input_pullup,
		input_pulldown,
		output,
	};

	/**
	 * @brief 물리 핀 정보를 복제하지 않는 논리 핀별 가변 상태입니다.
	 */
	struct PinRuntimeState
	{
		atomic_t mode;
		atomic_t output_latch;
	};

	PinRuntimeState pin_runtime_states[NUM_DIGITAL_PINS] = {};
	atomic_t last_gpio_error = ATOMIC_INIT(static_cast<atomic_val_t>(GpioError::none));
	atomic_t last_gpio_driver_error = ATOMIC_INIT(0);

	/**
	 * @brief M3에서 허용하는 Devicetree GPIO flag 비트입니다.
	 *
	 * Pull 설정은 Arduino pin mode가 소유하므로 descriptor의 pull flag를 설정 시
	 * 그대로 합치지 않습니다. Polarity는 향후 interrupt 의미를 보존하되 digital
	 * read/write는 raw API를 사용하므로 전기적 HIGH/LOW가 반전되지 않습니다.
	 */
	constexpr gpio_dt_flags_t supported_dt_flags = GPIO_ACTIVE_LOW | GPIO_PULL_UP | GPIO_PULL_DOWN;

	/**
	 * @brief 오류 번호를 driver 세부값보다 나중에 기록합니다.
	 *
	 * @param error Core 내부 오류 분류입니다.
	 * @param driver_error Zephyr driver가 반환한 원래 오류 번호입니다.
	 */
	void recordError(GpioError error, int driver_error = 0) noexcept
	{
		atomic_set(&last_gpio_driver_error, static_cast<atomic_val_t>(driver_error));
		atomic_set(&last_gpio_error, static_cast<atomic_val_t>(error));
	}

	/**
	 * @brief 성공한 API 호출 뒤 이전 오류 상태를 제거합니다.
	 */
	void recordSuccess() noexcept
	{
		recordError(GpioError::none);
	}

	/**
	 * @brief 논리 핀 설명자와 가변 상태를 안전하게 조회합니다.
	 *
	 * @param pin Arduino 논리 핀입니다.
	 * @param description 조회한 immutable 설명자 주소입니다.
	 * @param state 조회한 가변 상태 주소입니다.
	 * @return 두 주소를 모두 제공할 수 있으면 true입니다.
	 */
	[[nodiscard]] bool lookupPin(pin_size_t pin, const PinDescription *&description,
								 PinRuntimeState *&state) noexcept
	{
		const auto logical_pin = static_cast<std::size_t>(pin);
		description = pinDescription(logical_pin);
		if ((description == nullptr) || (logical_pin >= NUM_DIGITAL_PINS))
		{
			recordError(GpioError::invalid_pin);
			state = nullptr;
			return false;
		}

		state = &pin_runtime_states[logical_pin];
		return true;
	}

	/**
	 * @brief 현재 M3 공개 GPIO API가 허용하는 thread 문맥인지 확인합니다.
	 *
	 * @return thread 문맥이면 true, ISR 문맥이면 false입니다.
	 */
	[[nodiscard]] bool checkThreadContext() noexcept
	{
		if (k_is_in_isr())
		{
			recordError(GpioError::invalid_context);
			return false;
		}

		return true;
	}

	/**
	 * @brief 설명자의 GPIO device가 준비되었는지 확인합니다.
	 *
	 * @param description 검사할 핀 설명자입니다.
	 * @return 준비되었으면 true입니다.
	 */
	[[nodiscard]] bool checkDeviceReady(const PinDescription &description) noexcept
	{
		if (!gpio_is_ready_dt(&description.gpio))
		{
			recordError(GpioError::device_not_ready);
			return false;
		}

		return true;
	}

	/**
	 * @brief 현재 M3가 해석할 수 없는 Devicetree flag가 있는지 확인합니다.
	 *
	 * @param description 검사할 핀 설명자입니다.
	 * @return 모든 flag를 안전하게 처리할 수 있으면 true입니다.
	 */
	[[nodiscard]] bool checkDevicetreeFlags(const PinDescription &description) noexcept
	{
		const auto unsupported = static_cast<gpio_dt_flags_t>(
			description.gpio.dt_flags & static_cast<gpio_dt_flags_t>(~supported_dt_flags));
		if (unsupported != 0U)
		{
			recordError(GpioError::unsupported_devicetree_flags);
			return false;
		}

		return true;
	}

	/**
	 * @brief Devicetree polarity만 GPIO 설정에 보존합니다.
	 *
	 * @param description 대상 핀 설명자입니다.
	 * @return pin mode flag와 결합할 polarity flag입니다.
	 */
	[[nodiscard]] gpio_flags_t polarityFlag(const PinDescription &description) noexcept
	{
		return description.gpio.dt_flags & GPIO_ACTIVE_LOW;
	}

}

namespace nucode::arduino::internal
{

	GpioError lastGpioError() noexcept
	{
		return static_cast<GpioError>(atomic_get(&last_gpio_error));
	}

	int lastGpioDriverError() noexcept
	{
		return static_cast<int>(atomic_get(&last_gpio_driver_error));
	}

	void clearGpioError() noexcept
	{
		recordSuccess();
	}

}

void pinMode(pin_size_t pin, PinMode mode)
{
	if (!checkThreadContext())
	{
		return;
	}

	const PinDescription *description = nullptr;
	PinRuntimeState *state = nullptr;
	if (!lookupPin(pin, description, state))
	{
		return;
	}

	if (!checkDeviceReady(*description) || !checkDevicetreeFlags(*description))
	{
		return;
	}

	gpio_flags_t flags = polarityFlag(*description);
	RuntimePinMode runtime_mode = RuntimePinMode::unconfigured;

	if (mode == INPUT)
	{
		if (!hasPinCapability(description->capabilities, PinCapability::digital_input))
		{
			recordError(GpioError::unsupported_capability);
			return;
		}
		flags |= GPIO_INPUT;
		runtime_mode = RuntimePinMode::input;
	}
	else if (mode == INPUT_PULLUP)
	{
		if (!hasPinCapability(description->capabilities, PinCapability::digital_input))
		{
			recordError(GpioError::unsupported_capability);
			return;
		}
		flags |= GPIO_INPUT | GPIO_PULL_UP;
		runtime_mode = RuntimePinMode::input_pullup;
	}
	else if (mode == INPUT_PULLDOWN)
	{
		if (!hasPinCapability(description->capabilities, PinCapability::digital_input))
		{
			recordError(GpioError::unsupported_capability);
			return;
		}
		flags |= GPIO_INPUT | GPIO_PULL_DOWN;
		runtime_mode = RuntimePinMode::input_pulldown;
	}
	else if (mode == OUTPUT)
	{
		if (!hasPinCapability(description->capabilities, PinCapability::digital_output))
		{
			recordError(GpioError::unsupported_capability);
			return;
		}

		flags |= (atomic_get(&state->output_latch) != 0) ? GPIO_OUTPUT_HIGH
														 : GPIO_OUTPUT_LOW;

		if (hasPinCapability(description->capabilities, PinCapability::digital_input))
		{
			flags |= GPIO_INPUT;
		}
		runtime_mode = RuntimePinMode::output;
	}
	else
	{
		recordError(GpioError::invalid_mode);
		return;
	}

	const int result = gpio_pin_configure(description->gpio.port, description->gpio.pin, flags);
	if (result < 0)
	{
		recordError(GpioError::driver_error, result);
		return;
	}

	atomic_set(&state->mode, static_cast<atomic_val_t>(runtime_mode));
	recordSuccess();
}

void digitalWrite(pin_size_t pin, PinStatus value)
{
	if (!checkThreadContext())
	{
		return;
	}

	if ((value != LOW) && (value != HIGH))
	{
		recordError(GpioError::invalid_value);
		return;
	}

	const PinDescription *description = nullptr;
	PinRuntimeState *state = nullptr;
	if (!lookupPin(pin, description, state))
	{
		return;
	}

	if (!hasPinCapability(description->capabilities, PinCapability::digital_output))
	{
		recordError(GpioError::unsupported_capability);
		return;
	}

	if (atomic_get(&state->mode) != static_cast<atomic_val_t>(RuntimePinMode::output))
	{
		recordError(GpioError::wrong_mode);
		return;
	}

	if (!checkDeviceReady(*description))
	{
		return;
	}

	const atomic_val_t raw_value = (value == HIGH) ? 1 : 0;
	const int result = gpio_pin_set_raw(description->gpio.port, description->gpio.pin,
										static_cast<int>(raw_value));
	if (result < 0)
	{
		recordError(GpioError::driver_error, result);
		return;
	}

	atomic_set(&state->output_latch, raw_value);
	recordSuccess();
}

PinStatus digitalRead(pin_size_t pin)
{
	if (!checkThreadContext())
	{
		return LOW;
	}

	const PinDescription *description = nullptr;
	PinRuntimeState *state = nullptr;
	if (!lookupPin(pin, description, state))
	{
		return LOW;
	}

	if (!hasPinCapability(description->capabilities, PinCapability::digital_input))
	{
		recordError(GpioError::unsupported_capability);
		return LOW;
	}

	if (atomic_get(&state->mode) == static_cast<atomic_val_t>(RuntimePinMode::unconfigured))
	{
		recordError(GpioError::pin_not_configured);
		return LOW;
	}

	if (!checkDeviceReady(*description))
	{
		return LOW;
	}

	const int result = gpio_pin_get_raw(description->gpio.port, description->gpio.pin);
	if (result < 0)
	{
		recordError(GpioError::driver_error, result);
		return LOW;
	}

	recordSuccess();
	return (result == 0) ? LOW : HIGH;
}
