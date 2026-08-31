/**
 * @file wiring_interrupt.cpp
 * @brief Zephyr GPIO callback 위에 Arduino edge·level interrupt API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <variant.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/spinlock.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <limits.h>
#include <errno.h>
#include <cstddef>
#include <cstdint>

#include "internal/pin_description.h"

namespace
{

	using nucode::arduino::internal::GpioError;
	using nucode::arduino::internal::hasPinCapability;
	using nucode::arduino::internal::isPinConfiguredForInput;
	using nucode::arduino::internal::PinCapability;
	using nucode::arduino::internal::PinDescription;
	using nucode::arduino::internal::pinDescription;
	using nucode::arduino::internal::setGpioBackendError;
	using nucode::arduino::internal::setGpioBackendSuccess;

#if defined(NUM_PIN_ROLES)
	/** @brief sparse Variant를 포함한 interrupt slot 개수입니다. */
	constexpr std::size_t pin_slot_count = NUM_PIN_ROLES;
#else
	/** @brief 기존 연속형 시험 Variant의 interrupt slot 개수입니다. */
	constexpr std::size_t pin_slot_count = NUM_DIGITAL_PINS;
#endif

	/** @brief callback slot에 저장된 사용자 함수 형식입니다. */
	enum class CallbackKind : std::uint8_t
	{
		none = 0U,
		simple,
		parameter,
	};

	/** @brief Arduino interrupt의 전기적 trigger 종류입니다. */
	enum class TriggerKind : std::uint8_t
	{
		edge = 0U,
		level_low,
		level_high,
	};

	/** @brief 하나의 Arduino 논리 핀에 대응하는 고정 interrupt 상태입니다. */
	struct InterruptSlot
	{
		struct gpio_callback gpio_callback;
		struct k_spinlock lock;
		struct k_work_delayable level_rearm_work;
		atomic_t in_flight;
		atomic_t level_latched;
		atomic_t generation;
		bool work_initialized;
		bool registered;
		bool active;
		bool suspended;
		std::size_t logical_pin;
		gpio_flags_t trigger_flags;
		TriggerKind trigger_kind;
		CallbackKind callback_kind;
		voidFuncPtr simple_callback;
		voidFuncPtrParam parameter_callback;
		void *parameter;
	};

	InterruptSlot interrupt_slots[pin_slot_count] = {};
	K_MUTEX_DEFINE(interrupt_configuration_mutex);
	atomic_t callback_mask_depth = ATOMIC_INIT(0);
	k_tid_t callback_mask_owner = nullptr;

	/** @brief level trigger가 해제되었는지 다시 확인하는 기본 간격입니다. */
	constexpr k_timeout_t level_rearm_interval = K_MSEC(1);

	/**
	 * @brief Arduino mode를 Zephyr raw electrical interrupt flag로 변환합니다.
	 *
	 * @param mode Arduino interrupt mode입니다.
	 * @param flags 변환한 Zephyr flag를 받을 주소입니다.
	 * @param trigger_kind trigger 종류를 받을 주소입니다.
	 * @return 지원하는 mode이면 true입니다.
	 */
	[[nodiscard]] bool interruptFlags(PinStatus mode, gpio_flags_t &flags,
									 TriggerKind &trigger_kind) noexcept
	{
		switch (mode)
		{
		case LOW:
			flags = GPIO_INT_LEVEL_LOW;
			trigger_kind = TriggerKind::level_low;
			return true;
		case HIGH:
			flags = GPIO_INT_LEVEL_HIGH;
			trigger_kind = TriggerKind::level_high;
			return true;
		case RISING:
			flags = GPIO_INT_EDGE_RISING;
			trigger_kind = TriggerKind::edge;
			return true;
		case FALLING:
			flags = GPIO_INT_EDGE_FALLING;
			trigger_kind = TriggerKind::edge;
			return true;
		case CHANGE:
			flags = GPIO_INT_EDGE_BOTH;
			trigger_kind = TriggerKind::edge;
			return true;
		default:
			return false;
		}
	}

	/** @brief raw GPIO 값이 지정한 level trigger를 만족하는지 확인합니다. */
	[[nodiscard]] bool isLevelAsserted(TriggerKind trigger_kind, int raw_value) noexcept
	{
		return ((trigger_kind == TriggerKind::level_low) && (raw_value == 0)) ||
			   ((trigger_kind == TriggerKind::level_high) && (raw_value != 0));
	}

	/**
	 * @brief callback mask 복원 중 이미 assert된 level을 한 번 다시 전달되도록 재무장합니다.
	 *
	 * @details level IRQ는 mask 상태에서 최초 configure event가 소비될 수 있습니다. 전체
	 * Arduino callback mask를 해제한 뒤 raw level을 확인하고, 아직 callback이 전달되지 않은
	 * assert 상태만 disable/configure 순서로 다시 재무장합니다.
	 *
	 * @param slot 확인할 interrupt slot입니다.
	 * @return 성공 또는 처리할 level이 없으면 0, GPIO driver가 실패하면 음수 오류입니다.
	 */
	[[nodiscard]] int retriggerAssertedLevel(InterruptSlot &slot) noexcept
	{
		std::size_t logical_pin = 0U;
		gpio_flags_t trigger_flags = 0U;
		TriggerKind trigger_kind = TriggerKind::edge;

		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		const bool eligible = slot.registered && slot.active && !slot.suspended &&
						  (slot.trigger_kind != TriggerKind::edge) &&
						  (atomic_get(&slot.level_latched) == 0) &&
						  (atomic_get(&callback_mask_depth) == 0);
		if (eligible)
		{
			logical_pin = slot.logical_pin;
			trigger_flags = slot.trigger_flags;
			trigger_kind = slot.trigger_kind;
		}
		k_spin_unlock(&slot.lock, key);
		if (!eligible)
		{
			return 0;
		}

		const PinDescription *const description = pinDescription(logical_pin);
		if ((description == nullptr) || !gpio_is_ready_dt(&description->gpio))
		{
			return -ENODEV;
		}

		const int raw_value = gpio_pin_get_raw(description->gpio.port, description->gpio.pin);
		if (raw_value < 0)
		{
			return raw_value;
		}
		if (!isLevelAsserted(trigger_kind, raw_value))
		{
			return 0;
		}

		const k_spinlock_key_t recheck_key = k_spin_lock(&slot.lock);
		const bool still_eligible = slot.registered && slot.active && !slot.suspended &&
								(slot.trigger_kind == trigger_kind) &&
								(atomic_get(&slot.level_latched) == 0) &&
								(atomic_get(&callback_mask_depth) == 0);
		k_spin_unlock(&slot.lock, recheck_key);
		if (!still_eligible)
		{
			return 0;
		}

		int result = gpio_pin_interrupt_configure(description->gpio.port,
											 description->gpio.pin,
											 GPIO_INT_DISABLE);
		if (result < 0)
		{
			return result;
		}
		result = gpio_pin_interrupt_configure(description->gpio.port,
										 description->gpio.pin,
										 trigger_flags);
		return result;
	}

	/** @brief level이 해제될 때까지 polling한 뒤 같은 trigger를 재무장합니다. */
	void levelRearmHandler(struct k_work *work)
	{
		auto *delayable = k_work_delayable_from_work(work);
		auto *slot = CONTAINER_OF(delayable, InterruptSlot, level_rearm_work);

		std::size_t logical_pin = 0U;
		TriggerKind trigger_kind = TriggerKind::edge;
		gpio_flags_t trigger_flags = 0U;
		atomic_val_t generation = 0;

		const k_spinlock_key_t key = k_spin_lock(&slot->lock);
		const bool eligible = slot->registered && slot->active && !slot->suspended &&
							  (slot->trigger_kind != TriggerKind::edge) &&
							  (atomic_get(&callback_mask_depth) == 0);
		if (eligible)
		{
			logical_pin = slot->logical_pin;
			trigger_kind = slot->trigger_kind;
			trigger_flags = slot->trigger_flags;
			generation = atomic_get(&slot->generation);
		}
		k_spin_unlock(&slot->lock, key);

		if (!eligible)
		{
			return;
		}

		const PinDescription *const description = pinDescription(logical_pin);
		if ((description == nullptr) || !gpio_is_ready_dt(&description->gpio))
		{
			setGpioBackendError(GpioError::device_not_ready);
			return;
		}

		const int raw_value = gpio_pin_get_raw(description->gpio.port, description->gpio.pin);
		if (raw_value < 0)
		{
			setGpioBackendError(GpioError::driver_error, raw_value);
			return;
		}

		if (isLevelAsserted(trigger_kind, raw_value))
		{
			static_cast<void>(k_work_reschedule(&slot->level_rearm_work,
										 level_rearm_interval));
			return;
		}

		const k_spinlock_key_t recheck_key = k_spin_lock(&slot->lock);
		const bool still_eligible = slot->registered && slot->active && !slot->suspended &&
								(atomic_get(&slot->generation) == generation) &&
								(atomic_get(&callback_mask_depth) == 0);
		if (still_eligible)
		{
			atomic_set(&slot->level_latched, 0);
		}
		k_spin_unlock(&slot->lock, recheck_key);
		if (!still_eligible)
		{
			return;
		}

		const int result = gpio_pin_interrupt_configure(description->gpio.port,
												 description->gpio.pin,
												 trigger_flags);
		if (result < 0)
		{
			setGpioBackendError(GpioError::driver_error, result);
			return;
		}

		const k_spinlock_key_t final_key = k_spin_lock(&slot->lock);
		const bool became_stale = !slot->registered || !slot->active || slot->suspended ||
								  (atomic_get(&slot->generation) != generation) ||
								  (atomic_get(&callback_mask_depth) != 0);
		k_spin_unlock(&slot->lock, final_key);
		if (became_stale)
		{
			static_cast<void>(gpio_pin_interrupt_configure(description->gpio.port,
													 description->gpio.pin,
													 GPIO_INT_DISABLE));
		}
	}

	/** @brief GPIO driver callback에서 등록된 사용자 함수를 전달합니다. */
	void gpioInterruptHandler(const struct device *port, struct gpio_callback *callback,
							  gpio_port_pins_t pins)
	{
		ARG_UNUSED(port);
		ARG_UNUSED(pins);

		auto *slot = CONTAINER_OF(callback, InterruptSlot, gpio_callback);
		voidFuncPtr simple_callback = nullptr;
		voidFuncPtrParam parameter_callback = nullptr;
		void *parameter = nullptr;
		CallbackKind callback_kind = CallbackKind::none;
		TriggerKind trigger_kind = TriggerKind::edge;
		std::size_t logical_pin = 0U;
		bool suppress_asserted_level = false;

		const k_spinlock_key_t key = k_spin_lock(&slot->lock);
		if (slot->registered && slot->active)
		{
			trigger_kind = slot->trigger_kind;
			logical_pin = slot->logical_pin;
			const bool level_delivery = trigger_kind != TriggerKind::edge;
			const bool callback_masked = slot->suspended ||
									 (atomic_get(&callback_mask_depth) != 0);
			suppress_asserted_level = level_delivery && callback_masked;
			if (!callback_masked &&
				(!level_delivery || atomic_cas(&slot->level_latched, 0, 1)))
			{
				atomic_inc(&slot->in_flight);
				callback_kind = slot->callback_kind;
				simple_callback = slot->simple_callback;
				parameter_callback = slot->parameter_callback;
				parameter = slot->parameter;
			}
		}
		k_spin_unlock(&slot->lock, key);

		/** Mask 복원 중 이미 assert된 level을 arm하면 nrfx PORT event가 즉시 반복될 수
		 * 있습니다. 사용자 callback은 전달하지 않되 hardware trigger를 한 번 끊어 ISR
		 * storm을 막고, 마지막 interrupts()가 raw level을 확인해 one-shot으로 재무장합니다.
		 */
		if (suppress_asserted_level)
		{
			const PinDescription *const description = pinDescription(logical_pin);
			if (description != nullptr)
			{
				const int result = gpio_pin_interrupt_configure(description->gpio.port,
												 description->gpio.pin,
												 GPIO_INT_DISABLE);
				if (result < 0)
				{
					setGpioBackendError(GpioError::driver_error, result);
				}
			}
			return;
		}

		if (callback_kind == CallbackKind::none)
		{
			return;
		}

		if (trigger_kind != TriggerKind::edge)
		{
			const PinDescription *const description = pinDescription(logical_pin);
			if (description != nullptr)
			{
				const int result = gpio_pin_interrupt_configure(description->gpio.port,
														 description->gpio.pin,
														 GPIO_INT_DISABLE);
				if (result < 0)
				{
					setGpioBackendError(GpioError::driver_error, result);
				}
			}
		}

		if ((callback_kind == CallbackKind::simple) && (simple_callback != nullptr))
		{
			simple_callback();
		}
		else if ((callback_kind == CallbackKind::parameter) &&
				 (parameter_callback != nullptr))
		{
			parameter_callback(parameter);
		}

		atomic_dec(&slot->in_flight);
		if (trigger_kind != TriggerKind::edge)
		{
			static_cast<void>(k_work_reschedule(&slot->level_rearm_work,
										 level_rearm_interval));
		}
	}

	/** @brief slot을 비활성화하고 진행 중 callback과 level work를 정리합니다. */
	int removeSlot(const PinDescription &description, InterruptSlot &slot) noexcept
	{
		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		slot.active = false;
		slot.suspended = true;
		atomic_inc(&slot.generation);
		k_spin_unlock(&slot.lock, key);

		if (slot.work_initialized)
		{
			struct k_work_sync sync;
			static_cast<void>(k_work_cancel_delayable_sync(&slot.level_rearm_work, &sync));
		}

		int result = 0;
		if (slot.registered)
		{
			result = gpio_pin_interrupt_configure(description.gpio.port,
												  description.gpio.pin,
												  GPIO_INT_DISABLE);
			const int remove_result = gpio_remove_callback(description.gpio.port,
												   &slot.gpio_callback);
			if ((result == 0) && (remove_result < 0))
			{
				result = remove_result;
			}
		}

		while (atomic_get(&slot.in_flight) != 0)
		{
			k_yield();
		}

		const k_spinlock_key_t clear_key = k_spin_lock(&slot.lock);
		slot.registered = false;
		slot.active = false;
		slot.suspended = false;
		slot.logical_pin = 0U;
		slot.trigger_flags = 0U;
		slot.trigger_kind = TriggerKind::edge;
		slot.callback_kind = CallbackKind::none;
		slot.simple_callback = nullptr;
		slot.parameter_callback = nullptr;
		slot.parameter = nullptr;
		atomic_set(&slot.level_latched, 0);
		k_spin_unlock(&slot.lock, clear_key);
		return result;
	}

	/** @brief 공통 검증 뒤 사용자 callback을 GPIO trigger에 등록합니다. */
	void attachInterruptImpl(pin_size_t interrupt_number, voidFuncPtr simple_callback,
							 voidFuncPtrParam parameter_callback, void *parameter, PinStatus mode)
	{
		if (k_is_in_isr())
		{
			setGpioBackendError(GpioError::invalid_context);
			return;
		}

		gpio_flags_t flags = 0U;
		TriggerKind trigger_kind = TriggerKind::edge;
		if (!interruptFlags(mode, flags, trigger_kind))
		{
			setGpioBackendError(GpioError::invalid_interrupt_mode);
			return;
		}

		if ((simple_callback == nullptr) && (parameter_callback == nullptr))
		{
			setGpioBackendError(GpioError::null_callback);
			return;
		}

		const auto logical_pin = static_cast<std::size_t>(interrupt_number);
		const PinDescription *description = pinDescription(logical_pin);
		if ((description == nullptr) || (logical_pin >= pin_slot_count))
		{
			setGpioBackendError(GpioError::invalid_pin);
			return;
		}

		if (!hasPinCapability(description->capabilities, PinCapability::interrupt))
		{
			setGpioBackendError(GpioError::unsupported_capability);
			return;
		}

		if (!isPinConfiguredForInput(logical_pin))
		{
			setGpioBackendError(GpioError::interrupt_not_configured);
			return;
		}

		if (!gpio_is_ready_dt(&description->gpio))
		{
			setGpioBackendError(GpioError::device_not_ready);
			return;
		}

		static_cast<void>(k_mutex_lock(&interrupt_configuration_mutex, K_FOREVER));
		InterruptSlot &slot = interrupt_slots[logical_pin];
		const int previous_result = removeSlot(*description, slot);
		if (previous_result < 0)
		{
			setGpioBackendError(GpioError::driver_error, previous_result);
			static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
			return;
		}

		if (!slot.work_initialized)
		{
			k_work_init_delayable(&slot.level_rearm_work, levelRearmHandler);
			slot.work_initialized = true;
		}

		gpio_init_callback(&slot.gpio_callback, gpioInterruptHandler,
						   static_cast<gpio_port_pins_t>(BIT(description->gpio.pin)));
		int result = gpio_add_callback(description->gpio.port, &slot.gpio_callback);
		if (result < 0)
		{
			setGpioBackendError(GpioError::driver_error, result);
			static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
			return;
		}

		const bool masked = atomic_get(&callback_mask_depth) != 0;
		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		atomic_inc(&slot.generation);
		slot.registered = true;
		slot.active = true;
		slot.suspended = masked;
		slot.logical_pin = logical_pin;
		slot.trigger_flags = flags;
		slot.trigger_kind = trigger_kind;
		slot.callback_kind =
			(simple_callback != nullptr) ? CallbackKind::simple : CallbackKind::parameter;
		slot.simple_callback = simple_callback;
		slot.parameter_callback = parameter_callback;
		slot.parameter = parameter;
		atomic_set(&slot.level_latched, 0);
		k_spin_unlock(&slot.lock, key);

		if (!masked)
		{
			result = gpio_pin_interrupt_configure(description->gpio.port,
												  description->gpio.pin,
												  flags);
			if (result < 0)
			{
				static_cast<void>(removeSlot(*description, slot));
				setGpioBackendError(GpioError::driver_error, result);
				static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
				return;
			}
		}

		setGpioBackendSuccess();
		static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
	}

	/**
	 * @brief GPIO callback 전달과 모든 등록 trigger를 재시도 가능한 mask 상태로 고정합니다.
	 *
	 * @details Driver 복원 일부가 실패한 뒤 논리 상태만 활성화하면 callback이 영구 유실될 수
	 * 있습니다. 호출 thread를 owner로 유지하고 모든 slot을 suspended/disabled 상태로 되돌려
	 * 다음 `interrupts()` 호출이 전체 복원을 다시 시도할 수 있게 합니다.
	 *
	 * @param owner callback mask를 복원할 thread입니다.
	 * @return trigger disable 중 처음 발생한 음수 driver 오류 또는 0입니다.
	 */
	int preserveFailClosedMask(k_tid_t owner) noexcept
	{
		callback_mask_owner = owner;
		atomic_set(&callback_mask_depth, 1);
		int first_error = 0;
		for (auto &slot : interrupt_slots)
		{
			const k_spinlock_key_t key = k_spin_lock(&slot.lock);
			const bool should_disable = slot.registered && slot.active;
			const std::size_t logical_pin = slot.logical_pin;
			if (should_disable)
			{
				slot.suspended = true;
				atomic_set(&slot.level_latched, 0);
			}
			k_spin_unlock(&slot.lock, key);

			if (!should_disable)
			{
				continue;
			}
			if (slot.work_initialized)
			{
				struct k_work_sync sync;
				static_cast<void>(k_work_cancel_delayable_sync(
					&slot.level_rearm_work, &sync));
			}
			const PinDescription *const description = pinDescription(logical_pin);
			if (description != nullptr)
			{
				const int result = gpio_pin_interrupt_configure(description->gpio.port,
												 description->gpio.pin,
												 GPIO_INT_DISABLE);
				if ((first_error == 0) && (result < 0))
				{
					first_error = result;
				}
			}
		}
		for (auto &slot : interrupt_slots)
		{
			while (atomic_get(&slot.in_flight) != 0)
			{
				k_yield();
			}
		}
		return first_error;
	}

}

