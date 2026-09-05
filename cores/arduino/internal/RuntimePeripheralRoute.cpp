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

    RuntimePeripheralRoute::RuntimePeripheralRoute(const struct device *device,
                                                   struct pinctrl_dev_config *pinctrl_config,
                                                   IoResourceOwner owner, IoResourceKind block_kind,
                                                   std::uint16_t block_index) noexcept
        : device_(device), pinctrl_config_(pinctrl_config), owner_(owner), block_kind_(block_kind),
          block_index_(block_index)
    {
    }

    bool RuntimePeripheralRoute::stage(const PeripheralRouteConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            recordError(RuntimePeripheralRouteError::invalid_context);
            return false;
        }
        if (phase_ == Phase::active)
        {
            recordError(RuntimePeripheralRouteError::already_active);
            return false;
        }
        if (phase_ == Phase::faulted)
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
                if (configuration.logical_pins[index] == configuration.logical_pins[previous])
                {
                    recordError(RuntimePeripheralRouteError::invalid_argument);
                    return false;
                }
            }
        }

        staged_configuration_ = configuration;
        phase_ = Phase::staged;
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
        if (phase_ == Phase::active)
        {
            recordError(RuntimePeripheralRouteError::already_active);
            return false;
        }
        if (phase_ == Phase::faulted)
        {
            recordError(RuntimePeripheralRouteError::faulted);
            return false;
        }
        if (phase_ == Phase::empty || (device_ == nullptr) || (pinctrl_config_ == nullptr))
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

        acquired_.block_lease_ = {};
        const IoResourceId block_resource = peripheralIoResource(block_kind_, block_index_);
        const IoResourceResult block_result = reserveIoResources(
            owner_, &block_resource, 1U, IoAcquirePolicy::exclusive, acquired_.block_lease_);
        if (block_result != IoResourceResult::success)
        {
            recordError(RuntimePeripheralRouteError::ownership_conflict,
                        ownershipError(block_result));
            return false;
        }

        std::size_t prepared_count = 0U;
        for (; prepared_count < staged_configuration_.pin_count; ++prepared_count)
        {
            acquired_.pin_handovers_[prepared_count] = {};
            const PinHandoverResult result =
                beginGpioPinHandover(staged_configuration_.logical_pins[prepared_count], owner_,
                                     acquired_.pin_handovers_[prepared_count]);
            if (result != PinHandoverResult::success)
            {
                const int original_error = handoverError(result);
                if (unwindActivation(prepared_count + 1U))
                {
                    recordError(RuntimePeripheralRouteError::pin_handover_failed, original_error);
                }
                return false;
            }
        }

        for (std::size_t index = 0U; index < staged_configuration_.pin_count; ++index)
        {
            acquired_.active_default_pins_[index] = staged_configuration_.default_pins[index];
            acquired_.active_sleep_pins_[index] = staged_configuration_.sleep_pins[index];
        }
        acquired_.active_states_[0] = {
            acquired_.active_default_pins_,
            static_cast<std::uint8_t>(staged_configuration_.pin_count),
            PINCTRL_STATE_DEFAULT,
        };
        acquired_.active_states_[1] = {
            acquired_.active_sleep_pins_,
            static_cast<std::uint8_t>(staged_configuration_.pin_count),
            PINCTRL_STATE_SLEEP,
        };
        acquired_.previous_states_ = pinctrl_config_->states;
        acquired_.previous_state_count_ = pinctrl_config_->state_cnt;

        const int pinctrl_result =
            pinctrl_update_states(pinctrl_config_, acquired_.active_states_, 2U);
        if (pinctrl_result < 0)
        {
            if (unwindActivation(prepared_count))
            {
                recordError(RuntimePeripheralRouteError::pinctrl_failed, pinctrl_result);
            }
            return false;
        }
        acquired_.pinctrl_route_installed_ = true;

        const int pm_result = pm_device_runtime_get(device_);
        if (pm_result < 0)
        {
            if (unwindActivation(prepared_count))
            {
                recordError(RuntimePeripheralRouteError::pm_failed, pm_result);
            }
            return false;
        }
        acquired_.pm_reference_held_ = true;

        acquired_.committed_pin_count_ = 0U;
        for (; acquired_.committed_pin_count_ < staged_configuration_.pin_count;
             ++acquired_.committed_pin_count_)
        {
            const PinHandoverResult result =
                commitGpioPinHandover(acquired_.pin_handovers_[acquired_.committed_pin_count_]);
            if (result != PinHandoverResult::success)
            {
                const int original_error = handoverError(result);
                if (unwindActivation(staged_configuration_.pin_count))
                {
                    recordError(RuntimePeripheralRouteError::pin_handover_failed, original_error);
                }
                return false;
            }
        }

        const IoResourceResult commit_result = commitIoResources(acquired_.block_lease_);
        if (commit_result != IoResourceResult::success)
        {
            const int original_error = ownershipError(commit_result);
            if (unwindActivation(staged_configuration_.pin_count))
            {
                recordError(RuntimePeripheralRouteError::ownership_conflict, original_error);
            }
            return false;
        }

        phase_ = Phase::active;
        recordError(RuntimePeripheralRouteError::none);
        return true;
    }

    bool RuntimePeripheralRoute::active() const noexcept
    {
        return phase_ == Phase::active;
    }

    bool RuntimePeripheralRoute::faulted() const noexcept
    {
        return phase_ == Phase::faulted;
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

    void RuntimePeripheralRoute::recordError(RuntimePeripheralRouteError error,
                                             int driver_error) noexcept
    {
        last_driver_error_ = driver_error;
        last_error_ = error;
    }

} // namespace nucode::arduino::internal
