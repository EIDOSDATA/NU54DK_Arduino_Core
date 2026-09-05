// SPDX-License-Identifier: MIT
/** @brief 양쪽 DAP UART level shifter를 분리해도 SWD로 시험을 제어합니다. */
#include "protocol.h"
#include "serial_hil.h"
#include "fixture_hil.h"
#include "signal_hil.h"
#include <nucode/AnalogFabric.h>
#include <nucode/EventFabric.h>
#include <nucode/SerialFabric.h>
#include <variant.h>
#include <zephyr/kernel.h>

extern "C"
{
    alignas(4) volatile std::uint32_t v04_request[v04::words]{};
    alignas(4) volatile std::uint32_t v04_response[v04::words]{};
    alignas(4) volatile std::uint32_t v04_identity[16]{};
}

namespace
{
    using namespace nucode::arduino;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr char revision[] = NUCODE_HIL_CORE_REVISION;
    static_assert(sizeof(revision) == 41);
    alignas(4) std::uint8_t twi_memory[8]{};
    alignas(4) std::int16_t adc_memory[32]{};
    alignas(4) std::uint16_t pwm20_memory[4]{250U, 0U, 0U, 0U};
    alignas(4) std::uint16_t pwm21_memory[4]{0U, 500U, 0U, 0U};

    /** @brief PMIC 시험은 외부 fixture가 해제된 상태에서 읽기 전용으로 실행합니다. */
    std::uint32_t pmic(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count)
    {
        const auto instance = args[0];
        const auto repeats = args[1];
        if ((instance != 20U && instance != 21U && instance != 22U) || repeats == 0 ||
            repeats > 100 || (args[2] != 100000 && args[2] != 400000))
        {
            return 400;
        }
        auto *handle = serialFabric().twim(instance);
        const SerialSignalPin pins[] = {{SerialSignal::sda, PIN_P1_02},
                                        {SerialSignal::scl, PIN_P1_03}};
        const SerialDmaWorkspace workspace{twi_memory, sizeof(twi_memory)};
        const SerialFabricConfiguration configuration{SerialRouteClass::p1_flexible,
                                                      SerialElectricalProfile::pmic_read_only,
                                                      pins,
                                                      2,
                                                      &workspace,
                                                      1};
        if (handle == nullptr ||
            handle->configure({static_cast<TwiFabricFrequency>(args[2])}) !=
                SerialFabricResult::success ||
            handle->stage(configuration) != SerialFabricResult::success ||
            handle->activate() != SerialFabricResult::success)
        {
            return 501;
        }
        out[0] = 0;
        for (std::uint32_t round = 0; round < repeats; ++round)
        {
            twi_memory[0] = 0x0c;
            twi_memory[1] = 0;
            const auto result = handle->transfer(0x6a, twi_memory, 1, twi_memory + 1, 1, 100000);
            out[3] = static_cast<std::uint32_t>(result);
            if (result != SerialFabricResult::success || twi_memory[1] != 0x41)
            {
                break;
            }
            ++out[0];
            TwiFabricEvent event{};
            while (handle->takeEvent(event))
            {
            }
        }
        out[1] = twi_memory[1];
        out[2] = static_cast<std::uint32_t>(handle->deactivate(100000));
        count = 4;
        return out[0] == repeats && out[2] == 0 ? 0 : 502;
    }

    std::uint32_t timerTest(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count)
    {
        const auto instance = args[0];
        if (instance != 0 && instance != 10 && (instance < 20 || instance > 24))
        {
            return 400;
        }
        auto *timer = eventFabric().timer(instance);
        if (!timer || args[1] >= timer->channelCount() || args[2] < 1000 || args[2] > 10000)
        {
            return 400;
        }
        if (timer->acquire(1000000) != EventFabricResult::success)
        {
            return 510;
        }
        const bool started = timer->clear() == EventFabricResult::success &&
                             timer->start() == EventFabricResult::success;
        if (started)
        {
            k_busy_wait(args[2]);
        }
        out[0] = timer->capture(args[1]);
        out[1] = static_cast<std::uint32_t>(timer->stop());
        out[2] = static_cast<std::uint32_t>(timer->release());
        count = 3;
        return started && out[1] == 0 && out[2] == 0 ? 0 : 511;
    }

