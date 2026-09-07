/**
 * @file pwm_capture_hil.cpp
 * @brief B P1.14 PWM을 A P1.14의 GPIOTE→DPPI→TIMER로 측정하는 첫 경로입니다.
 * @note DMA 개별 slot·정적 level·기본 주기/듀티만 판정하며 모드 전체 PASS가 아닙니다.
 * SPDX-License-Identifier: MIT
 */
#include "pwm_capture_hil.h"
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
    constexpr std::uint32_t edge_capacity = 201U;
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
    /** @brief DMA 전후 16-byte guard이며 출력값은 한 개 slot에만 설정합니다. */
    struct alignas(4) Dma
    {
        std::uint32_t before[4];
        std::uint16_t values[4];
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
        return true;
    }

    /** @brief 연결을 먼저 해제하고 STOP을 증명한 자원만 반환합니다. */
    bool stop()
    {
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
        prepared = started = false;
        pwm = nullptr;
        return true;
    }

    /** @brief instance/slot/TOP/duty/DMA 극성만 허용하고 미구현 mode는 받지 않습니다. */
    bool prepare(const std::uint32_t *args)
    {
        if (prepared || timer_owned || pin_owned || channel_owned || pwm != nullptr ||
            args[0] < 20U || args[0] > 22U || args[1] > 3U ||
            (args[2] != 1000U && args[2] != 4000U) || args[3] > 100U || args[3] % 25U ||
            args[4] > 1U)
        {
            return false;
        }
        top = args[2];
        duty = args[3];
        error = edge_count = elapsed = sequence0 = sequence1 = playbacks = 0U;
        complete = false;
        for (unsigned index = 0U; index < 4U; ++index)
        {
            dma.before[index] = dma.after[index] = guard_word;
            dma.values[index] = 0U;
        }
        if (role == 2U)
        {
            PwmSequenceConfiguration configuration{};
            configuration.output_pins[args[1]] = PIN_P1_14;
            configuration.top_value = static_cast<std::uint16_t>(top);
            /** @brief bit15=1은 HIGH→LOW, bit15=0은 LOW→HIGH이며 비교값을 반대로 만듭니다. */
            const auto compare = top * (args[4] ? duty : 100U - duty) / 100U;
            dma.values[args[1]] = static_cast<std::uint16_t>(compare | (args[4] << 15U));
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
        } while (edge_count < edge_capacity && elapsed < duration);
        final_level = nrf_gpio_pin_read(pin);
        const bool disabled = dppi->disable(0U) == EventFabricResult::success;
        const bool stopped = timer->stop() == EventFabricResult::success;
        complete =
            disabled && stopped && (steady ? elapsed >= duration : edge_count == edge_capacity);
        if (!complete)
        {
            error = 1U;
        }
        return complete;
    }
} // namespace

bool pwmCaptureClaimed()
{
    return gate.claimed();
}

void servicePwmCapture()
{
    if (pwm != nullptr && started)
    {
        PwmSequenceEvent event{};
        while (pwm->takeEvent(event))
        {
            if (event.type == PwmSequenceEventType::sequence0_complete)
            {
                ++sequence0;
            }
            else if (event.type == PwmSequenceEventType::sequence1_complete)
            {
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
        if (fixtureClaimed() || signalClaimed() || args[0] != 408U || args[3] != 2U ||
            !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()))
        {
            return 403U;
        }
        out[0] = 408U;
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
    if (opcode == 41U && nargs == 5U)
    {
        const bool result = prepare(args);
        out[0] = result ? 0U : 1U;
        count = 1U;
        return result ? 0U : 751U;
    }
    if (opcode == 42U && nargs == 0U && role == 2U && prepared && !started)
    {
        started =
            pwm->play({dma.values, 4U, 0U, 0U}, nullptr, 1U, true) == AnalogFabricResult::success;
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
