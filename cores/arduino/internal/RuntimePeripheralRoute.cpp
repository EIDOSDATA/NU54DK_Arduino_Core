/**
 * @file RuntimePeripheralRoute.cpp
 * @brief 주변장치 runtime pinctrl·PM·ownership 전환을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "internal/RuntimePeripheralRoute.h"

#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <zephyr/pm/device_runtime.h>

#include <errno.h>

namespace nucode::arduino::internal
{
	namespace
	{
		/** @brief Pin handover 결과를 route 계층의 진단용 음수 값으로 변환합니다. */
		[[nodiscard]] int handoverError(PinHandoverResult result) noexcept
		{
			return -static_cast<int>(result);
		}

		/** @brief ownership 결과를 route 계층의 진단용 음수 값으로 변환합니다. */
		[[nodiscard]] int ownershipError(IoResourceResult result) noexcept
		{
			return -static_cast<int>(result);
		}
	}

	RuntimePeripheralRoute::RuntimePeripheralRoute(
		const struct device *device, struct pinctrl_dev_config *pinctrl_config,
		IoResourceOwner owner, IoResourceKind block_kind, std::uint16_t block_index) noexcept
		: device_(device), pinctrl_config_(pinctrl_config), owner_(owner),
		  block_kind_(block_kind), block_index_(block_index)
	{
	}

	bool RuntimePeripheralRoute::stage(
		const PeripheralRouteConfiguration &configuration) noexcept
	{
		if (k_is_in_isr())
		{
			recordError(RuntimePeripheralRouteError::invalid_context);
			return false;
		}
		if (active_)
		{
			recordError(RuntimePeripheralRouteError::already_active);
			return false;
		}
		if (faulted_)
		{
			recordError(RuntimePeripheralRouteError::faulted);
			return false;
		}
		if ((configuration.pin_count == 0U) ||
			(configuration.pin_count > runtime_peripheral_route_pin_capacity))
		{
			recordError(RuntimePeripheralRouteError::invalid_argument);
			return false;
		}

		for (std::size_t index = 0U; index < configuration.pin_count; ++index)
		{
			if (configuration.signals[index] == PeripheralSignal::invalid)
			{
				recordError(RuntimePeripheralRouteError::invalid_argument);
				return false;
			}
			for (std::size_t previous = 0U; previous < index; ++previous)
			{
				if (configuration.logical_pins[index] ==
					configuration.logical_pins[previous])
				{
					recordError(RuntimePeripheralRouteError::invalid_argument);
					return false;
				}
			}
		}

		staged_configuration_ = configuration;
		staged_ = true;
		recordError(RuntimePeripheralRouteError::none);
		return true;
	}

	bool RuntimePeripheralRoute::activate() noexcept
	{
		if (k_is_in_isr())
		{
			recordError(RuntimePeripheralRouteError::invalid_context);
			return false;
		}
		if (active_)
		{
			recordError(RuntimePeripheralRouteError::already_active);
			return false;
		}
		if (faulted_)
		{
			recordError(RuntimePeripheralRouteError::faulted);
			return false;
		}
		if (!staged_ || (device_ == nullptr) || (pinctrl_config_ == nullptr))
		{
			recordError(RuntimePeripheralRouteError::not_staged);
			return false;
		}
		if (!device_is_ready(device_))
		{
			recordError(RuntimePeripheralRouteError::device_not_ready);
			return false;
		}
		if (!pm_device_runtime_is_enabled(device_))
		{
			/** @brief 최초 Arduino begin이 장치를 ACTIVE에서 SUSPENDED로 옮긴 뒤 route를 바꿉니다. */
			const int enable_result = pm_device_runtime_enable(device_);
			if (enable_result < 0)
			{
				recordError(RuntimePeripheralRouteError::pm_not_enabled, enable_result);
				return false;
			}
		}

		enum pm_device_state state = PM_DEVICE_STATE_ACTIVE;
		const int state_result = pm_device_state_get(device_, &state);
		if (state_result < 0)
		{
			recordError(RuntimePeripheralRouteError::pm_failed, state_result);
			return false;
		}
		if (state != PM_DEVICE_STATE_SUSPENDED)
		{
			recordError(RuntimePeripheralRouteError::device_not_suspended);
			return false;
		}

		block_lease_ = {};
		const IoResourceId block_resource =
			peripheralIoResource(block_kind_, block_index_);
		const IoResourceResult block_result = reserveIoResources(
			owner_, &block_resource, 1U, IoAcquirePolicy::exclusive, block_lease_);
		if (block_result != IoResourceResult::success)
		{
			recordError(RuntimePeripheralRouteError::ownership_conflict,
						ownershipError(block_result));
			return false;
		}

		std::size_t prepared_count = 0U;
		for (; prepared_count < staged_configuration_.pin_count; ++prepared_count)
		{
			pin_handovers_[prepared_count] = {};
			const PinHandoverResult result = beginGpioPinHandover(
				staged_configuration_.logical_pins[prepared_count], owner_,
				pin_handovers_[prepared_count]);
			if (result != PinHandoverResult::success)
			{
				const int original_error = handoverError(result);
				if (unwindActivation(prepared_count + 1U))
				{
					recordError(RuntimePeripheralRouteError::pin_handover_failed,
								original_error);
				}
				return false;
			}
		}

		for (std::size_t index = 0U; index < staged_configuration_.pin_count; ++index)
		{
			active_default_pins_[index] = staged_configuration_.default_pins[index];
			active_sleep_pins_[index] = staged_configuration_.sleep_pins[index];
		}
		active_states_[0] = {
			active_default_pins_,
			static_cast<std::uint8_t>(staged_configuration_.pin_count),
			PINCTRL_STATE_DEFAULT,
		};
		active_states_[1] = {
			active_sleep_pins_,
			static_cast<std::uint8_t>(staged_configuration_.pin_count),
			PINCTRL_STATE_SLEEP,
		};
		previous_states_ = pinctrl_config_->states;
		previous_state_count_ = pinctrl_config_->state_cnt;

		const int pinctrl_result = pinctrl_update_states(pinctrl_config_, active_states_, 2U);
		if (pinctrl_result < 0)
		{
			if (unwindActivation(prepared_count))
			{
				recordError(RuntimePeripheralRouteError::pinctrl_failed, pinctrl_result);
			}
			return false;
		}
		pinctrl_route_installed_ = true;

		const int pm_result = pm_device_runtime_get(device_);
		if (pm_result < 0)
		{
			if (unwindActivation(prepared_count))
			{
				recordError(RuntimePeripheralRouteError::pm_failed, pm_result);
			}
			return false;
		}
		pm_reference_held_ = true;

		committed_pin_count_ = 0U;
		for (; committed_pin_count_ < staged_configuration_.pin_count;
			 ++committed_pin_count_)
		{
			const PinHandoverResult result =
				commitGpioPinHandover(pin_handovers_[committed_pin_count_]);
			if (result != PinHandoverResult::success)
			{
				const int original_error = handoverError(result);
				if (unwindActivation(staged_configuration_.pin_count))
				{
					recordError(RuntimePeripheralRouteError::pin_handover_failed,
								original_error);
				}
				return false;
			}
		}

		const IoResourceResult commit_result = commitIoResources(block_lease_);
		if (commit_result != IoResourceResult::success)
		{
			const int original_error = ownershipError(commit_result);
			if (unwindActivation(staged_configuration_.pin_count))
			{
				recordError(RuntimePeripheralRouteError::ownership_conflict,
							original_error);
			}
			return false;
		}

		active_ = true;
		recordError(RuntimePeripheralRouteError::none);
		return true;
	}

	bool RuntimePeripheralRoute::deactivate() noexcept
	{
		if (k_is_in_isr())
		{
			recordError(RuntimePeripheralRouteError::invalid_context);
			return false;
		}
		if (faulted_)
		{
			recordError(RuntimePeripheralRouteError::faulted);
			return false;
		}
		if (!active_)
		{
			recordError(RuntimePeripheralRouteError::none);
			return true;
		}

		if (!pm_reference_held_ || !pinctrl_route_installed_)
		{
			faulted_ = true;
			active_ = false;
			recordError(RuntimePeripheralRouteError::release_failed, -EIO);
			return false;
		}

		const int pm_result = pm_device_runtime_put(device_);
		if (pm_result < 0)
		{
			recordError(RuntimePeripheralRouteError::pm_failed, pm_result);
			return false;
		}
		pm_reference_held_ = false;
		const int pinctrl_result = pinctrl_update_states(
			pinctrl_config_, previous_states_, previous_state_count_);
		if (pinctrl_result < 0)
		{
			faulted_ = true;
			active_ = false;
			recordError(RuntimePeripheralRouteError::pinctrl_failed, pinctrl_result);
			return false;
		}
		pinctrl_route_installed_ = false;

		int first_error = 0;
		for (std::size_t index = staged_configuration_.pin_count; index > 0U; --index)
		{
			GpioPinHandover &handover = pin_handovers_[index - 1U];
			if (handover.phase != PinHandoverPhase::committed)
			{
				continue;
			}
			const PinHandoverResult result = restoreGpioAfterPeripheral(handover);
			if ((first_error == 0) && (result != PinHandoverResult::success))
			{
				first_error = handoverError(result);
			}
		}
		refreshCommittedPinCount();
		if (first_error != 0)
		{
			active_ = false;
			faulted_ = true;
			recordError(RuntimePeripheralRouteError::release_failed, first_error);
			return false;
		}

		const IoResourceResult release_result = releaseIoResources(block_lease_);
		if (release_result != IoResourceResult::success)
		{
			active_ = false;
			faulted_ = true;
			recordError(RuntimePeripheralRouteError::release_failed,
						ownershipError(release_result));
			return false;
		}

		active_ = false;
		recordError(RuntimePeripheralRouteError::none);
		return true;
	}

	bool RuntimePeripheralRoute::active() const noexcept
	{
		return active_;
	}

	bool RuntimePeripheralRoute::faulted() const noexcept
	{
		return faulted_;
	}

	RuntimePeripheralRouteError RuntimePeripheralRoute::lastError() const noexcept
	{
		return last_error_;
	}

	int RuntimePeripheralRoute::lastDriverError() const noexcept
	{
		return last_driver_error_;
	}

	const PeripheralRouteConfiguration &RuntimePeripheralRoute::configuration() const noexcept
	{
		return staged_configuration_;
	}

	bool RuntimePeripheralRoute::unwindActivation(std::size_t handover_count) noexcept
	{
		if (pm_reference_held_)
		{
			const int result = pm_device_runtime_put(device_);
			if (result < 0)
			{
				abandonPreparedPinsFailClosed(handover_count);
				faulted_ = true;
				recordError(RuntimePeripheralRouteError::release_failed, result);
				return false;
			}
			pm_reference_held_ = false;
		}

		if (pinctrl_route_installed_)
		{
			const int result = pinctrl_update_states(
				pinctrl_config_, previous_states_, previous_state_count_);
			if (result < 0)
			{
				abandonPreparedPinsFailClosed(handover_count);
				faulted_ = true;
				recordError(RuntimePeripheralRouteError::release_failed, result);
				return false;
			}
			pinctrl_route_installed_ = false;
		}

		int first_error = 0;
		for (std::size_t index = handover_count; index > 0U; --index)
		{
			GpioPinHandover &handover = pin_handovers_[index - 1U];
			PinHandoverResult result = PinHandoverResult::success;
			if (handover.phase == PinHandoverPhase::committed)
			{
				result = restoreGpioAfterPeripheral(handover);
			}
			else if (handover.phase == PinHandoverPhase::prepared)
			{
				result = rollbackGpioPinHandover(handover);
			}
			else if (handover.phase == PinHandoverPhase::faulted)
			{
				result = PinHandoverResult::driver_error;
			}
			if (first_error == 0 && result != PinHandoverResult::success)
			{
				first_error = handoverError(result);
			}
		}
		refreshCommittedPinCount();
		if (first_error != 0)
		{
			faulted_ = true;
			recordError(RuntimePeripheralRouteError::release_failed, first_error);
			return false;
		}

		IoResourceResult block_result = IoResourceResult::success;
		if (block_lease_.phase == IoLeasePhase::reserved)
		{
			block_result = rollbackIoResources(block_lease_);
		}
		else if (block_lease_.phase == IoLeasePhase::committed)
		{
			block_result = releaseIoResources(block_lease_);
		}
		if (block_result != IoResourceResult::success)
		{
			faulted_ = true;
			recordError(RuntimePeripheralRouteError::release_failed,
						ownershipError(block_result));
			return false;
		}

		active_ = false;
		return true;
	}

	void RuntimePeripheralRoute::abandonPreparedPinsFailClosed(
		std::size_t handover_count) noexcept
	{
		for (std::size_t index = handover_count; index > 0U; --index)
		{
			GpioPinHandover &handover = pin_handovers_[index - 1U];
			if (handover.phase == PinHandoverPhase::prepared && handover.lock_held)
			{
				static_cast<void>(abandonGpioPinHandoverFailClosed(handover));
			}
		}
	}

	void RuntimePeripheralRoute::refreshCommittedPinCount() noexcept
	{
		committed_pin_count_ = 0U;
		for (std::size_t index = 0U; index < staged_configuration_.pin_count; ++index)
		{
			committed_pin_count_ +=
				pin_handovers_[index].phase == PinHandoverPhase::committed ? 1U : 0U;
		}
	}

	void RuntimePeripheralRoute::recordError(RuntimePeripheralRouteError error,
										 int driver_error) noexcept
	{
		last_driver_error_ = driver_error;
		last_error_ = error;
	}

}
