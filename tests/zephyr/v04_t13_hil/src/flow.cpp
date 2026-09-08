/** @file @brief 별도 소유한 peer RTS GPIO로100ms CTS 정지와 DUT의 실제 대기를 보존합니다. */
#include "flow.h"
#include <nucode/SerialFabric.h>
#include "internal/IoResourceManager.h"
#include <hal/nrf_gpio.h>
#include <hal/nrf_uarte.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    unsigned policy = 0U, instance = 0U, state = 0U, physical = UINT32_MAX;
    std::uint32_t start_cycle = 0U, end_cycle = 0U;
    std::uint32_t first_frames = 0U, last_frames = 0U, current_frames = 0U;
    std::uint32_t pending_seen = 0U, high_seen = 0U, low_seen = 0U;
    IoResourceToken token{};
    NRF_UARTE_Type *registers = nullptr;
    std::uint32_t background_counts[20]{}, background_times[20]{};

    /** @brief GPIO 입력으로 돌아온 뒤에만 별도 RTS 소유권을 반환합니다. */
    bool release()
    {
        if (!token.active)
        {
            return true;
        }
        nrf_gpio_cfg_input(physical, NRF_GPIO_PIN_NOPULL);
        return releaseIoResources(token) == IoResourceResult::success;
    }
} // namespace

bool t13::flowPolicy(unsigned mode)
{
    if (mode > 2U || token.active || registers != nullptr)
    {
        return false;
    }
    policy = mode;
    return true;
}

bool t13::flowPrepare(const Case &test, Endpoint &endpoint)
{
    if (policy == 0U)
    {
        return true;
    }
    const bool concurrent = (test.id == 101U && test.serial_count == 4U) ||
                            (test.id == 105U && test.serial_count == 5U);
    if (concurrent && (endpoint.kind != Kind::uart || endpoint.instance != 30U))
    {
        return true;
    }
    if ((!concurrent && test.serial_count != 1U) || test.harness != 2U || test.adc_channels ||
        test.pwm_instance || test.pdm_instance || test.i2s || endpoint.kind != Kind::uart ||
        endpoint.pin_count != 4U || endpoint.instance < 20U ||
        (endpoint.instance > 22U && endpoint.instance != 30U) || endpoint.rate != 1000000U ||
        endpoint.length != 1024U || token.active || registers != nullptr)
    {
        return false;
    }
    instance = endpoint.instance;
    physical = UINT32_MAX;
    state = start_cycle = end_cycle = first_frames = last_frames = current_frames = 0U;
    pending_seen = high_seen = low_seen = 0U;
    for (unsigned index = 0U; index < 20U; ++index)
    {
        background_counts[index] = background_times[index] = 0U;
    }
    background_times[16] = test.serial_count;
    background_times[17] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    for (unsigned index = 0U; index < 4U; ++index)
    {
        const auto signal = static_cast<SerialSignal>(endpoint.signals[index]);
        if (signal == (policy == 2U ? SerialSignal::rts : SerialSignal::cts))
        {
            physical = endpoint.pins[index];
        }
    }
    if (physical != 38U && physical != 39U && physical != 2U && physical != 3U)
    {
        return false;
    }
    if (policy == 2U)
    {
        const gpio_dt_spec gpio{physical >= 32U ? DEVICE_DT_GET(DT_NODELABEL(gpio1))
                                                : DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                                static_cast<gpio_pin_t>(physical % 32U), 0U};
        const auto resource = gpioIoResource(gpio);
        if (acquireIoResources({IoOwnerKind::application, 244U}, &resource, 1U,
                               IoAcquirePolicy::exclusive, token) != IoResourceResult::success)
        {
            return false;
        }
        unsigned count = 0U;
        for (unsigned index = 0U; index < 4U; ++index)
        {
            const auto signal = static_cast<SerialSignal>(endpoint.signals[index]);
            if (signal == SerialSignal::txd || signal == SerialSignal::rxd)
            {
                endpoint.pins[count] = endpoint.pins[index];
                endpoint.signals[count++] = endpoint.signals[index];
            }
        }
        endpoint.pin_count = count;
        if (count != 2U)
        {
            static_cast<void>(release());
            return false;
        }
        nrf_gpio_pin_clear(physical);
        nrf_gpio_cfg(physical, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_CONNECT,
                     NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_S0S1, NRF_GPIO_PIN_NOSENSE);
    }
    registers = instance == 20U   ? NRF_UARTE20
                : instance == 21U ? NRF_UARTE21
                : instance == 22U ? NRF_UARTE22
                                  : NRF_UARTE30;
    return true;
}

