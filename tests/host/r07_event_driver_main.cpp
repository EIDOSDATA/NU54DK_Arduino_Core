/** @file @brief production DPPI의 endpoint·channel·반환·thread 동작을 검증합니다. */
#include <nucode/EventFabric.h>
#include <hal/nrf_dppi.h>
#include <zephyr/kernel.h>
#include "fabric_driver_stubs/resource_mock.h"
#include <cassert>
#include <cstring>
#include <thread>
#include <vector>

using namespace nucode::arduino;

int main(int argc, char **argv)
{
    assert(argc == 2);
    auto *const dppi = eventFabric().dppi(20U);
    const EventEndpoint publisher{0x1000U, 20U, EventEndpointRole::publisher};
    const EventEndpoint subscriber{0x2000U, 20U, EventEndpointRole::subscriber};
    if (std::strcmp(argv[1], "lookup") == 0)
    {
        assert(eventFabric().dppi(99U) == nullptr);
        assert(dppi == eventFabric().dppi(20U));
        assert(eventFabric().dppi(0U)->channelCount() == 8U);
        assert(eventFabric().dppi(10U)->channelCount() == 24U);
        assert(dppi->channelCount() == 16U);
        assert(eventFabric().dppi(30U)->channelCount() == 4U);
        assert(dppi->acquireChannel(16U) == EventFabricResult::invalid_argument);
        assert(dppi->acquireGroup(0U, 1U) == EventFabricResult::invalid_argument);
    }
    else if (std::strcmp(argv[1], "threads") == 0)
    {
        std::vector<std::thread> workers;
        for (unsigned worker = 0U; worker < 4U; ++worker)
        {
            workers.emplace_back(
                [worker, dppi]()
                {
                    for (unsigned round = 0U; round < 500U; ++round)
                    {
                        const EventEndpoint event{0x3000U + worker * 16U, 20U,
                                                  EventEndpointRole::publisher};
                        const EventEndpoint task{0x4000U + worker * 16U, 20U,
                                                 EventEndpointRole::subscriber};
                        assert(dppi->acquireChannel(worker) == EventFabricResult::success);
                        assert(dppi->connect(event, task, worker) == EventFabricResult::success);
                        assert(dppi->releaseChannel(worker) == EventFabricResult::success);
                    }
                });
        }
        for (auto &worker : workers)
        {
            worker.join();
        }
    }
    else
    {
        assert(dppi->connect(publisher, subscriber, 0U) == EventFabricResult::wrong_state);
        assert(dppi->acquireChannel(0U) == EventFabricResult::success);
        assert(dppi->acquireChannel(0U) == EventFabricResult::wrong_state);
        if (std::strcmp(argv[1], "invalid") == 0)
        {
            const EventEndpoint invalid[] = {{0U, 20U, EventEndpointRole::publisher},
                                             {0x1001U, 20U, EventEndpointRole::publisher},
                                             {0x1000U, 10U, EventEndpointRole::publisher},
                                             {0x1000U, 20U, EventEndpointRole::subscriber}};
            for (const auto &endpoint : invalid)
            {
                assert(dppi->connect(endpoint, subscriber, 0U) ==
                       EventFabricResult::unsupported_route);
            }
            assert(dppi->connect(publisher, {0x2001U, 20U, EventEndpointRole::subscriber}, 0U) ==
                   EventFabricResult::unsupported_route);
            assert(mock_endpoints.empty());
        }
        else if (std::strcmp(argv[1], "capacity") == 0)
        {
            for (unsigned index = 0U; index < 4U; ++index)
            {
                assert(dppi->connect(publisher,
                                     {0x2000U + index * 4U, 20U, EventEndpointRole::subscriber},
                                     0U) == EventFabricResult::success);
            }
            assert(dppi->connect(publisher, subscriber, 0U) == EventFabricResult::success);
            assert(dppi->connect(publisher, {0x2100U, 20U, EventEndpointRole::subscriber}, 0U) ==
                   EventFabricResult::resource_exhausted);
            assert(mock_endpoints.size() == 5U);
            assert(dppi->connect({0x1100U, 20U, EventEndpointRole::publisher}, subscriber, 0U) ==
                   EventFabricResult::ownership_conflict);
        }
        else if (std::strcmp(argv[1], "disconnect") == 0)
        {
            assert(dppi->connect(publisher, subscriber, 0U) == EventFabricResult::success);
            assert(dppi->disconnect(publisher, {0x2100U, 20U, EventEndpointRole::subscriber}, 0U) ==
                   EventFabricResult::invalid_argument);
            assert(mock_endpoints.size() == 2U);
            assert(dppi->disconnect(publisher, subscriber, 0U) == EventFabricResult::success);
            assert(mock_endpoints.empty());
            assert(dppi->disconnect(publisher, subscriber, 0U) ==
                   EventFabricResult::invalid_argument);
        }
        else if (std::strcmp(argv[1], "release") == 0)
        {
            assert(dppi->connect(publisher, subscriber, 0U) == EventFabricResult::success);
            assert(dppi->enable(0U) == EventFabricResult::success);
            assert(NRF_DPPIC20->enabled == 1U);
        }
        else if (std::strcmp(argv[1], "isr") == 0)
        {
            mock_in_isr = true;
            assert(dppi->connect(publisher, subscriber, 0U) == EventFabricResult::invalid_context);
            assert(dppi->releaseChannel(0U) == EventFabricResult::invalid_context);
            mock_in_isr = false;
            assert(mock_live_leases == 1);
        }
        else
        {
            assert(false);
        }
        assert(dppi->releaseChannel(0U) == EventFabricResult::success);
        assert(dppi->releaseChannel(0U) == EventFabricResult::wrong_state);
    }
    assert(mock_live_leases == 0);
    assert(mock_endpoints.empty());
    assert(NRF_DPPIC20->enabled == 0U);
}
