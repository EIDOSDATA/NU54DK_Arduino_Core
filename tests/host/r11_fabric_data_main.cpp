/** @file @brief 실제 Fabric을 별도 링크하여 연속 패턴·buffer 경계·event·재시작을 검증합니다. */
#include <nucode/AnalogFabric.h>
#include <nucode/StreamFabric.h>
#include <nrfx_saadc.h>
#include <nrfx_pwm.h>
#include <nrfx_pdm.h>
#include <nrfx_i2s.h>
#include <nrfx_qdec.h>
#include "fabric_driver_stubs/resource_mock.h"
#include <iostream>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <sys/mman.h>
#endif
using namespace nucode::arduino;

/** @brief production RAM 범위를 그대로 통과하는 이 Host process 전용 메모리를 만듭니다. */
void *mapRam()
{
    void *const requested = reinterpret_cast<void *>(0x20000000U);
#ifdef _WIN32
    void *const actual =
        VirtualAlloc(requested, 0x40000U, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
#else
    void *const actual =
        mmap(requested, 0x40000U, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
#endif
    assert(actual == requested);
    return actual;
}

/** @brief callback이 반환한 주소의 알려진 연속 data를 검증합니다. */
template <typename T> void checkPattern(const T *data, unsigned frame, unsigned count)
{
    for (unsigned index = 0; index < count; ++index)
    {
        assert(data[index] == static_cast<T>(frame * 37U + index * 11U));
    }
}
template <typename T> void fillPattern(T *data, unsigned frame, unsigned count)
{
    for (unsigned index = 0; index < count; ++index)
    {
        data[index] = static_cast<T>(frame * 37U + index * 11U);
    }
}

int main()
{
    void *const ram = mapRam();
    auto *const adc0 = reinterpret_cast<std::int16_t *>(0x20000000U);
    auto *const pdm0 = reinterpret_cast<std::int16_t *>(0x20001000U);
    auto *const rx0 = reinterpret_cast<std::uint32_t *>(0x20002000U);
    auto *const tx0 = reinterpret_cast<std::uint32_t *>(0x20003000U);
    auto *const pwm0 = reinterpret_cast<std::uint16_t *>(0x20004000U);
    auto &adc = analogFabric().saadc();
    auto *const pwm = analogFabric().pwm(20);
    auto *const pdm = streamFabric().pdm(20);
    auto *const i2s = streamFabric().i2s(20);
    auto *const qdec = streamFabric().qdec(21);
    assert(analogFabric().pwm(19) == nullptr && streamFabric().i2s(21) == nullptr);
    assert(streamFabric().pdm(22) == nullptr && streamFabric().qdec(22) == nullptr);
    const SaadcChannelConfiguration channel{SaadcInput::vdd};
    const SaadcConfiguration adc_config{&channel, 1, 12, 1, 0};
    PwmSequenceConfiguration pwm_config{};
    pwm_config.output_pins[0] = 0;
    PdmConfiguration pdm_config{};
    pdm_config.clock_pin = 1;
    pdm_config.data_pin = 2;
    I2sConfiguration i2s_config{};
    i2s_config.sck_pin = 3;
    i2s_config.lrck_pin = 4;
    i2s_config.data_in_pin = 5;
    i2s_config.data_out_pin = 6;
    QdecConfiguration qdec_config{};
    qdec_config.phase_a_pin = 7;
    qdec_config.phase_b_pin = 8;
    for (unsigned restart = 0; restart < 10; ++restart)
    {
        assert(adc.configure(adc_config) == AnalogFabricResult::success);
        assert(pwm->configure(pwm_config) == AnalogFabricResult::success);
        assert(pdm->configure(pdm_config) == StreamFabricResult::success);
        assert(i2s->configure(i2s_config) == StreamFabricResult::success);
        assert(qdec->configure(qdec_config) == StreamFabricResult::success);
        const PwmSequenceBuffer sequences[2]{{pwm0, 16, 2, 3}, {pwm0 + 16, 16, 4, 5}};
        fillPattern(pwm0, restart, 32);
        assert(adc.start(adc0, 16, adc0 + 16, 16) == AnalogFabricResult::success);
        assert(mock_saadc_buffers[0] == adc0 && mock_saadc_buffers[1] == adc0 + 16);
        assert(mock_saadc_sizes[0] == 16 && mock_saadc_sizes[1] == 16);
        assert(pwm->play(sequences[0], &sequences[1], 1, true, false) ==
               AnalogFabricResult::success);
        assert(mock_pwm_sequences[0].values.p_raw == pwm0 &&
               mock_pwm_sequences[1].values.p_raw == pwm0 + 16);
        assert(mock_pwm_sequences[0].repeats == 2 && mock_pwm_sequences[1].end_delay == 5);
        assert(pdm->start(pdm0, 16) == StreamFabricResult::success);
        assert(pdm->queueBuffer(pdm0 + 16, 16) == StreamFabricResult::success);
        assert(mock_pdm_buffer == pdm0 + 16 && mock_pdm_samples == 16);
        assert(i2s->start({rx0, tx0, 16}) == StreamFabricResult::success);
        assert(i2s->queueBuffers({rx0 + 16, tx0 + 16, 16}) == StreamFabricResult::success);
        assert(mock_i2s_buffers.p_rx_buffer == rx0 + 16 && mock_i2s_buffers.buffer_size == 16);
        assert(qdec->start() == StreamFabricResult::success);
        SaadcEvent adc_event{};
        assert(adc.takeEvent(adc_event) && adc_event.type == SaadcEventType::ready);
        mock_i2s_event(mock_i2s_driver, nullptr, NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED);
        I2sEvent i2s_event{};
        assert(i2s->takeEvent(i2s_event) && i2s_event.type == I2sEventType::buffers_needed);
        /** @brief 빈 두 번째 요청은 실제 첫 요청과 구별되는 underrun입니다. */
        mock_i2s_event(mock_i2s_driver, nullptr, NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED);
        assert(i2s->takeEvent(i2s_event) && i2s_event.type == I2sEventType::underrun);
        for (unsigned frame = 0; frame < 100; ++frame)
        {
            const auto offset = (frame % 2U) * 16U;
            auto *const adc_buffer = adc0 + offset;
            auto *const pdm_buffer = pdm0 + offset;
            auto *const rx_buffer = rx0 + offset;
            auto *const tx_buffer = tx0 + offset;
            fillPattern(adc_buffer, frame, 16);
            fillPattern(pdm_buffer, frame, 16);
            fillPattern(rx_buffer, frame, 16);
            fillPattern(tx_buffer, frame, 16);
            const nrfx_saadc_evt_t done{NRFX_SAADC_EVT_DONE, {{adc_buffer, 16}}};
            const auto key = irq_lock();
            mock_saadc_handler(&done);
            irq_unlock(key);
            assert(adc.takeEvent(adc_event) && adc_event.type == SaadcEventType::buffer_complete);
            assert(adc_event.buffer == adc_buffer && adc_event.samples == 16);
            checkPattern(adc_event.buffer, frame, 16);
            assert(adc.queueBuffer(adc_buffer, 16) == AnalogFabricResult::success);
            mock_pdm_event(mock_pdm_drivers[0], {false, pdm_buffer, 0});
            PdmEvent pdm_event{};
            assert(pdm->takeEvent(pdm_event) && pdm_event.type == PdmEventType::buffer_complete);
            assert(pdm_event.buffer == pdm_buffer && pdm_event.samples == 16);
            checkPattern(pdm_event.buffer, frame, 16);
            assert(pdm->queueBuffer(pdm_buffer, 16) == StreamFabricResult::success);
            const nrfx_i2s_buffers_t released{rx_buffer, tx_buffer, 16};
            mock_i2s_event(mock_i2s_driver, &released, NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED);
            assert(i2s->takeEvent(i2s_event) && i2s_event.type == I2sEventType::buffers_complete);
            assert(i2s_event.released.receive == rx_buffer &&
                   i2s_event.released.transmit == tx_buffer && i2s_event.released.words == 16);
            checkPattern(i2s_event.released.receive, frame, 16);
            checkPattern(i2s_event.released.transmit, frame, 16);
            assert(i2s->takeEvent(i2s_event) && i2s_event.type == I2sEventType::buffers_needed);
            assert(i2s->queueBuffers({rx_buffer, tx_buffer, 16}) == StreamFabricResult::success);
            mock_pwm_event(mock_pwm_drivers[0],
                           frame % 2 ? NRFX_PWM_EVENT_END_SEQ1 : NRFX_PWM_EVENT_END_SEQ0);
            PwmSequenceEvent pwm_event{};
            assert(pwm->takeEvent(pwm_event));
            assert(pwm_event.type == (frame % 2 ? PwmSequenceEventType::sequence1_complete
                                                : PwmSequenceEventType::sequence0_complete));
            checkPattern(pwm0, restart, 32);
            nrfx_qdec_event_t report{NRF_QDEC_EVENT_REPORTRDY, {}};
            report.data.report.acc = -static_cast<int>(frame);
            report.data.report.accdbl = frame % 3;
            mock_qdec_handler(report, mock_qdec_context);
            QdecEvent qdec_event{};
            assert(qdec->takeEvent(qdec_event) && qdec_event.type == QdecEventType::report);
            assert(qdec_event.accumulated == -static_cast<int>(frame) &&
                   qdec_event.double_transitions == frame % 3);
        }
        /** @brief driver overflow는 완료 data와 별도의 event로 보존됩니다. */
        mock_pdm_event(mock_pdm_drivers[0], {false, nullptr, NRFX_PDM_ERROR_OVERFLOW});
        PdmEvent overflow{};
        assert(pdm->takeEvent(overflow) && overflow.type == PdmEventType::overflow &&
               overflow.driver_error == -EOVERFLOW);
        mock_qdec_handler({NRF_QDEC_EVENT_ACCOF, {}}, mock_qdec_context);
        QdecEvent qdec_error{};
        assert(qdec->takeEvent(qdec_error) && qdec_error.driver_error == -EOVERFLOW);
        /** @brief RAM 끝을 넘거나 단위 정렬을 어긴 제출은 driver에 넘기지 않습니다. */
        assert(adc.queueBuffer(reinterpret_cast<std::int16_t *>(0x2003FFFEU), 2) ==
               AnalogFabricResult::invalid_argument);
        assert(pdm->queueBuffer(pdm0, 0) == StreamFabricResult::invalid_argument);
        assert(i2s->queueBuffers({reinterpret_cast<std::uint32_t *>(0x2003FFFCU), nullptr, 2}) ==
               StreamFabricResult::invalid_argument);
        assert(adc.stop(21) == AnalogFabricResult::success);
        assert(pwm->stop(21) == AnalogFabricResult::success);
        assert(pdm->stop(21) == StreamFabricResult::success);
        assert(i2s->stop(21) == StreamFabricResult::success);
        assert(qdec->stop() == StreamFabricResult::success);
        assert(mock_live_leases == 0);
    }
#ifdef _WIN32
    assert(VirtualFree(ram, 0, MEM_RELEASE));
#else
    assert(munmap(ram, 0x40000U) == 0);
#endif
    std::cout << "R11_DATA_PASS=5;RESTARTS=10;FRAMES=1000\n";
}
