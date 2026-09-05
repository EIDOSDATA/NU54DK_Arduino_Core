/** @file @brief 실제 manager·route와 장애 주입 경계의 소유권 회귀 검사입니다. */
#include "internal/RuntimePeripheralRoute.h"
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <cassert>
#include <cerrno>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

using namespace nucode::arduino::internal;
namespace
{
    std::string scenario;
    int pinctrl_calls = 0;
    int get_calls = 0;
    int put_calls = 0;
    int references = 0;
    int locks = 0;
    int pin_domain;
    bool enabled = true;
    bool active_device = false;
    const pinctrl_state original_states[] = {{nullptr, 0, PINCTRL_STATE_DEFAULT}};
    GpioPinHandover *pins[2]{};
    constexpr IoResourceOwner owner{IoOwnerKind::spi, 0};
    const IoResourceId block = peripheralIoResource(IoResourceKind::serial_block, 0);

    /** @brief 실물 pad의 두 논리 별칭을 같은 자원 키로 정규화합니다. */
    IoResourceId pinResource(std::size_t pin)
    {
        return {IoResourceKind::gpio_pin, &pin_domain, static_cast<std::uint16_t>(pin % 10), 1};
    }
    IoResourceState state(const IoResourceId &resource)
    {
        IoResourceSnapshot snapshot{};
        assert(ioResourceSnapshot(resource, snapshot) == IoResourceResult::success);
        return snapshot.state;
    }
    void claim(IoResourceOwner claimant, const IoResourceId &resource, IoResourceLease &lease)
    {
        assert(reserveIoResources(claimant, &resource, 1, IoAcquirePolicy::exclusive, lease) ==
               IoResourceResult::success);
        assert(commitIoResources(lease) == IoResourceResult::success);
    }
    void unlocked(GpioPinHandover &handover)
    {
        assert(handover.lock_held && locks > 0);
        handover.lock_held = false;
        --locks;
    }
    PinHandoverResult recovered(GpioPinHandover &handover, bool committed)
    {
        assert(handover.phase ==
               (committed ? PinHandoverPhase::committed : PinHandoverPhase::prepared));
        const bool fail = (scenario == "rollback" && handover.canonical_pin == 1) ||
                          (scenario == "restore_pin" && handover.canonical_pin == 1);
        if (!committed)
        {
            unlocked(handover);
        }
        if (fail)
        {
            handover.phase = PinHandoverPhase::faulted;
            return PinHandoverResult::driver_error;
        }
        const auto result = committed ? releaseIoResources(handover.ownership_lease)
                                      : rollbackIoResources(handover.ownership_lease);
        assert(result == IoResourceResult::success);
        handover.phase = PinHandoverPhase::rolled_back;
        return PinHandoverResult::success;
    }
} // namespace

int pinctrl_update_states(pinctrl_dev_config *config, const pinctrl_state *states,
                          std::uint8_t count)
{
    ++pinctrl_calls;
    if ((scenario == "pinctrl" && pinctrl_calls == 1) ||
        ((scenario == "unwind_pinctrl" || scenario == "restore_pinctrl") && pinctrl_calls == 2))
    {
        return -EIO;
    }
    config->states = states;
    config->state_cnt = count;
    return 0;
}
bool pm_device_runtime_is_enabled(const device *)
{
    return enabled;
}
int pm_device_runtime_enable(const device *)
{
    enabled = true;
    return 0;
}
int pm_device_state_get(const device *, pm_device_state *value)
{
    *value = active_device ? PM_DEVICE_STATE_ACTIVE : PM_DEVICE_STATE_SUSPENDED;
    return 0;
}
int pm_device_runtime_get(const device *)
{
    ++get_calls;
    if (scenario == "get" || scenario == "unwind_pinctrl" || scenario == "rollback")
    {
        return -EIO;
    }
    ++references;
    return 0;
}
int pm_device_runtime_put(const device *)
{
    ++put_calls;
    assert(references == 1);
    if (scenario == "unwind_put" || (scenario == "put_retry" && put_calls == 1))
    {
        return -EIO;
    }
    --references;
    return 0;
}
namespace nucode::arduino::internal
{
    PinHandoverResult beginGpioPinHandover(std::size_t pin, IoResourceOwner target,
                                           GpioPinHandover &handover) noexcept
    {
        const auto resource = pinResource(pin);
        if (reserveIoResources(target, &resource, 1, IoAcquirePolicy::exclusive,
                               handover.ownership_lease) != IoResourceResult::success)
        {
            return PinHandoverResult::ownership_conflict;
        }
        handover.phase = PinHandoverPhase::prepared;
        handover.canonical_pin = pin % 10;
        handover.lock_held = true;
        ++locks;
        pins[handover.canonical_pin] = &handover;
        if ((scenario == "begin0" && pin == 0) || (scenario == "begin1" && pin == 1))
        {
            return PinHandoverResult::driver_error;
        }
        return PinHandoverResult::success;
    }
    PinHandoverResult commitGpioPinHandover(GpioPinHandover &handover) noexcept
    {
        if ((scenario == "commit" || scenario == "unwind_put") && handover.canonical_pin == 1)
        {
            return PinHandoverResult::driver_error;
        }
        assert(commitIoResources(handover.ownership_lease) == IoResourceResult::success);
        unlocked(handover);
        handover.phase = PinHandoverPhase::committed;
        return PinHandoverResult::success;
    }
    PinHandoverResult rollbackGpioPinHandover(GpioPinHandover &handover) noexcept
    {
        return recovered(handover, false);
    }
    PinHandoverResult restoreGpioAfterPeripheral(GpioPinHandover &handover) noexcept
    {
        return recovered(handover, true);
    }
    PinHandoverResult abandonGpioPinHandoverFailClosed(GpioPinHandover &handover) noexcept
    {
        unlocked(handover);
        handover.phase = PinHandoverPhase::faulted;
        return PinHandoverResult::success;
    }
} // namespace nucode::arduino::internal