bool t13::flowStart()
{
    if (policy == 0U || state != 0U || registers == nullptr || registers->ENABLE == 0U ||
        nrf_gpio_pin_read(physical) != 0U)
    {
        return false;
    }
    if (policy == 1U)
    {
        state = 1U;
    }
    else
    {
        if (!token.active || registers->PSEL.RTS != NRF_UARTE_PSEL_DISCONNECTED ||
            registers->PSEL.CTS != NRF_UARTE_PSEL_DISCONNECTED)
        {
            return false;
        }
        nrf_gpio_pin_set(physical);
        start_cycle = k_cycle_get_32();
        high_seen = nrf_gpio_pin_read(physical);
        state = 2U;
    }
    return true;
}

/** @brief main service를 계속 돌리며 출력 유지 시간과 peer CTS 관측을 독립 기록합니다. */
void t13::flowService(const Endpoint &endpoint, std::uint32_t completed, bool pending)
{
    if (registers == nullptr || policy == 0U || endpoint.kind != Kind::uart ||
        endpoint.instance != instance)
    {
        return;
    }
    current_frames = completed;
    const auto now = k_cycle_get_32();
    if (policy == 2U)
    {
        if (state == 2U && k_cyc_to_us_floor32(now - start_cycle) >= 100000U)
        {
            nrf_gpio_pin_clear(physical);
            end_cycle = k_cycle_get_32();
            low_seen = nrf_gpio_pin_read(physical) == 0U ? 1U : 0U;
            state = 3U;
        }
        return;
    }
    const auto level = nrf_gpio_pin_read(physical);
    if (state == 1U && level != 0U)
    {
        state = 2U;
        start_cycle = now;
        first_frames = completed;
        high_seen = 1U;
    }
    if (state == 2U)
    {
        pending_seen |= pending ? 1U : 0U;
        if (level == 0U)
        {
            end_cycle = now;
            last_frames = completed;
            low_seen = 1U;
            state = 3U;
        }
    }
}

bool t13::flowStop()
{
    const bool released = release();
    if (released)
    {
        registers = nullptr;
    }
    return released;
}

/** @brief CTS가 실제 HIGH인 동안에만 다른 lane의 첫·마지막 완료량과 시각을 보존합니다. */
void t13::flowBackground(unsigned lane, const Endpoint &endpoint, std::uint32_t sent,
                         std::uint32_t received)
{
    if (registers == nullptr || state != 2U || lane >= max_lanes ||
        (endpoint.kind == Kind::uart && endpoint.instance == instance) ||
        nrf_gpio_pin_read(physical) == 0U)
    {
        return;
    }
    const auto bit = 1U << lane;
    const auto now = k_cycle_get_32();
    if ((background_times[0] & bit) == 0U)
    {
        background_times[0] |= bit;
        background_times[1U + lane] = now;
        background_times[11U + lane] = endpoint.instance;
        background_counts[lane * 4U] = sent;
        background_counts[lane * 4U + 2U] = received;
    }
    background_times[6U + lane] = now;
    background_counts[lane * 4U + 1U] = sent;
    background_counts[lane * 4U + 3U] = received;
}

void t13::flowBackgroundSnapshot(unsigned page, std::uint32_t *out, std::uint32_t &count)
{
    if (page > 1U)
    {
        count = 0U;
        return;
    }
    const auto *values = page == 0U ? background_counts : background_times;
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = values[index];
    }
    count = 20U;
}

void t13::flowSnapshot(std::uint32_t *out, std::uint32_t &count)
{
    std::uint32_t pin = physical;
    const auto *port = physical == UINT32_MAX ? nullptr : nrf_gpio_pin_port_decode(&pin);
    const std::uint32_t values[]{policy,
                                 instance,
                                 state,
                                 physical,
                                 start_cycle,
                                 end_cycle,
                                 CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC,
                                 first_frames,
                                 last_frames,
                                 current_frames,
                                 pending_seen,
                                 high_seen,
                                 low_seen,
                                 token.active ? 1U : 0U,
                                 port == nullptr ? UINT32_MAX : port->PIN_CNF[pin],
                                 registers == nullptr ? UINT32_MAX : registers->PSEL.TXD,
                                 registers == nullptr ? UINT32_MAX : registers->PSEL.RXD,
                                 registers == nullptr ? UINT32_MAX : registers->PSEL.RTS,
                                 registers == nullptr ? UINT32_MAX : registers->PSEL.CTS,
                                 registers == nullptr ? UINT32_MAX : registers->CONFIG};
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = values[index];
    }
    count = 20U;
}
