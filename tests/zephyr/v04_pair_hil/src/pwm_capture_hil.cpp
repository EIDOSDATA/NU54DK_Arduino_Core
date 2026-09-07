/**
 * @file pwm_capture_hil.cpp
 * @brief B P1.14 PWM의 일정 duty와 유한/triggered sequence를 A TIMER로 측정합니다.
 * @note 기존 408 일정 duty와 공통 508 모드 검증의 원본·명령을 구분합니다.
 * SPDX-License-Identifier: MIT
 */
#include "pwm_capture_hil.h"
#include "pwm_capture_vector.h"
#include "fixture_gate.h"
#include "fixture_hil.h"
#include "signal_hil.h"
#include <nucode/AnalogFabric.h>
#include <nucode/EventFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_timer.h>
#include <zephyr/kernel.h>

namespace
{
    using namespace nucode::arduino;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr std::uint32_t pin = NRF_GPIO_PIN_MAP(1, 14);
    constexpr std::uint32_t edge_capacity = 513U;
    constexpr std::uint32_t guard_word = 0xA55A9669U;
    v04::FixtureGate gate;
    PwmSequenceFabric *pwm = nullptr;
    TimerFabric *timer = nullptr;
    GpioteFabric *gpiote = nullptr;
    DppiFabric *dppi = nullptr;
    bool timer_owned = false, pin_owned = false, channel_owned = false, connected = false;
    bool prepared = false, started = false, complete = false;
    std::uint32_t error = 0U, edge_count = 0U, initial_level = 0U, final_level = 0U;
    std::uint32_t elapsed = 0U, sequence0 = 0U, sequence1 = 0U, playbacks = 0U;
    std::uint32_t top = 0U, duty = 0U;
    std::uint32_t value_count = 4U;
    bool advanced = false, triggered = false, asynchronous = false;
    bool egu_owned = false, start_channel_owned = false, start_connected = false;
    bool use_dppi_start = false;
    EguFabric *egu = nullptr;
    DppiFabric *start_dppi = nullptr;
    EventEndpoint start_endpoint{};
    std::uint32_t repeats = 0U, end_delay = 0U, playback_count = 0U;
    std::uint32_t capture_origin = 0U, capture_duration = 0U, event_order_errors = 0U;
    std::uint32_t step_count = 0U;
    /** @brief 작은 sequence의 요청 길이 이후 값도 canary로 검증합니다. */
    struct alignas(4) AdvancedDma
    {
        std::uint32_t before[4];
        std::uint16_t values[16];
        std::uint32_t after[4];
    } advanced_dma[2]{};
    /** @brief 최대 DMA 전후 16-byte guard이며 물리 출력 pin은 선택 slot 한 개에만 연결합니다. */
    struct alignas(4) Dma
    {
        std::uint32_t before[4];
        std::uint16_t values[256];
        std::uint32_t after[4];
    } dma{};
    std::uint32_t edges[edge_capacity][2]{};

    /** @brief DMA가 요청 범위를 벗어났는지 검사합니다. */
    bool guards()
    {
        for (unsigned index = 0U; index < 4U; ++index)
        {
            if (dma.before[index] != guard_word || dma.after[index] != guard_word)
            {
                return false;
            }
        }
        if (advanced)
        {
            for (const auto &buffer : advanced_dma)
            {
                for (unsigned index = 0U; index < 4U; ++index)
                {
                    if (buffer.before[index] != guard_word || buffer.after[index] != guard_word)
                    {
                        return false;
                    }
                }
                for (unsigned index = triggered ? 16U : 8U; index < 16U; ++index)
                {
                    if (buffer.values[index] != 0x9669U)
                    {
                        return false;
                    }
                }
            }
        }
        return true;
    }

