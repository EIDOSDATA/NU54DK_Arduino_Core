/** @file @brief driver 정지와 자원 반환 순서를 계수하는 Host allocator입니다. */
#pragma once
#include <zephyr/device.h>
#include "../../../cores/arduino/internal/IoResourceManager.h"
#include "../../../cores/arduino/internal/pin_description.h"
#include <array>
#include <atomic>
#include <cassert>
device mock_gpio0{0}, mock_gpio1{1}, mock_gpio2{2};
inline std::atomic<int> mock_live_leases{0};
inline bool mock_release_failure = false;
inline bool mock_commit_failure = false;
namespace nucode::arduino::internal
{
    const PinDescription *pinDescription(std::size_t pin) noexcept
    {
        static const auto pins = []
        {
            std::array<PinDescription, 16> result{};
            for (unsigned i = 0; i < result.size(); ++i)
            {
                result[i] = {i,
                             {&mock_gpio1, i},
                             PinCapability::digital_input | PinCapability::digital_output |
                                 PinCapability::pwm_output | PinCapability::analog_input,
                             PinOwnership::connector_gpio,
                             PinPolicy::normal,
                             PinRoute::header | PinRoute::gpio | PinRoute::port1 | PinRoute::pwm20 |
                                 PinRoute::pwm21 | PinRoute::pwm22,
                             static_cast<std::int8_t>(i)};
            }
            return result;
        }();
        return pin < pins.size() ? &pins[pin] : nullptr;
    }
    IoResourceResult reserveIoResources(IoResourceOwner owner, const IoResourceId *,
                                        std::size_t count, IoAcquirePolicy, IoResourceLease &lease,
                                        IoResourceSnapshot *) noexcept
    {
        assert(lease.phase == IoLeasePhase::empty);
        lease.owner = owner;
        lease.count = count;
        lease.phase = IoLeasePhase::reserved;
        ++mock_live_leases;
        return IoResourceResult::success;
    }
    IoResourceResult commitIoResources(IoResourceLease &lease) noexcept
    {
        if (mock_commit_failure)
        {
            return IoResourceResult::wrong_phase;
        }
        lease.phase = IoLeasePhase::committed;
        return IoResourceResult::success;
    }
    IoResourceResult releaseIoResources(IoResourceLease &lease) noexcept
    {
        if (mock_release_failure)
        {
            return IoResourceResult::stale_lease;
        }
        assert(lease.phase == IoLeasePhase::committed);
        lease = {};
        --mock_live_leases;
        return IoResourceResult::success;
    }
    IoResourceResult rollbackIoResources(IoResourceLease &lease) noexcept
    {
        assert(lease.phase == IoLeasePhase::reserved);
        if (mock_release_failure)
        {
            return IoResourceResult::stale_lease;
        }
        lease = {};
        --mock_live_leases;
        return IoResourceResult::success;
    }
    IoResourceResult acquireIoResources(IoResourceOwner owner, const IoResourceId *,
                                        std::size_t count, IoAcquirePolicy, IoResourceToken &token,
                                        IoResourceSnapshot *) noexcept
    {
        token.owner = owner;
        token.count = count;
        token.active = true;
        ++mock_live_leases;
        return IoResourceResult::success;
    }
    IoResourceResult releaseIoResources(IoResourceToken &token) noexcept
    {
        if (mock_release_failure)
        {
            return IoResourceResult::stale_lease;
        }
        assert(token.active);
        token = {};
        --mock_live_leases;
        return IoResourceResult::success;
    }
} // namespace nucode::arduino::internal
