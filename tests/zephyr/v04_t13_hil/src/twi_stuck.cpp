/** @file @brief 활성 DMA 없이 SDA LOW100ms와 staged recoverBus의 실제 오류·복구를 보존합니다. */
#include "twi_stuck.h"
#include "internal/IoResourceManager.h"
#include <hal/nrf_gpio.h>
#include <hal/nrf_twim.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <errno.h>

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    unsigned policy = 0U;
    std::uint32_t raw[20]{}, recovery[2][20]{};
    SerialFabricHandle *handle = nullptr;
    const t13::Buffer *tx = nullptr, *rx = nullptr;
    const NRF_TWIM_Type *registers = nullptr;
    IoResourceToken token{};
    unsigned sda = 42U, scl = 46U;
    static_assert(ECANCELED == 140 &&
                  static_cast<unsigned>(SerialFabricResult::driver_error) == 10U);

    bool guards()
    {
        return tx != nullptr && rx != nullptr && tx[0].guards(256U) && tx[1].guards(256U) &&
               rx[0].guards(256U) && rx[1].guards(256U);
    }

    /** @brief API가 네 DMA buffer를 모두 application 소유로 보고하는지 독립 확인합니다. */
    std::uint32_t buffers()
    {
        if (handle == nullptr || tx == nullptr || rx == nullptr)
        {
            return 0U;
        }
        std::uint32_t flags = 0U;
        const void *addresses[]{tx[0].data(), tx[1].data(), rx[0].data(), rx[1].data()};
        for (unsigned index = 0U; index < 4U; ++index)
        {
            const auto state =
                policy == 1U ? static_cast<TwimHandle *>(handle)->bufferState(addresses[index])
                             : static_cast<TwisHandle *>(handle)->bufferState(addresses[index]);
            flags |= state == DmaBufferState::application_owned ? 1U << index : 0U;
        }
        return flags;
    }

    bool staged()
    {
        return handle != nullptr && registers != nullptr &&
               handle->state() == SerialFabricState::staged && registers->ENABLE == 0U &&
               buffers() == 15U && guards();
    }

    std::uint32_t pinConfig(unsigned physical)
    {
        return physical >= 32U ? NRF_P1->PIN_CNF[physical - 32U] : NRF_P0->PIN_CNF[physical];
    }
} // namespace

bool t13::twiStuckPolicy(unsigned mode)
{
    if (mode > 2U || token.active || (handle != nullptr && raw[19] != 1U))
    {
        return false;
    }
    policy = mode;
    handle = nullptr;
    registers = nullptr;
    tx = rx = nullptr;
    return true;
}

bool t13::twiStuckEnabled()
{
    return policy != 0U;
}

bool t13::twiStuckSelection(const Case &test, const Endpoint &endpoint)
{
    if (policy == 0U)
    {
        return true;
    }
    if (test.id < 16U || test.id > 19U || test.harness != 2U || test.serial_count != 1U ||
        test.adc_channels || test.pwm_instance || test.pdm_instance || test.i2s ||
        endpoint.kind != (policy == 1U ? Kind::twim : Kind::twis) || endpoint.pin_count != 2U ||
        endpoint.length != 256U || endpoint.rate != 400000U)
    {
        return false;
    }
    const unsigned expected_instance = test.id == 19U ? 30U : test.id + 4U;
    if (endpoint.instance != expected_instance)
    {
        return false;
    }
    const unsigned expected_sda = endpoint.instance == 30U ? 0U : 42U;
    const unsigned expected_scl = endpoint.instance == 30U ? 1U : 46U;
    for (unsigned index = 0U; index < 2U; ++index)
    {
        const auto signal = static_cast<SerialSignal>(endpoint.signals[index]);
        if (!((signal == SerialSignal::sda && endpoint.pins[index] == expected_sda) ||
              (signal == SerialSignal::scl && endpoint.pins[index] == expected_scl)))
        {
            return false;
        }
    }
    return endpoint.signals[0] != endpoint.signals[1];
}