    std::uint32_t adcTest(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count)
    {
        /** @brief 이 opcode는 외부 패드를 읽거나 구동하지 않는 입력 allowlist만 사용합니다. */
        if ((args[0] != 0x80 && args[0] != 0x82) || args[1] == 0 || args[1] > 32)
        {
            return 400;
        }
        auto &adc = analogFabric().saadc();
        const SaadcChannelConfiguration channel{static_cast<SaadcInput>(args[0]),
                                                SaadcInput::disabled, SaadcGain::one_quarter};
        if (adc.configure({&channel, 1, 12, 1, 0}) != AnalogFabricResult::success ||
            adc.start(adc_memory, args[1], nullptr, 0) != AnalogFabricResult::success)
        {
            return 520;
        }
        bool ready = false, complete = false, failed = false;
        std::uint32_t sampled = 0;
        const auto deadline = k_uptime_get() + 2000;
        while (!complete && !failed && k_uptime_get() < deadline)
        {
            SaadcEvent event{};
            while (adc.takeEvent(event))
            {
                if (event.type == SaadcEventType::ready)
                {
                    ready = true;
                }
                if (event.type == SaadcEventType::error)
                {
                    failed = true;
                }
                if (event.type == SaadcEventType::buffer_complete)
                {
                    complete = event.buffer == adc_memory && event.samples == args[1];
                    failed |= !complete;
                }
            }
            if (ready && sampled < args[1])
            {
                if (adc.sample() != AnalogFabricResult::success)
                {
                    failed = true;
                }
                else
                {
                    ++sampled;
                }
            }
            if (!complete)
            {
                k_sleep(K_MSEC(1));
            }
        }
        out[0] = sampled;
        out[1] = static_cast<std::uint32_t>(adc.stop(100000));
        out[2] = complete ? 1U : 0U;
        if (out[1] != 0)
        {
            count = 3;
            return 522;
        }
        std::int16_t lowest = adc_memory[0], highest = adc_memory[0];
        for (std::size_t index = 0; index < args[1]; ++index)
        {
            if (adc_memory[index] < lowest)
            {
                lowest = adc_memory[index];
            }
            if (adc_memory[index] > highest)
            {
                highest = adc_memory[index];
            }
        }
        out[3] = static_cast<std::uint32_t>(static_cast<std::int32_t>(lowest));
        out[4] = static_cast<std::uint32_t>(static_cast<std::int32_t>(highest));
        count = 5;
        return complete && !failed && out[1] == 0 ? 0 : 521;
    }

    /** @brief 배선 없이 PWM20·PWM21·SAADC EasyDMA가 동시에 활성화되는지 검사합니다. */
    std::uint32_t concurrentAnalogTest(std::uint32_t *out, std::uint32_t &count)
    {
        auto *const pwm20 = analogFabric().pwm(20U);
        auto *const pwm21 = analogFabric().pwm(21U);
        auto &adc = analogFabric().saadc();
        PwmSequenceConfiguration first{};
        PwmSequenceConfiguration second{};
        first.output_pins[0] = PIN_P1_10;
        second.output_pins[1] = PIN_P1_14;
        first.top_value = second.top_value = 1000U;
        first.load = second.load = PwmSequenceLoad::individual;
        const SaadcChannelConfiguration channel{SaadcInput::vdd, SaadcInput::disabled,
                                                SaadcGain::one_quarter};
        if (pwm20 == nullptr || pwm21 == nullptr ||
            pwm20->configure(first) != AnalogFabricResult::success ||
            pwm21->configure(second) != AnalogFabricResult::success)
        {
            return 530U;
        }
        if (pwm20->play({pwm20_memory, 4U, 0U, 0U}, nullptr, 100U, false) !=
            AnalogFabricResult::success)
        {
            return 530U;
        }
        if (pwm21->play({pwm21_memory, 4U, 0U, 0U}, nullptr, 100U, false) !=
            AnalogFabricResult::success)
        {
            (void)pwm20->stop(100000U);
            return 530U;
        }
        if (adc.configure({&channel, 1U, 12U, 1U, 0U}) != AnalogFabricResult::success ||
            adc.start(adc_memory, 32U, nullptr, 0U) != AnalogFabricResult::success)
        {
            (void)pwm21->stop(100000U);
            (void)pwm20->stop(100000U);
            return 530U;
        }
        const bool simultaneous = pwm20->state() == AnalogFabricState::active &&
                                  pwm21->state() == AnalogFabricState::active &&
                                  adc.state() == AnalogFabricState::active;
        bool adc_ready = false;
        bool adc_complete = false;
        bool pwm20_complete = false;
        bool pwm21_complete = false;
        bool failed = false;
        std::uint32_t sampled = 0U;
        const auto deadline = k_uptime_get() + 2000;
        while ((!adc_complete || !pwm20_complete || !pwm21_complete) && !failed &&
               k_uptime_get() < deadline)
        {
            SaadcEvent adc_event{};
            while (adc.takeEvent(adc_event))
            {
                adc_ready |= adc_event.type == SaadcEventType::ready;
                adc_complete |= adc_event.type == SaadcEventType::buffer_complete &&
                                adc_event.buffer == adc_memory && adc_event.samples == 32U;
                failed |= adc_event.type == SaadcEventType::error;
            }
            PwmSequenceEvent pwm_event{};
            while (pwm20->takeEvent(pwm_event))
            {
                pwm20_complete |= pwm_event.type == PwmSequenceEventType::playback_complete;
                failed |= pwm_event.type == PwmSequenceEventType::error;
            }
            while (pwm21->takeEvent(pwm_event))
            {
                pwm21_complete |= pwm_event.type == PwmSequenceEventType::playback_complete;
                failed |= pwm_event.type == PwmSequenceEventType::error;
            }
            if (adc_ready && sampled < 32U)
            {
                if (adc.sample() != AnalogFabricResult::success)
                {
                    failed = true;
                }
                else
                {
                    ++sampled;
                }
            }
            k_sleep(K_MSEC(1));
        }
        const auto adc_stop = adc.stop(100000U);
        const auto pwm21_stop = pwm21->stop(100000U);
        const auto pwm20_stop = pwm20->stop(100000U);
        out[0] = simultaneous;
        out[1] = sampled;
        out[2] = adc_complete;
        out[3] = pwm20_complete;
        out[4] = pwm21_complete;
        out[5] = static_cast<std::uint32_t>(adc_stop);
        out[6] = static_cast<std::uint32_t>(pwm20_stop);
        out[7] = static_cast<std::uint32_t>(pwm21_stop);
        count = 8U;
        return simultaneous && sampled == 32U && adc_complete && pwm20_complete && pwm21_complete &&
                       !failed && adc_stop == AnalogFabricResult::success &&
                       pwm20_stop == AnalogFabricResult::success &&
                       pwm21_stop == AnalogFabricResult::success
                   ? 0U
                   : 531U;
    }