    /** @brief 연결을 먼저 해제하고 STOP을 증명한 자원만 반환합니다. */
    bool stop()
    {
        if (pwm != nullptr && pwm->state() == AnalogFabricState::faulted)
        {
            return false;
        }
        if (start_channel_owned)
        {
            if (start_dppi == nullptr || start_dppi->disable(1U) != EventFabricResult::success)
            {
                return false;
            }
            if (start_connected)
            {
                if (egu == nullptr || start_dppi->disconnect(egu->event(0U), start_endpoint, 1U) !=
                                          EventFabricResult::success)
                {
                    return false;
                }
                start_connected = false;
            }
            if (start_dppi->releaseChannel(1U) != EventFabricResult::success)
            {
                return false;
            }
            start_channel_owned = false;
        }
        if (egu_owned)
        {
            if (egu == nullptr || egu->release(0U) != EventFabricResult::success)
            {
                return false;
            }
            egu_owned = false;
        }
        if (pwm != nullptr && (pwm->state() == AnalogFabricState::active ||
                               pwm->state() == AnalogFabricState::stopping))
        {
            if (pwm->stop(100000U) != AnalogFabricResult::success)
            {
                return false;
            }
        }
        if (channel_owned)
        {
            if (dppi == nullptr)
            {
                return false;
            }
            if (dppi->disable(0U) != EventFabricResult::success)
            {
                return false;
            }
            if (connected)
            {
                if (gpiote == nullptr || timer == nullptr)
                {
                    return false;
                }
                if (dppi->disconnect(gpiote->inEvent(0U), timer->task(TimerTask::capture, 0U),
                                     0U) != EventFabricResult::success)
                {
                    return false;
                }
                connected = false;
            }
            if (dppi->releaseChannel(0U) != EventFabricResult::success)
            {
                return false;
            }
            channel_owned = false;
        }
        if (pin_owned)
        {
            if (gpiote == nullptr || gpiote->release(0U) != EventFabricResult::success)
            {
                return false;
            }
            pin_owned = false;
        }
        if (timer_owned)
        {
            if (timer == nullptr || timer->stop() != EventFabricResult::success ||
                timer->release() != EventFabricResult::success)
            {
                return false;
            }
            timer_owned = false;
        }
        prepared = started = asynchronous = false;
        pwm = nullptr;
        return true;
    }

    /** @brief 기존 다섯 필드 또는 load/value 수를 포함한 일곱 필드만 허용합니다. */
    bool prepare(const std::uint32_t *args, std::uint32_t nargs)
    {
        const v04::PwmCaptureVector vector{args[0],
                                           args[1],
                                           args[2],
                                           args[3],
                                           args[4],
                                           nargs == 7U ? args[5] : 2U,
                                           nargs == 7U ? args[6] : 4U};
        if (prepared || timer_owned || pin_owned || channel_owned || pwm != nullptr ||
            !vector.valid())
        {
            return false;
        }
        top = args[2];
        duty = args[3];
        value_count = vector.values;
        error = edge_count = elapsed = sequence0 = sequence1 = playbacks = 0U;
        complete = false;
        advanced = triggered = asynchronous = false;
        event_order_errors = step_count = 0U;
        for (unsigned index = 0U; index < 4U; ++index)
        {
            dma.before[index] = dma.after[index] = guard_word;
        }
        if (!v04::fillPwmCaptureValues(vector, dma.values, 256U))
        {
            return false;
        }
        if (role == 2U)
        {
            PwmSequenceConfiguration configuration{};
            configuration.output_pins[args[1]] = PIN_P1_14;
            configuration.top_value = vector.registerTop();
            configuration.load = static_cast<PwmSequenceLoad>(vector.load);
            pwm = analogFabric().pwm(static_cast<std::uint8_t>(args[0]));
            prepared =
                pwm != nullptr && pwm->configure(configuration) == AnalogFabricResult::success;
        }
        else
        {
            timer = eventFabric().timer(22U);
            gpiote = eventFabric().gpiote(20U);
            dppi = eventFabric().dppi(20U);
            if (timer == nullptr || gpiote == nullptr || dppi == nullptr)
            {
                return false;
            }
            timer_owned = timer->acquire(1000000U) == EventFabricResult::success;
            if (!timer_owned)
            {
                return false;
            }
            pin_owned = gpiote->acquireInput(0U, PIN_P1_14, GpiotePolarity::toggle) ==
                        EventFabricResult::success;
            if (!pin_owned)
            {
                return false;
            }
            channel_owned = dppi->acquireChannel(0U) == EventFabricResult::success;
            if (!channel_owned)
            {
                return false;
            }
            connected = dppi->connect(gpiote->inEvent(0U), timer->task(TimerTask::capture, 0U),
                                      0U) == EventFabricResult::success;
            prepared = connected;
        }
        return prepared;
    }