extern "C" void attachInterrupt(pin_size_t interrupt_number, voidFuncPtr callback,
								PinStatus mode)
{
	attachInterruptImpl(interrupt_number, callback, nullptr, nullptr, mode);
}

extern "C" void attachInterruptParam(pin_size_t interrupt_number, voidFuncPtrParam callback,
									 PinStatus mode, void *parameter)
{
	attachInterruptImpl(interrupt_number, nullptr, callback, parameter, mode);
}

extern "C" void detachInterrupt(pin_size_t interrupt_number)
{
	if (k_is_in_isr())
	{
		setGpioBackendError(GpioError::invalid_context);
		return;
	}

	const auto logical_pin = static_cast<std::size_t>(interrupt_number);
	const PinDescription *description = pinDescription(logical_pin);
	if ((description == nullptr) || (logical_pin >= pin_slot_count))
	{
		setGpioBackendError(GpioError::invalid_pin);
		return;
	}

	static_cast<void>(k_mutex_lock(&interrupt_configuration_mutex, K_FOREVER));
	const int result = removeSlot(*description, interrupt_slots[logical_pin]);
	if (result < 0)
	{
		setGpioBackendError(GpioError::driver_error, result);
	}
	else
	{
		setGpioBackendSuccess();
	}
	static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
}

