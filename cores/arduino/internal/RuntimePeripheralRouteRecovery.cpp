/** @file @brief 획득 기록에 따라 runtime route를 역순으로 복구합니다.
 * SPDX-License-Identifier: MIT
 */
#include "internal/RuntimePeripheralRoute.h"
#include <zephyr/kernel.h>
#include <zephyr/pm/device_runtime.h>
#include <errno.h>
namespace nucode::arduino::internal
{
    int RuntimePeripheralRoute::handoverError(PinHandoverResult result) noexcept
    {
        return -static_cast<int>(result);
    }
    int RuntimePeripheralRoute::ownershipError(IoResourceResult result) noexcept
    {
        return -static_cast<int>(result);
    }
    bool RuntimePeripheralRoute::deactivate() noexcept
    {
        if (k_is_in_isr())
        {
            recordError(RuntimePeripheralRouteError::invalid_context);
            return false;
        }
        if (phase_ == Phase::faulted)
        {
            recordError(RuntimePeripheralRouteError::faulted);
            return false;
        }
        if (phase_ != Phase::active)
        {
            recordError(RuntimePeripheralRouteError::none);
            return true;
        }

        if (!acquired_.pm_reference_held_ || !acquired_.pinctrl_route_installed_)
        {
            phase_ = Phase::faulted;
            recordError(RuntimePeripheralRouteError::release_failed, -EIO);
            return false;
        }

        const int pm_result = pm_device_runtime_put(device_);
        if (pm_result < 0)
        {
            recordError(RuntimePeripheralRouteError::pm_failed, pm_result);
            return false;
        }
        acquired_.pm_reference_held_ = false;
        const int pinctrl_result = pinctrl_update_states(
            pinctrl_config_, acquired_.previous_states_, acquired_.previous_state_count_);
        if (pinctrl_result < 0)
        {
            phase_ = Phase::faulted;
            recordError(RuntimePeripheralRouteError::pinctrl_failed, pinctrl_result);
            return false;
        }
        acquired_.pinctrl_route_installed_ = false;

        int first_error = 0;
        for (std::size_t index = staged_configuration_.pin_count; index > 0U; --index)
        {
            GpioPinHandover &handover = acquired_.pin_handovers_[index - 1U];
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
            phase_ = Phase::faulted;
            recordError(RuntimePeripheralRouteError::release_failed, first_error);
            return false;
        }

        const IoResourceResult release_result = releaseIoResources(acquired_.block_lease_);
        if (release_result != IoResourceResult::success)
        {
            phase_ = Phase::faulted;
            recordError(RuntimePeripheralRouteError::release_failed,
                        ownershipError(release_result));
            return false;
        }

        phase_ = Phase::staged;
        recordError(RuntimePeripheralRouteError::none);
        return true;
    }

    bool RuntimePeripheralRoute::unwindActivation(std::size_t handover_count) noexcept
    {
        if (acquired_.pm_reference_held_)
        {
            const int result = pm_device_runtime_put(device_);
            if (result < 0)
            {
                abandonPreparedPinsFailClosed(handover_count);
                phase_ = Phase::faulted;
                recordError(RuntimePeripheralRouteError::release_failed, result);
                return false;
            }
            acquired_.pm_reference_held_ = false;
        }

        if (acquired_.pinctrl_route_installed_)
        {
            const int result = pinctrl_update_states(pinctrl_config_, acquired_.previous_states_,
                                                     acquired_.previous_state_count_);
            if (result < 0)
            {
                abandonPreparedPinsFailClosed(handover_count);
                phase_ = Phase::faulted;
                recordError(RuntimePeripheralRouteError::release_failed, result);
                return false;
            }
            acquired_.pinctrl_route_installed_ = false;
        }

        int first_error = 0;
        for (std::size_t index = handover_count; index > 0U; --index)
        {
            GpioPinHandover &handover = acquired_.pin_handovers_[index - 1U];
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
            phase_ = Phase::faulted;
            recordError(RuntimePeripheralRouteError::release_failed, first_error);
            return false;
        }

        IoResourceResult block_result = IoResourceResult::success;
        if (acquired_.block_lease_.phase == IoLeasePhase::reserved)
        {
            block_result = rollbackIoResources(acquired_.block_lease_);
        }
        else if (acquired_.block_lease_.phase == IoLeasePhase::committed)
        {
            block_result = releaseIoResources(acquired_.block_lease_);
        }
        if (block_result != IoResourceResult::success)
        {
            phase_ = Phase::faulted;
            recordError(RuntimePeripheralRouteError::release_failed, ownershipError(block_result));
            return false;
        }

        phase_ = Phase::staged;
        return true;
    }

    void RuntimePeripheralRoute::abandonPreparedPinsFailClosed(std::size_t handover_count) noexcept
    {
        for (std::size_t index = handover_count; index > 0U; --index)
        {
            GpioPinHandover &handover = acquired_.pin_handovers_[index - 1U];
            if (handover.phase == PinHandoverPhase::prepared && handover.lock_held)
            {
                static_cast<void>(abandonGpioPinHandoverFailClosed(handover));
            }
        }
    }

    void RuntimePeripheralRoute::refreshCommittedPinCount() noexcept
    {
        acquired_.committed_pin_count_ = 0U;
        for (std::size_t index = 0U; index < staged_configuration_.pin_count; ++index)
        {
            acquired_.committed_pin_count_ +=
                acquired_.pin_handovers_[index].phase == PinHandoverPhase::committed ? 1U : 0U;
        }
    }
} // namespace nucode::arduino::internal