    /**
     * @brief 이미 출력 중인 peer의 에지 201개 또는 정적 100주기 구간을 읽습니다.
     * @note 시각은 DPPI가 CC0에 기록합니다. CPU는 CC0를 덮어쓰지 않으며 IRQ를 마스킹하지 않습니다.
     * 누락 에지·늦은 level 관측은 raw 간격·교대 level의 Host 판정으로 실패 처리합니다.
     */
    bool capture()
    {
        if (role != 1U || !prepared || started)
        {
            return false;
        }
        auto *const event = reinterpret_cast<volatile std::uint32_t *>(gpiote->inEvent(0U).address);
        if (timer->clear() != EventFabricResult::success ||
            timer->start() != EventFabricResult::success)
        {
            return false;
        }
        *event = 0U;
        __DMB();
        initial_level = nrf_gpio_pin_read(pin);
        if (dppi->enable(0U) != EventFabricResult::success)
        {
            return false;
        }
        /** @brief DPPI enable 이전에 들어온 event를 버려 이전 CC 값을 첫 표본으로 읽지 않습니다. */
        *event = 0U;
        __DMB();
        started = true;
        const bool steady = duty == 0U || duty == 100U;
        const auto duration = top * (steady ? 100U : 125U);
        const auto origin = k_cycle_get_32();
        do
        {
            if (*event != 0U)
            {
                const auto timestamp = nrf_timer_cc_get(NRF_TIMER22, NRF_TIMER_CC_CHANNEL0);
                const auto level = nrf_gpio_pin_read(pin);
                *event = 0U;
                __DMB();
                edges[edge_count][0] = timestamp;
                edges[edge_count][1] = level;
                ++edge_count;
            }
            elapsed = k_cyc_to_us_floor32(k_cycle_get_32() - origin);
        } while (edge_count < 201U && elapsed < duration);
        final_level = nrf_gpio_pin_read(pin);
        const bool disabled = dppi->disable(0U) == EventFabricResult::success;
        const bool stopped = timer->stop() == EventFabricResult::success;
        complete = disabled && stopped && (steady ? elapsed >= duration : edge_count == 201U);
        if (!complete)
        {
            error = 1U;
        }
        return complete;
    }

    /** @brief 유한 sequence를 시작하기 전에 peer capture를 비동기로 준비합니다. */
    bool beginAsync(std::uint32_t duration)
    {
        if (role != 1U || !prepared || (started && !complete) || duration < 100000U ||
            duration > 2000000U)
        {
            return false;
        }
        if (timer->clear() != EventFabricResult::success ||
            timer->start() != EventFabricResult::success)
        {
            return false;
        }
        auto *const event = reinterpret_cast<volatile std::uint32_t *>(gpiote->inEvent(0U).address);
        *event = 0U;
        __DMB();
        initial_level = nrf_gpio_pin_read(pin);
        if (dppi->enable(0U) != EventFabricResult::success)
        {
            return false;
        }
        *event = 0U;
        __DMB();
        edge_count = elapsed = 0U;
        complete = false;
        started = asynchronous = true;
        capture_duration = duration;
        capture_origin = k_cycle_get_32();
        return true;
    }

    /** @brief 실제 DPPI TIMER 시각을 기록하며 buffer 포화와 관측 기한을 구별합니다. */
    void pollAsync()
    {
        if (role != 1U || !asynchronous)
        {
            return;
        }
        if (gpiote == nullptr || timer == nullptr || dppi == nullptr)
        {
            error = 4U;
            asynchronous = false;
            return;
        }
        auto *const event = reinterpret_cast<volatile std::uint32_t *>(gpiote->inEvent(0U).address);
        if (*event != 0U)
        {
            const auto timestamp = nrf_timer_cc_get(NRF_TIMER22, NRF_TIMER_CC_CHANNEL0);
            const auto level = nrf_gpio_pin_read(pin);
            *event = 0U;
            __DMB();
            edges[edge_count][0] = timestamp;
            edges[edge_count++][1] = level;
        }
        elapsed = k_cyc_to_us_floor32(k_cycle_get_32() - capture_origin);
        if (edge_count == edge_capacity || elapsed >= capture_duration)
        {
            final_level = nrf_gpio_pin_read(pin);
            const bool disabled = dppi->disable(0U) == EventFabricResult::success;
            const bool stopped = timer->stop() == EventFabricResult::success;
            complete = disabled && stopped && edge_count < edge_capacity;
            asynchronous = false;
            if (!complete)
            {
                error = 4U;
            }
        }
    }

