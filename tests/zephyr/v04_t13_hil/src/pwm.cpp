/** @file @brief B의 PWM loop를 A의 GPIOTE/DPPI/TIMER22로 중단 없이 대조합니다. */
#include "stream_types.h"
#include <nucode/AnalogFabric.h>
#include <nucode/EventFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_timer.h>

namespace
{
    using namespace nucode::arduino;
    using namespace t13;
    constexpr unsigned role = CONFIG_NUCODE_V04_HIL_ROLE;
    auto &stats = stream_stats[1];
    PwmSequenceFabric *pwm = nullptr;
    TimerFabric *timer = nullptr;
    GpioteFabric *gpiote = nullptr;
    DppiFabric *dppi = nullptr;
    bool timer_owned = false, pin_owned = false, channel_owned = false, connected = false;
    Block<std::uint16_t, 32U> buffer;
    Edges edges;
    unsigned duty = 0U;
    std::uint32_t previous_poll = 0U;

    bool guards()
    {
        return !stats.enabled || role == 1U || buffer.guards();
    }
} // namespace

bool t13::pwmPrepare(const Case &test)
{
    stats.enabled = test.pwm_instance != 0U;
    pwm = nullptr;
    edges = {};
    previous_poll = 0U;
    duty = test.pwm_duty;
    if (!stats.enabled)
    {
        return true;
    }
    if (role == 2U)
    {
        buffer.initialize(0U);
        for (unsigned index = 0U; index < 32U; ++index)
        {
            buffer.values[index] = static_cast<std::uint16_t>(0x8000U | duty * 10U);
        }
        PwmSequenceConfiguration configuration{};
        configuration.output_pins[0] = PIN_P1_14;
        configuration.top_value = 1000U;
        configuration.load = PwmSequenceLoad::individual;
        pwm = analogFabric().pwm(test.pwm_instance);
        if (pwm == nullptr)
        {
            return stats.fail(20U);
        }
        const auto result = pwm->configure(configuration);
        return result == AnalogFabricResult::success ||
               stats.fail(1U, static_cast<std::uint32_t>(result));
    }
    timer = eventFabric().timer(22U);
    gpiote = eventFabric().gpiote(20U);
    dppi = eventFabric().dppi(20U);
    if (timer == nullptr || gpiote == nullptr || dppi == nullptr)
    {
        return stats.fail(21U);
    }
    timer_owned = timer->acquire(1000000U) == EventFabricResult::success;
    if (!timer_owned)
    {
        return stats.fail(2U);
    }
    pin_owned =
        gpiote->acquireInput(0U, PIN_P1_14, GpiotePolarity::toggle) == EventFabricResult::success;
    if (!pin_owned)
    {
        return stats.fail(3U);
    }
    channel_owned = dppi->acquireChannel(0U) == EventFabricResult::success;
    if (!channel_owned)
    {
        return stats.fail(4U);
    }
    connected = dppi->connect(gpiote->inEvent(0U), timer->task(TimerTask::capture, 0U), 0U) ==
                EventFabricResult::success;
    return connected || stats.fail(5U);
}

bool t13::pwmStart()
{
    if (!stats.enabled)
    {
        return true;
    }
    if (role == 2U)
    {
        const auto result = pwm->play({buffer.values, 32U, 0U, 0U}, nullptr, 1U, true);
        stats.active = result == AnalogFabricResult::success;
        stats.queued = stats.active ? 1U : 0U;
        return stats.active || stats.fail(6U, static_cast<std::uint32_t>(result));
    }
    auto *event = reinterpret_cast<volatile std::uint32_t *>(gpiote->inEvent(0U).address);
    if (timer->clear() != EventFabricResult::success ||
        timer->start() != EventFabricResult::success)
    {
        return stats.fail(7U);
    }
    *event = 0U;
    __DMB();
    stats.active = dppi->enable(0U) == EventFabricResult::success;
    return stats.active || stats.fail(8U);
}

