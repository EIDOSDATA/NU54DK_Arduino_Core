/**
 * @file wiring_interrupt.cpp
 * @brief Zephyr GPIO callback 위에 Arduino edge interrupt API를 구현합니다.
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

	/** @brief callback slot에 저장된 사용자 함수 형식입니다. */
	enum class CallbackKind : std::uint8_t
	{
		none = 0U,
		simple,
		parameter,
	};

	/** @brief 하나의 Arduino 논리 핀에 대응하는 고정 interrupt 상태입니다. */
	struct InterruptSlot
	{
		struct gpio_callback gpio_callback;
		struct k_spinlock lock;
		atomic_t in_flight;
		bool registered;
		bool active;
		CallbackKind kind;
		voidFuncPtr simple_callback;
		voidFuncPtrParam parameter_callback;
		void *parameter;
	};

	InterruptSlot interrupt_slots[NUM_DIGITAL_PINS] = {};
	K_MUTEX_DEFINE(interrupt_configuration_mutex);

	/**
	 * @brief Arduino edge mode를 Zephyr raw electrical edge flag로 변환합니다.
	 *
	 * @param mode Arduino interrupt mode입니다.
	 * @param flags 변환한 Zephyr flag를 받을 주소입니다.
	 * @return 지원하는 edge mode이면 true입니다.
	 */
	[[nodiscard]] bool interruptFlags(PinStatus mode, gpio_flags_t &flags) noexcept
	{
		switch (mode)
		{
		case RISING:
			flags = GPIO_INT_EDGE_RISING;
			return true;
		case FALLING:
			flags = GPIO_INT_EDGE_FALLING;
			return true;
		case CHANGE:
			flags = GPIO_INT_EDGE_BOTH;
			return true;
		default:
			return false;
		}
	}

	/**
	 * @brief GPIO driver callback에서 사용자 함수를 직접 실행합니다.
	 *
	 * @param port callback을 발생시킨 GPIO controller입니다.
	 * @param callback 등록된 Zephyr callback입니다.
	 * @param pins 발생한 핀 mask입니다.
	 */
	void gpioInterruptHandler(const struct device *port, struct gpio_callback *callback,
						  gpio_port_pins_t pins)
	{
		ARG_UNUSED(port);
		ARG_UNUSED(pins);

		auto *slot = CONTAINER_OF(callback, InterruptSlot, gpio_callback);
		voidFuncPtr simple_callback = nullptr;
		voidFuncPtrParam parameter_callback = nullptr;
		void *parameter = nullptr;
		CallbackKind kind = CallbackKind::none;

		const k_spinlock_key_t key = k_spin_lock(&slot->lock);
		if (slot->active)
		{
			atomic_inc(&slot->in_flight);
			kind = slot->kind;
			simple_callback = slot->simple_callback;
			parameter_callback = slot->parameter_callback;
			parameter = slot->parameter;
		}
		k_spin_unlock(&slot->lock, key);

		if ((kind == CallbackKind::simple) && (simple_callback != nullptr))
		{
			simple_callback();
		}
		else if ((kind == CallbackKind::parameter) && (parameter_callback != nullptr))
		{
			parameter_callback(parameter);
		}

		if (kind != CallbackKind::none)
		{
			atomic_dec(&slot->in_flight);
		}
	}

	/**
	 * @brief slot을 비활성화하고 진행 중 callback이 끝날 때까지 기다립니다.
	 *
	 * @param description 대상 GPIO 설명자입니다.
	 * @param slot 제거할 callback slot입니다.
	 * @return 모든 driver 작업이 성공하면 0입니다.
	 */
	int removeSlot(const PinDescription &description, InterruptSlot &slot) noexcept
	{
		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		slot.active = false;
		k_spin_unlock(&slot.lock, key);

		int result = 0;
		if (slot.registered)
		{
			result = gpio_pin_interrupt_configure(description.gpio.port, description.gpio.pin,
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
		slot.kind = CallbackKind::none;
		slot.simple_callback = nullptr;
		slot.parameter_callback = nullptr;
		slot.parameter = nullptr;
		k_spin_unlock(&slot.lock, clear_key);
		return result;
	}

	/**
	 * @brief 공통 검증 뒤 사용자 callback을 GPIO edge에 등록합니다.
	 *
	 * @param interrupt_number Arduino 논리 interrupt 번호입니다.
	 * @param simple_callback 매개변수 없는 callback입니다.
	 * @param parameter_callback 매개변수를 받는 callback입니다.
	 * @param parameter callback에 전달할 주소입니다.
	 * @param mode 감지할 raw electrical edge입니다.
	 */
	void attachInterruptImpl(pin_size_t interrupt_number, voidFuncPtr simple_callback,
						 voidFuncPtrParam parameter_callback, void *parameter, PinStatus mode)
	{
		if (k_is_in_isr())
		{
			setGpioBackendError(GpioError::invalid_context);
			return;
		}

		gpio_flags_t flags = 0U;
		if (!interruptFlags(mode, flags))
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
		if ((description == nullptr) || (logical_pin >= NUM_DIGITAL_PINS))
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

		gpio_init_callback(&slot.gpio_callback, gpioInterruptHandler,
					   static_cast<gpio_port_pins_t>(BIT(description->gpio.pin)));
		int result = gpio_add_callback(description->gpio.port, &slot.gpio_callback);
		if (result < 0)
		{
			setGpioBackendError(GpioError::driver_error, result);
			static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
			return;
		}

		const k_spinlock_key_t key = k_spin_lock(&slot.lock);
		slot.registered = true;
		slot.active = true;
		slot.kind = (simple_callback != nullptr) ? CallbackKind::simple : CallbackKind::parameter;
		slot.simple_callback = simple_callback;
		slot.parameter_callback = parameter_callback;
		slot.parameter = parameter;
		k_spin_unlock(&slot.lock, key);

		result = gpio_pin_interrupt_configure(description->gpio.port, description->gpio.pin,
									  flags);
		if (result < 0)
		{
			static_cast<void>(removeSlot(*description, slot));
			setGpioBackendError(GpioError::driver_error, result);
			static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
			return;
		}

		setGpioBackendSuccess();
		static_cast<void>(k_mutex_unlock(&interrupt_configuration_mutex));
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
	if ((description == nullptr) || (logical_pin >= NUM_DIGITAL_PINS))
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