    /** @brief 두 sequence 순서·반복/지연과 triggered hold에 필요한 pattern을 구성합니다. */
    bool prepareAdvanced(const std::uint32_t *args)
    {
        if (args[3] > 1U || args[4] > 1U || args[5] > 9U || args[6] > 3U || args[7] == 0U ||
            args[7] > 52U)
        {
            return false;
        }
        const std::uint32_t basic[]{args[0], args[1], args[2], 25U, 0U, 2U, 4U};
        if (!prepare(basic, 7U))
        {
            return false;
        }
        advanced = true;
        triggered = args[3] != 0U;
        repeats = args[5];
        end_delay = args[6];
        playback_count = args[7];
        const unsigned fractions[]{25U, 50U, 75U, 25U};
        for (unsigned sequence = 0U; sequence < 2U; ++sequence)
        {
            auto &buffer = advanced_dma[sequence];
            for (unsigned index = 0U; index < 4U; ++index)
            {
                buffer.before[index] = buffer.after[index] = guard_word;
            }
            for (unsigned index = 0U; index < 16U; ++index)
            {
                buffer.values[index] = 0x9669U;
            }
            for (unsigned index = 0U; index < (triggered ? 16U : 8U); ++index)
            {
                const auto selected =
                    triggered ? fractions[index / 4U] : fractions[sequence * 2U + index / 4U];
                const auto fraction = index % 4U == args[1] ? selected : 50U;
                buffer.values[index] =
                    static_cast<std::uint16_t>(0x8000U | (top * fraction / 100U));
            }
        }
        if (role == 2U)
        {
            PwmSequenceConfiguration configuration{};
            configuration.output_pins[args[1]] = PIN_P1_14;
            configuration.inverted[args[1]] = args[4] != 0U;
            configuration.top_value = static_cast<std::uint16_t>(top);
            configuration.triggered_step = triggered;
            prepared = pwm->configure(configuration) == AnalogFabricResult::success;
        }
        return prepared;
    }
} // namespace

bool pwmCaptureClaimed()
{
    return gate.claimed();
}

bool pwmCaptureNeedsPolling()
{
    return asynchronous;
}

void servicePwmCapture()
{
    pollAsync();
    if (pwm != nullptr && started)
    {
        PwmSequenceEvent event{};
        while (pwm->takeEvent(event))
        {
            if (event.type == PwmSequenceEventType::sequence0_complete)
            {
                if (advanced && !triggered && sequence0 != sequence1)
                {
                    ++event_order_errors;
                }
                ++sequence0;
            }
            else if (event.type == PwmSequenceEventType::sequence1_complete)
            {
                if (advanced && !triggered && sequence0 != sequence1 + 1U)
                {
                    ++event_order_errors;
                }
                ++sequence1;
            }
            else if (event.type == PwmSequenceEventType::playback_complete)
            {
                ++playbacks;
            }
            else if (event.type == PwmSequenceEventType::error)
            {
                error = 2U;
            }
        }
    }
    if (gate.fixture() && !gate.live(k_uptime_get()))
    {
        error = 3U;
        gate.close(stop());
    }
}