/** @brief stale lease·부분 batch·borrow·실제 thread 직렬화를 검증합니다. */
void managerScenario()
{
    IoResourceLease first{};
    claim(owner, block, first);
    if (scenario == "stale")
    {
        auto stale = first;
        assert(releaseIoResources(first) == IoResourceResult::success);
        assert(releaseIoResources(first) == IoResourceResult::wrong_phase);
        claim({IoOwnerKind::wire, 0}, block, first);
        assert(releaseIoResources(stale) == IoResourceResult::stale_lease);
        assert(state(block) == IoResourceState::active);
        resetIoResourceManagerForTest();
        assert(releaseIoResources(first) == IoResourceResult::stale_lease);
    }
    else if (scenario == "transfer")
    {
        IoResourceLease transfer{};
        assert(transferIoResources(owner, {IoOwnerKind::wire, 0}, &block, 1, transfer) ==
               IoResourceResult::success);
        auto stale = transfer;
        assert(rollbackIoResources(transfer) == IoResourceResult::success);
        assert(rollbackIoResources(transfer) == IoResourceResult::wrong_phase);
        assert(rollbackIoResources(stale) == IoResourceResult::stale_lease);
        assert(releaseIoResources(first) == IoResourceResult::success);
    }
    else if (scenario == "borrow")
    {
        IoResourceLease borrow{};
        assert(reserveIoResources(owner, &block, 1, IoAcquirePolicy::exclusive, borrow) ==
               IoResourceResult::success);
        assert(!borrow.entries[0].changed);
        assert(releaseIoResources(first) == IoResourceResult::conflict);
        assert(rollbackIoResources(borrow) == IoResourceResult::success);
        assert(reserveIoResources(owner, &block, 1, IoAcquirePolicy::exclusive, borrow) ==
               IoResourceResult::success);
        assert(commitIoResources(borrow) == IoResourceResult::success);
        assert(releaseIoResources(borrow) == IoResourceResult::success);
        assert(state(block) == IoResourceState::active);
        assert(releaseIoResources(first) == IoResourceResult::success);
    }
    else if (scenario == "capacity")
    {
        IoResourceId resources[8]{};
        for (std::uint16_t index = 0; index < 8; ++index)
        {
            resources[index] = peripheralIoResource(IoResourceKind::timer_channel, index);
        }
        IoResourceLease batch{};
        assert(reserveIoResources(owner, resources, 8, IoAcquirePolicy::exclusive, batch) ==
               IoResourceResult::capacity_exhausted);
        assert(state(resources[0]) == IoResourceState::free && batch.phase == IoLeasePhase::empty);
        assert(releaseIoResources(first) == IoResourceResult::success);
        assert(reserveIoResources(owner, resources, 8, IoAcquirePolicy::exclusive, batch) ==
               IoResourceResult::success);
        assert(rollbackIoResources(batch) == IoResourceResult::success);
        assert(reserveIoResources(owner, resources, 8, IoAcquirePolicy::exclusive, batch) ==
               IoResourceResult::success);
        assert(commitIoResources(batch) == IoResourceResult::success);
        assert(releaseIoResources(batch) == IoResourceResult::success);
    }
    else if (scenario == "dma")
    {
        std::uint8_t memory[32]{};
        auto whole = dmaMemoryIoResource(memory, 16);
        auto alias = dmaMemoryIoResource(memory + 8, 8);
        IoResourceLease dma{};
        claim(owner, whole, dma);
        IoResourceLease conflict{};
        assert(reserveIoResources(owner, &alias, 1, IoAcquirePolicy::exclusive, conflict) ==
               IoResourceResult::conflict);
        assert(state(alias) == IoResourceState::active);
        auto overflow = dmaMemoryIoResource(reinterpret_cast<void *>(UINTPTR_MAX - 1), 8);
        assert(reserveIoResources(owner, &overflow, 1, IoAcquirePolicy::exclusive, conflict) ==
               IoResourceResult::invalid_argument);
        assert(releaseIoResources(dma) == IoResourceResult::success);
    }
    else if (scenario == "threads")
    {
        assert(releaseIoResources(first) == IoResourceResult::success);
        std::vector<std::thread> threads;
        for (std::uint8_t index = 0; index < 4; ++index)
        {
            threads.emplace_back(
                [index]()
                {
                    for (unsigned attempt = 0; attempt < 500; ++attempt)
                    {
                        IoResourceLease lease{};
                        const auto result =
                            reserveIoResources({IoOwnerKind::application, index}, &block, 1,
                                               IoAcquirePolicy::exclusive, lease);
                        assert(result == IoResourceResult::success ||
                               result == IoResourceResult::conflict);
                        if (result == IoResourceResult::success)
                        {
                            assert(commitIoResources(lease) == IoResourceResult::success);
                            assert(releaseIoResources(lease) == IoResourceResult::success);
                        }
                    }
                });
        }
        for (auto &thread : threads)
        {
            thread.join();
        }
        assert(state(block) == IoResourceState::free);
    }
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    scenario = argv[1];
    resetIoResourceManagerForTest();
    if (scenario == "stale" || scenario == "transfer" || scenario == "borrow" ||
        scenario == "capacity" || scenario == "dma" || scenario == "threads")
    {
        managerScenario();
        return 0;
    }
    device dev{};
    pinctrl_dev_config pinctrl{original_states, 1};
    RuntimePeripheralRoute route(&dev, &pinctrl, owner, IoResourceKind::serial_block, 0);
    PeripheralRouteConfiguration config{};
    config.pin_count = 2;
    config.logical_pins[1] = scenario == "alias" ? 10 : 1;
    config.signals[0] = PeripheralSignal::spi_sck;
    config.signals[1] = PeripheralSignal::spi_mosi;
    assert(!route.activate() && route.lastError() == RuntimePeripheralRouteError::not_staged);
    assert(route.stage(config));
    if (scenario == "guards")
    {
        mock_in_isr = true;
        assert(!route.stage(config) && !route.activate() && !route.deactivate());
        IoResourceLease rejected{};
        assert(reserveIoResources(owner, &block, 1, IoAcquirePolicy::exclusive, rejected) ==
               IoResourceResult::invalid_context);
        mock_in_isr = false;
        config.logical_pins[1] = 0;
        assert(!route.stage(config));
        dev.ready = false;
        assert(!route.activate() &&
               route.lastError() == RuntimePeripheralRouteError::device_not_ready);
        dev.ready = true;
        active_device = true;
        assert(!route.activate() &&
               route.lastError() == RuntimePeripheralRouteError::device_not_suspended);
        assert(state(block) == IoResourceState::free && locks == 0);
        return 0;
    }
    if (scenario == "block")
    {
        IoResourceLease blocker{};
        claim({IoOwnerKind::wire, 0}, block, blocker);
        assert(!route.activate() &&
               route.lastError() == RuntimePeripheralRouteError::ownership_conflict);
        assert(releaseIoResources(blocker) == IoResourceResult::success);
        assert(route.activate() && route.deactivate());
        return 0;
    }
    const bool starts = scenario == "cycle" || scenario == "put_retry" ||
                        scenario == "restore_pinctrl" || scenario == "restore_pin" ||
                        scenario == "stale_release";
    assert(route.activate() == starts);
    if (starts)
    {
        assert(route.active() && references == 1 && locks == 0);
        assert(!route.activate() && !route.stage(config));
        if (scenario == "stale_release")
        {
            /** @brief pin 복구는 보존하고 block만 다른 generation으로 전환합니다. */
            IoResourceLease changed{};
            assert(transferIoResources(owner, {IoOwnerKind::wire, 0}, &block, 1, changed) ==
                   IoResourceResult::success);
            assert(commitIoResources(changed) == IoResourceResult::success);
        }
        if (scenario == "put_retry")
        {
            assert(!route.deactivate() && route.active() && !route.faulted());
            assert(references == 1 && state(block) == IoResourceState::active);
        }
        const bool fails = scenario == "restore_pinctrl" || scenario == "restore_pin" ||
                           scenario == "stale_release";
        assert(route.deactivate() != fails);
        if (!fails)
        {
            assert(route.deactivate() && references == 0 && locks == 0);
            assert(state(block) == IoResourceState::free && pinctrl.states == original_states);
            assert(route.activate() && route.deactivate());
            return 0;
        }
    }
    const bool fatal = scenario == "unwind_put" || scenario == "unwind_pinctrl" ||
                       scenario == "rollback" || scenario == "restore_pinctrl" ||
                       scenario == "restore_pin" || scenario == "stale_release";
    assert(locks == 0 && !route.active() && route.faulted() == fatal);
    if (fatal)
    {
        assert(state(block) != IoResourceState::free);
        assert(!route.activate() && !route.stage(config) && !route.deactivate());
        assert(references == (scenario == "unwind_put" ? 1 : 0));
        if (scenario != "stale_release")
        {
            assert(state(pinResource(1)) != IoResourceState::free);
        }
    }
    else
    {
        assert(references == 0 && state(block) == IoResourceState::free);
        assert(state(pinResource(0)) == IoResourceState::free &&
               state(pinResource(1)) == IoResourceState::free);
        assert(route.deactivate());
        scenario = "cycle";
        config.logical_pins[1] = 1;
        assert(route.stage(config) && route.activate() && route.deactivate());
    }
}