extern "C" void noInterrupts(void)
{
	if (k_is_in_isr())
	{
		setGpioBackendError(GpioError::invalid_context);
		return;
	}

	const k_tid_t caller = k_current_get();
	static_cast<void>(k_mutex_lock(&interrupt_configuration_mutex, K_FOREVER));
	const atomic_val_t depth = atomic_get(&callback_mask_depth);
	if (depth != 0)
	{
		if (callback_mask_owner != caller)
		{
			setGpioBackendError(GpioError::ownership_conflict);
			static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
			return;
		}
		if (depth == static_cast<atomic_val_t>(INT_MAX))
		{
			setGpioBackendError(GpioError::nesting_overflow);
			static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
			return;
		}
		atomic_inc(&callback_mask_depth);
		setGpioBackendSuccess();
		static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
		return;
	}

	callback_mask_owner = caller;
	atomic_set(&callback_mask_depth, 1);
	int first_error = 0;
	for (auto &slot : interrupt_slots)
	{
		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		const bool should_suspend = slot.registered && slot.active;
		const std::size_t logical_pin = slot.logical_pin;
		if (should_suspend)
		{
			slot.suspended = true;
			atomic_set(&slot.level_latched, 0);
		}
		k_spin_unlock(&slot.lock, key);

		if (!should_suspend)
		{
			continue;
		}

		if (slot.work_initialized)
		{
			struct k_work_sync sync;
			static_cast<void>(k_work_cancel_delayable_sync(&slot.level_rearm_work, &sync));
		}
		const PinDescription *const description = pinDescription(logical_pin);
		if (description != nullptr)
		{
			const int result = gpio_pin_interrupt_configure(description->gpio.port,
													  description->gpio.pin,
													  GPIO_INT_DISABLE);
			if ((first_error == 0) && (result < 0))
			{
				first_error = result;
			}
		}
	}

	for (auto &slot : interrupt_slots)
	{
		while (atomic_get(&slot.in_flight) != 0)
		{
			k_yield();
		}
	}

	if (first_error < 0)
	{
		int rollback_error = 0;
		for (auto &slot : interrupt_slots)
		{
			const k_spinlock_key_t key = k_spin_lock(&slot.lock);
			const bool should_restore = slot.registered && slot.active && slot.suspended;
			const std::size_t logical_pin = slot.logical_pin;
			const gpio_flags_t trigger_flags = slot.trigger_flags;
			k_spin_unlock(&slot.lock, key);
			const PinDescription *const description = pinDescription(logical_pin);
			if (should_restore && (description != nullptr))
			{
				const int result = gpio_pin_interrupt_configure(description->gpio.port,
												 description->gpio.pin,
												 trigger_flags);
				if ((rollback_error == 0) && (result < 0))
				{
					rollback_error = result;
				}
			}
		}
		if (rollback_error == 0)
		{
			for (auto &slot : interrupt_slots)
			{
				const k_spinlock_key_t key = k_spin_lock(&slot.lock);
				if (slot.registered && slot.active)
				{
					slot.suspended = false;
				}
				k_spin_unlock(&slot.lock, key);
			}
			callback_mask_owner = nullptr;
			atomic_set(&callback_mask_depth, 0);
			for (auto &slot : interrupt_slots)
			{
				const int result = retriggerAssertedLevel(slot);
				if ((rollback_error == 0) && (result < 0))
				{
					rollback_error = result;
				}
			}
		}
		if (rollback_error < 0)
		{
			static_cast<void>(preserveFailClosedMask(caller));
			setGpioBackendError(GpioError::driver_error, rollback_error);
		}
		else
		{
			setGpioBackendError(GpioError::driver_error, first_error);
		}
	}
	else
	{
		setGpioBackendSuccess();
	}
	static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
}

