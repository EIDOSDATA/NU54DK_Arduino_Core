/** @file @brief production StreamFabric의 STOP·overflow·다른 block 진행을 검증합니다. */
#include "../../cores/arduino/StreamFabric.cpp"
#include "../../cores/arduino/internal/stream/PdmFabric.cpp"
#include "../../cores/arduino/internal/stream/I2sFabric.cpp"
#include "../../cores/arduino/internal/stream/QdecFabric.cpp"
#include "fabric_driver_stubs/resource_mock.h"
#include <condition_variable>
#include <cstring>
#include <iostream>
using namespace nucode::arduino;
auto *i2s = streamFabric().i2s(20);
auto *pdm = streamFabric().pdm(20);
auto *qdec = streamFabric().qdec(21);
const I2sBuffers buffers{reinterpret_cast<std::uint32_t *>(0x20000000U), nullptr, 16};
void startI2s(StreamFabricResult expected = StreamFabricResult::success)
{
    I2sConfiguration configuration{};
    configuration.sck_pin = 0;
    configuration.lrck_pin = 1;
    configuration.data_in_pin = 2;
    assert(i2s->configure(configuration) == StreamFabricResult::success);
    assert(i2s->start(buffers) == expected);
}
void startPdm(StreamFabricResult expected = StreamFabricResult::success)
{
    PdmConfiguration configuration{};
    configuration.clock_pin = 3;
    configuration.data_pin = 4;
    assert(pdm->configure(configuration) == StreamFabricResult::success);
    assert(pdm->start(reinterpret_cast<std::int16_t *>(0x20002000U), 16) == expected);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    (void)nucode::arduino::connectStreamFabricIrqs();
    startI2s();
    if (std::strcmp(argv[1], "i2s_timeout") == 0)
    {
        mock_i2s_stop_ready = false;
        const int leases = mock_live_leases;
        assert(i2s->stop(21) == StreamFabricResult::stop_timeout);
        assert(mock_live_leases == leases && mock_i2s_uninits == 0);
        assert(i2s->start(buffers) == StreamFabricResult::wrong_state);
        mock_i2s_event(&nucode::arduino::i2s_driver, nullptr, NRFX_I2S_STATUS_TRANSFER_STOPPED);
        assert(i2s->stop(1) == StreamFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "pdm_timeout") == 0)
    {
        startPdm();
        mock_pdm_stop_ready = false;
        const int leases = mock_live_leases;
        assert(pdm->stop(21) == StreamFabricResult::stop_timeout);
        assert(mock_live_leases == leases && mock_pdm_uninits == 0);
        assert(waited_us == 21);
        mock_pdm_stop_ready = true;
        assert(pdm->stop(1) == StreamFabricResult::success);
    }
    else if (std::strcmp(argv[1], "other_progress") == 0)
    {
        QdecConfiguration configuration{};
        configuration.phase_a_pin = 5;
        configuration.phase_b_pin = 6;
        assert(qdec->configure(configuration) == StreamFabricResult::success);
        assert(qdec->start() == StreamFabricResult::success);
        mock_i2s_stop_ready = false;
        std::mutex mutex;
        std::condition_variable condition;
        bool waiting = false, advanced = false;
        std::thread worker(
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
                QdecEvent event{};
                assert(qdec->read(event) == StreamFabricResult::success);
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    advanced = true;
                    condition.notify_all();
                }
            });
        mock_wait = [&](std::uint32_t)
        {
            std::unique_lock<std::mutex> lock(mutex);
            waiting = true;
            condition.notify_all();
            assert(condition.wait_for(lock, std::chrono::seconds(1),
                                      [&]
                                      {
                                          return advanced;
                                      }));
            mock_i2s_event(&nucode::arduino::i2s_driver, nullptr, NRFX_I2S_STATUS_TRANSFER_STOPPED);
        };
        assert(i2s->stop(20) == StreamFabricResult::success);
        worker.join();
        assert(mock_qdec_reads == 1);
    }
    else if (std::strcmp(argv[1], "overflow") == 0)
    {
        for (unsigned i = 0; i < 14; ++i)
        {
            mock_i2s_event(&nucode::arduino::i2s_driver, nullptr,
                           NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED);
        }
        const I2sBuffers next{reinterpret_cast<std::uint32_t *>(0x20000100U), nullptr, 16};
        assert(i2s->queueBuffers(next) == StreamFabricResult::success);
        bool overflow = false;
        I2sEvent event{};
        while (i2s->takeEvent(event))
        {
            overflow |= event.driver_error == -ENOBUFS;
        }
        assert(overflow);
    }
    else if (std::strcmp(argv[1], "deadline") == 0)
    {
        mock_i2s_stop_ready = false;
        mock_wait = [](std::uint32_t)
        {
            mock_i2s_event(&nucode::arduino::i2s_driver, nullptr, NRFX_I2S_STATUS_TRANSFER_STOPPED);
        };
        assert(i2s->stop(1) == StreamFabricResult::success);
        assert(waited_us == 1);
        startI2s();
        assert(i2s->stop(UINT32_MAX) == StreamFabricResult::success);
    }
    else if (std::strcmp(argv[1], "repeat") == 0)
    {
        for (unsigned i = 0; i < 20; ++i)
        {
            assert(i2s->stop(20) == StreamFabricResult::success);
            assert(mock_live_leases == 0);
            startPdm();
            assert(pdm->stop(20) == StreamFabricResult::success);
            assert(mock_live_leases == 0);
            if (i != 19)
            {
                startI2s();
            }
        }
    }
    else if (std::strcmp(argv[1], "snapshot") == 0)
    {
        std::atomic<bool> done{false};
        std::thread irq_writer(
            [&]
            {
                for (unsigned i = 0; i < 20000; ++i)
                {
                    mock_i2s_event(&nucode::arduino::i2s_driver, nullptr,
                                   NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED);
                }
                done = true;
            });
        do
        {
            nucode::arduino::record(nucode::arduino::i2s_context, StreamFabricResult::success);
            const auto snapshot = nucode::arduino::i2s_context.diagnostics.snapshot();
            assert((snapshot.result == StreamFabricResult::success && snapshot.driver_error == 0) ||
                   (snapshot.result == StreamFabricResult::resource_exhausted &&
                    snapshot.driver_error == -ENOBUFS));
        } while (!done);
        irq_writer.join();
    }
    else if (std::strcmp(argv[1], "stale_stop") == 0)
    {
        assert(i2s->stop(1) == StreamFabricResult::success);
        startI2s();
        /** @brief 이전 실행의 STOP 기록이 남아 있어도 이번 STOP을 완료시키지 않습니다. */
        mock_i2s_stop_ready = false;
        assert(i2s->stop(21) == StreamFabricResult::stop_timeout);
        assert(mock_live_leases == 2);
        mock_i2s_event(&nucode::arduino::i2s_driver, nullptr, NRFX_I2S_STATUS_TRANSFER_STOPPED);
        assert(i2s->stop(1) == StreamFabricResult::success);
    }
    else if (std::strcmp(argv[1], "stop_queue_full") == 0)
    {
        for (unsigned i = 0; i < 14; ++i)
        {
            mock_i2s_event(&nucode::arduino::i2s_driver, nullptr,
                           NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED);
        }
        assert(i2s->stop(1) == StreamFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "release_failure") == 0)
    {
        mock_release_failure = true;
        assert(i2s->stop(1) == StreamFabricResult::release_failed);
        assert(i2s->state() == StreamFabricState::faulted);
        assert(mock_live_leases == 2);
        assert(nucode::arduino::i2s_context.dma_leases[0].active);
        assert(nucode::arduino::i2s_context.base_lease.phase ==
               nucode::arduino::internal::IoLeasePhase::committed);
    }
    else if (std::strcmp(argv[1], "pdm_metadata") == 0)
    {
        for (unsigned iteration = 0; iteration < 50; ++iteration)
        {
            startPdm();
            std::thread publisher(
                []
                {
                    assert(pdm->queueBuffer(reinterpret_cast<std::int16_t *>(0x20002100U), 32) ==
                           StreamFabricResult::success);
                });
            std::thread irq_reader(
                []
                {
                    const nrfx_pdm_evt_t event{false, reinterpret_cast<std::int16_t *>(0x20002000U),
                                               0};
                    mock_pdm_event(&nucode::arduino::pdm_drivers[0], event);
                });
            publisher.join();
            irq_reader.join();
            PdmEvent event{};
            assert(pdm->takeEvent(event));
            assert(event.type == PdmEventType::buffer_complete && event.samples == 16);
            assert(pdm->stop(1) == StreamFabricResult::success);
            assert(mock_live_leases == 2);
        }
    }
    else if (std::strcmp(argv[1], "i2s_commit_failure") == 0)
    {
        assert(i2s->stop(1) == StreamFabricResult::success);
        mock_commit_failure = true;
        mock_i2s_stop_ready = false;
        startI2s(StreamFabricResult::release_failed);
        assert(mock_live_leases == 2 && mock_i2s_uninits == 1);
        mock_commit_failure = false;
        mock_i2s_event(&nucode::arduino::i2s_driver, nullptr, NRFX_I2S_STATUS_TRANSFER_STOPPED);
        assert(i2s->stop(1) == StreamFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "pdm_buffer_failure") == 0)
    {
        assert(i2s->stop(1) == StreamFabricResult::success);
        mock_pdm_buffer_error = -EIO;
        mock_pdm_stop_ready = false;
        startPdm(StreamFabricResult::driver_error);
        assert(mock_live_leases == 2 && mock_pdm_uninits == 0);
        mock_pdm_buffer_error = 0;
        mock_pdm_stop_ready = true;
        assert(pdm->stop(1) == StreamFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "pdm_commit_failure") == 0)
    {
        assert(i2s->stop(1) == StreamFabricResult::success);
        mock_commit_failure = true;
        mock_pdm_stop_ready = false;
        startPdm(StreamFabricResult::release_failed);
        assert(mock_live_leases == 2 && mock_pdm_uninits == 0);
        mock_commit_failure = false;
        mock_pdm_stop_ready = true;
        assert(pdm->stop(1) == StreamFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else
    {
        return 2;
    }
    std::cout << "R03_STREAM_PASS=" << argv[1] << '\n';
}
