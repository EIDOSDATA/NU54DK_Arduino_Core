/** @file @brief 실제 parity/framing/break error와 고정 GPIO LOW의 원본을 보존합니다. */
#include "uart_fault.h"
#include "internal/IoResourceManager.h"
#include <hal/nrf_gpio.h>
#include <hal/nrf_uarte.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    unsigned policy = 0U, tx_pin = UINT32_MAX;
    std::uint32_t raw[20]{};
    NRF_UARTE_Type *registers = nullptr;
    IoResourceToken token{};
    static_assert(NRF_UARTE_ERROR_PARITY_MASK == 2U && NRF_UARTE_ERROR_FRAMING_MASK == 4U &&
                  NRF_UARTE_ERROR_BREAK_MASK == 8U);

    bool release()
    {
        if (!token.active)
        {
            return true;
        }
        nrf_gpio_cfg_input(tx_pin, NRF_GPIO_PIN_NOPULL);
        return releaseIoResources(token) == IoResourceResult::success;
    }
} // namespace

bool t13::uartFaultPolicy(unsigned mode)
{
    if (mode > 4U || registers != nullptr || token.active)
    {
        return false;
    }
    policy = mode;
    return true;
}

bool t13::uartFaultPrepare(const Case &test, const Endpoint &endpoint)
{
    if (policy == 0U)
    {
        return true;
    }
    if (test.serial_count != 1U || test.adc_channels || test.pwm_instance || test.pdm_instance ||
        test.i2s || endpoint.kind != Kind::uart || endpoint.pin_count != 4U ||
        endpoint.instance < 20U || (endpoint.instance > 22U && endpoint.instance != 30U) ||
        endpoint.rate != 1000000U || endpoint.length != 1024U || registers != nullptr ||
        token.active)
    {
        return false;
    }
    tx_pin = UINT32_MAX;
    for (unsigned index = 0U; index < 4U; ++index)
    {
        if (static_cast<SerialSignal>(endpoint.signals[index]) == SerialSignal::txd)
        {
            tx_pin = endpoint.pins[index];
        }
    }
    if (tx_pin != 36U && tx_pin != 37U && tx_pin != 0U && tx_pin != 1U)
    {
        return false;
    }
    for (auto &word : raw)
    {
        word = 0U;
    }
    raw[0] = policy;
    raw[1] = endpoint.instance;
    raw[4] = UINT32_MAX;
    raw[18] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    registers = endpoint.instance == 20U   ? NRF_UARTE20
                : endpoint.instance == 21U ? NRF_UARTE21
                : endpoint.instance == 22U ? NRF_UARTE22
                                           : NRF_UARTE30;
    return true;
}

nucode::arduino::UarteParity t13::uartFaultParity()
{
    return policy == 1U ? UarteParity::even : UarteParity::none;
}

bool t13::uartFaultTransmitAllowed()
{
    return policy == 0U || policy == 2U;
}

/** @brief 오류 주입 peer는 송신만 하며 정상 경로와 DUT 수신은 그대로 유지합니다. */
bool t13::uartFaultReceiveAllowed()
{
    return policy == 0U || policy == 1U || policy == 3U;
}

/** @brief parity peer의 RX 미시작 event·DMA 미소유를 STOP 전까지 누적 보존합니다. */
void t13::uartFaultReceiveSuppressed(bool pending)
{
    if (policy == 2U && registers != nullptr)
    {
        raw[12] |= nrf_uarte_event_check(registers, NRF_UARTE_EVENT_RXSTARTED) ? 1U : 0U;
        raw[13] |= pending ? 1U : 0U;
        raw[14] = 0x52584F46U;
    }
}

bool t13::uartFaultArm()
{
    /** @brief nrfx 초기화 뒤 ENABLE0은 정상이며 RX 시작 전에 최초 오류 관측을 준비합니다. */
    if (policy == 0U || registers == nullptr || raw[2] != 0U)
    {
        return false;
    }
    raw[2] = 1U;
    raw[9] = k_cycle_get_32();
    raw[15] = ((registers->CONFIG & UARTE_CONFIG_HWFC_Msk) ? 1U : 0U) |
              ((registers->CONFIG & UARTE_CONFIG_PARITY_Msk) ? 2U : 0U);
    raw[16] = registers->PSEL.TXD;
    raw[17] = registers->PSEL.RXD;
    return true;
}

