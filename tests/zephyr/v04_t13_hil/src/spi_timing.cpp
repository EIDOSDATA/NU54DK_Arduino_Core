/** @file @brief 제품 설정을 바꾸지 않고 SPI20/21/22의 속도와 수신 지연을 비교합니다. */
#include "spi_timing.h"
#include <hal/nrf_spim.h>
#include <hal/nrf_spis.h>
#include <hal/nrf_gpio.h>
#include <zephyr/kernel.h>

namespace
{
    unsigned policy = 0U;

    /** @brief 진단에서 허용한 세 serial block만 반환합니다. */
    NRF_SPIM_Type *registers(unsigned instance)
    {
        switch (instance)
        {
        case 20U:
            return NRF_SPIM20;
        case 21U:
            return NRF_SPIM21;
        case 22U:
            return NRF_SPIM22;
        default:
            return nullptr;
        }
    }
} // namespace

bool t13::spiTimingPolicy(unsigned mode)
{
    if (mode > 3U)
    {
        return false;
    }
    policy = mode;
    return true;
}

bool t13::spiTimingCase(Case &test)
{
    if (policy == 0U)
    {
        return true;
    }
    if (test.harness != 2U || test.serial_count != 1U || test.adc_channels || test.pwm_instance ||
        test.pdm_instance || test.i2s)
    {
        return false;
    }
    for (auto &endpoints : test.serial)
    {
        auto &endpoint = endpoints[0];
        if (registers(endpoint.instance) == nullptr || endpoint.kind < Kind::uart ||
            endpoint.kind > Kind::twis)
        {
            return false;
        }
        if (endpoint.kind == Kind::spim || endpoint.kind == Kind::spis)
        {
            if (endpoint.rate != 8000000U)
            {
                return false;
            }
            endpoint.rate = policy == 2U ? 4000000U : 8000000U;
        }
    }
    return true;
}

bool t13::spiTimingConfigured(const Endpoint &endpoint)
{
    if (policy != 3U || endpoint.kind != Kind::spim)
    {
        return true;
    }
    auto *reg = registers(endpoint.instance);
    /** @brief nrfx는 transfer 제출 때 ENABLE을 켜므로 준비 완료 시점에는 비활성 상태입니다. */
    if (reg == nullptr || reg->ENABLE != SPIM_ENABLE_ENABLE_Disabled || endpoint.rate != 8000000U)
    {
        return false;
    }
    /** @brief 첫 DMA 제출 전에만 진단용 RXDELAY0을 적용합니다. */
    reg->IFTIMING.RXDELAY = 0U;
    return reg->IFTIMING.RXDELAY == 0U;
}

void t13::spiTimingSnapshot(const Endpoint &endpoint, std::uint32_t *out)
{
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = UINT32_MAX;
    }
    out[0] = policy;
    out[1] = static_cast<unsigned>(endpoint.kind);
    out[2] = endpoint.instance;
    out[3] = endpoint.rate;
    const auto *reg = registers(endpoint.instance);
    if (reg != nullptr && (endpoint.kind == Kind::spim || endpoint.kind == Kind::spis))
    {
        out[4] = reg->ENABLE;
        out[5] = reg->CONFIG;
        out[9] = reg->DMA.RX.AMOUNT;
        out[10] = reg->DMA.TX.AMOUNT;
        if (endpoint.kind == Kind::spim)
        {
            out[6] = reg->PRESCALER;
            out[7] = reg->IFTIMING.RXDELAY;
            out[8] = reg->IFTIMING.CSNDUR;
        }
        else
        {
            const auto *slave = reinterpret_cast<const NRF_SPIS_Type *>(reg);
            out[4] = slave->ENABLE;
            out[5] = slave->CONFIG;
            out[9] = slave->DMA.RX.AMOUNT;
            out[10] = slave->DMA.TX.AMOUNT;
        }
    }
    /** @brief 공통 수신 경로의 GPIO 설정과 디지털 수준이며 아날로그 파형 측정은 아닙니다. */
    out[11] = NRF_P1->PIN_CNF[6U];
    out[12] = NRF_P1->PIN_CNF[7U];
    out[13] = NRF_P1->IN;
    out[14] = NRF_P1->DIR;
    out[15] = NRF_P1->OUT;
    out[16] = k_cycle_get_32();
    out[17] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    out[18] = CONFIG_NUCODE_V04_HIL_ROLE;
    out[19] = 1U;
}
