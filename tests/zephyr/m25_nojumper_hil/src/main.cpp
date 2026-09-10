/**
 * @file
 * @brief SWD 명령으로 무점퍼 PWM의 준비 취소·시작·정지·자원 반환을 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#include <nucode/AnalogFabric.h>
#include <nucode/EventFabric.h>
#include <internal/IoResourceManager.h>
#include <internal/pin_description.h>
#include <hal/nrf_pwm.h>
#include <variant.h>
#include <zephyr/kernel.h>
#include <cstdint>

extern "C"
{
    /** @brief exact ELF에서 찾는 mailbox입니다. request/response의 sequence는 마지막에 게시합니다. */
    volatile std::uint32_t nojumper_request[8]{};
    volatile std::uint32_t nojumper_response[32]{};
    volatile std::uint32_t nojumper_ready[4]{};
    alignas(4) volatile char nojumper_revision[41] = NUCODE_HIL_CORE_REVISION;
}

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    constexpr std::uint32_t magic = 0x4E4A5031U;
    constexpr std::uint32_t guard = 0xD65A91C3U;
    struct GuardedSequence
    {
        std::uint32_t before[4];
        std::uint16_t values[8];
        std::uint32_t after[4];
    };
    alignas(4) GuardedSequence sequences[2]{};

    /** @brief 초기화 시점만 buffer를 쓰며 DMA 구간에서는 guard와 원본을 변경하지 않습니다. */
    void prepareSequences(std::uint32_t top)
    {
        for (auto &sequence : sequences)
        {
            for (unsigned index = 0U; index < 4U; ++index)
            {
                sequence.before[index] = guard;
                sequence.after[index] = guard;
            }
            for (unsigned index = 0U; index < 8U; ++index)
            {
                sequence.values[index] =
                    static_cast<std::uint16_t>(index % 4U == 3U ? top : (0x8000U | (top / 2U)));
            }
        }
    }

    bool guardsValid()
    {
        for (const auto &sequence : sequences)
        {
            for (unsigned index = 0U; index < 4U; ++index)
            {
                if (sequence.before[index] != guard || sequence.after[index] != guard)
                {
                    return false;
                }
            }
        }
        return true;
    }

    bool resourceFree(const IoResourceId &id)
    {
        IoResourceSnapshot snapshot{};
        return ioResourceSnapshot(id, snapshot) == IoResourceResult::success &&
               snapshot.state == IoResourceState::free;
    }

    /** @brief P1.14 한 출력만 사용하며 보드 간 신호·DAP UART·공유 ADC 핀을 구동하지 않습니다. */
    void exercisePwm(const std::uint32_t *request, std::uint32_t *result)
    {
        const auto instance = static_cast<std::uint8_t>(request[3]);
        const auto flags = request[4];
        const auto load = request[5];
        const auto top = request[6];
        const auto repetitions = request[7];
        if (request[3] < 20U || request[3] > 22U || flags > 63U || load > 3U ||
            (top != 1000U && top != 4000U) || repetitions == 0U || repetitions > 100U ||
            ((flags & 32U) != 0U && (flags & 1U) == 0U))
        {
            result[2] = 1U;
            return;
        }
        NRF_PWM_Type *const registers = instance == 20U   ? NRF_PWM20
                                        : instance == 21U ? NRF_PWM21
                                                          : NRF_PWM22;
        auto *const pwm = analogFabric().pwm(instance);
        auto *const egu = eventFabric().egu(20U);
        auto *const dppi = eventFabric().dppi(20U);
        const auto gpio = pinDescription(PIN_P1_14)->gpio;
        const std::uint32_t pin_before = NRF_P1->PIN_CNF[14];
        const bool out_before = (NRF_P1->OUT & (1UL << 14U)) != 0U;
        prepareSequences(top);
        const PwmSequenceBuffer first{sequences[0].values, 8U, 0U, 0U};
        const PwmSequenceBuffer second{sequences[1].values, 8U, 0U, 0U};
        for (std::uint32_t run = 0U; run < repetitions; ++run)
        {
            PwmSequenceConfiguration configuration{};
            configuration.output_pins[0] = PIN_P1_14;
            configuration.load = static_cast<PwmSequenceLoad>(load);
            configuration.top_value = static_cast<std::uint16_t>(top);
            configuration.triggered_step = (flags & 8U) != 0U;
            result[8] = static_cast<std::uint32_t>(pwm->configure(configuration));
            if (result[8] != 0U)
            {
                result[2] = 2U;
                break;
            }
            registers->EVENTS_PWMPERIODEND = 0U;
            result[9] =
                static_cast<std::uint32_t>(pwm->play(first, (flags & 4U) != 0U ? &second : nullptr,
                                                     1U, (flags & 16U) != 0U, (flags & 1U) != 0U));
            if (result[9] != 0U)
            {
                result[2] = 3U;
                break;
            }
            bool dppi_acquired = false;
            bool egu_acquired = false;
            bool event_ok = true;
            if ((flags & 32U) != 0U)
            {
                egu_acquired = egu->acquire(0U) == EventFabricResult::success;
                dppi_acquired = dppi->acquireChannel(0U) == EventFabricResult::success;
                event_ok = egu_acquired && dppi_acquired;
                const EventEndpoint subscriber{pwm->startTaskAddress(), 20U,
                                               EventEndpointRole::subscriber};
                event_ok =
                    event_ok &&
                    dppi->connect(egu->event(0U), subscriber, 0U) == EventFabricResult::success &&
                    dppi->enable(0U) == EventFabricResult::success;
                if (event_ok)
                {
                    result[22] = static_cast<std::uint32_t>(pwm->stop(1000U));
                    event_ok = result[22] ==
                               static_cast<std::uint32_t>(AnalogFabricResult::ownership_conflict);
                }
                if (event_ok && (flags & 2U) != 0U)
                {
                    event_ok = egu->trigger(0U) == EventFabricResult::success;
                }
                k_busy_wait(2000U);
                if (dppi_acquired)
                {
                    event_ok &= dppi->releaseChannel(0U) == EventFabricResult::success;
                }
                if (egu_acquired)
                {
                    event_ok &= egu->release(0U) == EventFabricResult::success;
                }
            }
            else if ((flags & 3U) == 3U)
            {
                *reinterpret_cast<volatile std::uint32_t *>(pwm->startTaskAddress()) = 1U;
            }
            k_busy_wait(2000U);
            if (configuration.triggered_step && ((flags & 1U) == 0U || (flags & 2U) != 0U))
            {
                event_ok &= pwm->step() == AnalogFabricResult::success;
            }
            result[12] = registers->EVENTS_DMA.SEQ[0].READY;
            result[13] = registers->EVENTS_DMA.SEQ[1].READY;
            result[14] = registers->EVENTS_SEQSTARTED[0];
            result[15] = registers->EVENTS_SEQSTARTED[1];
            result[16] = registers->EVENTS_PWMPERIODEND;
            const auto start = k_cycle_get_32();
            result[10] = static_cast<std::uint32_t>(pwm->stop(100000U));
            result[23] = k_cyc_to_us_floor32(k_cycle_get_32() - start);
            result[11] = static_cast<std::uint32_t>(pwm->state());
            result[17] = registers->ENABLE;
            result[19] = guardsValid() ? 1U : 0U;
            result[20] = resourceFree(peripheralIoResource(IoResourceKind::pwm_block, instance)) &&
                         resourceFree(gpioIoResource(gpio)) &&
                         resourceFree(dmaMemoryIoResource(first.values, 16U)) &&
                         resourceFree(dmaMemoryIoResource(second.values, 16U));
            const bool expected_start = (flags & 1U) == 0U || (flags & 2U) != 0U;
            const bool observed_start =
                (result[12] | result[13]) != 0U && (result[14] | result[15]) != 0U;
            if (!event_ok || result[10] != 0U || result[17] != 0U || result[19] != 1U ||
                result[20] != 1U || expected_start != observed_start ||
                (!expected_start && result[16] != 0U))
            {
                result[2] = 4U;
                break;
            }
            ++result[21];
        }
        if (resourceFree(gpioIoResource(gpio)) && registers->ENABLE == 0U)
        {
            if (out_before)
            {
                NRF_P1->OUTSET = 1UL << 14U;
            }
            else
            {
                NRF_P1->OUTCLR = 1UL << 14U;
            }
            NRF_P1->PIN_CNF[14] = pin_before;
        }
        result[18] = NRF_P1->PIN_CNF[14];
        result[24] = pin_before;
        if (result[18] != pin_before)
        {
            result[2] = 5U;
        }
    }
} // namespace

