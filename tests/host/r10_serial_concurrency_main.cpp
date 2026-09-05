/** @file @brief 실제 lifecycle·manager와 지연 STOP 경계의 동시 호출을 검사합니다. */
#include <nucode/SerialFabric.h>
#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"
#include <hal/nrf_gpio.h>
#include <zephyr/kernel.h>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <string>
#include <thread>
using namespace nucode::arduino;
using namespace nucode::arduino::internal;
NRF_GPIO_Type mock_gpio[3]{};
int nrfx_power_constlat_mode_request()
{
    return 0;
}
int nrfx_power_constlat_mode_free()
{
    return 0;
}
namespace nucode::arduino::internal
{
    SerialFabricResult validateNu54dkSerialFabricRoute(SerialPersonality, std::uint8_t instance,
                                                       const SerialFabricConfiguration &,
                                                       ValidatedSerialRoute &route,
                                                       IoResourceId *resources, std::size_t,
                                                       std::size_t &count) noexcept
    {
        /** @brief 핀 정책은 기존 route 시험이 담당하고 여기서는 block 배타성을 고정합니다. */
        route = {};
        resources[0] = peripheralIoResource(IoResourceKind::serial_block, instance);
        count = 1;
        return SerialFabricResult::success;
    }
    SerialFabricResult nu54dkSerialFabricPsel(pin_size_t pin, std::uint32_t &psel) noexcept
    {
        psel = pin;
        return SerialFabricResult::success;
    }
} // namespace nucode::arduino::internal
namespace
{
    std::string scenario;
    std::mutex gate_mutex;
    std::condition_variable gate;
    bool waiting = false;
    bool complete_stop = false;
    bool competitor_done = false;
    std::atomic<unsigned> irqs{0};
    SerialFabricResult validate(std::uint8_t, const ValidatedSerialRoute &, int &) noexcept
    {
        return SerialFabricResult::success;
    }
    SerialFabricResult activate(std::uint8_t, const ValidatedSerialRoute &, int &) noexcept
    {
        return SerialFabricResult::success;
    }
    SerialFabricResult request(std::uint8_t instance, int &error) noexcept
    {
        if (instance == 20 && scenario == "request_error")
        {
            error = -5;
            return SerialFabricResult::driver_error;
        }
        return SerialFabricResult::success;
    }
    bool stopped(std::uint8_t instance) noexcept
    {
        if (instance == 20)
        {
            std::unique_lock<std::mutex> lock(gate_mutex);
            waiting = true;
            gate.notify_all();
            gate.wait(lock,
                      []
                      {
                          return complete_stop;
                      });
            return scenario != "timeout";
        }
        return true;
    }
    SerialFabricResult deactivate(std::uint8_t instance, int &error) noexcept
    {
        if (instance == 20 && scenario == "driver_error")
        {
            error = -5;
            return SerialFabricResult::driver_error;
        }
        return SerialFabricResult::success;
    }
    void irq(std::uint8_t) noexcept
    {
        ++irqs;
    }
    SerialFabricDriverAdapter adapter{validate, activate, request, stopped, deactivate, irq};
    IoResourceState resourceState(std::uint8_t instance)
    {
        IoResourceSnapshot snapshot{};
        const auto resource = peripheralIoResource(IoResourceKind::serial_block, instance);
        assert(ioResourceSnapshot(resource, snapshot) == IoResourceResult::success);
        return snapshot.state;
    }
} // namespace
int main(int argc, char **argv)
{
    assert(argc == 2);
    scenario = argv[1];
    auto *first = serialFabric().uarte(20);
    auto *other = serialFabric().uarte(21);
    auto *alias = serialFabric().twim(20);
    assert(registerSerialFabricAdapter(SerialPersonality::uarte, 20, adapter) ==
           SerialFabricResult::success);
    assert(registerSerialFabricAdapter(SerialPersonality::uarte, 21, adapter) ==
           SerialFabricResult::success);
    assert(registerSerialFabricAdapter(SerialPersonality::twim, 20, adapter) ==
           SerialFabricResult::success);
    SerialFabricConfiguration config{};
    assert(first->stage(config) == SerialFabricResult::success);
    assert(alias->stage(config) == SerialFabricResult::success);
    assert(other->stage(config) == SerialFabricResult::success);
    assert(first->activate() == SerialFabricResult::success);
    if (scenario == "request_error")
    {
        assert(first->deactivate(27) == SerialFabricResult::driver_error);
        assert(first->state() == SerialFabricState::faulted);
        assert(resourceState(20) == IoResourceState::active);
        assert(other->activate() == SerialFabricResult::success &&
               other->deactivate(27) == SerialFabricResult::success);
        return 0;
    }
    SerialFabricResult stop_result = SerialFabricResult::wrong_state;
    std::thread stopper(
        [&]
        {
            stop_result = first->deactivate(27);
        });
    {
        std::unique_lock<std::mutex> lock(gate_mutex);
        assert(gate.wait_for(lock, std::chrono::seconds(2),
                             []
                             {
                                 return waiting;
                             }));
    }
    assert(resourceState(20) == IoResourceState::active);
    dispatchSerialFabricIrq(20);
    assert(irqs == 1);
    SerialFabricResult competitor_result = SerialFabricResult::driver_error;
    std::thread competitor(
        [&]
        {
            if (scenario == "same_handle")
            {
                competitor_result = first->deactivate(27);
                assert(first->stage(config) == SerialFabricResult::wrong_state);
                const SerialFabricOperationGuard guard;
                assert(!isSerialFabricHandleActive(SerialPersonality::uarte, 20));
            }
            else if (scenario == "same_block")
            {
                competitor_result = alias->activate();
            }
            else
            {
                competitor_result = other->activate();
            }
            std::lock_guard<std::mutex> lock(gate_mutex);
            competitor_done = true;
            gate.notify_all();
        });
    bool progressed = false;
    {
        std::unique_lock<std::mutex> lock(gate_mutex);
        /** @brief 처리량 측정이 아니라 STOP 미완료 중 호출 종료 여부를 판별합니다. */
        progressed = gate.wait_for(lock, std::chrono::seconds(1),
                                   []
                                   {
                                       return competitor_done;
                                   });
        complete_stop = true;
        gate.notify_all();
    }
    stopper.join();
    competitor.join();
    assert(progressed);
    if (scenario == "same_handle" || scenario == "same_block")
    {
        assert(competitor_result == SerialFabricResult::wrong_state);
    }
    else
    {
        assert(competitor_result == SerialFabricResult::success);
        assert(other->deactivate(27) == SerialFabricResult::success);
    }
    const bool failed = scenario == "timeout" || scenario == "driver_error";
    assert(stop_result == (scenario == "timeout"        ? SerialFabricResult::stop_timeout
                           : scenario == "driver_error" ? SerialFabricResult::driver_error
                                                        : SerialFabricResult::success));
    assert(resourceState(20) == (failed ? IoResourceState::active : IoResourceState::free));
    assert(first->state() == (failed ? SerialFabricState::faulted : SerialFabricState::inactive));
    if (scenario == "timeout")
    {
        assert(waited_us == 27);
    }
}
