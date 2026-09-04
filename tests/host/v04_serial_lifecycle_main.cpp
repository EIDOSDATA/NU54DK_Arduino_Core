// Native execution of production SerialFabric.cpp with fake hardware/resources.
// This verifies transaction behavior, not electrical HIL or the nrfx adapters.
#include <nucode/SerialFabric.h>
#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"
#include <hal/nrf_gpio.h>
#include <cassert>
#include <cerrno>
#include <cstdint>

using namespace nucode::arduino;
using namespace nucode::arduino::internal;
NRF_GPIO_Type mock_gpio[3]{};
std::uint64_t waited_us = 0;
int refs = 0, requests = 0, frees = 0, activations = 0, deactivations = 0;
int rollbacks = 0, releases = 0, irq_calls = 0;
bool reserve_fail = false, commit_fail = false, activate_fail = false;
bool stop_ready = true, stop_fail = false, deactivate_fail = false;
bool reserved = false;
int nrfx_power_constlat_mode_request() { ++requests; return refs++ ? -EALREADY : 0; }
int nrfx_power_constlat_mode_free() { assert(refs > 0); ++frees; return --refs ? -EBUSY : 0; }

namespace nucode::arduino::internal
{
    SerialFabricResult validateNu54dkSerialFabricRoute(SerialPersonality, std::uint8_t,
        const SerialFabricConfiguration &config, ValidatedSerialRoute &route,
        IoResourceId *resources, std::size_t, std::size_t &count) noexcept
    {
        route.route = config.route;
        route.pin_count = config.pin_count;
        for (std::size_t i = 0; i < config.pin_count; ++i) route.pins[i] = config.pins[i];
        resources[0] = peripheralIoResource(IoResourceKind::serial_block, 20);
        count = 1;
        return SerialFabricResult::success;
    }
    SerialFabricResult nu54dkSerialFabricPsel(pin_size_t pin, std::uint32_t &psel) noexcept
    { psel = pin; return SerialFabricResult::success; }
    IoResourceResult reserveIoResources(IoResourceOwner owner, const IoResourceId *, std::size_t,
        IoAcquirePolicy, IoResourceLease &lease, IoResourceSnapshot *) noexcept
    {
        if (reserve_fail || reserved) return IoResourceResult::conflict;
        lease.owner = owner; lease.phase = IoLeasePhase::reserved; reserved = true;
        return IoResourceResult::success;
    }
    IoResourceResult commitIoResources(IoResourceLease &lease) noexcept
    {
        if (commit_fail) return IoResourceResult::wrong_phase;
        lease.phase = IoLeasePhase::committed; return IoResourceResult::success;
    }
    IoResourceResult rollbackIoResources(IoResourceLease &) noexcept
    { assert(reserved); reserved = false; ++rollbacks; return IoResourceResult::success; }
    IoResourceResult releaseIoResources(IoResourceLease &) noexcept
    { assert(reserved); reserved = false; ++releases; return IoResourceResult::success; }
}

SerialFabricResult validate(std::uint8_t, const ValidatedSerialRoute &, int &) noexcept
{ return SerialFabricResult::success; }
SerialFabricResult activate(std::uint8_t instance, const ValidatedSerialRoute &route, int &) noexcept
{
    assert(reserved);
    if (instance == 20 && route.route == SerialRouteClass::p2_dedicated20) assert(refs > 0);
    ++activations;
    // A fake failed init can still have changed pad configuration, but no DMA.
    mock_gpio[2].PIN_CNF[2] = 99;
    nrf_gpio_pin_write(66, 0);
    return activate_fail ? SerialFabricResult::driver_error : SerialFabricResult::success;
}
SerialFabricResult stop(std::uint8_t, int &) noexcept
{ return stop_fail ? SerialFabricResult::driver_error : SerialFabricResult::success; }
bool stopped(std::uint8_t) noexcept { return stop_ready; }
SerialFabricResult deactivate(std::uint8_t, int &) noexcept
{
    assert(stop_ready && reserved);
    ++deactivations;
    return deactivate_fail ? SerialFabricResult::driver_error : SerialFabricResult::success;
}
void irq(std::uint8_t) noexcept { ++irq_calls; }
const SerialFabricDriverAdapter adapter{validate, activate, stop, stopped, deactivate, irq};
const SerialSignalPin pins[] = {{SerialSignal::txd, 66}, {SerialSignal::rxd, 64}};

