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
#include "internal/PinHandover.h"
#include "internal/pin_description.h"
#if defined(CONFIG_NUCODE_ARDUINO_PWM)
#include "internal/PwmRuntime.h"
#endif

namespace
{

	using nucode::arduino::internal::canonicalPinId;
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
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		nucode::arduino::internal::PinInterruptHandoverState interrupt_recovery;
		bool interrupt_recovery_pending{false};
#endif
		atomic_t handover_faulted;
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

#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
	/** @brief pinMode 실패 뒤 보존한 interrupt snapshot 복원을 재시도합니다. */
	[[nodiscard]] int recoverPendingPinInterrupt(PinRuntimeState &state) noexcept
	{
		if (!state.interrupt_recovery_pending)
		{
			return 0;
		}
		const int result = nucode::arduino::internal::rollbackInterruptForPinHandover(
			state.interrupt_recovery);
		if (result == 0)
		{
			state.interrupt_recovery_pending = false;
		}
		return result;
	}
#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
	/** @brief pinMode rollback용 출력값을 보존하고 analogWrite route를 중지합니다. */
	[[nodiscard]] bool suspendAnalogWriteForGpio(
		pin_size_t pin,
		nucode::arduino::internal::PwmRuntimeSuspendedOutput &snapshot) noexcept
	{
		const std::size_t canonical_pin = canonicalPinId(pin);
		if (canonical_pin >= pin_slot_count)
		{
			return true;
		}

		const auto result = nucode::arduino::internal::pwmRuntimeSuspend(
			nucode::arduino::internal::PwmRuntimeClient::analog_write,
			static_cast<pin_size_t>(canonical_pin), snapshot);
		if ((result != nucode::arduino::internal::PwmRuntimeResult::success) &&
			(result != nucode::arduino::internal::PwmRuntimeResult::not_active))
		{
			recordError(GpioError::driver_error,
						nucode::arduino::internal::lastPwmRuntimeDriverError());
			return false;
		}
		return true;
	}

	/** @brief 실패한 pinMode 뒤 보존한 analogWrite 출력을 복원합니다. */
	void resumeAnalogWriteAfterGpioFailure(
		nucode::arduino::internal::PwmRuntimeSuspendedOutput &snapshot) noexcept
	{
		if (!snapshot.valid)
		{
			return;
		}
		if (nucode::arduino::internal::pwmRuntimeResume(snapshot) !=
			nucode::arduino::internal::PwmRuntimeResult::success)
		{
			recordError(GpioError::driver_error,
						nucode::arduino::internal::lastPwmRuntimeDriverError());
		}
	}
#endif

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
		const auto requested_pin = static_cast<std::size_t>(pin);
		description = pinDescription(requested_pin);
		const auto canonical_pin = canonicalPinId(requested_pin);
		if ((description == nullptr) || (canonical_pin >= pin_slot_count))
		{
			recordError(GpioError::invalid_pin);
			state = nullptr;
			return false;
		}