bool t13::twiStuckPrepare(const Endpoint &endpoint, SerialFabricHandle &selected,
                          const Buffer *transmit, const Buffer *receive)
{
    if (policy == 0U || handle != nullptr || token.active)
    {
        return false;
    }
    handle = &selected;
    tx = transmit;
    rx = receive;
    sda = endpoint.instance == 30U ? 0U : 42U;
    scl = endpoint.instance == 30U ? 1U : 46U;
    registers = endpoint.instance == 20U   ? NRF_TWIM20
                : endpoint.instance == 21U ? NRF_TWIM21
                : endpoint.instance == 22U ? NRF_TWIM22
                                           : NRF_TWIM30;
    for (auto &value : raw)
    {
        value = 0U;
    }
    for (auto &attempt : recovery)
    {
        for (auto &value : attempt)
        {
            value = 0U;
        }
    }
    raw[0] = policy;
    raw[1] = endpoint.instance;
    raw[2] = 1U;
    raw[4] = sda;
    raw[5] = scl;
    raw[18] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    if (!staged())
    {
        return false;
    }
    if (policy == 2U)
    {
        const gpio_dt_spec gpio{sda >= 32U ? DEVICE_DT_GET(DT_NODELABEL(gpio1))
                                           : DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                                static_cast<gpio_pin_t>(sda % 32U), 0U};
        const auto resource = gpioIoResource(gpio);
        if (acquireIoResources({IoOwnerKind::application, 246U}, &resource, 1U,
                               IoAcquirePolicy::exclusive, token) != IoResourceResult::success)
        {
            return false;
        }
        nrf_gpio_pin_set(sda);
        nrf_gpio_cfg(sda, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_CONNECT, NRF_GPIO_PIN_PULLUP,
                     NRF_GPIO_PIN_S0D1, NRF_GPIO_PIN_NOSENSE);
        raw[10] = (nrf_gpio_pin_dir_get(sda) == NRF_GPIO_PIN_DIR_OUTPUT ? 1U : 0U) |
                  (nrf_gpio_pin_input_get(sda) == NRF_GPIO_PIN_INPUT_CONNECT ? 2U : 0U) |
                  (nrf_gpio_pin_pull_get(sda) == NRF_GPIO_PIN_PULLUP ? 4U : 0U) |
                  (nrf_gpio_pin_drive_get(sda) == NRF_GPIO_PIN_S0D1 ? 8U : 0U);
        raw[3] = 1U;
        return nrf_gpio_pin_read(sda) == 1U && raw[10] == 15U;
    }
    return true;
}

bool t13::twiStuckStart()
{
    if (policy != 2U || raw[3] != 1U || !token.active || !staged() || nrf_gpio_pin_read(sda) != 1U)
    {
        return false;
    }
    nrf_gpio_pin_clear(sda);
    raw[6] = k_cycle_get_32();
    raw[8] = nrf_gpio_pin_read(sda) == 0U ? 1U : 0U;
    raw[3] = 2U;
    return raw[8] == 1U;
}

void t13::twiStuckService()
{
    if (policy == 2U && token.active && raw[3] == 2U &&
        k_cyc_to_us_floor32(k_cycle_get_32() - raw[6]) >= 100000U)
    {
        nrf_gpio_pin_set(sda);
        raw[7] = k_cycle_get_32();
        raw[9] = nrf_gpio_pin_read(sda);
        raw[3] = 3U;
    }
}

bool t13::twiStuckRecover(unsigned attempt)
{
    if (policy != 1U || attempt > 1U || raw[3] != attempt || !staged())
    {
        return false;
    }
    auto &meta = recovery[attempt];
    meta[0] = attempt;
    meta[1] = static_cast<std::uint32_t>(handle->state());
    meta[3] = registers->ENABLE;
    meta[5] = pinConfig(sda);
    meta[7] = pinConfig(scl);
    meta[9] = sda;
    meta[10] = scl;
    meta[11] = buffers();
    meta[13] = guards() ? 1U : 0U;
    meta[15] = nrf_gpio_pin_read(sda);
    const unsigned first = attempt == 0U ? 6U : 11U;
    raw[first] = k_cycle_get_32();
    const auto result = static_cast<TwimHandle *>(handle)->recoverBus();
    raw[first + 1U] = k_cycle_get_32();
    meta[17] = raw[first + 2U] = static_cast<std::uint32_t>(result);
    meta[18] = raw[first + 3U] = static_cast<std::uint32_t>(handle->lastDriverError());
    meta[2] = static_cast<std::uint32_t>(handle->state());
    meta[4] = registers->ENABLE;
    meta[6] = pinConfig(sda);
    meta[8] = pinConfig(scl);
    meta[12] = buffers();
    meta[14] = guards() ? 1U : 0U;
    meta[16] = nrf_gpio_pin_read(sda);
    meta[19] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    raw[first + 4U] = meta[15] | (meta[16] << 1U);
    ++raw[3];
    return true;
}

bool t13::twiStuckStop()
{
    if (policy == 0U)
    {
        return true;
    }
    if (token.active)
    {
        if (raw[3] == 2U)
        {
            raw[7] = k_cycle_get_32();
            raw[3] = 4U;
        }
        nrf_gpio_cfg_input(sda, NRF_GPIO_PIN_NOPULL);
        if (releaseIoResources(token) != IoResourceResult::success)
        {
            return false;
        }
    }
    raw[16] = guards() ? 1U : 0U;
    raw[17] = handle == nullptr ? UINT32_MAX : static_cast<std::uint32_t>(handle->state());
    raw[19] = handle == nullptr || staged() ? 1U : 0U;
    return raw[19] == 1U;
}

bool t13::twiStuckStaged(const SerialFabricHandle &selected)
{
    return policy != 0U && handle == &selected && !token.active && staged();
}

void t13::twiStuckSnapshot(unsigned page, std::uint32_t *out, std::uint32_t &count)
{
    if (page > 2U)
    {
        count = 0U;
        return;
    }
    raw[16] = guards() ? 1U : 0U;
    raw[17] = handle == nullptr ? UINT32_MAX : static_cast<std::uint32_t>(handle->state());
    if (policy == 2U)
    {
        raw[11] = token.active ? 1U : 0U;
        raw[12] = nrf_gpio_pin_read(sda);
        raw[13] = registers == nullptr ? UINT32_MAX : registers->ENABLE;
    }
    const auto *values = page == 0U ? raw : recovery[page - 1U];
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = values[index];
    }
    count = 20U;
}
