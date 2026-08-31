/**
 * @file wiring_digital.cpp
 * @brief Zephyr GPIO 위에 Arduino digital API를 구현합니다.
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

#include "internal/IoResourceManager.h"
#include "internal/pin_description.h"

namespace
{

	using nucode::arduino::internal::GpioError;
	using nucode::arduino::internal::gpioIoResource;
	using nucode::arduino::internal::hasPinCapability;
	using nucode::arduino::internal::IoAcquirePolicy;
	using nucode::arduino::internal::IoOwnerKind;
	using nucode::arduino::internal::IoResourceLease;
	using nucode::arduino::internal::IoResourceOwner;
	using nucode::arduino::internal::IoResourceResult;
	using nucode::arduino::internal::IoResourceSnapshot;
	using nucode::arduino::internal::IoResourceState;
	using nucode::arduino::internal::PinCapability;
	using nucode::arduino::internal::PinDescription;
	using nucode::arduino::internal::pinDescription;

#if defined(NUM_PIN_ROLES)
	/** @brief sparse Variant를 포함한 논리 pin 상태 slot 개수입니다. */
	constexpr std::size_t pin_slot_count = NUM_PIN_ROLES;
#else
	/** @brief 기존 연속형 시험 Variant의 논리 pin 상태 slot 개수입니다. */
	constexpr std::size_t pin_slot_count = NUM_DIGITAL_PINS;