UarteHandle *prepare(std::uint8_t instance = 20)
{
    resetSerialFabricForTest(); // fake drivers only
    refs = requests = frees = activations = deactivations = rollbacks = releases = irq_calls = 0;
    reserved = reserve_fail = commit_fail = activate_fail = stop_fail = deactivate_fail = false;
    stop_ready = true; waited_us = 0;
    for (auto &port : mock_gpio) port = {};
    mock_gpio[2].PIN_CNF[2] = 23;
    mock_gpio[2].PIN_CNF[0] = 42;
    mock_gpio[2].PIN_CNF[9] = 77;
    mock_gpio[2].out = (1U << 2) | (1U << 9);
    assert(registerSerialFabricAdapter(SerialPersonality::uarte, instance, adapter) == SerialFabricResult::success);
    auto *handle = serialFabric().uarte(instance);
    assert(handle->stage({SerialRouteClass::p2_dedicated20, SerialElectricalProfile::connector_fixture, pins, 2}) == SerialFabricResult::success);
    assert(requests == 0 && mock_gpio[2].PIN_CNF[2] == 23);
    return handle;
}
void restored()
{
    assert(mock_gpio[2].PIN_CNF[2] == 23 && mock_gpio[2].PIN_CNF[0] == 42);
    assert(mock_gpio[2].PIN_CNF[9] == 77 && mock_gpio[2].out == ((1U << 2) | (1U << 9)));
}
int main()
{
    auto *handle = prepare();
    refs = 1; // unrelated nrfx owner survives our EALREADY/EBUSY pair
    assert(handle->activate() == SerialFabricResult::success && refs == 2);
    dispatchSerialFabricIrq(20); assert(irq_calls == 1);
    assert(handle->deactivate() == SerialFabricResult::success);
    assert(refs == 1 && requests == 1 && frees == 1 && releases == 1);
    dispatchSerialFabricIrq(20); assert(irq_calls == 1); restored();

    handle = prepare(0);
    assert(handle->activate() == SerialFabricResult::success && requests == 0);
    assert(handle->deactivate() == SerialFabricResult::success && frees == 0); restored();

    handle = prepare(); reserve_fail = true;
    assert(handle->activate() == SerialFabricResult::ownership_conflict);
    assert(requests == 0 && activations == 0); restored();

    handle = prepare(); activate_fail = true;
    assert(handle->activate() == SerialFabricResult::driver_error);
    assert(refs == 0 && frees == 1 && rollbacks == 1 && !reserved); restored();

    handle = prepare(); commit_fail = true;
    assert(handle->activate() == SerialFabricResult::release_failed);
    assert(refs == 0 && frees == 1 && deactivations == 1 && rollbacks == 1); restored();

    handle = prepare(); commit_fail = true; stop_ready = false;
    assert(handle->activate() == SerialFabricResult::stop_timeout);
    assert(waited_us == 100000 && reserved && refs == 1 && frees == 0 && deactivations == 0);
    assert(handle->state() == SerialFabricState::faulted && rollbacks == 0);

    handle = prepare(); assert(handle->activate() == SerialFabricResult::success);
    stop_ready = false;
    assert(handle->deactivate(17) == SerialFabricResult::stop_timeout);
    assert(waited_us == 17 && reserved && refs == 1 && frees == 0 && releases == 0);
    assert(handle->activate() == SerialFabricResult::faulted);

    handle = prepare(); assert(handle->activate() == SerialFabricResult::success);
    deactivate_fail = true;
    assert(handle->deactivate() == SerialFabricResult::driver_error);
    assert(reserved && refs == 1 && frees == 0 && releases == 0);
    assert(mock_gpio[2].PIN_CNF[2] == 99); // not restored before proven adapter cleanup
    resetSerialFabricForTest();
}