void t13::captureService()
{
    if (role != 1U || !stats.active || stats.error != 0U)
    {
        return;
    }
    const auto cycle = k_cycle_get_32();
    if (previous_poll != 0U)
    {
        const auto gap = k_cyc_to_us_floor32(cycle - previous_poll);
        edges.maximum_poll_gap = gap > edges.maximum_poll_gap ? gap : edges.maximum_poll_gap;
    }
    previous_poll = cycle;
    auto *event = reinterpret_cast<volatile std::uint32_t *>(gpiote->inEvent(0U).address);
    if (*event != 0U)
    {
        /** @brief CC0는 DPPI만 기록하며 누락·늦은 GPIO level 관측은 간격/교대 오류로 남깁니다. */
        const auto timestamp = nrf_timer_cc_get(NRF_TIMER22, NRF_TIMER_CC_CHANNEL0);
        const auto level = nrf_gpio_pin_read(NRF_GPIO_PIN_MAP(1, 14));
        *event = 0U;
        __DMB();
        if (!edges.consume(timestamp, level, duty))
        {
            stats.fail(9U, edges.count);
        }
    }
}

void t13::pwmService()
{
    if (role != 2U || !stats.active || stats.error != 0U)
    {
        return;
    }
    PwmSequenceEvent event{};
    while (pwm->takeEvent(event))
    {
        if (event.type == PwmSequenceEventType::sequence0_complete ||
            event.type == PwmSequenceEventType::sequence1_complete)
        {
            ++stats.completed;
        }
        else if (event.type == PwmSequenceEventType::playback_complete)
        {
            ++stats.extra[0];
        }
        else
        {
            stats.fail(10U, static_cast<std::uint32_t>(event.type));
        }
    }
    if (!guards())
    {
        stats.fail(11U);
    }
}

bool t13::pwmStop()
{
    if (pwm != nullptr && pwm->state() == AnalogFabricState::faulted)
    {
        return stats.fail(12U);
    }
    if (pwm != nullptr &&
        (pwm->state() == AnalogFabricState::active || pwm->state() == AnalogFabricState::stopping))
    {
        const auto result = pwm->stop(100000U);
        if (result != AnalogFabricResult::success)
        {
            return stats.fail(13U, static_cast<std::uint32_t>(result));
        }
    }
    stats.active = false;
    if (role == 2U)
    {
        return guards() || stats.fail(19U);
    }
    if (channel_owned)
    {
        if (dppi->disable(0U) != EventFabricResult::success)
        {
            return stats.fail(14U);
        }
        if (connected && dppi->disconnect(gpiote->inEvent(0U), timer->task(TimerTask::capture, 0U),
                                          0U) != EventFabricResult::success)
        {
            return stats.fail(15U);
        }
        connected = false;
        if (dppi->releaseChannel(0U) != EventFabricResult::success)
        {
            return stats.fail(16U);
        }
        channel_owned = false;
    }
    if (pin_owned)
    {
        if (gpiote->release(0U) != EventFabricResult::success)
        {
            return stats.fail(17U);
        }
        pin_owned = false;
    }
    if (timer_owned)
    {
        if (timer->stop() != EventFabricResult::success ||
            timer->release() != EventFabricResult::success)
        {
            return stats.fail(18U);
        }
        timer_owned = false;
    }
    return guards() || stats.fail(19U);
}

bool t13::pwmHealthy()
{
    return stats.error == 0U;
}

void t13::pwmSnapshot(std::uint32_t *out)
{
    stats.snapshot(1U, guards(), out);
    if (role == 1U)
    {
        out[4] = out[6] = edges.count;
        out[9] = edges.high_min;
        out[10] = edges.high_max;
        out[11] = edges.low_min;
        out[12] = edges.low_max;
        out[14] = edges.first;
        out[15] = edges.last;
        out[16] = edges.maximum_poll_gap;
    }
}