#endif

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
		output_open_drain,
	};

	/**
	 * @brief 물리 핀 정보를 복제하지 않는 논리 핀별 가변 상태입니다.
	 */
	struct PinRuntimeState
	{
		atomic_t mode;
		atomic_t output_latch;
		IoResourceLease ownership_lease;
	};

	K_MUTEX_DEFINE(gpio_transition_mutex);
	PinRuntimeState pin_runtime_states[pin_slot_count] = {};
	atomic_t last_gpio_error = ATOMIC_INIT(static_cast<atomic_val_t>(GpioError::none));
	atomic_t last_gpio_driver_error = ATOMIC_INIT(0);

	/**
	 * @brief Core에서 허용하는 Devicetree GPIO flag 비트입니다.
	 *
	 * Pull 설정은 Arduino pin mode가 소유하므로 descriptor의 pull flag를 설정 시
	 * 그대로 합치지 않습니다. Polarity는 향후 interrupt 의미를 보존하되 digital
	 * read/write는 raw API를 사용하므로 전기적 HIGH/LOW가 반전되지 않습니다.
	 */
	constexpr gpio_dt_flags_t supported_dt_flags = GPIO_ACTIVE_LOW | GPIO_PULL_UP | GPIO_PULL_DOWN;
	constexpr IoResourceOwner gpio_owner{IoOwnerKind::gpio, 0U};

	/** @brief GPIO mode 전환과 read/write를 직렬화하는 scope lock입니다. */
	class GpioTransitionGuard
	{
	public:
		/** @brief GPIO 전환 mutex를 획득합니다. */
		GpioTransitionGuard() noexcept
		{
			nucode::arduino::internal::lockGpioTransition();
		}

		/** @brief GPIO 전환 mutex를 반환합니다. */
		~GpioTransitionGuard()
		{
			nucode::arduino::internal::unlockGpioTransition();
		}

		GpioTransitionGuard(const GpioTransitionGuard &) = delete;
		GpioTransitionGuard &operator=(const GpioTransitionGuard &) = delete;
	};

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

	/** @brief 소유권 관리자 오류를 GPIO 진단 값으로 변환합니다. */
	void recordOwnershipError(IoResourceResult result) noexcept
	{
		switch (result)
		{
		case IoResourceResult::invalid_context:
			recordError(GpioError::invalid_context);
			break;
		case IoResourceResult::capacity_exhausted:
			recordError(GpioError::resource_exhausted);
			break;
		case IoResourceResult::conflict:
		case IoResourceResult::stale_lease:
		case IoResourceResult::wrong_phase:
			recordError(GpioError::ownership_conflict);
			break;
		case IoResourceResult::invalid_argument:
			recordError(GpioError::invalid_pin);
			break;
		case IoResourceResult::success:
		default:
			recordError(GpioError::ownership_conflict);
			break;
		}
	}

	/** @brief descriptor의 물리 pad를 현재 GPIO backend가 소유하는지 확인합니다. */
	[[nodiscard]] bool isOwnedByGpio(const PinDescription &description) noexcept
	{
		IoResourceSnapshot snapshot{};
		if (nucode::arduino::internal::ioResourceSnapshot(
				gpioIoResource(description.gpio), snapshot) != IoResourceResult::success)
		{
			return false;
		}
		return (snapshot.state == IoResourceState::active) &&
			   (snapshot.owner.kind == gpio_owner.kind) &&
			   (snapshot.owner.instance == gpio_owner.instance);
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
		if ((description == nullptr) || (logical_pin >= pin_slot_count))
		{
			recordError(GpioError::invalid_pin);
			state = nullptr;
			return false;
		}

		state = &pin_runtime_states[logical_pin];
		return true;
	}

	/**
	 * @brief 현재 공개 GPIO API가 허용하는 thread 문맥인지 확인합니다.
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
	 * @brief 현재 Core가 해석할 수 없는 Devicetree flag가 있는지 확인합니다.
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
	void lockGpioTransition() noexcept
	{
		static_cast<void>(k_mutex_lock(&gpio_transition_mutex, K_FOREVER));
	}

	void unlockGpioTransition() noexcept
	{
		static_cast<void>(k_mutex_unlock(&gpio_transition_mutex));
	}

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

	void setGpioBackendError(GpioError error, int driver_error) noexcept
	{
		recordError(error, driver_error);
	}

	void setGpioBackendSuccess() noexcept
	{
		recordSuccess();
	}

	bool isPinConfiguredForInput(std::size_t logical_pin) noexcept
	{
		const PinDescription *const description = pinDescription(logical_pin);
		if ((logical_pin >= pin_slot_count) || (description == nullptr) ||
			!isOwnedByGpio(*description))
		{
			return false;
		}

		const auto mode = static_cast<RuntimePinMode>(
			atomic_get(&pin_runtime_states[logical_pin].mode));
		return (mode == RuntimePinMode::input) ||
			   (mode == RuntimePinMode::input_pullup) ||
			   (mode == RuntimePinMode::input_pulldown);
	}

	bool isPinConfiguredForOutput(std::size_t logical_pin) noexcept
	{
		const PinDescription *const description = pinDescription(logical_pin);
		if ((logical_pin >= pin_slot_count) || (description == nullptr) ||
			!isOwnedByGpio(*description))
		{
			return false;
		}

		const auto mode = static_cast<RuntimePinMode>(
			atomic_get(&pin_runtime_states[logical_pin].mode));
		return (mode == RuntimePinMode::output) ||
			   (mode == RuntimePinMode::output_open_drain);
	}

}

void pinMode(pin_size_t pin, PinMode mode)
{
	if (!checkThreadContext())
	{
		return;
	}
	GpioTransitionGuard transition_guard;

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
	else if (mode == OUTPUT_OPENDRAIN)
	{
		if (!hasPinCapability(description->capabilities, PinCapability::digital_output) ||
			!hasPinCapability(description->capabilities, PinCapability::open_drain))
		{
			recordError(GpioError::unsupported_capability);
			return;
		}

		flags |= (atomic_get(&state->output_latch) != 0)
				 ? (GPIO_OUTPUT_HIGH | GPIO_OPEN_DRAIN)
				 : (GPIO_OUTPUT_LOW | GPIO_OPEN_DRAIN);
		if (hasPinCapability(description->capabilities, PinCapability::digital_input))
		{
			flags |= GPIO_INPUT;
		}
		runtime_mode = RuntimePinMode::output_open_drain;
	}
	else
	{
		recordError(GpioError::invalid_mode);
		return;
	}

	const auto resource = gpioIoResource(description->gpio);
	IoResourceLease ownership_lease{};
	const IoResourceResult reserve_result = nucode::arduino::internal::reserveIoResources(
		gpio_owner, &resource, 1U, IoAcquirePolicy::exclusive, ownership_lease);
	if (reserve_result != IoResourceResult::success)
	{
		recordOwnershipError(reserve_result);
		return;
	}

#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
	/**
	 * 핀 재설정과 동시에 남은 edge callback이 새 mode에서 실행되는 것을
	 * 방지하기 위해 등록된 callback을 먼저 해제합니다.
	 */
	const int detach_result =
		nucode::arduino::internal::detachInterruptForPinTransition(
			static_cast<std::size_t>(pin));
	if (detach_result < 0)
	{
		(void)nucode::arduino::internal::rollbackIoResources(ownership_lease);
		atomic_set(&state->mode, static_cast<atomic_val_t>(RuntimePinMode::unconfigured));
		recordError(GpioError::driver_error, detach_result);
		return;
	}
#endif

	const int result = gpio_pin_configure(description->gpio.port, description->gpio.pin, flags);
	if (result < 0)
	{
		(void)nucode::arduino::internal::rollbackIoResources(ownership_lease);
		atomic_set(&state->mode, static_cast<atomic_val_t>(RuntimePinMode::unconfigured));
		recordError(GpioError::driver_error, result);
		return;
	}

	const bool newly_owned = ownership_lease.entries[0].changed;
	const IoResourceResult commit_result =
		nucode::arduino::internal::commitIoResources(ownership_lease);
	if (commit_result != IoResourceResult::success)
	{
		recordOwnershipError(commit_result);
		return;
	}
	if (newly_owned)
	{
		state->ownership_lease = ownership_lease;
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
	GpioTransitionGuard transition_guard;

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
	if (!isOwnedByGpio(*description))
	{
		recordError(GpioError::ownership_conflict);
		return;
	}

	const auto runtime_mode = static_cast<RuntimePinMode>(atomic_get(&state->mode));
	if ((runtime_mode != RuntimePinMode::output) &&
		(runtime_mode != RuntimePinMode::output_open_drain))
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
	GpioTransitionGuard transition_guard;

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
	if (!isOwnedByGpio(*description))
	{
		recordError(GpioError::ownership_conflict);
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
