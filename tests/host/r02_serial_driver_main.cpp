/**
 * @file
 * @brief production SPIM/TWIM과 SerialFabric의 완료·DMA·수명주기를 실제 thread로 검증합니다.
 * @details fake nrfx는 전기적 동작을 보증하지 않으며 callback과 STOP 경계만 제어합니다.
 */
#if defined(TEST_SPIM)
#include "../../cores/arduino/SpimFabric.cpp"
#else
#include "../../cores/arduino/TwimFabric.cpp"
#endif
#include <hal/nrf_gpio.h>
#include <cassert>
#include <condition_variable>
#include <cstring>
#include <iostream>

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
unsigned releases = 0;
namespace nucode::arduino::internal
{
    SerialFabricResult validateNu54dkSerialFabricRoute(SerialPersonality, std::uint8_t,
                                                       const SerialFabricConfiguration &config,
                                                       ValidatedSerialRoute &route,
                                                       IoResourceId *resources, std::size_t,
                                                       std::size_t &count) noexcept
    {
        route.pin_count = config.pin_count;
        for (std::size_t i = 0; i < config.pin_count; ++i)
        {
            route.pins[i] = config.pins[i];
        }
        route.dma_workspace_count = config.dma_workspace_count;
        for (std::size_t i = 0; i < config.dma_workspace_count; ++i)
        {
            route.dma_workspaces[i] = config.dma_workspaces[i];
        }
        resources[0] = peripheralIoResource(IoResourceKind::serial_block, 20);
        count = 1;
        return SerialFabricResult::success;
    }
    SerialFabricResult nu54dkSerialFabricPsel(pin_size_t pin, std::uint32_t &psel) noexcept
    {
        psel = pin;
        return SerialFabricResult::success;
    }
    IoResourceResult reserveIoResources(IoResourceOwner owner, const IoResourceId *, std::size_t,
                                        IoAcquirePolicy, IoResourceLease &lease,
                                        IoResourceSnapshot *) noexcept
    {
        lease.owner = owner;
        lease.phase = IoLeasePhase::reserved;
        return IoResourceResult::success;
    }
    IoResourceResult commitIoResources(IoResourceLease &lease) noexcept
    {
        lease.phase = IoLeasePhase::committed;
        return IoResourceResult::success;
    }
    IoResourceResult rollbackIoResources(IoResourceLease &) noexcept
    {
        return IoResourceResult::success;
    }
    IoResourceResult releaseIoResources(IoResourceLease &) noexcept
    {
        ++releases;
        return IoResourceResult::success;
    }
} // namespace nucode::arduino::internal