    std::uint32_t dispatch(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                           std::uint32_t *out, std::uint32_t &count)
    {
        if (opcode == 1 && nargs == 4)
        {
            count = 4;
            for (unsigned index = 0; index < count; ++index)
            {
                out[index] = args[index] ^ (0xa5000000U | role);
            }
            return 0;
        }
        if (opcode >= 16 && opcode <= 28)
        {
            return fixtureCommand(opcode, args, nargs, out, count);
        }
        if (opcode >= 32 && opcode <= 37)
        {
            return signalCommand(opcode, args, nargs, out, count);
        }
        if (fixtureClaimed() || signalClaimed())
        {
            return 403;
        }
        if (opcode == 2 && nargs == 3)
        {
            return pmic(args, out, count);
        }
        if (opcode == 3 && nargs == 3)
        {
            return timerTest(args, out, count);
        }
        if (opcode == 4 && nargs == 2)
        {
            return adcTest(args, out, count);
        }
        if (opcode == 5 && nargs == 0)
        {
            return concurrentAnalogTest(out, count);
        }
        if (opcode >= 9 && opcode <= 13)
        {
            return serialOnboard(opcode, args, nargs, out, count);
        }
        return 400;
    }
} // namespace

int main()
{
    initializeOnboardSerialIdle();
    v04_identity[1] = v04::version;
    v04_identity[2] = role;
    for (unsigned index = 0; index < 10; ++index)
    {
        std::uint32_t word = 0;
        for (unsigned byte = 0; byte < 4; ++byte)
        {
            word |= static_cast<std::uint32_t>(revision[index * 4 + byte]) << (byte * 8);
        }
        v04_identity[4 + index] = word;
    }
    __DMB();
    v04_identity[0] = v04::magic;
    std::uint32_t last_sequence = 0;
    std::uint32_t session_nonce[4]{};
    while (true)
    {
        serviceSerial();
        serviceFixture();
        serviceSignal();
        if (v04_request[0] != v04::magic)
        {
            k_sleep(K_MSEC(1));
            continue;
        }
        __DMB();
        std::uint32_t request[v04::words]{}, response[v04::words]{};
        for (unsigned index = 0; index < v04::words; ++index)
        {
            request[index] = v04_request[index];
        }
        v04_request[0] = 0;
        for (unsigned index = 0; index < 9; ++index)
        {
            response[index] = request[index];
        }
        bool same_nonce = true;
        for (unsigned index = 0; index < 4; ++index)
        {
            same_nonce &= request[5 + index] == session_nonce[index];
        }
        if (!v04::valid(request, role) || request[2] != last_sequence + 1 ||
            (last_sequence != 0 && !same_nonce))
        {
            response[9] = 409;
        }
        else
        {
            for (unsigned index = 0; index < 4; ++index)
            {
                session_nonce[index] = request[5 + index];
            }
            last_sequence = request[2];
            response[9] =
                dispatch(request[4], request + 11, request[10], response + 11, response[10]);
        }
        response[31] = v04::checksum(response);
        v04_response[0] = 0;
        for (unsigned index = 1; index < v04::words; ++index)
        {
            v04_response[index] = response[index];
        }
        __DMB();
        v04_response[0] = v04::magic;
    }
}