		state = &pin_runtime_states[canonical_pin];
		return true;
	}

	/** @brief runtime flag 복원 helper가 사용하는 polarity 조회 전방 선언입니다. */
	[[nodiscard]] gpio_flags_t polarityFlag(const PinDescription &description) noexcept;

	/** @brief 저장한 runtime mode를 Zephyr GPIO configure flag로 복원합니다. */
	[[nodiscard]] gpio_flags_t runtimeModeFlags(const PinDescription &description,
												RuntimePinMode mode,
												bool output_latch) noexcept
	{
		gpio_flags_t flags = polarityFlag(description);
		switch (mode)
		{
		case RuntimePinMode::input:
			return flags | GPIO_INPUT;
		case RuntimePinMode::input_pullup:
			return flags | GPIO_INPUT | GPIO_PULL_UP;
		case RuntimePinMode::input_pulldown:
			return flags | GPIO_INPUT | GPIO_PULL_DOWN;
		case RuntimePinMode::output:
			flags |= output_latch ? GPIO_OUTPUT_HIGH : GPIO_OUTPUT_LOW;
			return hasPinCapability(description.capabilities, PinCapability::digital_input)
					   ? flags | GPIO_INPUT
					   : flags;
		case RuntimePinMode::output_open_drain:
			flags |= output_latch ? GPIO_OUTPUT_HIGH : GPIO_OUTPUT_LOW;
			flags |= GPIO_OPEN_DRAIN;
			return hasPinCapability(description.capabilities, PinCapability::digital_input)
					   ? flags | GPIO_INPUT
					   : flags;
		case RuntimePinMode::unconfigured:
		default:
			return GPIO_DISCONNECTED;
		}
	}

	/** @brief ownership manager 결과를 핀 handover 결과로 변환합니다. */
	[[nodiscard]] nucode::arduino::internal::PinHandoverResult handoverResult(
		IoResourceResult result) noexcept
	{
		using nucode::arduino::internal::PinHandoverResult;
		switch (result)
		{
		case IoResourceResult::success:
			return PinHandoverResult::success;
		case IoResourceResult::invalid_context:
			return PinHandoverResult::invalid_context;
		case IoResourceResult::invalid_argument:
			return PinHandoverResult::invalid_argument;
		case IoResourceResult::wrong_phase:
			return PinHandoverResult::wrong_phase;
		case IoResourceResult::conflict:
		case IoResourceResult::capacity_exhausted:
		case IoResourceResult::stale_lease:
		default:
			return PinHandoverResult::ownership_conflict;
		}
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

	/** @brief PWM를 중지하기 전에 pinMode 요청의 불변 조건을 모두 검증합니다. */
	[[nodiscard]] bool preflightPinMode(pin_size_t pin, PinMode mode) noexcept
	{
		const PinDescription *const description = pinDescription(pin);
		const std::size_t canonical_pin = canonicalPinId(pin);
		if (description == nullptr || canonical_pin >= pin_slot_count)
		{
			recordError(GpioError::invalid_pin);
			return false;
		}
		if (!checkDeviceReady(*description) || !checkDevicetreeFlags(*description))
		{
			return false;
		}

		if (mode == INPUT || mode == INPUT_PULLUP || mode == INPUT_PULLDOWN)
		{
			if (!hasPinCapability(description->capabilities, PinCapability::digital_input))
			{
				recordError(GpioError::unsupported_capability);
				return false;
			}
			return true;
		}
		if (mode == OUTPUT)
		{
			if (!hasPinCapability(description->capabilities, PinCapability::digital_output))
			{
				recordError(GpioError::unsupported_capability);
				return false;
			}
			return true;
		}
		if (mode == OUTPUT_OPENDRAIN)
		{
			if (!hasPinCapability(description->capabilities, PinCapability::digital_output) ||
				!hasPinCapability(description->capabilities, PinCapability::open_drain))
			{
				recordError(GpioError::unsupported_capability);
				return false;
			}
			return true;
		}

		recordError(GpioError::invalid_mode);
		return false;
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
		const std::size_t canonical_pin = canonicalPinId(logical_pin);
		if ((canonical_pin >= pin_slot_count) || (description == nullptr) ||
			(atomic_get(&pin_runtime_states[canonical_pin].handover_faulted) != 0) ||
			!isOwnedByGpio(*description))
		{
			return false;
		}

		const auto mode = static_cast<RuntimePinMode>(
			atomic_get(&pin_runtime_states[canonical_pin].mode));
		return (mode == RuntimePinMode::input) ||
			   (mode == RuntimePinMode::input_pullup) ||
			   (mode == RuntimePinMode::input_pulldown);
	}

	bool isPinConfiguredForOutput(std::size_t logical_pin) noexcept
	{
		const PinDescription *const description = pinDescription(logical_pin);
		const std::size_t canonical_pin = canonicalPinId(logical_pin);
		if ((canonical_pin >= pin_slot_count) || (description == nullptr) ||
			(atomic_get(&pin_runtime_states[canonical_pin].handover_faulted) != 0) ||
			!isOwnedByGpio(*description))
		{
			return false;
		}

		const auto mode = static_cast<RuntimePinMode>(
			atomic_get(&pin_runtime_states[canonical_pin].mode));
		return (mode == RuntimePinMode::output) ||
			   (mode == RuntimePinMode::output_open_drain);
	}

	bool isGpioPinHandoverFaulted(std::size_t logical_pin) noexcept
	{
		const std::size_t canonical_pin = canonicalPinId(logical_pin);
		return canonical_pin >= pin_slot_count ||
			   atomic_get(&pin_runtime_states[canonical_pin].handover_faulted) != 0;
	}

	PinHandoverResult beginGpioPinHandover(std::size_t logical_pin,
										   IoResourceOwner target_owner,
										   GpioPinHandover &handover) noexcept
	{
		if (k_is_in_isr())
		{
			return PinHandoverResult::invalid_context;
		}
		if ((target_owner.kind == IoOwnerKind::none) ||
			(handover.phase == PinHandoverPhase::prepared) ||
			(handover.phase == PinHandoverPhase::committed) ||
			(handover.phase == PinHandoverPhase::faulted))
		{
			return PinHandoverResult::invalid_argument;
		}

		lockGpioTransition();
		handover = {};
		handover.lock_held = true;
		handover.requested_pin = logical_pin;
		handover.canonical_pin = canonicalPinId(logical_pin);
		handover.target_owner = target_owner;
		const PinDescription *const description = pinDescription(logical_pin);
		if ((description == nullptr) || (handover.canonical_pin >= pin_slot_count))
		{
			unlockGpioTransition();
			handover.lock_held = false;
			return PinHandoverResult::invalid_pin;
		}
		if (description->policy == PinPolicy::system_reserved)
		{
			unlockGpioTransition();
			handover.lock_held = false;
			return PinHandoverResult::unsupported;
		}
		if (!gpio_is_ready_dt(&description->gpio))
		{
			unlockGpioTransition();
			handover.lock_held = false;
			return PinHandoverResult::device_not_ready;
		}

		PinRuntimeState &runtime = pin_runtime_states[handover.canonical_pin];
		if (atomic_get(&runtime.handover_faulted) != 0
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
			|| runtime.interrupt_recovery_pending
#endif
		)
		{
			unlockGpioTransition();
			handover.lock_held = false;
			return PinHandoverResult::driver_error;
		}
		handover.previous_mode = static_cast<std::uint8_t>(atomic_get(&runtime.mode));
		handover.previous_output_latch = atomic_get(&runtime.output_latch) != 0;
		const IoResourceId resource = gpioIoResource(description->gpio);
		IoResourceSnapshot snapshot{};
		const IoResourceResult snapshot_result = ioResourceSnapshot(resource, snapshot);
		if (snapshot_result != IoResourceResult::success)
		{
			unlockGpioTransition();
			handover.lock_held = false;
			return handoverResult(snapshot_result);
		}

		IoResourceResult reserve_result = IoResourceResult::conflict;
		if (snapshot.state == IoResourceState::free)
		{
			reserve_result = reserveIoResources(target_owner, &resource, 1U,
												IoAcquirePolicy::exclusive,
												handover.ownership_lease);
		}
		else if ((snapshot.state == IoResourceState::active) &&
				 (snapshot.owner.kind == gpio_owner.kind) &&
				 (snapshot.owner.instance == gpio_owner.instance))
		{
			handover.previous_gpio_owned = true;
			reserve_result = transferIoResources(gpio_owner, target_owner, &resource, 1U,
												 handover.ownership_lease);
		}
		if (reserve_result != IoResourceResult::success)
		{
			unlockGpioTransition();
			handover.lock_held = false;
			return handoverResult(reserve_result);
		}

#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		const int interrupt_result = suspendInterruptForPinHandover(
			handover.canonical_pin, handover.interrupt);
		if (interrupt_result < 0)
		{
			const int interrupt_rollback =
				rollbackInterruptForPinHandover(handover.interrupt);
			const IoResourceResult ownership_rollback =
				rollbackIoResources(handover.ownership_lease);
			const bool cleanup_failed = interrupt_rollback < 0 ||
										ownership_rollback != IoResourceResult::success;
			handover.phase = cleanup_failed ? PinHandoverPhase::faulted
											: PinHandoverPhase::rolled_back;
			atomic_set(&runtime.handover_faulted, cleanup_failed ? 1 : 0);
			unlockGpioTransition();
			handover.lock_held = false;
			return ownership_rollback != IoResourceResult::success
					   ? handoverResult(ownership_rollback)
					   : PinHandoverResult::driver_error;
		}
#endif

		const auto previous_mode = static_cast<RuntimePinMode>(handover.previous_mode);
		if (handover.previous_gpio_owned &&
			(previous_mode != RuntimePinMode::unconfigured))
		{
			const int disconnect_result = gpio_pin_configure(
				description->gpio.port, description->gpio.pin, GPIO_DISCONNECTED);
			if (disconnect_result < 0)
			{
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
				const int interrupt_rollback =
					rollbackInterruptForPinHandover(handover.interrupt);
#else
				const int interrupt_rollback = 0;
#endif
				const IoResourceResult ownership_rollback =
					rollbackIoResources(handover.ownership_lease);
				const bool cleanup_failed = interrupt_rollback < 0 ||
											ownership_rollback != IoResourceResult::success;
				handover.phase = cleanup_failed ? PinHandoverPhase::faulted
												: PinHandoverPhase::rolled_back;
				atomic_set(&runtime.handover_faulted, cleanup_failed ? 1 : 0);
				unlockGpioTransition();
				handover.lock_held = false;
				return ownership_rollback != IoResourceResult::success
						   ? handoverResult(ownership_rollback)
						   : PinHandoverResult::driver_error;
			}
		}
		handover.phase = PinHandoverPhase::prepared;
		return PinHandoverResult::success;
	}

	PinHandoverResult rollbackGpioPinHandover(GpioPinHandover &handover) noexcept
	{
		if (handover.phase != PinHandoverPhase::prepared || !handover.lock_held)
		{
			return PinHandoverResult::wrong_phase;
		}
		const PinDescription *const description = pinDescription(handover.canonical_pin);
		if (description == nullptr)
		{
			unlockGpioTransition();
			handover.lock_held = false;
			return PinHandoverResult::invalid_pin;
		}

		int driver_result = 0;
		const auto previous_mode = static_cast<RuntimePinMode>(handover.previous_mode);
		if (handover.previous_gpio_owned &&
			(previous_mode != RuntimePinMode::unconfigured))
		{
			driver_result = gpio_pin_configure(
				description->gpio.port, description->gpio.pin,
				runtimeModeFlags(*description, previous_mode,
								 handover.previous_output_latch));
		}
		const IoResourceResult ownership_result = rollbackIoResources(
			handover.ownership_lease);
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		const int interrupt_result = rollbackInterruptForPinHandover(handover.interrupt);
		if ((driver_result == 0) && (interrupt_result < 0))
		{
			driver_result = interrupt_result;
		}
#endif
		handover.phase =
			(ownership_result == IoResourceResult::success && driver_result >= 0)
				? PinHandoverPhase::rolled_back
				: PinHandoverPhase::faulted;
		if (handover.phase == PinHandoverPhase::faulted &&
			handover.canonical_pin < pin_slot_count)
		{
			atomic_set(&pin_runtime_states[handover.canonical_pin].handover_faulted, 1);
		}
		unlockGpioTransition();
		handover.lock_held = false;
		if (ownership_result != IoResourceResult::success)
		{
			return handoverResult(ownership_result);
		}
		return driver_result < 0 ? PinHandoverResult::driver_error
								 : PinHandoverResult::success;
	}

	PinHandoverResult commitGpioPinHandover(GpioPinHandover &handover) noexcept
	{
		if (handover.phase != PinHandoverPhase::prepared || !handover.lock_held)
		{
			return PinHandoverResult::wrong_phase;
		}
		const IoResourceResult result = commitIoResources(handover.ownership_lease);
		if (result != IoResourceResult::success)
		{
			const PinHandoverResult rollback_result = rollbackGpioPinHandover(handover);
			return rollback_result == PinHandoverResult::success
					   ? handoverResult(result)
					   : rollback_result;
		}
		PinRuntimeState &runtime = pin_runtime_states[handover.canonical_pin];
		atomic_set(&runtime.mode, static_cast<atomic_val_t>(RuntimePinMode::unconfigured));
		runtime.ownership_lease = {};
		handover.phase = PinHandoverPhase::committed;
		unlockGpioTransition();
		handover.lock_held = false;
		return PinHandoverResult::success;
	}

	PinHandoverResult abandonGpioPinHandoverFailClosed(
		GpioPinHandover &handover) noexcept
	{
		if (handover.phase != PinHandoverPhase::prepared || !handover.lock_held ||
			handover.canonical_pin >= pin_slot_count)
		{
			return PinHandoverResult::wrong_phase;
		}
		PinRuntimeState &runtime = pin_runtime_states[handover.canonical_pin];
		atomic_set(&runtime.handover_faulted, 1);
		handover.phase = PinHandoverPhase::faulted;
		handover.lock_held = false;
		unlockGpioTransition();
		return PinHandoverResult::success;
	}

	PinHandoverResult restoreGpioAfterPeripheral(GpioPinHandover &handover) noexcept
	{
		if (k_is_in_isr())
		{
			return PinHandoverResult::invalid_context;
		}
		if (handover.phase != PinHandoverPhase::committed)
		{
			return PinHandoverResult::wrong_phase;
		}
		lockGpioTransition();
		const PinDescription *const description = pinDescription(handover.canonical_pin);
		if (description == nullptr)
		{
			unlockGpioTransition();
			return PinHandoverResult::invalid_pin;
		}

		if (!handover.previous_gpio_owned)
		{
			const IoResourceResult release_result = releaseIoResources(
				handover.ownership_lease);
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
			const int interrupt_result = release_result == IoResourceResult::success
											 ? commitInterruptForPinHandover(handover.interrupt)
											 : 0;
#else
			const int interrupt_result = 0;
#endif
			if (release_result == IoResourceResult::success && interrupt_result >= 0)
			{
				handover.phase = PinHandoverPhase::rolled_back;
			}
			else if (release_result != IoResourceResult::success || interrupt_result < 0)
			{
				handover.phase = PinHandoverPhase::faulted;
				atomic_set(&pin_runtime_states[handover.canonical_pin].handover_faulted, 1);
			}
			unlockGpioTransition();
			return release_result != IoResourceResult::success
					   ? handoverResult(release_result)
					   : (interrupt_result < 0 ? PinHandoverResult::driver_error
											   : PinHandoverResult::success);
		}

		const IoResourceId resource = gpioIoResource(description->gpio);
		IoResourceLease restore_lease{};
		const IoResourceResult reserve_result = transferIoResources(
			handover.target_owner, gpio_owner, &resource, 1U, restore_lease);
		if (reserve_result != IoResourceResult::success)
		{
			unlockGpioTransition();
			return handoverResult(reserve_result);
		}

		const auto previous_mode = static_cast<RuntimePinMode>(handover.previous_mode);
		int driver_result = 0;
		if (previous_mode != RuntimePinMode::unconfigured)
		{
			driver_result = gpio_pin_configure(
				description->gpio.port, description->gpio.pin,
				runtimeModeFlags(*description, previous_mode,
								 handover.previous_output_latch));
		}
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		if (driver_result == 0)
		{
			driver_result = rollbackInterruptForPinHandover(handover.interrupt);
		}
#endif
		if (driver_result < 0)
		{
			const int disconnect_result = gpio_pin_configure(
				description->gpio.port, description->gpio.pin, GPIO_DISCONNECTED);
			const IoResourceResult rollback_result = rollbackIoResources(restore_lease);
			if (disconnect_result < 0 || rollback_result != IoResourceResult::success)
			{
				atomic_set(&pin_runtime_states[handover.canonical_pin].handover_faulted, 1);
				handover.phase = PinHandoverPhase::faulted;
			}
			unlockGpioTransition();
			return PinHandoverResult::driver_error;
		}

		const IoResourceResult commit_result = commitIoResources(restore_lease);
		if (commit_result != IoResourceResult::success)
		{
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
			/** ownership 확정 실패 시 이미 복원한 callback을 다시 정지해
			 * 다음 restore 재시도에 사용할 snapshot을 보존합니다. */
			const int interrupt_suspend_result = suspendInterruptForPinHandover(
				handover.canonical_pin, handover.interrupt);
#else
			const int interrupt_suspend_result = 0;
#endif
			const int disconnect_result = gpio_pin_configure(
				description->gpio.port, description->gpio.pin, GPIO_DISCONNECTED);
			const IoResourceResult rollback_result = rollbackIoResources(restore_lease);
			if (interrupt_suspend_result < 0 || disconnect_result < 0 ||
				rollback_result != IoResourceResult::success)
			{
				atomic_set(&pin_runtime_states[handover.canonical_pin].handover_faulted, 1);
				handover.phase = PinHandoverPhase::faulted;
			}
			unlockGpioTransition();
			return handoverResult(commit_result);
		}
		PinRuntimeState &runtime = pin_runtime_states[handover.canonical_pin];
		runtime.ownership_lease = restore_lease;
		atomic_set(&runtime.mode, static_cast<atomic_val_t>(previous_mode));
		atomic_set(&runtime.output_latch, handover.previous_output_latch ? 1 : 0);
		handover.phase = PinHandoverPhase::rolled_back;
		unlockGpioTransition();
		return PinHandoverResult::success;
	}

	PinHandoverResult releasePeripheralPinHandover(GpioPinHandover &handover) noexcept
	{
		if (k_is_in_isr())
		{
			return PinHandoverResult::invalid_context;
		}
		if (handover.phase != PinHandoverPhase::committed)
		{
			return PinHandoverResult::wrong_phase;
		}
		lockGpioTransition();
		const IoResourceResult release_result = releaseIoResources(
			handover.ownership_lease);
		if (release_result != IoResourceResult::success)
		{
			unlockGpioTransition();
			return handoverResult(release_result);
		}
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		const int interrupt_result = commitInterruptForPinHandover(handover.interrupt);
#else
		const int interrupt_result = 0;
#endif
		handover.phase = interrupt_result < 0 ? PinHandoverPhase::faulted
											  : PinHandoverPhase::rolled_back;
		if (handover.phase == PinHandoverPhase::faulted &&
			handover.canonical_pin < pin_slot_count)
		{
			atomic_set(&pin_runtime_states[handover.canonical_pin].handover_faulted, 1);
		}
		unlockGpioTransition();
		return interrupt_result < 0 ? PinHandoverResult::driver_error
									: PinHandoverResult::success;
	}

}