#include "nojumper_ownership.h"
#include "nojumper_adc.h"
#include "nojumper_timer.h"
#include "nojumper_event.h"
#include "nojumper_time.h"

int main()
{
    nojumper_ready[1] = nojumper_revision[0] != '\0' ? 2U : 0U;
    nojumper_ready[0] = magic;
    std::uint32_t previous = 0U;
    while (true)
    {
        const auto sequence = nojumper_request[0];
        if (sequence != 0U && sequence != previous && nojumper_ready[3] == 0U)
        {
            std::uint32_t request[8]{};
            std::uint32_t result[32]{};
            nrf_barrier_rw();
            for (unsigned index = 0U; index < 8U; ++index)
            {
                request[index] = nojumper_request[index];
                result[index] = request[index];
            }
            result[2] = 0U;
            if (request[0] != sequence || request[1] == 0U || (request[2] < 1U || request[2] > 6U))
            {
                result[2] = 1U;
            }
            else
            {
                switch (request[2])
                {
                case 1U:
                    exercisePwm(request, result);
                    break;
                case 2U:
                    exerciseSaadc(request, result);
                    break;
                case 3U:
                    exerciseTimer(request, result);
                    break;
                case 4U:
                    exerciseEvent(request, result);
                    break;
                case 5U:
                    exerciseBridge(request, result);
                    break;
                case 6U:
                    exerciseTime(request, result);
                    break;
                default:
                    result[2] = 1U;
                    break;
                }
            }
            for (unsigned index = 1U; index < 32U; ++index)
            {
                nojumper_response[index] = result[index];
            }
            nrf_barrier_rw();
            nojumper_response[0] = sequence;
            previous = sequence;
            ++nojumper_ready[2];
            nojumper_ready[3] = result[2];
        }
        k_sleep(K_MSEC(1));
    }
}