void t13::uartFaultSubmitted(std::uint32_t cycle)
{
    if (policy == 2U && raw[2] == 1U && raw[3] == 0U)
    {
        raw[3] = 1U;
        raw[11] = cycle;
    }
}

void t13::uartFaultEvent(const nucode::arduino::UarteEvent &event, bool guards)
{
    if ((policy != 1U && policy != 3U) || raw[2] != 1U || raw[3] != 0U ||
        event.type != UarteEventType::error)
    {
        return;
    }
    raw[3] = 1U;
    raw[4] = static_cast<std::uint32_t>(event.type);
    raw[5] = event.error_mask;
    raw[6] = static_cast<std::uint32_t>(event.transferred);
    raw[7] = static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(event.buffer));
    raw[8] = guards ? 1U : 0U;
    raw[10] = k_cycle_get_32();
}

bool t13::uartFaultStop(bool serial_stopped)
{
    const bool released = release();
    if (released && serial_stopped)
    {
        raw[19] = 1U;
        registers = nullptr;
    }
    return released;
}

bool t13::uartFaultBreakReady()
{
    return policy == 4U && raw[2] == 1U && raw[3] == 0U && registers != nullptr;
}

/** @brief DUT 수신 시작 전에 peer UART를 반환한 TX net의 HIGH를 준비합니다. */
bool t13::uartFaultBreakPrepare()
{
    if (policy != 4U || raw[2] != 1U || raw[3] != 0U || raw[19] != 1U || registers != nullptr ||
        token.active)
    {
        return false;
    }
    const gpio_dt_spec gpio{tx_pin >= 32U ? DEVICE_DT_GET(DT_NODELABEL(gpio1))
                                          : DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                            static_cast<gpio_pin_t>(tx_pin % 32U), 0U};
    const auto resource = gpioIoResource(gpio);
    if (acquireIoResources({IoOwnerKind::application, 245U}, &resource, 1U,
                           IoAcquirePolicy::exclusive, token) != IoResourceResult::success)
    {
        return false;
    }
    nrf_gpio_pin_set(tx_pin);
    nrf_gpio_cfg(tx_pin, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_CONNECT, NRF_GPIO_PIN_NOPULL,
                 NRF_GPIO_PIN_S0S1, NRF_GPIO_PIN_NOSENSE);
    k_busy_wait(100U);
    raw[13] = nrf_gpio_pin_read(tx_pin) ? 1U : 0U;
    return raw[13] == 1U;
}

/** @brief 수신 시작 뒤 준비된 HIGH에서1ms LOW를 주입하고 즉시 입력으로 돌립니다. */
bool t13::uartFaultBreakPulse()
{
    if (policy != 4U || raw[2] != 1U || raw[3] != 0U || raw[19] != 1U || registers != nullptr ||
        !token.active || raw[13] != 1U || nrf_gpio_pin_read(tx_pin) == 0U)
    {
        return false;
    }
    nrf_gpio_pin_clear(tx_pin);
    raw[11] = k_cycle_get_32();
    raw[13] |= nrf_gpio_pin_read(tx_pin) == 0U ? 2U : 0U;
    k_busy_wait(1000U);
    nrf_gpio_pin_set(tx_pin);
    raw[12] = k_cycle_get_32();
    raw[13] |= nrf_gpio_pin_read(tx_pin) ? 4U : 0U;
    k_busy_wait(100U);
    raw[14] = release() ? 1U : 0U;
    raw[3] = 1U;
    return raw[13] == 7U && raw[14] == 1U;
}

void t13::uartFaultSnapshot(std::uint32_t *out, std::uint32_t &count)
{
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = raw[index];
    }
    count = 20U;
}