void pinMode(pin_size_t pin, PinMode mode)
{
	if (!checkThreadContext())
	{
		return;
	}
	if (!preflightPinMode(pin, mode))
	{
		return;
	}
#if defined(CONFIG_NUCODE_ARDUINO_PWM)
	/** @brief PWM allocator와 GPIO 전환 mutex의 잠금 순서를 일정하게 유지합니다. */
	nucode::arduino::internal::PwmRuntimeSuspendedOutput suspended_pwm{};
	if (!suspendAnalogWriteForGpio(pin, suspended_pwm))
	{
		return;
	}
#endif
	bool transition_recoverable = true;
	const bool configured = [&]() noexcept -> bool
	{
		GpioTransitionGuard transition_guard;

		const PinDescription *description = nullptr;
		PinRuntimeState *state = nullptr;
		if (!lookupPin(pin, description, state) || !checkDeviceReady(*description) ||
			!checkDevicetreeFlags(*description))
		{
			return false;
		}
		if (atomic_get(&state->handover_faulted) != 0)
		{
			transition_recoverable = false;
			recordError(GpioError::ownership_conflict);
			return false;
		}
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		const int pending_recovery = recoverPendingPinInterrupt(*state);
		if (pending_recovery < 0)
		{
			transition_recoverable = false;
			recordError(GpioError::driver_error, pending_recovery);
			return false;
		}
#endif

		const RuntimePinMode previous_mode =
			static_cast<RuntimePinMode>(atomic_get(&state->mode));
		const bool previous_latch = atomic_get(&state->output_latch) != 0;
		gpio_flags_t flags = polarityFlag(*description);
		RuntimePinMode runtime_mode = RuntimePinMode::unconfigured;

		if (mode == INPUT)
		{
			flags |= GPIO_INPUT;
			runtime_mode = RuntimePinMode::input;
		}
		else if (mode == INPUT_PULLUP)
		{
			flags |= GPIO_INPUT | GPIO_PULL_UP;
			runtime_mode = RuntimePinMode::input_pullup;
		}
		else if (mode == INPUT_PULLDOWN)
		{
			flags |= GPIO_INPUT | GPIO_PULL_DOWN;
			runtime_mode = RuntimePinMode::input_pulldown;
		}
		else if (mode == OUTPUT)
		{
			flags |= previous_latch ? GPIO_OUTPUT_HIGH : GPIO_OUTPUT_LOW;
			if (hasPinCapability(description->capabilities, PinCapability::digital_input))
			{
				flags |= GPIO_INPUT;
			}
			runtime_mode = RuntimePinMode::output;
		}
		else
		{
			flags |= previous_latch ? (GPIO_OUTPUT_HIGH | GPIO_OPEN_DRAIN)
									: (GPIO_OUTPUT_LOW | GPIO_OPEN_DRAIN);
			if (hasPinCapability(description->capabilities, PinCapability::digital_input))
			{
				flags |= GPIO_INPUT;
			}
			runtime_mode = RuntimePinMode::output_open_drain;
		}

		const auto resource = gpioIoResource(description->gpio);
		IoResourceLease ownership_lease{};
		const IoResourceResult reserve_result =
			nucode::arduino::internal::reserveIoResources(
				gpio_owner, &resource, 1U, IoAcquirePolicy::exclusive, ownership_lease);
		if (reserve_result != IoResourceResult::success)
		{
			recordOwnershipError(reserve_result);
			return false;
		}

#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		/**
		 * 핀 재설정 중 callback 실행만 정지하고, 모든 GPIO 전환이 성공한 뒤
		 * snapshot을 폐기합니다. 중간 실패에서는 같은 snapshot으로 복원합니다.
		 */
		state->interrupt_recovery = {};
		const int suspend_result =
			nucode::arduino::internal::suspendInterruptForPinHandover(
				static_cast<std::size_t>(pin), state->interrupt_recovery);
		state->interrupt_recovery_pending = state->interrupt_recovery.registered;
		if (suspend_result < 0)
		{
			const int interrupt_rollback = recoverPendingPinInterrupt(*state);
			const IoResourceResult ownership_rollback =
				nucode::arduino::internal::rollbackIoResources(ownership_lease);
			transition_recoverable = interrupt_rollback >= 0 &&
									 ownership_rollback == IoResourceResult::success;
			if (ownership_rollback != IoResourceResult::success)
			{
				atomic_set(&state->handover_faulted, 1);
			}
			recordError(GpioError::driver_error,
						interrupt_rollback < 0 ? interrupt_rollback : suspend_result);
			return false;
		}
#endif

		const int result =
			gpio_pin_configure(description->gpio.port, description->gpio.pin, flags);
		if (result < 0)
		{
			const IoResourceResult ownership_rollback =
				nucode::arduino::internal::rollbackIoResources(ownership_lease);
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
			const int interrupt_rollback = recoverPendingPinInterrupt(*state);
#else
			const int interrupt_rollback = 0;
#endif
			transition_recoverable = interrupt_rollback >= 0 &&
									 ownership_rollback == IoResourceResult::success;
			if (ownership_rollback != IoResourceResult::success)
			{
				atomic_set(&state->handover_faulted, 1);
			}
			recordError(GpioError::driver_error,
						interrupt_rollback < 0 ? interrupt_rollback : result);
			return false;
		}

		const bool newly_owned = ownership_lease.entries[0].changed;
		const IoResourceResult commit_result =
			nucode::arduino::internal::commitIoResources(ownership_lease);
		if (commit_result != IoResourceResult::success)
		{
			const int restore_result = gpio_pin_configure(
				description->gpio.port, description->gpio.pin,
				runtimeModeFlags(*description, previous_mode, previous_latch));
			const IoResourceResult ownership_rollback =
				nucode::arduino::internal::rollbackIoResources(ownership_lease);
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
			const int interrupt_rollback = recoverPendingPinInterrupt(*state);
#else
			const int interrupt_rollback = 0;
#endif
			transition_recoverable = restore_result >= 0 && interrupt_rollback >= 0 &&
									 ownership_rollback == IoResourceResult::success;
			if (restore_result < 0 || ownership_rollback != IoResourceResult::success)
			{
				atomic_set(&state->handover_faulted, 1);
			}
			if (restore_result < 0 || interrupt_rollback < 0)
			{
				recordError(GpioError::driver_error,
							interrupt_rollback < 0 ? interrupt_rollback : restore_result);
			}
			else
			{
				recordOwnershipError(commit_result);
			}
			return false;
		}

#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
		const int interrupt_commit =
			nucode::arduino::internal::commitInterruptForPinHandover(
				state->interrupt_recovery);
		if (interrupt_commit < 0)
		{
			const int interrupt_rollback = recoverPendingPinInterrupt(*state);
			const int restore_result = gpio_pin_configure(
				description->gpio.port, description->gpio.pin,
				runtimeModeFlags(*description, previous_mode, previous_latch));
			transition_recoverable =
				interrupt_rollback >= 0 && restore_result >= 0;
			if (restore_result < 0)
			{
				atomic_set(&state->handover_faulted, 1);
			}
			recordError(GpioError::driver_error,
						interrupt_rollback < 0 ? interrupt_rollback : interrupt_commit);
			return false;
		}
		state->interrupt_recovery_pending = false;
#endif
		if (newly_owned)
		{
			state->ownership_lease = ownership_lease;
		}

		atomic_set(&state->mode, static_cast<atomic_val_t>(runtime_mode));
		recordSuccess();
		return true;
	}();

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
	if (!configured && transition_recoverable)
	{
		resumeAnalogWriteAfterGpioFailure(suspended_pwm);
	}
#else
	static_cast<void>(configured);
	static_cast<void>(transition_recoverable);
#endif
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
	if (atomic_get(&state->handover_faulted) != 0)
	{
		recordError(GpioError::ownership_conflict);
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
	if (atomic_get(&state->handover_faulted) != 0)
	{
		recordError(GpioError::ownership_conflict);
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