std::uint32_t pwmCaptureCommand(std::uint32_t opcode, const std::uint32_t *args,
                                std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count)
{
    servicePwmCapture();
    if (opcode == 40U && nargs == 4U)
    {
        if (fixtureClaimed() || signalClaimed() || (args[0] != 408U && args[0] != 508U) ||
            args[3] != 2U || !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()))
        {
            return 403U;
        }
        out[0] = args[0];
        out[1] = 10000U;
        count = 2U;
        return 0U;
    }
    if (opcode == 45U && nargs == 0U)
    {
        const bool stopped = stop();
        gate.close(stopped);
        out[0] = stopped ? 0U : 1U;
        out[1] = nrf_gpio_pin_dir_get(pin) == NRF_GPIO_PIN_DIR_INPUT;
        out[2] = guards();
        count = 3U;
        return stopped ? 0U : 750U;
    }
    if (opcode == 46U && nargs == 0U)
    {
        const std::uint32_t values[]{prepared,   started,       complete,    error,
                                     edge_count, initial_level, final_level, elapsed,
                                     sequence0,  sequence1,     playbacks,   guards()};
        for (unsigned index = 0U; index < 12U; ++index)
        {
            out[index] = values[index];
        }
        count = 12U;
        return 0U;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403U;
    }
    if (opcode == 58U && nargs == 0U)
    {
        out[0] = gate.renew(k_uptime_get()) ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 59U && nargs == 0U)
    {
        const std::uint32_t values[]{nrf_gpio_pin_read(pin),
                                     event_order_errors,
                                     step_count,
                                     start_connected,
                                     advanced,
                                     triggered,
                                     guards(),
                                     error};
        for (unsigned index = 0U; index < 8U; ++index)
        {
            out[index] = values[index];
        }
        count = 8U;
        return 0U;
    }
    if (opcode == 47U && nargs == 1U)
    {
        out[0] = beginAsync(args[0]) ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 54U && nargs == 8U)
    {
        out[0] = prepareAdvanced(args) ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 55U && nargs == 1U && args[0] <= 1U && role == 2U && prepared && advanced &&
        !started)
    {
        const PwmSequenceBuffer first{advanced_dma[0].values, triggered ? 16U : 8U, repeats,
                                      end_delay};
        const PwmSequenceBuffer second{advanced_dma[1].values, 8U, repeats, end_delay};
        started = pwm->play(first, triggered ? nullptr : &second,
                            static_cast<std::uint16_t>(playback_count), false,
                            true) == AnalogFabricResult::success;
        use_dppi_start = args[0] != 0U;
        bool ready = started;
        if (ready && use_dppi_start)
        {
            egu = eventFabric().egu(20U);
            start_dppi = eventFabric().dppi(20U);
            ready = egu != nullptr && start_dppi != nullptr;
            if (ready)
            {
                egu_owned = egu->acquire(0U) == EventFabricResult::success;
                ready = egu_owned;
            }
            if (ready)
            {
                start_channel_owned = start_dppi->acquireChannel(1U) == EventFabricResult::success;
                ready = start_channel_owned;
            }
            if (ready)
            {
                start_endpoint = {pwm->startTaskAddress(), 20U, EventEndpointRole::subscriber};
                start_connected = start_dppi->connect(egu->event(0U), start_endpoint, 1U) ==
                                  EventFabricResult::success;
                ready = start_connected && start_dppi->enable(1U) == EventFabricResult::success;
            }
        }
        out[0] = ready ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 56U && nargs == 0U && role == 2U && started && advanced)
    {
        bool result = false;
        if (use_dppi_start)
        {
            result = start_connected && egu->trigger(0U) == EventFabricResult::success;
        }
        else if (const auto address = pwm->startTaskAddress(); address != 0U)
        {
            *reinterpret_cast<volatile std::uint32_t *>(address) = 1U;
            __DMB();
            result = true;
        }
        out[0] = result ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 57U && nargs == 0U && role == 2U && started && triggered)
    {
        const bool result = pwm->step() == AnalogFabricResult::success;
        if (result)
        {
            ++step_count;
        }
        out[0] = result ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 41U && (nargs == 5U || nargs == 7U))
    {
        const bool result = prepare(args, nargs);
        out[0] = result ? 0U : 1U;
        count = 1U;
        return result ? 0U : 751U;
    }
    if (opcode == 42U && nargs == 0U && role == 2U && prepared && !started)
    {
        started = pwm->play({dma.values, value_count, 0U, 0U}, nullptr, 1U, true) ==
                  AnalogFabricResult::success;
        out[0] = started ? 0U : 1U;
        count = 1U;
        return started ? 0U : 752U;
    }
    if (opcode == 43U && nargs == 0U && role == 1U && prepared && !started)
    {
        const bool result = capture();
        out[0] = result ? 0U : 1U;
        count = 1U;
        /** @brief 측정 실패도 status/raw를 읽고 STOP할 수 있게 transport 응답은 유지합니다. */
        return 0U;
    }
    if (opcode == 44U && nargs == 2U && role == 1U && started && args[1] > 0U && args[1] <= 8U &&
        args[0] <= edge_count && args[1] <= edge_count - args[0])
    {
        for (unsigned index = 0U; index < args[1]; ++index)
        {
            out[index * 2U] = edges[args[0] + index][0];
            out[index * 2U + 1U] = edges[args[0] + index][1];
        }
        count = args[1] * 2U;
        return 0U;
    }
    return 400U;
}