alignas(4) std::uint8_t memory[64]{};
#if defined(TEST_SPIM)
auto *handle = serialFabric().spim(20);
using Event = SpiFabricEvent;
auto submit()
{
    return handle->transferAsync(memory, 8, memory + 32, 8);
}
auto transfer(std::uint32_t timeout)
{
    return handle->transfer(memory, 8, memory + 32, 8, timeout);
}
#else
auto *handle = serialFabric().twim(20);
using Event = TwiFabricEvent;
auto submit()
{
    return handle->transferAsync(0x42, memory, 8, memory + 32, 8);
}
auto transfer(std::uint32_t timeout)
{
    return handle->transfer(0x42, memory, 8, memory + 32, 8, timeout);
}
#endif
auto &driver = nucode::arduino::contextFor(20)->driver;
void setup()
{
    assert(nucode::arduino::registerAdapters() == 0);
    SerialSignalPin pins[] = {{SerialSignal::sck, 1},
                              {SerialSignal::mosi, 2},
                              {SerialSignal::miso, 3},
                              {SerialSignal::scl, 4},
                              {SerialSignal::sda, 5}};
    SerialDmaWorkspace workspace{memory, sizeof(memory)};
    SerialFabricConfiguration config{};
    config.pins = pins;
    config.pin_count = 5;
    config.dma_workspaces = &workspace;
    config.dma_workspace_count = 1;
    assert(handle->stage(config) == SerialFabricResult::success);
    assert(handle->activate() == SerialFabricResult::success);
#if !defined(TEST_SPIM)
    mock_stop = []
    {
        mock_complete(driver);
    };
#endif
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    setup();
    if (std::strcmp(argv[1], "stale") == 0)
    {
        /** @brief 같은 DMA 주소의 이전 완료는 현재 timeout을 성공으로 바꾸면 안 됩니다. */
        assert(submit() == SerialFabricResult::success);
        mock_complete(driver);
        assert(transfer(21) == SerialFabricResult::stop_timeout);
        assert(waited_us >= 21);
    }
    else if (std::strcmp(argv[1], "consumer") == 0)
    {
        bool completed = false;
        mock_wait = [&](std::uint32_t)
        {
            if (!completed)
            {
                completed = true;
                mock_complete(driver);
                Event event{};
                while (handle->takeEvent(event))
                {
                }
            }
        };
        assert(transfer(50) == SerialFabricResult::success);
    }
    else if (std::strcmp(argv[1], "overflow") == 0)
    {
        for (unsigned i = 0; i < 10; ++i)
        {
            assert(submit() == SerialFabricResult::success);
            mock_complete(driver);
        }
        unsigned ticks = 0;
        mock_wait = [&](std::uint32_t)
        {
            if (++ticks == 3)
            {
                mock_complete(driver);
            }
        };
        assert(transfer(100) == SerialFabricResult::success);
        assert(ticks == 3);
    }
    else if (std::strcmp(argv[1], "deadline") == 0)
    {
        assert(transfer(0) == SerialFabricResult::invalid_argument);
        mock_wait = [](std::uint32_t)
        {
            mock_complete(driver);
        };
        assert(transfer(1) == SerialFabricResult::success);
        assert(waited_us == 1);
        assert(transfer(UINT32_MAX) == SerialFabricResult::success);
    }
    else if (std::strcmp(argv[1], "stop_failure") == 0)
    {
        mock_stop_ready = false;
        assert(submit() == SerialFabricResult::success);
#if defined(TEST_SPIM)
        assert(handle->cancelTransfer() == SerialFabricResult::stop_timeout);
#else
        assert(handle->cancelTransfer() == SerialFabricResult::success);
#endif
        assert(handle->bufferState(memory) == DmaBufferState::dma_owned);
        assert(submit() != SerialFabricResult::success);
        assert(handle->deactivate(30) == SerialFabricResult::stop_timeout);
        assert(handle->state() == SerialFabricState::faulted);
        assert(releases == 0);
    }
    else if (std::strcmp(argv[1], "submit_deactivate") == 0)
    {
        std::mutex mutex;
        std::condition_variable condition;
        bool inside = false, proceed = false;
        std::atomic<bool> deactivated{false}, attempting{false};
        mock_submit = [&]
        {
            std::unique_lock<std::mutex> lock(mutex);
            inside = true;
            condition.notify_all();
            condition.wait(lock,
                           [&]
                           {
                               return proceed;
                           });
        };
        std::thread producer(
            []
            {
                assert(submit() == SerialFabricResult::success);
            });
        {
            std::unique_lock<std::mutex> lock(mutex);
            condition.wait(lock,
                           [&]
                           {
                               return inside;
                           });
        }
        std::thread closer(
            [&]
            {
                attempting = true;
                assert(handle->deactivate(100) == SerialFabricResult::success);
                deactivated = true;
            });
        while (!attempting)
        {
            std::this_thread::yield();
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        assert(!deactivated);
        {
            std::lock_guard<std::mutex> lock(mutex);
            proceed = true;
            condition.notify_all();
        }
        producer.join();
        closer.join();
        assert(deactivated && releases == 1);
        assert(submit() == SerialFabricResult::wrong_state);
    }
    else if (std::strcmp(argv[1], "reservation") == 0)
    {
        /** @brief 완료 callback 뒤에도 waiter가 읽기 전까지 다음 제출은 거부합니다. */
        mock_wait = [](std::uint32_t)
        {
            mock_complete(driver);
            assert(submit() == SerialFabricResult::wrong_state);
        };
        assert(transfer(50) == SerialFabricResult::success);
        mock_wait = {};
        assert(submit() == SerialFabricResult::success);
        mock_complete(driver);
    }
    else if (std::strcmp(argv[1], "errors") == 0)
    {
        mock_submit_error = -EIO;
        assert(transfer(50) == SerialFabricResult::driver_error);
        assert(handle->bufferState(memory) == DmaBufferState::error);
        mock_submit_error = 0;
#if !defined(TEST_SPIM)
        mock_wait = [](std::uint32_t)
        {
            mock_complete(driver, NRFX_TWIM_EVT_ADDRESS_NACK);
        };
        assert(transfer(50) == SerialFabricResult::driver_error);
        assert(handle->bufferState(memory) == DmaBufferState::error);
#endif
        mock_wait = [](std::uint32_t)
        {
            mock_complete(driver);
        };
        assert(transfer(50) == SerialFabricResult::success);
    }
    else if (std::strcmp(argv[1], "generation_wrap") == 0)
    {
        nucode::arduino::contextFor(20)->operation_generation = UINT32_MAX - 1U;
        assert(submit() == SerialFabricResult::success);
        mock_complete(driver);
        mock_wait = [](std::uint32_t)
        {
            mock_complete(driver);
        };
        assert(transfer(20) == SerialFabricResult::success);
        assert(nucode::arduino::contextFor(20)->operation_generation == 0U);
        assert(transfer(20) == SerialFabricResult::success);
    }
    else if (std::strcmp(argv[1], "late_stop") == 0)
    {
        mock_stop_ready = false;
        assert(transfer(21) == SerialFabricResult::stop_timeout);
        assert(handle->bufferState(memory) == DmaBufferState::dma_owned);
        assert(submit() == SerialFabricResult::wrong_state);
        mock_stop_ready = true;
        assert(handle->cancelTransfer() == SerialFabricResult::success);
        assert(handle->bufferState(memory) == DmaBufferState::cancelled);
        /** @brief terminal 뒤 들어온 중복 callback은 buffer를 다시 완료로 바꾸지 않습니다. */
        mock_complete(driver);
        assert(handle->bufferState(memory) == DmaBufferState::cancelled);
        mock_wait = [](std::uint32_t)
        {
            mock_complete(driver);
        };
        assert(transfer(50) == SerialFabricResult::success);
    }
    else if (std::strcmp(argv[1], "wait_deactivate") == 0)
    {
        bool once = false;
        mock_wait = [&](std::uint32_t)
        {
            if (!once)
            {
                once = true;
                assert(handle->deactivate(100) == SerialFabricResult::success);
            }
        };
        assert(transfer(200) == SerialFabricResult::stop_timeout);
        assert(releases == 1);
    }
    else if (std::strcmp(argv[1], "other_thread") == 0)
    {
        /** @brief 동기 waiter가 실행 중일 때 다른 thread의 fabric 조회가 완료됩니다. */
        std::mutex mutex;
        std::condition_variable condition;
        bool waiting = false, queried = false;
        mock_wait = [&](std::uint32_t)
        {
            std::unique_lock<std::mutex> lock(mutex);
            waiting = true;
            condition.notify_all();
            condition.wait(lock,
                           [&]
                           {
                               return queried;
                           });
            mock_complete(driver);
        };
        std::thread reader(
            [&]
            {
                {
                    std::unique_lock<std::mutex> lock(mutex);
                    condition.wait(lock,
                                   [&]
                                   {
                                       return waiting;
                                   });
                }
                assert(handle->state() == SerialFabricState::active);
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    queried = true;
                    condition.notify_all();
                }
            });
        assert(transfer(50) == SerialFabricResult::success);
        reader.join();
    }
    else
    {
        return 2;
    }
    std::cout << "R02_DRIVER_PASS=" << argv[1] << '\n';
}
