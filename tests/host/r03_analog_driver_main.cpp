/** @file @brief production AnalogFabric의 STOP·overflow와 다른 block 진행을 검증합니다. */
#include "../../cores/arduino/AnalogFabric.cpp"
#include "fabric_driver_stubs/resource_mock.h"
#include <condition_variable>
#include <cstring>
#include <iostream>
using namespace nucode::arduino;
auto *pwm = analogFabric().pwm(20);
auto *other = analogFabric().pwm(21);
auto &saadc = analogFabric().saadc();
auto *samples = reinterpret_cast<std::int16_t *>(0x20000000U);
const PwmSequenceBuffer sequence{reinterpret_cast<std::uint16_t *>(0x20001000U), 4U, 0U, 0U};
void startPwm(PwmSequenceFabric *handle, unsigned pin,
              AnalogFabricResult expected = AnalogFabricResult::success)
{
    PwmSequenceConfiguration configuration{};
    configuration.output_pins[0] = pin;
    configuration.triggered_step = true;
    assert(handle->configure(configuration) == AnalogFabricResult::success);
    assert(handle->play(sequence, nullptr, 1, true, false) == expected);
}
void startSaadc(AnalogFabricResult expected = AnalogFabricResult::success)
{
    const SaadcChannelConfiguration channel{SaadcInput::vdd};
    const SaadcConfiguration config{&channel, 1, 12, 1, 0};
    assert(saadc.configure(config) == AnalogFabricResult::success);
    assert(saadc.start(samples, 16, nullptr, 0) == expected);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    (void)nucode::arduino::connectAnalogFabricIrqs();
    startPwm(pwm, 0);
    if (std::strcmp(argv[1], "pwm_timeout") == 0)
    {
        mock_pwm_stop_ready = false;
        const int leases = mock_live_leases;
        assert(pwm->stop(21) == AnalogFabricResult::stop_timeout);
        assert(mock_live_leases == leases);
        assert(mock_pwm_uninits == 0);
        assert(pwm->play(sequence, nullptr, 1, true, false) == AnalogFabricResult::wrong_state);
        mock_pwm_stop_ready = true;
        assert(pwm->stop(21) == AnalogFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "other_progress") == 0)
    {
        startPwm(other, 1);
        mock_pwm_stop_ready = false;
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
                assert(other->step() == AnalogFabricResult::success);
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
            mock_pwm_event(&nucode::arduino::pwm_drivers[0], NRFX_PWM_EVENT_STOPPED);
        };
        assert(pwm->stop(20) == AnalogFabricResult::success);
        worker.join();
        assert(mock_pwm_steps == 1);
    }
    else if (std::strcmp(argv[1], "overflow") == 0)
    {
        for (unsigned i = 0; i < 10; ++i)
        {
            mock_pwm_event(&nucode::arduino::pwm_drivers[0], NRFX_PWM_EVENT_END_SEQ0);
        }
        assert(pwm->step() == AnalogFabricResult::success);
        bool overflow = false;
        PwmSequenceEvent event{};
        while (pwm->takeEvent(event))
        {
            overflow |= event.driver_error == -ENOBUFS;
        }
        assert(overflow);
    }
    else if (std::strcmp(argv[1], "deadline") == 0)
    {
        mock_pwm_stop_ready = false;
        mock_wait = [](std::uint32_t)
        {
            mock_pwm_event(&nucode::arduino::pwm_drivers[0], NRFX_PWM_EVENT_STOPPED);
        };
        assert(pwm->stop(1) == AnalogFabricResult::success);
        assert(waited_us == 1);
        startPwm(pwm, 0);
        assert(pwm->stop(UINT32_MAX) == AnalogFabricResult::success);
    }
    else if (std::strcmp(argv[1], "saadc_timeout") == 0)
    {
        startSaadc();
        const int leases = mock_live_leases;
        mock_saadc_stop_ready = false;
        assert(saadc.stop(21) == AnalogFabricResult::stop_timeout);
        assert(mock_live_leases == leases);
        assert(mock_saadc_uninits == 0);
        assert(waited_us == 21);
        mock_saadc_event(NRFX_SAADC_EVT_FINISHED);
        assert(saadc.stop(1) == AnalogFabricResult::success);
    }
    else if (std::strcmp(argv[1], "repeat") == 0)
    {
        for (unsigned i = 0; i < 20; ++i)
        {
            assert(pwm->stop(20) == AnalogFabricResult::success);
            assert(mock_live_leases == 0);
            startSaadc();
            assert(saadc.stop(20) == AnalogFabricResult::success);
            assert(mock_live_leases == 0);
            if (i != 19)
            {
                startPwm(pwm, 0);
            }
        }
    }
    else if (std::strcmp(argv[1], "snapshot") == 0)
    {
        std::atomic<bool> done{false};
        std::atomic<unsigned> writes{0};
        std::thread irq_writer(
            [&]
            {
                for (unsigned i = 0; i < 20000; ++i)
                {
                    mock_pwm_event(&nucode::arduino::pwm_drivers[0], NRFX_PWM_EVENT_END_SEQ0);
                    ++writes;
                }
                done = true;
            });
        do
        {
            assert(pwm->step() == AnalogFabricResult::success);
            const auto snapshot = nucode::arduino::pwm_contexts[0].diagnostics.snapshot();
            assert((snapshot.result == AnalogFabricResult::success && snapshot.driver_error == 0) ||
                   (snapshot.result == AnalogFabricResult::resource_exhausted &&
                    snapshot.driver_error == -ENOBUFS));
        } while (!done);
        irq_writer.join();
        assert(writes == 20000);
    }
    else if (std::strcmp(argv[1], "release_failure") == 0)
    {
        const int leases = mock_live_leases;
        mock_release_failure = true;
        assert(pwm->stop(20) == AnalogFabricResult::release_failed);
        assert(pwm->state() == AnalogFabricState::faulted);
        assert(mock_live_leases == leases);
        assert(nucode::arduino::pwm_contexts[0].lease.phase ==
               nucode::arduino::internal::IoLeasePhase::committed);
        PwmSequenceConfiguration config{};
        config.output_pins[0] = 0;
        assert(pwm->configure(config) == AnalogFabricResult::wrong_state);
    }
    else if (std::strcmp(argv[1], "stop_queue_full") == 0)
    {
        for (unsigned i = 0; i < 10; ++i)
        {
            mock_pwm_event(&nucode::arduino::pwm_drivers[0], NRFX_PWM_EVENT_END_SEQ0);
        }
        assert(pwm->stop(1) == AnalogFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "pwm_commit_failure") == 0)
    {
        assert(pwm->stop(1) == AnalogFabricResult::success);
        mock_commit_failure = true;
        mock_pwm_stop_ready = false;
        startPwm(pwm, 0, AnalogFabricResult::release_failed);
        assert(mock_live_leases == 1 && mock_pwm_uninits == 1);
        mock_commit_failure = false;
        mock_pwm_stop_ready = true;
        assert(pwm->stop(1) == AnalogFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "saadc_queue_commit_failure") == 0)
    {
        assert(pwm->stop(1) == AnalogFabricResult::success);
        startSaadc();
        mock_commit_failure = true;
        mock_saadc_stop_ready = false;
        assert(saadc.queueBuffer(reinterpret_cast<std::int16_t *>(0x20003000U), 16) ==
               AnalogFabricResult::release_failed);
        assert(mock_live_leases == 2 && mock_saadc_uninits == 0);
        mock_commit_failure = false;
        mock_saadc_stop_ready = true;
        assert(saadc.stop(1) == AnalogFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else if (std::strcmp(argv[1], "saadc_commit_failure") == 0)
    {
        assert(pwm->stop(1) == AnalogFabricResult::success);
        mock_commit_failure = true;
        mock_saadc_stop_ready = false;
        startSaadc(AnalogFabricResult::release_failed);
        assert(mock_live_leases == 1 && mock_saadc_uninits == 0);
        mock_commit_failure = false;
        mock_saadc_stop_ready = true;
        assert(saadc.stop(1) == AnalogFabricResult::success);
        assert(mock_live_leases == 0);
    }
    else
    {
        return 2;
    }
    std::cout << "R03_ANALOG_PASS=" << argv[1] << '\n';
}
