/** @file @brief 지연 시작 PWM의 무출력 취소·DMA 시작 경계·lease 보존을 검증합니다. */
#include "../../cores/arduino/AnalogFabric.cpp"
#include "../../cores/arduino/internal/analog/SaadcFabric.cpp"
#include "../../cores/arduino/internal/analog/PwmSequenceFabric.cpp"
#include "fabric_driver_stubs/resource_mock.h"
#include <cstring>
#include <iostream>

using namespace nucode::arduino;
const PwmSequenceBuffer first{reinterpret_cast<std::uint16_t *>(0x20001000U), 4U, 0U, 0U};
const PwmSequenceBuffer second{reinterpret_cast<std::uint16_t *>(0x20002000U), 4U, 0U, 0U};

int main(int argc, char **argv)
{
    assert(argc == 2);
    auto *const pwm = analogFabric().pwm(20U);
    auto *const reg = NRF_PWM20;
    PwmSequenceConfiguration configuration{};
    configuration.output_pins[0] = 0U;
    configuration.triggered_step = true;
    assert(pwm->configure(configuration) == AnalogFabricResult::success);
    const bool complex = std::strcmp(argv[1], "complex") == 0;
    const bool commit_failure = std::strcmp(argv[1], "commit_failure") == 0;
    mock_commit_failure = commit_failure;
    assert(pwm->play(first, complex ? &second : nullptr, 1U, true, true) ==
           (commit_failure ? AnalogFabricResult::release_failed : AnalogFabricResult::success));
    assert(mock_live_leases == 1 && mock_pwm_starts == 0U);
    mock_commit_failure = false;

    if (std::strcmp(argv[1], "started_timeout") == 0 || std::strcmp(argv[1], "dma_pending") == 0)
    {
        reg->EVENTS_DMA.SEQ[0].READY = 1U;
        if (std::strcmp(argv[1], "started_timeout") == 0)
        {
            mock_pwm_start(reg, 0U);
        }
        mock_pwm_stop_ready = false;
        assert(pwm->stop(1U) == AnalogFabricResult::stop_timeout);
        assert(mock_live_leases == 1 && mock_pwm_uninits == 0U && reg->enabled);
        mock_pwm_start(reg, 0U);
        mock_pwm_stop_ready = true;
        assert(pwm->stop(20U) == AnalogFabricResult::success);
    }
    else if (std::strcmp(argv[1], "disable_race") == 0)
    {
        mock_pwm_on_disable = [](NRF_PWM_Type *registers)
        {
            mock_pwm_start(registers, 0U);
        };
        mock_pwm_stop_ready = false;
        assert(pwm->stop(1U) == AnalogFabricResult::stop_timeout);
        assert(mock_live_leases == 1 && mock_pwm_uninits == 0U);
        mock_pwm_on_disable = nullptr;
        mock_pwm_stop_ready = true;
        assert(pwm->stop(20U) == AnalogFabricResult::success);
    }
    else if (std::strcmp(argv[1], "subscribed") == 0)
    {
        reg->SUBSCRIBE_DMA.SEQ[1].START = PWM_SUBSCRIBE_DMA_SEQ_START_EN_Msk;
        assert(pwm->stop(20U) == AnalogFabricResult::ownership_conflict);
        assert(pwm->state() == AnalogFabricState::active);
        assert(mock_live_leases == 1 && reg->enabled);
        reg->SUBSCRIBE_DMA.SEQ[1].START = 0U;
        assert(pwm->stop(20U) == AnalogFabricResult::success);
    }
    else
    {
        assert(pwm->stop(20U) == AnalogFabricResult::success);
        assert(mock_pwm_starts == 0U && mock_pwm_stop_events == 0U);
        if (std::strcmp(argv[1], "repeat") == 0)
        {
            for (unsigned index = 0U; index < 100U; ++index)
            {
                assert(pwm->play(first) == AnalogFabricResult::success);
                assert(pwm->stop(20U) == AnalogFabricResult::success);
                assert(pwm->play(first, &second, 2U, false, true) == AnalogFabricResult::success);
                const auto starts = mock_pwm_starts;
                assert(pwm->stop(20U) == AnalogFabricResult::success);
                assert(mock_pwm_starts == starts);
            }
        }
    }
    assert(mock_live_leases == 0 && !reg->enabled);
    assert(pwm->state() == AnalogFabricState::configured);
    assert(pwm->startTaskAddress() == 0U);
    assert(pwm->play(first) == AnalogFabricResult::success);
    assert(pwm->stop(20U) == AnalogFabricResult::success);
    assert(mock_live_leases == 0);
    std::cout << "PWM_DEFERRED_PASS=" << argv[1] << '\n';
}