extern "C" void interrupts(void)
{
	if (k_is_in_isr())
	{
		setGpioBackendError(GpioError::invalid_context);
		return;
	}

	const k_tid_t caller = k_current_get();
	static_cast<void>(k_mutex_lock(&interrupt_configuration_mutex, K_FOREVER));
	const atomic_val_t depth = atomic_get(&callback_mask_depth);
	if (depth == 0)
	{
		setGpioBackendError(GpioError::interrupt_restore_without_disable);
		static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
		return;
	}
	if (callback_mask_owner != caller)
	{
		setGpioBackendError(GpioError::ownership_conflict);
		static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
		return;
	}
	if (depth > 1)
	{
		atomic_dec(&callback_mask_depth);
		setGpioBackendSuccess();
		static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
		return;
	}

	int first_error = 0;
	for (auto &slot : interrupt_slots)
	{
		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		const bool should_restore = slot.registered && slot.active && slot.suspended;
		const std::size_t logical_pin = slot.logical_pin;
		const gpio_flags_t trigger_flags = slot.trigger_flags;
		if (should_restore)
		{
			atomic_set(&slot.level_latched, 0);
		}
		k_spin_unlock(&slot.lock, key);

		const PinDescription *const description = pinDescription(logical_pin);
		if (should_restore && (description != nullptr))
		{
			const int result = gpio_pin_interrupt_configure(description->gpio.port,
													  description->gpio.pin,
													  trigger_flags);
			if ((first_error == 0) && (result < 0))
			{
				first_error = result;
			}
		}
	}

	if (first_error < 0)
	{
		for (auto &slot : interrupt_slots)
		{
			const k_spinlock_key_t key = k_spin_lock(&slot.lock);
			const bool should_disable = slot.registered && slot.active && slot.suspended;
			const std::size_t logical_pin = slot.logical_pin;
			k_spin_unlock(&slot.lock, key);
			const PinDescription *const description = pinDescription(logical_pin);
			if (should_disable && (description != nullptr))
			{
				static_cast<void>(gpio_pin_interrupt_configure(description->gpio.port,
														 description->gpio.pin,
														 GPIO_INT_DISABLE));
			}
		}
		setGpioBackendError(GpioError::driver_error, first_error);
		static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
		return;
	}

	for (auto &slot : interrupt_slots)
	{
		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		if (slot.registered && slot.active)
		{
			slot.suspended = false;
		}
		k_spin_unlock(&slot.lock, key);
	}
	callback_mask_owner = nullptr;
	atomic_set(&callback_mask_depth, 0);
	for (auto &slot : interrupt_slots)
	{
		const int result = retriggerAssertedLevel(slot);
		if ((first_error == 0) && (result < 0))
		{
			first_error = result;
		}
	}
	if (first_error < 0)
	{
		static_cast<void>(preserveFailClosedMask(caller));
		setGpioBackendError(GpioError::driver_error, first_error);
	}
	else
	{
		setGpioBackendSuccess();
	}
	static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
}
